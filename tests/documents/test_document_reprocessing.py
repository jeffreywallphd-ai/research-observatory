"""Authored reparse differences and explicit correction mappings; no model run."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.anchors.contracts import AnchorSelection  # noqa: E402
from research_observatory_core.anchors.contracts import build_target as derive_source_anchor  # noqa: E402
from research_observatory_core.document_corrections import (  # noqa: E402
    CorrectionPatch,
    CorrectionPreviewBase,
    CorrectionSave,
    RelabelCorrection,
    apply_correction,
    value_sha256,
)
from research_observatory_core.document_reprocessing import (  # noqa: E402
    anchor_candidates,
    compare_structures,
    mapped_patch,
    node_text,
    operation_id,
)
from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.parsing.contracts import DocumentIR, ParserWarning  # noqa: E402

from tests.documents.test_document_corrections import accepted_ir  # noqa: E402
from tests.parsing.contract_fixtures import ir, rich_ir_wire  # noqa: E402


class DocumentReprocessingTests(unittest.TestCase):
    def test_nested_collections_and_retained_strings_are_counted_before_copying(self):
        base = accepted_ir(DocumentIR.model_validate(rich_ir_wire())).structure
        warnings = tuple(
            ParserWarning(code="authored-warning", severity="warning", node_id=None, detail=None) for _ in range(101)
        )
        large = base.model_copy(update={"quality": base.quality.model_copy(update={"warnings": warnings})})
        with (
            patch("research_observatory_core.document_reprocessing.MAX_REPROCESSING_ITEMS", 100),
            patch("research_observatory_core.document_reprocessing.structural_signature") as copy,
            self.assertRaises(DocumentRevisionProblem),
        ):
            compare_structures(base, large)
        copy.assert_not_called()
        with (
            patch("research_observatory_core.document_reprocessing.MAX_REPROCESSING_TEXT", 1000),
            patch("research_observatory_core.document_reprocessing.structural_signature") as copy,
            self.assertRaises(DocumentRevisionProblem),
        ):
            compare_structures(base, base)
        copy.assert_not_called()

    def test_overlapping_spans_refuse_before_repeated_text_copies(self):
        base = accepted_ir(ir(raw="A" * 100)).structure
        nodes = tuple(base.nodes[0].model_copy(update={"node_id": new_uuid_v7(), "order": i}) for i in range(51))
        overlapping = base.model_copy(update={"nodes": nodes})
        with (
            patch("research_observatory_core.document_reprocessing.MAX_REPROCESSING_TEXT", 5000),
            patch("research_observatory_core.document_reprocessing.node_text", wraps=node_text) as copy,
            self.assertRaises(DocumentRevisionProblem),
        ):
            compare_structures(overlapping, base)
        copy.assert_not_called()

    def test_identical_text_with_fresh_ids_is_unchanged_and_originals_are_immutable(self):
        old, new = accepted_ir(ir()), accepted_ir(ir())
        before = old.model_dump_json()
        diff = compare_structures(old.structure, new.structure)
        self.assertTrue(diff)
        self.assertTrue(all(item.state == "unchanged" for item in diff))
        self.assertEqual(before, old.model_dump_json())

    def test_text_structure_reference_and_geometry_changes_are_separate(self):
        old = accepted_ir(DocumentIR.model_validate(rich_ir_wire()))
        new = accepted_ir(ir(raw="Changed authored text"))
        diff = compare_structures(old.structure, new.structure)
        self.assertIn("reference", {item.kind for item in diff})
        self.assertTrue({"added", "removed", "modified"}.intersection(item.state for item in diff))

    def test_table_and_citation_structure_changes_with_same_text_are_visible(self):
        old = accepted_ir(DocumentIR.model_validate(rich_ir_wire())).structure
        new = old.model_copy(
            update={
                "tables": (old.tables[0].model_copy(update={"rows": old.tables[0].rows + 1}),),
                "citations": (
                    old.citations[0].model_copy(update={"resolution": "unresolved", "reference_candidates": ()}),
                ),
            }
        )
        diff = {item.old_id: item.state for item in compare_structures(old, new)}
        self.assertEqual("modified", diff[old.tables[0].node_id])
        self.assertEqual("modified", diff[old.citations[0].node_id])

    def test_anchor_quote_context_is_advisory_unique_missing_or_ambiguous(self):
        old = accepted_ir(ir(raw="Unique authored quotation"))
        target = derive_source_anchor(
            old, AnchorSelection(revision_id=old.revision_id, node_id=old.structure.nodes[0].node_id)
        )

        def candidate(raw):
            base = accepted_ir(ir(raw=raw))
            return CorrectionPreviewBase(
                revision_id=base.revision_id,
                result=base.result,
                structure_sha256=base.structure_sha256,
                element_identities=base.element_identities,
                structure=base.structure,
            )

        unique = anchor_candidates(
            new_uuid_v7(), target, candidate("Unique authored quotation"), old_locator=old.structure.nodes[0].locator
        )
        self.assertIn(unique.state, {"unchanged", "moved"})
        self.assertEqual(
            "unresolvable", anchor_candidates(new_uuid_v7(), target, candidate("Different quotation")).state
        )
        assert target.quote is not None
        repeated = target.model_copy(update={"quote": target.quote.model_copy(update={"prefix": "", "suffix": ""})})
        self.assertEqual(
            "ambiguous",
            anchor_candidates(
                new_uuid_v7(), repeated, candidate("Unique authored quotation Unique authored quotation")
            ).state,
        )

    def test_omitted_duplicate_or_substituted_obligation_refuses_mapping(self):
        old, new = accepted_ir(ir()), accepted_ir(ir())
        node = old.structure.nodes[0]
        operation = RelabelCorrection(
            op="relabel", node_id=node.node_id, expected_node_sha256=value_sha256(node), label="Retained human label"
        )
        draft = CorrectionSave(
            command_id=new_uuid_v7(),
            draft_id=None,
            expected_draft_revision_id=None,
            patch=CorrectionPatch(
                base_revision_id=old.revision_id,
                expected_structure_sha256=old.structure_sha256,
                operations=(operation,),
            ),
            rationale="Authored rationale",
        )
        # The immutable record identity is the obligation origin; this authored
        # unit only needs these literal fields, no actor or publication authority.
        from types import SimpleNamespace

        record = SimpleNamespace(revision_id=new_uuid_v7(), patch=draft.patch)
        candidate = CorrectionPreviewBase(
            revision_id=new.revision_id,
            result=new.result,
            structure_sha256=new.structure_sha256,
            element_identities=new.element_identities,
            structure=new.structure,
        )
        from research_observatory_core.document_reprocessing import ReprocessingMapping

        good = ReprocessingMapping(
            obligation_id=operation_id(record.revision_id, 0, operation),
            node_id=new.structure.nodes[0].node_id,
            related_node_id=None,
            reference_id=None,
        )
        for mappings in ((), (good, good), (good.model_copy(update={"obligation_id": "0" * 64}),)):
            with self.assertRaises(DocumentRevisionProblem):
                mapped_patch(record, candidate, mappings)
        self.assertEqual(new.structure.nodes[0].node_id, mapped_patch(record, candidate, (good,)).operations[0].node_id)

    def test_mapping_preserves_each_operation_family_and_applies_to_exact_new_targets(self):
        from types import SimpleNamespace

        from research_observatory_core.document_reprocessing import ReprocessingMapping

        from tests.documents.test_document_corrections import DocumentCorrectionTests

        fixture = DocumentCorrectionTests(methodName="runTest")
        fixture.setUp()
        rich = DocumentIR.model_validate(rich_ir_wire())
        ref = fixture.base.structure.references[0]
        cases = [
            (rich, fixture.op("title", "relabel", label="Retained label"), "title", None, None),
            (
                rich,
                fixture.op("figure", "reorder", before_node_id=fixture.named["paragraph"]),
                "figure",
                "paragraph",
                None,
            ),
            (rich, fixture.op("paragraph", "split", at=11), "paragraph", None, None),
            (rich, fixture.op("ref1", "exclude"), "ref1", None, None),
            (
                rich,
                fixture.op(
                    "ref1",
                    "reference-rematch",
                    reference_id=ref.reference_id,
                    expected_reference_sha256=value_sha256(ref),
                    work_id=new_uuid_v7(),
                    work_revision_id=new_uuid_v7(),
                ),
                "ref1",
                None,
                0,
            ),
        ]
        for value, operation, name, related, reference_index in cases:
            with self.subTest(operation=operation["op"]):
                new = accepted_ir(value)
                named = {m.staged_id: m.canonical_id for m in new.element_identities}
                record = SimpleNamespace(revision_id=new_uuid_v7(), patch=fixture.patch(operation))
                candidate = CorrectionPreviewBase(
                    revision_id=new.revision_id,
                    result=new.result,
                    structure_sha256=new.structure_sha256,
                    element_identities=new.element_identities,
                    structure=new.structure,
                )
                mapping = ReprocessingMapping(
                    obligation_id=operation_id(record.revision_id, 0, record.patch.operations[0]),
                    node_id=named[name],
                    related_node_id=None if related is None else named[related],
                    reference_id=None
                    if reference_index is None
                    else new.structure.references[reference_index].reference_id,
                )
                mapped = mapped_patch(record, candidate, (mapping,))
                result = apply_correction(candidate, mapped)
                self.assertEqual(operation["op"], mapped.operations[0].op)
                self.assertTrue(result.ir.nodes)
                for field in ("label", "at", "workId", "workRevisionId"):
                    if field in operation:
                        self.assertEqual(operation[field], mapped.operations[0].model_dump(by_alias=True)[field])

        # Merge uses a separate authored pair because rich paragraph children
        # deliberately cannot be silently merged by the correction contract.
        wire = ir(raw="one two").model_dump(mode="json", by_alias=True)
        first = wire["nodes"][0]
        first["text"]["normalizedRange"]["end"] = 4
        first["text"]["rawRanges"][0]["end"] = 4
        wire["nodes"].append(
            {
                **first,
                "stagedId": "node-2",
                "order": 1,
                "text": {
                    "projectionId": "text-1",
                    "normalizedRange": {"start": 4, "end": 7},
                    "rawRanges": [{"start": 4, "end": 7}],
                },
            }
        )
        old, new = accepted_ir(DocumentIR.model_validate(wire)), accepted_ir(DocumentIR.model_validate(wire))
        first, other = old.structure.nodes
        patch_value = CorrectionPatch.model_validate(
            {
                "baseRevisionId": old.revision_id,
                "expectedStructureSha256": old.structure_sha256,
                "operations": [
                    {
                        "op": "merge",
                        "nodeId": first.node_id,
                        "expectedNodeSha256": value_sha256(first),
                        "withNodeId": other.node_id,
                        "expectedWithNodeSha256": value_sha256(other),
                    }
                ],
            }
        )
        record = SimpleNamespace(revision_id=new_uuid_v7(), patch=patch_value)
        candidate = CorrectionPreviewBase(
            revision_id=new.revision_id,
            result=new.result,
            structure_sha256=new.structure_sha256,
            element_identities=new.element_identities,
            structure=new.structure,
        )
        mapping = ReprocessingMapping(
            obligation_id=operation_id(record.revision_id, 0, patch_value.operations[0]),
            node_id=new.structure.nodes[0].node_id,
            related_node_id=new.structure.nodes[1].node_id,
            reference_id=None,
        )
        self.assertEqual(1, len(apply_correction(candidate, mapped_patch(record, candidate, (mapping,))).ir.nodes))

        from tests.documents.test_table_figures import accepted_docling, docling_table_figure

        old, _ = accepted_docling(docling_table_figure())
        new, _ = accepted_docling(docling_table_figure())
        table = next(n for n in old.structure.nodes if n.kind == "table")
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
        patch_value = CorrectionPatch.model_validate(
            {
                "baseRevisionId": old.revision_id,
                "expectedStructureSha256": old.structure_sha256,
                "operations": [
                    {
                        "op": "adjust-anchor",
                        "nodeId": table.node_id,
                        "expectedNodeSha256": value_sha256(table),
                        "locator": locator,
                    }
                ],
            }
        )
        record = SimpleNamespace(revision_id=new_uuid_v7(), patch=patch_value)
        candidate = CorrectionPreviewBase(
            revision_id=new.revision_id,
            result=new.result,
            structure_sha256=new.structure_sha256,
            element_identities=new.element_identities,
            structure=new.structure,
        )
        table = next(n for n in new.structure.nodes if n.kind == "table")
        mapping = ReprocessingMapping(
            obligation_id=operation_id(record.revision_id, 0, patch_value.operations[0]),
            node_id=table.node_id,
            related_node_id=None,
            reference_id=None,
        )
        result = apply_correction(candidate, mapped_patch(record, candidate, (mapping,)))
        self.assertEqual(
            locator, next(n for n in result.ir.nodes if n.staged_id == table.node_id).locator.model_dump(by_alias=True)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
