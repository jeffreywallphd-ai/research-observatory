"""Bounded inert Reader projection from declared synthetic protected collection."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]
from research_observatory_core.reference_reader import ReferenceReaderPage, reader_page  # noqa: E402

from tests.documents import test_reference_repository as fixtures  # noqa: E402


class ReferenceReaderTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ReferenceRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_bounded_page_retains_exact_source_target_and_unverified_review_disclosures(self):
        collection = self.f.repository.enrich(self.f.command())
        page = reader_page(collection, self.f.accepted.result.binding.source)
        self.assertEqual(collection.collection_revision_id, page.collection_revision_id)
        self.assertEqual(collection.entries[0].target, page.entries[0].target)
        self.assertEqual(fixtures.RAW, page.entries[0].raw_preview)
        self.assertFalse(page.entries[0].raw_truncated)
        self.assertEqual("unverified", page.scholarly_verification)
        self.assertEqual(1, page.total)
        self.assertIsNone(page.next_after_order)
        self.assertLessEqual(len(page.model_dump_json(by_alias=True).encode()), 65536)

    def test_untrusted_page_cannot_substitute_project_source_or_exact_target(self):
        collection = self.f.repository.enrich(self.f.command())
        value = reader_page(collection, self.f.accepted.result.binding.source).model_dump(mode="json", by_alias=True)
        value["entries"][0]["target"] = None
        with self.assertRaises(ValueError):
            ReferenceReaderPage.model_validate(value)
        value = reader_page(collection, self.f.accepted.result.binding.source).model_dump(mode="json", by_alias=True)
        value["source"]["projectId"] = "aaaaaaaa-aaaa-7aaa-aaaa-aaaaaaaaaaaa"
        with self.assertRaises(ValueError):
            ReferenceReaderPage.model_validate(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
