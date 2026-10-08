"""Authored synthetic selector expectations; no parser-quality claims."""

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.anchors.contracts import (  # noqa: E402
    AnchorSelection,
    SourceAnchorTarget,
    build_target,
)
from research_observatory_core.document_revisions import (  # noqa: E402
    AcceptedDocumentRevision,
    RetainedParseResultReceipt,
    canonicalize_structure,
    content_sha256,
    protected_json,
)
from research_observatory_core.parsing.contracts import DocumentIR, TextProjection  # noqa: E402

from tests.parsing import contract_fixtures as f  # noqa: E402


def accepted(raw="Synthetic passage repeated; Synthetic passage repeated.", *, geometry=False):
    wire = f.ir().model_dump(mode="json", by_alias=True)
    projection = TextProjection.from_raw("text-1", raw)
    wire["textProjections"] = [projection.model_dump(mode="json", by_alias=True)]
    wire["nodes"][0]["text"]["normalizedRange"]["end"] = len(projection.normalized_text)
    wire["nodes"][0]["text"]["rawRanges"] = [{"start": 0, "end": len(raw)}]
    wire["nodes"][0]["locator"]["rawRanges"] = [{"start": 0, "end": len(raw)}]
    if geometry:
        wire["pages"] = [
            {
                "pageIndex": 0,
                "width": 600.0,
                "height": 800.0,
                "rotation": 90,
                "unit": "points",
                "origin": "top-left",
                "frame": "unrotated-source-page",
            }
        ]
        wire["nodes"][0]["locator"] = {
            "kind": "page-region",
            "pageIndex": 0,
            "x0": 60.0,
            "y0": 160.0,
            "x1": 300.0,
            "y1": 400.0,
            "unit": "points",
            "origin": "top-left",
            "frame": "unrotated-source-page",
        }
    structure, mapping = canonicalize_structure(DocumentIR.model_validate(wire))
    receipt = RetainedParseResultReceipt(
        result_id=f.identity(801),
        revision_id=f.identity(802),
        binding=structure.binding,
        object_sha256="a" * 64,
        byte_length=1,
    )
    return AcceptedDocumentRevision(
        project_id=structure.binding.source.project_id,
        document_id=structure.binding.source.document_id,
        revision_id=f.identity(805),
        previous_revision_id=f.identity(804),
        result=receipt,
        decision_id=f.identity(806),
        decision_revision_id=f.identity(807),
        command_id=f.identity(803),
        command_sha256="c" * 64,
        accepted_by=f.identity(808),
        accepted_at="2026-10-08T00:00:00.000Z",
        intent_revision_id=f.identity(809),
        intent_sha256="d" * 64,
        policy_sha256="e" * 64,
        content_sha256=content_sha256(structure),
        structure_sha256=hashlib.sha256(protected_json(structure)).hexdigest(),
        element_identities=mapping,
        structure=structure,
    )


class AnchorContractTests(unittest.TestCase):
    def selection(self, value, start=0, end=17):
        return AnchorSelection(
            revision_id=value.revision_id,
            node_id=value.structure.nodes[0].node_id,
            normalized_range={"start": start, "end": end},
        )

    def test_repeated_quote_keeps_exact_position_and_serialized_identity(self):
        value = accepted()
        target = build_target(value, self.selection(value, 28, 45))
        self.assertEqual("Synthetic passage", target.quote.exact)
        self.assertEqual(28, target.text_position.start)
        self.assertEqual(value.revision_id, target.revision_id)
        self.assertEqual(value.structure.nodes[0].node_id, target.node_id)
        self.assertEqual(target, SourceAnchorTarget.model_validate_json(target.model_dump_json(by_alias=True)))
        self.assertEqual("unknown", target.confidence.state)
        self.assertIsNone(target.confidence.value)

    def test_nfc_crlf_and_supplementary_offsets_are_codepoints(self):
        value = accepted("Cafe\u0301\r\n\U0001f4da research")
        target = build_target(value, self.selection(value, 5, 6))
        self.assertEqual("\U0001f4da", target.quote.exact)
        self.assertEqual("Caf\u00e9\n\U0001f4da research", target.context.text)
        self.assertEqual(5, target.context.highlight.start)
        self.assertEqual(6, target.context.highlight.end)
        self.assertEqual("ro-text-nfc-1", target.normalization_version)
        self.assertEqual("16.0.0", target.unicode_version)

    def test_geometry_normalizes_source_points_once_and_declares_rotation(self):
        value = accepted(geometry=True)
        target = build_target(value, self.selection(value))
        region = target.page_region
        self.assertEqual(0, region.page_index)
        self.assertEqual(1, region.page_number)
        self.assertEqual((0.1, 0.2, 0.5, 0.5), (region.x0, region.y0, region.x1, region.y1))
        self.assertEqual(90, region.rotation)
        self.assertEqual("unrotated-source-page", region.frame)
        self.assertEqual("block", region.granularity)
        self.assertEqual((600.0, 800.0), (region.source_width, region.source_height))

    def test_missing_coordinates_remain_visible_typed_fallback(self):
        value = accepted()
        target = build_target(value, self.selection(value))
        self.assertIsNone(target.page_region)
        self.assertEqual("format-has-no-pages", target.coordinates_state)
        self.assertEqual("Synthetic passage", target.quote.exact)

    def test_wrong_revision_node_or_outside_node_span_is_denied(self):
        value = accepted()
        selection = self.selection(value)
        for update in (
            {"revision_id": f.identity(999)},
            {"node_id": f.identity(998)},
            {"normalized_range": {"start": 0, "end": 999}},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                build_target(value, selection.model_copy(update=update))

    def test_untrusted_authority_and_nonfinite_geometry_are_rejected(self):
        value = accepted(geometry=True)
        target = build_target(value, self.selection(value))
        for key, replacement in (("x0", float("nan")), ("x1", 1.1), ("pageNumber", 2)):
            wire = target.model_dump(mode="json", by_alias=True)
            wire["pageRegion"][key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                SourceAnchorTarget.model_validate(wire)
        wire = self.selection(value).model_dump(mode="json", by_alias=True)
        wire["claimedActor"] = f.identity(997)
        with self.assertRaises(ValueError):
            AnchorSelection.model_validate(wire)

    def test_protected_context_is_bounded_without_shifting_selected_span(self):
        value = accepted("a" * 20_000 + "chosen" + "z" * 20_000)
        target = build_target(value, self.selection(value, 20_000, 20_006))
        self.assertEqual("chosen", target.quote.exact)
        self.assertLessEqual(len(target.context.text), 8192)
        self.assertEqual(20_000, target.context.start + target.context.highlight.start)
        self.assertEqual("chosen", target.context.text[target.context.highlight.start : target.context.highlight.end])
        with self.assertRaises(ValueError):
            build_target(value, self.selection(value, 0, 3000))

    def test_selector_disagreement_and_quote_content_never_validate_silently(self):
        value = accepted()
        target = build_target(value, self.selection(value))
        for changed in ("quote", "highlight", "offset"):
            wire = target.model_dump(mode="json", by_alias=True)
            if changed == "quote":
                wire["quote"]["exact"] = "different source content"
            elif changed == "highlight":
                wire["context"]["highlight"]["end"] -= 1
            else:
                wire["context"]["start"] += 1
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                SourceAnchorTarget.model_validate(wire)


if __name__ == "__main__":
    unittest.main(verbosity=2)
