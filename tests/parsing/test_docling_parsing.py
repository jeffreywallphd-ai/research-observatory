"""Authored Docling adapter gold; synthetic values do not qualify a runtime."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "services/core-api/src"), str(REPO)]

from research_observatory_core.parsing.contracts import ParserAsset, RawParserArtifact  # noqa: E402
from research_observatory_core.parsing.docling import DOCLING_MEDIA_TYPE, decode_docling  # noqa: E402
from research_observatory_core.parsing.pipeline import decode_delivery  # noqa: E402
from research_observatory_core.parsing.requests import ParseRequest, ParseSuccess  # noqa: E402
from research_observatory_core.parsing.selection import (  # noqa: E402
    ParserRegistry,
    RegisteredParser,
    SelectionSource,
    select_parser,
    selection_sha256,
)
from research_observatory_core.ports.docling_parsing import AuthenticatedDoclingDelivery  # noqa: E402
from research_observatory_core.ports.parsing import ParseProblem  # noqa: E402

from tests.parsing.contract_fixtures import binding, descriptor, identity, source  # noqa: E402


def request(data=None):
    selected = source("pdf")
    if data is not None:
        selected = selected.model_copy(
            update={"object_sha256": hashlib.sha256(data).hexdigest(), "byte_length": len(data)}
        )
    producer = descriptor("ro-docling-cpu", ("pdf", "docx")).model_copy(
        update={
            "kind": "docling-cpu",
            "version": "2.126.0",
            "assets": (ParserAsset(component="docling-assets", version="synthetic-1", sha256="4" * 64),),
        }
    )
    selection = select_parser(
        (SelectionSource(selected, "available", "primary"),),
        ParserRegistry((RegisteredParser(producer, "available"),)),
        primary_attachment_id=selected.attachment_id,
    )
    return ParseRequest(
        schema_version="1.0",
        selection=selection,
        binding=binding(selected, producer).model_copy(update={"selection_sha256": selection_sha256(selection)}),
    )


def fixture():
    box = {"l": 10.0, "t": 100.0, "r": 110.0, "b": 80.0, "coord_origin": "BOTTOMLEFT"}

    def root(name, children):
        return {"self_ref": "#/" + name, "label": "unspecified", "children": children}

    item = {
        "self_ref": "#/texts/0",
        "parent": {"$ref": "#/body"},
        "children": [],
        "label": "text",
        "orig": "Cafe\u0301 \ufffd",
        "text": "Café \ufffd",
        "prov": [{"page_no": 1, "bbox": box}],
    }
    return {
        "schemaVersion": "2.0",
        "documentType": "docling-parser-output",
        "inputSha256": "1" * 64,
        "inputLength": 3,
        "format": "pdf",
        "status": "success",
        "document": {
            "schema_name": "DoclingDocument",
            "version": "1.10.0",
            "name": "synthetic",
            "origin": None,
            "body": root("body", [{"$ref": "#/texts/0"}]),
            "furniture": root("furniture", []),
            "groups": [],
            "texts": [item],
            "pictures": [],
            "tables": [],
            "key_value_items": [],
            "form_items": [],
            "pages": {"1": {"page_no": 1, "size": {"width": 612.0, "height": 792.0}}},
        },
        "sourcePages": [
            {"mediaBox": [0, 0, 612, 792], "cropBox": [0, 0, 612, 792], "rotation": 0, "userUnit": 1, "imagePixels": 0}
        ],
        "locations": {
            "#/texts/0": {
                "kind": "page-region",
                "pageIndex": 0,
                "x0": 10.0,
                "y0": 692.0,
                "x1": 110.0,
                "y1": 712.0,
                "unit": "points",
                "origin": "top-left",
                "frame": "unrotated-source-page",
            }
        },
        "geometryWarnings": [],
    }


def delivery(req, value):
    wire = json.dumps(value, ensure_ascii=False).encode()
    receipt = RawParserArtifact(
        stage_id=identity(720),
        object_sha256=hashlib.sha256(wire).hexdigest(),
        byte_length=len(wire),
        media_type=DOCLING_MEDIA_TYPE,
    )
    return AuthenticatedDoclingDelivery(
        wire=wire,
        producer=req.binding.producer,
        job_id=req.binding.attempt.job_id,
        attempt_id=req.binding.attempt.attempt_id,
        artifact_receipt=receipt,
    )


class DoclingAdapterTests(unittest.TestCase):
    def parse(self, value):
        req = request()
        result = decode_delivery(req, decode_docling(req, delivery(req, value)))
        self.assertIsInstance(result, ParseSuccess)
        assert isinstance(result, ParseSuccess)
        return result.ir

    def test_total_table_expansion_is_rejected_before_node_allocation(self):
        req, value = request(), fixture()
        document = value["document"]
        document["texts"], value["locations"] = [], {}
        document["body"]["children"] = []
        # Each list is within its individual limit. Combined cell expansion is
        # above the graph envelope while the authenticated raw wire is bounded.
        for index in range(2):
            cells = [
                {
                    "text": "",
                    "start_row_offset_idx": row,
                    "end_row_offset_idx": row + 1,
                    "start_col_offset_idx": 0,
                    "end_col_offset_idx": 1,
                    "row_span": 1,
                    "col_span": 1,
                }
                for row in range(50000)
            ]
            key = f"#/tables/{index}"
            document["tables"].append(
                {
                    "self_ref": key,
                    "parent": {"$ref": "#/body"},
                    "children": [],
                    "label": "table",
                    "data": {"num_rows": 50000, "num_cols": 1, "table_cells": cells},
                }
            )
            document["body"]["children"].append({"$ref": key})
        authenticated = delivery(req, value)
        self.assertLess(len(authenticated.wire), 64 * 1_048_576)
        with (
            patch(
                "research_observatory_core.parsing.docling.IRNode",
                side_effect=AssertionError("oversize expansion reached model allocation"),
            ),
            self.assertRaisesRegex(ParseProblem, "^parse-output-invalid$"),
        ):
            decode_docling(req, authenticated)

    def test_core_decode_cancellation_interrupts_preflight_before_model_allocation(self):
        req, value = request(), fixture()
        original = value["document"]["texts"][0]
        value["locations"] = {}
        value["document"]["texts"] = [dict(original, self_ref=f"#/texts/{i}") for i in range(1000)]
        value["document"]["body"]["children"] = [{"$ref": f"#/texts/{i}"} for i in range(1000)]
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks >= 4

        with (
            patch(
                "research_observatory_core.parsing.docling.IRNode",
                side_effect=AssertionError("cancelled preflight reached model allocation"),
            ),
            self.assertRaisesRegex(ParseProblem, "^parse-output-invalid$"),
        ):
            decode_docling(req, delivery(req, value), cancelled=cancelled)
        self.assertEqual(checks, 4)

    def test_figure_locator_lookup_has_linear_node_access(self):
        from research_observatory_core.parsing import docling

        req, value = request(), fixture()
        document = value["document"]
        for index in range(400):
            key = f"#/pictures/{index}"
            document["pictures"].append(
                {"self_ref": key, "parent": {"$ref": "#/body"}, "children": [], "label": "picture"}
            )
            document["body"]["children"].append({"$ref": key})
        accesses = 0
        original = docling.IRNode

        class ObservedNode:
            def __init__(self, **fields):
                self.node = original(**fields)

            @property
            def staged_id(self):
                nonlocal accesses
                accesses += 1
                return self.node.staged_id

            @property
            def locator(self):
                return self.node.locator

        # Isolate construction work; ordinary tests validate the complete IR.
        with patch.object(docling, "IRNode", ObservedNode), patch.object(docling, "DocumentIR", lambda **parts: parts):
            built = cast(dict[str, Any], docling._build_ir(req, value, delivery(req, value).artifact_receipt))
        self.assertEqual(len(built["figures"]), 400)
        self.assertLessEqual(accesses, 2 * len(built["nodes"]))

    def test_authored_text_offsets_source_frame_and_unknown_quality(self):
        ir = self.parse(fixture())
        projection = next(p for p in ir.text_projections if p.raw_text)
        self.assertEqual(projection.raw_text, "Cafe\u0301 \ufffd")
        self.assertEqual(projection.normalized_text, "Café \ufffd")
        text = next(n for n in ir.nodes if n.kind == "paragraph")
        self.assertEqual(text.text.raw_ranges[0].end, 7)
        self.assertEqual((text.locator.x0, text.locator.y0), (10.0, 692.0))
        self.assertEqual(ir.quality.reading_order, "ambiguous")
        self.assertEqual(ir.quality.anchor_coverage.state, "unknown")
        self.assertEqual(ir.quality.replacement_characters, 1)
        self.assertEqual(ir.quality.missing_text_pages, ())
        self.assertEqual(ir.disposition, "staged")
        self.assertEqual(len(ir.raw_artifacts), 1)

    def test_scan_and_unknown_block_are_retained_without_successful_layout_claim(self):
        value = fixture()
        value["status"] = "partial_success"
        value["document"]["texts"][0].update(label="vendor-unknown", orig="", text="")
        ir = self.parse(value)
        self.assertEqual(ir.quality.missing_text_pages, (0,))
        unknown = next(n for n in ir.nodes if n.kind == "unknown")
        self.assertEqual(unknown.source_element_type, "vendor-unknown")
        self.assertEqual(unknown.locator.kind, "page-region")
        self.assertIn("missing-text-ocr-disabled", {w.code for w in ir.quality.warnings})

    def test_source_receipt_job_version_and_geometry_substitution_deny(self):
        req, value = request(), fixture()
        valid = delivery(req, value)
        for invalid in (
            replace(valid, job_id=identity(999)),
            replace(valid, attempt_id=identity(999)),
            replace(valid, producer=valid.producer.model_copy(update={"version": "9.9.9"})),
            replace(valid, artifact_receipt=valid.artifact_receipt.model_copy(update={"object_sha256": "0" * 64})),
        ):
            with self.subTest(invalid=type(invalid)), self.assertRaises(ParseProblem):
                decode_docling(req, invalid)
        for mutate in (
            lambda v: v.update(inputSha256="0" * 64),
            lambda v: v["locations"]["#/texts/0"].update(x0=11.0),
            lambda v: v["document"].update(version="9.9.9"),
            lambda v: v["document"]["texts"][0].update(parent={"$ref": "#/furniture"}),
            lambda v: v["document"]["body"]["children"].append({"$ref": "#/texts/0"}),
        ):
            invalid = copy.deepcopy(value)
            mutate(invalid)
            with self.assertRaises(ParseProblem):
                decode_docling(req, delivery(req, invalid))

    def test_tables_keep_cell_text_and_spans_but_quality_is_unverified(self):
        value = fixture()
        table = copy.deepcopy(value["document"]["texts"][0])
        table.update(
            self_ref="#/tables/0",
            label="table",
            orig="",
            text="",
            data={
                "num_rows": 1,
                "num_cols": 2,
                "table_cells": [
                    {
                        "text": "A",
                        "row_span": 1,
                        "col_span": 2,
                        "start_row_offset_idx": 0,
                        "end_row_offset_idx": 1,
                        "start_col_offset_idx": 0,
                        "end_col_offset_idx": 2,
                        "bbox": {"l": 10.0, "t": 692.0, "r": 110.0, "b": 712.0, "coord_origin": "TOPLEFT"},
                    }
                ],
            },
        )
        value["document"]["tables"].append(table)
        value["document"]["body"]["children"].append({"$ref": "#/tables/0"})
        value["locations"]["#/tables/0"] = dict(value["locations"]["#/texts/0"])
        value["locations"]["#/tables/0/cell/0"] = dict(value["locations"]["#/texts/0"])
        ir = self.parse(value)
        self.assertEqual(ir.tables[0].grid_state, "ambiguous")
        self.assertEqual(ir.tables[0].cells[0].column_span, 2)
        self.assertEqual(ir.tables[0].cells[0].confidence.state, "unknown")
        self.assertEqual(ir.quality.table_cell_confidence[0].confidence.state, "unknown")
        value["document"]["tables"][0]["data"]["table_cells"][0]["end_row_offset_idx"] = True
        with self.assertRaises(ParseProblem):
            self.parse(value)


if __name__ == "__main__":
    unittest.main()
