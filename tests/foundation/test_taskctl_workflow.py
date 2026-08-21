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

import taskctl as taskctl_module  # noqa: E402
from taskctl import (  # noqa: E402
    amendment_history_snapshot,
    amendment_identity_snapshot,
    approved_wave_snapshot,
    bootstrap_scope_addendum_errors,
    build_parser,
    command_amendment_dispose,
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
    command_wave_checkpoint,
    command_wave_resume,
    command_wave_review,
    command_wave_start,
    command_wave_submit,
    evidence_reference_errors,
    evidence_sha256,
    exact_commit_errors,
    git_execution_identity,
    global_program_position,
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
            "priority": "P0",
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
            "title": "Test workflow",
            "status": "READY",
            "wave": "W0",
            "priority": "P0",
            "_position": 0,
            "completion": {"status": "PENDING", "reviewer": None, "reviewed_at": None, "evidence": []},
            "depends_on": [],
            "deployment_profiles": ["LOC"],
            "platform_targets": ["platform-neutral"],
            "tasks": [task],
        }
        capability = {
            "id": "CAP-00",
            "alias": "CAP-test-workflow",
            "title": "Test workflow capability",
            "execution_mode": "capability_campaign",
            "campaign": {
                "status": "ACTIVE",
                "scope": "capability-wave",
                "wave": "W0",
                "increment_id": "CAP-test-workflow/W0",
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
            "waves": [
                {
                    "id": "W0",
                    "title": "Test wave",
                    "goal": "Exercise workflow controls.",
                    "activation_gate": None,
                    "track": "local-baseline",
                    "approval": {
                        "status": "APPROVED",
                        "approved_by": "reviewer",
                        "approved_at": "2026-08-13T00:00:00+00:00",
                        "approved_commit": "a" * 40,
                        "capability_ids": ["CAP-00"],
                        "decision_ids": [],
                        "slice_ids": ["CAP-00.S01"],
                        "notes": None,
                    },
                    "campaign": None,
                    "checkpoints": [],
                    "completion": {
                        "status": "IN_PROGRESS",
                        "reviewer": None,
                        "reviewed_at": None,
                        "evidence": [],
                        "notes": None,
                    },
                }
            ],
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

    def interrupted_workflow(
        self,
        *,
        lifecycle_status: str = "MATERIALIZED",
        amendment_campaign_status: str | None = None,
    ) -> tuple[dict, dict, dict, dict, dict]:
        data, capabilities, slices, tasks, gates = self.workflow()
        wave = data["waves"][0]
        wave["id"] = "W1"
        wave["campaign"] = {
            "status": "PAUSED",
            "scope": "amendment-hold",
            "owner": "alice",
            "branch": "codex/test",
            "worktree": str(REPO),
            "base_sha": "a" * 40,
            "profile": "LOC",
            "platform": "windows-x64",
            "started_at": "2026-08-20T00:00:00+00:00",
            "updated_at": "2026-08-20T00:00:00+00:00",
            "pause_reason": "Approved interrupting amendment",
            "pause_category": "human-decision",
            "lease": None,
        }
        capability = capabilities["CAP-00"]
        capability["campaign"].update(status="PAUSED", wave="W1", lease=None)
        slice_ = slices["CAP-00.S01"]
        slice_["wave"] = "W1"
        ordinary_task = tasks["CAP-00.S01.T01"]
        ordinary_task["wave"] = "W1"
        campaign = None
        if amendment_campaign_status is not None:
            campaign = {
                "status": amendment_campaign_status,
                "scope": "wave-amendment",
                "owner": "alice",
                "branch": "codex/test",
                "worktree": str(REPO),
                "base_sha": "a" * 40,
                "profile": "LOC",
                "platform": "windows-x64",
                "started_at": "2026-08-20T00:00:00+00:00",
                "updated_at": "2026-08-20T00:00:00+00:00",
                "pause_reason": None,
                "lease": new_lease("alice", 8) if amendment_campaign_status == "ACTIVE" else None,
            }
        event_statuses = ["APPROVED"]
        if lifecycle_status != "APPROVED":
            event_statuses.append(lifecycle_status)
        amendment_tasks = []
        for position, (task_id, dependency) in enumerate(
            [
                ("W1.A02.T01", "W1.A02.B00"),
                ("W1.A02.T02", "W1.A02.T01"),
            ]
        ):
            amendment_task = {
                "id": task_id,
                "amendment_id": "W1.A02",
                "title": f"Approved enabler task {position + 1}",
                "objective": "Exercise the bounded amendment workflow.",
                "dependencies": [dependency],
                "acceptance_criteria": ["The approved boundary remains enforced."],
                "verification_commands": ["python -m unittest"],
                "packet_task_sha256": f"{position + 1}" * 64,
                "status": "NOT_STARTED",
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
                "_amendment_id": "W1.A02",
                "_position": position,
                "_target_wave": "W1",
            }
            amendment_tasks.append(amendment_task)
            tasks[task_id] = amendment_task
        amendment: dict[str, Any] = {
            "id": "W1.A02",
            "change_request_id": "ECR-0001",
            "target_wave": "W1",
            "kind": "gate-integrity-safety-defect",
            "approval_reference": {
                "path": "planning/wave-amendment-approvals/W1.A02.json",
                "sha256": "a" * 64,
                "introduction_commit": "a" * 40,
            },
            "lifecycle": {
                "status": lifecycle_status,
                "history": [
                    {
                        "id": f"E{position:02d}",
                        "status": status,
                        "actor": "agent:bootstrap",
                        "at": "2026-08-20T00:00:00+00:00",
                        "rationale": f"Amendment entered {status}.",
                    }
                    for position, status in enumerate(event_statuses, start=1)
                ],
            },
            "bootstrap": {
                "id": "W1.A02.B00",
                "status": "APPROVED",
                "implementer": "agent:bootstrap",
                "implementation_commit": "b" * 40,
                "evidence": [],
                "review": {
                    "reviewer": "agent:reviewer",
                    "result": "approved",
                    "reviewed_at": "2026-08-20T00:00:00+00:00",
                    "notes": None,
                },
            },
            "campaign": campaign,
            "tasks": amendment_tasks,
            "completion": {
                "status": "PENDING",
                "reviewer": None,
                "reviewed_at": None,
                "evidence": [],
                "notes": None,
            },
        }
        data["control_plane"] = {
            "revision": 2,
            "minimum_tool_revision": 2,
            "active_amendment": "W1.A02" if amendment_campaign_status == "ACTIVE" else None,
        }
        data["wave_amendments"] = [amendment]
        return data, capabilities, slices, tasks, gates

    def packet_bound_active_amendment_workflow(
        self,
    ) -> tuple[tuple[dict, dict, dict, dict, dict], dict[str, Any]]:
        data, *_ = load(str(REPO / "planning" / "backlog.yaml"))
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        packet = json.loads(
            (REPO / "planning/enabler-change-requests/ECR-0001.packet.json").read_text(encoding="utf-8")
        )
        amendment["bootstrap"]["status"] = "APPROVED"
        amendment["bootstrap"]["review"] = {
            "reviewer": "b00-independent-reviewer",
            "result": "approved",
            "reviewed_at": "2026-08-21T00:00:00+00:00",
            "notes": "Approved for adversarial fixture execution.",
        }
        amendment["tasks"] = [
            taskctl_module.materialized_amendment_task("W1.A02", packet_task) for packet_task in packet["taskInventory"]
        ]
        amendment["lifecycle"] = {
            "status": "ACTIVE",
            "history": [
                *amendment["lifecycle"]["history"],
                {
                    "id": "E02",
                    "status": "MATERIALIZED",
                    "actor": "codex",
                    "at": "2026-08-21T00:01:00+00:00",
                    "rationale": "Materialized exact approved tasks for the test fixture.",
                },
                {
                    "id": "E03",
                    "status": "ACTIVE",
                    "actor": "codex",
                    "at": "2026-08-21T00:02:00+00:00",
                    "rationale": "Activated the bounded amendment fixture.",
                },
            ],
        }
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        amendment["campaign"] = {
            "status": "ACTIVE",
            "scope": "wave-amendment",
            "owner": "codex",
            "branch": branch,
            "worktree": str(REPO),
            "base_sha": head,
            "profile": "LOC",
            "platform": "windows-x64",
            "started_at": "2026-08-21T00:02:00+00:00",
            "updated_at": "2026-08-21T00:02:00+00:00",
            "pause_reason": None,
            "lease": new_lease("codex", 8),
        }
        data["control_plane"]["active_amendment"] = "W1.A02"
        wave = next(item for item in data["waves"] if item["id"] == "W1")
        wave["campaign"]["status"] = "PAUSED"
        wave["campaign"]["scope"] = "amendment-hold"
        indexed = taskctl_module.index_backlog(data)
        taskctl_module.refresh_derived_states(*indexed)
        return indexed, packet

    def test_next_at_pending_release_gate_prints_decision_complete_handoff(self) -> None:
        data, capabilities, slices, tasks, gates = self.workflow()
        capability = capabilities["CAP-00"]
        active_slice = slices.pop("CAP-00.S01")
        active_task = tasks.pop("CAP-00.S01.T01")
        completed_task = copy.deepcopy(active_task)
        completed_task.update(id="CAP-00.S00.T01", slice_id="CAP-00.S00", status="DONE")
        completed_slice = copy.deepcopy(active_slice)
        completed_slice.update(
            id="CAP-00.S00",
            title="Completed foundation",
            wave="W0",
            status="DONE",
            tasks=[completed_task],
            completion={
                "status": "APPROVED",
                "reviewer": "agent:reviewer",
                "reviewed_at": "2026-08-13T00:00:00+00:00",
                "evidence": ["evidence.json"],
            },
        )
        active_task.update(wave="W1")
        active_slice.update(wave="W1", _position=1)
        capability["slices"] = [completed_slice, active_slice]
        capability["campaign"].update(status="PAUSED", wave="W0", pause_category="wave-complete", lease=None)
        data["waves"][0]["completion"].update(
            status="APPROVED",
            reviewer="agent:wave-reviewer",
            reviewed_at="2026-08-13T00:00:00+00:00",
            evidence=["wave-report.json"],
        )
        slices.update({completed_slice["id"]: completed_slice, active_slice["id"]: active_slice})
        tasks.update({completed_task["id"]: completed_task, active_task["id"]: active_task})
        gate = {
            "id": "G0",
            "after_wave": "W0",
            "name": "Test release gate",
            "criteria": ["Exact evidence proves the test outcome."],
            "status": "PENDING",
            "unlocks_waves": ["W1"],
            "approval": {"approved_by": None, "approved_at": None, "evidence": [], "notes": None},
        }
        data["waves"].append({"id": "W1", "activation_gate": "G0"})
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
        self.assertIn("READY FOR HUMAN APPROVAL", rendered)
        self.assertIn("What the eventual approval must establish", rendered)
        self.assertIn("Exact evidence proves the test outcome", rendered)
        self.assertIn("planning/review-site/CAP-00/index.html", rendered)
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
        slices["CAP-00.S01"]["status"] = "DONE"
        slices["CAP-00.S01"]["completion"].update(
            status="APPROVED",
            reviewer="agent:reviewer",
            reviewed_at="2026-08-13T00:00:00+00:00",
            evidence=["report.json"],
        )
        data["waves"][0]["completion"] = {
            "status": "APPROVED",
            "reviewer": "agent:wave-reviewer",
            "reviewed_at": "2026-08-13T00:00:00+00:00",
            "evidence": ["wave-report.json"],
            "notes": "qualified",
        }
        with patch("taskctl.persist"):
            command_gate_approve(args, data, capabilities, slices, tasks, gates)
        self.assertEqual("APPROVED", gate["status"])
        with self.assertRaisesRegex(SystemExit, "Only a PENDING"), patch("taskctl.persist"):
            command_gate_approve(args, data, capabilities, slices, tasks, gates)

    def test_release_gates_must_approve_in_wave_order(self) -> None:
        data, capabilities, slices, tasks, _ = self.workflow()
        task = tasks["CAP-00.S01.T01"]
        task.update(status="DONE", wave="W1")
        slice_ = slices["CAP-00.S01"]
        slice_.update(status="DONE", wave="W1")
        slice_["completion"].update(
            status="APPROVED",
            reviewer="agent:reviewer",
            reviewed_at="2026-08-13T00:00:00+00:00",
            evidence=["report.json"],
        )
        first = {"id": "G0", "status": "PENDING", "after_wave": "W0", "unlocks_waves": ["W1"]}
        second = {"id": "G1", "status": "PENDING", "after_wave": "W1", "unlocks_waves": ["W2"]}
        data["release_gates"] = [first, second]
        gates = {"G0": first, "G1": second}
        args = Namespace(gate="G1", approver="reviewer", evidence=["report.json"], note="", file="unused")

        with self.assertRaisesRegex(SystemExit, "upstream gate G0"), patch("taskctl.persist"):
            command_gate_approve(args, data, capabilities, slices, tasks, gates)

    def test_capability_start_records_the_active_wave_increment(self) -> None:
        context = self.workflow()
        capability = context[1]["CAP-00"]
        capability["campaign"] = {"status": "PLANNED"}
        capability["completion"]["status"] = "PENDING"
        args = Namespace(
            capability="CAP-test-workflow",
            wave="W0",
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
            command_capability_start(args, *context)

        self.assertEqual("capability-wave", capability["campaign"]["scope"])
        self.assertEqual("W0", capability["campaign"]["wave"])
        self.assertEqual("CAP-test-workflow/W0", capability["campaign"]["increment_id"])

    def test_wave_start_requires_complete_approval_and_owns_cross_capability_execution(self) -> None:
        context = self.workflow()
        data, capabilities, _slices, _tasks, _gates = context
        capabilities["CAP-00"]["campaign"] = None
        wave = data["waves"][0]
        wave["campaign"] = {"status": "PLANNED"}
        wave["completion"]["status"] = "PENDING"
        args = Namespace(
            wave="W0",
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

        wave["approval"]["status"] = "PENDING"
        with self.assertRaisesRegex(SystemExit, "no approved pre-Wave packet"), patch("taskctl.persist"):
            command_wave_start(args, *context)

        wave["approval"]["status"] = "APPROVED"
        with (
            patch("taskctl.git_execution_identity", return_value=identity),
            patch("taskctl.require_wave_planning_ready"),
            patch("taskctl.persist"),
        ):
            command_wave_start(args, *context)

        self.assertEqual("wave", wave["campaign"]["scope"])
        self.assertEqual("ACTIVE", wave["campaign"]["status"])
        self.assertEqual("IN_PROGRESS", wave["completion"]["status"])

    def test_wave_checkpoint_and_exit_review_are_distinct_from_gate_approval(self) -> None:
        context = self.workflow()
        data, capabilities, slices, tasks, _gates = context
        capabilities["CAP-00"]["campaign"] = None
        wave = data["waves"][0]
        wave["campaign"] = {
            "status": "ACTIVE",
            "scope": "wave",
            "owner": "alice",
            "profile": "LOC",
            "platform": "windows-x64",
            "branch": "codex/test",
            "base_sha": "a" * 40,
            "worktree": str(REPO),
            "lease": new_lease("alice", 8),
        }
        with patch("taskctl.persist"):
            command_wave_checkpoint(
                Namespace(
                    wave="W0",
                    agent="alice",
                    kind="risk-cluster",
                    evidence=["checkpoint.json"],
                    note="contract cluster closed",
                    file="unused",
                ),
                *context,
            )
        self.assertEqual("W0.CP01", wave["checkpoints"][0]["id"])
        self.assertEqual("ACTIVE", wave["campaign"]["status"])

        tasks["CAP-00.S01.T01"]["status"] = "DONE"
        slices["CAP-00.S01"]["status"] = "DONE"
        slices["CAP-00.S01"]["completion"].update(
            status="APPROVED",
            reviewer="agent:slice-reviewer",
            reviewed_at="2026-08-13T00:00:00+00:00",
            evidence=["slice.json"],
        )
        with patch("taskctl.persist"):
            command_wave_submit(
                Namespace(wave="W0", agent="alice", evidence=["wave.json"], note="full suite passed", file="unused"),
                *context,
            )
        self.assertEqual("REVIEW", wave["completion"]["status"])
        with self.assertRaisesRegex(SystemExit, "independent"), patch("taskctl.persist"):
            command_wave_review(
                Namespace(wave="W0", reviewer="alice", result="approved", note="", file="unused"), *context
            )
        with patch("taskctl.persist"):
            command_wave_review(
                Namespace(
                    wave="W0", reviewer="agent:wave-reviewer", result="approved", note="qualified", file="unused"
                ),
                *context,
            )
        self.assertEqual("APPROVED", wave["completion"]["status"])
        self.assertEqual("COMPLETE", wave["campaign"]["status"])

    def test_final_slice_review_closes_only_the_current_wave_increment(self) -> None:
        context = self.workflow()
        capability = context[1]["CAP-00"]
        current = context[2]["CAP-00.S01"]
        current.update(status="REVIEW")
        current["completion"]["status"] = "REVIEW"
        current["tasks"][0]["status"] = "DONE"
        future = copy.deepcopy(current)
        future.update(id="CAP-00.S02", title="Future packaging", wave="W1", status="DEFERRED", _position=1)
        future["completion"] = {"status": "PENDING", "reviewer": None, "reviewed_at": None, "evidence": []}
        future["tasks"] = []
        capability["slices"].append(future)
        context[2][future["id"]] = future

        with patch("taskctl.persist"):
            command_slice_review(
                Namespace(slice=current["id"], reviewer="agent:reviewer", result="approved", note="", file="unused"),
                *context,
            )

        self.assertEqual("APPROVED", current["completion"]["status"])
        self.assertEqual("PAUSED", capability["campaign"]["status"])
        self.assertEqual("wave-complete", capability["campaign"]["pause_category"])
        self.assertEqual("PENDING", future["completion"]["status"])

    def test_future_capability_slice_does_not_replace_the_current_global_gate(self) -> None:
        context = self.workflow()
        data, capabilities, slices, tasks, _ = context
        current = slices["CAP-00.S01"]
        current.update(status="DONE")
        current["completion"]["status"] = "APPROVED"
        tasks["CAP-00.S01.T01"]["status"] = "DONE"
        data["waves"][0]["completion"].update(
            status="APPROVED",
            reviewer="agent:wave-reviewer",
            reviewed_at="2026-08-13T00:00:00+00:00",
            evidence=["wave-report.json"],
        )
        future = copy.deepcopy(current)
        future.update(id="CAP-00.S02", title="Future packaging", wave="W4", status="DEFERRED")
        future["completion"] = {"status": "PENDING"}
        future_task = copy.deepcopy(tasks["CAP-00.S01.T01"])
        future_task.update(id="CAP-00.S02.T01", slice_id=future["id"], wave="W4", status="DEFERRED")
        future["tasks"] = [future_task]
        capabilities["CAP-00"]["slices"].append(future)
        slices[future["id"]] = future
        tasks[future_task["id"]] = future_task

        second = copy.deepcopy(capabilities["CAP-00"])
        second.update(id="CAP-02", alias="CAP-current-wave-work", campaign=None)
        second_slice = copy.deepcopy(current)
        second_slice.update(id="CAP-02.S01", title="Current wave work", wave="W1", status="READY")
        second_slice["completion"] = {"status": "PENDING"}
        second_task = copy.deepcopy(tasks["CAP-00.S01.T01"])
        second_task.update(
            id="CAP-02.S01.T01", capability_id="CAP-02", slice_id=second_slice["id"], wave="W1", status="READY"
        )
        second_slice["tasks"] = [second_task]
        second["slices"] = [second_slice]
        capabilities[second["id"]] = second
        slices[second_slice["id"]] = second_slice
        tasks[second_task["id"]] = second_task
        data["capabilities"].append(second)
        data["waves"] = [
            {"id": "W0", "activation_gate": None, "completion": {"status": "APPROVED"}},
            {"id": "W1", "activation_gate": "G0", "completion": {"status": "PENDING"}},
            {"id": "W4", "activation_gate": "G3", "completion": {"status": "PENDING"}},
        ]
        gates = {
            "G0": {"id": "G0", "after_wave": "W0", "status": "APPROVED", "unlocks_waves": ["W1"]},
            "G1": {"id": "G1", "after_wave": "W1", "status": "PENDING", "unlocks_waves": ["W2"]},
            "G3": {"id": "G3", "after_wave": "W3", "status": "PENDING", "unlocks_waves": ["W4"]},
            "G4": {"id": "G4", "after_wave": "W4", "status": "PENDING", "unlocks_waves": ["W5"]},
        }
        data["release_gates"] = list(gates.values())

        program = global_program_position(data, slices, tasks, gates)

        self.assertEqual("W1", program["current_wave"])
        self.assertEqual("G1", program["next_gate"]["id"])

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
        with self.assertRaisesRegex(SystemExit, "independent from the Wave campaign owner"), patch("taskctl.persist"):
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

    def test_validated_save_protects_approved_wave_amendment_inventory_and_append_only_history(self) -> None:
        data, *_ = load(str(REPO / "planning" / "backlog.yaml"))
        approval_snapshot = approved_wave_snapshot(data)
        approved_wave = next(wave for wave in data["waves"] if (wave.get("approval") or {}).get("status") == "APPROVED")
        approved_wave["approval"]["notes"] = "retroactive rewrite"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backlog.yaml"
            destination.write_text("sentinel: true\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "immutable APPROVED Wave approval changed"):
                save_validated(str(destination), data, expected_approved_waves=approval_snapshot)
            self.assertEqual("sentinel: true\n", destination.read_text(encoding="utf-8"))

        interrupted, *_ = self.interrupted_workflow()
        inventory_snapshot = amendment_identity_snapshot(interrupted)
        interrupted["wave_amendments"][0]["tasks"].append({"id": "W1.A02.T99"})
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backlog.yaml"
            destination.write_text("sentinel: true\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "task inventory changed outside the materialization transition"):
                save_validated(
                    str(destination),
                    interrupted,
                    expected_amendment_identity=inventory_snapshot,
                )
            self.assertEqual("sentinel: true\n", destination.read_text(encoding="utf-8"))

        interrupted, *_ = self.interrupted_workflow()
        history_snapshot = amendment_history_snapshot(interrupted)
        interrupted["wave_amendments"][0]["lifecycle"]["history"][0]["rationale"] = "rewritten history"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backlog.yaml"
            destination.write_text("sentinel: true\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "Append-only lifecycle history changed for W1.A02"):
                save_validated(
                    str(destination),
                    interrupted,
                    expected_amendment_history=history_snapshot,
                )
            self.assertEqual("sentinel: true\n", destination.read_text(encoding="utf-8"))

    def test_interrupted_wave_commands_print_a_decision_complete_amendment_handoff(self) -> None:
        args = Namespace(
            profile="LOC",
            platform="windows-x64",
            file=str(REPO / "planning" / "backlog.yaml"),
        )
        commands = [taskctl_module.command_status, command_next, taskctl_module.command_next_capability]
        for command in commands:
            with self.subTest(command=command.__name__):
                context = self.interrupted_workflow()
                output = io.StringIO()
                with redirect_stdout(output):
                    command(args, *context)
                rendered = output.getvalue()
                self.assertIn("STOPPED AT WAVE AMENDMENT W1.A02", rendered)
                self.assertIn("ECR-0001", rendered)
                self.assertIn("planning/review-site/enablers/ECR-0001.html", rendered)
                self.assertIn("planning/wave-amendment-approvals/W1.A02.json", rendered)
                self.assertIn("Decision alternatives", rendered)
                self.assertIn("Resume condition", rendered)
                self.assertNotIn("wave start W1", rendered)
                self.assertNotIn("wave approve W1", rendered)

    def test_interrupting_amendment_denies_ordinary_claim_resume_and_exit_gate(self) -> None:
        data, capabilities, slices, tasks, gates = self.interrupted_workflow()
        with (
            self.assertRaisesRegex(SystemExit, "Ordinary task claim denied while W1.A02 interrupts W1"),
            patch(
                "taskctl.git_execution_identity",
                return_value=("alice", "codex/test", "a" * 40, str(REPO)),
            ),
            patch("taskctl.persist"),
        ):
            command_claim(self.claim_args(), data, capabilities, slices, tasks, gates)

        data, capabilities, slices, tasks, gates = self.interrupted_workflow()
        resume_args = Namespace(
            wave="W1",
            agent="alice",
            branch="codex/test",
            base_sha="a" * 40,
            worktree=str(REPO),
            profile="LOC",
            platform="windows-x64",
            lease_hours=8,
            file=str(REPO / "planning" / "backlog.yaml"),
        )
        with self.assertRaisesRegex(
            SystemExit,
            "cannot resume until its interrupting amendment is adopted or disposed",
        ):
            command_wave_resume(resume_args, data, capabilities, slices, tasks, gates)

        data, capabilities, slices, tasks, gates = self.interrupted_workflow()
        ordinary = tasks["CAP-00.S01.T01"]
        ordinary.update(
            status="DONE",
            evidence=[{"type": "criterion-manifest"}],
            review={
                "reviewer": "agent:reviewer",
                "result": "approved",
                "reviewed_at": "2026-08-20T00:00:00+00:00",
                "notes": None,
            },
        )
        slices["CAP-00.S01"]["completion"].update(
            status="APPROVED",
            reviewer="agent:reviewer",
            reviewed_at="2026-08-20T00:00:00+00:00",
            evidence=["slice-review.json"],
        )
        data["waves"][0]["completion"].update(
            status="APPROVED",
            reviewer="agent:wave-reviewer",
            reviewed_at="2026-08-20T00:00:00+00:00",
            evidence=["wave-review.json"],
        )
        gate = {
            "id": "G1",
            "name": "W1 exit",
            "after_wave": "W1",
            "criteria": ["The interrupting amendment is adopted."],
            "status": "PENDING",
            "unlocks_waves": [],
            "approval": {"approved_by": None, "approved_at": None, "evidence": [], "notes": None},
        }
        data["release_gates"] = [gate]
        gates["G1"] = gate
        with self.assertRaisesRegex(SystemExit, "W1.A02 is unfinished"), patch("taskctl.persist"):
            command_gate_approve(
                Namespace(
                    gate="G1",
                    approver="agent:owner",
                    evidence=["gate-evidence.json"],
                    note="",
                    file="unused",
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

    def test_amendment_semantics_require_exact_bootstrap_history_and_exclusive_campaign(self) -> None:
        data, capabilities, slices, tasks, gates = self.interrupted_workflow(
            lifecycle_status="ACTIVE", amendment_campaign_status="ACTIVE"
        )
        amendment = data["wave_amendments"][0]
        amendment["bootstrap"]["id"] = "W1.A02.B99"
        amendment["lifecycle"]["history"][0]["id"] = "E02"
        capabilities["CAP-00"]["campaign"].update(
            status="ACTIVE",
            lease=new_lease("alice", 8),
        )

        errors = validate(data, capabilities, slices, tasks, gates)

        self.assertIn("W1.A02: interrupting amendment lacks its exact bootstrap identity", errors)
        self.assertIn("W1.A02: lifecycle event IDs are not sequential", errors)
        self.assertIn("A Wave amendment campaign cannot run beside an ACTIVE ordinary campaign", errors)

    def test_b00_r01_semantics_freeze_bootstrap_candidate_evidence_and_independent_review(self) -> None:
        data, capabilities, slices, tasks, gates = load(str(REPO / "planning" / "backlog.yaml"))
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        bootstrap = amendment["bootstrap"]
        bootstrap.update(
            status="APPROVED",
            implementation_commit="f" * 40,
            review={"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
        )
        bootstrap["evidence"][0]["sha256"] = "0" * 64
        with patch("taskctl.evidence_reference_errors", return_value=[]):
            errors = validate(data, capabilities, slices, tasks, gates, repo=REPO)
        joined = "\n".join(errors)
        self.assertIn("W1.A02.B00: bootstrap implementation commit is invalid", joined)
        self.assertIn("W1.A02.B00: bootstrap evidence hash mismatch", joined)
        self.assertIn("W1.A02.B00: APPROVED bootstrap lacks its complete independent review projection", joined)

        data, capabilities, slices, tasks, gates = load(str(REPO / "planning" / "backlog.yaml"))
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        bootstrap = amendment["bootstrap"]
        approval_commit = amendment["approval_reference"]["introduction_commit"]
        bootstrap.update(
            status="APPROVED",
            implementation_commit=approval_commit,
            review={
                "reviewer": bootstrap["implementer"],
                "result": "approved",
                "reviewed_at": "2026-08-21T00:00:00+00:00",
                "notes": "Self-review must not authorize execution.",
            },
        )
        evidence_path = REPO / bootstrap["evidence"][0]["path"]
        manifest = json.loads(evidence_path.read_text(encoding="utf-8"))
        manifest["baseCommit"] = "0" * 40
        manifest["branch"] = "codex/unapproved-branch"
        manifest["changedFiles"].append("product/outside-approved-bootstrap-scope.py")
        altered_payload = json.dumps(manifest, sort_keys=True).encode("utf-8")
        bootstrap["evidence"][0]["sha256"] = evidence_sha256(altered_payload)
        original_read_bytes = Path.read_bytes

        def altered_manifest_bytes(path: Path) -> bytes:
            if path.resolve() == evidence_path.resolve():
                return altered_payload
            return original_read_bytes(path)

        original_run = subprocess.run

        def altered_scope(command: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
            if command[:3] == ["git", "diff", "--name-only"] and command[3:5] == [
                approval_commit,
                approval_commit,
            ]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "product/outside-approved-bootstrap-scope.py\n",
                    "",
                )
            return original_run(command, *args, **kwargs)

        with (
            patch.object(Path, "read_bytes", altered_manifest_bytes),
            patch("taskctl.subprocess.run", side_effect=altered_scope),
            patch("taskctl.evidence_reference_errors", return_value=[]),
        ):
            errors = validate(data, capabilities, slices, tasks, gates, repo=REPO)
        joined = "\n".join(errors)
        self.assertIn("W1.A02.B00: bootstrap candidate does not strictly descend from its prior candidate", joined)
        self.assertIn("W1.A02.B00: bootstrap evidence base does not match the frozen review boundary", joined)
        self.assertIn("W1.A02.B00: bootstrap evidence branch does not match the current codex branch", joined)
        self.assertIn("W1.A02.B00: bootstrap changed path is outside approved scope", joined)
        self.assertIn("W1.A02.B00: bootstrap reviewer is not independent from the implementer", joined)

    def test_b00_r01_review_and_materialization_revalidate_the_frozen_bootstrap(self) -> None:
        data, capabilities, slices, tasks, gates = load(str(REPO / "planning" / "backlog.yaml"))
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        amendment["bootstrap"]["status"] = "REVIEW"
        amendment["bootstrap"]["review"] = {
            "reviewer": None,
            "result": None,
            "reviewed_at": None,
            "notes": None,
        }
        amendment["bootstrap"]["evidence"][0]["sha256"] = "0" * 64
        approval = json.loads((REPO / "planning/wave-amendment-approvals/W1.A02.json").read_text(encoding="utf-8"))
        packet = json.loads(
            (REPO / "planning/enabler-change-requests/ECR-0001.packet.json").read_text(encoding="utf-8")
        )
        with (
            self.assertRaisesRegex(SystemExit, "bootstrap evidence hash mismatch"),
            patch("taskctl.discover_repository", return_value=REPO),
            patch("taskctl.require_clean_repository"),
            patch("taskctl.load_amendment_authority", return_value=(approval, packet, b"approval")),
            patch("taskctl.persist"),
        ):
            taskctl_module.command_amendment_bootstrap_review(
                Namespace(
                    amendment="W1.A02",
                    reviewer="new-independent-reviewer",
                    result="approved",
                    note="must revalidate",
                    file=str(REPO / "planning/backlog.yaml"),
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

        data, capabilities, slices, tasks, gates = load(str(REPO / "planning" / "backlog.yaml"))
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        amendment["bootstrap"]["status"] = "APPROVED"
        amendment["bootstrap"]["review"] = {
            "reviewer": None,
            "result": None,
            "reviewed_at": None,
            "notes": None,
        }
        approval = json.loads((REPO / "planning/wave-amendment-approvals/W1.A02.json").read_text(encoding="utf-8"))
        packet = json.loads(
            (REPO / "planning/enabler-change-requests/ECR-0001.packet.json").read_text(encoding="utf-8")
        )
        with (
            self.assertRaisesRegex(
                SystemExit,
                "APPROVED bootstrap lacks its complete independent review projection",
            ),
            patch("taskctl.discover_repository", return_value=REPO),
            patch("taskctl.require_clean_repository"),
            patch("taskctl.load_amendment_authority", return_value=(approval, packet, b"approval")),
            patch("taskctl.save_validated"),
        ):
            taskctl_module.command_amendment_materialize(
                Namespace(amendment="W1.A02", agent="codex", file=str(REPO / "planning/backlog.yaml")),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

    def test_b00_r01_bootstrap_resubmit_is_append_only_and_strictly_descendant(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(
            [
                "amendment",
                "bootstrap-resubmit",
                "W1.A02",
                "--agent",
                "codex",
                "--implementation-commit",
                "d" * 40,
                "--evidence",
                "artifacts/evidence/W1.A02.B00.remediation.json",
            ]
        )
        self.assertEqual("bootstrap-resubmit", parsed.amendment_command)

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "artifacts/evidence").mkdir(parents=True)
            evidence_path = repo / "artifacts/evidence/W1.A02.B00.remediation.json"
            evidence_path.write_text(json.dumps({"commit": "d" * 40}), encoding="utf-8")
            data, capabilities, slices, tasks, gates = load(str(REPO / "planning" / "backlog.yaml"))
            amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
            bootstrap = amendment["bootstrap"]
            prior_projection = copy.deepcopy(
                {key: bootstrap[key] for key in ("implementer", "implementation_commit", "evidence", "review")}
            )
            approval = json.loads((REPO / "planning/wave-amendment-approvals/W1.A02.json").read_text(encoding="utf-8"))
            packet = json.loads(
                (REPO / "planning/enabler-change-requests/ECR-0001.packet.json").read_text(encoding="utf-8")
            )

            def git_result(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(command, 0, "d" * 40 + "\n", "")
                if command[:3] == ["git", "diff", "--name-only"]:
                    return subprocess.CompletedProcess(command, 0, "tests/foundation/test_taskctl_workflow.py\n", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            args = Namespace(
                amendment="W1.A02",
                agent="codex",
                implementation_commit="d" * 40,
                evidence=str(evidence_path),
                file=str(repo / "planning/backlog.yaml"),
            )
            with (
                patch("taskctl.discover_repository", return_value=repo),
                patch("taskctl.load_amendment_authority", return_value=(approval, packet, b"approval")),
                patch("taskctl.require_clean_repository"),
                patch("taskctl.git_commit_exists", return_value=True),
                patch("taskctl.git_is_ancestor", return_value=True),
                patch("taskctl.require_amendment_packet_integrity"),
                patch("taskctl.bootstrap_attempt_errors", return_value=[]),
                patch("taskctl.subprocess.run", side_effect=git_result),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_bootstrap_resubmit(
                    args,
                    data,
                    capabilities,
                    slices,
                    tasks,
                    gates,
                )

            self.assertEqual("REVIEW", bootstrap["status"])
            self.assertEqual("d" * 40, bootstrap["implementation_commit"])
            self.assertEqual(
                {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
                bootstrap["review"],
            )
            self.assertEqual(1, len(bootstrap["attempts"]))
            self.assertEqual("R01", bootstrap["attempts"][0]["id"])
            for key, value in prior_projection.items():
                self.assertEqual(value, bootstrap["attempts"][0][key])
            self.assertEqual(evidence_sha256(evidence_path.read_bytes()), bootstrap["evidence"][0]["sha256"])
            self.assertNotEqual(prior_projection["evidence"], bootstrap["evidence"])

            bootstrap.update(
                status="CHANGES_REQUESTED",
                implementation_commit=prior_projection["implementation_commit"],
                evidence=copy.deepcopy(prior_projection["evidence"]),
                review=copy.deepcopy(prior_projection["review"]),
                attempts=[],
            )
            args.implementation_commit = prior_projection["implementation_commit"]
            with (
                self.assertRaisesRegex(SystemExit, "strict descendant of the prior candidate"),
                patch("taskctl.discover_repository", return_value=repo),
                patch("taskctl.load_amendment_authority", return_value=(approval, packet, b"approval")),
                patch("taskctl.require_amendment_packet_integrity"),
                patch("taskctl.git_is_ancestor", return_value=False),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_bootstrap_resubmit(
                    args,
                    data,
                    capabilities,
                    slices,
                    tasks,
                    gates,
                )

    def test_b00_r02_validate_denies_any_materialized_task_packet_drift(self) -> None:
        context, _packet = self.packet_bound_active_amendment_workflow()
        data, capabilities, slices, tasks, gates = context
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        first, second = amendment["tasks"]
        first["title"] = "Altered title"
        first["objective"] = "Altered objective"
        first["dependencies"] = []
        first["acceptance_criteria"] = ["Altered criterion"]
        first["verification_commands"] = ["altered command"]
        first["packet_task_sha256"] = "0" * 64
        amendment["tasks"] = [second, first]
        data, capabilities, slices, tasks, gates = taskctl_module.index_backlog(data)

        with patch("taskctl.evidence_reference_errors", return_value=[]):
            errors = validate(data, capabilities, slices, tasks, gates, repo=REPO)
        joined = "\n".join(errors)
        self.assertIn("W1.A02.T02: amendment task identity/order mismatch", joined)
        for field in (
            "title",
            "objective",
            "dependencies",
            "acceptance_criteria",
            "verification_commands",
            "packet_task_sha256",
        ):
            self.assertIn(f"immutable amendment task field {field} differs from the approved packet", joined)

    def test_b00_r02_command_entry_points_deny_materialized_task_packet_drift(self) -> None:
        def drifted_context() -> tuple[dict, dict, dict, dict, dict]:
            context, _packet = self.packet_bound_active_amendment_workflow()
            context[3]["W1.A02.T01"]["objective"] = "Drifted after activation"
            return context

        data, capabilities, slices, tasks, gates = drifted_context()
        task = tasks["W1.A02.T01"]
        campaign = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")["campaign"]
        with (
            self.assertRaisesRegex(
                SystemExit,
                "immutable amendment task field objective differs from the approved packet",
            ),
            patch(
                "taskctl.git_execution_identity",
                return_value=("codex", campaign["branch"], campaign["base_sha"], str(REPO)),
            ),
            patch("taskctl.persist"),
        ):
            command_claim(
                self.claim_args(
                    task=task["id"],
                    agent="codex",
                    branch=campaign["branch"],
                    base_sha=campaign["base_sha"],
                    worktree=str(REPO),
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

        data, capabilities, slices, tasks, gates = drifted_context()
        task = tasks["W1.A02.T01"]
        task.update(
            status="IN_PROGRESS",
            owner="codex",
            branch=next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")["campaign"]["branch"],
            base_sha="a" * 40,
            worktree=str(REPO),
            lease=new_lease("codex", 8),
        )
        with (
            self.assertRaisesRegex(
                SystemExit,
                "immutable amendment task field objective differs from the approved packet",
            ),
            patch("taskctl.persist"),
        ):
            command_evidence(
                Namespace(
                    task=task["id"],
                    agent="codex",
                    from_file=str(REPO / "artifacts/evidence/does-not-exist.json"),
                    file=str(REPO / "planning/backlog.yaml"),
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

        data, capabilities, slices, tasks, gates = drifted_context()
        task = tasks["W1.A02.T01"]
        task.update(
            status="REVIEW",
            owner="codex",
            evidence=[{"type": "criterion-manifest"}],
            verification_state="passed",
            lease=new_lease("codex", 8),
        )
        with (
            self.assertRaisesRegex(
                SystemExit,
                "immutable amendment task field objective differs from the approved packet",
            ),
            patch("taskctl.persist"),
        ):
            command_review(
                Namespace(
                    task=task["id"],
                    reviewer="independent-reviewer",
                    result="approved",
                    lease_hours=8,
                    note="must deny drift",
                    file=str(REPO / "planning/backlog.yaml"),
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

        data, capabilities, slices, tasks, gates = drifted_context()
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        amendment["campaign"].update(status="COMPLETE", lease=None)
        amendment["completion"].update(
            status="APPROVED",
            reviewer="exit-reviewer",
            reviewed_at="2026-08-21T00:00:00+00:00",
            evidence=["exit.json"],
        )
        amendment["lifecycle"]["status"] = "REVIEW"
        amendment["lifecycle"]["history"][-1]["status"] = "REVIEW"
        data["control_plane"]["active_amendment"] = None
        for task in amendment["tasks"]:
            task.update(
                status="DONE",
                lease=None,
                evidence=[{"type": "criterion-manifest"}],
                review={
                    "reviewer": "task-reviewer",
                    "result": "approved",
                    "reviewed_at": "2026-08-21T00:00:00+00:00",
                    "notes": None,
                },
            )
        with (
            self.assertRaisesRegex(
                SystemExit,
                "immutable amendment task field objective differs from the approved packet",
            ),
            patch("taskctl.persist"),
        ):
            taskctl_module.command_amendment_adopt(
                Namespace(
                    amendment="W1.A02",
                    agent="codex",
                    evidence=["checkpoint.json"],
                    note="must deny drift",
                    file=str(REPO / "planning/backlog.yaml"),
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

    def test_b00_r03_finite_state_table_denies_cross_field_amendment_contradictions(self) -> None:
        cases: list[tuple[str, tuple[dict, dict, dict, dict, dict], str]] = []

        context = self.interrupted_workflow(lifecycle_status="APPROVED", amendment_campaign_status="ACTIVE")
        cases.append(
            (
                "active-campaign-approved-lifecycle",
                context,
                "unmaterialized APPROVED lifecycle cannot have tasks or a campaign",
            )
        )

        context = self.interrupted_workflow(lifecycle_status="ACTIVE", amendment_campaign_status="ACTIVE")
        context[0]["waves"][0]["campaign"]["scope"] = "wave"
        cases.append(
            (
                "ordinary-wave-scope",
                context,
                "executable lifecycle requires the paused amendment-hold Wave",
            )
        )

        for marker in (None, "W1.A01"):
            context = self.interrupted_workflow(lifecycle_status="ACTIVE", amendment_campaign_status="ACTIVE")
            context[0]["control_plane"]["active_amendment"] = marker
            cases.append(
                (
                    f"active-marker-{marker}",
                    context,
                    "control plane active_amendment does not exactly match the sole ACTIVE amendment campaign",
                )
            )

        context = self.interrupted_workflow(lifecycle_status="MATERIALIZED")
        context[0]["wave_amendments"][0]["bootstrap"]["status"] = "REVIEW"
        cases.append(
            (
                "executable-unapproved-bootstrap",
                context,
                "executable lifecycle requires an independently approved bootstrap",
            )
        )

        context = self.interrupted_workflow(lifecycle_status="MATERIALIZED")
        context[0]["wave_amendments"][0]["tasks"] = []
        context[3].pop("W1.A02.T01")
        context[3].pop("W1.A02.T02")
        cases.append(
            (
                "executable-missing-tasks",
                context,
                "executable lifecycle requires the exact materialized task inventory",
            )
        )

        context = self.interrupted_workflow(lifecycle_status="ADOPTED", amendment_campaign_status="ACTIVE")
        cases.append(("terminal-active-state", context, "terminal lifecycle retains active execution state"))

        for name, context, expected in cases:
            with self.subTest(case=name):
                errors = validate(*context)
                self.assertIn(expected, "\n".join(errors))

    def test_amendment_materialization_and_activation_use_the_exact_safe_inventory(self) -> None:
        data, capabilities, slices, tasks, gates = self.interrupted_workflow(lifecycle_status="APPROVED")
        amendment = data["wave_amendments"][0]
        amendment["tasks"] = []
        tasks.pop("W1.A02.T01")
        tasks.pop("W1.A02.T02")
        data["waves"][0]["campaign"]["scope"] = "wave"
        packet_tasks = [
            {
                "id": "W1.A02.T01",
                "title": "First approved enabler task",
                "objective": "Exercise exact materialization.",
                "dependencies": ["W1.A02.B00"],
                "acceptanceCriteria": ["Only approved work is executable."],
                "verification": ["python -m unittest first"],
            },
            {
                "id": "W1.A02.T02",
                "title": "Second approved enabler task",
                "objective": "Exercise ordered activation.",
                "dependencies": ["W1.A02.T01"],
                "acceptanceCriteria": ["Dependency order is preserved."],
                "verification": ["python -m unittest second"],
            },
        ]
        packet = {"taskInventory": packet_tasks}
        approval = {"authorizedTaskIds": ["W1.A02.T01", "W1.A02.T02"]}
        with (
            patch("taskctl.discover_repository", return_value=REPO),
            patch("taskctl.require_clean_repository"),
            patch("taskctl.load_amendment_authority", return_value=(approval, packet, b"approval")),
            patch("taskctl.require_amendment_packet_integrity"),
            patch("taskctl.save_validated") as save,
        ):
            taskctl_module.command_amendment_materialize(
                Namespace(amendment="W1.A02", agent="alice", file="unused"),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

        self.assertEqual(["W1.A02.T01", "W1.A02.T02"], [task["id"] for task in amendment["tasks"]])
        self.assertEqual(
            [taskctl_module.canonical_json_sha256(item) for item in packet_tasks],
            [task["packet_task_sha256"] for task in amendment["tasks"]],
        )
        self.assertEqual("MATERIALIZED", amendment["lifecycle"]["status"])
        self.assertEqual("amendment-hold", data["waves"][0]["campaign"]["scope"])
        self.assertNotIn("expected_amendment_identity", save.call_args.kwargs)

        activate_args = Namespace(
            amendment="W1.A02",
            agent="alice",
            branch="codex/test",
            base_sha="a" * 40,
            worktree=str(REPO),
            profile="LOC",
            platform="windows-x64",
            lease_hours=8,
            file="unused",
        )
        with (
            patch(
                "taskctl.git_execution_identity",
                return_value=("alice", "codex/test", "a" * 40, str(REPO)),
            ),
            patch("taskctl.discover_repository", return_value=REPO),
            patch("taskctl.require_clean_repository"),
            patch("taskctl.load_amendment_authority", return_value=(approval, packet, b"approval")),
            patch("taskctl.require_amendment_packet_integrity"),
            patch("taskctl.persist"),
        ):
            taskctl_module.command_amendment_activate(
                activate_args,
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

        self.assertEqual("ACTIVE", amendment["lifecycle"]["status"])
        self.assertEqual("ACTIVE", amendment["campaign"]["status"])
        self.assertEqual("W1.A02", data["control_plane"]["active_amendment"])
        self.assertEqual("READY", amendment["tasks"][0]["status"])
        self.assertEqual("NOT_STARTED", amendment["tasks"][1]["status"])

    def test_amendment_adoption_records_security_checkpoint_and_keeps_wave_paused(self) -> None:
        data, capabilities, slices, tasks, gates = self.interrupted_workflow(lifecycle_status="REVIEW")
        amendment = data["wave_amendments"][0]
        amendment["campaign"] = {
            "status": "COMPLETE",
            "scope": "wave-amendment",
            "owner": "alice",
            "branch": "codex/test",
            "worktree": str(REPO),
            "base_sha": "a" * 40,
            "profile": "LOC",
            "platform": "windows-x64",
            "started_at": "2026-08-20T00:00:00+00:00",
            "updated_at": "2026-08-20T00:00:00+00:00",
            "pause_reason": None,
            "lease": None,
        }
        amendment["completion"].update(
            status="APPROVED",
            reviewer="agent:exit-reviewer",
            reviewed_at="2026-08-20T00:00:00+00:00",
            evidence=["exit-review.json"],
        )
        for task in amendment["tasks"]:
            task.update(
                status="DONE",
                completed_at="2026-08-20T00:00:00+00:00",
                evidence=[{"type": "criterion-manifest"}],
                verification_state="passed",
                review={
                    "reviewer": "agent:task-reviewer",
                    "result": "approved",
                    "reviewed_at": "2026-08-20T00:00:00+00:00",
                    "notes": None,
                },
            )
        data["control_plane"]["active_amendment"] = None

        with patch("taskctl.require_runtime_amendment_integrity"), patch("taskctl.persist"):
            taskctl_module.command_amendment_adopt(
                Namespace(
                    amendment="W1.A02",
                    agent="alice",
                    evidence=["control-security-checkpoint.json"],
                    note="Control repair adopted.",
                    file="unused",
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

        wave = data["waves"][0]
        self.assertEqual("PAUSED", wave["campaign"]["status"])
        self.assertEqual("wave", wave["campaign"]["scope"])
        self.assertEqual("security", wave["checkpoints"][-1]["kind"])
        self.assertEqual(["control-security-checkpoint.json"], wave["checkpoints"][-1]["evidence"])
        self.assertEqual("ADOPTED", amendment["lifecycle"]["status"])
        self.assertIsNone(data["control_plane"]["active_amendment"])

    def test_amendment_disposition_is_append_only_independent_and_keeps_wave_paused(self) -> None:
        data, capabilities, slices, tasks, gates = self.interrupted_workflow(
            lifecycle_status="PAUSED", amendment_campaign_status="PAUSED"
        )
        amendment = data["wave_amendments"][0]
        with patch("taskctl.persist"):
            command_amendment_dispose(
                Namespace(
                    amendment="W1.A02",
                    reviewer="independent-reviewer",
                    result="deferred",
                    safe_resume_condition="The original Wave controls remain sufficient.",
                    evidence=["control-disposition.json"],
                    note="Deferred without executing the task delta.",
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

        self.assertEqual("DEFERRED", amendment["lifecycle"]["status"])
        self.assertEqual("DEFERRED", amendment["tasks"][0]["status"])
        self.assertEqual("wave", data["waves"][0]["campaign"]["scope"])
        self.assertEqual("security", data["waves"][0]["checkpoints"][-1]["kind"])
        self.assertIsNone(data["control_plane"]["active_amendment"])
        with self.assertRaisesRegex(SystemExit, "terminal amendment disposition"):
            command_amendment_dispose(
                Namespace(
                    amendment="W1.A02",
                    reviewer="another-reviewer",
                    result="withdrawn",
                    safe_resume_condition="Still safe.",
                    evidence=["second.json"],
                    note="duplicate",
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

    def test_bootstrap_scope_addendum_is_hash_bound_and_history_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            approval_dir = repo / "planning/wave-amendment-approvals"
            approval_dir.mkdir(parents=True)
            schema_source = REPO / "planning/wave-amendment-approvals/bootstrap-scope-addendum.schema.json"
            record_source = REPO / "planning/wave-amendment-approvals/W1.A02.B00.addendum-01.json"
            schema_path = approval_dir / schema_source.name
            record_path = approval_dir / record_source.name
            schema_path.write_bytes(schema_source.read_bytes())
            payload = record_source.read_bytes()
            record_path.write_bytes(payload)
            reference = {
                "path": "planning/wave-amendment-approvals/W1.A02.B00.addendum-01.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "introduction_commit": "c" * 40,
            }
            with (
                patch("taskctl.approval_introduction_commit", return_value="c" * 40),
                patch("taskctl.git_blob", return_value=payload),
                patch("taskctl.git_commit_exists", return_value=True),
                patch("taskctl.git_is_ancestor", return_value=True),
            ):
                self.assertEqual(
                    [],
                    bootstrap_scope_addendum_errors(repo, reference, "W1.A02", "W1.A02.B00"),
                )
                reference["sha256"] = "0" * 64
                self.assertIn(
                    "W1.A02.B00: bootstrap scope-addendum hash mismatch",
                    bootstrap_scope_addendum_errors(repo, reference, "W1.A02", "W1.A02.B00"),
                )

    def test_parser_exposes_only_the_approved_amendment_lifecycle_commands(self) -> None:
        parser = build_parser()
        commands = [
            ["amendment", "status", "W1.A02"],
            [
                "amendment",
                "bootstrap-submit",
                "W1.A02",
                "--agent",
                "alice",
                "--approval-commit",
                "a" * 40,
                "--implementation-commit",
                "b" * 40,
                "--evidence",
                "bootstrap-evidence.json",
            ],
            [
                "amendment",
                "bootstrap-review",
                "W1.A02",
                "--reviewer",
                "reviewer",
                "--result",
                "approved",
                "--note",
                "reviewed",
            ],
            ["amendment", "materialize", "W1.A02", "--agent", "alice"],
            [
                "amendment",
                "activate",
                "W1.A02",
                "--agent",
                "alice",
                "--branch",
                "codex/test",
                "--base-sha",
                "a" * 40,
                "--worktree",
                str(REPO),
                "--profile",
                "LOC",
                "--platform",
                "windows-x64",
                "--lease-hours",
                "8",
            ],
            ["amendment", "pause", "W1.A02", "--agent", "alice", "--reason", "bounded stop"],
            [
                "amendment",
                "submit",
                "W1.A02",
                "--agent",
                "alice",
                "--evidence",
                "exit.json",
                "--note",
                "ready",
            ],
            [
                "amendment",
                "review",
                "W1.A02",
                "--reviewer",
                "reviewer",
                "--result",
                "approved",
                "--note",
                "approved",
            ],
            [
                "amendment",
                "adopt",
                "W1.A02",
                "--agent",
                "alice",
                "--evidence",
                "checkpoint.json",
                "--note",
                "adopted",
            ],
            [
                "amendment",
                "dispose",
                "W1.A02",
                "--reviewer",
                "reviewer",
                "--result",
                "deferred",
                "--safe-resume-condition",
                "The base Wave remains safe.",
                "--evidence",
                "disposition.json",
                "--note",
                "deferred",
            ],
        ]
        for command in commands:
            with self.subTest(command=command[1]):
                parsed = parser.parse_args(command)
                self.assertEqual("amendment", parsed.command)
                self.assertEqual(command[1], parsed.amendment_command)

        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            parser.parse_args(["amendment", "activate", "W1.A02", "--override-safe-boundary"])

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
