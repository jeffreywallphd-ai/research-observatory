"""Authored structural corrections; no parser, principal or hardware qualification."""

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_corrections import (  # noqa: E402
    CorrectionPatch,
    apply_correction,
    value_sha256,
)
from research_observatory_core.document_revisions import (  # noqa: E402
    AcceptedDocumentRevision,
    DocumentRevisionProblem,
    RetainedParseResultReceipt,
    canonicalize_structure,
    content_sha256,
    protected_json,
)
from research_observatory_core.parsing.contracts import DocumentIR, TextProjection  # noqa: E402

from tests.parsing.contract_fixtures import identity, ir, rich_ir_wire  # noqa: E402


def accepted_ir(value):
    structure, mapping = canonicalize_structure(value)
    return AcceptedDocumentRevision(
        project_id=structure.binding.source.project_id,
        document_id=structure.binding.source.document_id,
        revision_id=identity(805),
        previous_revision_id=identity(804),
        result=RetainedParseResultReceipt(
            result_id=identity(801),
            revision_id=identity(802),
            binding=structure.binding,
            object_sha256="a" * 64,
            byte_length=1,
        ),
        decision_id=identity(806),
        decision_revision_id=identity(807),
        command_id=identity(803),
        command_sha256="c" * 64,
        accepted_by=identity(808),
        accepted_at="2026-10-10T00:00:00.000Z",
        intent_revision_id=identity(809),
        intent_sha256="d" * 64,
        policy_sha256="e" * 64,
        content_sha256=content_sha256(structure),
        structure_sha256=value_sha256(structure),
        element_identities=mapping,
        structure=structure,
    )


class DocumentCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.base = accepted_ir(DocumentIR.model_validate(rich_ir_wire()))
        self.named = {row.staged_id: row.canonical_id for row in self.base.element_identities}
        self.nodes = {row.node_id: row for row in self.base.structure.nodes}

    def op(self, name, kind, **fields):
        node = self.nodes[self.named[name]]
        return {"op": kind, "nodeId": node.node_id, "expectedNodeSha256": value_sha256(node), **fields}

    def patch(self, *ops, base=None):
        selected = base or self.base
        return CorrectionPatch.model_validate(
            {
                "schemaVersion": "1.0",
                "baseRevisionId": selected.revision_id,
                "expectedStructureSha256": selected.structure_sha256,
                "operations": list(ops),
            }
        )

    def test_label_is_human_overlay_and_machine_text_confidence_and_history_stay_exact(self):
        before = protected_json(self.base)
        result = apply_correction(self.base, self.patch(self.op("title", "relabel", label="Authored section label")))
        self.assertEqual("Authored section label", result.labels[0].label)
        self.assertEqual(self.named["title"], result.labels[0].node_id)
        self.assertEqual(self.base.structure.quality, result.ir.quality)
        self.assertEqual(self.base.structure.text_projections[0].raw_text, result.ir.text_projections[0].raw_text)
        self.assertEqual(before, protected_json(self.base))
        self.assertEqual(
            result, apply_correction(self.base, self.patch(self.op("title", "relabel", label="Authored section label")))
        )
        self.assertEqual(hashlib.sha256(protected_json(result)).hexdigest(), result.result_sha256)

    def test_reorder_moves_complete_sibling_subtree_and_preserves_semantic_targets(self):
        result = apply_correction(
            self.base, self.patch(self.op("figure", "reorder", before_node_id=self.named["paragraph"]))
        )
        names = [row.staged_id for row in result.ir.nodes]
        self.assertLess(names.index(self.named["figure"]), names.index(self.named["caption"]))
        self.assertLess(names.index(self.named["caption"]), names.index(self.named["paragraph"]))
        self.assertEqual(
            self.named["paragraph"], next(n for n in result.ir.nodes if n.staged_id == self.named["marker"]).parent_id
        )
        self.assertEqual(
            self.base.structure.citations[0].reference_candidates, result.ir.citations[0].reference_candidates
        )
        self.assertEqual(tuple(range(len(names))), tuple(n.order for n in result.ir.nodes))

    def test_split_keeps_exact_quote_contributors_and_moves_contained_citation_child(self):
        result = apply_correction(self.base, self.patch(self.op("paragraph", "split", at=11)))
        original = self.nodes[self.named["paragraph"]]
        fragments = [n for n in result.ir.nodes if n.kind == "paragraph"]
        self.assertEqual(2, len(fragments))
        assert fragments[0].text is not None and fragments[1].text is not None
        assert original.text is not None
        self.assertEqual(
            (6, 11, 11, 14),
            (
                fragments[0].text.normalized_range.start,
                fragments[0].text.normalized_range.end,
                fragments[1].text.normalized_range.start,
                fragments[1].text.normalized_range.end,
            ),
        )
        marker = next(n for n in result.ir.nodes if n.staged_id == self.named["marker"])
        assert marker.text is not None
        self.assertEqual(fragments[1].staged_id, marker.parent_id)
        self.assertEqual(original.text.projection_id, marker.text.projection_id)
        self.assertEqual(
            (self.named["paragraph"],) * 2,
            tuple(o.source_node_id for o in result.origins if o.result_node_id in {n.staged_id for n in fragments}),
        )
        with self.assertRaises(DocumentRevisionProblem):
            apply_correction(self.base, self.patch(self.op("paragraph", "split", at=12)))

    def test_unicode_split_uses_codepoints_and_refuses_shared_raw_contributors(self):
        projection = TextProjection.from_raw("text-1", "Cafe\u0301 \U0001f600 tail")
        wire = ir(raw="abcdef").model_dump(mode="json", by_alias=True)
        wire["textProjections"] = [projection.model_dump(mode="json", by_alias=True)]
        wire["nodes"][0]["text"] = {
            "projectionId": "text-1",
            "normalizedRange": {"start": 0, "end": len(projection.normalized_text)},
            "rawRanges": [{"start": 0, "end": len(projection.raw_text)}],
        }
        wire["nodes"][0]["locator"]["rawRanges"] = wire["nodes"][0]["text"]["rawRanges"]
        base = accepted_ir(DocumentIR.model_validate(wire))
        node = base.structure.nodes[0]
        operation = {"op": "split", "nodeId": node.node_id, "expectedNodeSha256": value_sha256(node), "at": 6}
        result = apply_correction(base, self.patch(operation, base=base))
        assert result.ir.nodes[0].text is not None
        self.assertEqual("Café \U0001f600", projection.normalized_text[: result.ir.nodes[0].text.normalized_range.end])
        self.assertEqual(7, result.ir.nodes[0].text.raw_ranges[0].end)
        shared = TextProjection.from_raw("text-1", "\u0344 tail")
        wire["textProjections"] = [shared.model_dump(mode="json", by_alias=True)]
        wire["nodes"][0]["text"]["normalizedRange"]["end"] = len(shared.normalized_text)
        wire["nodes"][0]["text"]["rawRanges"][0]["end"] = len(shared.raw_text)
        wire["nodes"][0]["locator"]["rawRanges"] = wire["nodes"][0]["text"]["rawRanges"]
        expanded = accepted_ir(DocumentIR.model_validate(wire))
        expanded_node = expanded.structure.nodes[0]
        with self.assertRaisesRegex(DocumentRevisionProblem, "document-correction-split-ambiguous"):
            apply_correction(
                expanded,
                self.patch(
                    {
                        "op": "split",
                        "nodeId": expanded_node.node_id,
                        "expectedNodeSha256": value_sha256(expanded_node),
                        "at": 1,
                    },
                    base=expanded,
                ),
            )

    def test_original_page_anchor_accepts_only_geometry_within_the_authenticated_page(self):
        from tests.documents.test_table_figures import accepted_docling, docling_table_figure

        base, _ = accepted_docling(docling_table_figure())
        node = next(n for n in base.structure.nodes if n.kind == "table")
        locator = {
            "kind": "page-region",
            "pageIndex": 0,
            "x0": 1.0,
            "y0": 2.0,
            "x1": 20.0,
            "y1": 30.0,
            "unit": "points",
            "origin": "top-left",
            "frame": "unrotated-source-page",
        }
        operation = {
            "op": "adjust-anchor",
            "nodeId": node.node_id,
            "expectedNodeSha256": value_sha256(node),
            "locator": locator,
        }
        result = apply_correction(base, self.patch(operation, base=base))
        changed = next(n for n in result.ir.nodes if n.staged_id == node.node_id)
        self.assertEqual(locator, changed.locator.model_dump(mode="json", by_alias=True))
        self.assertEqual(base.structure.pages, result.ir.pages)
        self.assertEqual(node.locator, next(n for n in base.structure.nodes if n.node_id == node.node_id).locator)
        with self.assertRaises(DocumentRevisionProblem):
            apply_correction(
                base,
                self.patch({**operation, "locator": {**locator, "x1": base.structure.pages[0].width + 1}}, base=base),
            )

    def test_merge_adjacent_plain_blocks_preserves_source_and_multiple_origins(self):
        wire = ir(raw="one two").model_dump(mode="json", by_alias=True)
        node = wire["nodes"][0]
        node["text"]["normalizedRange"]["end"] = 4
        node["text"]["rawRanges"][0]["end"] = 4
        other = {
            **node,
            "stagedId": "node-2",
            "order": 1,
            "text": {
                "projectionId": "text-1",
                "normalizedRange": {"start": 4, "end": 7},
                "rawRanges": [{"start": 4, "end": 7}],
            },
        }
        wire["nodes"].append(other)
        base = accepted_ir(DocumentIR.model_validate(wire))
        first, second = base.structure.nodes
        operation = {
            "op": "merge",
            "nodeId": first.node_id,
            "expectedNodeSha256": value_sha256(first),
            "withNodeId": second.node_id,
            "expectedWithNodeSha256": value_sha256(second),
        }
        result = apply_correction(base, self.patch(operation, base=base))
        self.assertEqual(1, len(result.ir.nodes))
        self.assertEqual("one two", result.ir.text_projections[0].raw_text)
        self.assertEqual({first.node_id, second.node_id}, {o.source_node_id for o in result.origins})

    def test_reference_rematch_preserves_raw_machine_assertions_and_distinguishes_human_target(self):
        ref = self.base.structure.references[0]
        op = self.op(
            "ref1",
            "reference-rematch",
            reference_id=ref.reference_id,
            expected_reference_sha256=value_sha256(ref),
            work_id=identity(900),
            work_revision_id=identity(901),
        )
        result = apply_correction(self.base, self.patch(op))
        self.assertEqual(ref.raw_text, result.ir.references[0].raw_text)
        self.assertEqual(ref.identifiers, result.ir.references[0].identifiers)
        self.assertEqual("human-proposed", result.reference_matches[0].basis)
        self.assertEqual(identity(901), result.reference_matches[0].work_revision_id)
        self.assertEqual("unverified", result.reference_matches[0].scholarly_verification)

    def test_exclusion_removes_effective_subtree_but_preserves_projection_original_and_explicit_missing_targets(self):
        original = protected_json(self.base)
        result = apply_correction(self.base, self.patch(self.op("ref1", "exclude")))
        self.assertNotIn(self.named["ref1"], {n.staged_id for n in result.ir.nodes})
        self.assertIn(self.named["ref1"], result.excluded_node_ids)
        self.assertEqual((self.base.structure.references[1].reference_id,), result.ir.citations[0].reference_candidates)
        self.assertEqual("candidate", result.ir.citations[0].resolution)
        self.assertEqual(self.base.structure.text_projections[0].raw_text, result.ir.text_projections[0].raw_text)
        self.assertEqual(original, protected_json(self.base))

    def test_wrong_base_old_value_cross_parent_and_invalid_geometry_refuse_entire_patch(self):
        op = self.op("title", "relabel", label="Changed")
        for wire in (
            {**self.patch(op).model_dump(mode="json", by_alias=True), "baseRevisionId": identity(999)},
            {**self.patch(op).model_dump(mode="json", by_alias=True), "expectedStructureSha256": "0" * 64},
            self.patch({**op, "expectedNodeSha256": "0" * 64}).model_dump(mode="json", by_alias=True),
        ):
            with self.subTest(wire=wire), self.assertRaises(DocumentRevisionProblem):
                apply_correction(self.base, CorrectionPatch.model_validate(wire))
        with self.assertRaises(DocumentRevisionProblem):
            apply_correction(self.base, self.patch(self.op("title", "reorder", before_node_id=self.named["caption"])))
        with self.assertRaises(DocumentRevisionProblem):
            apply_correction(
                self.base,
                self.patch(
                    self.op(
                        "caption",
                        "adjust-anchor",
                        locator={
                            "kind": "page-region",
                            "pageIndex": 0,
                            "x0": 0.0,
                            "y0": 0.0,
                            "x1": 10.0,
                            "y1": 10.0,
                            "unit": "points",
                            "origin": "top-left",
                            "frame": "unrotated-source-page",
                        },
                    )
                ),
            )

    def test_closed_operations_and_bounded_labels(self):
        for op in (
            self.op("title", "relabel", label=" "),
            self.op("title", "relabel", label="x" * 161),
            {**self.op("title", "relabel", label="label"), "actorId": identity(999)},
            self.op("title", "arbitrary-code", label="label"),
        ):
            with self.subTest(op=op), self.assertRaises(ValueError):
                self.patch(op)
        with self.assertRaises(ValueError):
            self.patch(*(self.op("title", "relabel", label="label") for _ in range(33)))


if __name__ == "__main__":
    unittest.main()
