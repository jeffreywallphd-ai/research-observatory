"""Revision-scoped identity and lossless structure; synthetic authored IR."""

import hashlib
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_revisions import (  # noqa: E402
    AcceptedDocumentRevision,
    CanonicalDocumentStructure,
    DocumentRevisionAcceptance,
    DocumentRevisionProblem,
    RetainedParseResultReceipt,
    acceptance_eligible,
    canonicalize_structure,
    content_sha256,
    protected_json,
)
from research_observatory_core.domain_contracts import is_uuid_v7  # noqa: E402
from research_observatory_core.parsing.contracts import DocumentIR, TextProjection  # noqa: E402

from tests.parsing import contract_fixtures as fixtures  # noqa: E402


class DocumentRevisionContractTests(unittest.TestCase):
    def rich(self):
        return DocumentIR.model_validate(fixtures.rich_ir_wire())

    def test_core_ids_are_unique_remapped_and_stable_in_serialized_revision(self):
        original = self.rich()
        structure, mapping = canonicalize_structure(original)
        restored = CanonicalDocumentStructure.model_validate_json(structure.model_dump_json(by_alias=True))
        self.assertEqual(structure, restored)
        ids = [item.canonical_id for item in mapping]
        self.assertTrue(all(is_uuid_v7(value) for value in ids))
        self.assertEqual(len(ids), len(set(ids)))
        by_role = {(item.role, item.staged_id): item.canonical_id for item in mapping}
        for old, new in zip(original.nodes, structure.nodes, strict=True):
            self.assertEqual(by_role["node", old.staged_id], new.node_id)
            self.assertEqual(by_role.get(("node", old.parent_id)), new.parent_id)
            self.assertEqual(old.kind, new.kind)
            self.assertEqual(old.order, new.order)
            self.assertEqual(old.source_element_type, new.source_element_type)
            if old.text:
                self.assertEqual(by_role["projection", old.text.projection_id], new.text.projection_id)
                self.assertEqual(old.text.normalized_range, new.text.normalized_range)
                self.assertEqual(old.text.raw_ranges, new.text.raw_ranges)
        self.assertEqual(original.binding, structure.binding)
        self.assertEqual(original.raw_artifacts, structure.raw_artifacts)
        self.assertEqual(original.pages, structure.pages)
        self.assertEqual(
            [by_role["reference", value] for value in original.citations[0].reference_candidates],
            list(structure.citations[0].reference_candidates),
        )
        self.assertEqual(by_role["node", original.tables[0].cells[0].node_id], structure.tables[0].cells[0].node_id)
        self.assertEqual(by_role["node", original.figures[0].node_id], structure.figures[0].node_id)
        self.assertEqual(original.figures[0].preview_stage_id, structure.figures[0].preview_stage_id)

    def test_reparse_never_reuses_structural_ids_even_with_identical_machine_content(self):
        first, one = canonicalize_structure(self.rich())
        second, two = canonicalize_structure(self.rich())
        self.assertTrue({item.canonical_id for item in one}.isdisjoint(item.canonical_id for item in two))
        self.assertEqual(first.text_projections[0].raw_text, second.text_projections[0].raw_text)

    def test_raw_nfc_codepoints_and_sentence_kind_are_preserved(self):
        value = fixtures.ir().model_dump(mode="json", by_alias=True)
        projection = TextProjection.from_raw("text-1", "Cafe\u0301\r\n\U0001f4da")
        value["textProjections"] = [projection.model_dump(mode="json", by_alias=True)]
        value["nodes"][0]["kind"] = "sentence"
        value["nodes"][0]["text"].update(
            normalizedRange={"start": 0, "end": len(projection.normalized_text)},
            rawRanges=[{"start": 0, "end": len(projection.raw_text)}],
        )
        value["nodes"][0]["locator"]["rawRanges"] = [{"start": 0, "end": len(projection.raw_text)}]
        original = DocumentIR.model_validate(value)
        structure, _ = canonicalize_structure(original)
        current = structure.text_projections[0]
        self.assertEqual(projection.raw_text, current.raw_text)
        self.assertEqual("Caf\u00e9\n\U0001f4da", current.normalized_text)
        self.assertEqual(projection.mappings, current.mappings)
        self.assertEqual("sentence", structure.nodes[0].kind)
        self.assertEqual(6, structure.nodes[0].text.normalized_range.end)

    def test_incomplete_structure_is_denied_but_ambiguity_remains_for_human_review(self):
        value = self.rich().model_dump(mode="json", by_alias=True)
        self.assertTrue(acceptance_eligible(DocumentIR.model_validate(value)))
        # An unresolved reference/unknown confidence is not a fabricated failure.
        self.assertEqual("ambiguous", value["citations"][0]["resolution"])
        for code in ("parser-partial-output", "missing-text-ocr-disabled"):
            altered = dict(value, quality=dict(value["quality"]))
            altered["quality"]["warnings"] = [{"code": code, "severity": "warning", "nodeId": None, "detail": None}]
            partial = DocumentIR.model_validate(altered)
            self.assertFalse(acceptance_eligible(partial))
            with self.assertRaises(DocumentRevisionProblem):
                canonicalize_structure(partial)
        self.assertFalse(acceptance_eligible(fixtures.ir(raw="")))

    def test_identity_factory_collision_is_rejected_and_canonical_dangling_link_denies(self):
        with self.assertRaises(DocumentRevisionProblem):
            canonicalize_structure(self.rich(), identity_factory=lambda: fixtures.identity(800))
        structure, _ = canonicalize_structure(self.rich())
        wire = structure.model_dump(mode="json", by_alias=True)
        wire["nodes"][0]["nodeId"] = "parser-selected-node"
        with self.assertRaises(ValueError):
            CanonicalDocumentStructure.model_validate(wire)

    def test_portable_revision_shapes_and_semantic_authority_are_separate(self):
        structure, mapping = canonicalize_structure(self.rich())
        receipt = RetainedParseResultReceipt(
            result_id=fixtures.identity(801),
            revision_id=fixtures.identity(802),
            binding=structure.binding,
            object_sha256="a" * 64,
            byte_length=1,
        )
        command = DocumentRevisionAcceptance(
            command_id=fixtures.identity(803),
            result_id=receipt.result_id,
            expected_current_revision_id=fixtures.identity(804),
            confirmation_sha256="b" * 64,
            decision="accept-structure",
        )
        accepted = AcceptedDocumentRevision(
            project_id=structure.binding.source.project_id,
            document_id=structure.binding.source.document_id,
            revision_id=fixtures.identity(805),
            previous_revision_id=command.expected_current_revision_id,
            result=receipt,
            decision_id=fixtures.identity(806),
            decision_revision_id=fixtures.identity(807),
            command_id=command.command_id,
            command_sha256="c" * 64,
            accepted_by=fixtures.identity(808),
            accepted_at="2026-10-07T00:00:00.000Z",
            intent_revision_id=fixtures.identity(809),
            intent_sha256="d" * 64,
            policy_sha256="e" * 64,
            content_sha256=content_sha256(structure),
            structure_sha256=hashlib.sha256(protected_json(structure)).hexdigest(),
            element_identities=mapping,
            structure=structure,
        )
        for name, model in (
            ("document-structure.v1.schema.json", structure),
            ("document-revision.v1.schema.json", accepted),
            ("document-revision-acceptance.v1.schema.json", command),
            ("retained-parse-result.v1.schema.json", receipt),
        ):
            schema = json.loads((ROOT / "packages/contracts/documents" / name).read_text())
            Draft202012Validator.check_schema(schema)
            self.assertTrue(schema["x-research-observatory-semanticRules"])
            validator = Draft202012Validator(schema)
            wire = model.model_dump(mode="json", by_alias=True)
            validator.validate(wire)
            wire["claimedActor"] = "caller-must-not-supply-authority"
            self.assertTrue(list(validator.iter_errors(wire)))
        wire = accepted.model_dump(mode="json", by_alias=True)
        wire["contentSha256"] = "0" * 64
        Draft202012Validator(
            schema=json.loads((ROOT / "packages/contracts/documents/document-revision.v1.schema.json").read_text())
        ).validate(wire)
        with self.assertRaises(ValueError):
            AcceptedDocumentRevision.model_validate(wire)
        wire = accepted.model_dump(mode="json", by_alias=True)
        wire["acceptedAt"] = "2026-99-07T00:00:00.000Z"
        with self.assertRaises(ValueError):
            AcceptedDocumentRevision.model_validate(wire)
        wire = structure.model_dump(mode="json", by_alias=True)
        wire["citations"][0]["referenceCandidates"] = [fixtures.identity(999)]
        with self.assertRaises(ValueError):
            CanonicalDocumentStructure.model_validate(wire)


if __name__ == "__main__":
    unittest.main(verbosity=2)
