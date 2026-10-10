"""Authored synthetic citation expectations; no model or scholarly-quality proof."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_citations import extract_citation_contexts  # noqa: E402
from research_observatory_core.document_references import extract_references  # noqa: E402
from research_observatory_core.document_revisions import protected_json  # noqa: E402

from tests.documents.test_reference_entries import accepted_native  # noqa: E402
from tests.parsing.test_native_parsing import native_parse  # noqa: E402


def jats(body, references):
    return ("<article><body>" + body + "</body><back><ref-list>" + references + "</ref-list></back></article>").encode()


def reference(identifier, label, author="Example", year="2024"):
    return (
        f'<ref id="{identifier}"><label>{label}</label><element-citation>'
        '<person-group person-group-type="author"><name>'
        f"<surname>{author}</surname><given-names>Ada</given-names></name></person-group>"
        f"<year>{year}</year><article-title>Synthetic reference; NOT A SCHOLARLY SOURCE.</article-title>"
        "</element-citation></ref>"
    )


def derive(raw, format="jats", *, artifact=True):
    accepted = accepted_native(raw, format)
    native = native_parse(raw, format)[3] if artifact else None
    before = protected_json(accepted)
    references = extract_references(accepted, native_artifact=native)
    contexts = extract_citation_contexts(accepted, references, native_artifact=native)
    assert before == protected_json(accepted)
    return accepted, contexts


class CitationContextTests(unittest.TestCase):
    def test_explicit_group_is_distinct_from_duplicate_id_and_partial_target_set(self):
        refs = reference("r1", "1") + reference("r2", "2", "Sample")
        accepted, contexts = derive(
            jats('<p>Synthetic result <xref ref-type="bibr" rid="r1 r2">[1,2]</xref>.</p>', refs)
        )
        entry = contexts[0]
        self.assertEqual("candidate", entry.resolution)
        self.assertEqual(["candidate", "candidate"], [g.resolution for g in entry.targets])
        self.assertEqual(
            [r.reference_id for r in accepted.structure.references], [g.reference_ids[0] for g in entry.targets]
        )
        _, partial = derive(jats('<p>See <xref ref-type="bibr" rid="r1 missing">[1,9]</xref>.</p>', refs))
        self.assertEqual("unresolved", partial[0].resolution)
        self.assertEqual(["candidate", "unresolved"], [g.resolution for g in partial[0].targets])
        self.assertEqual(1, len(partial[0].targets[0].reference_ids))
        _, duplicate = derive(
            jats('<p>See <xref ref-type="bibr" rid="r1">[1]</xref>.</p>', refs + reference("r1", "3"))
        )
        self.assertEqual("ambiguous", duplicate[0].resolution)
        self.assertEqual(2, len(duplicate[0].targets[0].reference_ids))

    def test_repeated_markers_keep_distinct_exact_parent_ranges_and_unverified_source(self):
        raw = jats(
            '<p>Synthetic e\u0301 😀\r\nFirst <xref ref-type="bibr" rid="r1">[1]</xref>. '
            'Second <xref ref-type="bibr" rid="r1">[1]</xref>.</p>',
            reference("r1", "1"),
        )
        accepted, contexts = derive(raw)
        self.assertEqual(2, len(contexts))
        self.assertNotEqual(contexts[0].paragraph.marker_range, contexts[1].paragraph.marker_range)
        self.assertEqual([0, 1], [c.order for c in contexts])
        for entry in contexts:
            self.assertEqual("[1]", entry.raw_marker)
            self.assertEqual("[1]", entry.anchor.quote.exact)
            self.assertEqual(accepted.revision_id, entry.anchor.revision_id)
            self.assertEqual("unverified", entry.scholarly_verification)
            part = entry.paragraph
            left, right = part.marker_range.start, part.marker_range.end
            origin = part.text_span.normalized_range.start
            self.assertEqual("[1]", part.normalized_text[left - origin : right - origin])
            self.assertIn("😀", part.raw_text)
            self.assertIn("\r\n", part.raw_text)
            self.assertIsNotNone(entry.sentence)

    def test_cross_element_composition_does_not_invent_parent_marker_offsets(self):
        _, contexts = derive(
            jats('<p>Synthetic e<xref ref-type="bibr" rid="r1">\u0301</xref> context.</p>', reference("r1", "1"))
        )
        entry = contexts[0]
        self.assertEqual("\u0301", entry.raw_marker)
        self.assertEqual("\u0301", entry.anchor.quote.exact)
        self.assertIsNone(entry.paragraph.marker_range)
        self.assertEqual("normalization-boundary", entry.context_reason)
        self.assertIn("é", entry.paragraph.normalized_text)

    def test_numeric_group_range_missing_and_duplicate_labels(self):
        refs = reference("r1", "1") + reference("r3", "3") + reference("r4", "4")
        _, contexts = derive(jats("<p>Synthetic [1, 3\u20134]. Missing [1, 9].</p>", refs))
        self.assertEqual(2, len(contexts))
        self.assertEqual("candidate", contexts[0].resolution)
        self.assertEqual(3, len(contexts[0].targets))
        self.assertEqual("unresolved", contexts[1].resolution)
        self.assertEqual(["candidate", "unresolved"], [g.resolution for g in contexts[1].targets])
        _, duplicate = derive(jats("<p>Synthetic [1].</p>", refs + reference("r5", "1")))
        self.assertEqual("ambiguous", duplicate[0].resolution)

    def test_unreported_numbering_is_not_inferred_from_reference_order(self):
        _, contexts = derive(
            jats(
                "<p>Synthetic [1].</p>",
                '<ref id="r1"><mixed-citation>Synthetic unnumbered reference.</mixed-citation></ref>',
            )
        )
        self.assertEqual("unresolved", contexts[0].resolution)
        self.assertEqual((), contexts[0].targets[0].reference_ids)

    def test_author_year_narrative_group_and_duplicate_are_inferred_candidates(self):
        refs = reference("r1", "1") + reference("r2", "2", "Sample", "2023")
        _, contexts = derive(jats("<p>Synthetic Example (2024). Group (Example, 2024; Sample, 2023).</p>", refs))
        self.assertEqual(["candidate", "candidate"], [c.resolution for c in contexts])
        self.assertEqual(["narrative", "author-year"], [c.style for c in contexts])
        self.assertEqual([1, 2], [len(c.targets) for c in contexts])
        self.assertTrue(all(c.knowledge_status == "inferred" for c in contexts))
        _, duplicate = derive(jats("<p>Synthetic (Example, 2024).</p>", refs + reference("r3", "3")))
        self.assertEqual("ambiguous", duplicate[0].resolution)

    def test_reported_superscript_and_footnote_body_do_not_reinterpret_footnote_numbers(self):
        raw = jats(
            '<p>Synthetic <xref ref-type="bibr" rid="r1"><sup>1</sup></xref>; '
            'note <xref ref-type="fn" rid="f1"><sup>1</sup></xref>.</p>'
            '<fn id="f1"><p>Synthetic note cites [1].</p></fn>',
            reference("r1", "1"),
        )
        _, contexts = derive(raw)
        reported = [c for c in contexts if c.canonical_citation_id]
        self.assertEqual(1, len(reported))
        self.assertEqual("superscript", reported[0].style)
        self.assertEqual("candidate", reported[0].resolution)
        self.assertTrue(any(c.raw_marker == "[1]" and c.resolution == "candidate" for c in contexts))
        self.assertTrue(
            all(
                c.resolution == "unresolved"
                for c in contexts
                if c.style == "superscript" and not c.canonical_citation_id
            )
        )

    def test_bracketed_nonbibliographic_callouts_and_unreported_superscripts_do_not_gain_targets(self):
        cases = (
            '<p>Synthetic <xref ref-type="fn" rid="f1">[1]</xref>.</p><fn id="f1"><p>Note body cites [1].</p></fn>',
            "<p>Synthetic <sup>[1]</sup>.</p>",
        )
        for body in cases:
            with self.subTest(body=body):
                _, contexts = derive(jats(body, reference("r1", "1")))
                if "xref" in body:
                    self.assertEqual(1, len(contexts))
                    self.assertIn("Note body", contexts[0].paragraph.raw_text)
                    self.assertEqual("candidate", contexts[0].resolution)
                else:
                    self.assertEqual(1, len(contexts))
                    self.assertEqual("superscript", contexts[0].style)
                    self.assertEqual("unresolved", contexts[0].resolution)

    def test_unavailable_native_offsets_do_not_reinterpret_nested_superscript_from_parent(self):
        _, contexts = derive(
            jats("<p>Synthetic <italic><sup>[1]</sup></italic>.</p>", reference("r1", "1")), artifact=False
        )
        self.assertEqual(1, len(contexts))
        self.assertEqual("superscript", contexts[0].style)
        self.assertEqual("unresolved", contexts[0].resolution)

    def test_native_detail_unavailable_keeps_multi_candidate_ir_ambiguity(self):
        _, contexts = derive(
            jats(
                '<p>Synthetic <xref ref-type="bibr" rid="r1 r2">[1,2]</xref>.</p>',
                reference("r1", "1") + reference("r2", "2"),
            ),
            artifact=False,
        )
        self.assertEqual("ambiguous", contexts[0].resolution)

    def test_nested_reported_marker_without_native_offsets_is_not_reinferred_in_parent(self):
        _, contexts = derive(
            jats(
                '<p>Synthetic <italic><xref ref-type="bibr" rid="r1 r2">[1,2]</xref></italic>.</p>',
                reference("r1", "1") + reference("r2", "2"),
            ),
            artifact=False,
        )
        self.assertEqual(1, len(contexts))
        self.assertEqual("ambiguous", contexts[0].resolution)
        self.assertIsNone(contexts[0].paragraph.marker_range)
        self.assertEqual("normalization-boundary", contexts[0].context_reason)

    def test_inferred_observation_cannot_claim_a_reported_canonical_identity(self):
        _, contexts = derive(jats('<p>Synthetic <xref ref-type="bibr" rid="r1">[1]</xref>.</p>', reference("r1", "1")))
        value = contexts[0].model_dump() | {"knowledge_status": "inferred"}
        with self.assertRaisesRegex(ValueError, "citation-reported-identity-missing"):
            type(contexts[0]).model_validate(value)

    def test_cancellation_preserves_the_accepted_document(self):
        accepted = accepted_native(jats("<p>Synthetic [1].</p>", reference("r1", "1")))
        before = protected_json(accepted)
        with self.assertRaisesRegex(ValueError, "citation-operation-cancelled"):
            extract_citation_contexts(accepted, extract_references(accepted), cancelled=lambda: True)
        self.assertEqual(before, protected_json(accepted))

    def test_tei_and_html_reported_targets_keep_partial_and_external_links_unresolved(self):
        cases = [
            (
                "tei",
                b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>Synthetic '
                b'<ref type="bibr" target="#r1 #missing">[1,9]</ref>.</p></body><back>'
                b'<listBibl><bibl xml:id="r1">[1] Synthetic reference.</bibl></listBibl></back></text></TEI>',
            ),
            (
                "html",
                b'<html><body><p>Synthetic <a role="doc-biblioref" href="#r1">[1]</a>. External '
                b'<a role="doc-biblioref" href="https://example.invalid/r1">[1]</a>.</p>'
                b'<div role="doc-bibliography"><div role="doc-biblioentry" id="r1">'
                b"[1] Synthetic reference.</div></div></body></html>",
            ),
        ]
        for format, raw in cases:
            with self.subTest(format=format):
                _, contexts = derive(raw, format)
                reported = [c for c in contexts if c.canonical_citation_id]
                if format == "tei":
                    self.assertEqual("unresolved", reported[0].resolution)
                    self.assertEqual(["candidate", "unresolved"], [g.resolution for g in reported[0].targets])
                else:
                    self.assertEqual(["candidate", "unresolved"], [c.resolution for c in reported])

    def test_canonical_tei_reference_targets_do_not_require_optional_type_attribute(self):
        raw = (
            b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>Synthetic '
            b'<ref target="#r1">[1]</ref>. Partial <ref target="#r1 #missing">[1,9]</ref>.</p>'
            b'</body><back><listBibl><bibl xml:id="r1">[1] Synthetic reference.</bibl>'
            b"</listBibl></back></text></TEI>"
        )
        accepted, contexts = derive(raw, "tei")
        self.assertEqual(2, len(accepted.structure.citations))
        self.assertEqual(["candidate", "unresolved"], [c.resolution for c in contexts])
        self.assertEqual(["candidate", "unresolved"], [g.resolution for g in contexts[1].targets])

    def test_hostile_range_does_not_expand_unbounded_and_nfc_reordering_keeps_raw(self):
        _, contexts = derive(
            jats("<p>Synthetic a\u0315\u0300 😀 [1]. Hostile [1\u2013999999].</p>", reference("r1", "1"))
        )
        self.assertEqual(["candidate", "unresolved"], [c.resolution for c in contexts])
        self.assertEqual(1, len(contexts[1].targets))
        self.assertIn("a\u0315\u0300", contexts[0].paragraph.raw_text)
        self.assertEqual("[1]", contexts[0].anchor.quote.exact)

    def test_substituted_native_receipt_or_reference_source_is_refused(self):
        raw = jats("<p>Synthetic [1].</p>", reference("r1", "1"))
        accepted = accepted_native(raw)
        native = native_parse(raw, "jats")[3]
        refs = extract_references(accepted, native_artifact=native)
        with self.assertRaises(ValueError):
            extract_citation_contexts(accepted, refs, native_artifact=native + b" ")
        changed = refs[0].model_copy(update={"raw_text": "fabricated"})
        with self.assertRaisesRegex(ValueError, "citation-reference-source-invalid"):
            extract_citation_contexts(accepted, (changed,), native_artifact=native)


if __name__ == "__main__":
    unittest.main(verbosity=2)
