"""Authored structures, not scholarly gold or model/hardware qualification."""

import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core import document_table_figures as domain  # noqa: E402
from research_observatory_core.document_revisions import (  # noqa: E402
    AcceptedDocumentRevision,
    canonicalize_structure,
    content_sha256,
    protected_json,
)
from research_observatory_core.document_table_figures import (  # noqa: E402
    OriginalStructurePreview,
    extract_table_figures,
)
from research_observatory_core.parsing.docling import decode_docling  # noqa: E402
from research_observatory_core.parsing.pipeline import decode_delivery  # noqa: E402
from research_observatory_core.parsing.requests import ParseSuccess  # noqa: E402

from tests.documents.test_reference_entries import accepted_native  # noqa: E402
from tests.parsing import test_docling_parsing as docling  # noqa: E402
from tests.parsing.test_native_parsing import native_parse  # noqa: E402


def derive(raw, format="jats", *, retained=True):
    accepted = accepted_native(raw, format)
    native = native_parse(raw, format)[3] if retained else None
    before = protected_json(accepted)
    entries = extract_table_figures(accepted, native_artifact=native)
    assert before == protected_json(accepted)
    return accepted, entries


def accepted_docling(value):
    request = docling.request()
    delivery = docling.delivery(request, value)
    result = decode_delivery(request, decode_docling(request, delivery))
    assert isinstance(result, ParseSuccess)
    ir = result.ir
    structure, mapping = canonicalize_structure(ir)
    # Detached authored adapter fixture. It does not qualify a runtime/model.
    wire = accepted_native(b"<article><body>Authored synthetic fixture</body></article>").model_dump(
        mode="json", by_alias=True
    )
    wire.update(
        projectId=structure.binding.source.project_id,
        documentId=structure.binding.source.document_id,
        structure=structure.model_dump(mode="json", by_alias=True),
        elementIdentities=[v.model_dump(mode="json", by_alias=True) for v in mapping],
        contentSha256=content_sha256(structure),
        structureSha256=hashlib.sha256(protected_json(structure)).hexdigest(),
    )
    wire["result"]["binding"] = structure.binding.model_dump(mode="json", by_alias=True)
    return AcceptedDocumentRevision.model_validate(wire), delivery.wire


def docling_table_figure():
    value = docling.fixture()
    value["sourcePages"][0]["rotation"] = 90
    document = value["document"]
    document["pages"]["1"]["size"] = dict(width=792.0, height=612.0)
    document["texts"][0].update(label="caption", orig="Synthetic caption", text="Synthetic caption")
    table = copy.deepcopy(document["texts"][0])
    table.update(
        self_ref="#/tables/0",
        label="table",
        orig="",
        text="",
        captions=[{"$ref": "#/texts/0"}],
        data=dict(
            num_rows=50000,
            num_cols=50000,
            table_cells=[
                dict(
                    text="Synthetic cell",
                    row_span=2,
                    col_span=3,
                    start_row_offset_idx=1,
                    end_row_offset_idx=3,
                    start_col_offset_idx=2,
                    end_col_offset_idx=5,
                    column_header=True,
                    row_header=False,
                    bbox=dict(l=10.0, t=100.0, r=110.0, b=80.0, coord_origin="BOTTOMLEFT"),
                )
            ],
        ),
    )
    document["tables"].append(table)
    picture = dict(
        self_ref="#/pictures/0",
        parent={"$ref": "#/body"},
        children=[],
        label="picture",
        prov=copy.deepcopy(document["texts"][0]["prov"]),
        captions=[{"$ref": "#/texts/0"}],
        image={"uri": "https://invalid.example/untrusted.png"},
    )
    document["pictures"].append(picture)
    document["body"]["children"].extend([{"$ref": "#/tables/0"}, {"$ref": "#/pictures/0"}])
    value["locations"]["#/texts/0"].update(x0=512.0, y0=682.0, x1=532.0, y1=782.0)
    value["locations"]["#/tables/0"] = dict(value["locations"]["#/texts/0"])
    value["locations"]["#/tables/0/cell/0"] = dict(value["locations"]["#/texts/0"])
    value["locations"]["#/pictures/0"] = dict(value["locations"]["#/texts/0"])
    return value


