from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from backlog_views import (  # noqa: E402
    PLAN_VIEW,
    expected_outputs,
    hierarchy,
    render_summary,
    source_digest,
    synchronize,
)


class BacklogViewTests(unittest.TestCase):
    def temporary_repo(self, temporary: str) -> Path:
        root = Path(temporary)
        (root / "planning").mkdir()
        shutil.copy2(REPO / "planning" / "backlog.yaml", root / "planning" / "backlog.yaml")
        shutil.copy2(REPO / "planning" / "backlog.schema.json", root / "planning" / "backlog.schema.json")
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
        summary = render_summary(data, source_digest(backlog.read_bytes()))

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

            canonical = destination.read_bytes()
            destination.write_bytes(canonical.replace(b"\n", b"\r\n"))
            stale, _ = synchronize(root, check=True)
            self.assertIn(destination.relative_to(root), stale)
            synchronize(root, check=False)
            self.assertEqual(canonical, destination.read_bytes())

            destination.write_bytes(b"\xff\xfeinvalid UTF-8")
            stale, _ = synchronize(root, check=True)
            self.assertIn(destination.relative_to(root), stale)
            synchronize(root, check=False)
            self.assertEqual(canonical, destination.read_bytes())

    def test_plan_and_digest_use_one_immutable_backlog_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            backlog = root / "planning" / "backlog.yaml"
            original = backlog.read_bytes()
            mutated = original.replace(
                b"title: Research Observatory Capability -> Slice -> Task Execution Plan",
                b"title: MUTATED AFTER SNAPSHOT",
                1,
            )
            original_read_bytes = Path.read_bytes
            backlog_reads = 0

            def unstable_read(path: Path) -> bytes:
                nonlocal backlog_reads
                if path == backlog:
                    backlog_reads += 1
                    return original if backlog_reads == 1 else mutated
                return original_read_bytes(path)

            with patch.object(Path, "read_bytes", unstable_read):
                outputs = expected_outputs(root)

            plan = outputs[root.resolve() / PLAN_VIEW]
            self.assertEqual(1, backlog_reads)
            self.assertIn("Research Observatory Capability -> Slice -> Task Execution Plan", plan)
            self.assertIn(source_digest(original), plan)
            self.assertNotIn(source_digest(mutated), plan)

    def test_output_redirect_and_io_failures_are_fail_closed_and_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = self.temporary_repo(temporary)
            redirect = root / "docs"
            try:
                if os.name == "nt":
                    created = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(redirect), outside],
                        capture_output=True,
                        check=False,
                    )
                    if created.returncode != 0:
                        self.skipTest("directory junctions are unavailable")
                else:
                    redirect.symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(SystemExit, "parent escapes repository"):
                    expected_outputs(root)
            finally:
                if redirect.exists():
                    redirect.rmdir()

        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            synchronize(root, check=False)
            destination = root.resolve() / PLAN_VIEW
            original_read_bytes = Path.read_bytes

            def denied_read(path: Path) -> bytes:
                if path == destination:
                    raise PermissionError("controlled read denial")
                return original_read_bytes(path)

            with (
                patch.object(Path, "read_bytes", denied_read),
                self.assertRaisesRegex(SystemExit, "Cannot read generated backlog view"),
            ):
                synchronize(root, check=True)

            destination.write_bytes(b"stale")
            with (
                patch("backlog_views.os.replace", side_effect=PermissionError("controlled replace denial")),
                self.assertRaisesRegex(SystemExit, "Cannot update generated backlog view"),
            ):
                synchronize(root, check=False)
            self.assertEqual(b"stale", destination.read_bytes())
            self.assertEqual([], list(destination.parent.glob(f"{destination.name}.*.tmp")))


if __name__ == "__main__":
    unittest.main()
