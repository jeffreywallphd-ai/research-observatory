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
        self.git(repo, "checkout", "-B", "codex/w1-windows-local-runtime")
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
        backlog["control_plane"]["revision"] = taskctl.CONTROL_TOOL_REVISION
        backlog["control_plane"]["minimum_tool_revision"] = taskctl.CONTROL_TOOL_REVISION
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
        self.assertEqual(taskctl.CONTROL_TOOL_REVISION, installed["control_plane"]["revision"])
        self.assertEqual(taskctl.CONTROL_TOOL_REVISION, installed["control_plane"]["minimum_tool_revision"])
        supplement = installed["control_plane"]["recovery_holds"][0]["supplements"][0]
        self.assertEqual("GRR-0001.S01", supplement["id"])
        self.assertEqual("GRR-0001.B01", supplement["bootstrap"]["id"])
        self.assertEqual("IN_PROGRESS", supplement["bootstrap"]["status"])
        self.assertEqual([], supplement["bootstrap"]["attempts"])
        self.assertEqual([], taskctl.backlog_schema_errors(taskctl.serializable_backlog(installed)))

        _current_payload, current, _capabilities, _slices, _tasks, _gates = recoveryctl.backlog_state(REPO)
        stale = copy.deepcopy(current)
        stale["control_plane"]["recovery_holds"][0]["id"] = "HOLD-W1-GRR-9999"
        with self.assertRaisesRegex(SystemExit, "activation boundary"):
            recoveryctl.validate_supplement_boundary(REPO, packet, stale, require_installed=True)

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
