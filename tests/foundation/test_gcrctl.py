from __future__ import annotations

import argparse
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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import gcrctl  # noqa: E402
import taskctl  # noqa: E402


class GcrctlTests(unittest.TestCase):
    def git(self, repo: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def write_json(self, repo: Path, relative: str, document: dict) -> Path:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path

    def fixture(self, temporary: str) -> tuple[Path, str, str, dict]:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr@example.test")
        self.git(repo, "config", "user.name", "GCR Test")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-b", gcrctl.BRANCH)
        schema = repo / gcrctl.RUNTIME_SCHEMA_PATH
        schema.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcrctl.RUNTIME_SCHEMA_PATH, schema)
        self.write_json(repo, gcrctl.APPROVAL_PATH, {"fixture": True})
        backlog: dict[str, Any] = {
            "control_plane": {
                "revision": 6,
                "minimum_tool_revision": 6,
                "active_amendment": None,
                "recovery_holds": [],
            }
        }
        (repo / "planning/backlog.yaml").write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "approval base")
        base = self.git(repo, "rev-parse", "HEAD")
        controller = repo / "tools/gcrctl.py"
        controller.parent.mkdir(parents=True, exist_ok=True)
        controller.write_text("# bounded implementation\n", encoding="utf-8")
        self.git(repo, "add", "tools/gcrctl.py")
        self.git(repo, "commit", "-m", "candidate")
        candidate = self.git(repo, "rev-parse", "HEAD")
        trigger = repo / gcrctl.TRIGGER_PATH
        trigger.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcrctl.TRIGGER_PATH, trigger)
        packet = {
            "activationBoundary": {"controlRevision": 6},
            "acceptanceCriteria": ["criterion"],
            "bootstrapUnit": {"authorizedPaths": ["tools/gcrctl.py"]},
        }
        return repo, base, candidate, packet

    def evidence(self, repo: Path, base: str, candidate: str, packet: dict) -> str:
        relative = gcrctl.evidence_path_for("R01")
        self.write_json(
            repo,
            relative,
            {
                "schemaVersion": "1.0-control-recovery-evidence",
                "documentType": "governance-control-recovery-bootstrap-evidence",
                "controlRecoveryId": gcrctl.GCR_ID,
                "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
                "attemptId": "R01",
                "commit": candidate,
                "baseCommit": base,
                "branch": gcrctl.BRANCH,
                "triggerWitness": gcrctl.trigger_witness(),
                "changedFiles": ["tools/gcrctl.py"],
                "checks": [{"id": "focused", "command": "focused", "exitCode": 0, "result": "passed"}],
                "acceptanceCriteria": [
                    {"index": 1, "statement": packet["acceptanceCriteria"][0], "evidence": ["proved"]}
                ],
                "findingClosures": [],
                "unverifiedItems": [],
                "verificationSelection": {
                    "riskAnalysis": "Controller state transition risk.",
                    "selectedChecks": ["focused"],
                    "deferredCoverage": ["Wave qualification"],
                },
            },
        )
        return relative

    def test_current_exact_authority_is_approved_and_witness_is_non_authoritative(self) -> None:
        approval, packet, introduction = gcrctl.load_authority(REPO)
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual(gcrctl.GCR_ID, packet["controlRecoveryId"])
        self.assertEqual(gcrctl.PACKET_COMMIT, approval["packet"]["commit"])
        self.assertEqual(gcrctl.trigger_witness(), approval["triggerWitness"])
        self.assertEqual("c34f8398adc54b3703b94daf7482faf9c09cfdfc", introduction)
        self.assertFalse(approval["triggerWitness"]["executionAuthority"])

    def test_real_git_submit_review_and_direct_child_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, base, candidate, packet = self.fixture(temporary)
            evidence_relative = self.evidence(repo, base, candidate, packet)
            submit = argparse.Namespace(
                repo=repo,
                agent=gcrctl.ACTOR,
                approval_commit=base,
                implementation_commit=candidate,
                evidence=evidence_relative,
            )
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                patch.object(gcrctl, "current_boundary", return_value=(b"backlog", {})),
            ):
                gcrctl.freeze_submission(submit, remediation=False)
            state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual("REVIEW", state["status"])
            self.assertEqual(candidate, state["currentSubmission"]["candidateCommit"])
            self.git(repo, "add", gcrctl.STATE_PATH, evidence_relative)
            self.git(repo, "commit", "-m", "reviewed state")
            reviewed_state = self.git(repo, "rev-parse", "HEAD")

            review_relative = gcrctl.review_path_for("R01")
            self.write_json(
                repo,
                review_relative,
                {
                    "schemaVersion": "1.0-control-recovery-review",
                    "documentType": "governance-control-recovery-bootstrap-review",
                    "controlRecoveryId": gcrctl.GCR_ID,
                    "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
                    "attemptId": "R01",
                    "candidateCommit": candidate,
                    "reviewedStateCommit": reviewed_state,
                    "reviewer": "independent-reviewer",
                    "result": "approved",
                    "evidence": state["currentSubmission"]["evidence"],
                    "findings": [],
                    "closures": [],
                    "notes": "Approved isolated lifecycle.",
                },
            )
            review = argparse.Namespace(repo=repo, reviewer="independent-reviewer", ledger=review_relative)
            with patch.object(gcrctl, "load_authority", return_value=({}, packet, base)):
                gcrctl.command_review(review)
            state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual("APPROVED", state["status"])
            self.assertIsNone(state["currentSubmission"])
            self.git(repo, "add", gcrctl.STATE_PATH, review_relative)
            self.git(repo, "commit", "-m", "approved state")
            approved_state = self.git(repo, "rev-parse", "HEAD")

            adoption_relative = "artifacts/evidence/governance-control-recovery/GCR-0001.B00.adoption.json"
            self.write_json(
                repo,
                adoption_relative,
                {
                    "schemaVersion": "1.0-control-recovery-adoption-evidence",
                    "documentType": "governance-control-recovery-adoption-evidence",
                    "controlRecoveryId": gcrctl.GCR_ID,
                    "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
                    "reviewedStateCommit": approved_state,
                    "triggerWitness": gcrctl.trigger_witness(),
                    "predecessorRevision": 6,
                    "successorRevision": 7,
                    "expectedChangedFiles": ["planning/backlog.yaml", gcrctl.STATE_PATH],
                    "checks": [{"id": "adoption", "command": "adoption", "exitCode": 0, "result": "passed"}],
                    "unverifiedItems": [],
                },
            )
            self.git(repo, "add", adoption_relative)
            self.git(repo, "commit", "-m", "adoption evidence")
            adoption = argparse.Namespace(
                repo=repo,
                approved_state_commit=approved_state,
                evidence=adoption_relative,
                agent=gcrctl.ACTOR,
            )
            backlog_payload = (repo / "planning/backlog.yaml").read_bytes()
            backlog_document = yaml.safe_load(backlog_payload)
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                patch.object(gcrctl, "current_boundary", return_value=(backlog_payload, backlog_document)),
                patch.object(taskctl, "backlog_schema_errors", return_value=[]),
                patch.object(taskctl, "validate", return_value=[]),
            ):
                gcrctl.command_adopt(adoption)
            adopted_backlog = yaml.safe_load((repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
            adopted_state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual(7, adopted_backlog["control_plane"]["revision"])
            self.assertEqual(6, adopted_backlog["control_plane"]["control_generations"][0]["predecessor_revision"])
            self.assertEqual("ADOPTED", adopted_state["status"])
            self.assertEqual(
                sorted(["planning/backlog.yaml", gcrctl.STATE_PATH]),
                sorted(self.git(repo, "diff", "--name-only", "HEAD", "--").splitlines()),
            )

    def test_submit_denies_wrong_actor_without_writing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, base, candidate, packet = self.fixture(temporary)
            evidence_relative = self.evidence(repo, base, candidate, packet)
            args = argparse.Namespace(
                repo=repo,
                agent="other-agent",
                approval_commit=base,
                implementation_commit=candidate,
                evidence=evidence_relative,
            )
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                patch.object(gcrctl, "current_boundary", return_value=(b"backlog", {})),
                self.assertRaisesRegex(SystemExit, "exact actor codex"),
            ):
                gcrctl.freeze_submission(args, remediation=False)
            self.assertFalse((repo / gcrctl.STATE_PATH).exists())


if __name__ == "__main__":
    unittest.main()
