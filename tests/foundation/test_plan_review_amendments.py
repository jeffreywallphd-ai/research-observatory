from __future__ import annotations

import copy
import re
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

from backlog_views import (  # noqa: E402
    amendment_exit_review_markdown,
    render_plan,
    render_summary,
    task_review_markdown,
)
from plan_review_check import (  # noqa: E402
    amendment_exit_manifest_errors,
    amendment_exit_render_errors,
    task_review_manifest_errors,
    task_review_render_errors,
)
from plan_review_check import (  # noqa: E402
    main as check_review_site,
)
from plan_review_site import (  # noqa: E402
    amendment_adoption_checkpoints,
    amendment_exit_projection,
    amendment_exit_review_html,
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


def controlled_exit_amendment() -> dict[str, Any]:
    def packet(
        attempt_id: str,
        *,
        candidate: str,
        packet_hash: str,
        evidence_hash: str,
        prior: str | None,
        open_ids: list[str],
    ) -> dict[str, Any]:
        return {
            "id": attempt_id,
            "submitted_by": "codex",
            "submitted_at": "2026-08-21T04:00:00Z",
            "candidate_commit": candidate,
            "declared_candidate_commit": candidate,
            "branch": "codex/w1-windows-local-runtime",
            "evidence_reference": {
                "type": "amendment-exit-evidence",
                "amendment_id": "W1.A02",
                "path": f"artifacts/evidence/W1.A02.exit-{attempt_id}.json",
                "sha256": evidence_hash,
                "commit": candidate,
            },
            "acceptance_criteria_sha256": "a" * 64,
            "selected_checks": ["python -m unittest tests.foundation.test_example"],
            "selected_checks_sha256": "b" * 64,
            "prior_attempt_id": prior,
            "open_finding_ids": open_ids,
            "packet_sha256": packet_hash,
        }

    first_packet = packet(
        "R01",
        candidate="1" * 40,
        packet_hash="c" * 64,
        evidence_hash="d" * 64,
        prior=None,
        open_ids=[],
    )
    second_packet = packet(
        "R02",
        candidate="2" * 40,
        packet_hash="e" * 64,
        evidence_hash="f" * 64,
        prior="R01",
        open_ids=["EF01"],
    )
    approved_review = {
        "reviewer": "exit-independent-reviewer",
        "result": "approved",
        "reviewed_at": "2026-08-21T05:00:00Z",
        "reviewed_state_commit": "4" * 40,
        "notes": "EF01 is closed without flattening R01.",
    }
    return {
        "id": "W1.A02",
        "change_request_id": "ECR-0001",
        "target_wave": "W1",
        "completion": {
            "status": "APPROVED",
            "reviewer": approved_review["reviewer"],
            "reviewed_at": approved_review["reviewed_at"],
            "evidence": ["artifacts/evidence/W1.A02.exit-R02.json"],
            "notes": approved_review["notes"],
            "exit_review_control": {
                "version": 1,
                "attempts": [
                    {
                        "submission": first_packet,
                        "review": {
                            "reviewer": "exit-independent-reviewer",
                            "result": "changes-requested",
                            "reviewed_at": "2026-08-21T04:30:00Z",
                            "reviewed_state_commit": "3" * 40,
                            "notes": "EF01 blocks exit approval.",
                        },
                        "ledger": {
                            "path": "artifacts/evidence/W1.A02.exit-review-R01.json",
                            "sha256": "1" * 64,
                        },
                        "findings": [
                            {
                                "id": "EF01",
                                "severity": "high",
                                "blocking": True,
                                "criterion_index": 1,
                                "title": "Exit history is flattened",
                                "reproduction": "Generate the amendment detail after remediation.",
                                "required_remediation": "Retain R01 beside R02.",
                            }
                        ],
                        "closures": [],
                    },
                    {
                        "submission": second_packet,
                        "review": approved_review,
                        "ledger": {
                            "path": "artifacts/evidence/W1.A02.exit-review-R02.json",
                            "sha256": "2" * 64,
                        },
                        "findings": [],
                        "closures": [
                            {
                                "finding_id": "EF01",
                                "disposition": "fixed",
                                "evidence": "R02 retains the complete exit-review history.",
                            }
                        ],
                    },
                ],
                "current_submission": None,
            },
        },
    }


def controlled_adoption_waves() -> list[dict[str, Any]]:
    return [
        {
            "id": "W1",
            "checkpoints": [
                {
                    "id": "W1.CP01",
                    "kind": "security",
                    "recorded_by": "codex",
                    "recorded_at": "2026-08-21T05:30:00Z",
                    "evidence": [
                        {
                            "type": "amendment-adoption-evidence",
                            "amendment_id": "W1.A02",
                            "path": "artifacts/evidence/W1.A02.adoption.json",
                            "sha256": "8" * 64,
                            "commit": "9" * 40,
                        },
                        {
                            "type": "amendment-adoption-evidence",
                            "amendment_id": "W1.A03",
                            "path": "artifacts/evidence/W1.A03.adoption.json",
                            "sha256": "7" * 64,
                            "commit": "6" * 40,
                        },
                    ],
                    "notes": "Adopted W1.A02 control-plane changes.",
                }
            ],
        }
    ]


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

    def test_pending_v2_ecr_renders_exact_authority_and_non_executable_state(self) -> None:
        entry = next(
            item for item in self.manifest["enabler_change_requests"] if item["change_request_id"] == "ECR-0002"
        )
        detail = (self.site / "enablers/ECR-0002.html").read_text(encoding="utf-8")
        authority_section = detail.split("<h2>Ordered Wave authority chain</h2>", 1)[1].split("</section>", 1)[0]

        self.assertEqual("PENDING", entry["approval_status"])
        for marker in (
            "W1 base approval",
            "594e63be501711d67d17a4aef176bb9b6a8748be",
            "901eb5c1351fa32c7173a5f0cebc2fdf9ddb1701",
            "W1.A01",
            "c5bbd97c0cdc665eecb973f5862478ef7be97752",
            "a20685b90532c60e0286e5e05f68b46c613e935d",
            "W1.A02",
            "57d73bcf314ea6aab38b8056ead118d6ef270921",
            "6e9c440102a5c463bb35d81f4dbdc3453d9ce029",
            "W1.A03",
            "Pending, non-executable proposal; no bootstrap/task authority",
        ):
            self.assertIn(marker, authority_section)
        self.assertNotIn("<code>missing</code>", authority_section)
        self.assertIn("No human approval is recorded", detail)
        self.assertIn("Proposed bounded inventory", detail)
        self.assertIn("completion and independent approval of the one task", detail)
        self.assertNotIn("both DONE", detail)
        self.assertFalse([line for line in detail.splitlines() if line.rstrip() != line])

        static_review = (REPO / "planning/enabler-change-requests/ECR-0002-review.html").read_text(encoding="utf-8")
        proposal = (REPO / "planning/enabler-change-requests/ECR-0002.md").read_text(encoding="utf-8")
        pointer = re.search(r"exact approval wording is in section ([0-9]+)", static_review, flags=re.IGNORECASE)
        self.assertIsNotNone(pointer)
        assert pointer is not None
        approval_heading = f"## {pointer.group(1)}. Exact approval and next condition"
        self.assertIn(approval_heading, proposal)
        approval_section = proposal.split(approval_heading, 1)[1]
        self.assertIn("Approve ECR-0002 as W1.A03 at packet commit", approval_section)

    def test_interrupted_approved_wave_suppresses_repeat_commands_but_future_wave_keeps_approval(self) -> None:
        wave_one = (self.site / "waves/W1.html").read_text(encoding="utf-8")
        self.assertIn("W1 ordinary execution is interrupted", wave_one)
        self.assertIn("../recoveries/GRR-0001.html", wave_one)
        self.assertIn("bootstrap-only", wave_one)
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

    def test_amendment_exit_history_and_bound_adoption_render_without_flattening(self) -> None:
        amendment = controlled_exit_amendment()
        waves = controlled_adoption_waves()
        projection = amendment_exit_projection(amendment)
        checkpoints = amendment_adoption_checkpoints(amendment, waves)
        rendered = amendment_exit_review_html(amendment, checkpoints)
        markdown = "\n".join(amendment_exit_review_markdown(amendment, waves, heading_level=3))

        self.assertEqual([], amendment_exit_render_errors(rendered, projection, checkpoints))
        self.assertEqual(
            [],
            amendment_exit_manifest_errors("synthetic", projection, checkpoints, amendment, waves),
        )
        self.assertFalse([line for line in rendered.splitlines() if line.rstrip() != line])
        for marker in (
            "EF01",
            "fixed",
            "3" * 40,
            "4" * 40,
            "d" * 64,
            "f" * 64,
            "1" * 64,
            "2" * 64,
            "W1.CP01",
            "8" * 64,
            "9" * 40,
            "Latest completion projection",
        ):
            self.assertIn(marker, rendered)
            self.assertIn(marker, markdown)
        self.assertIn("Amendment-exit review round R01", rendered)
        self.assertIn("Amendment-exit review round R02", rendered)
        self.assertIn("Exit round R01", markdown)
        self.assertIn("Exit round R02", markdown)
        self.assertNotIn("W1.A03.adoption.json", rendered)
        self.assertLess(rendered.index("review round R01"), rendered.index("review round R02"))
        self.assertLess(markdown.index("Exit round R01"), markdown.index("Exit round R02"))

    def test_amendment_exit_checker_rejects_omission_hash_drift_and_flattening(self) -> None:
        amendment = controlled_exit_amendment()
        waves = controlled_adoption_waves()
        projection = amendment_exit_projection(amendment)
        checkpoints = amendment_adoption_checkpoints(amendment, waves)
        rendered = amendment_exit_review_html(amendment, checkpoints)

        without_first_round = rendered.replace('data-exit-review-attempt="W1.A02:R01"', "", 1)
        self.assertTrue(
            any(
                "round count" in error or "R01" in error
                for error in amendment_exit_render_errors(without_first_round, projection, checkpoints)
            )
        )
        altered_exit_hash = rendered.replace("d" * 64, "0" * 64)
        self.assertTrue(
            any(
                "R01" in error and "hash" in error
                for error in amendment_exit_render_errors(altered_exit_hash, projection, checkpoints)
            )
        )
        without_closure = rendered.replace('data-exit-review-closure="W1.A02:R02:EF01"', "", 1)
        self.assertTrue(
            any("closure" in error for error in amendment_exit_render_errors(without_closure, projection, checkpoints))
        )
        altered_adoption_hash = rendered.replace("8" * 64, "0" * 64)
        self.assertTrue(
            any(
                "adoption" in error
                for error in amendment_exit_render_errors(altered_adoption_hash, projection, checkpoints)
            )
        )

        flattened = copy.deepcopy(projection)
        flattened["exit_review_control"]["attempts"] = flattened["exit_review_control"]["attempts"][1:]
        self.assertTrue(amendment_exit_manifest_errors("synthetic", flattened, checkpoints, amendment, waves))
        omitted_checkpoints: list[dict[str, Any]] = []
        self.assertTrue(amendment_exit_manifest_errors("synthetic", projection, omitted_checkpoints, amendment, waves))

    def test_amendment_exit_current_submission_is_distinct_from_completed_history(self) -> None:
        amendment = controlled_exit_amendment()
        current = copy.deepcopy(amendment["completion"]["exit_review_control"]["attempts"][-1]["submission"])
        current.update(
            id="R03",
            candidate_commit="5" * 40,
            declared_candidate_commit="5" * 40,
            prior_attempt_id="R02",
            packet_sha256="6" * 64,
        )
        current["evidence_reference"].update(
            path="artifacts/evidence/W1.A02.exit-R03.json",
            sha256="7" * 64,
            commit="5" * 40,
        )
        amendment["completion"]["status"] = "REVIEW"
        amendment["completion"]["exit_review_control"]["current_submission"] = current
        projection = amendment_exit_projection(amendment)
        rendered = amendment_exit_review_html(amendment, [])

        self.assertEqual([], amendment_exit_render_errors(rendered, projection, []))
        self.assertIn('data-exit-current-submission="W1.A02:R03"', rendered)
        self.assertIn("Current immutable exit submission awaiting review", rendered)
        self.assertIn("Latest completion projection", rendered)

    def test_legacy_amendment_completion_is_labeled_without_invented_exit_history(self) -> None:
        amendment = {
            "id": "W1.A01",
            "target_wave": "W1",
            "completion": {
                "status": "APPROVED",
                "reviewer": "repository-owner",
                "reviewed_at": "2026-08-20T23:38:52Z",
                "evidence": ["planning/wave-amendment-approvals/W1.A01.json"],
                "notes": "Historical authority migration only.",
            },
        }
        projection = amendment_exit_projection(amendment)
        rendered = amendment_exit_review_html(amendment, [])
        markdown = "\n".join(amendment_exit_review_markdown(amendment, [], heading_level=3))

        self.assertEqual([], amendment_exit_render_errors(rendered, projection, []))
        self.assertIn("Legacy latest-completion-only projection", rendered)
        self.assertIn("legacy latest-completion-only projection", markdown)
        self.assertIn("Historical authority migration only.", rendered)
        self.assertNotIn("data-exit-review-attempt", rendered)
        self.assertNotIn("Exit round R01", markdown)

    def test_backlog_views_render_base_amendment_and_bounded_task_separately(self) -> None:
        exit_amendment = controlled_exit_amendment()
        adoption_wave = controlled_adoption_waves()[0]
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
                    "checkpoints": adoption_wave["checkpoints"],
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
                    "completion": exit_amendment["completion"],
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
        for marker in (
            "Exit round R01",
            "Exit round R02",
            "EF01",
            "W1.CP01",
            "8" * 64,
        ):
            self.assertIn(marker, summary)
            self.assertIn(marker, plan)
        self.assertIn("Amendment-exit review and adoption projections", summary)


if __name__ == "__main__":
    unittest.main()
