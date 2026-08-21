from __future__ import annotations

import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from backlog_views import render_plan, render_summary, task_review_markdown  # noqa: E402
from plan_review_check import (  # noqa: E402
    main as check_review_site,
)
from plan_review_check import (  # noqa: E402
    task_review_manifest_errors,
    task_review_render_errors,
)
from plan_review_site import (  # noqa: E402
    build_site,
    load_enabler_change_requests,
    task_review_history_html,
    task_review_projection,
)


def controlled_review_task() -> dict[str, Any]:
    def evidence_reference(commit: str, suffix: str) -> dict[str, Any]:
        return {
            "type": "criterion-manifest",
            "path": f"artifacts/evidence/TEST.T01.{suffix}.json",
            "sha256": suffix * 64,
            "commit": commit,
            "recorded_at": "2026-08-21T01:00:00Z",
        }

    def packet(
        attempt_id: str,
        *,
        candidate: str,
        base: str,
        packet_hash: str,
        evidence_hash_character: str,
        prior: str | None,
        open_ids: list[str],
    ) -> dict[str, Any]:
        reference = evidence_reference(candidate, evidence_hash_character)
        return {
            "id": attempt_id,
            "submitted_by": "codex",
            "submitted_at": "2026-08-21T01:00:00Z",
            "candidate_commit": candidate,
            "base_commit": base,
            "branch": "codex/w1-windows-local-runtime",
            "evidence_reference": reference,
            "acceptance_criteria_sha256": "a" * 64,
            "changed_paths": ["tools/example.py"],
            "selected_checks": ["python -m unittest tests.foundation.test_example"],
            "deferred_checks": ["Wave-exit full profile"],
            "selection_rationale": "Focused control change; full profile remains at Wave exit.",
            "selection_sha256": "b" * 64,
            "prior_attempt_id": prior,
            "open_finding_ids": open_ids,
            "root_cause_analysis": None,
            "packet_sha256": packet_hash,
        }

    first_commit = "1" * 40
    second_commit = "2" * 40
    first_packet = packet(
        "R01",
        candidate=first_commit,
        base="0" * 40,
        packet_hash="c" * 64,
        evidence_hash_character="d",
        prior=None,
        open_ids=[],
    )
    second_packet = packet(
        "R02",
        candidate=second_commit,
        base=first_commit,
        packet_hash="e" * 64,
        evidence_hash_character="f",
        prior="R01",
        open_ids=["F01"],
    )
    approved_review = {
        "reviewer": "independent-reviewer",
        "result": "approved",
        "reviewed_at": "2026-08-21T02:00:00Z",
        "notes": "F01 is explicitly closed.",
    }
    return {
        "id": "W1.A02.T99",
        "title": "Synthetic controlled review",
        "status": "DONE",
        "review": approved_review,
        "review_control": {
            "version": 1,
            "attempts": [
                {
                    "submission": first_packet,
                    "review": {
                        "reviewer": "independent-reviewer",
                        "result": "changes-requested",
                        "reviewed_at": "2026-08-21T01:30:00Z",
                        "notes": "F01 blocks approval.",
                    },
                    "ledger": {"path": "artifacts/evidence/TEST.T01.R01-review.json", "sha256": "1" * 64},
                    "findings": [
                        {
                            "id": "F01",
                            "severity": "high",
                            "blocking": True,
                            "criterion_index": 1,
                            "title": "History is flattened",
                            "reproduction": "Generate the view after remediation.",
                            "required_remediation": "Retain R01 beside R02.",
                        }
                    ],
                    "closures": [],
                },
                {
                    "submission": second_packet,
                    "review": approved_review,
                    "ledger": {"path": "artifacts/evidence/TEST.T01.R02-review.json", "sha256": "2" * 64},
                    "findings": [],
                    "closures": [
                        {
                            "finding_id": "F01",
                            "disposition": "fixed",
                            "evidence": "R02 retains both immutable rounds.",
                        }
                    ],
                },
            ],
            "current_submission": None,
        },
    }


