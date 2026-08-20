from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from backlog_views import render_plan, render_summary  # noqa: E402
from plan_review_check import main as check_review_site  # noqa: E402
from plan_review_site import build_site, load_enabler_change_requests  # noqa: E402


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
        self.assertEqual("APPROVED", entry["approval_status"])
        self.assertEqual("NOT_MATERIALIZED", entry["lifecycle_status"])
        self.assertEqual("NONE", entry["campaign_status"])
        self.assertEqual(
            "9ed06e76ea09f069cf58fa0f55bfb130797b791b328e4bb24b69ce12dc3ac1aa",
            entry["packet_sha256"],
        )

        register = (self.site / "enablers/index.html").read_text(encoding="utf-8")
        detail = (self.site / "enablers/ECR-0001.html").read_text(encoding="utf-8")
        self.assertIn("Enabler change request register", register)
        for marker in (
            "Proposal, approval, materialization, and campaign state",
            "Hash-bound source records",
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