def paged_docling_table_figure(page_count=1):
    """Small authored adapter data for bounded Reader/Native wiring tests."""
    value = docling_table_figure()
    value["sourcePages"][0]["rotation"] = 0
    value["sourcePages"] *= page_count
    value["document"]["pages"] = {
        str(index + 1): dict(page_no=index + 1, size=dict(width=612.0, height=792.0)) for index in range(page_count)
    }
    region = dict(
        kind="page-region",
        pageIndex=0,
        x0=10.0,
        y0=692.0,
        x1=110.0,
        y1=712.0,
        unit="points",
        origin="top-left",
        frame="unrotated-source-page",
    )
    for key in value["locations"]:
        value["locations"][key] = dict(region)
    # Authored page text explicitly labels every page; this is a wiring
    # fixture, not a claim that a model extracted text from the PDF.
    for index in range(1, page_count):
        item = copy.deepcopy(value["document"]["texts"][0])
        key = f"#/texts/{index}"
        text = f"Synthetic authored page {index + 1}"
        item.update(self_ref=key, label="text", orig=text, text=text)
        item["prov"][0]["page_no"] = index + 1
        value["document"]["texts"].append(item)
        value["document"]["body"]["children"].append({"$ref": key})
        value["locations"][key] = dict(region, pageIndex=index)
    original = value["document"]["tables"][0]["data"]["table_cells"][0]
    cells = []
    for index in range(10):
        cell = copy.deepcopy(original)
        cell.update(
            text=f"Synthetic cell {index + 1}",
            start_row_offset_idx=index,
            end_row_offset_idx=index + 1,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            row_span=1,
            col_span=1,
            column_header=index == 0,
        )
        cells.append(cell)
        value["locations"][f"#/tables/0/cell/{index}"] = dict(region)
    value["document"]["tables"][0]["data"] = dict(num_rows=10, num_cols=1, table_cells=cells)
    if page_count >= 3:
        for key, item, page in (
            ("#/tables/0", value["document"]["tables"][0], 1),
            ("#/pictures/0", value["document"]["pictures"][0], 2),
        ):
            item["prov"][0]["page_no"] = page + 1
            value["locations"][key] = dict(region, pageIndex=page)
        for index in range(10):
            value["locations"][f"#/tables/0/cell/{index}"] = dict(region, pageIndex=1)
    return value


