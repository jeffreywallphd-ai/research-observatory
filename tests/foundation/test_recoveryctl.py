from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import planctl  # noqa: E402
import recoveryctl  # noqa: E402
import taskctl  # noqa: E402


def identity_packet(request: str, wave: str, amendment_count: int) -> dict:
    amendments = []
    for index in range(1, amendment_count + 1):
        amendments.append(
            {
                "id": f"{wave}.A{index:02d}",
                "changeRequestId": None if index == 1 else f"ECR-{index - 1:04d}",
            }
        )
    next_amendment = f"{wave}.A{amendment_count + 1:02d}"
    return {
        "recoveryRequestId": request,
        "targetWave": wave,
        "authorityChain": {"waveBase": {"waveId": wave}, "orderedAmendments": amendments},
        "controlHold": {"id": f"HOLD-{wave}-{request}"},
        "bootstrapUnit": {"id": f"{request}.B00"},
        "postBootstrap": {
            "requiredChangeRequestId": f"ECR-{max(amendment_count - 1, 0) + 1:04d}",
            "requiredAmendmentId": next_amendment,
            "requiredProposedTaskIds": [f"{next_amendment}.T01", f"{next_amendment}.T02"],
            "postBootstrapExecutionAuthority": False,
            "ordinaryWaveResumeAuthorized": False,
        },
    }


