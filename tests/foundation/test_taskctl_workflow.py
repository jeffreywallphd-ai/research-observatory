from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from taskctl import (  # noqa: E402
    build_parser,
    command_block,
    command_claim,
    command_evidence,
    command_gate_approve,
    command_renew,
    command_review,
    command_submit,
    evidence_sha256,
    exact_commit_errors,
    identity_snapshot,
    load,
    new_lease,
    save_atomic,
    save_validated,
)


class TaskctlWorkflowTests(unittest.TestCase):
    def workflow(self) -> tuple[dict, dict, dict, dict, dict]:
        task = {
            "id": "CAP-00.S01.T01",
            "capability_id": "CAP-00",
            "slice_id": "CAP-00.S01",
            "acceptance_criteria": ["criterion"],
            "dependencies": [],
            "status": "READY",
            "wave": "W0",
            "deployment_profiles": ["LOC"],
            "platform_targets": ["platform-neutral"],
            "owner": None,
            "branch": None,
            "base_sha": None,
            "worktree": None,
            "lease": None,
            "started_at": None,
            "updated_at": None,
            "completed_at": None,
            "blocker": None,
            "implementation_notes": "",
            "evidence": [],
            "verification_state": None,
            "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
        }
        slice_ = {
            "id": "CAP-00.S01",
            "status": "READY",
            "wave": "W0",
            "_position": 0,
            "completion": {"status": "PENDING", "reviewer": None, "reviewed_at": None, "evidence": []},
            "depends_on": [],
            "tasks": [task],
        }
        capability = {
            "id": "CAP-00",
            "execution_mode": "capability_campaign",
            "campaign": {
                "status": "ACTIVE",
                "owner": "alice",
                "profile": "LOC",
                "platform": "windows-x64",
                "lease": new_lease("alice", 8),
            },
            "completion": {"status": "IN_PROGRESS"},
            "slices": [slice_],
        }
        data = {
            "waves": [{"id": "W0", "activation_gate": None}],
            "capabilities": [capability],
            "release_gates": [],
        }
        return data, {"CAP-00": capability}, {"CAP-00.S01": slice_}, {task["id"]: task}, {}

    def claim_args(self, **overrides: object) -> Namespace:
        values: dict[str, object] = {
            "task": "CAP-00.S01.T01",
            "agent": "alice",
            "branch": "codex/test",
            "base_sha": "a" * 40,
            "worktree": str(REPO),
            "profile": "LOC",
            "platform": "windows-x64",
            "lease_hours": 8,
            "file": str(REPO / "planning" / "backlog.yaml"),
        }
        values.update(overrides)
        return Namespace(**values)

    def test_claim_enforces_ready_gate_dependency_profile_and_campaign_lease(self) -> None:
        context = self.workflow()
        with patch("taskctl.persist"):
            command_claim(self.claim_args(), *context)
        self.assertEqual("IN_PROGRESS", context[3]["CAP-00.S01.T01"]["status"])
        self.assertEqual("alice", context[3]["CAP-00.S01.T01"]["lease"]["claimed_by"])

        for mutation, expected in [
            ("dependency", "not READY"),
            ("slice_dependency", "not READY"),
            ("gate", "not READY"),
            ("profile", "not eligible"),
            ("owner", "owned by alice, not bob"),
        ]:
            with self.subTest(mutation=mutation):
                data, capabilities, slices, tasks, gates = self.workflow()
                args = self.claim_args()
                task = tasks["CAP-00.S01.T01"]
                if mutation == "dependency":
                    dependency = copy.deepcopy(task)
                    dependency.update(id="CAP-00.S01.T00", status="NOT_STARTED")
                    tasks[dependency["id"]] = dependency
                    slices["CAP-00.S01"]["tasks"].insert(0, dependency)
                    task["dependencies"] = [dependency["id"]]
                elif mutation == "slice_dependency":
                    dependency = copy.deepcopy(task)
                    dependency.update(id="CAP-00.S01.T00", status="NOT_STARTED")
                    tasks[dependency["id"]] = dependency
                    slices["CAP-00.S01"]["tasks"].insert(0, dependency)
                    slices["CAP-00.S01"]["depends_on"] = [dependency["id"]]
                elif mutation == "gate":
                    data["waves"][0]["activation_gate"] = "G0"
                    gates["G0"] = {"id": "G0", "status": "PENDING"}
                elif mutation == "profile":
                    task["deployment_profiles"] = ["CLD"]
                else:
                    args.agent = "bob"
                with self.assertRaisesRegex(SystemExit, expected), patch("taskctl.persist"):
                    command_claim(args, data, capabilities, slices, tasks, gates)

    def test_active_task_mutations_require_the_lease_owner(self) -> None:
        context = self.workflow()
        task = context[3]["CAP-00.S01.T01"]
        task.update(
            status="IN_PROGRESS",
            owner="alice",
            branch="codex/test",
            base_sha="a" * 40,
            lease=new_lease("alice", 8),
            evidence=[{"type": "criterion-manifest"}],
            verification_state="passed",
        )
        commands = [
            (
                command_block,
                Namespace(task=task["id"], agent="bob", reason="blocked", next_action="retry", file="unused"),
            ),
            (command_submit, Namespace(task=task["id"], agent="bob", note="", file="unused")),
            (
                command_evidence,
                Namespace(task=task["id"], agent="bob", from_file="missing.json", file="unused"),
            ),
        ]
        for command, args in commands:
            with (
                self.subTest(command=command.__name__),
                self.assertRaisesRegex(SystemExit, "owned by alice, not bob"),
                patch("taskctl.persist"),
            ):
                command(args, *context)

    def test_review_approval_is_legal_only_from_review_and_releases_lease(self) -> None:
        context = self.workflow()
        task = context[3]["CAP-00.S01.T01"]
        args = Namespace(
            task=task["id"], reviewer="reviewer", result="approved", note="verified", lease_hours=8, file="unused"
        )
        with self.assertRaisesRegex(SystemExit, "Only REVIEW"), patch("taskctl.persist"):
            command_review(args, *context)
        task.update(
            status="REVIEW",
            owner="alice",
            branch="codex/test",
            base_sha="a" * 40,
            lease=new_lease("alice", 8),
            evidence=[{"type": "criterion-manifest"}],
            verification_state="passed",
        )
        with patch("taskctl.persist"):
            command_review(args, *context)
        self.assertEqual("DONE", task["status"])
        self.assertIsNone(task["lease"])
        self.assertEqual("approved", task["review"]["result"])
        self.assertEqual("IN_PROGRESS", context[2]["CAP-00.S01"]["status"])

    def test_expired_task_lease_can_be_renewed_only_by_its_owner(self) -> None:
        context = self.workflow()
        task = context[3]["CAP-00.S01.T01"]
        task.update(
            status="IN_PROGRESS",
            owner="alice",
            branch="codex/test",
            base_sha="a" * 40,
            lease={
                "claimed_by": "alice",
                "claimed_at": "2020-01-01T00:00:00+00:00",
                "expires_at": "2020-01-01T01:00:00+00:00",
            },
        )
        with self.assertRaisesRegex(SystemExit, "owned by alice, not bob"), patch("taskctl.persist"):
            command_renew(Namespace(task=task["id"], agent="bob", lease_hours=8, file="unused"), *context)
        with patch("taskctl.persist"):
            command_renew(Namespace(task=task["id"], agent="alice", lease_hours=8, file="unused"), *context)
        self.assertEqual("alice", task["lease"]["claimed_by"])

    def test_evidence_requires_current_head_and_records_canonical_repository_path(self) -> None:
        context = self.workflow()
        task = context[3]["CAP-00.S01.T01"]
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        task.update(
            status="IN_PROGRESS",
            owner="alice",
            branch="codex/test",
            base_sha=head,
            lease=new_lease("alice", 8),
        )
        manifest = {
            "taskId": task["id"],
            "commit": head,
            "baseCommit": head,
            "branch": "codex/test",
            "checks": [{"command": "test", "exitCode": 0}],
            "acceptanceCriteria": [{"criterion_index": 1, "evidence": ["verified"]}],
            "unverifiedItems": [],
        }
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts" / "evidence") as temporary:
            evidence = Path(temporary) / "manifest.json"
            evidence.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
            args = Namespace(
                task=task["id"], agent="alice", from_file=str(evidence), file=str(REPO / "planning" / "backlog.yaml")
            )
            with patch("taskctl.persist"):
                command_evidence(args, *context)
            reference = task["evidence"][0]
            self.assertTrue(reference["path"].startswith("artifacts/evidence/"))
            self.assertNotIn("\\", reference["path"])
            self.assertEqual(evidence_sha256(evidence.read_bytes()), reference["sha256"])

            stale = copy.deepcopy(manifest)
            stale["commit"] = "0" * 40
            errors = exact_commit_errors(task, stale, REPO)
            self.assertTrue(any("current HEAD" in error for error in errors))

    def test_release_gate_rejects_incomplete_wave_and_reapproval(self) -> None:
        data, capabilities, slices, tasks, _ = self.workflow()
        gate = {"id": "G0", "status": "PENDING", "after_wave": "W0", "unlocks_waves": []}
        gates = {"G0": gate}
        data["release_gates"] = [gate]
        args = Namespace(gate="G0", approver="reviewer", evidence=["report.json"], note="", file="unused")
        with self.assertRaisesRegex(SystemExit, "first incomplete task"), patch("taskctl.persist"):
            command_gate_approve(args, data, capabilities, slices, tasks, gates)
        tasks["CAP-00.S01.T01"]["status"] = "DONE"
        with patch("taskctl.persist"):
            command_gate_approve(args, data, capabilities, slices, tasks, gates)
        self.assertEqual("APPROVED", gate["status"])
        with self.assertRaisesRegex(SystemExit, "Only a PENDING"), patch("taskctl.persist"):
            command_gate_approve(args, data, capabilities, slices, tasks, gates)

    def test_atomic_save_preserves_destination_on_replace_failure_and_stale_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backlog.yaml"
            destination.write_text("original: true\n", encoding="utf-8")
            original_sha = hashlib.sha256(destination.read_bytes()).hexdigest()
            with self.assertRaises(OSError), patch("taskctl.os.replace", side_effect=OSError("replace failed")):
                save_atomic(str(destination), {"replacement": True}, expected_sha256=original_sha)
            self.assertEqual("original: true\n", destination.read_text(encoding="utf-8"))
            self.assertEqual([], list(destination.parent.glob("backlog.yaml.*.tmp")))

            destination.write_text("concurrent: true\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "changed after taskctl loaded"):
                save_atomic(str(destination), {"replacement": True}, expected_sha256=original_sha)
            self.assertEqual("concurrent: true\n", destination.read_text(encoding="utf-8"))

    def test_validated_save_rejects_identity_change_and_corrupt_schema_without_writing(self) -> None:
        data, *_ = load(str(REPO / "planning" / "backlog.yaml"))
        original_identity = identity_snapshot(data)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backlog.yaml"
            destination.write_text("sentinel: true\n", encoding="utf-8")
            data["capabilities"][0]["slices"][0]["tasks"][0]["id"] = "CAP-00.S01.T99"
            with self.assertRaisesRegex(SystemExit, "Stable backlog IDs"):
                save_validated(str(destination), data, expected_identity=original_identity)
            self.assertEqual("sentinel: true\n", destination.read_text(encoding="utf-8"))

            clean, *_ = load(str(REPO / "planning" / "backlog.yaml"))
            clean["capabilities"][0]["slices"][0]["tasks"][0]["status"] = "CORRUPT"
            with self.assertRaisesRegex(SystemExit, "Refusing to save invalid backlog schema"):
                save_validated(str(destination), clean)
            self.assertEqual("sentinel: true\n", destination.read_text(encoding="utf-8"))

    def test_parser_has_no_campaign_override_bypass(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            parser.parse_args(
                [
                    "claim",
                    "CAP-00.S01.T01",
                    "--agent",
                    "alice",
                    "--branch",
                    "codex/test",
                    "--base-sha",
                    "a" * 40,
                    "--override-campaign",
                ]
            )


if __name__ == "__main__":
    unittest.main()
