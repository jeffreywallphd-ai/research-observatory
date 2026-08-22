from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

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
    def test_canonical_recovery_authority_and_hold_validate(self) -> None:
        approval, packet, hold = recoveryctl.validate_request(REPO, "GRR-0001")
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual("W1.A03", packet["postBootstrap"]["requiredAmendmentId"])
        self.assertEqual("ACTIVE", hold["status"])
        self.assertEqual("IN_PROGRESS", hold["bootstrap"]["status"])

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