class PlanReviewAmendmentTests(unittest.TestCase):
    temporary: ClassVar[tempfile.TemporaryDirectory[str]]
    site: ClassVar[Path]
    manifest: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.site = Path(cls.temporary.name) / "review-site"
        cls.manifest = build_site(REPO, cls.site)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_ecr_register_preserves_states_and_wave_authority(self) -> None:
        entry = next(
            item for item in self.manifest["enabler_change_requests"] if item["change_request_id"] == "ECR-0001"
        )
        backlog = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        amendment = next(
            (item for item in backlog.get("wave_amendments", []) if item.get("id") == "W1.A02"),
            None,
        )
        expected_lifecycle = ((amendment or {}).get("lifecycle") or {}).get("status") or "NOT_MATERIALIZED"
        expected_bootstrap = ((amendment or {}).get("bootstrap") or {}).get("status") or "NOT_SUBMITTED"
        expected_campaign = ((amendment or {}).get("campaign") or {}).get("status") or "NONE"
        self.assertEqual("APPROVED", entry["approval_status"])
        self.assertEqual(expected_lifecycle, entry["lifecycle_status"])
        self.assertEqual(expected_bootstrap, entry["bootstrap_status"])
        self.assertEqual(expected_campaign, entry["campaign_status"])
        if amendment and amendment.get("bootstrap"):
            self.assertEqual(
                f"R{len(entry['bootstrap_attempts']):02d}",
                entry["bootstrap_attempts"][-1]["id"],
            )
        self.assertEqual(
            "9ed06e76ea09f069cf58fa0f55bfb130797b791b328e4bb24b69ce12dc3ac1aa",
            entry["packet_sha256"],
        )
        self.assertEqual(
            ["docs/planning-implementation-plan.md"],
            entry["scope_addenda"][0]["authorized_additional_paths"],
        )

        register = (self.site / "enablers/index.html").read_text(encoding="utf-8")
        detail = (self.site / "enablers/ECR-0001.html").read_text(encoding="utf-8")
        self.assertIn("Enabler change request register", register)
        for marker in (
            "Proposal, approval, materialization, and campaign state",
            "Hash-bound source records",
            "Append-only bootstrap scope addenda",
            "Append-only bootstrap review attempts",
            "docs/planning-implementation-plan.md",
            "W1 base approval",
            "W1.A01",
            "W1.A02",
            "Safe resume boundary",
        ):
            self.assertIn(marker, detail)

    def test_interrupted_approved_wave_suppresses_repeat_commands_but_future_wave_keeps_approval(self) -> None:
        wave_one = (self.site / "waves/W1.html").read_text(encoding="utf-8")
        self.assertIn("W1 ordinary execution is interrupted", wave_one)
        self.assertIn("../enablers/ECR-0001.html", wave_one)
        self.assertIn("Exact ordinary resume condition", wave_one)
        self.assertNotIn("wave approve W1", wave_one)
        self.assertNotIn("wave start W1", wave_one)

        wave_two = (self.site / "waves/W2.html").read_text(encoding="utf-8")
        self.assertIn("wave approve W2", wave_two)
        self.assertIn("Approval command after review", wave_two)

    def test_review_checker_validates_enabler_hashes_pages_and_links(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "plan_review_check.py",
                "--repo",
                str(REPO),
                "--site",
                str(self.site),
            ],
        ):
            self.assertEqual(0, check_review_site())

    def test_ecr_loader_fails_closed_when_declared_source_bytes_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(
                REPO / "planning/enabler-change-requests",
                root / "planning/enabler-change-requests",
            )
            approvals = root / "planning/wave-amendment-approvals"
            approvals.mkdir(parents=True)
            shutil.copy2(
                REPO / "planning/wave-amendment-approvals/W1.A02.json",
                approvals / "W1.A02.json",
            )
            proposal = root / "planning/enabler-change-requests/ECR-0001.md"
            proposal.write_text(proposal.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "declared source hash mismatch"):
                load_enabler_change_requests(root, {})

    def test_controlled_review_history_renders_rounds_findings_closures_hashes_and_projection(self) -> None:
        task = controlled_review_task()
        rendered = task_review_history_html(task)
        projection = task_review_projection(task)
        markdown = "\n".join(task_review_markdown(task, heading_level=4))

        self.assertEqual([], task_review_render_errors(rendered, projection))
        self.assertFalse([line for line in rendered.splitlines() if line.rstrip() != line])
        for marker in (
            "changes-requested",
            "approved",
            "F01",
            "fixed",
            "c" * 64,
            "e" * 64,
            "1" * 64,
            "2" * 64,
            "Current latest-review projection",
        ):
            self.assertIn(marker, rendered)
            self.assertIn(marker, markdown)
        self.assertIn("Review round R01", rendered)
        self.assertIn("Review round R02", rendered)
        self.assertIn("Round R01", markdown)
        self.assertIn("Round R02", markdown)
        self.assertLess(rendered.index("Review round R01"), rendered.index("Review round R02"))
        self.assertLess(markdown.index("Round R01"), markdown.index("Round R02"))

    def test_review_render_checker_rejects_flattened_round_hash_and_closure(self) -> None:
        task = controlled_review_task()
        rendered = task_review_history_html(task)
        projection = task_review_projection(task)

        without_first_round = rendered.replace('data-review-attempt="W1.A02.T99:R01"', "", 1)
        self.assertTrue(
            any(
                "round count" in error or "R01" in error
                for error in task_review_render_errors(without_first_round, projection)
            )
        )
        altered_hash = rendered.replace("c" * 64, "9" * 64)
        self.assertTrue(
            any("R01" in error and "hash" in error for error in task_review_render_errors(altered_hash, projection))
        )
        without_closure = rendered.replace('data-review-closure="W1.A02.T99:R02:F01"', "", 1)
        self.assertTrue(any("closure" in error for error in task_review_render_errors(without_closure, projection)))

        manifest_projection = [task_review_projection(task)]
        self.assertEqual([], task_review_manifest_errors("synthetic", manifest_projection, [task]))
        flattened_projection = [dict(manifest_projection[0])]
        flattened_projection[0]["review_control"] = {
            **manifest_projection[0]["review_control"],
            "attempts": manifest_projection[0]["review_control"]["attempts"][1:],
        }
        self.assertTrue(task_review_manifest_errors("synthetic", flattened_projection, [task]))

    def test_legacy_latest_review_is_labeled_without_fabricated_rounds(self) -> None:
        task = {
            "id": "CAP-02.S04.T01",
            "title": "Legacy reviewed task",
            "status": "DONE",
            "review": {
                "reviewer": "legacy-independent-reviewer",
                "result": "approved",
                "reviewed_at": "2026-08-18T00:00:00Z",
                "notes": "Latest historical projection only.",
            },
        }
        rendered = task_review_history_html(task)
        projection = task_review_projection(task)
        markdown = "\n".join(task_review_markdown(task, heading_level=4))

        self.assertEqual([], task_review_render_errors(rendered, projection))
        self.assertIn("Legacy latest-review-only projection", rendered)
        self.assertIn("legacy latest-review-only projection", markdown)
        self.assertIn("Latest historical projection only.", rendered)
        self.assertNotIn("data-review-attempt", rendered)
        self.assertNotIn("Round R01", markdown)

    def test_current_submission_is_distinct_from_completed_rounds_and_latest_projection(self) -> None:
        task = controlled_review_task()
        current = copy.deepcopy(task["review_control"]["attempts"][-1]["submission"])
        current.update(
            id="R03",
            candidate_commit="3" * 40,
            base_commit="2" * 40,
            prior_attempt_id="R02",
            packet_sha256="3" * 64,
        )
        current["evidence_reference"].update(
            path="artifacts/evidence/TEST.T01.current.json",
            sha256="4" * 64,
            commit="3" * 40,
        )
        task["status"] = "REVIEW"
        task["review_control"]["current_submission"] = current
        projection = task_review_projection(task)
        rendered = task_review_history_html(task)

        self.assertEqual([], task_review_render_errors(rendered, projection))
        self.assertFalse([line for line in rendered.splitlines() if line.rstrip() != line])
        self.assertIn('data-current-submission="W1.A02.T99:R03"', rendered)
        self.assertIn("Current immutable submission awaiting review", rendered)
        self.assertIn("Current latest-review projection", rendered)
        flattened = rendered.replace('data-current-submission="W1.A02.T99:R03"', "", 1)
        self.assertTrue(
            any("current immutable submission" in error for error in task_review_render_errors(flattened, projection))
        )

    def test_backlog_views_render_base_amendment_and_bounded_task_separately(self) -> None:
        data = {
            "plan": {"title": "Plan"},
            "status_definitions": {"NOT_STARTED": "not started"},
            "waves": [
                {
                    "id": "W1",
                    "title": "Wave one",
                    "track": "local",
                    "approval": {"status": "APPROVED"},
                    "campaign": {"status": "PAUSED"},
                    "completion": {"status": "PAUSED"},
                }
            ],
            "release_gates": [],
            "capabilities": [],
            "wave_approval_bases": [
                {
                    "wave_id": "W1",
                    "packet_commit": "1" * 40,
                    "record_commit": "2" * 40,
                }
            ],
            "wave_amendments": [
                {
                    "id": "W1.A02",
                    "change_request_id": "ECR-0001",
                    "target_wave": "W1",
                    "kind": "gate-integrity-safety-defect",
                    "approval_reference": {"path": "planning/wave-amendment-approvals/W1.A02.json", "sha256": "3" * 64},
                    "lifecycle": {
                        "status": "MATERIALIZED",
                        "history": [
                            {
                                "id": "E01",
                                "status": "APPROVED",
                                "actor": "repository-owner",
                                "at": "2026-08-20T00:00:00Z",
                                "rationale": "Approved exact scope",
                            }
                        ],
                    },
                    "bootstrap": {"status": "APPROVED"},
                    "campaign": None,
                    "completion": {"status": "PENDING"},
                    "tasks": [
                        {
                            "id": "W1.A02.T01",
                            "title": "Immutable reviews",
                            "objective": "Preserve history",
                            "dependencies": ["W1.A02.B00"],
                            "acceptance_criteria": ["History is append-only"],
                            "verification_commands": ["python -m unittest"],
                            "status": "NOT_STARTED",
                            "review": {},
                        }
                    ],
                }
            ],
        }
        summary = render_summary(data, "4" * 64)
        plan = render_plan(data, "4" * 64)
        self.assertIn("Wave authority and append-only amendments", summary)
        self.assertIn("`W1.A02`", summary)
        self.assertIn("`MATERIALIZED`", summary)
        self.assertIn("# Enabler change requests and Wave amendments", plan)
        self.assertIn("ECR-0001", plan)
        self.assertIn("W1.A02.T01", plan)


if __name__ == "__main__":
    unittest.main()
