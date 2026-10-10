"""Small Reader projections from actual protected synthetic citation collections."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]
from research_observatory_core.citation_reader import CitationReaderPage, reader_page  # noqa: E402

from tests.documents import test_citation_repository as fixtures  # noqa: E402


class CitationReaderTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.CitationRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_one_context_exact_source_reference_selector_pagination_and_unverified_state(self):
        collection = self.f.repository.enrich(self.f.command())
        page = reader_page(collection, self.f.accepted.result.binding.source, self.f.ref, self.f.accepted)
        entry = page.entries[0]
        self.assertEqual(2, page.total)
        self.assertEqual(0, page.next_after_order)
        self.assertEqual("[1]", entry.marker_preview)
        self.assertEqual("candidate", entry.resolution)
        self.assertEqual(0, entry.text_offset)
        self.assertEqual(10, entry.node_text_start)
        self.assertIn("Missing [9]", entry.paragraph.text_preview)
        self.assertEqual(self.f.ref.entries[0].reference_id, entry.targets[0].references[0].reference_id)
        self.assertEqual("unverified", page.scholarly_verification)
        next_page = reader_page(
            collection, self.f.accepted.result.binding.source, self.f.ref, self.f.accepted, after_order=0
        )
        self.assertEqual("[9]", next_page.entries[0].marker_preview)
        self.assertEqual(23, next_page.entries[0].text_offset)
        self.assertIsNone(next_page.next_after_order)
        self.assertLessEqual(len(page.model_dump_json(by_alias=True).encode()), 65536)

    def test_reference_binding_offset_and_target_count_substitution_are_refused(self):
        collection = self.f.repository.enrich(self.f.command())
        with self.assertRaises(ValueError):
            reader_page(
                collection,
                self.f.accepted.result.binding.source,
                self.f.ref.model_copy(update={"intent_sha256": "f" * 64}),
                self.f.accepted,
            )
        for field, value in (("textOffset", 5), ("targetCount", 0), ("markerLength", 1)):
            wire = reader_page(
                collection, self.f.accepted.result.binding.source, self.f.ref, self.f.accepted
            ).model_dump(mode="json", by_alias=True)
            wire["entries"][0][field] = value
            with self.assertRaises(ValueError):
                CitationReaderPage.model_validate(wire)


if __name__ == "__main__":
    unittest.main(verbosity=2)
