from __future__ import annotations

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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from planctl import (  # noqa: E402
    _approval_introduction_commit,
    _authority_chain_v4_errors,
    _schema_errors,
    _v4_packet_review_errors,
    approve_ecr,
    ecr_validation_errors,
    load_backlog,
)


class PlanctlAmendmentTests(unittest.TestCase):
    def _post_migration_v4_packet(self) -> dict[str, Any]:
        predecessor = json.loads(
            (REPO / "planning/enabler-change-requests/ECR-0003.packet.json").read_text(encoding="utf-8")
        )
        reserved_approval_path = REPO / "planning/wave-amendment-approvals/W1.A04.json"
        reserved_approval = json.loads(reserved_approval_path.read_text(encoding="utf-8"))
        migration_path = REPO / "planning/governance-migrations/GOV-MIG-0001.json"
        migration_relative = migration_path.relative_to(REPO).as_posix()
        migration_commit = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", migration_relative],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        migration = {
            "id": "GOV-MIG-0001",
            "path": migration_relative,
            "sha256": hashlib.sha256(migration_path.read_bytes()).hexdigest(),
            "commit": migration_commit,
        }
        experience_path = REPO / "design/ui-reference/project-settings.html"
        tasks = [f"W1.A05.T{index:02d}" for index in range(1, 5)]
        bootstrap = "W1.A05.B00"
        scale = {"S": 1, "M": 3, "L": 5}
        baseline_commit = predecessor["authorityChain"]["waveBase"]["packetCommit"]
        baseline_backlog = yaml.safe_load(
            subprocess.check_output(["git", "show", f"{baseline_commit}:planning/backlog.yaml"], cwd=REPO).decode(
                "utf-8"
            )
        )
        baseline_tasks = [
            {"id": task["id"], "estimate": task["estimate"], "points": scale[task["estimate"]]}
            for capability in baseline_backlog["capabilities"]
            for slice_ in capability["slices"]
            if slice_.get("wave") == "W1"
            for task in slice_["tasks"]
        ]
        return {
            "$schema": "./enabler-change-request.v4.schema.json",
            "schemaVersion": "4.0-proposal",
            "documentType": "enabler-change-request-packet",
            "changeRequestId": "ECR-0004",
            "proposedAmendmentId": "W1.A05",
            "targetWave": "W1",
            "status": "pending-approval",
            "executionState": "non-executable",
            "classification": "product-scope-security-experience",
            "authorityChain": {
                "waveBase": predecessor["authorityChain"]["waveBase"],
                "orderedAmendments": predecessor["authorityChain"]["orderedAmendments"],
                "reservedAmendments": [
                    {
                        "id": "W1.A04",
                        "changeRequestId": "ECR-0003",
                        "status": "APPROVED_UNMATERIALIZED_SUPERSEDED",
                        "packetCommit": reserved_approval["packet"]["commit"],
                        "approvalReference": {
                            "path": reserved_approval_path.relative_to(REPO).as_posix(),
                            "sha256": hashlib.sha256(reserved_approval_path.read_bytes()).hexdigest(),
                            "introductionCommit": _approval_introduction_commit(
                                REPO, reserved_approval_path.relative_to(REPO).as_posix()
                            ),
                        },
                        "supersededByMigration": migration,
                    }
                ],
            },
            "migrationAuthority": migration,
            "activationBoundary": {
                "waveStatus": "PAUSED",
                "ordinaryTaskStatesDenied": ["IN_PROGRESS", "REVIEW"],
                "reviewCandidateMutationDenied": True,
                "otherEnablerCampaignDenied": True,
                "activeRecoveryHolds": [],
            },
            "bootstrapUnit": {
                "id": bootstrap,
                "kind": "append-only-amendment-bootstrap",
                "exceptionReason": "Install generic post-migration materialization support after approval.",
                "authorizedPaths": ["tools/taskctl.py"],
                "requiredOutcomes": ["Preserve predecessor authority and materialize only the exact packet."],
                "prohibitedOutcomes": ["No product implementation or Wave resume."],
            },
            "sliceContributions": [
                {
                    "id": "W1.A05.S01",
                    "capabilityId": "CAP-02",
                    "title": "Authentication-provider refactor",
                    "objective": "Separate provider-neutral lock state from native verification adapters.",
                    "workType": "mixed-refactor-and-new",
                    "refactorTaskIds": [tasks[0]],
                    "taskIds": tasks[:2],
                    "acceptanceCriteria": ["Existing behavior remains available behind a provider boundary."],
                },
                {
                    "id": "W1.A05.S02",
                    "capabilityId": "CAP-02",
                    "title": "Configurable local sign-in",
                    "objective": "Offer no login, password, and Windows Hello modes.",
                    "workType": "new-product-work",
                    "refactorTaskIds": [],
                    "taskIds": tasks[2:],
                    "acceptanceCriteria": ["No login is the explicit default."],
                },
            ],
            "authorizedTaskIds": tasks,
            "taskInventory": [
                {
                    "id": task_id,
                    "title": f"Task {position}",
                    "objective": "Bounded implementation objective.",
                    "estimate": estimate,
                    "dependencies": [bootstrap],
                    "acceptanceCriteria": ["Criterion-linked evidence is required."],
                    "verification": ["Run affected deterministic checks."],
                }
                for position, (task_id, estimate) in enumerate(zip(tasks, ["L", "L", "M", "L"], strict=True), start=1)
            ],
            "refactorBudget": {
                "baseline": {
                    "waveId": "W1",
                    "sourceCommit": baseline_commit,
                    "sourcePath": "planning/backlog.yaml",
                    "estimateScale": scale,
                    "tasks": baseline_tasks,
                    "totalPoints": sum(item["points"] for item in baseline_tasks),
                },
                "refactorAllocations": [{"taskId": tasks[0], "estimate": "L", "points": 5}],
                "refactorPoints": 5,
                "refactorSharePercent": 2.6,
                "limitPolicy": {"mode": "standard-15-percent", "limitPercent": 15},
                "refactorTaskIds": [tasks[0]],
                "method": "Existing W1 estimate points with M=3 and L=5.",
            },
            "governedExperience": {
                "referenceId": "fixture-reference",
                "approvalRequired": True,
                "files": [
                    {
                        "path": experience_path.relative_to(REPO).as_posix(),
                        "sha256": hashlib.sha256(experience_path.read_bytes()).hexdigest(),
                    }
                ],
            },
            "acceptanceCriteria": ["Exact product authority remains non-executable before approval."],
            "verificationObligations": ["Independently review the exact packet commit."],
            "rollback": ["Reject or withdraw the inert packet before approval."],
            "nonGoals": ["No release gate, remote action, or product implementation."],
            "files": [
                {
                    "path": "planning/enabler-change-requests/ECR-0004.md",
                    "sha256": "a" * 64,
                    "role": "canonical-proposal",
                },
                {
                    "path": "planning/enabler-change-requests/enabler-change-request.v4.schema.json",
                    "sha256": "b" * 64,
                    "role": "proposal-schema",
                },
                {
                    "path": "planning/enabler-change-requests/ECR-0004-review.html",
                    "sha256": "c" * 64,
                    "role": "human-review",
                },
            ],
        }

    def _copy_ecr_fixture(self, root: Path, *, include_approval: bool) -> Path:
        shutil.copytree(
            REPO / "planning" / "enabler-change-requests",
            root / "planning" / "enabler-change-requests",
        )
        approvals = root / "planning" / "wave-amendment-approvals"
        approvals.mkdir(parents=True)
        shutil.copy2(
            REPO / "planning" / "wave-amendment-approvals" / "wave-amendment-approval.schema.json",
            approvals / "wave-amendment-approval.schema.json",
        )
        shutil.copy2(
            REPO / "planning" / "wave-amendment-approvals" / "W1.A01.json",
            approvals / "W1.A01.json",
        )
        draft = root / "approval-draft.json"
        shutil.copy2(REPO / "planning" / "wave-amendment-approvals" / "W1.A02.json", draft)
        if include_approval:
            shutil.copy2(draft, approvals / "W1.A02.json")
        return draft

    def test_repository_ecr_approval_is_exact_commit_and_history_bound(self) -> None:
        self.assertEqual([], ecr_validation_errors(REPO, "ECR-0001", require_approved=True))

    def test_post_migration_v4_packet_preserves_reserved_authority_and_slice_budget(self) -> None:
        packet = self._post_migration_v4_packet()
        schema = REPO / "planning/enabler-change-requests/enabler-change-request.v4.schema.json"
        self.assertEqual([], _schema_errors(packet, schema, "ECR v4 fixture"))
        self.assertEqual([], _authority_chain_v4_errors(REPO, packet))

        backlog, _ = load_backlog(REPO)
        pre_bootstrap = copy.deepcopy(backlog)
        pre_bootstrap["wave_amendments"] = [
            item for item in pre_bootstrap["wave_amendments"] if item["id"] not in {"W1.A04", "W1.A05"}
        ]
        with patch("planctl.load_backlog", return_value=(pre_bootstrap, REPO / "planning/backlog.yaml")):
            self.assertEqual([], _authority_chain_v4_errors(REPO, packet))

        altered_terminal = copy.deepcopy(backlog)
        reserved = next(item for item in altered_terminal["wave_amendments"] if item["id"] == "W1.A04")
        reserved["lifecycle"]["status"] = "ADOPTED"
        with patch("planctl.load_backlog", return_value=(altered_terminal, REPO / "planning/backlog.yaml")):
            self.assertTrue(
                any("terminal migration materialization" in error for error in _authority_chain_v4_errors(REPO, packet))
            )

        partial_append = copy.deepcopy(backlog)
        partial_append["wave_amendments"] = [
            item for item in partial_append["wave_amendments"] if item["id"] != "W1.A05"
        ]
        with patch("planctl.load_backlog", return_value=(partial_append, REPO / "planning/backlog.yaml")):
            self.assertTrue(any("predecessor chain" in error for error in _authority_chain_v4_errors(REPO, packet)))

        tampered = copy.deepcopy(packet)
        tampered["authorityChain"]["reservedAmendments"][0]["approvalReference"]["sha256"] = "0" * 64
        self.assertTrue(any("reserved authority" in error for error in _authority_chain_v4_errors(REPO, tampered)))

        substituted_intro = copy.deepcopy(packet)
        substituted_intro["authorityChain"]["reservedAmendments"][0]["approvalReference"]["introductionCommit"] = (
            packet["migrationAuthority"]["commit"]
        )
        self.assertTrue(
            any("introduction blob" in error for error in _authority_chain_v4_errors(REPO, substituted_intro))
        )

        substituted_migration = copy.deepcopy(packet)
        substituted_migration["migrationAuthority"]["commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
        substituted_migration["authorityChain"]["reservedAmendments"][0]["supersededByMigration"] = copy.deepcopy(
            substituted_migration["migrationAuthority"]
        )
        self.assertTrue(
            any(
                "exact adopted file commit" in error
                for error in _authority_chain_v4_errors(REPO, substituted_migration)
            )
        )

        substituted_effective_state = copy.deepcopy(packet)
        substituted_effective_state["authorityChain"]["orderedAmendments"][0]["effectiveStateCommit"] = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        )
        self.assertTrue(
            any(
                "exact ADOPTED transition" in error
                for error in _authority_chain_v4_errors(REPO, substituted_effective_state)
            )
        )

        over_budget = copy.deepcopy(packet)
        over_budget["refactorBudget"]["refactorPoints"] = 40
        over_budget["refactorBudget"]["refactorSharePercent"] = 20.6
        self.assertTrue(any("refactor budget" in error for error in _authority_chain_v4_errors(REPO, over_budget)))

        inflated = copy.deepcopy(packet)
        inflated["refactorBudget"]["baseline"]["totalPoints"] = 1_000_000_000
        inflated["refactorBudget"]["refactorSharePercent"] = 0.0
        self.assertTrue(any("refactor baseline" in error for error in _authority_chain_v4_errors(REPO, inflated)))

        omitted_allocation = copy.deepcopy(packet)
        omitted_allocation["refactorBudget"]["refactorAllocations"] = []
        self.assertTrue(
            any("refactor budget" in error for error in _authority_chain_v4_errors(REPO, omitted_allocation))
        )

        non_finite = copy.deepcopy(packet)
        non_finite["refactorBudget"]["refactorPoints"] = float("inf")
        self.assertTrue(any("refactor budget" in error for error in _authority_chain_v4_errors(REPO, non_finite)))

        directed_exception = copy.deepcopy(packet)
        directed_exception["refactorBudget"]["limitPolicy"] = {
            "mode": "owner-directed-wave-exception",
            "authorizedBy": "repository-owner",
            "authorization": "Complete this authentication refactor within W1 without applying the 15% cap.",
            "scopeTaskIds": ["W1.A05.T01"],
            "rationale": "The provider boundary is necessary to deliver the requested login modes coherently.",
        }
        self.assertEqual([], _authority_chain_v4_errors(REPO, directed_exception))

        overbroad_exception = copy.deepcopy(directed_exception)
        overbroad_exception["refactorBudget"]["limitPolicy"]["scopeTaskIds"] = ["W1.A05.T02"]
        self.assertTrue(
            any("refactor budget" in error for error in _authority_chain_v4_errors(REPO, overbroad_exception))
        )

    def test_v4_schema_allows_truthful_empty_predecessor_and_reservation_sets(self) -> None:
        packet = self._post_migration_v4_packet()
        packet["authorityChain"]["orderedAmendments"] = []
        packet["authorityChain"]["reservedAmendments"] = []
        schema = REPO / "planning/enabler-change-requests/enabler-change-request.v4.schema.json"
        self.assertEqual([], _schema_errors(packet, schema, "empty-history ECR v4 fixture"))

    def test_v4_change_request_identity_is_repository_global(self) -> None:
        packet = self._post_migration_v4_packet()
        packet["changeRequestId"] = "ECR-0001"
        self.assertTrue(
            any("repository-global namespace" in error for error in _authority_chain_v4_errors(REPO, packet))
        )

    def test_v4_approval_denies_an_invented_review_projection_without_ledger(self) -> None:
        packet = self._post_migration_v4_packet()
        record = {
            "approvedBy": "repository-owner",
            "packet": {"commit": "f" * 40, "sha256": "a" * 64},
            "independentPacketReview": {
                "reviewer": "invented-independent-reviewer",
                "candidateCommit": "f" * 40,
                "result": "APPROVED",
                "attemptId": "R01",
                "findingIdsClosed": [],
            },
        }
        errors = _v4_packet_review_errors(REPO, packet, record)
        self.assertTrue(any("review ledger" in error for error in errors), errors)

    def test_committed_approval_rewrite_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy_ecr_fixture(root, include_approval=True)
            approval_path = root / "planning" / "wave-amendment-approvals" / "W1.A02.json"
            introduced_payload = approval_path.read_bytes()
            record = json.loads(introduced_payload)
            record["decision"] = "Rewritten after approval."
            approval_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

            def fake_blob(_root: Path, _commit: str, relative: str) -> bytes | None:
                if relative == "planning/wave-amendment-approvals/W1.A02.json":
                    return introduced_payload
                path = root.joinpath(*Path(relative).parts)
                return path.read_bytes() if path.exists() else None

            with (
                patch("planctl._authority_history_errors", return_value=[]),
                patch("planctl._git_commit_exists", return_value=True),
                patch("planctl._git_is_ancestor", return_value=True),
                patch("planctl._approval_introduction_commit", return_value="6" * 40),
                patch("planctl._git_blob", side_effect=fake_blob),
            ):
                errors = ecr_validation_errors(root, "ECR-0001", require_approved=True)

            self.assertTrue(any("changed after its introduction commit" in error for error in errors), errors)

    def test_future_approval_is_exclusive_create_and_duplicate_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = self._copy_ecr_fixture(root, include_approval=False)
            packet_commit = "57d73bcf314ea6aab38b8056ead118d6ef270921"

            def fake_blob(_root: Path, _commit: str, relative: str) -> bytes | None:
                path = root.joinpath(*Path(relative).parts)
                return path.read_bytes() if path.exists() else None

            def fake_run(command, **_kwargs):
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(command, 0, stdout=packet_commit + "\n", stderr="")
                if command[:3] == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                raise AssertionError(f"unexpected subprocess: {command}")

            with (
                patch("planctl._authority_history_errors", return_value=[]),
                patch("planctl._git_commit_exists", return_value=True),
                patch("planctl._git_blob", side_effect=fake_blob),
                patch("planctl.subprocess.run", side_effect=fake_run),
            ):
                destination = approve_ecr(
                    root,
                    "ECR-0001",
                    record_path=draft,
                    approver="repository-owner",
                    commit=packet_commit,
                )
                created = destination.read_bytes()
                with self.assertRaisesRegex(ValueError, "duplicate approval is forbidden"):
                    approve_ecr(
                        root,
                        "ECR-0001",
                        record_path=draft,
                        approver="repository-owner",
                        commit=packet_commit,
                    )

            self.assertEqual(draft.read_bytes(), created)
            self.assertEqual(created, destination.read_bytes())

    def test_approved_validation_rejects_missing_append_only_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy_ecr_fixture(root, include_approval=False)
            with patch("planctl._authority_history_errors", return_value=[]):
                errors = ecr_validation_errors(root, "ECR-0001", require_approved=True)
            self.assertIn(
                "ECR has no immutable approval record: planning/wave-amendment-approvals/W1.A02.json",
                errors,
            )


if __name__ == "__main__":
    unittest.main()
