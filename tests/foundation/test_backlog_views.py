from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from backlog_views import expected_outputs, hierarchy, render_summary, source_digest, synchronize  # noqa: E402


class BacklogViewTests(unittest.TestCase):
    def temporary_repo(self, temporary: str) -> Path:
        root = Path(temporary)
        (root / "planning").mkdir()
        shutil.copy2(REPO / "planning" / "backlog.yaml", root / "planning" / "backlog.yaml")
        return root

    def test_committed_views_match_the_authoritative_backlog(self) -> None:
        stale, updated = synchronize(REPO, check=True)

        self.assertEqual([], stale)
        self.assertEqual([], updated)

    def test_generation_is_idempotent_and_does_not_rewrite_unchanged_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            stale, updated = synchronize(root, check=False)
            self.assertEqual(set(stale), set(updated))
            first = {path: (root / path).read_bytes() for path in updated}
            mtimes = {path: (root / path).stat().st_mtime_ns for path in updated}

            stale, updated_again = synchronize(root, check=False)

            self.assertEqual([], stale)
            self.assertEqual([], updated_again)
            self.assertEqual(first, {path: (root / path).read_bytes() for path in first})
            self.assertEqual(mtimes, {path: (root / path).stat().st_mtime_ns for path in mtimes})

    def test_summary_counts_and_statuses_are_derived_from_yaml(self) -> None:
        backlog = REPO / "planning" / "backlog.yaml"
        data = yaml.safe_load(backlog.read_text(encoding="utf-8"))
        capabilities, slices, tasks = hierarchy(data)
        summary = render_summary(data, source_digest(backlog))

        self.assertIn(f"| Capabilities | {len(capabilities)} |", summary)
        self.assertIn(f"| Slices | {len(slices)} |", summary)
        self.assertIn(f"| Tasks | {len(tasks)} |", summary)
        for status, count in Counter(task["status"] for task in tasks).items():
            self.assertIn(f"| `{status}` | {count} |", summary)

    def test_check_detects_manual_edits_and_regeneration_repairs_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            synchronize(root, check=False)
            destination = next(iter(expected_outputs(root)))
            destination.write_text(destination.read_text(encoding="utf-8") + "manual edit\n", encoding="utf-8")

            stale, updated = synchronize(root, check=True)
            self.assertIn(destination.relative_to(root), stale)
            self.assertEqual([], updated)
            self.assertTrue(destination.read_text(encoding="utf-8").endswith("manual edit\n"))

            _, repaired = synchronize(root, check=False)
            self.assertIn(destination.relative_to(root), repaired)
            self.assertEqual(expected_outputs(root)[destination], destination.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
