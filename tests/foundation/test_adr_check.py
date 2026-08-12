from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from adr_check import validate_change_set, validate_registry  # noqa: E402
from adr_new import create_adr  # noqa: E402


class ArchitectureDecisionWorkflowTests(unittest.TestCase):
    def test_repository_adr_registry_and_task_links_are_valid(self) -> None:
        errors, records = validate_registry(REPO)

        self.assertEqual([], errors)
        self.assertEqual(
            {
                "ADR-0001",
                "ADR-0002",
                "ADR-0003",
                "ADR-0004",
                "ADR-0005",
                "ADR-0006",
                "ADR-0007",
                "ADR-0008",
                "ADR-0009",
                "ADR-0010",
                "ADR-0011",
            },
            set(records),
        )
        self.assertIn("CAP-00.S02.T03", records["ADR-0001"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-00.S05.T02", records["ADR-0002"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-00.S06.T03", records["ADR-0003"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-00.S06.T04", records["ADR-0004"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-01.S01.T01", records["ADR-0005"]["metadata"]["linked_tasks"])

    def test_unindexed_adr_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "repo"
            shutil.copytree(
                REPO,
                checkout,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".venv",
                    ".local",
                    "__pycache__",
                    "dist",
                    "node_modules",
                    "product-dist",
                    "target",
                ),
            )
            sample = checkout / "docs" / "adr" / "ADR-9999-unindexed.md"
            sample.write_text("---\nid: ADR-9999\n---\n", encoding="utf-8")

            errors, _ = validate_registry(checkout)

            self.assertIn("unindexed ADR file: docs/adr/ADR-9999-unindexed.md", errors)

    def test_protected_change_without_changed_adr_is_rejected(self) -> None:
        errors, records = validate_registry(REPO)
        self.assertEqual([], errors)

        change_errors = validate_change_set(REPO, ["architecture-boundaries.json"], records)

        self.assertTrue(any("lacks a changed, indexed Proposed or Accepted ADR" in error for error in change_errors))

    def test_changed_matching_adr_covers_protected_change(self) -> None:
        errors, records = validate_registry(REPO)
        self.assertEqual([], errors)

        change_errors = validate_change_set(
            REPO,
            [
                "architecture-protected-paths.json",
                "docs/adr/ADR-0001-machine-checked-architecture-boundaries.md",
            ],
            records,
        )

        self.assertEqual([], change_errors)

    def test_scaffold_creates_proposed_record_and_index_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "repo"
            (checkout / "docs" / "adr").mkdir(parents=True)
            (checkout / "planning").mkdir()
            shutil.copy2(REPO / "docs" / "adr" / "index.json", checkout / "docs" / "adr" / "index.json")
            shutil.copy2(REPO / "planning" / "backlog.yaml", checkout / "planning" / "backlog.yaml")

            output = create_adr(
                checkout,
                "ADR-0099",
                "Example decision",
                ["CAP-00.S02.T03"],
                ["packages/contracts/**"],
            )

            self.assertTrue(output.is_file())
            self.assertIn("status: Proposed", output.read_text(encoding="utf-8"))
            index = json.loads((checkout / "docs" / "adr" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual("ADR-0099", index["records"][-1]["id"])


if __name__ == "__main__":
    unittest.main()
