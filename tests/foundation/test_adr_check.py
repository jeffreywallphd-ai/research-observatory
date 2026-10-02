from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from adr_check import task_ids, validate_change_set, validate_registry  # noqa: E402
from adr_new import create_adr  # noqa: E402


class ArchitectureDecisionWorkflowTests(unittest.TestCase):
    def test_materialized_amendment_tasks_are_valid_adr_links(self) -> None:
        backlog = {
            "capabilities": [{"slices": [{"tasks": [{"id": "CAP-00.S01.T01"}]}]}],
            "wave_amendments": [
                {
                    "taskInventory": [{"id": "W2.A01.T99"}],
                    "tasks": [{"id": "W2.A01.T01"}],
                }
            ],
        }
        self.assertEqual({"CAP-00.S01.T01", "W2.A01.T01"}, task_ids(backlog))

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
                "ADR-0012",
                "ADR-0013",
                "ADR-0014",
                "ADR-0015",
                "ADR-0016",
                "ADR-0017",
                "ADR-0018",
                "ADR-0019",
                "ADR-0020",
                "ADR-0021",
                "ADR-0022",
                "ADR-0023",
                "ADR-0024",
                "ADR-0025",
                "ADR-0026",
                "ADR-0027",
                "ADR-0028",
                "ADR-0029",
                "ADR-0030",
                "ADR-0031",
                "ADR-0032",
                "ADR-0033",
                "ADR-0034",
                "ADR-0035",
            },
            set(records),
        )
        self.assertIn("CAP-00.S02.T03", records["ADR-0001"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-00.S05.T02", records["ADR-0002"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-00.S06.T03", records["ADR-0003"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-00.S06.T04", records["ADR-0004"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-01.S01.T01", records["ADR-0005"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-02.S01.T01", records["ADR-0012"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-03.S01.T01", records["ADR-0013"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-02.S02.T01", records["ADR-0014"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-02.S03.T02", records["ADR-0015"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-02.S03.T02", records["ADR-0016"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-02.S04.T01", records["ADR-0017"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-02.S04.T02", records["ADR-0018"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-02.S04.T03", records["ADR-0019"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-02.S04.T04", records["ADR-0020"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-07.S01.T01", records["ADR-0021"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-03.S02.T01", records["ADR-0022"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-03.S02.T03", records["ADR-0023"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-04.S02.T01", records["ADR-0027"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-04.S05.T01", records["ADR-0028"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-05.S02.T01", records["ADR-0029"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-04.S02.T03", records["ADR-0030"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-04.S03.T01", records["ADR-0031"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-04.S03.T02", records["ADR-0032"]["metadata"]["linked_tasks"])
        self.assertIn("CAP-04.S03.T03", records["ADR-0033"]["metadata"]["linked_tasks"])

    def test_unindexed_adr_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "repo"
            # Complete validator inputs; local caches and protected fixtures are
            # unrelated to registry validation and must not enter this copy.
            shutil.copytree(REPO / "docs" / "adr", checkout / "docs" / "adr")
            (checkout / "planning").mkdir()
            shutil.copy2(REPO / "planning" / "backlog.yaml", checkout / "planning" / "backlog.yaml")
            shutil.copy2(REPO / "architecture-protected-paths.json", checkout / "architecture-protected-paths.json")
            self.assertEqual([], validate_registry(checkout)[0])
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
