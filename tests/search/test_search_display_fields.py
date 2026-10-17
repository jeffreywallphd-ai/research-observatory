"""Selected lawful fields may be distributed across distinct source rows."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.lexical_delivery import display_metadata  # noqa: E402
from research_observatory_core.lexical_index_repository import IndexServiceProblem  # noqa: E402

from tests.search.test_protected_lexical_store import row  # noqa: E402


class SearchDisplayFieldTests(unittest.TestCase):
    def test_title_and_year_follow_selected_fields_instead_of_first_source(self):
        first = row(text="", year=None, identifiers="10.00000/synthetic")
        second = replace(first, entry_id="b" * 64, title="Selected synthetic title", year=2024)
        for rows in ((first, second), (second, first)):
            self.assertEqual(("Selected synthetic title", 2024), display_metadata(rows))
        self.assertEqual(("Untitled record", None), display_metadata((first,)))

    def test_conflicting_fields_or_different_item_work_bindings_are_not_silently_composed(self):
        first = row(text="First")
        for other in (replace(first, title="Other"), replace(first, year=2023), replace(first, item_id=new_uuid_v7())):
            with self.assertRaises(IndexServiceProblem):
                display_metadata((first, other))


if __name__ == "__main__":
    unittest.main()
