"""Bounded projections over actual encrypted, explicitly synthetic structures."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_table_figures import (  # noqa: E402
    TableFigureCollection,
    extract_table_figures,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.table_figure_reader import TableFigureReaderPage, reader_page  # noqa: E402

from tests.documents import test_table_figure_repository as fixtures  # noqa: E402
from tests.documents.test_table_figures import accepted_docling, paged_docling_table_figure  # noqa: E402


class TableFigureReaderTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.TableFigureRepositoryTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.collection = self.f.repository.enrich(self.f.command())

    def page(self, collection=None, **kwargs):
        return reader_page(
            collection or self.collection, self.f.accepted.structure.binding.source, self.f.accepted, **kwargs
        )

    def test_exact_source_one_object_sparse_cell_page_quality_and_exclusion(self):
        page = self.page()
        table = page.entries[0]
        self.assertEqual((2, 0), (page.total, page.next_after_order))
        self.assertEqual(["A", "B"], [c.text_preview for c in table.cells])
        self.assertEqual(["low-confidence", "reported-confidence"], [c.triage for c in table.cells])
        self.assertEqual(0, table.cells[0].jump.text_offset)
        self.assertEqual(17, table.cells[0].jump.node_text_start)
        self.assertEqual("unverified", page.scholarly_verification)
        self.assertEqual("unavailable", table.caption_state)
        self.assertEqual("format-has-no-pages", table.preview.reason)
        self.assertLessEqual(len(page.model_dump_json(by_alias=True).encode()), 65536)
        second = self.page(after_order=0)
        self.assertEqual("figure", second.entries[0].kind)
        self.assertIsNone(second.next_after_order)
        excluded = self.f.repository.exclude(self.f.exclude(self.collection))
        projected = self.page(excluded).entries[0]
        self.assertTrue(projected.excluded)
        self.assertEqual(excluded.exclusions[0], projected.exclusion)
        self.assertEqual(table.cells, projected.cells)

    def test_substituted_source_anchor_and_unpinned_object_cell_cursor_are_refused(self):
        with self.assertRaises(ValueError):
            reader_page(
                self.collection, self.collection.source.model_copy(update={"object_sha256": "f" * 64}), self.f.accepted
            )
        with self.assertRaises(ValueError):
            self.page(after_cell=0, cell_object_id=new_uuid_v7())
        with self.assertRaises(ValueError):
            self.page(after_cell=0)
        with self.assertRaises(ValueError):
            self.page(after_order=True)
        wire = self.collection.model_dump(mode="json", by_alias=True)
        wire["entries"][0]["cells"][0]["anchor"]["revisionId"] = new_uuid_v7()
        with self.assertRaises(ValueError):
            TableFigureCollection.model_validate(wire)
        for field, value in (("cellCount", 0), ("nextAfterCell", 0), ("nodeId", new_uuid_v7())):
            wire = self.page().model_dump(mode="json", by_alias=True)
            wire["entries"][0][field] = value
            with self.assertRaises(ValueError):
                TableFigureReaderPage.model_validate(wire)

    def test_ten_reported_cells_have_bounded_exact_cursor_and_truncated_caption(self):
        value = paged_docling_table_figure()
        caption = "Synthetic caption " + "x" * 600
        value["document"]["texts"][0].update(orig=caption, text=caption)
        accepted, artifact = accepted_docling(value)
        entries = extract_table_figures(accepted, docling_artifact=artifact)
        collection = self.collection.model_copy(
            update={
                "project_id": accepted.project_id,
                "document_revision_id": accepted.revision_id,
                "source": accepted.structure.binding.source,
                "content_sha256": accepted.content_sha256,
                "structure_sha256": accepted.structure_sha256,
                "entries": entries,
            }
        )
        collection = TableFigureCollection.model_validate(collection.model_dump())
        page = reader_page(collection, collection.source, accepted)
        table = page.entries[0]
        self.assertEqual((10, 8, 7), (table.cell_count, len(table.cells), table.next_after_cell))
        self.assertTrue(table.captions[0].truncated)
        self.assertEqual((512, len(caption)), (len(table.captions[0].text_preview), table.captions[0].text_length))
        self.assertEqual("source-page-region", table.preview.kind)
        self.assertEqual(collection.source.document_revision_id, table.preview.source_revision_id)
        second = reader_page(collection, collection.source, accepted, after_cell=7, cell_object_id=table.node_id)
        self.assertEqual(["Synthetic cell 9", "Synthetic cell 10"], [c.text_preview for c in second.entries[0].cells])
        self.assertIsNone(second.entries[0].next_after_cell)
        self.assertTrue(all(c.jump.node_id == entries[0].cells[c.cell_order].node_id for c in second.entries[0].cells))
        self.assertLessEqual(len(second.model_dump_json(by_alias=True).encode()), 65536)


if __name__ == "__main__":
    unittest.main(verbosity=2)
