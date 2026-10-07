"""Challenge portable structure, explicit locations and copied wire models."""

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from pydantic import ValidationError  # noqa: E402
from research_observatory_core.parsing.contracts import DocumentIR, TextProjection  # noqa: E402

from tests.parsing.contract_fixtures import ir, rich_ir_wire  # noqa: E402


class DocumentIRTests(unittest.TestCase):
    def test_scholarly_structure_retains_spans_candidates_figures_and_unknowns(self):
        value = rich_ir_wire()
        result = DocumentIR.model_validate(value)
        self.assertEqual(result, DocumentIR.model_validate_json(result.model_dump_json(by_alias=True)))
        self.assertEqual("ambiguous", result.citations[0].resolution)
        self.assertEqual(("ref-entry-1", "ref-entry-2"), result.citations[0].reference_candidates)
        self.assertEqual(2, result.tables[0].cells[0].row_span)
        self.assertEqual("unknown", result.tables[0].cells[0].confidence.state)
        self.assertEqual(0.7, result.tables[0].cells[1].confidence.value)
        self.assertEqual("synthetic-unsupported-element", result.nodes[-1].source_element_type)
        self.assertEqual("Unknown", result.text_projections[0].raw_text[43:50])
        self.assertEqual(result.raw_artifacts[0].stage_id, result.figures[0].preview_stage_id)
        value["tables"][0]["cells"][1].update(row=1, column=0)
        value["tables"][0]["gridState"] = "ambiguous"
        self.assertEqual("ambiguous", DocumentIR.model_validate(value).tables[0].grid_state)

    def test_scholarly_cross_references_and_conflicting_table_identity_are_refused(self):
        original = rich_ir_wire()
        mutations = (
            lambda v: v["references"][0].update(nodeId="paragraph"),
            lambda v: v["citations"][0].update(referenceCandidates=["missing"]),
            lambda v: v["citations"][0].update(resolution="unresolved"),
            lambda v: v["figures"][0].update(previewStageId="018f0000-0000-7000-8000-000000000999"),
            lambda v: v["tables"][0]["cells"][1].update(nodeId="cell1"),
            lambda v: v["tables"][0]["cells"][1].update(row=1, column=0),
            lambda v: v["quality"]["tableCellConfidence"].append(dict(v["quality"]["tableCellConfidence"][0])),
            lambda v: v["quality"]["warnings"][0].update(nodeId="missing"),
        )
        for index, change in enumerate(mutations):
            value = json.loads(json.dumps(original))
            change(value)
            with self.subTest(index=index), self.assertRaises(ValidationError):
                DocumentIR.model_validate(value)

    def test_wire_preserves_raw_text_and_independent_mapping(self):
        projection = TextProjection.from_raw("text-1", "D\u0307\u0323\r\n\U0001f642")
        self.assertEqual("\u1e0c\u0307\n\U0001f642", projection.normalized_text)
        self.assertEqual(
            ({"start": 0, "end": 1}, {"start": 2, "end": 3}),
            tuple(value.model_dump() for value in projection.mappings[0].raw_ranges),
        )
        self.assertEqual(projection, TextProjection.model_validate_json(projection.model_dump_json(by_alias=True)))
        value = ir()
        self.assertEqual(value, DocumentIR.model_validate_json(value.model_dump_json(by_alias=True)))
        self.assertNotIn("canonical", json.dumps(value.model_dump(mode="json", by_alias=True)))

    def test_malformed_order_parent_offsets_and_versions_are_refused(self):
        original = ir().model_dump(mode="json", by_alias=True)
        mutations = (
            lambda v: v.update(schemaVersion="99.0"),
            lambda v: v.update(disposition="accepted"),
            lambda v: v["nodes"][0].update(parentId="missing"),
            lambda v: v["nodes"][0].update(order=True),
            lambda v: v["nodes"][0]["text"]["rawRanges"][0].update(end=4),
            lambda v: v["nodes"][0]["text"]["normalizedRange"].update(end=4),
            lambda v: v["nodes"].append(dict(v["nodes"][0], order=1)),
            lambda v: v["textProjections"][0].update(normalizedText="replaced"),
            lambda v: v["textProjections"][0]["mappings"][0]["rawRanges"][0].update(end=2),
            lambda v: v["textProjections"][0].update(mappings=[]),
            lambda v: v["binding"]["source"].update(path="unrestricted"),
        )
        for change in mutations:
            value = json.loads(json.dumps(original))
            change(value)
            with self.subTest(value=ascii(change)), self.assertRaises(ValidationError):
                DocumentIR.model_validate(value)

    def test_copied_instances_and_private_error_inputs_are_revalidated(self):
        original = ir()
        forged = original.model_copy(update={"disposition": "accepted"})
        with self.assertRaises(ValidationError):
            DocumentIR.model_validate(forged)
        invalid = original.model_dump(mode="json", by_alias=True)
        invalid["textProjections"][0]["rawText"] = "PRIVATE-SYNTHETIC-\ud800"
        with self.assertRaises(ValidationError) as caught:
            DocumentIR.model_validate(invalid)
        self.assertNotIn("PRIVATE-SYNTHETIC", str(caught.exception))

    def test_page_frame_locations_and_unknown_content_remain_explicit(self):
        value = ir().model_dump(mode="json", by_alias=True)
        value["pages"] = [
            {
                "pageIndex": 0,
                "width": 612.0,
                "height": 792.0,
                "rotation": 90,
                "unit": "points",
                "origin": "top-left",
                "frame": "unrotated-source-page",
            }
        ]
        value["nodes"][0]["locator"] = {
            "kind": "page-region",
            "pageIndex": 0,
            "x0": 10.0,
            "y0": 20.0,
            "x1": 200.0,
            "y1": 60.0,
            "unit": "points",
            "origin": "top-left",
            "frame": "unrotated-source-page",
        }
        parsed = DocumentIR.model_validate(value)
        self.assertEqual(90, parsed.pages[0].rotation)
        changes = (
            lambda v: v["pages"][0].update(rotation=False),
            lambda v: v["pages"][0].update(width=float("inf")),
            lambda v: v["nodes"][0]["locator"].update(x1=613.0),
            lambda v: v["nodes"][0]["locator"].update(pageIndex=1),
            lambda v: v["nodes"][0]["locator"].update(origin="bottom-left"),
            lambda v: v["nodes"][0].update(kind="unknown", sourceElementType=None),
        )
        for change in changes:
            mutated = json.loads(json.dumps(value))
            change(mutated)
            with self.subTest(change=ascii(change)), self.assertRaises(ValidationError):
                DocumentIR.model_validate(mutated)
        value["nodes"][0].update(kind="unknown", sourceElementType="unsupported-scholarly-element")
        self.assertEqual("abc", DocumentIR.model_validate(value).text_projections[0].raw_text)
        value["nodes"][0]["locator"] = {"kind": "unavailable", "reason": "unsupported-location"}
        self.assertEqual("unavailable", DocumentIR.model_validate(value).nodes[0].locator.kind)

    def test_locator_cannot_point_away_from_its_own_decoded_text(self):
        value = ir().model_dump(mode="json", by_alias=True)
        value["nodes"][0]["locator"]["rawRanges"] = [{"start": 1, "end": 2}]
        with self.assertRaises(ValidationError):
            DocumentIR.model_validate(value)


if __name__ == "__main__":
    unittest.main()
