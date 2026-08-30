from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from plan_review_site import (  # noqa: E402
    build_site,
    extract_task_section,
    task_page_name,
    task_worksheet_html,
    task_worksheet_projection,
)


class PlanReviewTaskDrilldownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.site = Path(cls.temporary.name) / "review-site"
        cls.manifest = build_site(REPO, cls.site)
        cls.backlog = yaml.safe_load((REPO / "planning" / "backlog.yaml").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_manifest_and_pages_cover_every_backlog_task_without_hard_coded_inventory(self) -> None:
        authored_slices = {
            str(slice_["slice_id"])
            for capability in self.manifest["capabilities"]
            for slice_ in capability["slices"]
        }
        expected = [
            str(task["id"])
            for capability in self.backlog.get("capabilities", [])
            for slice_ in capability.get("slices", [])
            if str(slice_["id"]) in authored_slices
            for task in slice_.get("tasks", [])
        ]
        projected = [
            str(task["task_id"])
            for capability in self.manifest["capabilities"]
            for slice_ in capability["slices"]
            for task in slice_["tasks"]
        ]
        self.assertEqual(expected, projected)
        for capability in self.manifest["capabilities"]:
            for slice_ in capability["slices"]:
                for task in slice_["tasks"]:
                    page = self.site / task["page"]
                    self.assertTrue(page.is_file(), task["task_id"])
                    text = page.read_text(encoding="utf-8")
                    self.assertIn(f'data-task-page="{task["task_id"]}"', text)
                    self.assertIn("Scope and acceptance", text)
                    self.assertIn("Profiles and commands", text)

    def test_wave_pages_render_nested_collapsible_cards_from_exact_wave_inventory(self) -> None:
        waves = {str(wave["wave_id"]): wave for wave in self.manifest["waves"]}
        authored_task_ids = {
            str(task["task_id"])
            for capability in self.manifest["capabilities"]
            for slice_ in capability["slices"]
            for task in slice_["tasks"]
        }
        for wave_id, wave in waves.items():
            text = (self.site / wave["page"]).read_text(encoding="utf-8")
            for capability_id in wave["capability_ids"]:
                self.assertEqual(1, text.count(f'data-wave-capability="{capability_id}"'))
            for slice_id in wave["slice_ids"]:
                self.assertEqual(1, text.count(f'data-wave-slice="{slice_id}"'))
            for task_id in wave["task_ids"]:
                self.assertEqual(1, text.count(f'data-wave-task="{task_id}"'))
                if task_id in authored_task_ids:
                    self.assertIn(f'href="../{task_id.split(".")[0]}/{task_page_name(task_id)}"', text)
            self.assertIn('<details class="wave-capability"', text, wave_id)
            self.assertIn('<details class="wave-slice-card"', text, wave_id)
            self.assertIn('<details class="wave-task-card"', text, wave_id)

    def test_capability_to_slice_to_task_links_are_generated_from_manifest_data(self) -> None:
        for capability in self.manifest["capabilities"]:
            capability_page = (self.site / capability["page"]).read_text(encoding="utf-8")
            for slice_ in capability["slices"]:
                slice_name = Path(slice_["page"]).name
                self.assertIn(f'href="{slice_name}"', capability_page)
                slice_page = (self.site / slice_["page"]).read_text(encoding="utf-8")
                for task in slice_["tasks"]:
                    self.assertIn(f'href="{Path(task["page"]).name}"', slice_page)

    def test_task_section_and_optional_worksheet_are_task_keyed_and_non_gating(self) -> None:
        task_id = "CAP-99.S01.T01"
        markdown = (
            "## 9. Task-by-task implementation plan\n\n"
            "### 9.1 `CAP-99.S01.T01` - First\nFirst body.\n\n"
            "### 9.2 `CAP-99.S01.T02` - Second\nSecond body.\n"
        )
        section = extract_task_section(markdown, task_id)
        self.assertIn("First body", section)
        self.assertNotIn("Second body", section)

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            worksheet = repo / "artifacts" / "evidence" / f"{task_id}.task-start.md"
            worksheet.parent.mkdir(parents=True)
            worksheet.write_text("# Worksheet\n\nCriterion closure.\n", encoding="utf-8")
            projection = task_worksheet_projection(repo, task_id)
            self.assertIsNotNone(projection)
            assert projection is not None
            self.assertEqual(f"artifacts/evidence/{task_id}.task-start.md", projection["path"])
            rendered = task_worksheet_html(projection, task_id)
            self.assertIn(f'data-task-worksheet="{task_id}"', rendered)
            self.assertIn(projection["sha256"], rendered)

        absent = task_worksheet_html(None, task_id)
        self.assertIn(f'data-task-worksheet-absent="{task_id}"', absent)
        self.assertIn("does not block execution", absent)

    def test_task_page_name_rejects_non_canonical_or_path_like_identities(self) -> None:
        self.assertEqual("CAP-03.S04.T01.html", task_page_name("CAP-03.S04.T01"))
        for unsafe in ("../CAP-03.S04.T01", "CAP-03/S04/T01", "CAP-X.S04.T01"):
            with self.assertRaises(ValueError):
                task_page_name(unsafe)


if __name__ == "__main__":
    unittest.main()
