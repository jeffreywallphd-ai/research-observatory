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

import gcrctl  # noqa: E402
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
        approval_introduction = taskctl.approval_introduction_commit(
            REPO,
            "planning/wave-amendment-approvals/W1.A03.json",
        )
        if not approval_introduction:
            raise AssertionError("Canonical W1.A03 approval introduction is unavailable")
        fixture_base = self.git(REPO, "rev-parse", f"{approval_introduction}^")
        self.git(repo, "checkout", "-b", "codex/append-fixture", fixture_base)
        shutil.copy2(REPO / "tools/taskctl.py", repo / "tools/taskctl.py")
        shutil.copy2(REPO / "tools/planctl.py", repo / "tools/planctl.py")
        shutil.copy2(REPO / "tools/recoveryctl.py", repo / "tools/recoveryctl.py")
        backlog_path = repo / "planning/backlog.yaml"
        backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
        hold = (backlog["control_plane"]["recovery_holds"])[0]
        bootstrap = hold["bootstrap"]
        recovery_packet = json.loads(
            (repo / "planning/governance-recovery-requests/GRR-0001.packet.json").read_text(encoding="utf-8")
        )

        def open_findings() -> list[str]:
            open_ids: set[str] = set()
            for prior_attempt in bootstrap["attempts"]:
                prior_path = repo / prior_attempt["ledger"]["path"]
                prior_ledger = json.loads(prior_path.read_text(encoding="utf-8"))
                open_ids.difference_update(
                    str(item["findingId"]) for item in prior_ledger["closures"] if isinstance(item, dict)
                )
                open_ids.update(str(item["id"]) for item in prior_ledger["findings"] if isinstance(item, dict))
            return sorted(open_ids)

        if bootstrap["status"] == "REVIEW":
            submission = bootstrap["current_submission"]
            attempt_id = submission["attempt_id"]
            candidate = submission["candidate_commit"]
            evidence = copy.deepcopy(bootstrap["evidence"])
            submission_branch = bootstrap["submission_branch"]
            reviewed_state_commit = self.git(repo, "rev-parse", "HEAD")
        elif bootstrap["status"] in {"CHANGES_REQUESTED", "BLOCKED"}:
            latest_candidate = bootstrap["implementation_commit"]
            candidate = self.git(repo, "rev-parse", "HEAD")
            attempt_id = f"R{len(bootstrap['attempts']) + 1:02d}"
            submission_branch = self.git(repo, "branch", "--show-current")
            source_evidence_path = repo / bootstrap["evidence"]["path"]
            evidence_document = json.loads(source_evidence_path.read_text(encoding="utf-8"))
            changed_paths = self.git(repo, "diff", "--name-only", f"{latest_candidate}..{candidate}").splitlines()
            evidence_document.update(
                branch=submission_branch,
                baseCommit=latest_candidate,
                candidateCommit=candidate,
                changedPaths=changed_paths,
                riskAnalysis="Fixture remediation preserves prior attempts and closes every open recovery finding.",
            )
            evidence_name = f"GRR-0001.B00.remediation-{len(bootstrap['attempts']):02d}.evidence.json"
            evidence_path = repo / "planning/governance-recovery-approvals" / evidence_name
            evidence_payload = (json.dumps(evidence_document, indent=2) + "\n").encode()
            evidence_path.write_bytes(evidence_payload)
            evidence = {
                "type": "governance-recovery-evidence",
                "path": evidence_path.relative_to(repo).as_posix(),
                "sha256": hashlib.sha256(evidence_payload).hexdigest(),
                "commit": candidate,
                "recorded_at": "2026-08-22T18:00:00+00:00",
            }
            bootstrap.update(
                status="REVIEW",
                implementation_commit=candidate,
                submission_branch=submission_branch,
                evidence=copy.deepcopy(evidence),
                review={"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
                current_submission={
                    "attempt_id": attempt_id,
                    "candidate_commit": candidate,
                    "evidence_sha256": evidence["sha256"],
                    "acceptance_criteria_sha256": taskctl.canonical_json_sha256(recovery_packet["acceptanceCriteria"]),
                },
            )
            backlog_path.write_bytes(yaml.safe_dump(backlog, sort_keys=False, width=120).encode())
            self.git(
                repo,
                "add",
                backlog_path.relative_to(repo).as_posix(),
                evidence_path.relative_to(repo).as_posix(),
            )
            self.git(repo, "commit", "-m", "test: freeze recovery REVIEW state")
            reviewed_state_commit = self.git(repo, "rev-parse", "HEAD")
        elif bootstrap["status"] == "APPROVED":
            attempt_id = ""
            candidate = ""
            evidence = {}
            submission_branch = ""
            reviewed_state_commit = ""
        else:
            raise AssertionError(f"Unsupported fixture recovery state: {bootstrap['status']}")

        if bootstrap["status"] != "APPROVED":
            ledger_path = repo / f"planning/governance-recovery-approvals/GRR-0001.B00.review-{attempt_id}.json"
            ledger = {
                "schemaVersion": "1.0",
                "documentType": "governance-recovery-bootstrap-review",
                "recoveryRequestId": "GRR-0001",
                "bootstrapUnit": bootstrap["id"],
                "attemptId": attempt_id,
                "candidateCommit": candidate,
                "reviewedStateCommit": reviewed_state_commit,
                "reviewer": "fixture-independent-reviewer",
                "result": "approved",
                "evidence": {
                    "path": evidence["path"],
                    "sha256": evidence["sha256"],
                },
                "notes": "Approved fixture recovery from the frozen current submission.",
                "findings": [],
                "closures": [
                    {"findingId": finding_id, "notes": "Closed by the fixture's lawful successor attempt."}
                    for finding_id in open_findings()
                ],
            }
            ledger_payload = (json.dumps(ledger, indent=2) + "\n").encode()
            ledger_path.write_bytes(ledger_payload)
            review = {
                "reviewer": ledger["reviewer"],
                "result": "approved",
                "reviewed_at": "2026-08-22T18:00:00+00:00",
                "notes": ledger["notes"],
            }
            bootstrap["attempts"].append(
                {
                    "id": attempt_id,
                    "implementer": bootstrap["implementer"],
                    "implementation_commit": candidate,
                    "submission_branch": submission_branch,
                    "evidence": copy.deepcopy(evidence),
                    "review": copy.deepcopy(review),
                    "ledger": {
                        "path": ledger_path.relative_to(repo).as_posix(),
                        "sha256": hashlib.sha256(ledger_payload).hexdigest(),
                    },
                }
            )
            bootstrap.update(
                status="APPROVED",
                implementation_commit=candidate,
                submission_branch=submission_branch,
                evidence=copy.deepcopy(evidence),
                review=review,
                current_submission=None,
            )
        proposal_path = repo / "planning/enabler-change-requests/ECR-0002.md"
        review_path = repo / "planning/enabler-change-requests/ECR-0002-review.html"
        proposal_path.write_bytes(b"# Fixture ECR-0002\n")
        review_path.write_bytes(b"<!doctype html><title>Fixture ECR-0002</title>\n")
        recovery_authority = recovery_packet["authorityChain"]
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

    def second_hold_fixture(self, temporary: str) -> Path:
        repo = Path(temporary) / "second-hold-fixture"
        bundle = Path(temporary) / "second-hold.bundle"
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
        self.git(repo, "config", "user.name", "Fixture Implementer")
        self.git(repo, "config", "commit.gpgsign", "false")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(
            repo,
            "checkout",
            "-B",
            "codex/w1-windows-local-runtime",
            "fdf437b78711e409f4c61f2e6e365bf3e8162105",
        )
        for relative in (
            "tools/taskctl.py",
            "tools/recoveryctl.py",
            "planning/backlog.schema.json",
            "planning/enabler-change-requests/enabler-change-request.v3.schema.json",
        ):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
            self.git(repo, "add", relative)
        if self.git(repo, "status", "--porcelain"):
            self.git(repo, "commit", "-m", "fixture: install revision 6 controller")
        return repo

    def test_second_recovery_hold_start_is_atomic_consecutive_and_preserving(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as temporary:
            repo = self.second_hold_fixture(temporary)
            backlog_path = repo / "planning/backlog.yaml"
            before = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            predecessor = json.dumps(
                before["control_plane"]["recovery_holds"][0],
                sort_keys=True,
                separators=(",", ":"),
            )
            recoveryctl.command_bootstrap_start(argparse.Namespace(repo=repo, request="GRR-0002", agent="codex"))
            installed = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            control = installed["control_plane"]
            self.assertEqual(6, control["revision"])
            self.assertEqual(6, control["minimum_tool_revision"])
            self.assertEqual(
                predecessor,
                json.dumps(control["recovery_holds"][0], sort_keys=True, separators=(",", ":")),
            )
            successor = control["recovery_holds"][1]
            self.assertEqual("HOLD-W1-GRR-0002", successor["id"])
            self.assertEqual("ACTIVE", successor["status"])
            self.assertEqual("GRR-0002.B00", successor["bootstrap"]["id"])
            self.assertEqual("IN_PROGRESS", successor["bootstrap"]["status"])
            self.assertEqual("ECR-0003", successor["post_bootstrap"]["required_change_request_id"])
            self.assertEqual("W1.A04", successor["post_bootstrap"]["required_amendment_id"])
            self.assertEqual(["W1.A04.T01"], successor["post_bootstrap"]["required_proposed_task_ids"])
            self.assertEqual([], taskctl.validate(*taskctl.load(str(backlog_path)), repo=repo))

            self.git(repo, "add", "planning/backlog.yaml")
            self.git(repo, "commit", "-m", "fixture: install second recovery hold")
            frozen = backlog_path.read_bytes()
            with self.assertRaisesRegex(SystemExit, "next consecutive identity GRR-0003"):
                recoveryctl.command_bootstrap_start(argparse.Namespace(repo=repo, request="GRR-0002", agent="codex"))
            self.assertEqual(frozen, backlog_path.read_bytes())

            old_tool = repo / "tools" / "old-taskctl.py"
            old_tool.write_bytes(
                subprocess.run(
                    ["git", "show", "0b450222ff569db356b84e413941aa2af585a64e:tools/taskctl.py"],
                    cwd=repo,
                    capture_output=True,
                    check=True,
                ).stdout
            )
            result = subprocess.run(
                [sys.executable, str(old_tool), "--file", str(backlog_path), "validate"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertRegex(
                result.stdout + result.stderr,
                "control plane revision is missing or unsupported|Backlog schema validation failed",
            )

    def supplement_lifecycle_fixture(
        self,
        temporary: str,
    ) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
        repo = Path(temporary) / "supplement-fixture"
        bundle = Path(temporary) / "supplement-fixture.bundle"
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
        supplement_approval_intro = taskctl.approval_introduction_commit(
            REPO,
            "planning/governance-recovery-approvals/GRR-0001.S01.json",
        )
        if not supplement_approval_intro:
            raise AssertionError("Canonical supplement approval introduction is unavailable")
        self.git(repo, "checkout", "-B", "codex/supplement-fixture", supplement_approval_intro)

        backlog_path = repo / "planning/backlog.yaml"
        current = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        current_supplement = copy.deepcopy(current["control_plane"]["recovery_holds"][0]["supplements"][0])
        backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
        backlog["control_plane"]["revision"] = taskctl.RECOVERY_BASE_REVISION
        backlog["control_plane"]["minimum_tool_revision"] = taskctl.RECOVERY_BASE_REVISION
        hold = backlog["control_plane"]["recovery_holds"][0]
        hold["supplements"] = [current_supplement]
        b00_snapshot = copy.deepcopy(hold["bootstrap"])
        supplement = hold["supplements"][0]
        bootstrap = supplement["bootstrap"]
        bootstrap.update(
            status="IN_PROGRESS",
            implementation_commit=None,
            submission_branch=None,
            evidence=None,
            review={"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
            current_submission=None,
            attempts=[],
        )
        approvals = repo / "planning/governance-recovery-approvals"
        for artifact in approvals.glob("GRR-0001.B01*"):
            artifact.unlink()
        for schema_name in (
            "governance-recovery-supplement-evidence.schema.json",
            "governance-recovery-supplement-review.schema.json",
        ):
            shutil.copy2(
                REPO / "planning/governance-recovery-requests" / schema_name,
                repo / "planning/governance-recovery-requests" / schema_name,
            )
        backlog_path.write_bytes(yaml.safe_dump(backlog, sort_keys=False, width=120).encode())
        self.git(repo, "add", "--all")
        self.git(repo, "commit", "-m", "test: establish initial B01 lifecycle boundary")

        approval, packet, _approval_payload, _packet_payload = recoveryctl.load_supplement_authority(
            repo,
            "GRR-0001.S01",
        )
        return repo, approval, packet, b00_snapshot

    def gcr_adopted_clone(self, temporary: str) -> Path:
        """Create a real-Git revision-7 clone through the actual GCR lifecycle."""

        repo = Path(temporary) / "gcr-adopted-supplement-fixture"
        bundle = Path(temporary) / "gcr-adopted-supplement-fixture.bundle"
        subprocess.run(
            ["git", "bundle", "create", str(bundle), "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "-c", "core.autocrlf=true", "clone", "--quiet", str(bundle), str(repo)],
            capture_output=True,
            text=True,
            check=True,
        )
        self.git(repo, "config", "user.email", "fixture@example.invalid")
        self.git(repo, "config", "user.name", "Fixture Reviewer")
        self.git(repo, "config", "commit.gpgsign", "false")
        self.git(repo, "config", "core.autocrlf", "false")
        r05_disposition = taskctl.approval_introduction_commit(
            repo,
            gcrctl.review_path_for("R05"),
        )
        self.assertIsNotNone(r05_disposition)
        self.git(repo, "checkout", "--detach", str(r05_disposition))
        self.git(repo, "checkout", "-B", gcrctl.BRANCH)
        backlog_path = repo / "planning/backlog.yaml"
        backlog_path.write_bytes(backlog_path.read_bytes().replace(b"\n", b"\r\n"))
        witness = repo / recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH
        witness.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH, witness)
        fixture_candidate_paths = [
            "planning/governance-control-recovery/governance-control-recovery-transaction.schema.json",
            "tests/foundation/test_recoveryctl.py",
            "tools/gcrctl.py",
            "tools/recoveryctl.py",
        ]
        for relative in fixture_candidate_paths:
            shutil.copy2(REPO / relative, repo / relative)
        if self.git(repo, "status", "--short", "--", *fixture_candidate_paths):
            self.git(repo, "add", "--", *fixture_candidate_paths)
            self.git(repo, "commit", "-m", "fixture: install current R06 candidate")

        _approval, packet, approval_base = gcrctl.load_authority(repo)
        candidate = self.git(repo, "rev-parse", "HEAD")
        attempt_id = "R06"
        evidence_relative = gcrctl.evidence_path_for(attempt_id)
        evidence_path = repo / evidence_relative
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        changed_files = self.git(repo, "diff", "--name-only", f"{approval_base}..{candidate}", "--").splitlines()
        evidence = {
            "schemaVersion": "1.0-control-recovery-evidence",
            "documentType": "governance-control-recovery-bootstrap-evidence",
            "controlRecoveryId": gcrctl.GCR_ID,
            "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
            "attemptId": attempt_id,
            "commit": candidate,
            "baseCommit": approval_base,
            "branch": gcrctl.BRANCH,
            "triggerWitness": gcrctl.trigger_witness(),
            "changedFiles": changed_files,
            "checks": [{"id": "fixture-r06", "command": "fixture:r06", "exitCode": 0, "result": "passed"}],
            "acceptanceCriteria": [
                {"index": index, "statement": statement, "evidence": ["The real-Git fixture passed."]}
                for index, statement in enumerate(packet["acceptanceCriteria"], start=1)
            ],
            "findingClosures": [
                {
                    "findingId": "GCR-0001.B00-R05-F01",
                    "disposition": "fixed",
                    "evidence": "The fixture executes the exact witness-aware v2 lifecycle.",
                }
            ],
            "unverifiedItems": [],
            "verificationSelection": {
                "riskAnalysis": "The fixture closes the exact R05 workspace finding with a real v2 lifecycle.",
                "selectedChecks": ["fixture-r06"],
                "deferredCoverage": ["Independent repository review remains separate."],
            },
        }
        evidence_path.write_bytes((json.dumps(evidence, indent=2) + "\n").encode())
        gcrctl.freeze_submission(
            argparse.Namespace(
                repo=repo,
                agent=gcrctl.ACTOR,
                implementation_commit=candidate,
                evidence=evidence_relative,
            ),
            remediation=True,
        )
        self.git(repo, "add", evidence_relative, gcrctl.STATE_PATH)
        self.git(repo, "commit", "-m", "fixture: freeze GCR R06")
        reviewed_state = self.git(repo, "rev-parse", "HEAD")
        state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
        review_relative = gcrctl.review_path_for(attempt_id)
        review_path = repo / review_relative
        review = {
            "schemaVersion": "1.0-control-recovery-review",
            "documentType": "governance-control-recovery-bootstrap-review",
            "controlRecoveryId": gcrctl.GCR_ID,
            "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
            "attemptId": attempt_id,
            "candidateCommit": candidate,
            "reviewedStateCommit": reviewed_state,
            "reviewer": "fixture-independent-reviewer",
            "result": "approved",
            "evidence": state["currentSubmission"]["evidence"],
            "findings": [],
            "closures": [
                {
                    "findingId": "GCR-0001.B00-R05-F01",
                    "disposition": "fixed",
                    "evidence": "The real-Git witness-aware v2 lifecycle passes.",
                }
            ],
            "notes": "Approved only for the isolated lifecycle fixture.",
        }
        review_path.write_bytes((json.dumps(review, indent=2) + "\n").encode())
        gcrctl.command_review(
            argparse.Namespace(repo=repo, reviewer="fixture-independent-reviewer", ledger=review_relative)
        )
        self.git(repo, "add", review_relative, gcrctl.STATE_PATH)
        self.git(repo, "commit", "-m", "fixture: approve GCR R06")
        approved_state = self.git(repo, "rev-parse", "HEAD")

        adoption_relative = "artifacts/evidence/governance-control-recovery/GCR-0001.B00.adoption.json"
        adoption_path = repo / adoption_relative
        adoption = {
            "schemaVersion": "1.0-control-recovery-adoption-evidence",
            "documentType": "governance-control-recovery-adoption-evidence",
            "controlRecoveryId": gcrctl.GCR_ID,
            "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
            "reviewedStateCommit": approved_state,
            "triggerWitness": gcrctl.trigger_witness(),
            "predecessorRevision": 6,
            "successorRevision": 7,
            "expectedChangedFiles": ["planning/backlog.yaml", gcrctl.STATE_PATH],
            "checks": [{"id": "fixture-adoption", "command": "fixture:adoption", "exitCode": 0, "result": "passed"}],
            "unverifiedItems": [],
        }
        adoption_path.write_bytes((json.dumps(adoption, indent=2) + "\n").encode())
        self.git(repo, "add", adoption_relative)
        self.git(repo, "commit", "-m", "fixture: bind GCR adoption evidence")
        self.assertEqual(
            taskctl.git_blob(repo, approved_state, gcrctl.STATE_PATH),
            (repo / gcrctl.STATE_PATH).read_bytes(),
            "fixture GCR state worktree bytes differ from the approved-state Git blob",
        )
        gcrctl.command_adopt(
            argparse.Namespace(
                repo=repo,
                agent=gcrctl.ACTOR,
                approved_state_commit=approved_state,
                evidence=adoption_relative,
            )
        )
        self.git(repo, "add", gcrctl.BACKLOG_PATH, gcrctl.STATE_PATH)
        self.git(repo, "commit", "-m", "fixture: finalize GCR adoption")
        self.assertEqual([], taskctl.validate(*taskctl.load(str(repo / "planning/backlog.yaml"))[0:5], repo=repo))
        return repo

    def install_v2_supplement_authority(self, repo: Path) -> tuple[dict[str, Any], str]:
        """Freeze and approve an exact GRR-0002.S01 fixture packet in Git."""

        base_approval, base_packet, base_approval_payload, base_packet_payload = recoveryctl.load_recovery_authority(
            repo, "GRR-0002"
        )
        _base_approval, _base_packet, base_hold = recoveryctl.validate_request(repo, "GRR-0002")
        latest_attempt = base_hold["bootstrap"]["attempts"][-1]
        latest_ledger_path = str(latest_attempt["ledger"]["path"])
        latest_ledger_payload = (repo / latest_ledger_path).read_bytes()
        latest_ledger = json.loads(latest_ledger_payload)
        base_approval_relative = "planning/governance-recovery-approvals/GRR-0002.json"
        base_approval_intro = taskctl.approval_introduction_commit(repo, base_approval_relative)
        self.assertIsNotNone(base_approval_intro)

        proposal_relative = "planning/governance-recovery-requests/GRR-0002.S01.md"
        review_relative = "planning/governance-recovery-requests/GRR-0002.S01-review.html"
        schema_relative = "planning/governance-recovery-requests/governance-recovery-supplement.v2.schema.json"
        (repo / proposal_relative).write_bytes(b"# Fixture GRR-0002.S01\n")
        (repo / review_relative).write_bytes(b"<!doctype html><title>Fixture GRR-0002.S01</title>\n")
        witness_payload = (repo / recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH).read_bytes()
        witness = json.loads(witness_payload)
        amendment_relative = "planning/wave-amendment-approvals/W1.A04.json"
        amendment_payload = (repo / amendment_relative).read_bytes()
        amendment = json.loads(amendment_payload)
        amendment_intro = taskctl.approval_introduction_commit(repo, amendment_relative)
        self.assertIsNotNone(amendment_intro)
        ecr = amendment["packet"]
        backlog_payload = (repo / "planning/backlog.yaml").read_bytes()
        discovery_commit = self.git(repo, "rev-parse", "HEAD")
        packet = {
            "$schema": "./governance-recovery-supplement.v2.schema.json",
            "schemaVersion": "2.0-recovery-supplement-proposal",
            "documentType": "governance-recovery-supplement-packet",
            "recoveryRequestId": "GRR-0002",
            "supplementId": "GRR-0002.S01",
            "title": "Fixture exact witness-aware v2 lifecycle",
            "targetWave": "W1",
            "status": "pending-human-approval",
            "executionState": "non-executable",
            "classification": "approved-bootstrap-latent-control-defect",
            "controlTransition": {
                "predecessorRevision": 7,
                "successorRevision": 8,
                "generationNeutral": True,
                "olderReadersFailClosed": True,
            },
            "baseRecoveryAuthority": {
                "packet": {
                    "path": "planning/governance-recovery-requests/GRR-0002.packet.json",
                    "sha256": recoveryctl.sha256(base_packet_payload),
                    "commit": base_approval["packet"]["commit"],
                },
                "approval": {
                    "path": base_approval_relative,
                    "sha256": recoveryctl.sha256(base_approval_payload),
                    "introductionCommit": base_approval_intro,
                },
                "holdId": base_packet["controlHold"]["id"],
                "bootstrapUnit": base_packet["bootstrapUnit"]["id"],
                "latestApprovedReview": {
                    "attemptId": latest_ledger["attemptId"],
                    "path": latest_ledger_path,
                    "sha256": recoveryctl.sha256(latest_ledger_payload),
                    "candidateCommit": latest_ledger["candidateCommit"],
                    "reviewedStateCommit": latest_ledger["reviewedStateCommit"],
                },
            },
            "targetAmendmentAuthority": {
                "changeRequestPacket": {
                    "id": "ECR-0003",
                    "path": ecr["path"],
                    "sha256": ecr["sha256"],
                    "commit": ecr["commit"],
                },
                "amendmentApproval": {
                    "id": "W1.A04",
                    "path": amendment_relative,
                    "sha256": recoveryctl.sha256(amendment_payload),
                    "introductionCommit": amendment_intro,
                },
                "bootstrap": {
                    "id": "W1.A04.B00",
                    "candidateCommit": witness["commit"],
                    "evidence": {
                        "path": recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH,
                        "sha256": recoveryctl.sha256(witness_payload),
                        "commit": witness["commit"],
                    },
                },
                "backlogPresence": False,
            },
            "triggerEvidence": {
                "discoveryCommit": discovery_commit,
                "backlogSha256": recoveryctl.sha256(backlog_payload),
                "command": "fixture: supplement-start GRR-0002.S01",
                "diagnostic": "The revision-7 pre-append lane requires its separately approved v2 supplement.",
                "atomicNoMutation": True,
            },
            "activationBoundary": {
                "controlRevision": 7,
                "holdStatus": "ACTIVE",
                "waveStatus": "PAUSED",
                "waveScope": "wave",
                "amendmentId": "W1.A04",
                "amendmentBacklogStatus": "ABSENT",
                "blockedTaskId": "CAP-02.S04.T03",
                "blockedTaskStatus": "BLOCKED",
            },
            "supplementalBootstrap": {
                "id": "GRR-0002.B01",
                "kind": "append-only-approved-bootstrap-remediation",
                "exceptionReason": "Exercise the exact witness-aware generation-neutral transition.",
                "authorizedPaths": [
                    "planning/backlog.yaml",
                    "planning/governance-recovery-approvals/GRR-0002.B01*",
                    "tests/foundation/test_recoveryctl.py",
                    "tools/recoveryctl.py",
                ],
                "requiredOutcomes": ["The exact witness-aware v2 lifecycle reaches independent B01 approval."],
                "prohibitedOutcomes": ["No amendment materialization or ordinary Wave execution occurs."],
            },
            "acceptanceCriteria": [
                "GRR-0002.S01 traverses start, submission, independent review, and approved validation."
            ],
            "verificationObligations": ["Run the isolated real-Git witness-aware v2 lifecycle."],
            "rollback": ["Any failure leaves the prior canonical backlog byte-identical."],
            "alternatives": [{"id": "A"}, {"id": "B"}],
            "files": [
                {
                    "path": schema_relative,
                    "sha256": recoveryctl.sha256((repo / schema_relative).read_bytes()),
                },
                {
                    "path": proposal_relative,
                    "sha256": recoveryctl.sha256((repo / proposal_relative).read_bytes()),
                },
                {
                    "path": review_relative,
                    "sha256": recoveryctl.sha256((repo / review_relative).read_bytes()),
                },
            ],
            "requiredApprovalStatement": "Approve only fixture GRR-0002.S01/B01 at its exact packet commit.",
        }
        packet_relative = "planning/governance-recovery-requests/GRR-0002.S01.packet.json"
        packet_path = repo / packet_relative
        packet_path.write_bytes((json.dumps(packet, indent=2) + "\n").encode())
        self.assertEqual(
            [],
            recoveryctl.schema_errors(packet, repo / schema_relative),
        )
        self.git(repo, "add", proposal_relative, review_relative, packet_relative)
        self.git(repo, "commit", "-m", "fixture: freeze GRR-0002.S01 packet")
        packet_commit = self.git(repo, "rev-parse", "HEAD")
        packet_payload = packet_path.read_bytes()
        approval = {
            "$schema": "../governance-recovery-requests/governance-recovery-supplement-approval.v2.schema.json",
            "schemaVersion": "2.0",
            "documentType": "governance-recovery-supplement-approval",
            "recoveryRequestId": "GRR-0002",
            "supplementId": "GRR-0002.S01",
            "targetWave": "W1",
            "status": "APPROVED",
            "approvedBy": "fixture-owner",
            "approvedAt": "2026-08-24T06:00:00Z",
            "decision": "Approve only the isolated fixture supplemental bootstrap.",
            "packet": {
                "commit": packet_commit,
                "path": packet_relative,
                "sha256": recoveryctl.sha256(packet_payload),
                "proposalPath": proposal_relative,
                "proposalSha256": recoveryctl.sha256((repo / proposal_relative).read_bytes()),
                "schemaPath": schema_relative,
                "schemaSha256": recoveryctl.sha256((repo / schema_relative).read_bytes()),
                "reviewPath": review_relative,
                "reviewSha256": recoveryctl.sha256((repo / review_relative).read_bytes()),
            },
            "supplementalBootstrapUnit": "GRR-0002.B01",
            "independentPacketReview": {
                "reviewer": "fixture-packet-reviewer",
                "attemptId": "R01",
                "candidateCommit": packet_commit,
                "packetSha256": recoveryctl.sha256(packet_payload),
                "result": "APPROVED",
                "openFindingIds": [],
                "closedFindingIds": [],
                "priorAdverseLedger": None,
            },
            "executionAuthority": {
                "supplementalBootstrapOnly": True,
                "postBootstrapExecution": False,
                "amendmentMaterialization": False,
                "ordinaryWaveResume": False,
                "taskExecution": False,
                "releaseGateApproval": False,
            },
        }
        approval_relative = "planning/governance-recovery-approvals/GRR-0002.S01.json"
        (repo / approval_relative).write_bytes((json.dumps(approval, indent=2) + "\n").encode())
        self.git(repo, "add", approval_relative)
        self.git(repo, "commit", "-m", "fixture: approve GRR-0002.S01 packet")
        approval_intro = self.git(repo, "rev-parse", "HEAD")
        loaded_approval, loaded_packet, _approval_payload, _packet_payload = recoveryctl.load_supplement_authority(
            repo, "GRR-0002.S01"
        )
        self.assertEqual(approval, loaded_approval)
        self.assertEqual(packet, loaded_packet)
        return packet, approval_intro

    def write_supplement_evidence(
        self,
        repo: Path,
        packet: dict[str, Any],
        *,
        relative: str,
        base: str,
        candidate: str,
        check_id: str,
    ) -> bytes:
        changed_paths = self.git(repo, "diff", "--name-only", f"{base}..{candidate}", "--").splitlines()
        document = {
            "schemaVersion": "1.0",
            "documentType": "governance-recovery-supplement-bootstrap-evidence",
            "recoveryRequestId": "GRR-0001",
            "supplementId": "GRR-0001.S01",
            "bootstrapUnit": "GRR-0001.B01",
            "branch": self.git(repo, "branch", "--show-current"),
            "baseCommit": base,
            "candidateCommit": candidate,
            "changedPaths": changed_paths,
            "riskAnalysis": "Executable fixture covers the complete supplemental submission and review boundary.",
            "requiredOutcomes": [
                {"criterion": criterion, "evidence": ["The executable supplement lifecycle fixture passed."]}
                for criterion in packet["supplementalBootstrap"]["requiredOutcomes"]
            ],
            "acceptanceCriteria": [
                {"criterion": criterion, "evidence": ["The executable supplement lifecycle fixture passed."]}
                for criterion in packet["acceptanceCriteria"]
            ],
            "checks": [
                {
                    "id": check_id,
                    "command": f"fixture:{check_id}",
                    "result": "passed",
                }
            ],
            "deferredCoverage": ["Full W1 qualification remains at Wave exit."],
            "unverifiedItems": [],
        }
        payload = (json.dumps(document, indent=2) + "\n").encode()
        (repo / relative).write_bytes(payload)
        return payload

    @staticmethod
    def supplement_finding() -> dict[str, Any]:
        return {
            "id": "GRR-0001.B01-R01-F01",
            "severity": "high",
            "blocking": True,
            "criterionIndex": 4,
            "title": "Fixture lifecycle finding",
            "reproduction": "Run the executable supplement lifecycle fixture.",
            "requiredRemediation": "Commit a strict-descendant remediation and close this finding.",
        }

    def write_supplement_ledger(
        self,
        repo: Path,
        *,
        result: str,
        reviewer: str,
        findings: list[dict[str, Any]],
        closures: list[dict[str, str]],
        reviewed_state: str | None = None,
        evidence_sha256: str | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        backlog = yaml.safe_load((repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
        bootstrap = backlog["control_plane"]["recovery_holds"][0]["supplements"][0]["bootstrap"]
        submission = bootstrap["current_submission"]
        evidence = bootstrap["evidence"]
        ledger = {
            "schemaVersion": "1.0",
            "documentType": "governance-recovery-supplement-bootstrap-review",
            "recoveryRequestId": "GRR-0001",
            "supplementId": "GRR-0001.S01",
            "bootstrapUnit": "GRR-0001.B01",
            "attemptId": submission["attempt_id"],
            "candidateCommit": submission["candidate_commit"],
            "reviewedStateCommit": reviewed_state or self.git(repo, "rev-parse", "HEAD"),
            "reviewer": reviewer,
            "result": result,
            "evidence": {
                "path": evidence["path"],
                "sha256": evidence_sha256 or evidence["sha256"],
            },
            "notes": f"Fixture disposition: {result}.",
            "findings": findings,
            "closures": closures,
        }
        path = repo / f"planning/governance-recovery-approvals/GRR-0001.B01.review-{submission['attempt_id']}.json"
        path.write_bytes((json.dumps(ledger, indent=2) + "\n").encode())
        return path, ledger

    def test_canonical_recovery_authority_and_hold_validate(self) -> None:
        approval, packet, hold = recoveryctl.validate_request(REPO, "GRR-0001")
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual("W1.A03", packet["postBootstrap"]["requiredAmendmentId"])
        self.assertEqual("RELEASED", hold["status"])
        self.assertIsNotNone(hold["released_at"])
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

    def test_approved_supplement_authority_and_installed_stopped_boundary_validate(self) -> None:
        approval, packet, _approval_payload, _packet_payload = recoveryctl.load_supplement_authority(
            REPO, "GRR-0001.S01"
        )
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual("GRR-0001.B01", packet["supplementalBootstrap"]["id"])
        _approval, _packet, hold, supplement = recoveryctl.validate_supplement(REPO, "GRR-0001.S01")
        self.assertEqual("RELEASED", hold["status"])
        self.assertEqual("APPROVED", supplement["bootstrap"]["status"])
        self.assertTrue(
            recoveryctl.path_authorized(
                "planning/governance-recovery-approvals/GRR-0001.B01.review-R01.json",
                packet["supplementalBootstrap"]["authorizedPaths"],
            )
        )
        self.assertTrue(
            recoveryctl.path_authorized(
                "planning/governance-recovery-requests/governance-recovery-supplement-review.schema.json",
                packet["supplementalBootstrap"]["authorizedPaths"],
            )
        )
        self.assertFalse(
            recoveryctl.path_authorized(
                "planning/governance-recovery-approvals/nested/GRR-0001.B01.review-R01.json",
                packet["supplementalBootstrap"]["authorizedPaths"],
            )
        )

    def test_supplement_start_is_sequential_revisioned_and_atomic(self) -> None:
        approval, packet, _approval_payload, _packet_payload = recoveryctl.load_supplement_authority(
            REPO, "GRR-0001.S01"
        )
        payload, data, capabilities, slices, tasks, gates = recoveryctl.backlog_state(REPO)
        data = copy.deepcopy(data)
        data["control_plane"]["revision"] = 4
        data["control_plane"]["minimum_tool_revision"] = 4
        data["control_plane"]["recovery_holds"][0].pop("supplements", None)
        captured: dict[str, Any] = {}

        def capture(_repo: Path, prior: bytes, candidate: dict[str, Any]) -> None:
            self.assertEqual(payload, prior)
            captured["data"] = copy.deepcopy(candidate)

        args = argparse.Namespace(repo=REPO, supplement="GRR-0001.S01", agent="codex")
        with (
            patch.object(
                recoveryctl,
                "load_supplement_authority",
                return_value=(approval, packet, b"approval", json.dumps(packet).encode()),
            ),
            patch.object(recoveryctl, "require_clean"),
            patch.object(
                recoveryctl,
                "backlog_state",
                return_value=(payload, data, capabilities, slices, tasks, gates),
            ),
            patch.object(
                recoveryctl,
                "validate_supplement_boundary",
                return_value=(data["control_plane"]["recovery_holds"][0], data["wave_amendments"][-1]),
            ),
            patch.object(recoveryctl, "save_backlog", side_effect=capture),
        ):
            recoveryctl.command_supplement_start(args)

        installed = captured["data"]
        self.assertEqual(6, installed["control_plane"]["revision"])
        self.assertEqual(6, installed["control_plane"]["minimum_tool_revision"])
        supplement = installed["control_plane"]["recovery_holds"][0]["supplements"][0]
        self.assertEqual("GRR-0001.S01", supplement["id"])
        self.assertEqual("GRR-0001.B01", supplement["bootstrap"]["id"])
        self.assertEqual("IN_PROGRESS", supplement["bootstrap"]["status"])
        self.assertEqual([], supplement["bootstrap"]["attempts"])
        self.assertNotIn("successor_control_revision", supplement)
        self.assertEqual([], taskctl.backlog_schema_errors(taskctl.serializable_backlog(installed)))

        _current_payload, current, _capabilities, _slices, _tasks, _gates = recoveryctl.backlog_state(REPO)
        stale = copy.deepcopy(current)
        stale["control_plane"]["recovery_holds"][0]["id"] = "HOLD-W1-GRR-9999"
        with self.assertRaisesRegex(SystemExit, "activation boundary"):
            recoveryctl.validate_supplement_boundary(REPO, packet, stale, require_installed=True)

    def test_v2_supplement_start_uses_exact_seven_to_eight_transition(self) -> None:
        approval, packet, _approval_payload, _packet_payload = recoveryctl.load_supplement_authority(
            REPO, "GRR-0001.S01"
        )
        packet = copy.deepcopy(packet)
        packet["schemaVersion"] = "2.0-recovery-supplement-proposal"
        packet["controlTransition"] = {
            "predecessorRevision": 7,
            "successorRevision": 8,
            "generationNeutral": True,
            "olderReadersFailClosed": True,
        }
        payload, data, capabilities, slices, tasks, gates = recoveryctl.backlog_state(REPO)
        data = copy.deepcopy(data)
        data["control_plane"]["revision"] = 7
        data["control_plane"]["minimum_tool_revision"] = 7
        data["control_plane"]["recovery_holds"][0]["supplements"] = []
        captured: dict[str, Any] = {}

        def capture(_repo: Path, prior: bytes, candidate: dict[str, Any]) -> None:
            self.assertEqual(payload, prior)
            captured["data"] = copy.deepcopy(candidate)

        args = argparse.Namespace(repo=REPO, supplement="GRR-0001.S01", agent="codex")
        with (
            patch.object(
                recoveryctl,
                "load_supplement_authority",
                return_value=(approval, packet, b"approval", json.dumps(packet).encode()),
            ),
            patch.object(recoveryctl, "require_supplement_workspace"),
            patch.object(
                recoveryctl,
                "backlog_state",
                return_value=(payload, data, capabilities, slices, tasks, gates),
            ),
            patch.object(
                recoveryctl,
                "validate_supplement_boundary",
                return_value=(data["control_plane"]["recovery_holds"][0], {}),
            ),
            patch.object(recoveryctl, "save_backlog", side_effect=capture),
        ):
            recoveryctl.command_supplement_start(args)

        installed = captured["data"]
        self.assertEqual(8, installed["control_plane"]["revision"])
        self.assertEqual(8, installed["control_plane"]["minimum_tool_revision"])
        supplement = installed["control_plane"]["recovery_holds"][0]["supplements"][0]
        self.assertEqual(7, supplement["predecessor_control_revision"])
        self.assertEqual(8, supplement["successor_control_revision"])

    def test_v2_supplement_workspace_requires_exact_non_authoritative_witness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "witness-workspace-fixture"
            bundle = Path(temporary) / "witness-workspace-fixture.bundle"
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
            packet = {"schemaVersion": "2.0-recovery-supplement-proposal"}
            witness = repo / recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH
            witness.parent.mkdir(parents=True, exist_ok=True)
            witness_payload = (REPO / recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH).read_bytes()
            witness.write_bytes(witness_payload)

            recoveryctl.require_supplement_workspace(repo, packet)
            transition_relative = "planning/governance-recovery-approvals/GRR-0002.B01.evidence.json"
            transition = repo / transition_relative
            transition.write_text("{}\n", encoding="utf-8")
            recoveryctl.require_supplement_workspace(
                repo,
                packet,
                transition_untracked={transition_relative},
            )
            transition.unlink()
            with self.assertRaisesRegex(SystemExit, "untracked-path boundary differs"):
                recoveryctl.require_supplement_workspace(
                    repo,
                    packet,
                    transition_untracked={transition_relative},
                )

            duplicate = repo / "artifacts/evidence/W1.A04.B00.copy.json"
            duplicate.write_bytes(witness_payload)
            with self.assertRaisesRegex(SystemExit, "untracked-path boundary differs"):
                recoveryctl.require_supplement_workspace(repo, packet)
            duplicate.unlink()

            witness.write_bytes(witness_payload + b" ")
            with self.assertRaisesRegex(SystemExit, "witness hash differs"):
                recoveryctl.require_supplement_workspace(repo, packet)
            witness.write_bytes(witness_payload)

            witness.unlink()
            with self.assertRaisesRegex(SystemExit, "does not name an existing regular file"):
                recoveryctl.require_supplement_workspace(repo, packet)
            witness.write_bytes(witness_payload)

            self.git(repo, "add", "-f", recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH)
            with self.assertRaisesRegex(SystemExit, "witness must remain unstaged"):
                recoveryctl.require_supplement_workspace(repo, packet)
            self.git(repo, "reset", "HEAD", "--", recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH)

            staged = repo / "planning/staged-supplement-fixture.txt"
            staged.write_text("staged\n", encoding="utf-8")
            self.git(repo, "add", staged.relative_to(repo).as_posix())
            with self.assertRaisesRegex(SystemExit, "Staged source exists"):
                recoveryctl.require_supplement_workspace(repo, packet)
            self.git(repo, "reset", "HEAD", "--", staged.relative_to(repo).as_posix())
            staged.unlink()

            tracked = repo / "tools/recoveryctl.py"
            tracked_payload = tracked.read_bytes()
            tracked.write_bytes(tracked_payload + b"\n# dirty\n")
            with self.assertRaisesRegex(SystemExit, "Tracked worktree changes exist"):
                recoveryctl.require_supplement_workspace(repo, packet)
            tracked.write_bytes(tracked_payload)

            target = repo / "artifacts/evidence/redirected-witness-target.json"
            witness.unlink()
            target.write_bytes(witness_payload)
            try:
                witness.symlink_to(target)
            except OSError:
                witness.write_bytes(witness_payload)
            else:
                with self.assertRaisesRegex(SystemExit, "symlink or junction"):
                    recoveryctl.require_supplement_workspace(repo, packet)
                witness.unlink()
                witness.write_bytes(witness_payload)
            target.unlink()

            state_path = repo / recoveryctl.CONTROL_RECOVERY_STATE_PATH
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["triggerWitness"]["executionAuthority"] = True
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            self.git(repo, "add", recoveryctl.CONTROL_RECOVERY_STATE_PATH)
            self.git(repo, "commit", "-m", "fixture: make witness authority-bearing")
            with self.assertRaisesRegex(SystemExit, "non-authoritative state binding"):
                recoveryctl.require_supplement_workspace(repo, packet)

    def test_b01_scope_addendum_is_exact_commit_bound_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            empty = Path(temporary) / "empty"
            empty.mkdir()
            self.assertEqual(
                [],
                recoveryctl.approved_b01_scope_addendum_paths(
                    empty,
                    "GRR-0001.S01",
                    "not-inspected-without-artifacts",
                ),
            )

            repo = Path(temporary) / "b01-scope-addendum-fixture"
            bundle = Path(temporary) / "b01-scope-addendum-fixture.bundle"
            subprocess.run(
                ["git", "bundle", "create", str(bundle), "HEAD"],
                cwd=REPO,
                capture_output=True,
                text=True,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.autocrlf=false",
                    "clone",
                    "--quiet",
                    str(bundle),
                    str(repo),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            candidate = self.git(repo, "rev-parse", "HEAD")
            self.assertEqual(
                recoveryctl.B01_SCOPE_GENERATED_PATHS,
                recoveryctl.approved_b01_scope_addendum_paths(
                    repo,
                    "GRR-0002.S01",
                    candidate,
                ),
            )
            with self.assertRaisesRegex(SystemExit, "strictly descend"):
                recoveryctl.approved_b01_scope_addendum_paths(
                    repo,
                    "GRR-0002.S01",
                    recoveryctl.B01_SCOPE_BASE_CANDIDATE,
                )
            self.assertEqual(
                [],
                recoveryctl.approved_b01_scope_addendum_paths(
                    repo,
                    "GRR-0001.S01",
                    candidate,
                ),
            )

            approval_path = repo / recoveryctl.B01_SCOPE_APPROVAL_PATH
            approval_payload = approval_path.read_bytes()
            approval_path.write_bytes(approval_payload + b" ")
            with self.assertRaisesRegex(SystemExit, "immutable Git blob"):
                recoveryctl.approved_b01_scope_addendum_paths(
                    repo,
                    "GRR-0002.S01",
                    candidate,
                )
            approval_path.write_bytes(approval_payload)
            approval_path.unlink()
            with self.assertRaisesRegex(SystemExit, "partial"):
                recoveryctl.approved_b01_scope_addendum_paths(
                    repo,
                    "GRR-0002.S01",
                    candidate,
                )

    def test_grr_0002_s01_v2_real_git_witness_aware_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.gcr_adopted_clone(temporary)
            packet, approval_intro = self.install_v2_supplement_authority(repo)
            backlog_path = repo / "planning/backlog.yaml"
            witness_path = repo / recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH
            witness_payload = witness_path.read_bytes()

            recoveryctl.command_supplement_start(
                argparse.Namespace(repo=repo, supplement="GRR-0002.S01", agent="codex")
            )
            started = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            installed = started["control_plane"]["recovery_holds"][1]["supplements"][0]
            self.assertEqual(8, started["control_plane"]["revision"])
            self.assertEqual(7, installed["predecessor_control_revision"])
            self.assertEqual(8, installed["successor_control_revision"])
            self.assertEqual("IN_PROGRESS", installed["bootstrap"]["status"])
            self.git(repo, "add", "planning/backlog.yaml")
            self.git(repo, "commit", "-m", "fixture: start GRR-0002.S01 B01")
            candidate = self.git(repo, "rev-parse", "HEAD")

            evidence_relative = "planning/governance-recovery-approvals/GRR-0002.B01.evidence.json"
            changed_paths = self.git(repo, "diff", "--name-only", f"{approval_intro}..{candidate}", "--").splitlines()
            evidence = {
                "schemaVersion": "1.0",
                "documentType": "governance-recovery-supplement-bootstrap-evidence",
                "recoveryRequestId": "GRR-0002",
                "supplementId": "GRR-0002.S01",
                "bootstrapUnit": "GRR-0002.B01",
                "branch": self.git(repo, "branch", "--show-current"),
                "baseCommit": approval_intro,
                "candidateCommit": candidate,
                "changedPaths": changed_paths,
                "riskAnalysis": "The real-Git fixture traverses the exact witness-aware v2 lane.",
                "requiredOutcomes": [
                    {"criterion": criterion, "evidence": ["The real-Git lifecycle passed."]}
                    for criterion in packet["supplementalBootstrap"]["requiredOutcomes"]
                ],
                "acceptanceCriteria": [
                    {"criterion": criterion, "evidence": ["The real-Git lifecycle passed."]}
                    for criterion in packet["acceptanceCriteria"]
                ],
                "checks": [{"id": "v2-lifecycle", "command": "fixture:v2-lifecycle", "result": "passed"}],
                "deferredCoverage": ["Ordinary W1 execution remains separately gated."],
                "unverifiedItems": [],
            }
            (repo / evidence_relative).write_bytes((json.dumps(evidence, indent=2) + "\n").encode())
            recoveryctl.freeze_supplement_submission(
                argparse.Namespace(
                    repo=repo,
                    supplement="GRR-0002.S01",
                    agent="codex",
                    implementation_commit=candidate,
                    evidence=evidence_relative,
                ),
                remediation=False,
            )
            self.git(repo, "add", "planning/backlog.yaml", evidence_relative)
            self.git(repo, "commit", "-m", "fixture: freeze GRR-0002.B01 review state")
            reviewed_state = self.git(repo, "rev-parse", "HEAD")
            frozen = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            bootstrap = frozen["control_plane"]["recovery_holds"][1]["supplements"][0]["bootstrap"]
            self.assertEqual("REVIEW", bootstrap["status"])

            ledger_relative = "planning/governance-recovery-approvals/GRR-0002.B01.review-R01.json"
            ledger = {
                "schemaVersion": "1.0",
                "documentType": "governance-recovery-supplement-bootstrap-review",
                "recoveryRequestId": "GRR-0002",
                "supplementId": "GRR-0002.S01",
                "bootstrapUnit": "GRR-0002.B01",
                "attemptId": "R01",
                "candidateCommit": candidate,
                "reviewedStateCommit": reviewed_state,
                "reviewer": "fixture-independent-reviewer",
                "result": "approved",
                "evidence": {
                    "path": evidence_relative,
                    "sha256": recoveryctl.sha256((repo / evidence_relative).read_bytes()),
                },
                "notes": "Approved only for the isolated witness-aware lifecycle fixture.",
                "findings": [],
                "closures": [],
            }
            (repo / ledger_relative).write_bytes((json.dumps(ledger, indent=2) + "\n").encode())
            recoveryctl.command_supplement_review(
                argparse.Namespace(
                    repo=repo,
                    supplement="GRR-0002.S01",
                    reviewer="fixture-independent-reviewer",
                    from_path=ledger_relative,
                )
            )
            self.git(repo, "add", "planning/backlog.yaml", ledger_relative)
            self.git(repo, "commit", "-m", "fixture: approve GRR-0002.B01")
            _approval, _packet, hold, supplement = recoveryctl.validate_supplement(
                repo,
                "GRR-0002.S01",
                require_approved=True,
            )
            self.assertEqual("ACTIVE", hold["status"])
            self.assertEqual("APPROVED", supplement["bootstrap"]["status"])
            self.assertEqual(witness_payload, witness_path.read_bytes())
            self.assertEqual(
                [recoveryctl.CONTROL_RECOVERY_TRIGGER_PATH],
                self.git(repo, "ls-files", "--others", "--exclude-standard").splitlines(),
            )

    def test_released_hold_ecr_identity_is_prefix_stable_when_w1_a04_is_appended(self) -> None:
        data = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        data = copy.deepcopy(data)
        data["wave_amendments"].append({"id": "W1.A04", "target_wave": "W1", "change_request_id": "ECR-0003"})
        errors = taskctl.recovery_hold_errors(data, None)
        self.assertNotIn(
            "HOLD-W1-GRR-0001: post-bootstrap change-request identity is not consecutive",
            errors,
        )

    def test_supplement_submission_review_remediation_and_adversarial_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, approval, packet, b00_snapshot = self.supplement_lifecycle_fixture(temporary)
            backlog_path = repo / "planning/backlog.yaml"
            candidate_r01 = self.git(repo, "rev-parse", "HEAD")
            approval_intro = taskctl.approval_introduction_commit(
                repo,
                "planning/governance-recovery-approvals/GRR-0001.S01.json",
            )
            self.assertIsNotNone(approval_intro)
            evidence_r01 = "planning/governance-recovery-approvals/GRR-0001.B01.evidence.json"
            lawful_evidence = self.write_supplement_evidence(
                repo,
                packet,
                relative=evidence_r01,
                base=str(approval_intro),
                candidate=candidate_r01,
                check_id="supplement-r01",
            )
            submit_args = argparse.Namespace(
                repo=repo,
                supplement="GRR-0001.S01",
                agent="codex",
                implementation_commit=candidate_r01,
                evidence=evidence_r01,
            )
            initial_backlog = backlog_path.read_bytes()

            wrong_actor = copy.deepcopy(submit_args)
            wrong_actor.agent = "other-agent"
            with self.assertRaisesRegex(SystemExit, "retain the installed identity"):
                recoveryctl.freeze_supplement_submission(wrong_actor, remediation=False)
            self.assertEqual(initial_backlog, backlog_path.read_bytes())

            stale_candidate = copy.deepcopy(submit_args)
            stale_candidate.implementation_commit = "0" * 40
            with self.assertRaisesRegex(SystemExit, "must equal current HEAD"):
                recoveryctl.freeze_supplement_submission(stale_candidate, remediation=False)
            self.assertEqual(initial_backlog, backlog_path.read_bytes())

            unsafe_evidence = copy.deepcopy(submit_args)
            unsafe_evidence.evidence = (
                "planning/governance-recovery-approvals/../governance-recovery-approvals/GRR-0001.B01.evidence.json"
            )
            with self.assertRaisesRegex(SystemExit, "evidence path must be"):
                recoveryctl.freeze_supplement_submission(unsafe_evidence, remediation=False)
            self.assertEqual(initial_backlog, backlog_path.read_bytes())

            evidence_path = repo / evidence_r01
            forged_evidence = json.loads(lawful_evidence)
            forged_evidence["candidateCommit"] = "0" * 40
            evidence_path.write_bytes((json.dumps(forged_evidence, indent=2) + "\n").encode())
            with self.assertRaisesRegex(SystemExit, "base/candidate binding mismatch"):
                recoveryctl.freeze_supplement_submission(submit_args, remediation=False)
            self.assertEqual(initial_backlog, backlog_path.read_bytes())
            evidence_path.write_bytes(lawful_evidence)

            controller_path = repo / "tools/recoveryctl.py"
            controller_payload = controller_path.read_bytes()
            controller_path.write_bytes(controller_payload + b"\n# dirty fixture\n")
            with self.assertRaisesRegex(SystemExit, "Tracked worktree changes exist"):
                recoveryctl.freeze_supplement_submission(submit_args, remediation=False)
            self.assertEqual(initial_backlog, backlog_path.read_bytes())
            controller_path.write_bytes(controller_payload)

            stale_payload = backlog_path.read_bytes()
            stale_data = yaml.safe_load(stale_payload)
            backlog_path.write_bytes(stale_payload + b"\n")
            with self.assertRaisesRegex(SystemExit, "Backlog changed after taskctl loaded it"):
                recoveryctl.save_backlog(repo, stale_payload, stale_data)
            self.assertEqual(stale_payload + b"\n", backlog_path.read_bytes())
            backlog_path.write_bytes(stale_payload)

            recoveryctl.freeze_supplement_submission(submit_args, remediation=False)
            frozen_r01 = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            bootstrap_r01 = frozen_r01["control_plane"]["recovery_holds"][0]["supplements"][0]["bootstrap"]
            self.assertEqual("REVIEW", bootstrap_r01["status"])
            self.assertEqual("R01", bootstrap_r01["current_submission"]["attempt_id"])
            self.git(repo, "add", "planning/backlog.yaml", evidence_r01)
            self.git(repo, "commit", "-m", "test: freeze B01 R01 submission")
            reviewed_state_r01 = self.git(repo, "rev-parse", "HEAD")
            review_args = argparse.Namespace(
                repo=repo,
                supplement="GRR-0001.S01",
                reviewer="fixture-independent-reviewer",
                from_path="planning/governance-recovery-approvals/GRR-0001.B01.review-R01.json",
            )
            finding = self.supplement_finding()
            frozen_backlog = backlog_path.read_bytes()

            self.write_supplement_ledger(
                repo,
                result="changes-requested",
                reviewer="codex",
                findings=[finding],
                closures=[],
            )
            self_review_args = copy.deepcopy(review_args)
            self_review_args.reviewer = "codex"
            with self.assertRaisesRegex(SystemExit, "must be independent"):
                recoveryctl.command_supplement_review(self_review_args)
            self.assertEqual(frozen_backlog, backlog_path.read_bytes())

            self.write_supplement_ledger(
                repo,
                result="changes-requested",
                reviewer="fixture-independent-reviewer",
                findings=[finding],
                closures=[],
            )
            mismatched_actor = copy.deepcopy(review_args)
            mismatched_actor.reviewer = "different-reviewer"
            with self.assertRaisesRegex(SystemExit, "actor differs from the ledger"):
                recoveryctl.command_supplement_review(mismatched_actor)
            self.assertEqual(frozen_backlog, backlog_path.read_bytes())

            self.write_supplement_ledger(
                repo,
                result="changes-requested",
                reviewer="fixture-independent-reviewer",
                findings=[finding],
                closures=[],
                evidence_sha256="0" * 64,
            )
            with self.assertRaisesRegex(SystemExit, "evidence differs from the frozen submission"):
                recoveryctl.command_supplement_review(review_args)
            self.assertEqual(frozen_backlog, backlog_path.read_bytes())

            self.write_supplement_ledger(
                repo,
                result="changes-requested",
                reviewer="fixture-independent-reviewer",
                findings=[finding],
                closures=[],
                reviewed_state="0" * 40,
            )
            with self.assertRaisesRegex(SystemExit, "differs from the frozen submission"):
                recoveryctl.command_supplement_review(review_args)
            self.assertEqual(frozen_backlog, backlog_path.read_bytes())

            self.write_supplement_ledger(
                repo,
                result="changes-requested",
                reviewer="fixture-independent-reviewer",
                findings=[finding, copy.deepcopy(finding)],
                closures=[],
            )
            with self.assertRaisesRegex(SystemExit, "invalid finding"):
                recoveryctl.command_supplement_review(review_args)
            self.assertEqual(frozen_backlog, backlog_path.read_bytes())

            self.write_supplement_ledger(
                repo,
                result="approved",
                reviewer="fixture-independent-reviewer",
                findings=[finding],
                closures=[],
            )
            with self.assertRaisesRegex(SystemExit, "cannot introduce or retain blocking findings"):
                recoveryctl.command_supplement_review(review_args)
            self.assertEqual(frozen_backlog, backlog_path.read_bytes())

            unsafe_review_args = copy.deepcopy(review_args)
            unsafe_review_args.from_path = (
                "planning/governance-recovery-approvals/../governance-recovery-approvals/GRR-0001.B01.review-R01.json"
            )
            with self.assertRaisesRegex(SystemExit, "ledger path must be"):
                recoveryctl.command_supplement_review(unsafe_review_args)
            self.assertEqual(frozen_backlog, backlog_path.read_bytes())

            ledger_r01, _ledger = self.write_supplement_ledger(
                repo,
                result="changes-requested",
                reviewer="fixture-independent-reviewer",
                findings=[finding],
                closures=[],
                reviewed_state=reviewed_state_r01,
            )
            recoveryctl.command_supplement_review(review_args)
            adverse_r01 = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            bootstrap_r01 = adverse_r01["control_plane"]["recovery_holds"][0]["supplements"][0]["bootstrap"]
            self.assertEqual("CHANGES_REQUESTED", bootstrap_r01["status"])
            self.assertEqual(["R01"], [item["id"] for item in bootstrap_r01["attempts"]])
            self.git(repo, "add", "planning/backlog.yaml", ledger_r01.relative_to(repo).as_posix())
            self.git(repo, "commit", "-m", "test: record B01 R01 changes requested")

            r01_ledger_payload = ledger_r01.read_bytes()
            adverse_backlog = backlog_path.read_bytes()
            ledger_r01.write_bytes(r01_ledger_payload + b" ")
            with self.assertRaises(SystemExit):
                recoveryctl.validate_supplement(repo, "GRR-0001.S01")
            self.assertEqual(adverse_backlog, backlog_path.read_bytes())
            ledger_r01.write_bytes(r01_ledger_payload)

            evidence_r01_payload = evidence_path.read_bytes()
            evidence_path.write_bytes(evidence_r01_payload + b" ")
            with self.assertRaises(SystemExit):
                recoveryctl.validate_supplement(repo, "GRR-0001.S01")
            self.assertEqual(adverse_backlog, backlog_path.read_bytes())
            evidence_path.write_bytes(evidence_r01_payload)

            marker = repo / "tests/foundation/supplement-lifecycle-fixture.txt"
            marker.write_text("strict descendant remediation\n", encoding="utf-8")
            self.git(repo, "add", marker.relative_to(repo).as_posix())
            self.git(repo, "commit", "-m", "test: remediate B01 R01 finding")
            candidate_r02 = self.git(repo, "rev-parse", "HEAD")
            evidence_r02 = "planning/governance-recovery-approvals/GRR-0001.B01.remediation-01.evidence.json"
            lawful_remediation_evidence = self.write_supplement_evidence(
                repo,
                packet,
                relative=evidence_r02,
                base=candidate_r01,
                candidate=candidate_r02,
                check_id="supplement-r02",
            )
            resubmit_args = argparse.Namespace(
                repo=repo,
                supplement="GRR-0001.S01",
                agent="codex",
                implementation_commit=candidate_r02,
                evidence=evidence_r02,
            )

            old_candidate = copy.deepcopy(resubmit_args)
            old_candidate.implementation_commit = candidate_r01
            with self.assertRaisesRegex(SystemExit, "must equal current HEAD"):
                recoveryctl.freeze_supplement_submission(old_candidate, remediation=True)
            self.assertEqual(adverse_backlog, backlog_path.read_bytes())

            remediation_path = repo / evidence_r02
            forged_remediation = json.loads(lawful_remediation_evidence)
            forged_remediation["baseCommit"] = "0" * 40
            remediation_path.write_bytes((json.dumps(forged_remediation, indent=2) + "\n").encode())
            with self.assertRaisesRegex(SystemExit, "base/candidate binding mismatch"):
                recoveryctl.freeze_supplement_submission(resubmit_args, remediation=True)
            self.assertEqual(adverse_backlog, backlog_path.read_bytes())
            remediation_path.write_bytes(lawful_remediation_evidence)

            marker_payload = marker.read_bytes()
            marker.write_bytes(marker_payload + b"dirty\n")
            with self.assertRaisesRegex(SystemExit, "Tracked worktree changes exist"):
                recoveryctl.freeze_supplement_submission(resubmit_args, remediation=True)
            self.assertEqual(adverse_backlog, backlog_path.read_bytes())
            marker.write_bytes(marker_payload)

            recoveryctl.freeze_supplement_submission(resubmit_args, remediation=True)
            frozen_r02 = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            bootstrap_r02 = frozen_r02["control_plane"]["recovery_holds"][0]["supplements"][0]["bootstrap"]
            self.assertEqual("REVIEW", bootstrap_r02["status"])
            self.assertEqual("R02", bootstrap_r02["current_submission"]["attempt_id"])
            self.git(repo, "add", "planning/backlog.yaml", evidence_r02)
            self.git(repo, "commit", "-m", "test: freeze B01 R02 submission")
            reviewed_state_r02 = self.git(repo, "rev-parse", "HEAD")
            review_r02_args = argparse.Namespace(
                repo=repo,
                supplement="GRR-0001.S01",
                reviewer="fixture-independent-reviewer",
                from_path="planning/governance-recovery-approvals/GRR-0001.B01.review-R02.json",
            )
            frozen_r02_backlog = backlog_path.read_bytes()

            self.write_supplement_ledger(
                repo,
                result="approved",
                reviewer="fixture-independent-reviewer",
                findings=[],
                closures=[],
            )
            with self.assertRaisesRegex(SystemExit, "retain blocking findings"):
                recoveryctl.command_supplement_review(review_r02_args)
            self.assertEqual(frozen_r02_backlog, backlog_path.read_bytes())

            closure = {"findingId": finding["id"], "notes": "Closed by executable lifecycle coverage."}
            self.write_supplement_ledger(
                repo,
                result="approved",
                reviewer="fixture-independent-reviewer",
                findings=[],
                closures=[closure, copy.deepcopy(closure)],
            )
            with self.assertRaisesRegex(SystemExit, "closures are not append-only"):
                recoveryctl.command_supplement_review(review_r02_args)
            self.assertEqual(frozen_r02_backlog, backlog_path.read_bytes())

            unknown_closure = {"findingId": "GRR-0001.B01-R01-UNKNOWN", "notes": "Invalid closure."}
            self.write_supplement_ledger(
                repo,
                result="approved",
                reviewer="fixture-independent-reviewer",
                findings=[],
                closures=[unknown_closure],
            )
            with self.assertRaisesRegex(SystemExit, "closures are not append-only"):
                recoveryctl.command_supplement_review(review_r02_args)
            self.assertEqual(frozen_r02_backlog, backlog_path.read_bytes())

            ledger_r02, _ledger = self.write_supplement_ledger(
                repo,
                result="approved",
                reviewer="fixture-independent-reviewer",
                findings=[],
                closures=[closure],
                reviewed_state=reviewed_state_r02,
            )
            recoveryctl.command_supplement_review(review_r02_args)
            approved = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            hold = approved["control_plane"]["recovery_holds"][0]
            bootstrap = hold["supplements"][0]["bootstrap"]
            self.assertEqual("APPROVED", bootstrap["status"])
            self.assertEqual(["R01", "R02"], [item["id"] for item in bootstrap["attempts"]])
            self.assertIsNone(bootstrap["current_submission"])
            self.assertEqual(b00_snapshot, hold["bootstrap"])

            approved_backlog = backlog_path.read_bytes()
            ledger_r02_payload = ledger_r02.read_bytes()
            ledger_r02.write_bytes(ledger_r02_payload + b" ")
            with self.assertRaises(SystemExit):
                recoveryctl.validate_supplement(repo, "GRR-0001.S01")
            self.assertEqual(approved_backlog, backlog_path.read_bytes())
            ledger_r02.write_bytes(ledger_r02_payload)

            remediation_payload = remediation_path.read_bytes()
            remediation_path.write_bytes(remediation_payload + b" ")
            with self.assertRaises(SystemExit):
                recoveryctl.validate_supplement(repo, "GRR-0001.S01")
            self.assertEqual(approved_backlog, backlog_path.read_bytes())
            remediation_path.write_bytes(remediation_payload)

            _approval, _packet, _hold, validated = recoveryctl.validate_supplement(
                repo,
                "GRR-0001.S01",
            )
            self.assertEqual("APPROVED", validated["bootstrap"]["status"])
            self.assertEqual("APPROVED", approval["status"])

    def test_taskctl_shared_recovery_review_history_denies_projection_tamper(self) -> None:
        _approval, packet, _hold = recoveryctl.validate_request(REPO, "GRR-0001")
        data, _capabilities, _slices, _tasks, _gates = taskctl.load(str(REPO / "planning/backlog.yaml"))
        canonical = data["control_plane"]["recovery_holds"][0]
        self.assertEqual([], taskctl.recovery_review_history_errors(REPO, canonical, packet))
        mutations = {
            "attempt-identity": lambda hold: hold["bootstrap"]["attempts"][-1].__setitem__("id", "R99"),
            "candidate-binding": lambda hold: hold["bootstrap"]["attempts"][-1].__setitem__(
                "implementation_commit", "0" * 40
            ),
            "evidence-binding": lambda hold: hold["bootstrap"]["attempts"][-1]["evidence"].__setitem__(
                "sha256", "0" * 64
            ),
            "reviewer-binding": lambda hold: hold["bootstrap"]["attempts"][-1]["review"].__setitem__(
                "reviewer", "forged-reviewer"
            ),
            "result-binding": lambda hold: hold["bootstrap"]["attempts"][-1]["review"].__setitem__(
                "result", "changes-requested"
            ),
        }
        for label, mutate in mutations.items():
            tampered = copy.deepcopy(canonical)
            mutate(tampered)
            with self.subTest(label=label):
                self.assertTrue(taskctl.recovery_review_history_errors(REPO, tampered, packet))

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

    def test_v3_ecr_schema_requires_exact_recovery_authority_binding(self) -> None:
        schema = json.loads(
            (REPO / "planning/enabler-change-requests/enabler-change-request.v3.schema.json").read_text(
                encoding="utf-8"
            )
        )
        packet = json.loads(
            (REPO / "planning/enabler-change-requests/ECR-0002.packet.json").read_text(encoding="utf-8")
        )
        packet["$schema"] = "./enabler-change-request.v3.schema.json"
        packet["schemaVersion"] = "3.0-proposal"
        packet["changeRequestId"] = "ECR-0003"
        packet["proposedAmendmentId"] = "W1.A04"
        packet["activationBoundary"]["recoveryHoldId"] = "HOLD-W1-GRR-0002"
        packet["recoveryAuthority"] = {
            "recoveryRequestId": "GRR-0002",
            "holdId": "HOLD-W1-GRR-0002",
            "holdStatus": "ACTIVE",
            "packetReference": {
                "path": "planning/governance-recovery-requests/GRR-0002.packet.json",
                "sha256": "a" * 64,
                "commit": "b" * 40,
            },
            "approvalReference": {
                "path": "planning/governance-recovery-approvals/GRR-0002.json",
                "sha256": "c" * 64,
                "introduction_commit": "d" * 40,
            },
            "bootstrap": {
                "id": "GRR-0002.B00",
                "status": "APPROVED",
                "attemptId": "R01",
                "candidateCommit": "e" * 40,
                "reviewedStateCommit": "f" * 40,
                "reviewLedger": {
                    "path": "planning/governance-recovery-approvals/GRR-0002.B00.review-R01.json",
                    "sha256": "1" * 64,
                },
            },
        }
        packet["bootstrapUnit"]["id"] = "W1.A04.B00"
        packet["authorizedTaskIds"] = ["W1.A04.T01"]
        packet["taskInventory"][0]["id"] = "W1.A04.T01"
        packet["taskInventory"][0]["dependencies"] = ["W1.A04.B00"]
        packet["taskInventory"] = packet["taskInventory"][:1]
        packet["files"][1]["path"] = "planning/enabler-change-requests/enabler-change-request.v3.schema.json"
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(packet)))
        del packet["recoveryAuthority"]
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(packet)))

    def test_real_second_ecr_and_third_amendment_append_is_semantic_atomic_and_preserving(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO) as temporary:
            repo, args, before = self.append_fixture(temporary)
            self.assertEqual([], planctl.ecr_validation_errors(repo, "ECR-0002", require_approved=True))

            def loaded() -> tuple[dict, dict, dict, dict, dict]:
                return taskctl.load(args.file)

            missing_closure_state = loaded()
            state_bootstrap = missing_closure_state[0]["control_plane"]["recovery_holds"][0]["bootstrap"]
            latest_attempt = state_bootstrap["attempts"][-1]
            latest_ledger_path = repo / latest_attempt["ledger"]["path"]
            lawful_ledger_payload = latest_ledger_path.read_bytes()
            forged_ledger = json.loads(lawful_ledger_payload)
            forged_ledger["closures"] = []
            forged_ledger_payload = (json.dumps(forged_ledger, indent=2) + "\n").encode()
            latest_ledger_path.write_bytes(forged_ledger_payload)
            latest_attempt["ledger"]["sha256"] = hashlib.sha256(forged_ledger_payload).hexdigest()
            try:
                with self.assertRaisesRegex(SystemExit, "open blocking findings"):
                    taskctl.command_amendment_append_bootstrap_submit(args, *missing_closure_state)
                self.assertEqual(before, Path(args.file).read_bytes())
            finally:
                latest_ledger_path.write_bytes(lawful_ledger_payload)

            unfrozen_review_state = loaded()
            state_bootstrap = unfrozen_review_state[0]["control_plane"]["recovery_holds"][0]["bootstrap"]
            latest_attempt = state_bootstrap["attempts"][-1]
            latest_ledger_path = repo / latest_attempt["ledger"]["path"]
            lawful_ledger_payload = latest_ledger_path.read_bytes()
            forged_ledger = json.loads(lawful_ledger_payload)
            forged_ledger["reviewedStateCommit"] = self.git(repo, "rev-parse", "HEAD")
            forged_ledger_payload = (json.dumps(forged_ledger, indent=2) + "\n").encode()
            latest_ledger_path.write_bytes(forged_ledger_payload)
            latest_attempt["ledger"]["sha256"] = hashlib.sha256(forged_ledger_payload).hexdigest()
            try:
                with self.assertRaisesRegex(SystemExit, "reviewed state lacks its exact frozen submission"):
                    taskctl.command_amendment_append_bootstrap_submit(args, *unfrozen_review_state)
                self.assertEqual(before, Path(args.file).read_bytes())
            finally:
                latest_ledger_path.write_bytes(lawful_ledger_payload)

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
            repeated_separator = copy.deepcopy(args)
            repeated_separator.evidence = "artifacts/evidence//W1.A03.B00.json"
            denial_cases.append(("repeated-separator", repeated_separator, loaded()))
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
            recoveryctl.validate_request(repo, "GRR-0001")
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
            canonical.replace("approvals/", "approvals//"),
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
            review_path.replace("approvals/", "approvals//"),
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
            append_evidence.replace("evidence/", "evidence//"),
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
        parsed = taskctl.build_parser().parse_args(
            [
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
            ]
        )
        data = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        if not taskctl.active_recovery_holds(data):
            data = copy.deepcopy(data)
            data["control_plane"]["recovery_holds"][-1]["status"] = "ACTIVE"
            data["control_plane"]["recovery_holds"][-1]["released_at"] = None
        active = taskctl.active_recovery_holds(data)[0]
        with self.assertRaisesRegex(SystemExit, f"Governance recovery hold {active['id']} denies this mutation"):
            taskctl.require_recovery_hold_permission(parsed, data, {}, REPO)
        with patch.object(taskctl, "CONTROL_TOOL_REVISION", 3):
            errors = taskctl.wave_authority_errors(data, None)
        self.assertTrue(
            {
                "control plane revision is missing or unsupported",
                "this taskctl revision is too old for the active control plane",
            }
            & set(errors)
        )

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
        self.assertIn("already terminally RELEASED", result.stderr)
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
