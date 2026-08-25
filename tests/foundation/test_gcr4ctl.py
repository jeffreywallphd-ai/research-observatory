from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import gcr4ctl  # noqa: E402


class Gcr4ctlTests(unittest.TestCase):
    def git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def exact_boundary_fixture(self, temporary: str) -> Path:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr4@example.test")
        self.git(repo, "config", "user.name", "GCR4 Test")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-b", gcr4ctl.BRANCH)
        for relative in (
            gcr4ctl.GCR3_RUNTIME_V3_PATH,
            gcr4ctl.GCR3_SUCCESSOR_SCHEMA_PATH,
            gcr4ctl.TRANSACTION_SCHEMA_PATH,
        ):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        state = subprocess.run(
            ["git", "show", f"{gcr4ctl.GCR3_REVIEWED_STATE_COMMIT}:{gcr4ctl.GCR3_STATE_PATH}"],
            cwd=REPO,
            capture_output=True,
            check=True,
        ).stdout
        state_path = repo / gcr4ctl.GCR3_STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_bytes(state)
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "exact frozen boundary")
        for relative in (gcr4ctl.TRIGGER_PATH, gcr4ctl.GCR3_LEDGER_PATH):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        return repo

    def test_optional_state_loader_accepts_authorized_absence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self.assertEqual((None, None), gcr4ctl.load_state(repo, required=False))
            with self.assertRaisesRegex(SystemExit, "state is absent"):
                gcr4ctl.load_state(repo, required=True)

    def test_exact_approved_authority_is_valid(self) -> None:
        approval, packet, introduction = gcr4ctl.load_authority(REPO)
        self.assertEqual(gcr4ctl.APPROVAL_COMMIT, introduction)
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual(gcr4ctl.BOOTSTRAP_ID, packet["bootstrapUnit"]["id"])

    def test_packet_and_all_new_schemas_are_draft_2020_12_valid(self) -> None:
        packet = json.loads((REPO / gcr4ctl.PACKET_PATH).read_bytes())
        gcr4ctl.validate_schema(REPO, packet, gcr4ctl.REQUEST_SCHEMA_PATH, "GCR-0004 packet")
        for relative in (
            gcr4ctl.REQUEST_SCHEMA_PATH,
            gcr4ctl.RUNTIME_SCHEMA_PATH,
            gcr4ctl.TRANSACTION_SCHEMA_PATH,
            gcr4ctl.GCR3_SUCCESSOR_SCHEMA_PATH,
        ):
            Draft202012Validator.check_schema(json.loads((REPO / relative).read_bytes()))

    def test_real_git_workspace_and_exact_adverse_derivation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.exact_boundary_fixture(temporary)
            gcr4ctl.require_workspace(repo)
            state = gcr4ctl.recovered_gcr3_state(
                repo,
                approved_state="a" * 40,
                evidence_commit="b" * 40,
                evidence_payload=b'{"exact":true}\n',
            )
            self.assertEqual("CHANGES_REQUESTED", state["status"])
            self.assertEqual(1, len(state["attempts"]))
            self.assertEqual(2, len(state["attempts"][0]["findings"]))
            self.assertEqual([], state["attempts"][0]["closures"])
            self.assertIsNone(state["currentSubmission"])
            self.assertIsNone(state["adoption"])
            self.assertFalse(state["reviewTransitionRecovery"]["ordinaryExecutionAuthority"])
            payload = (json.dumps(state, indent=2) + "\n").encode()
            gcr4ctl.validate_successor(repo, payload)

            old_schema = json.loads((repo / gcr4ctl.GCR3_RUNTIME_V3_PATH).read_bytes())
            self.assertTrue(list(Draft202012Validator(old_schema).iter_errors(state)))
            successor_schema = json.loads((repo / gcr4ctl.GCR3_SUCCESSOR_SCHEMA_PATH).read_bytes())
            self.assertEqual([], list(Draft202012Validator(successor_schema).iter_errors(state)))

            transaction = gcr4ctl.transaction_document(
                predecessor=(repo / gcr4ctl.GCR3_STATE_PATH).read_bytes(),
                successor=payload,
                approved_state="a" * 40,
                evidence_commit="b" * 40,
            )
            gcr4ctl.validate_transaction(repo, transaction)
            transaction["unexpected"] = True
            with self.assertRaises(SystemExit):
                gcr4ctl.validate_transaction(repo, transaction)

    def test_workspace_rejects_any_third_untracked_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.exact_boundary_fixture(temporary)
            (repo / "unexpected.txt").write_text("denied\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "untracked-path boundary differs"):
                gcr4ctl.require_workspace(repo)

    def test_successor_schema_rejects_substituted_bridge_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.exact_boundary_fixture(temporary)
            state = gcr4ctl.recovered_gcr3_state(
                repo,
                approved_state="a" * 40,
                evidence_commit="b" * 40,
                evidence_payload=b'{"exact":true}\n',
            )
            state["reviewTransitionRecovery"]["reviewedStateCommit"] = "f" * 40
            with self.assertRaisesRegex(SystemExit, "schema validation failed"):
                gcr4ctl.validate_successor(repo, (json.dumps(state) + "\n").encode())

    def test_child_process_crashes_recover_to_one_exact_state(self) -> None:
        boundaries = [
            "gcr4-lock-durable",
            "gcr4-state-next-durable",
            "gcr4-transaction-published",
            "gcr4-state-published",
            "gcr4-state-directory-durable",
            "gcr4-cleanup-GCR-0004.B00.application-transaction.json",
            "gcr4-cleanup-GCR-0004.B00.application.lock",
        ]
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary:
                repo = self.exact_boundary_fixture(temporary)
                predecessor = (repo / gcr4ctl.GCR3_STATE_PATH).read_bytes()
                approved_state = self.git(repo, "rev-parse", "HEAD")
                evidence_path = repo / gcr4ctl.APPLICATION_EVIDENCE_PATH
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                evidence_payload = b'{"exact":"application-evidence"}\n'
                evidence_path.write_bytes(evidence_payload)
                self.git(repo, "add", gcr4ctl.APPLICATION_EVIDENCE_PATH)
                self.git(repo, "commit", "-m", "exact application evidence")
                evidence_commit = self.git(repo, "rev-parse", "HEAD")
                successor_document = gcr4ctl.recovered_gcr3_state(
                    repo,
                    approved_state=approved_state,
                    evidence_commit=evidence_commit,
                    evidence_payload=evidence_payload,
                )
                successor = (json.dumps(successor_document, indent=2) + "\n").encode()
                transaction = gcr4ctl.transaction_document(
                    predecessor=predecessor,
                    successor=successor,
                    approved_state=approved_state,
                    evidence_commit=evidence_commit,
                )
                anchor = gcr4ctl.application_anchor(
                    approved_state=approved_state,
                    evidence_commit=evidence_commit,
                    predecessor_payload=predecessor,
                    successor_payload=successor,
                )
                metadata = repo / ".git/gcr4-test"
                metadata.mkdir()
                (metadata / "transaction.json").write_bytes((json.dumps(transaction, indent=2) + "\n").encode())
                (metadata / "anchor.json").write_bytes((json.dumps(anchor, indent=2) + "\n").encode())
                (metadata / "successor.json").write_bytes(successor)
                child = "\n".join(
                    [
                        "import json, os, pathlib, sys",
                        f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                        "import gcr4ctl",
                        "repo = pathlib.Path(sys.argv[1])",
                        "boundary = sys.argv[2]",
                        "meta = repo / '.git/gcr4-test'",
                        "transaction = json.loads((meta / 'transaction.json').read_bytes())",
                        "anchor = json.loads((meta / 'anchor.json').read_bytes())",
                        "successor = (meta / 'successor.json').read_bytes()",
                        "def crash(label):",
                        "  if label == boundary: os._exit(77)",
                        "gcr4ctl.adoption_fault_boundary = crash",
                        "artifacts = gcr4ctl.transaction_artifacts(repo)",
                        "with gcr4ctl.transaction_lock(repo, anchor=anchor):",
                        ("  gcr4ctl.write_new_durable(artifacts[gcr4ctl.STATE_NEXT_PATH], successor)"),
                        "  crash('gcr4-state-next-durable')",
                        (
                            "  gcr4ctl.write_new_durable(artifacts[gcr4ctl.TRANSACTION_PATH], "
                            "(json.dumps(transaction, indent=2) + '\\n').encode())"
                        ),
                        "  crash('gcr4-transaction-published')",
                        "  gcr4ctl.complete_transaction(repo, transaction)",
                    ]
                )
                result = subprocess.run(
                    [sys.executable, "-c", child, str(repo), boundary],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                if gcr4ctl.present_transaction_artifacts(repo):
                    self.assertIn(
                        gcr4ctl.recover_transaction(repo),
                        {"RESTORED_PREDECESSOR", "COMPLETED_SUCCESSOR"},
                    )
                self.assertIn(
                    (repo / gcr4ctl.GCR3_STATE_PATH).read_bytes(),
                    {predecessor, successor},
                )
                self.assertEqual([], gcr4ctl.present_transaction_artifacts(repo))
                self.assertEqual("ABSENT", gcr4ctl.recover_transaction(repo))


if __name__ == "__main__":
    unittest.main()
