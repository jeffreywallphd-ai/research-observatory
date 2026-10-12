"""Authored synthetic reference expectations, never scholarly gold or model proof."""

import hashlib
import sys
import tracemalloc
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_references import (  # noqa: E402
    MAX_REFERENCE_BYTES,
    extract_references,
)
from research_observatory_core.document_revisions import (  # noqa: E402
    AcceptedDocumentRevision,
    RetainedParseResultReceipt,
    canonicalize_structure,
    content_sha256,
    protected_json,
)
from research_observatory_core.parsing.contracts import DocumentIR  # noqa: E402

from tests.parsing.contract_fixtures import identity  # noqa: E402
from tests.parsing.test_native_parsing import native_parse  # noqa: E402


def accepted_native(data, format="jats", *, change=None):
    ir, _, _, _ = native_parse(data, format)
    if change is not None:
        wire = ir.model_dump(mode="json", by_alias=True)
        change(wire)
        ir = DocumentIR.model_validate(wire)
    structure, mapping = canonicalize_structure(ir)
    receipt = RetainedParseResultReceipt(
        result_id=identity(801),
        revision_id=identity(802),
        binding=structure.binding,
        object_sha256="a" * 64,
        byte_length=1,
    )
    return AcceptedDocumentRevision(
        project_id=structure.binding.source.project_id,
        document_id=structure.binding.source.document_id,
        revision_id=identity(805),
        previous_revision_id=identity(804),
        result=receipt,
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
        structure_sha256=hashlib.sha256(protected_json(structure)).hexdigest(),
        element_identities=mapping,
        structure=structure,
    )


JATS = (
    b"<article><body><p>Authored synthetic fixture; NOT A SCHOLARLY "
    b"SOURCE.</p></body><back><ref-list>\n<ref "
    b'id="r1"><label>1</label><element-citation><person-group '
    b'person-group-type="author"><name><surname>Example</surname><given-names>Ada<'
    b"/given-names></name></person-group><article-title>Synthetic reference "
    b"alpha</article-title><year>2024</year><source>Example "
    b'journal</source><pub-id pub-id-type="doi">10.99999/SYNTHETIC-A</pub-id></ele'
    b'ment-citation></ref>\n<ref id="r2"><mixed-citation>Unstructured synthetic '
    b"reference without reported "
    b"fields.</mixed-citation></ref>\n</ref-list></back></article>"
)


