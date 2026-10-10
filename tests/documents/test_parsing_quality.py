"""Frozen authored labels for diagnostic triage; no parser/model qualification."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.parsing.contracts import DocumentIR, ParserWarning  # noqa: E402
from research_observatory_core.parsing.quality import MAX_QUALITY_ITEMS, assess_ir  # noqa: E402

from tests.parsing import contract_fixtures as fixtures  # noqa: E402
from tests.parsing.test_native_parsing import native_parse  # noqa: E402


class ParsingQualityTests(unittest.TestCase):
    def test_plain_text_measured_zero_is_distinct_from_unknown_expectations_and_no_pages(self):
        ir = fixtures.ir()
        before = ir.model_dump_json(by_alias=True)
        report = assess_ir(ir)
        self.assertEqual("reported", report.dimensions.text_coverage.state)
        self.assertEqual(3, report.dimensions.text_coverage.observed_count)
        self.assertEqual(1.0, report.dimensions.text_coverage.ratio)
        self.assertEqual("not-applicable", report.dimensions.page_text_coverage.state)
        self.assertIsNone(report.dimensions.page_text_coverage.expected_count)
        self.assertEqual(0, report.dimensions.sections.observed_count)
        self.assertEqual("unknown", report.dimensions.sections.state)
        self.assertIsNone(report.dimensions.sections.expected_count)
        self.assertEqual(0, report.dimensions.references.observed_count)
        self.assertIsNone(report.dimensions.references.missing_count)
        self.assertEqual(0, report.dimensions.encoding.count)
        self.assertEqual("unknown", report.dimensions.anchor_coverage.parser_observation.state)
        self.assertFalse(report.review_required)
        self.assertTrue(report.human_inspection_available)
        self.assertEqual(before, ir.model_dump_json(by_alias=True))

    def test_frozen_rich_fixture_dimensions_and_low_cell_confidence_route_to_review(self):
        report = assess_ir(DocumentIR.model_validate(fixtures.rich_ir_wire()))
        self.assertTrue(report.review_required)
        self.assertEqual("ambiguous", report.dimensions.reading_order.state)
        self.assertEqual(1, report.dimensions.unresolved_references.count)
        self.assertEqual(1, report.dimensions.table_cell_confidence.low_reported_count)
        self.assertEqual(1, report.dimensions.table_cell_confidence.unknown_count)
        self.assertEqual("unknown", report.dimensions.anchor_coverage.parser_observation.state)
        self.assertIn("reading-order-ambiguous", report.review_reasons)
        self.assertIn("unresolved-references", report.review_reasons)
        self.assertIn("low-table-cell-confidence", report.review_reasons)
        self.assertTrue(report.human_inspection_available)
        self.assertNotIn("score", report.model_dump_json(by_alias=True).lower())

    def test_threshold_and_every_missing_confidence_state_preserve_their_meaning(self):
        for state, value, low in (
            ("reported", 0.799, True),
            ("reported", 0.8, False),
            ("unknown", None, False),
            ("not-reported", None, False),
            ("not-applicable", None, False),
            ("unavailable", None, False),
        ):
            with self.subTest(state=state, value=value):
                wire = fixtures.ir().model_dump(mode="json", by_alias=True)
                wire["nodes"][0]["confidence"] = {"state": state, "value": value}
                wire["quality"]["anchorCoverage"] = {"state": state, "value": value}
                report = assess_ir(DocumentIR.model_validate(wire))
                self.assertEqual(int(low), report.dimensions.extraction_confidence.low_reported_count)
                self.assertEqual(state, report.dimensions.anchor_coverage.parser_observation.state)
                self.assertEqual(low, "low-extraction-confidence" in report.review_reasons)

    def test_page_text_missing_encoding_anchor_and_geometry_labels_are_independent(self):
        wire = fixtures.ir(raw="a\ufffdb").model_dump(mode="json", by_alias=True)
        wire["binding"]["source"]["format"] = "pdf"
        wire["binding"]["producer"]["inputFormats"] = ["pdf"]
        wire["pages"] = [
            {
                "pageIndex": i,
                "width": 100.0,
                "height": 100.0,
                "rotation": 0,
                "unit": "points",
                "origin": "top-left",
                "frame": "unrotated-source-page",
            }
            for i in range(2)
        ]
        wire["nodes"][0]["locator"] = {"kind": "unavailable", "reason": "not-reported"}
        wire["quality"]["missingTextPages"] = [1]
        wire["quality"]["warnings"] = [
            {
                "code": "unsupported-table-geometry",
                "severity": "warning",
                "nodeId": None,
                "detail": "private diagnostic must never be delivered",
            }
        ]
        report = assess_ir(DocumentIR.model_validate(wire))
        self.assertEqual(2, report.dimensions.page_text_coverage.expected_count)
        self.assertEqual(2, report.dimensions.page_text_coverage.missing_count)
        self.assertEqual(1, report.dimensions.encoding.count)
        self.assertEqual(1, report.dimensions.anchor_coverage.missing_count)
        self.assertEqual(1, report.dimensions.table_geometry.count)
        self.assertTrue(
            {"missing-page-text", "replacement-characters", "missing-anchors", "table-geometry"}.issubset(
                report.review_reasons
            )
        )
        self.assertNotIn("private diagnostic", report.model_dump_json(by_alias=True))

    def test_authenticated_native_expectations_detect_missing_blocks_without_inventing_sections(self):
        ir, raw, _, raw_wire = native_parse(b"<root><section><p>A</p></section><reference>R</reference></root>", "xml")
        report = assess_ir(ir, native_artifact=raw_wire)
        self.assertEqual("reported", report.dimensions.sections.state)
        self.assertEqual(1, report.dimensions.sections.expected_count)
        self.assertEqual(1, report.dimensions.references.expected_count)
        self.assertEqual(0, report.dimensions.expected_blocks.missing_count)
        altered = ir.model_dump(mode="json", by_alias=True)
        section = next(item for item in altered["nodes"] if item["kind"] == "section")
        section["kind"] = "region"
        report = assess_ir(DocumentIR.model_validate(altered), native_artifact=raw_wire)
        self.assertEqual(1, report.dimensions.sections.missing_count)
        self.assertIn("missing-expected-blocks", report.review_reasons)
        raw["sourceSha256"] = "0" * 64
        with self.assertRaises(ValueError):
            assess_ir(ir, native_artifact=json.dumps(raw).encode())

    def test_native_zero_source_expectations_and_ambiguous_anchors_are_explicit(self):
        ir, _, _, raw_wire = native_parse(b"<root><p>A</p></root>", "xml")
        unknown = assess_ir(ir)
        self.assertIsNone(unknown.dimensions.sections.expected_count)
        self.assertIsNone(unknown.dimensions.references.expected_count)
        measured = assess_ir(ir, native_artifact=raw_wire)
        self.assertEqual(0, measured.dimensions.sections.expected_count)
        self.assertEqual(0, measured.dimensions.references.expected_count)
        wire = ir.model_dump(mode="json", by_alias=True)
        wire["quality"]["warnings"].append(
            {"code": "ambiguous-anchor", "severity": "warning", "nodeId": None, "detail": None}
        )
        ambiguous = assess_ir(DocumentIR.model_validate(wire), native_artifact=raw_wire)
        self.assertEqual("ambiguous", ambiguous.dimensions.anchor_coverage.state)
        self.assertEqual(1, ambiguous.dimensions.anchor_coverage.ambiguous_count)
        self.assertIn("missing-anchors", ambiguous.review_reasons)

    def test_cancellation_and_resource_limits_are_content_free(self):
        with self.assertRaisesRegex(ValueError, "parsing-quality-stopped"):
            assess_ir(fixtures.ir(raw="private research"), cancelled=lambda: True)
        wire = fixtures.ir().model_dump(mode="json", by_alias=True)
        warning = ParserWarning(code="synthetic-warning", severity="warning", node_id=None, detail=None)
        # Repeated warnings are legal retained IR; reject before flattening.
        wire["nodes"][0]["warnings"] = [warning.model_dump(mode="json", by_alias=True)] * MAX_QUALITY_ITEMS
        value = DocumentIR.model_validate(wire)
        with self.assertRaisesRegex(ValueError, "parsing-quality-resource-limit"):
            assess_ir(value)
        with (
            patch("research_observatory_core.parsing.quality.time.monotonic", side_effect=(0.0, 6.0)),
            self.assertRaisesRegex(ValueError, "parsing-quality-resource-limit"),
        ):
            assess_ir(fixtures.ir())
        native_ir, _, _, native_raw = native_parse(b"<root><p>A</p></root>", "xml")
        retained_count = sum(
            len(items)
            for items in (
                native_ir.nodes,
                native_ir.text_projections,
                native_ir.references,
                native_ir.citations,
                native_ir.tables,
                native_ir.figures,
                native_ir.pages,
                native_ir.quality.warnings,
                native_ir.quality.table_cell_confidence,
            )
        ) + sum(len(node.warnings) for node in native_ir.nodes)
        retained_count += sum(len(table.cells) for table in native_ir.tables)
        with (
            patch("research_observatory_core.parsing.quality.MAX_QUALITY_ITEMS", retained_count),
            self.assertRaisesRegex(ValueError, "parsing-quality-resource-limit"),
        ):
            assess_ir(native_ir, native_artifact=native_raw)

    def test_language_neutral_report_has_no_authority_or_aggregate_correctness(self):
        report = assess_ir(DocumentIR.model_validate(fixtures.rich_ir_wire()))
        schema = json.loads(
            (ROOT / "packages/contracts/documents/parsing-quality-dimensions.v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        wire = report.model_dump(mode="json", by_alias=True)
        Draft202012Validator(schema).validate(wire)
        wire["correctnessScore"] = 1.0
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(wire)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
