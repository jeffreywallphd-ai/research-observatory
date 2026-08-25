from __future__ import annotations

import argparse
import copy
import json
import shutil
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

import gcr2ctl  # noqa: E402
import taskctl  # noqa: E402


class Gcr2ctlTests(unittest.TestCase):
    def git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

    def write_json(self, repo: Path, relative: str, document: dict) -> Path:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path

    def fixture(self, temporary: str) -> tuple[Path, str, str, dict]:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr2@example.test")
        self.git(repo, "config", "user.name", "GCR2 Test")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-b", gcr2ctl.BRANCH)
        shutil.copy2(REPO / ".gitignore", repo / ".gitignore")
        for relative in (gcr2ctl.RUNTIME_SCHEMA_PATH, gcr2ctl.TRANSACTION_SCHEMA_PATH):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        self.write_json(repo, gcr2ctl.APPROVAL_PATH, {"fixture": True})
        backlog = {
            "control_plane": {
                "revision": 8,
                "minimum_tool_revision": 8,
                "active_amendment": None,
                "recovery_holds": [{"id": "HOLD-W1-GRR-0002", "status": "ACTIVE"}],
                "control_generations": [],
            }
        }
        (repo / gcr2ctl.BACKLOG_PATH).write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "approval base")
        base = self.git(repo, "rev-parse", "HEAD")
        controller = repo / "tools/gcr2ctl.py"
        controller.parent.mkdir(parents=True, exist_ok=True)
        controller.write_text("# bounded GCR-0002 implementation\n", encoding="utf-8")
        self.git(repo, "add", "tools/gcr2ctl.py")
        self.git(repo, "commit", "-m", "implementation candidate")
        candidate = self.git(repo, "rev-parse", "HEAD")
        trigger = repo / gcr2ctl.TRIGGER_PATH
        trigger.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcr2ctl.TRIGGER_PATH, trigger)
        packet = {
            "activationBoundary": {"controlRevision": 8},
            "acceptanceCriteria": ["criterion"],
            "bootstrapUnit": {"authorizedPaths": ["tools/gcr2ctl.py"]},
        }
        return repo, base, candidate, packet

    def evidence(self, repo: Path, base: str, candidate: str, packet: dict) -> str:
        relative = gcr2ctl.evidence_path("R01")
        self.write_json(
            repo,
            relative,
            {
                "schemaVersion": "2.0-control-recovery-evidence",
                "documentType": "governance-control-recovery-bootstrap-evidence",
                "controlRecoveryId": gcr2ctl.GCR_ID,
                "bootstrapUnit": gcr2ctl.BOOTSTRAP_ID,
                "attemptId": "R01",
                "commit": candidate,
                "baseCommit": base,
                "branch": gcr2ctl.BRANCH,
                "triggerWitness": gcr2ctl.trigger_witness(),
                "changedFiles": ["tools/gcr2ctl.py"],
                "checks": [{"id": "focused", "command": "focused", "exitCode": 0, "result": "passed"}],
                "acceptanceCriteria": [
                    {"index": 1, "statement": packet["acceptanceCriteria"][0], "evidence": ["proved"]}
                ],
                "findingClosures": [],
                "unverifiedItems": [],
                "verificationSelection": {
                    "riskAnalysis": "Exact controller state and transaction risk.",
                    "selectedChecks": ["focused"],
                    "deferredCoverage": ["Wave qualification"],
                },
            },
        )
        return relative

    def submitted_fixture(self, temporary: str) -> tuple[Path, dict, str, str, str]:
        repo, base, candidate, packet = self.fixture(temporary)
        evidence = self.evidence(repo, base, candidate, packet)
        args = argparse.Namespace(
            repo=repo,
            agent=gcr2ctl.ACTOR,
            approval_commit=base,
            implementation_commit=candidate,
            evidence=evidence,
        )
        with patch.object(gcr2ctl, "load_authority", return_value=({}, packet, base)):
            gcr2ctl.freeze_submission(args, remediation=False)
        return repo, packet, base, candidate, evidence

    def test_repository_authority_is_valid_at_revision_eight(self) -> None:
        approval, packet, base = gcr2ctl.load_authority(REPO)
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual(gcr2ctl.GCR_ID, packet["controlRecoveryId"])
        self.assertEqual("c029ba348a8bd0abee23e11c078aff4b8fd0b02b", base)
        _payload, backlog = gcr2ctl.current_boundary(REPO, packet, revision=8)
        self.assertEqual(8, backlog["control_plane"]["revision"])

    def test_v3_schemas_are_exactly_revision_eight_to_nine(self) -> None:
        packet_schema = json.loads(
            (REPO / "planning/governance-recovery-requests/governance-recovery-supplement.v3.schema.json").read_text(
                encoding="utf-8"
            )
        )
        approval_schema = json.loads(
            (
                REPO / "planning/governance-recovery-requests/governance-recovery-supplement-approval.v3.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(packet_schema)
        Draft202012Validator.check_schema(approval_schema)
        transition = packet_schema["properties"]["controlTransition"]["properties"]
        self.assertEqual(8, transition["predecessorRevision"]["const"])
        self.assertEqual(9, transition["successorRevision"]["const"])
        self.assertEqual("GRR-0002.S02", packet_schema["properties"]["supplementId"]["const"])
        self.assertEqual("GRR-0002.B02", approval_schema["properties"]["supplementalBootstrapUnit"]["const"])

    def test_submit_freezes_exact_real_git_candidate_and_witness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _packet, _base, candidate, evidence = self.submitted_fixture(temporary)
            state = json.loads((repo / gcr2ctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual("REVIEW", state["status"])
            self.assertEqual(candidate, state["currentSubmission"]["candidateCommit"])
            self.assertEqual(gcr2ctl.trigger_witness(), state["triggerWitness"])
            before = (repo / gcr2ctl.STATE_PATH).read_bytes()
            extra = repo / "unrelated.tmp"
            extra.write_text("denied\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "untracked-path boundary"):
                gcr2ctl.require_workspace(repo, extra_untracked={evidence, gcr2ctl.STATE_PATH})
            self.assertEqual(before, (repo / gcr2ctl.STATE_PATH).read_bytes())

    def test_transaction_schema_rejects_crossed_canonical_bindings(self) -> None:
        predecessor_backlog = yaml.safe_dump({"control_plane": {"revision": 8}}).encode()
        predecessor_state = json.dumps({"status": "APPROVED"}).encode()
        successor_backlog = yaml.safe_dump({"control_plane": {"revision": 9}}).encode()
        successor_state = json.dumps({"status": "ADOPTION_FINALIZATION"}).encode()
        transaction = gcr2ctl.transaction_document(
            predecessor_backlog=predecessor_backlog,
            predecessor_state=predecessor_state,
            successor_backlog=successor_backlog,
            successor_state=successor_state,
            reviewed_state="1" * 40,
            evidence_commit="2" * 40,
        )
        gcr2ctl.validate_transaction(REPO, transaction)
        crossed = copy.deepcopy(transaction)
        crossed["predecessor"]["backlog"]["path"] = gcr2ctl.STATE_PATH
        with self.assertRaisesRegex(SystemExit, "schema validation failed"):
            gcr2ctl.validate_transaction(REPO, crossed)
        redirected = copy.deepcopy(transaction)
        redirected["paths"]["state"] = "planning/other.json"
        with self.assertRaisesRegex(SystemExit, "schema validation failed"):
            gcr2ctl.validate_transaction(REPO, redirected)

    def test_unpublished_transaction_restores_exact_predecessor_and_cleans_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _packet, _base, _candidate, evidence = self.submitted_fixture(temporary)
            self.git(repo, "add", evidence, gcr2ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "freeze submitted state")
            predecessor_backlog = (repo / gcr2ctl.BACKLOG_PATH).read_bytes()
            predecessor_state = (repo / gcr2ctl.STATE_PATH).read_bytes()
            artifacts = gcr2ctl.transaction_artifacts(repo)
            gcr2ctl.write_new_durable(artifacts[gcr2ctl.LOCK_PATH], b"lock\n")
            gcr2ctl.write_new_durable(artifacts[gcr2ctl.BACKLOG_NEXT_PATH], b"substituted\n")
            (repo / gcr2ctl.BACKLOG_PATH).write_bytes(b"partial\n")
            with patch.object(gcr2ctl, "BACKLOG_SHA256", gcr2ctl.sha256(predecessor_backlog)):
                self.assertEqual("RESTORED_PREDECESSOR", gcr2ctl.recover_transaction(repo))
            self.assertEqual(predecessor_backlog, (repo / gcr2ctl.BACKLOG_PATH).read_bytes())
            self.assertEqual(predecessor_state, (repo / gcr2ctl.STATE_PATH).read_bytes())
            self.assertEqual([], gcr2ctl.present_transaction_artifacts(repo))
            self.assertEqual("ABSENT", gcr2ctl.recover_transaction(repo))

    def test_taskctl_revision_eight_reader_fails_closed_on_revision_nine(self) -> None:
        backlog = yaml.safe_load((REPO / gcr2ctl.BACKLOG_PATH).read_text(encoding="utf-8"))
        backlog["control_plane"]["revision"] = 9
        backlog["control_plane"]["minimum_tool_revision"] = 9
        with patch.object(taskctl, "CONTROL_TOOL_REVISION", 8):
            errors = taskctl.wave_authority_errors(backlog, None)
        self.assertTrue(
            any(
                message in errors
                for message in (
                    "this taskctl revision is too old for the active control plane",
                    "control plane revision is missing or unsupported",
                )
            ),
            errors,
        )

    def test_child_process_crashes_recover_to_one_exact_pair(self) -> None:
        boundaries = [
            "lock-durable",
            "backlog-next-durable",
            "state-next-durable",
            "transaction-published",
            "backlog-published",
            "state-published",
            "successor-directories-durable",
            "cleanup-GCR-0002.B00.adoption-transaction.json",
            "cleanup-GCR-0002.B00.adoption.lock",
        ]
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary:
                repo, _packet, _base, _candidate, evidence = self.submitted_fixture(temporary)
                self.git(repo, "add", evidence, gcr2ctl.STATE_PATH)
                self.git(repo, "commit", "-m", "freeze submitted state")
                predecessor_backlog = (repo / gcr2ctl.BACKLOG_PATH).read_bytes()
                predecessor_state = (repo / gcr2ctl.STATE_PATH).read_bytes()
                successor_backlog_document = yaml.safe_load(predecessor_backlog)
                successor_backlog_document["control_plane"]["revision"] = 9
                successor_backlog_document["control_plane"]["minimum_tool_revision"] = 9
                successor_backlog = yaml.safe_dump(successor_backlog_document, sort_keys=False).encode()
                successor_state_document = json.loads(predecessor_state)
                successor_state_document["status"] = "ADOPTION_FINALIZATION"
                successor_state = (json.dumps(successor_state_document, indent=2) + "\n").encode()
                child = "\n".join(
                    [
                        "import json, os, pathlib, sys, yaml",
                        "from unittest.mock import patch",
                        f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                        "import gcr2ctl, taskctl",
                        "repo = pathlib.Path(sys.argv[1])",
                        "boundary = sys.argv[2]",
                        "old_backlog = (repo / gcr2ctl.BACKLOG_PATH).read_bytes()",
                        "old_state = (repo / gcr2ctl.STATE_PATH).read_bytes()",
                        "backlog = yaml.safe_load(old_backlog)",
                        "backlog['control_plane']['revision'] = 9",
                        "backlog['control_plane']['minimum_tool_revision'] = 9",
                        "new_backlog = yaml.safe_dump(backlog, sort_keys=False).encode()",
                        "state = json.loads(old_state)",
                        "state['status'] = 'ADOPTION_FINALIZATION'",
                        "new_state = (json.dumps(state, indent=2) + '\\n').encode()",
                        "transaction = gcr2ctl.transaction_document(",
                        "  predecessor_backlog=old_backlog, predecessor_state=old_state,",
                        "  successor_backlog=new_backlog, successor_state=new_state,",
                        "  reviewed_state='1' * 40, evidence_commit='2' * 40)",
                        "def crash(label):",
                        "  if label == boundary: os._exit(77)",
                        "gcr2ctl.adoption_fault_boundary = crash",
                        "artifacts = gcr2ctl.transaction_artifacts(repo)",
                        (
                            "with taskctl.exclusive_backlog_lock(repo / gcr2ctl.BACKLOG_PATH), "
                            "gcr2ctl.transaction_lock(repo):"
                        ),
                        "  gcr2ctl.write_new_durable(artifacts[gcr2ctl.BACKLOG_NEXT_PATH], new_backlog)",
                        "  crash('backlog-next-durable')",
                        "  gcr2ctl.write_new_durable(artifacts[gcr2ctl.STATE_NEXT_PATH], new_state)",
                        "  crash('state-next-durable')",
                        (
                            "  gcr2ctl.write_new_durable(artifacts[gcr2ctl.TRANSACTION_PATH], "
                            "(json.dumps(transaction, indent=2) + '\\n').encode())"
                        ),
                        "  crash('transaction-published')",
                        "  with patch.object(gcr2ctl, 'validate_successor_pair'):",
                        "    gcr2ctl.complete_transaction(repo, transaction)",
                    ]
                )
                result = subprocess.run(
                    [sys.executable, "-c", child, str(repo), boundary],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                if gcr2ctl.present_transaction_artifacts(repo):
                    with (
                        patch.object(gcr2ctl, "BACKLOG_SHA256", gcr2ctl.sha256(predecessor_backlog)),
                        patch.object(gcr2ctl, "validate_successor_pair"),
                    ):
                        outcome = gcr2ctl.recover_transaction(repo)
                    self.assertIn(outcome, {"RESTORED_PREDECESSOR", "COMPLETED_SUCCESSOR"})
                live = (
                    (repo / gcr2ctl.BACKLOG_PATH).read_bytes(),
                    (repo / gcr2ctl.STATE_PATH).read_bytes(),
                )
                self.assertIn(
                    live,
                    {
                        (predecessor_backlog, predecessor_state),
                        (successor_backlog, successor_state),
                    },
                )
                self.assertEqual([], gcr2ctl.present_transaction_artifacts(repo))
                self.assertEqual("ABSENT", gcr2ctl.recover_transaction(repo))


if __name__ == "__main__":
    unittest.main()
