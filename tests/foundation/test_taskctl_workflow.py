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
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from taskctl import (  # noqa: E402
    build_parser,
    command_block,
    command_cancel,
    command_capability_resume,
    command_capability_review,
    command_capability_start,
    command_claim,
    command_evidence,
    command_gate_approve,
    command_next,
    command_renew,
    command_reopen,
    command_review,
    command_slice_review,
    command_submit,
    evidence_reference_errors,
    evidence_sha256,
    exact_commit_errors,
    git_execution_identity,
    identity_snapshot,
    load,
    new_lease,
    save_atomic,
    save_validated,
    validate,
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
            "deployment_profiles": ["LOC"],
            "platform_targets": ["platform-neutral"],
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
                "branch": "codex/test",
                "base_sha": "a" * 40,
                "worktree": str(REPO),
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

    def test_next_at_pending_release_gate_prints_decision_complete_handoff(self) -> None:
        data, capabilities, slices, tasks, gates = self.workflow()
        gate = {
            "id": "G0",
            "after_wave": "W0",
            "name": "Test release gate",
            "criteria": ["Exact evidence proves the test outcome."],
            "status": "PENDING",
            "unlocks_waves": ["W0"],
            "approval": {"approved_by": None, "approved_at": None, "evidence": [], "notes": None},
        }
        data["waves"][0]["activation_gate"] = "G0"
        data["release_gates"] = [gate]
        gates["G0"] = gate
        args = Namespace(
            profile="LOC",
            platform="windows-x64",
            file=str(REPO / "planning" / "backlog.yaml"),
        )
        output = io.StringIO()
        with redirect_stdout(output):
            command_next(args, data, capabilities, slices, tasks, gates)
        rendered = output.getvalue()
        self.assertIn("STOPPED AT RELEASE GATE G0: Test release gate", rendered)
        self.assertIn("NOT CURRENTLY APPROVABLE: 1 W0 tasks are not DONE", rendered)
        self.assertIn("What the eventual approval must establish", rendered)
        self.assertIn("Exact evidence proves the test outcome", rendered)
        self.assertIn("planning/review-site/CAP-00/index.html", rendered)
        self.assertIn("planning/review-site/CAP-00/CAP-00.S01.html", rendered)
        self.assertIn("Decision alternatives", rendered)
        self.assertIn("A (recommended)", rendered)
        self.assertIn("gate approve G0 --approver <human> --evidence <criterion-linked-evidence>", rendered)

    def test_claim_enforces_ready_gate_dependency_profile_and_campaign_lease(self) -> None:
        context = self.workflow()
        with (
            patch("taskctl.persist"),
            patch(
                "taskctl.git_execution_identity",
                return_value=("alice", "codex/test", "a" * 40, REPO.as_posix()),
            ),
        ):
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
                identity = (args.agent.strip(), "codex/test", "a" * 40, REPO.as_posix())
                with (
                    self.assertRaisesRegex(SystemExit, expected),
                    patch("taskctl.persist"),
                    patch("taskctl.git_execution_identity", return_value=identity),
                ):
                    command_claim(args, data, capabilities, slices, tasks, gates)

    def test_active_task_mutations_require_the_lease_owner(self) -> None:
        context = self.workflow()
        task = context[3]["CAP-00.S01.T01"]
        task.update(
            status="IN_PROGRESS",
            owner="alice",
            branch="codex/test",
            base_sha="a" * 40,
            worktree=str(REPO),
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
            worktree=str(REPO),
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
            worktree=str(REPO),
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
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "planning").mkdir()
            (repo / "artifacts" / "evidence").mkdir(parents=True)
            (repo / "planning" / "backlog.yaml").write_text("plan: fixture\n", encoding="utf-8")
            (repo / "implementation.txt").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "test-branch"], cwd=repo, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Taskctl Test"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, capture_output=True, check=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
            ).stdout.strip()
            (repo / "implementation.txt").write_text("implemented\n", encoding="utf-8")
            subprocess.run(["git", "add", "implementation.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "implementation"], cwd=repo, capture_output=True, check=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
            ).stdout.strip()
            task.update(
                status="IN_PROGRESS",
                owner="alice",
                branch="test-branch",
                base_sha=base,
                worktree=repo.as_posix(),
                lease=new_lease("alice", 8),
            )
            context[1]["CAP-00"]["campaign"].update(branch="test-branch", base_sha=base, worktree=repo.as_posix())
            manifest = {
                "taskId": task["id"],
                "commit": head,
                "baseCommit": base,
                "branch": "test-branch",
                "changedFiles": ["implementation.txt"],
                "checks": [{"command": "test", "exitCode": 0}],
                "acceptanceCriteria": [{"criterion_index": 1, "evidence": ["verified"]}],
                "unverifiedItems": [],
            }
            evidence = repo / "artifacts" / "evidence" / "manifest.json"
            evidence.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
            unrelated = repo / "untracked.py"
            unrelated.write_text("raise RuntimeError\n", encoding="utf-8")
            args = Namespace(
                task=task["id"],
                agent="alice",
                from_file=str(evidence),
                file=str(repo / "planning" / "backlog.yaml"),
            )
            with self.assertRaisesRegex(SystemExit, "untracked source"), patch("taskctl.persist"):
                command_evidence(args, *context)
            unrelated.unlink()
            original_read_bytes = Path.read_bytes
            evidence_reads = 0

            def read_snapshot(path: Path) -> bytes:
                nonlocal evidence_reads
                if path == evidence:
                    evidence_reads += 1
                return original_read_bytes(path)

            with patch("taskctl.persist"), patch.object(Path, "read_bytes", read_snapshot):
                command_evidence(args, *context)
            self.assertEqual(1, evidence_reads)
            reference = task["evidence"][0]
            self.assertEqual("artifacts/evidence/manifest.json", reference["path"])
            self.assertEqual(evidence_sha256(evidence.read_bytes()), reference["sha256"])

            alias = evidence.with_name("alias.json")
            alias.write_bytes(evidence.read_bytes())
            args.from_file = str(alias)
            with self.assertRaisesRegex(SystemExit, "Logically duplicate"), patch("taskctl.persist"):
                command_evidence(args, *context)
            alias.unlink()

            forged_reference_manifest = copy.deepcopy(manifest)
            forged_reference_manifest.update(
                baseCommit="0" * 40,
                checks=[{"command": "test", "exitCode": 1}],
                acceptanceCriteria=[],
                unverifiedItems=["missing verification"],
            )
            forged_payload = json.dumps(forged_reference_manifest).encode()
            evidence.write_bytes(forged_payload)
            reference["sha256"] = evidence_sha256(forged_payload)
            reference_errors = evidence_reference_errors({task["id"]: task}, repo)
            self.assertTrue(any("check failed" in error for error in reference_errors))
            self.assertTrue(any("criterion evidence" in error for error in reference_errors))
            self.assertTrue(any("unverifiedItems" in error for error in reference_errors))
            evidence.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
            reference["sha256"] = evidence_sha256(evidence.read_bytes())

            review_fix_source = repo / "review-fix.txt"
            review_fix_source.write_text("review correction\n", encoding="utf-8")
            subprocess.run(["git", "add", "artifacts/evidence/manifest.json", "review-fix.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "review fix"], cwd=repo, capture_output=True, check=True)
            review_fix_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
            ).stdout.strip()
            followup_manifest = {
                **manifest,
                "commit": review_fix_head,
                "baseCommit": head,
                "changedFiles": ["artifacts/evidence/manifest.json", "review-fix.txt"],
                "supersedes": {
                    "path": "artifacts/evidence/manifest.json",
                    "reason": "review correction",
                },
            }
            followup = repo / "artifacts" / "evidence" / "followup.json"
            args.from_file = str(followup)

            omitted_scope = copy.deepcopy(followup_manifest)
            omitted_scope["changedFiles"] = ["review-fix.txt"]
            followup.write_text(json.dumps(omitted_scope), encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(SystemExit, "exactly match"), patch("taskctl.persist"):
                command_evidence(args, *context)

            forged_base = copy.deepcopy(followup_manifest)
            forged_base["baseCommit"] = base
            followup.write_text(json.dumps(forged_base), encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(SystemExit, "baseCommit must equal"), patch("taskctl.persist"):
                command_evidence(args, *context)

            followup.write_text(json.dumps(followup_manifest), encoding="utf-8", newline="\n")
            with patch("taskctl.persist"):
                command_evidence(args, *context)
            followup_reference = task["evidence"][1]

            mutated_followup = copy.deepcopy(followup_manifest)
            mutated_followup["unverifiedItems"] = ["newly unverified after approval"]
            mutated_payload = json.dumps(mutated_followup).encode()
            followup.write_bytes(mutated_payload)
            followup_reference["sha256"] = evidence_sha256(mutated_payload)
            followup_reference["legacy_policy"] = "pre-exact-evidence-hosted-ci-residual-v1"
            task["status"] = "DONE"
            task["review"] = {
                "reviewer": "reviewer",
                "result": "approved",
                "reviewed_at": "2026-08-08T00:00:00+00:00",
                "notes": "approved",
            }
            post_done_errors = evidence_reference_errors({task["id"]: task}, repo)
            self.assertTrue(any("unverifiedItems" in error for error in post_done_errors), post_done_errors)
            self.assertTrue(any("not authorized" in error for error in post_done_errors), post_done_errors)
            task["status"] = "IN_PROGRESS"
            followup_reference.pop("legacy_policy")
            followup.write_text(json.dumps(followup_manifest), encoding="utf-8", newline="\n")
            followup_reference["sha256"] = evidence_sha256(followup.read_bytes())

            stale = copy.deepcopy(manifest)
            stale["commit"] = "0" * 40
            errors = exact_commit_errors(task, stale, repo, evidence_path=evidence)
            self.assertTrue(any("current HEAD" in error for error in errors))

            mutations: list[tuple[dict[str, Any], str]] = [
                ({"changedFiles": []}, "changedFiles must be a non-empty"),
                ({"changedFiles": ["planning/backlog.yaml"]}, "exactly match"),
                ({"checks": [{"exitCode": 0}]}, "non-empty command"),
                ({"unverifiedItems": None}, "unverifiedItems must be present"),
            ]
            for mutation, expected in mutations:
                with self.subTest(expected=expected):
                    forged = copy.deepcopy(manifest)
                    forged.update(mutation)
                    errors = exact_commit_errors(task, forged, repo, evidence_path=evidence)
                    self.assertTrue(any(expected in error for error in errors), errors)

            task["branch"] = "forged-branch"
            forged_branch = copy.deepcopy(manifest)
            forged_branch["branch"] = "forged-branch"
            errors = exact_commit_errors(task, forged_branch, repo, evidence_path=evidence)
            self.assertIn("task branch does not match the current Git branch", errors)
            task["branch"] = "test-branch"

            (repo / "implementation.txt").write_text("dirty after verification\n", encoding="utf-8")
            errors = exact_commit_errors(task, manifest, repo, evidence_path=evidence)
            self.assertIn("tracked worktree changes exist outside the exact implementation commit", errors)

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

    def test_git_execution_identity_requires_real_head_branch_and_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "planning").mkdir()
            backlog = repo / "planning" / "backlog.yaml"
            backlog.write_text("plan: fixture\n", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "identity-branch"], cwd=repo, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Taskctl Test"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, capture_output=True, check=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
            ).stdout.strip()

            identity = git_execution_identity(
                str(backlog),
                agent=" alice ",
                branch="identity-branch",
                base_sha=head,
                worktree=str(repo),
            )
            self.assertEqual(("alice", "identity-branch", head, repo.as_posix()), identity)
            with self.assertRaisesRegex(SystemExit, "current Git HEAD"):
                git_execution_identity(
                    str(backlog),
                    agent="alice",
                    branch="identity-branch",
                    base_sha="0" * 40,
                    worktree=str(repo),
                )
            with self.assertRaisesRegex(SystemExit, "canonical Git worktree"):
                git_execution_identity(
                    str(backlog), agent="alice", branch="identity-branch", base_sha=head, worktree=None
                )
            with self.assertRaisesRegex(SystemExit, "current Git branch"):
                git_execution_identity(str(backlog), agent="alice", branch="other", base_sha=head, worktree=str(repo))

    def test_campaign_start_resume_and_cancellation_follow_explicit_boundaries(self) -> None:
        context = self.workflow()
        capability = context[1]["CAP-00"]
        capability["campaign"]["status"] = "PAUSED"
        start_args = Namespace(
            capability="CAP-00",
            agent="alice",
            branch="codex/test",
            base_sha="a" * 40,
            worktree=str(REPO),
            profile="LOC",
            platform="windows-x64",
            lease_hours=8,
            file=str(REPO / "planning" / "backlog.yaml"),
        )
        identity = ("alice", "codex/test", "a" * 40, REPO.as_posix())
        with (
            self.assertRaisesRegex(SystemExit, "cannot start from campaign state PAUSED"),
            patch("taskctl.git_execution_identity", return_value=identity),
            patch("taskctl.persist"),
        ):
            command_capability_start(start_args, *context)

        resume_args = copy.copy(start_args)
        resume_args.profile = "CLD"
        with (
            self.assertRaisesRegex(SystemExit, "not eligible"),
            patch("taskctl.git_execution_identity", return_value=identity),
            patch("taskctl.persist"),
        ):
            command_capability_resume(resume_args, *context)
        resume_args.profile = "LOC"
        resume_args.agent = " alice "
        with patch("taskctl.git_execution_identity", return_value=identity), patch("taskctl.persist"):
            command_capability_resume(resume_args, *context)
        self.assertEqual("alice", capability["campaign"]["owner"])

        task = context[3]["CAP-00.S01.T01"]
        with self.assertRaisesRegex(SystemExit, "owned by alice, not bob"), patch("taskctl.persist"):
            command_cancel(
                Namespace(task=task["id"], actor="bob", reason="cancel", replacement=None, file="unused"),
                *context,
            )
        with patch("taskctl.persist"):
            command_cancel(
                Namespace(task=task["id"], actor=" alice ", reason="cancel", replacement=None, file="unused"),
                *context,
            )
        self.assertEqual("alice", task["cancellation"]["cancelled_by"])
        with self.assertRaisesRegex(SystemExit, "CANCELLED tasks cannot"), patch("taskctl.persist"):
            command_cancel(
                Namespace(task=task["id"], actor="mallory", reason="rewrite", replacement=None, file="unused"),
                *context,
            )

    def test_capability_review_remediation_can_resume_after_every_slice_is_approved(self) -> None:
        context = self.workflow()
        capability = context[1]["CAP-00"]
        for slice_ in capability["slices"]:
            slice_["completion"]["status"] = "APPROVED"
        capability["campaign"].update(status="PAUSED", owner="alice")
        capability["completion"]["status"] = "CHANGES_REQUESTED"
        args = Namespace(
            capability="CAP-00",
            agent="alice",
            branch="codex/test",
            base_sha="a" * 40,
            worktree=str(REPO),
            profile="LOC",
            platform="windows-x64",
            lease_hours=8,
            file=str(REPO / "planning" / "backlog.yaml"),
        )
        identity = ("alice", "codex/test", "a" * 40, REPO.as_posix())

        with patch("taskctl.git_execution_identity", return_value=identity), patch("taskctl.persist"):
            command_capability_resume(args, *context)

        self.assertEqual("ACTIVE", capability["campaign"]["status"])
        self.assertEqual("IN_PROGRESS", capability["completion"]["status"])

        capability["campaign"]["status"] = "PAUSED"
        capability["completion"]["status"] = "APPROVED"
        with (
            self.assertRaisesRegex(SystemExit, "no eligible slice or capability-review remediation"),
            patch("taskctl.git_execution_identity", return_value=identity),
            patch("taskctl.persist"),
        ):
            command_capability_resume(args, *context)

    def test_task_slice_and_capability_owners_cannot_self_review(self) -> None:
        context = self.workflow()
        task = context[3]["CAP-00.S01.T01"]
        task.update(
            status="REVIEW",
            owner="alice",
            branch="codex/test",
            base_sha="a" * 40,
            worktree=str(REPO),
            lease=new_lease("alice", 8),
            evidence=[{"type": "criterion-manifest"}],
            verification_state="passed",
        )
        review_args = Namespace(
            task=task["id"], reviewer=" alice ", result="approved", note="", lease_hours=8, file="unused"
        )
        with self.assertRaisesRegex(SystemExit, "independent from the task owner"), patch("taskctl.persist"):
            command_review(review_args, *context)

        slice_ = context[2]["CAP-00.S01"]
        slice_["completion"]["status"] = "REVIEW"
        with self.assertRaisesRegex(SystemExit, "independent from the campaign owner"), patch("taskctl.persist"):
            command_slice_review(
                Namespace(slice=slice_["id"], reviewer="alice", result="approved", note="", file="unused"),
                *context,
            )

        capability = context[1]["CAP-00"]
        capability["campaign"]["status"] = "REVIEW"
        capability["completion"]["status"] = "REVIEW"
        with self.assertRaisesRegex(SystemExit, "independent from the campaign owner"), patch("taskctl.persist"):
            command_capability_review(
                Namespace(capability=capability["id"], reviewer="alice", result="approved", note="", file="unused"),
                *context,
            )

    def test_approved_release_gate_remains_a_semantic_invariant_and_blocks_reopen(self) -> None:
        data, capabilities, slices, tasks, _ = self.workflow()
        gate = {
            "id": "G0",
            "status": "APPROVED",
            "after_wave": "W0",
            "unlocks_waves": [],
            "approval": {
                "approved_by": "reviewer",
                "approved_at": "2026-01-01T00:00:00+00:00",
                "evidence": ["report.json"],
            },
        }
        gates = {"G0": gate}
        data["release_gates"] = [gate]
        errors = validate(data, capabilities, slices, tasks, gates)
        self.assertIn("G0: APPROVED while preceding-wave task CAP-00.S01.T01 is incomplete", errors)

        task = tasks["CAP-00.S01.T01"]
        task.update(
            status="DONE",
            owner="alice",
            branch="codex/test",
            base_sha="a" * 40,
            worktree=str(REPO),
            lease=None,
            evidence=[{"type": "criterion-manifest"}],
            verification_state="passed",
            review={"reviewer": "reviewer", "result": "approved", "reviewed_at": "2026-01-01T00:00:00+00:00"},
        )
        with self.assertRaisesRegex(SystemExit, "release gate is APPROVED"), patch("taskctl.persist"):
            command_reopen(
                Namespace(task=task["id"], agent="alice", reason="reopen", lease_hours=8, file="unused"),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

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