class ReferenceExtractionTests(unittest.TestCase):
    def test_order_raw_and_exact_revision_identity_survive_derivation(self):
        value = accepted_native(JATS)
        before = protected_json(value)
        entries = extract_references(value)
        self.assertEqual([0, 1], [e.order for e in entries])
        self.assertEqual([r.reference_id for r in value.structure.references], [e.reference_id for e in entries])
        for entry, original in zip(entries, value.structure.references, strict=True):
            self.assertEqual(original.raw_text, entry.raw_text_span)
            assert entry.anchor is not None
            self.assertEqual(value.revision_id, entry.anchor.revision_id)
            self.assertEqual(original.node_id, entry.anchor.node_id)
            self.assertEqual("unverified", entry.scholarly_verification)
        self.assertEqual("Unstructured synthetic reference without reported fields.", entries[1].raw_text)
        self.assertEqual(before, protected_json(value))

    def test_structured_fields_and_identifier_keep_observation_and_source_spans(self):
        entry = extract_references(accepted_native(JATS), native_artifact=native_parse(JATS, "jats")[3])[0]
        fields = {f.name: f for f in entry.fields}
        self.assertEqual("Synthetic reference alpha", fields["title"].values[0].value)
        self.assertEqual("2024", fields["year"].values[0].value)
        self.assertIn("Example", fields["authors"].values[0].value)
        self.assertEqual("Example journal", fields["venue"].values[0].value)
        identifier = entry.identifiers[0]
        self.assertEqual("10.99999/SYNTHETIC-A", identifier.assertion.observed)
        self.assertEqual("10.99999/synthetic-a", identifier.assertion.normalized.canonical)
        self.assertTrue(identifier.source_spans)
        self.assertEqual("unverified", identifier.assertion.verification_state)
        self.assertFalse(extract_references(accepted_native(JATS))[1].fields)

    def test_author_role_is_unknown_without_retained_attribute_evidence(self):
        entry = extract_references(accepted_native(JATS))[0]
        self.assertNotIn("authors", {f.name for f in entry.fields})

    def test_unbound_native_attributes_are_rejected(self):
        value = accepted_native(JATS)
        raw = native_parse(JATS.replace(b'person-group-type="author"', b'person-group-type="editor"'), "jats")[3]
        with self.assertRaisesRegex(ValueError, "reference-native-binding-invalid"):
            extract_references(value, native_artifact=raw)

    def test_parser_identifier_missing_from_reference_is_inactive(self):
        def change(wire):
            wire["references"][0]["identifiers"] = [{"scheme": "doi", "observed": "10.99999/not-in-this-reference"}]

        value = accepted_native(JATS, change=change)
        identifier = extract_references(value)[0].identifiers[0]
        self.assertFalse(identifier.source_spans)
        self.assertFalse(identifier.assertion.active_for_matching)

    def test_embedded_and_prefix_identifier_assertions_are_inactive(self):
        for source in ("10.99999/SYNTHETIC-A", "prefix10.99999/SYNTHETIC", "10.99999/SYNTHETIC?x=1"):
            with self.subTest(source=source):
                raw = (
                    "<article><back><ref-list><ref><mixed-citation>Authored synthetic doi:"
                    + source
                    + "</mixed-citation></ref></ref-list></back></article>"
                ).encode()

                def change(wire):
                    wire["references"][0]["identifiers"] = [{"scheme": "doi", "observed": "10.99999/SYNTHETIC"}]

                entry = extract_references(accepted_native(raw, change=change))[0]
                self.assertFalse(entry.identifiers[0].assertion.active_for_matching)
                self.assertFalse(entry.identifiers[0].source_spans)

    def test_complete_identifiers_keep_wrappers_punctuation_and_structural_boundaries(self):
        for raw_identifier in (
            "10.99999/SYNTHETIC-A",
            "https://doi.org/10.99999/SYNTHETIC-A",
            "doi:10.99999/SYNTHETIC-A",
        ):
            with self.subTest(raw_identifier=raw_identifier):
                raw = JATS.replace(b"10.99999/SYNTHETIC-A", raw_identifier.encode())
                entry = extract_references(accepted_native(raw), native_artifact=native_parse(raw, "jats")[3])[0]
                self.assertTrue(entry.identifiers[0].assertion.active_for_matching)
                self.assertEqual("10.99999/synthetic-a", entry.identifiers[0].assertion.normalized.canonical)
        raw = JATS.replace(b"SYNTHETIC-A", b"SYNTHETIC-A.")
        entry = extract_references(accepted_native(raw))[0]
        self.assertTrue(entry.identifiers[0].assertion.active_for_matching)
        self.assertEqual("10.99999/synthetic-a.", entry.identifiers[0].assertion.normalized.canonical)

    def test_identifier_grounding_never_rewrites_unicode_or_partial_native_values(self):
        for source, scheme, assertion, active in (
            ("10.99999/Cafe\u0301", "doi", "10.99999/Café", False),
            ("10.99999/Cafe\u0301", "doi", "10.99999/Cafe\u0301", True),
            ("10.99999/SYNTHETIC part", "doi", "10.99999/SYNTHETIC", False),
            ("10.99999/SYNTHETIC part", "doi", "10.99999/SYNTHETIC part", True),
            ("12345678", "pmid", "1234567", False),
            ("12345678", "pmid", "12345678", True),
        ):
            with self.subTest(source=source, assertion=assertion):
                raw = JATS.replace(b"10.99999/SYNTHETIC-A", source.encode()).replace(
                    b'pub-id-type="doi"', f'pub-id-type="{scheme}"'.encode()
                )

                def change(wire, scheme=scheme, assertion=assertion):
                    wire["references"][0]["identifiers"] = [{"scheme": scheme, "observed": assertion}]

                value = accepted_native(raw, change=change)
                for native_artifact in (None, native_parse(raw, "jats")[3]):
                    entry = extract_references(value, native_artifact=native_artifact)[0]
                    self.assertEqual(active, entry.identifiers[0].assertion.active_for_matching)

    def test_retained_native_identifier_scheme_is_authoritative(self):
        raw = JATS.replace(b"10.99999/SYNTHETIC-A", b"12345678").replace(b'pub-id-type="doi"', b'pub-id-type="pmid"')

        def change(wire):
            wire["references"][0]["identifiers"] = [{"scheme": "s2-corpus", "observed": "12345678"}]

        entry = extract_references(accepted_native(raw, change=change), native_artifact=native_parse(raw, "jats")[3])[0]
        self.assertFalse(entry.identifiers[0].assertion.active_for_matching)

    def test_unstructured_identifier_observation_retains_original_unicode(self):
        raw = (
            "<article><back><ref-list><ref><mixed-citation>Authored synthetic doi:10.99999/Cafe\u0301"
            "</mixed-citation></ref></ref-list></back></article>"
        ).encode()
        identifier = extract_references(accepted_native(raw))[0].identifiers[0]
        self.assertEqual("10.99999/Cafe\u0301", identifier.assertion.observed)
        self.assertEqual("10.99999/cafe\u0301", identifier.assertion.normalized.canonical)
        self.assertTrue(identifier.assertion.active_for_matching)

    def test_complete_unstructured_identifier_segments_and_resolver_uris_remain_active(self):
        for source, assertion, canonical in (
            ("doi:10.99999/SYNTHETIC part", "10.99999/SYNTHETIC part", "10.99999/synthetic part"),
            (
                "https://doi.org/10.99999/SYNTHETIC%20part more text",
                "10.99999/SYNTHETIC part",
                "10.99999/synthetic part",
            ),
            ("doi:10.99999/SYNTHETIC\nmore text", "10.99999/SYNTHETIC", "10.99999/synthetic"),
        ):
            with self.subTest(source=source):
                raw = (
                    "<article><back><ref-list><ref><mixed-citation>Authored synthetic "
                    + source
                    + "</mixed-citation></ref></ref-list></back></article>"
                ).encode()

                def change(wire, assertion=assertion):
                    wire["references"][0]["identifiers"] = [{"scheme": "doi", "observed": assertion}]

                identifier = extract_references(accepted_native(raw, change=change))[0].identifiers[0]
                self.assertTrue(identifier.assertion.active_for_matching)
                self.assertEqual(canonical, identifier.assertion.normalized.canonical)

    def test_complete_unstructured_isbn_segments_keep_spaces_and_wrappers(self):
        for source in ("ISBN: 978 0 306 40615 7", "ISBN-13: 978-0-306-40615-7", "--978-0-306-40615-7"):
            with self.subTest(source=source):
                raw = (
                    "<article><back><ref-list><ref><mixed-citation>Authored synthetic "
                    + source
                    + "</mixed-citation></ref></ref-list></back></article>"
                ).encode()

                def change(wire):
                    wire["references"][0]["identifiers"] = [{"scheme": "isbn", "observed": "9780306406157"}]

                identifier = extract_references(accepted_native(raw, change=change))[0].identifiers[0]
                self.assertTrue(identifier.assertion.active_for_matching)
                self.assertEqual("9780306406157", identifier.assertion.normalized.canonical)

    def test_many_unmatched_words_do_not_accumulate_source_sized_identifier_tails(self):
        raw = (
            "<article><back><ref-list><ref><mixed-citation>"
            + "word " * 3000
            + "</mixed-citation></ref></ref-list></back></article>"
        ).encode()

        def change(wire):
            wire["references"][0]["identifiers"] = [{"scheme": "doi", "observed": "10.99999/absent"}]

        accepted = accepted_native(raw, change=change)
        before = protected_json(accepted)
        self.assertFalse(tracemalloc.is_tracing())
        tracemalloc.start()
        try:
            entry = extract_references(accepted)[0]
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, MAX_REFERENCE_BYTES)
        self.assertFalse(entry.identifiers[0].assertion.active_for_matching)
        self.assertEqual(before, protected_json(accepted))

    def test_oversized_reference_is_rejected_and_source_stays_immutable(self):
        raw = ("<article><back><ref-list><ref>" + "x" * 65537 + "</ref></ref-list></back></article>").encode()
        value = accepted_native(raw)
        before = protected_json(value)
        with self.assertRaisesRegex(ValueError, "reference-operation-limit"):
            extract_references(value)
        self.assertEqual(before, protected_json(value))

    def test_unstructured_author_year_title_are_inferred_with_exact_spans(self):
        raw = (
            b"<article><back><ref-list><ref><mixed-citation>Example, A. (2024). Synthetic "
            b"title. Synthetic venue. doi:10.99999/synthetic-raw</mixed-citation></ref></r"
            b"ef-list></back></article>"
        )
        entry = extract_references(accepted_native(raw))[0]
        fields = {field.name: field for field in entry.fields}
        self.assertEqual("Synthetic title", fields["title"].values[0].value)
        self.assertEqual("2024", fields["year"].values[0].value)
        self.assertEqual("Example, A.", fields["authors"].values[0].value)
        for field in fields.values():
            self.assertEqual("inferred", field.values[0].knowledge_status)
            self.assertEqual(entry.raw_text_span.projection_id, field.values[0].source_span.projection_id)
        self.assertEqual("10.99999/synthetic-raw", entry.identifiers[0].assertion.normalized.canonical)

    def test_foreign_namespace_fields_do_not_acquire_jats_semantics(self):
        raw = (
            b'<article xmlns:x="urn:synthetic-foreign"><back><ref-list><ref><mixed-citatio'
            b"n><x:article-title>Foreign "
            b"label</x:article-title><x:year>2024</x:year><x:pub-id "
            b'pub-id-type="doi">10.99999/foreign</x:pub-id></mixed-citation></ref></ref-li'
            b"st></back></article>"
        )
        entry = extract_references(accepted_native(raw))[0]
        self.assertIn("Foreign label", entry.raw_text)
        self.assertFalse(entry.fields)
        self.assertFalse(entry.identifiers)

    def test_tei_missing_attribute_and_monograph_title_are_not_invented_article_fields(self):
        raw = (
            b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><back><listBibl><biblStruct><'
            b"analytic><author><persName><surname>Example</surname></persName></author><ti"
            b"tle>Synthetic article</title></analytic><monogr><title>Synthetic "
            b'container</title><imprint><date when="2024"/></imprint></monogr><idno '
            b'type="DOI">10.99999/tei</idno></biblStruct></listBibl></back></text></TEI>'
        )
        entry = extract_references(accepted_native(raw, "tei"))[0]
        fields = {f.name: f for f in entry.fields}
        self.assertEqual("Synthetic article", fields["title"].values[0].value)
        self.assertEqual("Synthetic container", fields["venue"].values[0].value)
        self.assertNotIn("year", fields)

    def test_raw_crlf_combining_and_astral_content_is_retained(self):
        raw = (
            "<article><back><ref-list><ref><mixed-citation>Café\r\n📚 "
            "synthetic</mixed-citation></ref></ref-list></back></article>"
        ).encode()
        entry = extract_references(accepted_native(raw))[0]
        self.assertEqual("Cafe\u0301\r\n📚 synthetic", entry.raw_text)
        self.assertEqual("Café\n📚 synthetic", entry.normalized_text)
        assert entry.anchor is not None
        assert entry.anchor.quote is not None
        self.assertEqual("Café\n📚 synthetic", entry.anchor.quote.exact)

    def test_explicit_cancellation_fails_without_changing_accepted_value(self):
        value = accepted_native(JATS)
        before = protected_json(value)
        with self.assertRaisesRegex(ValueError, "reference-operation-cancelled"):
            extract_references(value, cancelled=lambda: True)
        self.assertEqual(before, protected_json(value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
