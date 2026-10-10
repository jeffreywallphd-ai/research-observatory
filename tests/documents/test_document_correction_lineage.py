"""Authored retained-source relationships after human structural edits.

These are pure adapter-output fixtures, not parser/model or principal proof.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_citations import extract_citation_contexts  # noqa: E402
from research_observatory_core.document_correction_lineage import CorrectionSourceLineage  # noqa: E402
from research_observatory_core.document_corrections import CorrectionPatch, value_sha256  # noqa: E402
from research_observatory_core.document_references import extract_references  # noqa: E402
from research_observatory_core.document_revisions import (  # noqa: E402
    AcceptedDocumentRevision,
    DocumentRevisionProblem,
    content_sha256,
)
from research_observatory_core.document_table_figures import extract_table_figures  # noqa: E402
from research_observatory_core.parsing.native_contracts import NativeStructure  # noqa: E402

from tests.documents.test_citation_contexts import jats, reference  # noqa: E402
from tests.documents.test_reference_entries import JATS, accepted_native  # noqa: E402
from tests.documents.test_table_figures import accepted_docling, docling_table_figure  # noqa: E402
from tests.parsing.contract_fixtures import identity  # noqa: E402
from tests.parsing.test_native_parsing import native_parse  # noqa: E402


def corrected(base, lineage, *operations):
    patch = CorrectionPatch(
        base_revision_id=base.revision_id, expected_structure_sha256=base.structure_sha256, operations=operations
    )
    structure, mapping, result = lineage.preview(base, patch)
    wire = base.model_dump(mode="json", by_alias=True)
    wire.update(
        revisionId=identity(950 + lineage.generation),
        previousRevisionId=base.revision_id,
        structure=structure.model_dump(mode="json", by_alias=True),
        elementIdentities=[m.model_dump(mode="json", by_alias=True) for m in mapping],
        contentSha256=content_sha256(structure),
        structureSha256=value_sha256(structure),
    )
    accepted = AcceptedDocumentRevision.model_validate(wire)
    return accepted, lineage.advance(accepted, result)


def op(node, kind, **values):
    return {"op": kind, "nodeId": node.node_id, "expectedNodeSha256": value_sha256(node), **values}


class CorrectionLineageTests(unittest.TestCase):
    def test_excluded_reference_fields_and_identifiers_cannot_reappear_in_fallback_scans(self):
        raw = jats(
            "<p>Authored synthetic only</p>",
            '<ref id="r1"><mixed-citation>Example (2024). '
            "<article-title>Excluded synthetic title</article-title>. doi:"
            '<pub-id pub-id-type="doi">10.99999/SYNTHETIC-X</pub-id></mixed-citation></ref>'
            '<ref id="r2"><element-citation><article-title>Retained synthetic title</article-title>'
            '<pub-id pub-id-type="doi">10.99999/SYNTHETIC-Y</pub-id></element-citation></ref>',
        )
        base = accepted_native(raw)
        native = native_parse(raw, "jats")[3]
        second_reference_order = next(
            n.order for n in base.structure.nodes if n.node_id == base.structure.references[1].node_id
        )
        removed = tuple(
            op(n, "exclude")
            for n in base.structure.nodes
            if n.source_element_type in {"article-title", "pub-id"} and n.order < second_reference_order
        )
        current, lineage = corrected(base, CorrectionSourceLineage.machine(base), *removed)
        for revision, source_lineage in (
            (current, lineage),
            corrected(current, lineage, op(current.structure.nodes[0], "relabel", label="Human label")),
        ):
            first, retained = extract_references(revision, native_artifact=native, source_lineage=source_lineage)
            self.assertIn("Excluded synthetic title", first.raw_text)
            self.assertNotIn("Excluded synthetic title", [v.value for f in first.fields for v in f.values])
            self.assertEqual(["authors", "year"], [f.name for f in first.fields])
            excluded = next(i for i in first.identifiers if i.assertion.observed == "10.99999/SYNTHETIC-X")
            self.assertFalse(excluded.assertion.active_for_matching)
            self.assertEqual((), excluded.source_spans)
            self.assertEqual(
                "Retained synthetic title", next(f for f in retained.fields if f.name == "title").values[0].value
            )
            self.assertTrue(retained.identifiers[0].assertion.active_for_matching)

    def test_excluded_citation_cannot_reappear_from_parent_projection(self):
        raw = jats('<p>Before <xref ref-type="bibr" rid="r1">[1]</xref> after [1].</p>', reference("r1", "1"))
        base = accepted_native(raw)
        native = native_parse(raw, "jats")[3]
        excluded = next(n for n in base.structure.nodes if n.kind == "citation-marker")
        current, lineage = corrected(base, CorrectionSourceLineage.machine(base), op(excluded, "exclude"))
        entries = extract_references(current, native_artifact=native, source_lineage=lineage)
        citations = extract_citation_contexts(current, entries, native_artifact=native, source_lineage=lineage)
        self.assertEqual(1, len(citations))
        self.assertEqual("[1]", citations[0].normalized_marker)
        self.assertEqual(17, citations[0].marker_span.normalized_range.start)
        self.assertIsNone(citations[0].paragraph)
        self.assertIsNone(citations[0].sentence)
        self.assertIsNone(citations[0].anchor)
        self.assertEqual("excluded-region", citations[0].context_reason)
        parent = next(n for n in current.structure.nodes if n.kind == "paragraph")
        self.assertTrue(lineage.excludes_span(parent.node_id, parent.text))
        successor, later = corrected(current, lineage, op(parent, "relabel", label="Human label"))
        later_entries = extract_references(successor, native_artifact=native, source_lineage=later)
        self.assertEqual(
            1, len(extract_citation_contexts(successor, later_entries, native_artifact=native, source_lineage=later))
        )

    def test_reordered_references_keep_author_role_identifier_scheme_and_original_native_index(self):
        raw = JATS.replace(
            b'<person-group person-group-type="author">',
            b'<person-group person-group-type="editor"><name><surname>NotAuthor</surname></name></person-group>'
            b'<person-group person-group-type="author">',
        )
        base = accepted_native(raw)
        native = native_parse(raw, "jats")[3]
        before = extract_references(base, native_artifact=native)
        nodes = {n.node_id: n for n in base.structure.nodes}
        first, second = base.structure.references
        current, lineage = corrected(
            base,
            CorrectionSourceLineage.machine(base),
            op(nodes[second.node_id], "reorder", beforeNodeId=first.node_id),
        )
        entries = extract_references(current, native_artifact=native, source_lineage=lineage)
        original = next(e for e in entries if e.identifiers)
        author = next(f for f in original.fields if f.name == "authors").values[0]
        self.assertNotIn("NotAuthor", author.value)
        self.assertEqual(
            next(f for f in before[0].fields if f.name == "authors").values[0].native_element_index,
            author.native_element_index,
        )
        self.assertEqual("doi", original.identifiers[0].assertion.scheme)
        self.assertEqual("10.99999/SYNTHETIC-A", original.identifiers[0].assertion.observed)
        assert original.anchor is not None
        self.assertEqual(current.revision_id, original.anchor.revision_id)
        self.assertTrue({e.node_id for e in entries}.isdisjoint({e.node_id for e in before}))

    def test_split_and_cross_projection_merge_keep_repeated_citation_offsets_without_duplicates(self):
        raw = jats("<p>One [1].</p><p>Two [1].</p><p>Cafe\u0301 😀 tail</p>", reference("r1", "1"))
        base = accepted_native(raw)
        native = native_parse(raw, "jats")[3]
        first, second, third = [n for n in base.structure.nodes if n.kind == "paragraph"]
        current, lineage = corrected(
            base,
            CorrectionSourceLineage.machine(base),
            op(first, "merge", withNodeId=second.node_id, expectedWithNodeSha256=value_sha256(second)),
            op(third, "split", at=6),
        )
        refs = extract_references(current, native_artifact=native, source_lineage=lineage)
        contexts = extract_citation_contexts(current, refs, native_artifact=native, source_lineage=lineage)
        self.assertEqual(["[1]", "[1]"], [c.normalized_marker for c in contexts])
        self.assertEqual([4, 12], [c.marker_span.normalized_range.start for c in contexts])
        merged = next(n for n in current.structure.nodes if n.kind == "paragraph" and n.text.normalized_range.end == 16)
        self.assertIsNone(lineage.native_index(merged.node_id))
        intervals = lineage.source_intervals(merged.node_id, merged.text, NativeStructure.model_validate_json(native))
        self.assertEqual(2, len(intervals))
        self.assertEqual(["candidate", "candidate"], [c.resolution for c in contexts])

    def test_native_table_wrapper_caption_label_and_header_survive_reorder_and_exclusion(self):
        raw = (
            b"<article><body><p>Authored.</p><table-wrap><label>T1</label><caption>Authored caption</caption>"
            b"<table><tr><th>Header</th><td>Body</td></tr></table></table-wrap></body></article>"
        )
        base = accepted_native(raw)
        native = native_parse(raw, "jats")[3]
        para = next(n for n in base.structure.nodes if n.kind == "paragraph")
        wrapper = next(n for n in base.structure.nodes if n.source_element_type == "table-wrap")
        current, lineage = corrected(
            base,
            CorrectionSourceLineage.machine(base),
            op(wrapper, "reorder", beforeNodeId=para.node_id),
            op(para, "exclude"),
        )
        old = extract_table_figures(base, native_artifact=native)[0]
        entry = extract_table_figures(current, native_artifact=native, source_lineage=lineage)[0]
        self.assertEqual(old.captions[0].normalized_text, entry.captions[0].normalized_text)
        self.assertEqual(old.labels[0].normalized_text, entry.labels[0].normalized_text)
        self.assertEqual(["reported-header", "reported-body"], [c.header_state for c in entry.cells])
        assert entry.captions[0].anchor is not None
        self.assertEqual(current.revision_id, entry.captions[0].anchor.revision_id)

    def test_docling_retained_relationships_authenticate_original_then_map_corrected_ids(self):
        base, artifact = accepted_docling(docling_table_figure())
        node = next(n for n in base.structure.nodes if n.kind == "table")
        figure = next(n for n in base.structure.nodes if n.kind == "figure")
        current, lineage = corrected(
            base, CorrectionSourceLineage.machine(base), op(figure, "reorder", beforeNodeId=node.node_id)
        )
        old = extract_table_figures(base, docling_artifact=artifact)
        entries = extract_table_figures(current, docling_artifact=artifact, source_lineage=lineage)
        self.assertEqual(
            sorted(e.captions[0].normalized_text for e in old), sorted(e.captions[0].normalized_text for e in entries)
        )
        self.assertTrue(all(e.captions[0].node_id in {n.node_id for n in current.structure.nodes} for e in entries))
        with self.assertRaises(ValueError):
            extract_table_figures(
                current,
                docling_artifact=artifact.replace(b"Synthetic caption", b"Changed caption!!"),
                source_lineage=lineage,
            )

    def test_cross_revision_lineage_and_substituted_native_receipt_are_denied(self):
        base = accepted_native(JATS)
        node = next(n for n in base.structure.nodes if n.kind == "paragraph")
        current, lineage = corrected(base, CorrectionSourceLineage.machine(base), op(node, "split", at=8))
        with self.assertRaises(DocumentRevisionProblem):
            lineage.validate(base)
        with self.assertRaises(ValueError):
            extract_references(
                current, native_artifact=native_parse(JATS.replace(b"2024", b"2025"), "jats")[3], source_lineage=lineage
            )


if __name__ == "__main__":
    unittest.main()
