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
from contextlib import chdir, redirect_stderr, redirect_stdout
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
    canonical_json_sha256,
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
    wave_resume_history_snapshot,
    wave_resume_record_errors,
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
        data["wave_amendments"] = [
            amendment for amendment in data["wave_amendments"] if amendment["id"] in {"W1.A01", "W1.A02"}
        ]
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

    def b00_initial_review_bootstrap_fixture(self) -> dict[str, Any]:
        return {
            "id": "W1.A02.B00",
            "status": "REVIEW",
            "implementer": "codex",
            "implementation_commit": "2493dee313a2df8929dbd2eed31d9e0e672fc368",
            "submission_branch": "codex/w1-windows-local-runtime",
            "scope_addenda": [
                {
                    "path": "planning/wave-amendment-approvals/W1.A02.B00.addendum-01.json",
                    "sha256": "c00c7574cf6def6db76754531d351cc0eb13853076f4d714074a611238a1a19d",
                    "introduction_commit": "502908c16d9751af56c720df0cdabd74c235721a",
                }
            ],
            "evidence": [
                {
                    "type": "criterion-manifest",
                    "path": "artifacts/evidence/W1.A02.B00.json",
                    "sha256": "74c93ae166d7e7a3ff41a194c38d207f8593abe7aefd108a879444f5aadb2370",
                    "commit": "2493dee313a2df8929dbd2eed31d9e0e672fc368",
                    "recorded_at": "2026-08-20T23:38:52+00:00",
                }
            ],
            "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
        }

    def b00_resubmission_source_bootstrap_fixture(self) -> dict[str, Any]:
        bootstrap = self.b00_initial_review_bootstrap_fixture()
        bootstrap.update(
            status="CHANGES_REQUESTED",
            review={
                "reviewer": "b00-independent-reviewer",
                "result": "changes-requested",
                "reviewed_at": "2026-08-20T23:49:47+00:00",
                "notes": "B00-R01, B00-R02, and B00-R03 require bounded remediation.",
            },
        )
        return bootstrap

    def b00_resubmitted_review_bootstrap_fixture(self) -> dict[str, Any]:
        prior = self.b00_resubmission_source_bootstrap_fixture()
        return {
            "id": "W1.A02.B00",
            "status": "REVIEW",
            "implementer": "codex",
            "implementation_commit": "badf4c0ec7ff1f5e121806b9fc3f9d87b0edf43c",
            "submission_branch": "codex/w1-windows-local-runtime",
            "scope_addenda": copy.deepcopy(prior["scope_addenda"]),
            "evidence": [
                {
                    "type": "criterion-manifest",
                    "path": "artifacts/evidence/W1.A02.B00.remediation-01.json",
                    "sha256": "b06a2c258b933dab4ad87e2b0f223b3f1a6e2cefb3d4478e59b864edfb4e53ff",
                    "commit": "badf4c0ec7ff1f5e121806b9fc3f9d87b0edf43c",
                    "recorded_at": "2026-08-21T00:07:19+00:00",
                }
            ],
            "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
            "attempts": [
                {
                    "id": "R01",
                    "implementer": prior["implementer"],
                    "implementation_commit": prior["implementation_commit"],
                    "submission_branch": prior["submission_branch"],
                    "evidence": copy.deepcopy(prior["evidence"]),
                    "review": copy.deepcopy(prior["review"]),
                }
            ],
        }

    def canonical_workflow_with_b00_bootstrap(
        self,
        bootstrap: dict[str, Any],
    ) -> tuple[dict, dict, dict, dict, dict]:
        context = load(str(REPO / "planning" / "backlog.yaml"))
        context[0]["wave_amendments"] = [
            amendment for amendment in context[0]["wave_amendments"] if amendment["id"] in {"W1.A01", "W1.A02"}
        ]
        amendment = next(item for item in context[0]["wave_amendments"] if item["id"] == "W1.A02")
        amendment["bootstrap"] = copy.deepcopy(bootstrap)
        amendment["lifecycle"] = {
            "status": "APPROVED",
            "history": [copy.deepcopy(amendment["lifecycle"]["history"][0])],
        }
        amendment["campaign"] = None
        amendment["tasks"] = []
        amendment["completion"] = {
            "status": "PENDING",
            "reviewer": None,
            "reviewed_at": None,
            "evidence": [],
            "notes": None,
        }
        context[0]["control_plane"]["active_amendment"] = None
        context[0]["control_plane"]["recovery_holds"] = []
        wave = next(item for item in context[0]["waves"] if item["id"] == "W1")
        wave["campaign"]["status"] = "PAUSED"
        wave["campaign"]["scope"] = "wave"
        return taskctl_module.index_backlog(context[0])

    def controlled_task_repository(
        self,
        root: Path,
    ) -> tuple[tuple[dict, dict, dict, dict, dict], Path, dict[str, Any], str, str]:
        repo = root / "repo"
        (repo / "planning").mkdir(parents=True)
        (repo / "artifacts" / "evidence").mkdir(parents=True)
        (repo / "planning" / "backlog.yaml").write_text("fixture: true\n", encoding="utf-8")
        (repo / "verification-profiles.json").write_text(
            json.dumps(
                {
                    "commands": {
                        "foundation:unit": {
                            "argv": ["python", "-m", "unittest", "focused"],
                        },
                        "foundation:backlog": {
                            "argv": ["python", "tools/taskctl.py", "validate"],
                        },
                    }
                }
            ),
            encoding="utf-8",
            newline="\n",
        )
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

        context = self.workflow()
        data, capabilities, _slices, tasks, _gates = context
        data["control_plane"] = {"revision": 3, "minimum_tool_revision": 3, "active_amendment": None}
        task = tasks["CAP-00.S01.T01"]
        task.update(
            status="IN_PROGRESS",
            owner="alice",
            branch="test-branch",
            base_sha=base,
            worktree=repo.as_posix(),
            lease=new_lease("alice", 8),
            evidence=[],
            verification_state=None,
        )
        capabilities["CAP-00"]["campaign"].update(
            branch="test-branch",
            base_sha=base,
            worktree=repo.as_posix(),
        )
        return context, repo, task, base, head

    def commit_all(self, repo: Path, message: str) -> str:
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repo, capture_output=True, check=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

    def amendment_exit_repository(
        self,
        root: Path,
    ) -> tuple[tuple[dict, dict, dict, dict, dict], Path, dict[str, Any], dict[str, Any], str, str]:
        repo = root / "repo"
        (repo / "planning").mkdir(parents=True)
        evidence_dir = repo / "artifacts" / "evidence"
        evidence_dir.mkdir(parents=True)
        (repo / "planning" / "backlog.yaml").write_text("{}\n", encoding="utf-8")
        (repo / "implementation.txt").write_text("bounded amendment implementation\n", encoding="utf-8")
        subprocess.run(
            ["git", "init", "-b", "codex/amendment-exit"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Taskctl Test"], cwd=repo, check=True)
        implementation_commit = self.commit_all(repo, "implementation")

        context = self.interrupted_workflow(lifecycle_status="REVIEW")
        data, _capabilities, _slices, _tasks, _gates = context
        amendment = data["wave_amendments"][0]
        amendment["campaign"] = {
            "status": "REVIEW",
            "scope": "wave-amendment",
            "owner": "alice",
            "branch": "codex/amendment-exit",
            "worktree": repo.as_posix(),
            "base_sha": implementation_commit,
            "profile": "LOC",
            "platform": "windows-x64",
            "started_at": "2026-08-21T01:00:00+00:00",
            "updated_at": "2026-08-21T02:00:00+00:00",
            "pause_reason": None,
            "lease": None,
        }
        for task in amendment["tasks"]:
            task.update(
                status="DONE",
                completed_at="2026-08-21T01:30:00+00:00",
                evidence=[{"type": "criterion-manifest"}],
                verification_state="passed",
                review={
                    "reviewer": "agent:task-reviewer",
                    "result": "approved",
                    "reviewed_at": "2026-08-21T01:45:00+00:00",
                    "notes": None,
                },
            )
        amendment["completion"].update(
            status="REVIEW",
            reviewer=None,
            reviewed_at=None,
            evidence=["artifacts/evidence/W1.A02.exit-R01.json"],
            notes="Legacy exit submission awaiting independent review.",
        )
        amendment["lifecycle"]["history"].append(
            {
                "id": "E02",
                "status": "REVIEW",
                "actor": "alice",
                "at": "2026-08-21T02:00:00+00:00",
                "rationale": "Submitted the legacy exit projection for review.",
            }
        )
        data["control_plane"]["active_amendment"] = None
        wave = data["waves"][0]
        wave["campaign"].update(
            status="PAUSED",
            scope="amendment-hold",
            pause_reason="Approved interrupting amendment",
        )
        exit_manifest = {
            "documentType": "wave-amendment-exit-evidence",
            "schemaVersion": "1.0",
            "amendmentId": "W1.A02",
            "changeRequestId": "ECR-0001",
            "targetWave": "W1",
            "candidateCommit": implementation_commit,
            "branch": "codex/amendment-exit",
            "waveCampaign": {
                "status": "PAUSED",
                "scope": "amendment-hold",
                "pauseReason": "Approved interrupting amendment",
            },
            "amendmentCampaign": {
                "status": "REVIEW",
                "scope": "wave-amendment",
                "pauseReason": None,
            },
            "requiredNextTransition": "independent amendment exit review",
            "checks": [
                {
                    "command": "python tools/taskctl.py validate",
                    "result": "passed",
                    "summary": "The bounded controller state validates.",
                }
            ],
        }
        exit_path = evidence_dir / "W1.A02.exit-R01.json"
        exit_path.write_text(json.dumps(exit_manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        (repo / "planning" / "backlog.yaml").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        reviewed_state = self.commit_all(repo, "legacy frozen exit review state")
        approved_packet = {"acceptanceCriteria": [f"Exit criterion {index}" for index in range(1, 7)]}
        return context, repo, amendment, approved_packet, implementation_commit, reviewed_state

    def write_amendment_exit_ledger(
        self,
        repo: Path,
        submission: dict[str, Any],
        *,
        attempt_id: str,
        reviewed_state_commit: str,
        result: str,
        findings: list[dict[str, Any]],
        closures: list[dict[str, Any]],
    ) -> Path:
        path = repo / "artifacts" / "evidence" / f"W1.A02.exit-review-{attempt_id}.json"
        reference = submission["evidence_reference"]
        ledger = {
            "amendment_id": "W1.A02",
            "attempt_id": attempt_id,
            "reviewed_state_commit": reviewed_state_commit,
            "reviewer": "agent:exit-reviewer",
            "result": result,
            "evidence": {"path": reference["path"], "sha256": reference["sha256"]},
            "notes": f"Immutable {attempt_id} exit disposition.",
            "findings": findings,
            "closures": closures,
        }
        path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8", newline="\n")
        return path

    def write_controlled_task_evidence(
        self,
        repo: Path,
        task: dict[str, Any],
        *,
        name: str,
        candidate: str,
        base: str,
        changed_paths: list[str],
        open_finding_ids: list[str] | None = None,
        root_cause_analysis: str | None = None,
        risk_analysis: str = "The changed controller path requires focused workflow validation.",
        check_command: str = "python -m unittest focused",
        selected_command_ids: list[str] | None = None,
        supersedes: str | None = None,
    ) -> Path:
        disposition: dict[str, Any] = {"openFindingIds": list(open_finding_ids or [])}
        if root_cause_analysis is not None:
            disposition["rootCauseAnalysis"] = root_cause_analysis
        manifest: dict[str, Any] = {
            "taskId": task["id"],
            "commit": candidate,
            "baseCommit": base,
            "branch": "test-branch",
            "changedFiles": changed_paths,
            "checks": [{"command": check_command, "exitCode": 0}],
            "acceptanceCriteria": [
                {"criterion_index": index, "evidence": [f"criterion {index} verified"]}
                for index, _criterion in enumerate(task["acceptance_criteria"], start=1)
            ],
            "unverifiedItems": [],
            "verificationSelection": {
                "riskAnalysis": risk_analysis,
                "deferred": ["complete Wave-exit profile"],
                "selectedCommandIds": list(
                    ["foundation:unit"] if selected_command_ids is None else selected_command_ids
                ),
            },
            "reviewerDisposition": disposition,
        }
        if supersedes is not None:
            prior_reference = next(
                reference for reference in task.get("evidence", []) if reference.get("path") == supersedes
            )
            manifest["supersedes"] = {
                "path": supersedes,
                "sha256": prior_reference["sha256"],
                "commit": prior_reference["commit"],
                "reason": "review remediation",
            }
        evidence = repo / "artifacts" / "evidence" / name
        evidence.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
        return evidence

    def review_finding(
        self,
        finding_id: str,
        *,
        severity: str = "high",
        blocking: bool = True,
    ) -> dict[str, Any]:
        return {
            "id": finding_id,
            "severity": severity,
            "blocking": blocking,
            "criterion_index": 1,
            "title": f"Finding {finding_id}",
            "reproduction": "Run the deterministic review-control fixture.",
            "required_remediation": "Correct the bounded review-control behavior.",
        }

    def write_task_review_ledger(
        self,
        repo: Path,
        task: dict[str, Any],
        *,
        name: str,
        reviewer: str,
        result: str,
        findings: list[dict[str, Any]],
        closures: list[dict[str, Any]] | None = None,
        notes: str = "consolidated review",
    ) -> Path:
        submission = task["review_control"]["current_submission"]
        ledger = {
            "task_id": task["id"],
            "attempt_id": submission["id"],
            "candidate_commit": submission["candidate_commit"],
            "reviewer": reviewer,
            "result": result,
            "notes": notes,
            "findings": findings,
            "closures": list(closures or []),
        }
        path = repo / "artifacts" / "evidence" / name
        path.write_text(json.dumps(ledger), encoding="utf-8", newline="\n")
        return path

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

    def test_t01_atomic_submit_freezes_one_packet_with_one_persist(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["submit", "CAP-00.S01.T01", "--agent", "alice", "--from", "manifest.json"])
        self.assertEqual("manifest.json", parsed.from_file)

        with tempfile.TemporaryDirectory() as temporary:
            context, repo, task, base, head = self.controlled_task_repository(Path(temporary))
            evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-01.json",
                candidate=head,
                base=base,
                changed_paths=["implementation.txt"],
            )
            args = Namespace(
                task=task["id"],
                agent="alice",
                from_file=str(evidence),
                note="submit exact packet",
                file=str(repo / "planning" / "backlog.yaml"),
            )
            original_read_bytes = Path.read_bytes
            evidence_reads = 0

            def count_evidence_read(path: Path) -> bytes:
                nonlocal evidence_reads
                if path == evidence:
                    evidence_reads += 1
                return original_read_bytes(path)

            with patch("taskctl.persist") as persist, patch.object(Path, "read_bytes", count_evidence_read):
                command_submit(args, *context)

            self.assertEqual(1, evidence_reads)
            persist.assert_called_once()
            self.assertEqual("REVIEW", task["status"])
            self.assertEqual("passed", task["verification_state"])
            self.assertEqual(1, len(task["evidence"]))
            control = task["review_control"]
            self.assertEqual([], control["attempts"])
            packet = control["current_submission"]
            self.assertEqual("R01", packet["id"])
            self.assertEqual(head, packet["candidate_commit"])
            self.assertEqual(task["evidence"][0], packet["evidence_reference"])
            self.assertEqual(["implementation.txt"], packet["changed_paths"])
            self.assertEqual(["python -m unittest focused"], packet["selected_checks"])
            self.assertEqual(["complete Wave-exit profile"], packet["deferred_checks"])
            self.assertEqual(
                taskctl_module.canonical_json_sha256(task["acceptance_criteria"]),
                packet["acceptance_criteria_sha256"],
            )
            self.assertEqual(taskctl_module.task_submission_packet_sha256(packet), packet["packet_sha256"])

    def test_t01_atomic_submit_failure_never_writes_partial_backlog_state(self) -> None:
        failures: list[BaseException] = [
            SystemExit("Backlog changed after taskctl loaded it"),
            OSError("replace failed"),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as temporary:
                context, repo, task, base, head = self.controlled_task_repository(Path(temporary))
                evidence = self.write_controlled_task_evidence(
                    repo,
                    task,
                    name="round-01.json",
                    candidate=head,
                    base=base,
                    changed_paths=["implementation.txt"],
                )
                backlog = repo / "planning" / "backlog.yaml"
                before = backlog.read_bytes()
                args = Namespace(
                    task=task["id"],
                    agent="alice",
                    from_file=str(evidence),
                    note="atomic failure",
                    file=str(backlog),
                )
                with self.assertRaises(type(failure)), patch("taskctl.persist", side_effect=failure) as persist:
                    command_submit(args, *context)

                persist.assert_called_once()
                self.assertEqual(before, backlog.read_bytes())

    def test_t01_submission_packet_tamper_matrix_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, repo, task, base, head = self.controlled_task_repository(Path(temporary))
            evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-01.json",
                candidate=head,
                base=base,
                changed_paths=["implementation.txt"],
            )
            with patch("taskctl.persist"):
                command_submit(
                    Namespace(
                        task=task["id"],
                        agent="alice",
                        from_file=str(evidence),
                        note="",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )
            frozen = copy.deepcopy(task)
            cases: list[tuple[str, Any, str]] = [
                (
                    "candidate",
                    lambda packet: packet.update(candidate_commit="0" * 40),
                    "submission candidate differs from its evidence reference",
                ),
                (
                    "evidence",
                    lambda packet: packet["evidence_reference"].update(sha256="0" * 64),
                    "submission evidence reference is not attached",
                ),
                (
                    "criteria",
                    lambda packet: packet.update(acceptance_criteria_sha256="0" * 64),
                    "frozen acceptance criteria hash differs from the task",
                ),
                (
                    "changed-paths",
                    lambda packet: packet.update(changed_paths=["forged.py"]),
                    "frozen changed-path identity differs from its evidence manifest",
                ),
                (
                    "selected-checks",
                    lambda packet: packet.update(selected_checks=["forged check"]),
                    "frozen selected-check identity differs from its evidence manifest",
                ),
                (
                    "selection-hash",
                    lambda packet: packet.update(selection_sha256="0" * 64),
                    "frozen verification-selection hash differs from its evidence manifest",
                ),
                (
                    "packet-hash",
                    lambda packet: packet.update(packet_sha256="0" * 64),
                    "immutable task submission packet hash mismatch",
                ),
            ]
            for name, mutate, expected in cases:
                with self.subTest(case=name):
                    forged = copy.deepcopy(frozen)
                    mutate(forged["review_control"]["current_submission"])
                    errors = taskctl_module.task_review_control_errors(forged, repo)
                    self.assertTrue(any(expected in error for error in errors), errors)

    def test_t01_review_denies_self_review_unranked_and_duplicate_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, repo, task, base, head = self.controlled_task_repository(Path(temporary))
            evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-01.json",
                candidate=head,
                base=base,
                changed_paths=["implementation.txt"],
            )
            with patch("taskctl.persist"):
                command_submit(
                    Namespace(
                        task=task["id"],
                        agent="alice",
                        from_file=str(evidence),
                        note="",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )

            self_review = self.write_task_review_ledger(
                repo,
                task,
                name="self-review.json",
                reviewer="alice",
                result="changes-requested",
                findings=[self.review_finding("F01")],
            )
            with self.assertRaisesRegex(SystemExit, "independent from the task owner"), patch("taskctl.persist"):
                command_review(
                    Namespace(
                        task=task["id"],
                        reviewer="alice",
                        result="changes-requested",
                        from_file=str(self_review),
                        lease_hours=8,
                        note="",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )

            invalid_ledgers = [
                (
                    "unranked.json",
                    [self.review_finding("F01", severity="low"), self.review_finding("F02", severity="high")],
                    "descending severity order",
                ),
                (
                    "duplicate.json",
                    [self.review_finding("F01"), self.review_finding("F01")],
                    "globally unique",
                ),
            ]
            for name, findings, expected in invalid_ledgers:
                ledger = self.write_task_review_ledger(
                    repo,
                    task,
                    name=name,
                    reviewer="independent-reviewer",
                    result="changes-requested",
                    findings=findings,
                )
                with (
                    self.subTest(case=name),
                    self.assertRaisesRegex(SystemExit, expected),
                    patch("taskctl.persist"),
                ):
                    command_review(
                        Namespace(
                            task=task["id"],
                            reviewer="independent-reviewer",
                            result="changes-requested",
                            from_file=str(ledger),
                            lease_hours=8,
                            note="",
                            file=str(repo / "planning" / "backlog.yaml"),
                        ),
                        *context,
                    )

    def test_t01_remediation_replays_open_findings_and_closes_blockers_before_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, repo, task, base, first_head = self.controlled_task_repository(Path(temporary))
            first_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-01.json",
                candidate=first_head,
                base=base,
                changed_paths=["implementation.txt"],
            )
            with patch("taskctl.persist"):
                command_submit(
                    Namespace(
                        task=task["id"],
                        agent="alice",
                        from_file=str(first_evidence),
                        note="",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )
            first_ledger = self.write_task_review_ledger(
                repo,
                task,
                name="review-01.json",
                reviewer="independent-reviewer",
                result="changes-requested",
                findings=[self.review_finding("F01")],
            )
            with patch("taskctl.persist"):
                command_review(
                    Namespace(
                        task=task["id"],
                        reviewer="independent-reviewer",
                        result="changes-requested",
                        from_file=str(first_ledger),
                        lease_hours=8,
                        note="consolidated review",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )

            (repo / "remediation.txt").write_text("fixed\n", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "add",
                    "artifacts/evidence/round-01.json",
                    "artifacts/evidence/review-01.json",
                    "remediation.txt",
                ],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "commit", "-m", "remediate review"], cwd=repo, capture_output=True, check=True)
            second_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
            ).stdout.strip()
            changed = [
                "artifacts/evidence/round-01.json",
                "artifacts/evidence/review-01.json",
                "remediation.txt",
            ]
            remediation = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-02.json",
                candidate=second_head,
                base=base,
                changed_paths=changed,
                open_finding_ids=["F01"],
                supersedes="artifacts/evidence/round-01.json",
            )
            submit_args = Namespace(
                task=task["id"],
                agent="alice",
                from_file=str(remediation),
                note="",
                file=str(repo / "planning" / "backlog.yaml"),
            )
            with self.assertRaisesRegex(SystemExit, "baseCommit must equal"), patch("taskctl.persist"):
                command_submit(submit_args, *context)

            remediation = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-02.json",
                candidate=second_head,
                base=first_head,
                changed_paths=changed,
                open_finding_ids=[],
                supersedes="artifacts/evidence/round-01.json",
            )
            submit_args.from_file = str(remediation)
            with self.assertRaisesRegex(SystemExit, "exact open finding IDs"), patch("taskctl.persist"):
                command_submit(submit_args, *context)

            remediation = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-02.json",
                candidate=second_head,
                base=first_head,
                changed_paths=changed,
                open_finding_ids=["F01"],
                supersedes="artifacts/evidence/round-01.json",
            )
            submit_args.from_file = str(remediation)
            with patch("taskctl.persist"):
                command_submit(submit_args, *context)
            self.assertEqual("R02", task["review_control"]["current_submission"]["id"])
            self.assertEqual(["F01"], task["review_control"]["current_submission"]["open_finding_ids"])

            approval = self.write_task_review_ledger(
                repo,
                task,
                name="review-02.json",
                reviewer="second-independent-reviewer",
                result="approved",
                findings=[],
            )
            review_args = Namespace(
                task=task["id"],
                reviewer="second-independent-reviewer",
                result="approved",
                from_file=str(approval),
                lease_hours=8,
                note="consolidated review",
                file=str(repo / "planning" / "backlog.yaml"),
            )
            with self.assertRaisesRegex(SystemExit, "blocking finding remains open"), patch("taskctl.persist"):
                command_review(review_args, *context)

            approval = self.write_task_review_ledger(
                repo,
                task,
                name="review-02.json",
                reviewer="second-independent-reviewer",
                result="approved",
                findings=[],
                closures=[
                    {
                        "finding_id": "F01",
                        "disposition": "fixed",
                        "evidence": "artifacts/evidence/round-02.json",
                    }
                ],
            )
            review_args.from_file = str(approval)
            with patch("taskctl.persist"):
                command_review(review_args, *context)

            self.assertEqual("DONE", task["status"])
            attempts = task["review_control"]["attempts"]
            self.assertEqual(2, len(attempts))
            self.assertEqual("changes-requested", attempts[0]["review"]["result"])
            self.assertEqual("approved", attempts[1]["review"]["result"])
            self.assertEqual("F01", attempts[1]["closures"][0]["finding_id"])
            self.assertEqual(
                {
                    "prior_attempt_id": "R01",
                    "replayed_finding_ids": ["F01"],
                    "closed_finding_ids": ["F01"],
                },
                attempts[1]["telemetry"]["remediation"],
            )
            self.assertEqual(attempts[-1]["review"], task["review"])

    def test_t01_third_submission_requires_root_cause_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, repo, task, base, first_head = self.controlled_task_repository(Path(temporary))
            first_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-01.json",
                candidate=first_head,
                base=base,
                changed_paths=["implementation.txt"],
            )
            with patch("taskctl.persist"):
                command_submit(
                    Namespace(
                        task=task["id"],
                        agent="alice",
                        from_file=str(first_evidence),
                        note="",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )
            first_ledger = self.write_task_review_ledger(
                repo,
                task,
                name="review-01.json",
                reviewer="reviewer-1",
                result="changes-requested",
                findings=[self.review_finding("F01")],
            )
            with patch("taskctl.persist"):
                command_review(
                    Namespace(
                        task=task["id"],
                        reviewer="reviewer-1",
                        result="changes-requested",
                        from_file=str(first_ledger),
                        lease_hours=8,
                        note="consolidated review",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )

            (repo / "round-two-fix.txt").write_text("round two fix\n", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "add",
                    "artifacts/evidence/round-01.json",
                    "artifacts/evidence/review-01.json",
                    "round-two-fix.txt",
                ],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "commit", "-m", "round two fix"], cwd=repo, capture_output=True, check=True)
            second_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
            ).stdout.strip()
            second_changed = [
                "artifacts/evidence/round-01.json",
                "artifacts/evidence/review-01.json",
                "round-two-fix.txt",
            ]
            second_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-02.json",
                candidate=second_head,
                base=first_head,
                changed_paths=second_changed,
                open_finding_ids=["F01"],
                supersedes="artifacts/evidence/round-01.json",
            )
            with patch("taskctl.persist"):
                command_submit(
                    Namespace(
                        task=task["id"],
                        agent="alice",
                        from_file=str(second_evidence),
                        note="",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )
            second_ledger = self.write_task_review_ledger(
                repo,
                task,
                name="review-02.json",
                reviewer="reviewer-2",
                result="changes-requested",
                findings=[self.review_finding("F02")],
                closures=[
                    {
                        "finding_id": "F01",
                        "disposition": "fixed",
                        "evidence": "artifacts/evidence/round-02.json",
                    }
                ],
            )
            with patch("taskctl.persist"):
                command_review(
                    Namespace(
                        task=task["id"],
                        reviewer="reviewer-2",
                        result="changes-requested",
                        from_file=str(second_ledger),
                        lease_hours=8,
                        note="consolidated review",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )

            (repo / "root-cause-fix.txt").write_text("systemic fix\n", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "add",
                    "artifacts/evidence/round-02.json",
                    "artifacts/evidence/review-02.json",
                    "root-cause-fix.txt",
                ],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "commit", "-m", "root cause fix"], cwd=repo, capture_output=True, check=True)
            third_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
            ).stdout.strip()
            changed = [
                "artifacts/evidence/round-02.json",
                "artifacts/evidence/review-02.json",
                "root-cause-fix.txt",
            ]
            cumulative_changed = [*second_changed, *changed]
            expanded_risk = (
                "Expanded round-three risk analysis for open finding F02 covers its root cause, incremental paths, "
                "and the focused plus deferred verification boundary."
            )

            older_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-03.json",
                candidate=third_head,
                base=first_head,
                changed_paths=cumulative_changed,
                open_finding_ids=["F02"],
                root_cause_analysis="Two review rounds exposed a shared invariant gap.",
                risk_analysis=expanded_risk,
                supersedes="artifacts/evidence/round-01.json",
            )
            args = Namespace(
                task=task["id"],
                agent="alice",
                from_file=str(older_evidence),
                note="",
                file=str(repo / "planning" / "backlog.yaml"),
            )
            with (
                self.assertRaisesRegex(SystemExit, "immediately preceding submission's exact evidence reference"),
                patch("taskctl.persist"),
            ):
                command_submit(args, *context)

            cumulative_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-03.json",
                candidate=third_head,
                base=second_head,
                changed_paths=changed,
                open_finding_ids=["F02"],
                root_cause_analysis="Two review rounds exposed a shared invariant gap.",
                risk_analysis=expanded_risk,
                supersedes="artifacts/evidence/round-01.json",
            )
            args.from_file = str(cumulative_evidence)
            with (
                self.assertRaisesRegex(SystemExit, "immediately preceding submission's exact evidence reference"),
                patch("taskctl.persist"),
            ):
                command_submit(args, *context)

            older_base_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-03.json",
                candidate=third_head,
                base=first_head,
                changed_paths=cumulative_changed,
                open_finding_ids=["F02"],
                root_cause_analysis="Two review rounds exposed a shared invariant gap.",
                risk_analysis=expanded_risk,
                supersedes="artifacts/evidence/round-02.json",
            )
            args.from_file = str(older_base_evidence)
            with self.assertRaisesRegex(SystemExit, "baseCommit must equal"), patch("taskctl.persist"):
                command_submit(args, *context)

            third_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-03.json",
                candidate=third_head,
                base=second_head,
                changed_paths=changed,
                open_finding_ids=["F02"],
                risk_analysis=expanded_risk,
                supersedes="artifacts/evidence/round-02.json",
            )
            args.from_file = str(third_evidence)
            with self.assertRaisesRegex(SystemExit, "rootCauseAnalysis"), patch("taskctl.persist"):
                command_submit(args, *context)

            third_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-03.json",
                candidate=third_head,
                base=second_head,
                changed_paths=changed,
                open_finding_ids=["F02"],
                root_cause_analysis=(
                    "Two review rounds exposed a shared invariant gap; expand the remediation boundary."
                ),
                supersedes="artifacts/evidence/round-02.json",
            )
            args.from_file = str(third_evidence)
            with self.assertRaisesRegex(SystemExit, "riskAnalysis.*open finding"), patch("taskctl.persist"):
                command_submit(args, *context)

            third_evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="round-03.json",
                candidate=third_head,
                base=second_head,
                changed_paths=changed,
                open_finding_ids=["F02"],
                root_cause_analysis=(
                    "Two review rounds exposed a shared invariant gap; expand the remediation boundary."
                ),
                risk_analysis=expanded_risk,
                supersedes="artifacts/evidence/round-02.json",
            )
            args.from_file = str(third_evidence)
            with patch("taskctl.persist"):
                command_submit(args, *context)
            packet = task["review_control"]["current_submission"]
            self.assertEqual("R03", packet["id"])
            self.assertIn("F02", packet["selection_rationale"])
            self.assertIn("shared invariant gap", packet["root_cause_analysis"])

            forged = copy.deepcopy(task)
            forged_manifest = json.loads(third_evidence.read_text(encoding="utf-8"))
            first_reference = forged["review_control"]["attempts"][0]["submission"]["evidence_reference"]
            forged_manifest["supersedes"] = {
                "path": first_reference["path"],
                "sha256": first_reference["sha256"],
                "commit": first_reference["commit"],
                "reason": "attempt to rewrite lineage to R01",
            }
            third_evidence.write_text(json.dumps(forged_manifest), encoding="utf-8", newline="\n")
            forged_sha = evidence_sha256(third_evidence.read_bytes())
            forged_reference = forged["evidence"][-1]
            forged_reference["sha256"] = forged_sha
            forged_packet = forged["review_control"]["current_submission"]
            forged_packet["evidence_reference"]["sha256"] = forged_sha
            forged_packet["packet_sha256"] = taskctl_module.task_submission_packet_sha256(forged_packet)
            errors = taskctl_module.task_review_control_errors(forged, repo)
            self.assertTrue(
                any("does not supersede the immediately preceding submission" in error for error in errors),
                errors,
            )

    def test_t02_new_submissions_require_canonical_frozen_command_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, repo, task, base, head = self.controlled_task_repository(Path(temporary))
            evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="selection.json",
                candidate=head,
                base=base,
                changed_paths=["implementation.txt"],
                selected_command_ids=[],
            )
            args = Namespace(
                task=task["id"],
                agent="alice",
                from_file=str(evidence),
                note="",
                file=str(repo / "planning" / "backlog.yaml"),
            )
            with self.assertRaisesRegex(SystemExit, "non-empty.*selectedCommandIds"), patch("taskctl.persist"):
                command_submit(args, *context)

            evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="selection.json",
                candidate=head,
                base=base,
                changed_paths=["implementation.txt"],
                selected_command_ids=["private/path"],
            )
            args.from_file = str(evidence)
            with self.assertRaisesRegex(SystemExit, "privacy-safe command IDs"), patch("taskctl.persist"):
                command_submit(args, *context)

            evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="selection.json",
                candidate=head,
                base=base,
                changed_paths=["implementation.txt"],
                selected_command_ids=["unknown:command"],
            )
            args.from_file = str(evidence)
            with (
                self.assertRaisesRegex(SystemExit, "unknown canonical verification command IDs"),
                patch("taskctl.persist"),
            ):
                command_submit(args, *context)

            evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="selection.json",
                candidate=head,
                base=base,
                changed_paths=["implementation.txt"],
                selected_command_ids=["foundation:unit"],
            )
            args.from_file = str(evidence)
            with patch("taskctl.persist"):
                command_submit(args, *context)
            packet = task["review_control"]["current_submission"]
            self.assertEqual(["foundation:unit"], packet["selected_command_ids"])

            forged = copy.deepcopy(task)
            forged_packet = forged["review_control"]["current_submission"]
            forged_packet["selected_command_ids"] = ["unknown:command"]
            forged_packet["packet_sha256"] = taskctl_module.task_submission_packet_sha256(forged_packet)
            errors = taskctl_module.task_review_control_errors(forged, repo)
            self.assertTrue(any("command-ID selection differs" in error for error in errors), errors)
            self.assertTrue(any("unknown canonical verification command IDs" in error for error in errors), errors)

    def test_t02_review_telemetry_is_prospective_deterministic_and_privacy_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, repo, task, base, head = self.controlled_task_repository(Path(temporary))
            raw_command = "python focused.py --source C:/private/research-secret.txt --token prompt-secret"
            risk_canary = "prompt/source/research-data/chain-of-thought canary"
            evidence = self.write_controlled_task_evidence(
                repo,
                task,
                name="private-user-data-path.json",
                candidate=head,
                base=base,
                changed_paths=["implementation.txt"],
                risk_analysis=risk_canary,
                check_command=raw_command,
                selected_command_ids=["foundation:unit"],
            )
            submit_args = Namespace(
                task=task["id"],
                agent="alice",
                from_file=str(evidence),
                note="implementation note canary",
                file=str(repo / "planning" / "backlog.yaml"),
            )
            with patch("taskctl.utc_now", return_value="2026-08-21T02:00:00+00:00"), patch("taskctl.persist"):
                command_submit(submit_args, *context)

            self.assertEqual([], taskctl_module.task_review_telemetry_events(context[3]))
            with redirect_stdout(io.StringIO()) as pending_output:
                taskctl_module.command_review_telemetry(
                    Namespace(repo_root=repo),
                    *context,
                )
            self.assertEqual("[]", pending_output.getvalue().strip())

            critical = self.review_finding("F01", severity="critical")
            critical.update(
                title="source content canary",
                reproduction="research data canary",
                required_remediation="chain-of-thought canary",
            )
            low = self.review_finding("F02", severity="low", blocking=False)
            low.update(
                title="private report canary",
                reproduction="user-data path canary",
                required_remediation="secret material canary",
            )
            ledger = self.write_task_review_ledger(
                repo,
                task,
                name="private-review-path.json",
                reviewer="reviewer-secret-identity",
                result="changes-requested",
                findings=[critical, low],
                notes="free-form review note canary",
            )
            with patch("taskctl.utc_now", return_value="2026-08-21T02:02:03+00:00"), patch("taskctl.persist"):
                command_review(
                    Namespace(
                        task=task["id"],
                        reviewer="reviewer-secret-identity",
                        result="changes-requested",
                        from_file=str(ledger),
                        lease_hours=8,
                        note="free-form review note canary",
                        file=str(repo / "planning" / "backlog.yaml"),
                    ),
                    *context,
                )

            event = task["review_control"]["attempts"][0]["telemetry"]
            self.assertEqual(
                {
                    "task_id",
                    "amendment_id",
                    "attempt_id",
                    "submitted_at",
                    "reviewed_at",
                    "duration_seconds",
                    "outcome",
                    "finding_counts",
                    "command_ids",
                    "remediation",
                },
                set(event),
            )
            self.assertEqual(
                {"critical", "high", "medium", "low", "blocking", "total"},
                set(event["finding_counts"]),
            )
            self.assertEqual(
                {"prior_attempt_id", "replayed_finding_ids", "closed_finding_ids"},
                set(event["remediation"]),
            )
            self.assertEqual(123, event["duration_seconds"])
            self.assertEqual(
                {"critical": 1, "high": 0, "medium": 0, "low": 1, "blocking": 1, "total": 2},
                event["finding_counts"],
            )
            self.assertEqual(["foundation:unit"], event["command_ids"])
            self.assertEqual(
                {"prior_attempt_id": None, "replayed_finding_ids": [], "closed_finding_ids": []},
                event["remediation"],
            )

            outputs: list[str] = []
            for _ in range(2):
                with redirect_stdout(io.StringIO()) as stream:
                    taskctl_module.command_review_telemetry(Namespace(repo_root=repo), *context)
                outputs.append(stream.getvalue())
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual([event], json.loads(outputs[0]))
            forbidden = [
                raw_command,
                hashlib.sha256(raw_command.encode("utf-8")).hexdigest(),
                risk_canary,
                "private-user-data-path.json",
                "reviewer-secret-identity",
                "free-form review note canary",
                "source content canary",
                "research data canary",
                "chain-of-thought canary",
                "private report canary",
                "user-data path canary",
                "secret material canary",
                head,
                task["review_control"]["attempts"][0]["submission"]["evidence_reference"]["sha256"],
            ]
            for canary in forbidden:
                self.assertNotIn(canary, outputs[0])

            missing = copy.deepcopy(task)
            missing_attempt = missing["review_control"]["attempts"][0]
            missing_attempt.pop("telemetry")
            errors = taskctl_module.task_review_telemetry_errors(missing, missing_attempt, repo)
            self.assertTrue(any("lacks required privacy-safe telemetry" in error for error in errors), errors)
            control_errors = taskctl_module.task_review_control_errors(missing, repo)
            self.assertTrue(
                any("lacks required privacy-safe telemetry" in error for error in control_errors),
                control_errors,
            )
            with self.assertRaisesRegex(ValueError, "lacks required privacy-safe telemetry"):
                taskctl_module.task_review_telemetry_events({missing["id"]: missing})
            with self.assertRaisesRegex(SystemExit, "lacks required privacy-safe telemetry"):
                taskctl_module.command_review_telemetry(
                    Namespace(repo_root=repo),
                    context[0],
                    context[1],
                    context[2],
                    {missing["id"]: missing},
                    context[4],
                )

            historical_t01: dict[str, Any] = {
                "id": "W1.A02.T01",
                "review_control": {
                    "version": 1,
                    "attempts": [
                        {
                            "submission": {
                                "id": "R01",
                                "submitted_at": "2026-08-21T01:10:21+00:00",
                                "selected_checks": ["raw historical command, not a telemetry ID"],
                            },
                            "review": {
                                "result": "changes-requested",
                                "reviewed_at": "2026-08-21T01:21:15+00:00",
                            },
                            "findings": [
                                {"id": "W1.A02.T01-R01-F01", "severity": "medium", "blocking": True},
                                {"id": "W1.A02.T01-R01-F02", "severity": "low", "blocking": True},
                            ],
                            "closures": [],
                        }
                    ],
                    "current_submission": None,
                },
            }
            historical_attempt = historical_t01["review_control"]["attempts"][0]
            self.assertEqual([], taskctl_module.task_review_telemetry_errors(historical_t01, historical_attempt, repo))
            self.assertEqual(
                [],
                taskctl_module.task_review_telemetry_events({historical_t01["id"]: historical_t01}),
            )
            historical_attempt["submission"]["selected_command_ids"] = []
            self.assertEqual([], taskctl_module.task_review_telemetry_errors(historical_t01, historical_attempt, repo))

            count_tamper = copy.deepcopy(task)
            count_tamper["review_control"]["attempts"][0]["telemetry"]["finding_counts"]["total"] = 99
            errors = taskctl_module.task_review_telemetry_errors(
                count_tamper,
                count_tamper["review_control"]["attempts"][0],
                repo,
            )
            self.assertTrue(any("differs from its exact" in error for error in errors), errors)
            with self.assertRaisesRegex(SystemExit, "differs from its exact"):
                taskctl_module.command_review_telemetry(
                    Namespace(repo_root=repo),
                    context[0],
                    context[1],
                    context[2],
                    {count_tamper["id"]: count_tamper},
                    context[4],
                )

            dangling = copy.deepcopy(task)
            dangling["review_control"]["attempts"][0]["telemetry"]["remediation"]["prior_attempt_id"] = "R99"
            errors = taskctl_module.task_review_telemetry_errors(
                dangling,
                dangling["review_control"]["attempts"][0],
                repo,
            )
            self.assertTrue(any("differs from its exact" in error for error in errors), errors)

            reversed_time = copy.deepcopy(task)
            reversed_attempt = reversed_time["review_control"]["attempts"][0]
            reversed_attempt["submission"]["submitted_at"] = "2026-08-21T03:00:00+00:00"
            reversed_attempt["telemetry"]["submitted_at"] = "2026-08-21T03:00:00+00:00"
            errors = taskctl_module.task_review_telemetry_errors(reversed_time, reversed_attempt, repo)
            self.assertTrue(any("duration cannot be negative" in error for error in errors), errors)

            invalid_time = copy.deepcopy(task)
            invalid_attempt = invalid_time["review_control"]["attempts"][0]
            invalid_attempt["submission"]["submitted_at"] = "not-a-time"
            invalid_attempt["telemetry"]["submitted_at"] = "not-a-time"
            errors = taskctl_module.task_review_telemetry_errors(invalid_time, invalid_attempt, repo)
            self.assertTrue(any("timestamps are invalid" in error for error in errors), errors)

            unknown = copy.deepcopy(task)
            unknown_attempt = unknown["review_control"]["attempts"][0]
            unknown_attempt["submission"]["selected_command_ids"] = ["unknown:command"]
            unknown_attempt["telemetry"]["command_ids"] = ["unknown:command"]
            errors = taskctl_module.task_review_telemetry_errors(unknown, unknown_attempt, repo)
            self.assertTrue(any("unknown canonical verification command IDs" in error for error in errors), errors)

            amendment_task = copy.deepcopy(task)
            amendment_task["id"] = "W1.A02.T02"
            amendment_task["amendment_id"] = "W1.A02"
            amendment_event = taskctl_module.build_task_review_telemetry_event(
                amendment_task,
                amendment_task["review_control"]["attempts"][0],
            )
            self.assertEqual("W1.A02", amendment_event["amendment_id"])

    def test_t01_append_only_history_and_legacy_projection_compatibility(self) -> None:
        context = self.workflow()
        data, _capabilities, _slices, tasks, _gates = context
        task = tasks["CAP-00.S01.T01"]
        task["review_control"] = {
            "version": 1,
            "attempts": [
                {
                    "submission": {"id": "R01"},
                    "review": {
                        "reviewer": "independent-reviewer",
                        "result": "changes-requested",
                        "reviewed_at": "2026-08-21T01:00:00+00:00",
                        "notes": "preserve me",
                    },
                    "ledger": {"path": "artifacts/evidence/review-01.json", "sha256": "1" * 64},
                    "findings": [self.review_finding("F01")],
                    "closures": [],
                }
            ],
            "current_submission": None,
        }
        history = taskctl_module.task_review_history_snapshot(data)
        task["review_control"]["attempts"][0]["review"]["notes"] = "rewritten"
        with self.assertRaisesRegex(SystemExit, "Append-only task review history changed"):
            save_validated("unused", data, expected_task_review_history=history)

        legacy = self.workflow()
        legacy_task = legacy[3]["CAP-00.S01.T01"]
        self.assertNotIn("review_control", legacy_task)
        legacy_task.update(
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
            command_review(
                Namespace(
                    task=legacy_task["id"],
                    reviewer="legacy-reviewer",
                    result="approved",
                    from_file=None,
                    lease_hours=8,
                    note="legacy latest projection",
                    file="unused",
                ),
                *legacy,
            )
        self.assertNotIn("review_control", legacy_task)
        self.assertEqual("approved", legacy_task["review"]["result"])

        controlled = copy.deepcopy(task)
        controlled["review_control"]["attempts"][0]["review"]["notes"] = "preserve me"
        controlled["review"] = {
            "reviewer": "different-reviewer",
            "result": "approved",
            "reviewed_at": "2026-08-21T03:00:00+00:00",
            "notes": "flattened history",
        }
        errors = taskctl_module.task_review_control_errors(controlled, repo=None)
        self.assertIn(
            f"{controlled['id']}: legacy latest-review projection differs from append-only history",
            errors,
        )

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

    def test_wave_resume_appends_one_non_self_referential_record(self) -> None:
        context = self.workflow()
        data, capabilities, slices, tasks, _gates = context
        capabilities["CAP-00"]["campaign"] = None
        wave = data["waves"][0]
        wave["id"] = "W1"
        slices["CAP-00.S01"]["wave"] = "W1"
        tasks["CAP-00.S01.T01"]["wave"] = "W1"
        wave["campaign"] = {
            "status": "PAUSED",
            "scope": "wave",
            "owner": "alice",
            "branch": "codex/test",
            "worktree": REPO.as_posix(),
            "base_sha": "9" * 40,
            "profile": "LOC",
            "platform": "windows-x64",
            "started_at": "2026-08-20T00:00:00+00:00",
            "updated_at": "2026-08-23T00:00:00+00:00",
            "pause_reason": "Quiescent test boundary",
            "pause_category": "human-decision",
            "lease": None,
        }
        wave["completion"]["status"] = "PAUSED"
        prior = copy.deepcopy(wave["campaign"])
        args = Namespace(
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
        identity = ("alice", "codex/test", "a" * 40, REPO.as_posix())
        with (
            patch("taskctl.approved_unbootstrapped_amendment", return_value=None),
            patch("taskctl.global_program_position", return_value={"state": "ACTIVE_WAVE", "current_wave": "W1"}),
            patch("taskctl.require_wave_planning_ready"),
            patch("taskctl.git_execution_identity", return_value=identity),
            patch("taskctl.require_clean_repository"),
            patch("taskctl.persist") as persisted,
        ):
            command_wave_resume(args, *context)

        record = wave["campaign"]["resume_records"][0]
        self.assertEqual("W1.R01", record["id"])
        self.assertEqual("W1", record["wave_id"])
        self.assertEqual("a" * 40, record["pre_resume_commit"])
        self.assertEqual(canonical_json_sha256(prior), record["prior_campaign_sha256"])
        self.assertEqual("alice", record["actor"])
        self.assertEqual(record["resumed_at"], wave["campaign"]["updated_at"])
        self.assertEqual("a" * 40, wave["campaign"]["base_sha"])
        self.assertEqual("W1", args.authorized_wave_resume_append)
        persisted.assert_called_once()

    def test_wave_resume_wrong_identity_fails_without_mutation(self) -> None:
        context = self.workflow()
        data, capabilities, slices, tasks, _gates = context
        capabilities["CAP-00"]["campaign"] = None
        wave = data["waves"][0]
        wave["id"] = "W1"
        slices["CAP-00.S01"]["wave"] = "W1"
        tasks["CAP-00.S01.T01"]["wave"] = "W1"
        wave["campaign"] = {
            "status": "PAUSED",
            "scope": "wave",
            "owner": "alice",
            "branch": "codex/test",
            "worktree": REPO.as_posix(),
            "base_sha": "9" * 40,
            "profile": "LOC",
            "platform": "windows-x64",
            "started_at": "2026-08-20T00:00:00+00:00",
            "updated_at": "2026-08-23T00:00:00+00:00",
            "pause_reason": "Quiescent test boundary",
            "pause_category": "human-decision",
            "lease": None,
        }
        before = json.dumps(data, sort_keys=True)
        args = Namespace(
            wave="W1",
            agent="alice",
            branch="codex/test",
            base_sha="a" * 40,
            worktree=str(REPO),
            profile="LAB",
            platform="windows-x64",
            lease_hours=8,
            file=str(REPO / "planning" / "backlog.yaml"),
        )
        identity = ("alice", "codex/test", "a" * 40, REPO.as_posix())
        with (
            patch("taskctl.approved_unbootstrapped_amendment", return_value=None),
            patch("taskctl.global_program_position", return_value={"state": "ACTIVE_WAVE", "current_wave": "W1"}),
            patch("taskctl.require_wave_planning_ready"),
            patch("taskctl.git_execution_identity", return_value=identity),
            patch("taskctl.require_clean_repository"),
            self.assertRaisesRegex(SystemExit, "recorded profile and platform"),
        ):
            command_wave_resume(args, *context)
        self.assertEqual(before, json.dumps(data, sort_keys=True))

    def test_wave_resume_records_validate_historical_binding_and_fail_closed(self) -> None:
        data, *_ = load(str(REPO / "planning" / "backlog.yaml"))
        wave = next(item for item in data["waves"] if item["id"] == "W1")
        prior = copy.deepcopy(wave["campaign"])
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        resumed_at = "2026-08-24T00:00:00+00:00"
        record = {
            "id": "W1.R01",
            "wave_id": "W1",
            "control_revision": 6,
            "prior_status": "PAUSED",
            "pre_resume_commit": head,
            "prior_campaign_sha256": canonical_json_sha256(prior),
            "branch": prior["branch"],
            "worktree": prior["worktree"],
            "profile": prior["profile"],
            "platform": prior["platform"],
            "actor": prior["owner"],
            "resumed_at": resumed_at,
        }
        campaign = copy.deepcopy(prior)
        campaign.update(
            status="ACTIVE",
            base_sha=head,
            updated_at=resumed_at,
            pause_reason=None,
            pause_category=None,
            resume_records=[record],
        )
        self.assertEqual([], wave_resume_record_errors(data, "W1", campaign, REPO))

        stale = copy.deepcopy(campaign)
        stale["resume_records"][0]["prior_campaign_sha256"] = "0" * 64
        self.assertTrue(
            any("stale or rewritten" in error for error in wave_resume_record_errors(data, "W1", stale, REPO))
        )

        cross_wave = copy.deepcopy(campaign)
        cross_wave["resume_records"][0]["wave_id"] = "W2"
        self.assertTrue(any("cross-Wave" in error for error in wave_resume_record_errors(data, "W1", cross_wave, REPO)))

        non_ancestral = copy.deepcopy(campaign)
        non_ancestral["resume_records"][0]["pre_resume_commit"] = "0" * 40
        non_ancestral["base_sha"] = "0" * 40
        self.assertTrue(
            any(
                "missing or non-ancestral" in error
                for error in wave_resume_record_errors(data, "W1", non_ancestral, REPO)
            )
        )

        duplicate = copy.deepcopy(campaign)
        duplicate["resume_records"].append({**copy.deepcopy(record), "id": "W1.R02"})
        self.assertTrue(
            any(
                "duplicate pre-resume commit" in error
                for error in wave_resume_record_errors(data, "W1", duplicate, REPO)
            )
        )

        missing = copy.deepcopy(campaign)
        missing.pop("resume_records")
        self.assertTrue(
            any(
                "lacks its durable resume record" in error
                for error in wave_resume_record_errors(data, "W1", missing, None)
            )
        )

    def test_wave_resume_history_is_append_only_and_only_resume_may_append(self) -> None:
        data, *_ = load(str(REPO / "planning" / "backlog.yaml"))
        wave = next(item for item in data["waves"] if item["id"] == "W1")
        record = {
            "id": "W1.R01",
            "wave_id": "W1",
            "control_revision": 6,
            "prior_status": "PAUSED",
            "pre_resume_commit": "a" * 40,
            "prior_campaign_sha256": "b" * 64,
            "branch": wave["campaign"]["branch"],
            "worktree": wave["campaign"]["worktree"],
            "profile": wave["campaign"]["profile"],
            "platform": wave["campaign"]["platform"],
            "actor": wave["campaign"]["owner"],
            "resumed_at": wave["campaign"]["updated_at"],
        }
        snapshot = wave_resume_history_snapshot(data)
        wave["campaign"]["resume_records"] = [record]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backlog.yaml"
            destination.write_text("sentinel: true\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "Unauthorized Wave resume history append for W1"):
                save_validated(
                    str(destination),
                    data,
                    expected_wave_resume_history=snapshot,
                )
            self.assertEqual("sentinel: true\n", destination.read_text(encoding="utf-8"))

        preserved = wave_resume_history_snapshot(data)
        wave["campaign"]["resume_records"][0]["actor"] = "mallory"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backlog.yaml"
            destination.write_text("sentinel: true\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "Append-only Wave resume history changed for W1"):
                save_validated(
                    str(destination),
                    data,
                    expected_wave_resume_history=preserved,
                )
            self.assertEqual("sentinel: true\n", destination.read_text(encoding="utf-8"))

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
        data, capabilities, slices, tasks, gates = self.canonical_workflow_with_b00_bootstrap(
            self.b00_initial_review_bootstrap_fixture()
        )
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

        data, capabilities, slices, tasks, gates = self.canonical_workflow_with_b00_bootstrap(
            self.b00_initial_review_bootstrap_fixture()
        )
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
        self.assertIn("W1.A02.B00: branch does not match the claimed task branch", joined)
        self.assertIn("W1.A02.B00: bootstrap changed path is outside approved scope", joined)
        self.assertIn("W1.A02.B00: bootstrap reviewer is not independent from the implementer", joined)

    def test_b00_r01_review_and_materialization_revalidate_the_frozen_bootstrap(self) -> None:
        data, capabilities, slices, tasks, gates = self.canonical_workflow_with_b00_bootstrap(
            self.b00_initial_review_bootstrap_fixture()
        )
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

        data, capabilities, slices, tasks, gates = self.canonical_workflow_with_b00_bootstrap(
            self.b00_initial_review_bootstrap_fixture()
        )
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
            evidence_path.write_text(
                json.dumps(
                    {
                        "commit": "d" * 40,
                        "baseCommit": "2493dee313a2df8929dbd2eed31d9e0e672fc368",
                        "branch": "codex/w1-windows-local-runtime",
                        "changedFiles": ["tests/foundation/test_taskctl_workflow.py"],
                    }
                ),
                encoding="utf-8",
            )
            data, capabilities, slices, tasks, gates = self.canonical_workflow_with_b00_bootstrap(
                self.b00_resubmission_source_bootstrap_fixture()
            )
            amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
            bootstrap = amendment["bootstrap"]
            prior_projection = copy.deepcopy(
                {
                    key: bootstrap[key]
                    for key in ("implementer", "implementation_commit", "submission_branch", "evidence", "review")
                }
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

    def test_b00_r04_historical_bootstrap_validation_does_not_depend_on_live_branch(self) -> None:
        data, capabilities, slices, tasks, gates = self.canonical_workflow_with_b00_bootstrap(
            self.b00_resubmitted_review_bootstrap_fixture()
        )
        original_run = subprocess.run

        def main_checkout(command: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
            if command[:3] == ["git", "branch", "--show-current"]:
                return subprocess.CompletedProcess(command, 0, "main\n", "")
            return original_run(command, *args, **kwargs)

        with (
            patch("taskctl.subprocess.run", side_effect=main_checkout),
            patch("taskctl.evidence_reference_errors", return_value=[]),
        ):
            errors = validate(data, capabilities, slices, tasks, gates, repo=REPO)

        self.assertEqual([], errors)

    def test_b00_r04_bootstrap_review_denies_the_wrong_live_branch(self) -> None:
        data, capabilities, slices, tasks, gates = self.canonical_workflow_with_b00_bootstrap(
            self.b00_initial_review_bootstrap_fixture()
        )
        approval = json.loads((REPO / "planning/wave-amendment-approvals/W1.A02.json").read_text(encoding="utf-8"))
        packet = json.loads(
            (REPO / "planning/enabler-change-requests/ECR-0001.packet.json").read_text(encoding="utf-8")
        )
        original_run = subprocess.run

        def wrong_live_branch(command: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
            if command[:3] == ["git", "branch", "--show-current"]:
                return subprocess.CompletedProcess(command, 0, "main\n", "")
            return original_run(command, *args, **kwargs)

        with (
            self.assertRaisesRegex(
                SystemExit,
                "bootstrap submission branch does not match the current codex branch",
            ),
            patch("taskctl.discover_repository", return_value=REPO),
            patch("taskctl.require_clean_repository"),
            patch("taskctl.load_amendment_authority", return_value=(approval, packet, b"approval")),
            patch("taskctl.subprocess.run", side_effect=wrong_live_branch),
            patch("taskctl.persist"),
        ):
            taskctl_module.command_amendment_bootstrap_review(
                Namespace(
                    amendment="W1.A02",
                    reviewer="new-independent-reviewer",
                    result="approved",
                    note="The live branch must remain part of review entry validation.",
                    file=str(REPO / "planning/backlog.yaml"),
                ),
                data,
                capabilities,
                slices,
                tasks,
                gates,
            )

    def test_b00_r04_bootstrap_manifest_must_match_the_frozen_submission_branch(self) -> None:
        data, capabilities, slices, tasks, gates = self.canonical_workflow_with_b00_bootstrap(
            self.b00_initial_review_bootstrap_fixture()
        )
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        amendment["bootstrap"]["submission_branch"] = "codex/forged-submission-branch"

        with patch("taskctl.evidence_reference_errors", return_value=[]):
            errors = validate(data, capabilities, slices, tasks, gates, repo=REPO)

        self.assertIn(
            "W1.A02.B00: branch does not match the claimed task branch",
            errors,
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

    def test_consecutive_amendment_hold_has_one_latest_owner_and_allows_only_adopted_predecessors(self) -> None:
        data, capabilities, slices, tasks, gates = self.interrupted_workflow(lifecycle_status="ADOPTED")
        predecessor = data["wave_amendments"][0]
        predecessor["completion"].update(
            status="APPROVED",
            reviewer="independent-reviewer",
            reviewed_at="2026-08-21T00:00:00+00:00",
            evidence=["exit.json"],
        )
        successor = copy.deepcopy(predecessor)
        successor["id"] = "W1.A03"
        successor["change_request_id"] = "ECR-0002"
        successor["approval_reference"]["path"] = "planning/wave-amendment-approvals/W1.A03.json"
        successor["bootstrap"]["id"] = "W1.A03.B00"
        successor["lifecycle"] = {
            "status": "MATERIALIZED",
            "history": [
                {
                    "id": "E01",
                    "status": "APPROVED",
                    "actor": "repository-owner",
                    "at": "2026-08-21T00:00:00+00:00",
                    "rationale": "Approved successor.",
                },
                {
                    "id": "E02",
                    "status": "MATERIALIZED",
                    "actor": "codex",
                    "at": "2026-08-21T00:01:00+00:00",
                    "rationale": "Materialized successor.",
                },
            ],
        }
        successor["campaign"] = None
        successor["completion"] = {
            "status": "PENDING",
            "reviewer": None,
            "reviewed_at": None,
            "evidence": [],
            "notes": None,
        }
        successor_tasks = []
        for position, source in enumerate(successor["tasks"]):
            task = copy.deepcopy(source)
            task["id"] = f"W1.A03.T{position + 1:02d}"
            task["amendment_id"] = "W1.A03"
            task["dependencies"] = ["W1.A03.B00" if position == 0 else "W1.A03.T01"]
            task["_amendment_id"] = "W1.A03"
            successor_tasks.append(task)
            tasks[task["id"]] = task
        successor["tasks"] = successor_tasks
        data["wave_amendments"].append(successor)

        errors = validate(data, capabilities, slices, tasks, gates)
        self.assertNotIn("W1.A02: terminal lifecycle did not restore ordinary Wave scope", errors)
        self.assertNotIn("W1: amendment-hold scope requires exactly one executable amendment owner", errors)

        predecessor["lifecycle"]["status"] = "WITHDRAWN"
        predecessor["lifecycle"]["history"][-1]["status"] = "WITHDRAWN"
        errors = validate(data, capabilities, slices, tasks, gates)
        self.assertIn("W1.A02: predecessor of the amendment-hold owner is not ADOPTED", errors)

        predecessor["lifecycle"]["status"] = "MATERIALIZED"
        predecessor["lifecycle"]["history"][-1]["status"] = "MATERIALIZED"
        errors = validate(data, capabilities, slices, tasks, gates)
        self.assertIn("W1: more than one amendment owns the shared amendment-hold scope", errors)

    def test_amendment_exit_review_migrates_r01_preserves_it_through_r02_and_binds_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, repo, amendment, approved_packet, implementation_commit, reviewed_state = (
                self.amendment_exit_repository(Path(temporary))
            )
            file_path = str(repo / "planning" / "backlog.yaml")
            authority: tuple[dict[str, Any], dict[str, Any], bytes] = (
                {},
                approved_packet,
                b"approved packet",
            )
            review_args = Namespace(
                amendment="W1.A02",
                reviewer="agent:exit-reviewer",
                result="changes-requested",
                from_path="",
                note="",
                file=file_path,
            )
            with chdir(repo), patch("taskctl.load_amendment_authority", return_value=authority):
                legacy_submission = taskctl_module.build_amendment_exit_submission(
                    review_args,
                    context[0],
                    amendment,
                    amendment["completion"]["evidence"][0],
                    migration_state_commit=reviewed_state,
                )
            finding = {
                "id": "W1.A02-EXIT-R01-F01",
                "severity": "high",
                "blocking": True,
                "criterion_index": 6,
                "title": "Exit review is not history-bound",
                "reproduction": "Substitute the reviewed evidence reference.",
                "required_remediation": "Freeze review and checkpoint bindings.",
            }
            r01_ledger = self.write_amendment_exit_ledger(
                repo,
                legacy_submission,
                attempt_id="R01",
                reviewed_state_commit=reviewed_state,
                result="changes-requested",
                findings=[finding],
                closures=[],
            )
            review_args.from_path = str(r01_ledger)
            with (
                chdir(repo),
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_review(review_args, *context)

            control = amendment["completion"]["exit_review_control"]
            self.assertIsNone(control["current_submission"])
            self.assertEqual(["R01"], [item["submission"]["id"] for item in control["attempts"]])
            self.assertEqual(reviewed_state, control["attempts"][0]["submission"]["candidate_commit"])
            self.assertEqual(
                implementation_commit,
                control["attempts"][0]["submission"]["declared_candidate_commit"],
            )
            self.assertEqual("changes-requested", control["attempts"][0]["review"]["result"])
            with patch("taskctl.load_amendment_authority", return_value=authority):
                self.assertEqual(
                    [],
                    taskctl_module.amendment_exit_review_control_errors(context[0], amendment, repo),
                )
            frozen_r01 = json.dumps(control["attempts"][0], sort_keys=True)

            amendment["campaign"].update(
                status="ACTIVE",
                pause_reason=None,
                lease=new_lease("alice", 8),
            )
            amendment["lifecycle"]["status"] = "ACTIVE"
            amendment["lifecycle"]["history"].append(
                {
                    "id": "E03",
                    "status": "ACTIVE",
                    "actor": "alice",
                    "at": "2026-08-21T03:00:00+00:00",
                    "rationale": "Perform bounded remediation.",
                }
            )
            context[0]["control_plane"]["active_amendment"] = "W1.A02"
            exit_r02 = repo / "artifacts" / "evidence" / "W1.A02.exit-R02.json"
            r02_manifest = {
                "documentType": "wave-amendment-exit-evidence",
                "schemaVersion": "1.0",
                "amendmentId": "W1.A02",
                "changeRequestId": "ECR-0001",
                "targetWave": "W1",
                "candidateCommit": reviewed_state,
                "branch": "codex/amendment-exit",
                "waveCampaign": {
                    "status": "PAUSED",
                    "scope": "amendment-hold",
                    "pauseReason": "Approved interrupting amendment",
                },
                "amendmentCampaign": {
                    "status": "ACTIVE",
                    "scope": "wave-amendment",
                    "pauseReason": None,
                },
                "requiredNextTransition": "independent amendment exit review",
                "checks": [
                    {
                        "command": "python tools/taskctl.py validate",
                        "result": "passed",
                        "summary": "The remediated exit state validates.",
                    },
                    {
                        "command": "python -m unittest focused-exit-control",
                        "result": "passed",
                        "summary": "Adversarial exit tests pass.",
                    },
                ],
            }
            exit_r02.write_text(json.dumps(r02_manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
            (repo / "planning" / "backlog.yaml").write_text(
                json.dumps(context[0], indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            bound_exit_commit = self.commit_all(repo, "bounded R02 exit evidence")
            submit_args = Namespace(
                amendment="W1.A02",
                agent="alice",
                evidence=None,
                from_path=str(exit_r02),
                note="R02 remediates the open exit finding.",
                file=file_path,
            )
            with (
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_submit(submit_args, *context)

            current = control["current_submission"]
            self.assertEqual("R02", current["id"])
            self.assertEqual("R01", current["prior_attempt_id"])
            self.assertEqual([finding["id"]], current["open_finding_ids"])
            self.assertEqual(bound_exit_commit, current["candidate_commit"])
            self.assertEqual(reviewed_state, current["declared_candidate_commit"])
            self.assertEqual(
                taskctl_module.canonical_json_sha256(approved_packet["acceptanceCriteria"]),
                current["acceptance_criteria_sha256"],
            )
            self.assertEqual(taskctl_module.amendment_exit_packet_sha256(current), current["packet_sha256"])
            self.assertEqual(
                [
                    "python tools/taskctl.py validate",
                    "python -m unittest focused-exit-control",
                ],
                current["selected_checks"],
            )
            self.assertEqual(
                taskctl_module.canonical_json_sha256(current["selected_checks"]),
                current["selected_checks_sha256"],
            )

            (repo / "planning" / "backlog.yaml").write_text(
                json.dumps(context[0], indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            r02_reviewed_state = self.commit_all(repo, "freeze R02 submission")
            closure = {
                "finding_id": finding["id"],
                "disposition": "fixed",
                "evidence": "R02 binds the exact candidate, review ledger, and checkpoint evidence.",
            }
            r02_ledger = self.write_amendment_exit_ledger(
                repo,
                current,
                attempt_id="R02",
                reviewed_state_commit=r02_reviewed_state,
                result="approved",
                findings=[],
                closures=[closure],
            )
            approved_review_args = Namespace(
                amendment="W1.A02",
                reviewer="agent:exit-reviewer",
                result="approved",
                from_path=str(r02_ledger),
                note="",
                file=file_path,
            )
            stale_ledger = self.write_amendment_exit_ledger(
                repo,
                current,
                attempt_id="R02",
                reviewed_state_commit=bound_exit_commit,
                result="approved",
                findings=[],
                closures=[closure],
            )
            with (
                self.assertRaisesRegex(SystemExit, "exact current frozen submission state"),
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_review(
                    Namespace(**{**vars(approved_review_args), "from_path": str(stale_ledger)}),
                    *context,
                )
            self.write_amendment_exit_ledger(
                repo,
                current,
                attempt_id="R02",
                reviewed_state_commit=r02_reviewed_state,
                result="approved",
                findings=[],
                closures=[closure],
            )
            denied_ledger = json.loads(r02_ledger.read_text(encoding="utf-8"))
            denied_ledger["closures"] = []
            r02_ledger.write_text(json.dumps(denied_ledger, indent=2) + "\n", encoding="utf-8", newline="\n")
            with (
                self.assertRaisesRegex(SystemExit, "blocking findings remain open"),
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_review(approved_review_args, *context)
            self.write_amendment_exit_ledger(
                repo,
                current,
                attempt_id="R02",
                reviewed_state_commit=r02_reviewed_state,
                result="approved",
                findings=[],
                closures=[closure],
            )
            with (
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_review(approved_review_args, *context)

            self.assertEqual(frozen_r01, json.dumps(control["attempts"][0], sort_keys=True))
            self.assertEqual(["R01", "R02"], [item["submission"]["id"] for item in control["attempts"]])
            self.assertEqual([closure], control["attempts"][1]["closures"])
            self.assertEqual("APPROVED", amendment["completion"]["status"])
            with chdir(repo), patch("taskctl.load_amendment_authority", return_value=authority):
                self.assertEqual(
                    [],
                    taskctl_module.amendment_exit_review_control_errors(context[0], amendment, repo),
                )

            (repo / "planning" / "backlog.yaml").write_text(
                json.dumps(context[0], indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            reviewed_completion_commit = self.commit_all(repo, "approved R02 completion")
            checkpoint_path = repo / "artifacts" / "evidence" / "W1.A02.adoption.json"
            missing_adopt_args = Namespace(
                amendment="W1.A02",
                agent="alice",
                evidence=None,
                from_path=str(repo / "artifacts" / "evidence" / "missing-adoption.json"),
                note="",
                file=file_path,
            )
            with (
                self.assertRaisesRegex(SystemExit, "must exist in current HEAD"),
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_adopt(missing_adopt_args, *context)
            checkpoint_manifest = {
                "documentType": "wave-amendment-adoption-evidence",
                "amendmentId": "W1.A02",
                "targetWave": "W1",
                "candidateCommit": reviewed_completion_commit,
                "branch": "codex/amendment-exit",
                "reviewedCompletionCommit": reviewed_completion_commit,
            }
            checkpoint_path.write_text(json.dumps(checkpoint_manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
            checkpoint_commit = self.commit_all(repo, "bind adoption checkpoint")

            def require_exit_integrity(_file: str, _amendment: dict[str, Any]) -> None:
                errors = taskctl_module.amendment_exit_review_control_errors(context[0], _amendment, repo)
                if errors:
                    raise SystemExit("Invalid amendment exit control:\n- " + "\n- ".join(errors))

            adopt_args = Namespace(
                amendment="W1.A02",
                agent="alice",
                evidence=None,
                from_path=str(checkpoint_path),
                note="Adopt the independently approved control amendment.",
                file=file_path,
            )
            checkpoint_path.write_text(
                json.dumps({**checkpoint_manifest, "targetWave": "W2"}, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with (
                self.assertRaisesRegex(SystemExit, "Tracked worktree changes"),
                patch("taskctl.require_runtime_amendment_integrity", side_effect=require_exit_integrity),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_adopt(adopt_args, *context)
            subprocess.run(
                ["git", "restore", "artifacts/evidence/W1.A02.adoption.json"],
                cwd=repo,
                capture_output=True,
                check=True,
            )
            with (
                patch("taskctl.require_runtime_amendment_integrity", side_effect=require_exit_integrity),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_adopt(adopt_args, *context)

            checkpoint = context[0]["waves"][0]["checkpoints"][-1]
            self.assertEqual("ADOPTED", amendment["lifecycle"]["status"])
            self.assertEqual("wave", context[0]["waves"][0]["campaign"]["scope"])
            self.assertEqual(
                {
                    "type": "amendment-adoption-evidence",
                    "amendment_id": "W1.A02",
                    "path": "artifacts/evidence/W1.A02.adoption.json",
                    "sha256": evidence_sha256(checkpoint_path.read_bytes()),
                    "commit": checkpoint_commit,
                },
                checkpoint["evidence"][0],
            )
            with chdir(repo), patch("taskctl.load_amendment_authority", return_value=authority):
                self.assertEqual(
                    [],
                    taskctl_module.amendment_exit_review_control_errors(context[0], amendment, repo),
                )

            amendment_history = amendment_history_snapshot(context[0])
            rewritten = copy.deepcopy(context[0])
            rewritten["wave_amendments"][0]["completion"]["exit_review_control"]["attempts"][0]["review"]["notes"] = (
                "rewritten"
            )
            with self.assertRaisesRegex(SystemExit, "Append-only lifecycle history changed for W1.A02:exit-review"):
                save_validated(
                    file_path,
                    rewritten,
                    expected_amendment_history=amendment_history,
                    schema_path=REPO / "planning" / "backlog.schema.json",
                )

            checkpoint_history = taskctl_module.wave_checkpoint_history_snapshot(context[0])
            rewritten = copy.deepcopy(context[0])
            rewritten["waves"][0]["checkpoints"][-1]["evidence"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(SystemExit, "Append-only Wave checkpoint history changed for W1"):
                save_validated(
                    file_path,
                    rewritten,
                    expected_wave_checkpoint_history=checkpoint_history,
                    schema_path=REPO / "planning" / "backlog.schema.json",
                )

    def test_amendment_exit_and_adoption_evidence_fail_closed_on_tamper_and_unreviewed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, repo, amendment, approved_packet, _implementation_commit, reviewed_state = (
                self.amendment_exit_repository(Path(temporary))
            )
            authority: tuple[dict[str, Any], dict[str, Any], bytes] = (
                {},
                approved_packet,
                b"approved packet",
            )
            file_path = str(repo / "planning" / "backlog.yaml")
            review_args = Namespace(
                amendment="W1.A02",
                reviewer="agent:exit-reviewer",
                result="changes-requested",
                from_path="",
                note="",
                file=file_path,
            )
            with chdir(repo), patch("taskctl.load_amendment_authority", return_value=authority):
                submission = taskctl_module.build_amendment_exit_submission(
                    review_args,
                    context[0],
                    amendment,
                    amendment["completion"]["evidence"][0],
                    migration_state_commit=reviewed_state,
                )
                baseline_errors = taskctl_module.amendment_exit_submission_errors(
                    context[0],
                    amendment,
                    approved_packet,
                    submission,
                    expected_id="R01",
                    expected_prior_id=None,
                    expected_prior_submission=None,
                    expected_open_ids=[],
                    repo=repo,
                    strict_state=False,
                )
            self.assertEqual([], baseline_errors)

            relabeled_exit_reference = copy.deepcopy(submission["evidence_reference"])
            relabeled_exit_reference["type"] = "amendment-adoption-evidence"
            with chdir(repo):
                relabeled_errors = taskctl_module.bound_evidence_reference_errors(
                    repo,
                    relabeled_exit_reference,
                    expected_type="amendment-adoption-evidence",
                    expected_amendment="W1.A02",
                    label="W1.A02/adoption",
                )
            self.assertTrue(
                any("documentType does not match" in error for error in relabeled_errors),
                relabeled_errors,
            )

            mutations = [
                ("evidence-hash", ("evidence_reference", "sha256"), "0" * 64, "evidence hash differs"),
                ("evidence-path", ("evidence_reference", "path"), "artifacts/evidence/missing.json", "absent"),
                ("packet-hash", ("packet_sha256",), "0" * 64, "packet hash mismatch"),
                (
                    "criteria-hash",
                    ("acceptance_criteria_sha256",),
                    "0" * 64,
                    "criteria hash differs",
                ),
                ("branch", ("branch",), "codex/substituted", "frozen exit branch differs"),
                ("open-ids", ("open_finding_ids",), ["invented"], "exact open findings"),
            ]
            for name, path, value, expected in mutations:
                with self.subTest(name=name), patch("taskctl.load_amendment_authority", return_value=authority):
                    forged = copy.deepcopy(submission)
                    cursor: Any = forged
                    for key in path[:-1]:
                        cursor = cursor[key]
                    cursor[path[-1]] = value
                    errors = taskctl_module.amendment_exit_submission_errors(
                        context[0],
                        amendment,
                        approved_packet,
                        forged,
                        expected_id="R01",
                        expected_prior_id=None,
                        expected_prior_submission=None,
                        expected_open_ids=[],
                        repo=repo,
                        strict_state=False,
                    )
                    self.assertTrue(any(expected in error for error in errors), errors)

            amendment["campaign"].update(
                status="ACTIVE",
                branch="codex/amendment-exit",
                pause_reason=None,
                lease=new_lease("alice", 8),
            )
            amendment["completion"].update(status="CHANGES_REQUESTED")
            missing_args = Namespace(
                amendment="W1.A02",
                agent="alice",
                evidence=None,
                from_path=str(repo / "artifacts" / "evidence" / "missing.json"),
                note="",
                file=file_path,
            )
            with (
                self.assertRaisesRegex(SystemExit, "must exist in the exact candidate commit"),
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_submit(missing_args, *context)

            (repo / "implementation.txt").write_text("dirty mutation\n", encoding="utf-8")
            dirty_args = copy.copy(missing_args)
            dirty_args.from_path = str(repo / "artifacts" / "evidence" / "W1.A02.exit-R01.json")
            with (
                self.assertRaisesRegex(SystemExit, "Tracked worktree changes"),
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_submit(dirty_args, *context)
            subprocess.run(["git", "restore", "implementation.txt"], cwd=repo, capture_output=True, check=True)

            tree = subprocess.run(
                ["git", "rev-parse", "HEAD^{tree}"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            fork_commit = subprocess.run(
                ["git", "commit-tree", tree, "-m", "forked candidate"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            forked_exit = repo / "artifacts" / "evidence" / "forked-exit.json"
            forked_exit.write_text(
                json.dumps(
                    {
                        "documentType": "wave-amendment-exit-evidence",
                        "amendmentId": "W1.A02",
                        "changeRequestId": "ECR-0001",
                        "targetWave": "W1",
                        "candidateCommit": fork_commit,
                        "branch": "codex/amendment-exit",
                        "waveCampaign": {
                            "status": "PAUSED",
                            "scope": "amendment-hold",
                            "pauseReason": "Approved interrupting amendment",
                        },
                        "amendmentCampaign": {
                            "status": "ACTIVE",
                            "scope": "wave-amendment",
                            "pauseReason": None,
                        },
                        "requiredNextTransition": "independent amendment exit review",
                        "checks": [{"command": "python tools/taskctl.py validate", "result": "passed"}],
                    }
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            self.commit_all(repo, "forked candidate evidence probe")
            forked_args = copy.copy(missing_args)
            forked_args.from_path = str(forked_exit)
            with (
                self.assertRaisesRegex(SystemExit, "current codex-branch history"),
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.load_amendment_authority", return_value=authority),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_submit(forked_args, *context)

            amendment["campaign"].update(status="COMPLETE", lease=None)
            amendment["completion"].update(
                status="APPROVED",
                reviewer="agent:exit-reviewer",
                reviewed_at="2026-08-21T04:00:00+00:00",
            )
            unreviewed_checkpoint = repo / "artifacts" / "evidence" / "unreviewed-checkpoint.json"
            unreviewed_checkpoint.write_text(
                json.dumps(
                    {
                        "documentType": "wave-amendment-adoption-evidence",
                        "amendmentId": "W1.A02",
                        "targetWave": "W1",
                        "candidateCommit": reviewed_state,
                        "branch": "codex/amendment-exit",
                        "reviewedCompletionCommit": reviewed_state,
                    }
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            self.commit_all(repo, "unreviewed checkpoint probe")
            adopt_args = Namespace(
                amendment="W1.A02",
                agent="alice",
                evidence=None,
                from_path=str(unreviewed_checkpoint),
                note="",
                file=file_path,
            )
            with (
                self.assertRaisesRegex(SystemExit, "immutable amendment exit review history"),
                patch("taskctl.require_runtime_amendment_integrity"),
                patch("taskctl.persist"),
            ):
                taskctl_module.command_amendment_adopt(adopt_args, *context)

    def test_adoption_reference_validation_rejects_a_substituted_target_wave(self) -> None:
        approved_attempt = {
            "submission": {"branch": "codex/amendment-exit"},
            "review": {"result": "approved"},
        }
        amendment = {
            "id": "W1.A02",
            "target_wave": "W1",
            "completion": {"exit_review_control": {"attempts": [approved_attempt]}},
        }
        reviewed_completion = "a" * 40
        checkpoint_commit = "b" * 40
        payload = json.dumps(
            {
                "documentType": "wave-amendment-adoption-evidence",
                "amendmentId": "W1.A02",
                "targetWave": "W2",
                "candidateCommit": reviewed_completion,
                "branch": "codex/amendment-exit",
                "reviewedCompletionCommit": reviewed_completion,
            }
        ).encode()
        reference = {
            "type": "amendment-adoption-evidence",
            "amendment_id": "W1.A02",
            "path": "artifacts/evidence/W1.A02.adoption.json",
            "sha256": taskctl_module.evidence_sha256(payload),
            "commit": checkpoint_commit,
        }
        with (
            patch("taskctl.bound_evidence_reference_errors", return_value=[]),
            patch("taskctl.git_blob", return_value=payload),
            patch("taskctl.git_commit_exists", return_value=True),
            patch("taskctl.git_is_ancestor", return_value=True),
            patch(
                "taskctl.historical_amendment_completion",
                return_value={"exit_review_control": {"attempts": [approved_attempt]}},
            ),
        ):
            errors = taskctl_module.amendment_adoption_reference_errors(Path("unused"), reference, amendment)
        self.assertIn("W1.A02: adoption evidence target Wave mismatch", errors)

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

    def test_approved_exit_can_reactivate_only_for_pre_adoption_remediation(self) -> None:
        context, packet = self.packet_bound_active_amendment_workflow()
        data, capabilities, slices, tasks, gates = context
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        amendment["lifecycle"]["status"] = "REVIEW"
        amendment["campaign"].update(status="COMPLETE", lease=None)
        amendment["completion"].update(
            status="APPROVED",
            reviewer="agent:exit-reviewer",
            reviewed_at="2026-08-21T04:00:00+00:00",
            evidence=["artifacts/evidence/W1.A02.exit.json"],
            exit_review_control={
                "version": 1,
                "attempts": [
                    {
                        "submission": {"id": "R01"},
                        "review": {"result": "approved"},
                        "ledger": {},
                        "findings": [],
                        "closures": [],
                    }
                ],
                "current_submission": None,
            },
        )
        for task in amendment["tasks"]:
            task["status"] = "DONE"
        data["control_plane"]["active_amendment"] = None
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        args = Namespace(
            amendment="W1.A02",
            agent="codex",
            branch=branch,
            base_sha=head,
            worktree=str(REPO),
            profile="LOC",
            platform="windows-x64",
            lease_hours=8,
            file=str(REPO / "planning" / "backlog.yaml"),
        )
        amendment["completion"]["exit_review_control"]["attempts"][-1]["review"]["result"] = "changes-requested"
        with self.assertRaisesRegex(SystemExit, "approved-exit amendment awaiting adoption remediation"):
            taskctl_module.command_amendment_activate(args, data, capabilities, slices, tasks, gates)
        amendment["completion"]["exit_review_control"]["attempts"][-1]["review"]["result"] = "approved"
        with (
            patch("taskctl.git_execution_identity", return_value=("codex", branch, head, str(REPO))),
            patch("taskctl.discover_repository", return_value=REPO),
            patch("taskctl.require_clean_repository"),
            patch("taskctl.load_amendment_authority", return_value=({}, packet, b"packet")),
            patch("taskctl.require_amendment_packet_integrity"),
            patch("taskctl.persist"),
        ):
            taskctl_module.command_amendment_activate(args, data, capabilities, slices, tasks, gates)

        self.assertEqual("ACTIVE", amendment["lifecycle"]["status"])
        self.assertEqual("ACTIVE", amendment["campaign"]["status"])
        self.assertEqual("W1.A02", data["control_plane"]["active_amendment"])
        self.assertIn("failed adoption transition", amendment["lifecycle"]["history"][-1]["rationale"])

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
        approved_attempt = {
            "submission": {"id": "R01"},
            "review": {"result": "approved"},
            "ledger": {},
            "findings": [],
            "closures": [],
        }
        amendment["completion"]["exit_review_control"] = {
            "version": 1,
            "attempts": [approved_attempt],
            "current_submission": None,
        }
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
        reviewed_completion_commit = "b" * 40
        checkpoint_commit = "c" * 40
        checkpoint_payload = json.dumps(
            {
                "documentType": "wave-amendment-adoption-evidence",
                "amendmentId": "W1.A02",
                "targetWave": "W1",
                "candidateCommit": reviewed_completion_commit,
                "branch": "codex/test",
                "reviewedCompletionCommit": reviewed_completion_commit,
            }
        ).encode()
        with (
            patch("taskctl.require_runtime_amendment_integrity"),
            patch("taskctl.discover_repository", return_value=REPO),
            patch("taskctl.require_clean_repository"),
            patch("taskctl.git_head_branch", return_value=(checkpoint_commit, "codex/test")),
            patch(
                "taskctl.safe_evidence_relative",
                return_value=(
                    "artifacts/evidence/control-security-checkpoint.json",
                    REPO / "artifacts/evidence/control-security-checkpoint.json",
                ),
            ),
            patch("taskctl.git_blob", return_value=checkpoint_payload),
            patch("taskctl.git_is_ancestor", return_value=True),
            patch(
                "taskctl.historical_amendment_completion",
                return_value={
                    "exit_review_control": {
                        "version": 1,
                        "attempts": [copy.deepcopy(approved_attempt)],
                        "current_submission": None,
                    }
                },
            ),
            patch("taskctl.persist"),
        ):
            taskctl_module.command_amendment_adopt(
                Namespace(
                    amendment="W1.A02",
                    agent="alice",
                    evidence=None,
                    from_path="control-security-checkpoint.json",
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
        self.assertEqual(
            [
                {
                    "type": "amendment-adoption-evidence",
                    "amendment_id": "W1.A02",
                    "path": "artifacts/evidence/control-security-checkpoint.json",
                    "sha256": evidence_sha256(checkpoint_payload),
                    "commit": checkpoint_commit,
                }
            ],
            wave["checkpoints"][-1]["evidence"],
        )
        self.assertEqual("ADOPTED", amendment["lifecycle"]["status"])
        self.assertIsNone(data["control_plane"]["active_amendment"])

    def test_adopted_amendments_select_only_their_own_security_checkpoint(self) -> None:
        wave = {
            "checkpoints": [
                {
                    "id": "W1.CP01",
                    "kind": "security",
                    "evidence": [
                        {
                            "type": "amendment-adoption-evidence",
                            "amendment_id": "W1.A02",
                            "path": "artifacts/evidence/W1.A02.adoption.json",
                        }
                    ],
                },
                {
                    "id": "W1.CP02",
                    "kind": "security",
                    "evidence": [
                        {
                            "type": "amendment-adoption-evidence",
                            "amendment_id": "W1.A03",
                            "path": "artifacts/evidence/W1.A03.adoption.json",
                        }
                    ],
                },
                {
                    "id": "W1.CP03",
                    "kind": "risk-cluster",
                    "evidence": [
                        {
                            "type": "amendment-adoption-evidence",
                            "amendment_id": "W1.A02",
                            "path": "artifacts/evidence/not-a-security-checkpoint.json",
                        }
                    ],
                },
            ]
        }

        self.assertEqual(
            ["W1.CP01"],
            [item["id"] for item in taskctl_module.amendment_adoption_checkpoints(wave, "W1.A02")],
        )
        self.assertEqual(
            ["W1.CP02"],
            [item["id"] for item in taskctl_module.amendment_adoption_checkpoints(wave, "W1.A03")],
        )
        self.assertEqual([], taskctl_module.amendment_adoption_checkpoints(wave, "W1.A04"))

    def test_consecutive_adopted_amendments_validate_against_their_own_checkpoints(self) -> None:
        data = taskctl_module.historical_backlog_document(
            REPO,
            "c9ef5be1faf0119562b036c2b5eed882fab08b24",
        )
        self.assertIsNotNone(data)
        assert data is not None
        amendment = taskctl_module.wave_amendment_map(data)["W1.A03"]
        amendment["lifecycle"]["status"] = "ADOPTED"
        amendment["lifecycle"]["history"].append(
            {
                "id": f"E{len(amendment['lifecycle']['history']) + 1:02d}",
                "status": "ADOPTED",
                "actor": "codex",
                "at": "2026-08-22T21:00:00+00:00",
                "rationale": "Projected consecutive-amendment adoption.",
            }
        )
        amendment["campaign"].update(status="COMPLETE", lease=None)
        data["control_plane"]["active_amendment"] = None
        wave = taskctl_module.wave_map(data)["W1"]
        wave["campaign"]["scope"] = "wave"
        adoption_commit = "fb8bec15e0b02e521955269beabd7eb5a912d756"
        adoption_path = "artifacts/evidence/W1.A03.adoption.json"
        adoption_payload = taskctl_module.git_blob(REPO, adoption_commit, adoption_path)
        self.assertIsNotNone(adoption_payload)
        assert adoption_payload is not None
        wave["checkpoints"].append(
            {
                "id": f"W1.CP{len(wave['checkpoints']) + 1:02d}",
                "kind": "security",
                "recorded_by": "codex",
                "recorded_at": "2026-08-22T21:00:00+00:00",
                "evidence": [
                    {
                        "type": "amendment-adoption-evidence",
                        "amendment_id": "W1.A03",
                        "path": adoption_path,
                        "sha256": hashlib.sha256(adoption_payload).hexdigest(),
                        "commit": adoption_commit,
                    }
                ],
                "notes": "Projected W1.A03 adoption checkpoint.",
            }
        )

        self.assertEqual([], taskctl_module.validate(*taskctl_module.index_backlog(data), repo=REPO))

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
                "--from",
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
                "--from",
                "exit-review.json",
                "--note",
                "approved",
            ],
            [
                "amendment",
                "adopt",
                "W1.A02",
                "--agent",
                "alice",
                "--from",
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