class TableFigureTests(unittest.TestCase):
    def test_blank_human_rationale_and_substituted_original_preview_node_are_refused(self):
        from research_observatory_core.domain_contracts import new_uuid_v7

        with self.assertRaises(ValueError):
            domain.TableFigureExcludeCommand(
                command_id=new_uuid_v7(),
                revision_id=new_uuid_v7(),
                expected_collection_revision_id=new_uuid_v7(),
                node_id=new_uuid_v7(),
                rationale=" ",
            )
        accepted, artifact = accepted_docling(docling_table_figure())
        table = extract_table_figures(accepted, docling_artifact=artifact)[0]
        wire = table.model_dump(mode="json", by_alias=True)
        wire["preview"]["nodeId"] = new_uuid_v7()
        with self.assertRaises(ValueError):
            domain.TableFigureEntry.model_validate(wire)

    def test_docling_exact_retained_relationships_sparse_grid_and_rotated_original_preview(self):
        accepted, artifact = accepted_docling(docling_table_figure())
        before = protected_json(accepted)
        table, figure = extract_table_figures(accepted, docling_artifact=artifact)
        self.assertEqual(
            (50000, 50000, "ambiguous", 1), (table.rows, table.columns, table.grid_state, len(table.cells))
        )
        self.assertEqual(
            (1, 2, 2, 3, "reported-header"),
            (
                table.cells[0].row,
                table.cells[0].column,
                table.cells[0].row_span,
                table.cells[0].column_span,
                table.cells[0].header_state,
            ),
        )
        self.assertEqual("unknown-confidence", table.cells[0].triage)
        for entry in (table, figure):
            self.assertEqual("reported", entry.caption_state)
            self.assertEqual("Synthetic caption", entry.captions[0].raw_text)
            assert entry.captions[0].anchor is not None
            assert entry.captions[0].anchor.page_region is not None
            assert isinstance(entry.preview, OriginalStructurePreview)
            self.assertEqual(90, entry.captions[0].anchor.page_region.rotation)
            self.assertEqual("object", entry.preview.basis)
            self.assertEqual(accepted.structure.binding.source.document_revision_id, entry.preview.source_revision_id)
            self.assertEqual(accepted.structure.binding.source.object_sha256, entry.preview.object_sha256)
            self.assertEqual("unrotated-source-page", entry.preview.locator.frame)
            self.assertEqual("unverified", entry.scholarly_verification)
        self.assertEqual("not-reported", figure.retained_preview_state)
        self.assertEqual(before, protected_json(accepted))
        with self.assertRaises(ValueError):
            extract_table_figures(
                accepted, docling_artifact=artifact.replace(b"Synthetic caption", b"Substituted value")
            )

    def test_docling_bad_caption_ref_remains_unavailable(self):
        value = docling_table_figure()
        value["document"]["tables"][0]["captions"] = [{"$ref": "#/texts/999"}]
        accepted, artifact = accepted_docling(value)
        table = extract_table_figures(accepted, docling_artifact=artifact)[0]
        self.assertEqual("unavailable", table.caption_state)
        self.assertFalse(table.captions)

    def test_caption_count_cancellation_and_deadline_are_bounded(self):
        raw = b"<article><body><fig>" + b"<caption>Unassigned</caption>" * 33 + b"</fig></body></article>"
        accepted = accepted_native(raw)
        with self.assertRaisesRegex(domain.TableFigureProblem, "structure-operation-limit"):
            extract_table_figures(accepted, native_artifact=native_parse(raw, "jats")[3])
        with self.assertRaisesRegex(domain.TableFigureProblem, "structure-operation-cancelled"):
            extract_table_figures(accepted, cancelled=lambda: True)
        with (
            patch.object(domain.time, "monotonic", side_effect=[0, 6]),
            self.assertRaisesRegex(domain.TableFigureProblem, "structure-operation-limit"),
        ):
            extract_table_figures(accepted)

    def test_foreign_namespace_wrapper_does_not_establish_caption_ownership(self):
        _, entries = derive(
            b"<article xmlns:x='urn:unknown'><body><x:table-wrap><caption>Unassigned</caption>"
            b"<table><tr><td>A</td></tr></table></x:table-wrap></body></article>"
        )
        self.assertEqual("not-reported", entries[0].caption_state)
        self.assertFalse(entries[0].captions)

    def test_cumulative_admission_precedes_whole_entry_serialization(self):
        # Small authored fixture and patched budget challenge the algorithm
        # without allocating the multi-GiB projection reuse that motivated it.
        accepted = accepted_native(
            b"<article><body><table>"
            + b"<tr><td>"
            + b"x" * 1024
            + b"</td></tr>" * 1
            + b"<tr><td>"
            + b"y" * 1024
            + b"</td></tr>"
            + b"</table></body></article>"
        )

        def no_whole_entry(value):
            if isinstance(value, domain.TableFigureEntry):
                self.fail("Oversize entry reached whole-entry serialization before admission")
            return protected_json(value)

        with (
            patch.object(domain, "MAX_TABLE_FIGURE_BYTES", 16000),
            patch.object(domain, "protected_json", no_whole_entry),
            self.assertRaisesRegex(domain.TableFigureProblem, "structure-operation-limit"),
        ):
            extract_table_figures(accepted)

    def test_table_wrapper_caption_label_headers_and_spans_preserve_exact_source(self):
        raw = (
            b"<article><body><table-wrap><label>Table S1</label>"
            b"<caption><p>Synthetic cells; NOT VERIFIED RESULTS.</p></caption>"
            b"<table><thead><tr><th colspan='2'>Reported header</th></tr></thead>"
            b"<tbody><tr><td>A</td><td>B</td></tr></tbody></table>"
            b"</table-wrap></body></article>"
        )
        accepted, entries = derive(raw)
        self.assertEqual(1, len(entries))
        table = entries[0]
        self.assertEqual("table", table.kind)
        self.assertEqual(accepted.structure.tables[0].node_id, table.node_id)
        self.assertEqual("reported", table.caption_state)
        self.assertEqual("Synthetic cells; NOT VERIFIED RESULTS.", table.captions[0].raw_text)
        self.assertEqual("Table S1", table.labels[0].raw_text)
        self.assertEqual((2, 2, "reported"), (table.rows, table.columns, table.grid_state))
        self.assertEqual(
            [(0, 0, 1, 2), (1, 0, 1, 1), (1, 1, 1, 1)],
            [(c.row, c.column, c.row_span, c.column_span) for c in table.cells],
        )
        self.assertEqual(["reported-header", "reported-body", "reported-body"], [c.header_state for c in table.cells])
        self.assertTrue(
            all(c.confidence.state == "unknown" and c.scholarly_verification == "unverified" for c in table.cells)
        )
        self.assertEqual("unverified", table.scholarly_verification)
        self.assertEqual(accepted.revision_id, table.captions[0].anchor.revision_id)
        self.assertEqual("format-has-no-pages", table.preview.reason)

    def test_competing_captions_are_preserved_instead_of_first_caption_winning(self):
        accepted, entries = derive(
            b"<article><body><fig><caption>First synthetic caption</caption>"
            b"<caption>Second synthetic caption</caption><graphic href='https://invalid.example/image'/></fig>"
            b"</body></article>"
        )
        figure = entries[0]
        self.assertEqual("figure", figure.kind)
        self.assertEqual("ambiguous", figure.caption_state)
        self.assertEqual(["First synthetic caption", "Second synthetic caption"], [c.raw_text for c in figure.captions])
        self.assertEqual(accepted.structure.figures[0].node_id, figure.node_id)
        self.assertEqual("unavailable", figure.preview.kind)
        self.assertEqual("unverified", figure.scholarly_verification)

    def test_shared_wrapper_cannot_associate_caption_to_two_tables(self):
        _, entries = derive(
            b"<article><body><table-wrap><caption>Unassigned synthetic caption</caption>"
            b"<table><tr><td>A</td></tr></table><table><tr><td>B</td></tr></table>"
            b"</table-wrap></body></article>"
        )
        self.assertEqual(2, len(entries))
        self.assertEqual(["ambiguous", "ambiguous"], [e.caption_state for e in entries])
        self.assertTrue(all(e.captions[0].raw_text == "Unassigned synthetic caption" for e in entries))

    def test_missing_retained_native_relationships_do_not_promote_first_caption_or_headers(self):
        _, entries = derive(
            b"<article><body><fig><caption>First</caption><caption>Second</caption></fig>"
            b"<table-wrap><caption>Table</caption><table><tr><th>Heading</th></tr></table></table-wrap>"
            b"</body></article>",
            retained=False,
        )
        self.assertEqual(["unavailable", "unavailable"], [e.caption_state for e in entries])
        self.assertTrue(all(not e.captions for e in entries))
        self.assertEqual("not-reported", entries[1].cells[0].header_state)

    def test_untrusted_retained_relationship_bytes_are_refused(self):
        accepted = accepted_native(b"<article><body><fig><caption>Original</caption></fig></body></article>")
        substituted = native_parse(b"<article><body><fig><caption>Changed!</caption></fig></body></article>", "jats")[3]
        with self.assertRaises(ValueError):
            extract_table_figures(accepted, native_artifact=substituted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