class GovernanceRecoveryTests(unittest.TestCase):
    @staticmethod
    def git(repo: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        return result.stdout.strip()

    def append_fixture(self, temporary: str) -> tuple[Path, argparse.Namespace, bytes]:
        repo = Path(temporary) / "append-fixture"
        bundle = Path(temporary) / "fixture.bundle"
        subprocess.run(
            ["git", "bundle", "create", str(bundle), "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "clone", "--quiet", str(bundle), str(repo)],
            capture_output=True,
            text=True,
            check=True,
        )
        self.git(repo, "config", "user.email", "fixture@example.invalid")
        self.git(repo, "config", "user.name", "Fixture Reviewer")
        self.git(repo, "config", "commit.gpgsign", "false")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-b", "codex/append-fixture")
        shutil.copy2(REPO / "tools/taskctl.py", repo / "tools/taskctl.py")
        shutil.copy2(REPO / "tools/planctl.py", repo / "tools/planctl.py")
        backlog_path = repo / "planning/backlog.yaml"
        backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
        hold = (backlog["control_plane"]["recovery_holds"])[0]
        ledger_path = repo / hold["bootstrap"]["attempts"][-1]["ledger"]["path"]
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger.update(result="approved", findings=[], closures=[], notes="Approved fixture recovery.")
        ledger_payload = (json.dumps(ledger, indent=2) + "\n").encode()
        ledger_path.write_bytes(ledger_payload)
        review = {
            "reviewer": ledger["reviewer"],
            "result": "approved",
            "reviewed_at": "2026-08-22T18:00:00+00:00",
            "notes": "Approved fixture recovery.",
        }
        hold["bootstrap"]["attempts"][-1]["review"] = copy.deepcopy(review)
        hold["bootstrap"]["attempts"][-1]["ledger"]["sha256"] = hashlib.sha256(ledger_payload).hexdigest()
        hold["bootstrap"].update(status="APPROVED", review=review, current_submission=None)
        proposal_path = repo / "planning/enabler-change-requests/ECR-0002.md"
        review_path = repo / "planning/enabler-change-requests/ECR-0002-review.html"
        proposal_path.write_bytes(b"# Fixture ECR-0002\n")
        review_path.write_bytes(b"<!doctype html><title>Fixture ECR-0002</title>\n")
        recovery_authority = json.loads(
            (repo / "planning/governance-recovery-requests/GRR-0001.packet.json").read_text(encoding="utf-8")
        )["authorityChain"]
        authority = {
            "waveBase": recovery_authority["waveBase"],
            "orderedAmendments": [
                {
                    "id": item["id"],
                    "changeRequestId": item["changeRequestId"],
                    "status": item["status"],
                    "packetCommit": item["packetCommit"],
                    "approvalReference": item["approvalRecord"],
                    "effectiveStateCommit": item["effectiveStateCommit"],
                }
                for item in recovery_authority["orderedAmendments"]
            ],
        }
        packet: dict[str, Any] = {
            "$schema": "./enabler-change-request.v2.schema.json",
            "schemaVersion": "2.0-proposal",
            "documentType": "enabler-change-request-packet",
            "changeRequestId": "ECR-0002",
            "proposedAmendmentId": "W1.A03",
            "targetWave": "W1",
            "status": "pending-approval",
            "executionState": "non-executable",
            "classification": "gate-integrity-safety-defect",
            "authorityChain": authority,
            "activationBoundary": {
                "waveStatus": "PAUSED",
                "ordinaryTaskStatesDenied": ["IN_PROGRESS", "REVIEW"],
                "reviewCandidateMutationDenied": True,
                "otherEnablerCampaignDenied": True,
                "recoveryHoldId": hold["id"],
            },
            "bootstrapUnit": {
                "id": "W1.A03.B00",
                "kind": "append-only-amendment-bootstrap",
                "exceptionReason": "Executable append fixture.",
                "authorizedPaths": ["tools/fixture-a03.txt"],
                "requiredOutcomes": ["Append the exact subsequent amendment."],
                "prohibitedOutcomes": ["Do not alter predecessors."],
            },
            "authorizedTaskIds": ["W1.A03.T01"],
            "taskInventory": [
                {
                    "id": "W1.A03.T01",
                    "title": "Fixture task",
                    "objective": "Exercise the append lane.",
                    "dependencies": ["W1.A03.B00"],
                    "acceptanceCriteria": ["The fixture appends."],
                    "verification": ["Run the fixture test."],
                }
            ],
            "acceptanceCriteria": ["The exact amendment is appended."],
            "verificationObligations": ["Validate semantic authority and CAS persistence."],
            "rollback": ["Retain predecessor authority."],
            "nonGoals": ["No product work."],
            "files": [],
        }
        schema_path = repo / "planning/enabler-change-requests/enabler-change-request.v2.schema.json"
        for path, role in (
            (proposal_path, "canonical-proposal"),
            (schema_path, "proposal-schema"),
            (review_path, "human-review"),
        ):
            packet["files"].append(
                {
                    "path": path.relative_to(repo).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "role": role,
                }
            )
        packet_path = repo / "planning/enabler-change-requests/ECR-0002.packet.json"
        packet_path.write_bytes((json.dumps(packet, indent=2) + "\n").encode())
        backlog_path.write_bytes(yaml.safe_dump(backlog, sort_keys=False, width=120).encode())
        self.git(repo, "add", "--all")
        self.git(repo, "commit", "-m", "test: freeze ECR-0002 packet")
        packet_commit = self.git(repo, "rev-parse", "HEAD")
        packet_payload = packet_path.read_bytes()
        approval = {
            "schemaVersion": "1.0",
            "documentType": "wave-amendment-approval",
            "amendmentId": "W1.A03",
            "changeRequestId": "ECR-0002",
            "targetWave": "W1",
            "status": "APPROVED",
            "approvedBy": "repository-owner",
            "approvedAt": "2026-08-22T18:01:00+00:00",
            "decision": "Approve executable append fixture.",
            "packet": {
                "path": "planning/enabler-change-requests/ECR-0002.packet.json",
                "sha256": hashlib.sha256(packet_payload).hexdigest(),
                "commit": packet_commit,
                "proposalPath": "planning/enabler-change-requests/ECR-0002.md",
                "proposalSha256": hashlib.sha256(proposal_path.read_bytes()).hexdigest(),
            },
            "effectiveBase": authority,
            "authorizedTaskIds": ["W1.A03.T01"],
            "bootstrapUnit": "W1.A03.B00",
            "independentPacketReview": {
                "reviewer": "fixture-independent-reviewer",
                "result": "APPROVED",
                "candidateCommit": packet_commit,
            },
        }
        approval_path = repo / "planning/wave-amendment-approvals/W1.A03.json"
        approval_path.write_bytes((json.dumps(approval, indent=2) + "\n").encode())
        self.git(repo, "add", approval_path.relative_to(repo).as_posix())
        self.git(repo, "commit", "-m", "test: approve ECR-0002")
        approval_commit = self.git(repo, "rev-parse", "HEAD")
        marker = repo / "tools/fixture-a03.txt"
        marker.write_bytes(b"fixture\n")
        self.git(repo, "add", marker.relative_to(repo).as_posix())
        self.git(repo, "commit", "-m", "test: implement W1.A03.B00")
        implementation_commit = self.git(repo, "rev-parse", "HEAD")
        branch = self.git(repo, "branch", "--show-current")
        evidence_path = repo / "artifacts/evidence/W1.A03.B00.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence = {
            "schemaVersion": "1.0",
            "documentType": "task-criterion-evidence",
            "taskId": "W1.A03.B00",
            "commit": implementation_commit,
            "baseCommit": approval_commit,
            "branch": branch,
            "changedFiles": ["tools/fixture-a03.txt"],
            "checks": [{"command": "fixture append", "exitCode": 0, "result": "passed"}],
            "acceptanceCriteria": [{"criterion_index": 1, "evidence": ["The real append command passed."]}],
            "unverifiedItems": [],
        }
        evidence_path.write_bytes((json.dumps(evidence, indent=2) + "\n").encode())
        before = backlog_path.read_bytes()
        args = argparse.Namespace(
            amendment="W1.A03",
            agent="fixture-agent",
            approval_commit=approval_commit,
            implementation_commit=implementation_commit,
            evidence="artifacts/evidence/W1.A03.B00.json",
            file=str(backlog_path),
            source_sha256=hashlib.sha256(before).hexdigest(),
        )
        return repo, args, before

    def test_canonical_recovery_authority_and_hold_validate(self) -> None:
        approval, packet, hold = recoveryctl.validate_request(REPO, "GRR-0001")
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual("W1.A03", packet["postBootstrap"]["requiredAmendmentId"])
        self.assertEqual("ACTIVE", hold["status"])
        status = hold["bootstrap"]["status"]
        self.assertIn(status, {"IN_PROGRESS", "REVIEW", "CHANGES_REQUESTED", "BLOCKED", "APPROVED"})
        if status == "REVIEW":
            self.assertIsNotNone(hold["bootstrap"]["current_submission"])
        else:
            self.assertIsNone(hold["bootstrap"]["current_submission"])
        if status in {"CHANGES_REQUESTED", "BLOCKED", "APPROVED"}:
            self.assertTrue(hold["bootstrap"]["attempts"])
            expected = {
                "changes-requested": "CHANGES_REQUESTED",
                "blocked": "BLOCKED",
                "approved": "APPROVED",
            }
            self.assertEqual(
                status,
                expected[hold["bootstrap"]["attempts"][-1]["review"]["result"]],
            )

    def test_second_and_third_recovery_identities_are_generic(self) -> None:
        for request, wave, amendment_count in (("GRR-0002", "W2", 2), ("GRR-0003", "W10", 3)):
            with self.subTest(request=request):
                self.assertEqual(
                    [],
                    recoveryctl.recovery_identity_errors(identity_packet(request, wave, amendment_count)),
                )

    def test_cross_wave_gapped_and_mismatched_identities_fail(self) -> None:
        packet = identity_packet("GRR-0002", "W2", 2)
        packet["authorityChain"]["orderedAmendments"][1]["id"] = "W3.A02"
        packet["postBootstrap"]["requiredProposedTaskIds"] = ["W2.A04.T01"]
        errors = recoveryctl.recovery_identity_errors(packet)
        self.assertTrue(any("predecessor" in error for error in errors))
        self.assertTrue(any("task" in error for error in errors))

    def test_generic_ecr_schema_accepts_second_and_third_amendments(self) -> None:
        schema = json.loads(
            (REPO / "planning/enabler-change-requests/enabler-change-request.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        for wave, amendment, ecr in (("W2", "W2.A03", "ECR-0002"), ("W10", "W10.A04", "ECR-0003")):
            task_id = f"{amendment}.T01"
            packet = {
                "$schema": "./enabler-change-request.v2.schema.json",
                "schemaVersion": "2.0-proposal",
                "documentType": "enabler-change-request-packet",
                "changeRequestId": ecr,
                "proposedAmendmentId": amendment,
                "targetWave": wave,
                "status": "pending-approval",
                "executionState": "non-executable",
                "classification": "gate-integrity-safety-defect",
                "authorityChain": {
                    "waveBase": {"waveId": wave, "packetCommit": "a" * 40, "approvalRecordCommit": "b" * 40},
                    "orderedAmendments": [
                        {
                            "id": f"{wave}.A01",
                            "changeRequestId": None,
                            "status": "ADOPTED",
                            "packetCommit": "c" * 40,
                            "approvalReference": {
                                "path": f"planning/wave-amendment-approvals/{wave}.A01.json",
                                "sha256": "d" * 64,
                                "introductionCommit": "e" * 40,
                            },
                            "effectiveStateCommit": "f" * 40,
                        }
                    ],
                },
                "activationBoundary": {
                    "waveStatus": "PAUSED",
                    "ordinaryTaskStatesDenied": ["IN_PROGRESS", "REVIEW"],
                    "reviewCandidateMutationDenied": True,
                    "otherEnablerCampaignDenied": True,
                    "recoveryHoldId": f"HOLD-{wave}-GRR-0002",
                },
                "bootstrapUnit": {
                    "id": f"{amendment}.B00",
                    "kind": "append-only-amendment-bootstrap",
                    "exceptionReason": "test fixture",
                    "authorizedPaths": ["tools/taskctl.py"],
                    "requiredOutcomes": ["outcome"],
                    "prohibitedOutcomes": ["no bypass"],
                },
                "authorizedTaskIds": [task_id],
                "taskInventory": [
                    {
                        "id": task_id,
                        "title": "fixture",
                        "objective": "fixture",
                        "dependencies": [f"{amendment}.B00"],
                        "acceptanceCriteria": ["criterion"],
                        "verification": ["check"],
                    }
                ],
                "acceptanceCriteria": ["criterion"],
                "verificationObligations": ["check"],
                "rollback": ["hold"],
                "nonGoals": ["no bypass"],
                "files": [
                    {
                        "path": f"planning/enabler-change-requests/{ecr}.md",
                        "sha256": "1" * 64,
                        "role": "canonical-proposal",
                    },
                    {
                        "path": "planning/enabler-change-requests/enabler-change-request.v2.schema.json",
                        "sha256": "2" * 64,
                        "role": "proposal-schema",
                    },
                    {
                        "path": f"planning/enabler-change-requests/{ecr}-review.html",
                        "sha256": "3" * 64,
                        "role": "human-review",
                    },
                ],
            }
            with self.subTest(amendment=amendment):
                self.assertEqual([], list(Draft202012Validator(schema).iter_errors(packet)))

    def test_real_second_ecr_and_third_amendment_append_is_semantic_atomic_and_preserving(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as temporary:
            repo, args, before = self.append_fixture(temporary)
            self.assertEqual([], planctl.ecr_validation_errors(repo, "ECR-0002", require_approved=True))

            def loaded() -> tuple[dict, dict, dict, dict, dict]:
                return taskctl.load(args.file)

            denial_cases: list[tuple[str, argparse.Namespace, tuple[dict, dict, dict, dict, dict]]] = []
            duplicate = copy.deepcopy(args)
            duplicate.amendment = "W1.A02"
            denial_cases.append(("duplicate", duplicate, loaded()))
            nonconsecutive = copy.deepcopy(args)
            nonconsecutive.amendment = "W1.A04"
            denial_cases.append(("nonconsecutive", nonconsecutive, loaded()))
            wrong_hold_state = loaded()
            wrong_hold_state[0]["control_plane"]["recovery_holds"][0]["post_bootstrap"]["required_amendment_id"] = (
                "W1.A04"
            )
            denial_cases.append(("wrong-hold", copy.deepcopy(args), wrong_hold_state))
            wrong_task_state = loaded()
            wrong_task_state[0]["control_plane"]["recovery_holds"][0]["post_bootstrap"][
                "required_proposed_task_ids"
            ] = ["W1.A03.T02"]
            denial_cases.append(("wrong-task", copy.deepcopy(args), wrong_task_state))
            reordered_state = loaded()
            reordered_state[0]["wave_amendments"].reverse()
            denial_cases.append(("reordered", copy.deepcopy(args), reordered_state))
            stale = copy.deepcopy(args)
            stale.source_sha256 = "0" * 64
            denial_cases.append(("stale", stale, loaded()))
            for label, denied_args, state in denial_cases:
                with self.subTest(label=label), self.assertRaises(SystemExit):
                    taskctl.command_amendment_append_bootstrap_submit(denied_args, *state)
                self.assertEqual(before, Path(args.file).read_bytes())

            packet_path = repo / "planning/enabler-change-requests/ECR-0002.packet.json"
            original_packet = packet_path.read_bytes()
            packet = json.loads(original_packet)
            packet["authorityChain"]["orderedAmendments"].reverse()
            packet_path.write_bytes((json.dumps(packet, indent=2) + "\n").encode())
            errors = planctl.ecr_validation_errors(repo, "ECR-0002", require_approved=False)
            self.assertTrue(any("gapped, reordered, duplicated, or forked" in error for error in errors))
            self.assertEqual(before, Path(args.file).read_bytes())
            packet_path.write_bytes(original_packet)

            state = loaded()
            predecessor_snapshot = taskctl.exact_record_snapshot(state[0], "wave_amendments")
            taskctl.command_amendment_append_bootstrap_submit(args, *state)
            appended = yaml.safe_load(Path(args.file).read_text(encoding="utf-8"))
            self.assertEqual(["W1.A01", "W1.A02", "W1.A03"], [item["id"] for item in appended["wave_amendments"]])
            self.assertEqual(
                predecessor_snapshot,
                taskctl.exact_record_snapshot(
                    appended,
                    "wave_amendments",
                    identities={"W1.A01", "W1.A02"},
                ),
            )

    def test_unsafe_and_redirected_control_paths_fail_before_access(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as temporary:
            root = Path(temporary)
            (root / "safe").mkdir()
            (root / "safe" / "record.json").write_text("{}", encoding="utf-8")
            for relative in ("/absolute.json", "safe\\record.json", "safe/../record.json", "safe/./record.json"):
                with self.subTest(relative=relative), self.assertRaises(SystemExit):
                    recoveryctl.safe_repo_path(root, relative, label="fixture")
            link = root / "redirect"
            try:
                link.symlink_to(root / "safe", target_is_directory=True)
            except OSError:
                with (
                    patch.object(recoveryctl, "is_junction", side_effect=lambda path: path.name == "safe"),
                    self.assertRaisesRegex(SystemExit, "symlink or junction"),
                ):
                    recoveryctl.safe_repo_path(root, "safe/record.json", label="fixture")
            else:
                with self.assertRaisesRegex(SystemExit, "symlink or junction"):
                    recoveryctl.safe_repo_path(root, "redirect/record.json", label="fixture")

    def test_recovery_artifact_entry_rejects_raw_absolute_backslash_and_dot_segments(self) -> None:
        canonical = "planning/governance-recovery-approvals/GRR-0001.B00.evidence.json"
        variants = (
            str((REPO / canonical).resolve()),
            canonical.replace("/", "\\"),
            canonical.replace("approvals/", "approvals/./"),
            canonical.replace("approvals/", "approvals/../governance-recovery-approvals/"),
        )
        for value in variants:
            with (
                self.subTest(value=value),
                patch.object(taskctl, "canonical_control_artifact_path") as artifact_access,
                self.assertRaises(SystemExit),
            ):
                recoveryctl.evidence_relative(REPO, value, "GRR-0001", "GRR-0001.B00")
            artifact_access.assert_not_called()
        review_path = "planning/governance-recovery-approvals/GRR-0001.B00.review-R02.json"
        bootstrap = {"id": "GRR-0001.B00", "current_submission": {"attempt_id": "R02"}}
        for value in (
            str((REPO / review_path).resolve()),
            review_path.replace("/", "\\"),
            review_path.replace("approvals/", "approvals/./"),
        ):
            args = argparse.Namespace(
                request="GRR-0001",
                repo=REPO,
                from_path=value,
                reviewer="independent-reviewer",
            )
            with (
                self.subTest(review_value=value),
                patch.object(taskctl, "canonical_control_artifact_path") as artifact_access,
                self.assertRaises(SystemExit),
            ):
                recoveryctl.review_ledger(args, {"acceptanceCriteria": ["criterion"]}, bootstrap)
            artifact_access.assert_not_called()
        append_evidence = "artifacts/evidence/W1.A03.B00.json"
        for value in (
            str((REPO / append_evidence).resolve()),
            append_evidence.replace("/", "\\"),
            append_evidence.replace("evidence/", "evidence/./"),
            append_evidence.replace("evidence/", "evidence/../evidence/"),
        ):
            with self.subTest(append_value=value), self.assertRaises(SystemExit):
                taskctl.canonical_control_artifact_path(
                    REPO,
                    value,
                    prefix="artifacts/evidence",
                    label="Appended amendment bootstrap evidence",
                    require_exists=False,
                )

    def test_frozen_predecessor_records_deny_atomic_rewrite(self) -> None:
        original = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        frozen_amendments = taskctl.exact_record_snapshot(original, "wave_amendments")
        frozen_waves = taskctl.exact_record_snapshot(original, "waves", identities={"W1"})
        frozen_bases = taskctl.exact_record_snapshot(
            original,
            "wave_approval_bases",
            identity_field="wave_id",
        )
        mutation_paths = (
            (
                "lifecycle",
                lambda data: data["wave_amendments"][1]["lifecycle"]["history"][0].__setitem__("rationale", "forged"),
            ),
            (
                "task-completion",
                lambda data: data["wave_amendments"][1]["tasks"][0].__setitem__(
                    "completed_at", "2026-01-01T00:00:00+00:00"
                ),
            ),
            (
                "amendment-completion",
                lambda data: data["wave_amendments"][1]["completion"].__setitem__("notes", "forged"),
            ),
            (
                "task-review",
                lambda data: data["wave_amendments"][1]["tasks"][0]["review"].__setitem__("notes", "forged"),
            ),
            ("checkpoint", lambda data: data["waves"][1]["checkpoints"][0].__setitem__("notes", "forged")),
            ("wave-base", lambda data: data["wave_approval_bases"][0].__setitem__("packet_commit", "0" * 40)),
        )
        with tempfile.TemporaryDirectory(dir=REPO) as temporary:
            destination = Path(temporary) / "backlog.yaml"
            for label, mutate in mutation_paths:
                destination.write_text("sentinel", encoding="utf-8")
                candidate = copy.deepcopy(original)
                mutate(candidate)
                with self.subTest(label=label), self.assertRaisesRegex(SystemExit, "Frozen"):
                    taskctl.save_validated(
                        str(destination),
                        candidate,
                        expected_frozen_waves=frozen_waves,
                        expected_frozen_wave_bases=frozen_bases,
                        expected_frozen_amendments=frozen_amendments,
                    )
                self.assertEqual("sentinel", destination.read_text(encoding="utf-8"))

    def test_recovery_save_derives_all_frozen_expectations_from_prior_payload(self) -> None:
        original = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        payload = yaml.safe_dump(original, sort_keys=False).encode()
        mutated = copy.deepcopy(original)
        mutated["wave_amendments"][1]["tasks"][0]["review"]["notes"] = "forged"
        with patch.object(taskctl, "save_validated") as save:
            recoveryctl.save_backlog(REPO, payload, mutated)
        kwargs = save.call_args.kwargs
        self.assertEqual(
            taskctl.exact_record_snapshot(original, "wave_amendments"),
            kwargs["expected_frozen_amendments"],
        )
        self.assertNotEqual(
            taskctl.exact_record_snapshot(mutated, "wave_amendments"),
            kwargs["expected_frozen_amendments"],
        )

    def test_recovery_submit_review_release_common_writer_denies_predecessor_rewrite_atomically(self) -> None:
        backlog_path = REPO / "planning/backlog.yaml"
        payload = backlog_path.read_bytes()
        original = yaml.safe_load(payload)
        mutated = copy.deepcopy(original)
        mutated["wave_amendments"][1]["completion"]["notes"] = "forged"
        with self.assertRaisesRegex(SystemExit, "Frozen Wave amendment record changed"):
            recoveryctl.save_backlog(REPO, payload, mutated)
        self.assertEqual(payload, backlog_path.read_bytes())

    def test_taskctl_hold_denies_wave_resume_and_older_revision(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "tools/taskctl.py"),
                "--file",
                str(REPO / "planning/backlog.yaml"),
                "wave",
                "resume",
                "W1",
                "--agent",
                "codex",
                "--branch",
                "codex/w1-windows-local-runtime",
                "--base-sha",
                "0" * 40,
                "--worktree",
                str(REPO),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Governance recovery hold HOLD-W1-GRR-0001 denies this mutation", result.stderr)
        data = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        with patch.object(taskctl, "CONTROL_TOOL_REVISION", 3):
            errors = taskctl.wave_authority_errors(data, None)
        self.assertIn("control plane revision is missing or unsupported", errors)

    def test_failed_release_is_atomic(self) -> None:
        backlog = REPO / "planning/backlog.yaml"
        before = backlog.read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "tools/recoveryctl.py"),
                "--repo",
                str(REPO),
                "release",
                "GRR-0001",
                "--agent",
                "codex",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("requires independent bootstrap approval", result.stderr)
        self.assertEqual(before, backlog.read_bytes())

    def test_recovery_review_binds_cli_actor_and_denies_self_review(self) -> None:
        candidate = "c" * 40
        reviewed_state = "d" * 40
        evidence = {"path": "planning/governance-recovery-approvals/GRR-0001.B00.evidence.json", "sha256": "e" * 64}
        bootstrap = {
            "id": "GRR-0001.B00",
            "implementer": "codex",
            "evidence": evidence,
            "current_submission": {"attempt_id": "R01", "candidate_commit": candidate},
            "attempts": [],
        }
        packet = {"acceptanceCriteria": ["criterion"]}
        ledger = {
            "schemaVersion": "1.0",
            "documentType": "governance-recovery-bootstrap-review",
            "recoveryRequestId": "GRR-0001",
            "bootstrapUnit": "GRR-0001.B00",
            "attemptId": "R01",
            "candidateCommit": candidate,
            "reviewedStateCommit": reviewed_state,
            "reviewer": "agent:ledger-reviewer",
            "result": "approved",
            "evidence": evidence,
            "findings": [],
            "closures": [],
        }
        args = argparse.Namespace(
            request="GRR-0001",
            repo=REPO,
            from_path="planning/governance-recovery-approvals/GRR-0001.B00.review-R01.json",
            reviewer="agent:cli-reviewer",
        )
        with (
            patch.object(recoveryctl, "safe_repo_path", return_value=REPO / "unused.json"),
            patch.object(recoveryctl, "load_json", return_value=(ledger, b"{}")),
            patch.object(recoveryctl, "git_output", return_value=reviewed_state),
            self.assertRaisesRegex(SystemExit, "must equal the CLI review actor"),
        ):
            recoveryctl.review_ledger(args, packet, bootstrap)
        args.reviewer = "codex"
        ledger["reviewer"] = "codex"
        with (
            patch.object(recoveryctl, "safe_repo_path", return_value=REPO / "unused.json"),
            patch.object(recoveryctl, "load_json", return_value=(ledger, b"{}")),
            patch.object(recoveryctl, "git_output", return_value=reviewed_state),
            self.assertRaisesRegex(SystemExit, "independent from the implementer"),
        ):
            recoveryctl.review_ledger(args, packet, bootstrap)

    def test_recovery_transition_denies_dirty_tracked_worktree(self) -> None:
        with (
            patch.object(recoveryctl.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)),
            self.assertRaisesRegex(SystemExit, "Tracked worktree changes exist"),
        ):
            recoveryctl.require_clean(REPO)


if __name__ == "__main__":
    unittest.main()
