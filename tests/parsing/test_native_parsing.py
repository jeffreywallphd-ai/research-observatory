"""Declared synthetic native gold; no packaged LPAC or scholarly-source claim."""

import hashlib
import importlib
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "services/core-api/src"), str(REPO)]

from research_observatory_core.parsing.contracts import RawParserArtifact  # noqa: E402
from research_observatory_core.parsing.pipeline import decode_delivery  # noqa: E402
from research_observatory_core.parsing.requests import ParseRequest, ParseSuccess  # noqa: E402
from research_observatory_core.parsing.selection import (  # noqa: E402
    ParserRegistry,
    RegisteredParser,
    SelectionSource,
    select_parser,
    selection_sha256,
)
from research_observatory_core.ports.parsing import ParseProblem  # noqa: E402

from tests.parsing.contract_fixtures import binding, descriptor, identity, source  # noqa: E402

FIXTURES = REPO / "tests/fixtures/documents/native"
RAW_MEDIA = "application/vnd.research-observatory.native-structure+json"


def native_request(data, kind):
    selected = source(kind).model_copy(
        update={"object_sha256": hashlib.sha256(data).hexdigest(), "byte_length": len(data)}
    )
    producer = descriptor()
    selection = select_parser(
        (SelectionSource(selected, "available", "primary"),),
        ParserRegistry((RegisteredParser(producer, "available"),)),
        primary_attachment_id=selected.attachment_id,
    )
    bound = binding(selected, producer).model_copy(update={"selection_sha256": selection_sha256(selection)})
    return ParseRequest(schema_version="1.0", binding=bound, selection=selection)


def native_delivery(req, raw):
    values = importlib.import_module("research_observatory_core.ports.native_parsing")
    artifact = RawParserArtifact(
        stage_id=identity(710),
        object_sha256=hashlib.sha256(raw).hexdigest(),
        byte_length=len(raw),
        media_type=RAW_MEDIA,
    )
    return values.AuthenticatedNativeDelivery(
        wire=raw,
        producer=req.binding.producer,
        job_id=req.binding.attempt.job_id,
        attempt_id=req.binding.attempt.attempt_id,
        artifact_receipt=artifact,
    )


def native_parse(data, kind):
    worker = importlib.import_module("workers.document.native_parsing")
    adapter = importlib.import_module("research_observatory_core.parsing.native")
    req = native_request(data, kind)
    raw = worker.parse_native_structure(data, format=kind, cancelled=lambda: False)
    result = decode_delivery(req, adapter.decode_native_structure(req, native_delivery(req, raw)))
    assert isinstance(result, ParseSuccess)
    return result.ir, json.loads(raw), req, raw


def node_text(ir, node):
    if node.text is None:
        return None
    projection = next(p for p in ir.text_projections if p.projection_id == node.text.projection_id)
    return projection.normalized_text[node.text.normalized_range.start : node.text.normalized_range.end]


class NativeParsingTests(unittest.TestCase):
    def test_four_synthetic_formats_retain_hierarchy_and_scholarly_structure(self):
        for kind, filename in (
            ("jats", "synthetic-jats.xml"),
            ("tei", "synthetic-tei.xml"),
            ("xml", "synthetic-generic.xml"),
            ("html", "synthetic-html.html"),
        ):
            with self.subTest(format=kind):
                data = (FIXTURES / filename).read_bytes()
                ir, raw, req, _ = native_parse(data, kind)
                self.assertEqual("staged", ir.disposition)
                self.assertEqual(req.binding, ir.binding)
                self.assertEqual(hashlib.sha256(data).hexdigest(), raw["sourceSha256"])
                self.assertEqual(len(data), raw["sourceByteLength"])
                kinds = {n.kind for n in ir.nodes}
                self.assertTrue(
                    {
                        "title",
                        "abstract",
                        "section",
                        "paragraph",
                        "list",
                        "list-item",
                        "footnote",
                        "table",
                        "table-cell",
                        "figure",
                        "caption",
                    }
                    <= kinds
                )
                self.assertTrue(
                    any(node_text(ir, n) == "Before emphasis [F1] after." for n in ir.nodes)
                    if kind != "xml"
                    else any(node_text(ir, n) == "Before emphasis after." for n in ir.nodes)
                )
                for index, element in enumerate(raw["elements"]):
                    node = ir.nodes[index]
                    self.assertEqual(f"native-node-{index}", node.staged_id)
                    self.assertEqual(f"native-text-{index}", node.text.projection_id)
                    self.assertEqual(
                        raw["text"][element["textStart"] : element["textEnd"]], ir.text_projections[index].raw_text
                    )
                    self.assertTrue(data[element["byteStart"] : element["byteEnd"]].startswith(b"<"))
                    if node.kind != "table-cell":
                        self.assertEqual(
                            None if element["parentIndex"] is None else f"native-node-{element['parentIndex']}",
                            node.parent_id,
                        )
                self.assertEqual(1, len(ir.figures))
                self.assertIsNone(ir.figures[0].preview_stage_id)
                if kind != "xml":
                    self.assertEqual(1, len(ir.references))
                    self.assertEqual("candidate", ir.citations[0].resolution)
                    self.assertEqual((ir.references[0].staged_id,), ir.citations[0].reference_candidates)
                self.assertTrue(all(n.confidence.state == "unknown" for n in ir.nodes))
                nodes = {n.staged_id: n for n in ir.nodes}
                before = next(n for n in ir.nodes if n.kind == "paragraph" and node_text(ir, n).startswith("Before "))
                self.assertEqual("section", nodes[before.parent_id].kind)
                emphasis = next(n for n in ir.nodes if node_text(ir, n) == "emphasis")
                self.assertEqual(before.staged_id, emphasis.parent_id)
                item = next(n for n in ir.nodes if n.kind == "list-item")
                self.assertEqual("list", nodes[item.parent_id].kind)
                note = next(n for n in ir.nodes if n.kind == "footnote")
                self.assertEqual("section", nodes[note.parent_id].kind)
                self.assertEqual("SYNTHETIC NOTE", node_text(ir, note))
                caption = next(n for n in ir.nodes if n.kind == "caption")
                self.assertEqual("figure", nodes[caption.parent_id].kind)
                self.assertEqual("SYNTHETIC CAPTION", node_text(ir, caption))

    def test_jats_default_and_prefix_namespaces_preserve_the_same_text_and_types(self):
        original = (FIXTURES / "synthetic-jats.xml").read_bytes()
        namespaced = original.replace(b"<article>", b'<article xmlns="http://jats.nlm.nih.gov">')
        import re

        prefixed = re.sub(rb"<(\/?)([A-Za-z][A-Za-z0-9-]*)(?=[\s/>])", rb"<\1j:\2", original)
        prefixed = prefixed.replace(b"<j:article>", b'<j:article xmlns:j="http://jats.nlm.nih.gov">')
        outputs = [native_parse(data, "jats")[0] for data in (original, namespaced, prefixed)]
        self.assertEqual([n.kind for n in outputs[0].nodes], [n.kind for n in outputs[1].nodes])
        self.assertEqual([n.kind for n in outputs[0].nodes], [n.kind for n in outputs[2].nodes])
        self.assertEqual(
            [node_text(outputs[0], n) for n in outputs[0].nodes], [node_text(outputs[2], n) for n in outputs[2].nodes]
        )
        self.assertTrue(any(node_text(outputs[1], n) == "SYNTHETIC é 🙂" for n in outputs[1].nodes))

    def test_empty_unknowns_keep_distinct_byte_anchors_and_separate_nfc_projections(self):
        data = b'<p xmlns:x="urn:test">A<x:empty/><x:empty/><x:mark>&#x30A;</x:mark></p>'
        ir, raw, _, _ = native_parse(data, "xml")
        self.assertEqual("Å", node_text(ir, ir.nodes[0]))
        self.assertEqual(["unknown"] * 3, [n.kind for n in ir.nodes[1:]])
        self.assertEqual(
            ["{urn:test}empty", "{urn:test}empty", "{urn:test}mark"], [n.source_element_type for n in ir.nodes[1:]]
        )
        self.assertEqual(["", "", "\u030a"], [node_text(ir, n) for n in ir.nodes[1:]])
        self.assertNotEqual(raw["elements"][1]["byteStart"], raw["elements"][2]["byteStart"])
        self.assertEqual(b"<x:empty/>", data[raw["elements"][1]["byteStart"] : raw["elements"][1]["byteEnd"]])
        self.assertEqual(b"<x:empty/>", data[raw["elements"][2]["byteStart"] : raw["elements"][2]["byteEnd"]])
        self.assertEqual(4, len({n.text.projection_id for n in ir.nodes}))
        self.assertEqual(["native-node-0"] * 3, [n.parent_id for n in ir.nodes[1:]])

    def test_physical_newlines_entities_and_cdata_have_truthful_raw_text(self):
        data = b"<p>A\r\nB&#xD;C<![CDATA[D\r\nE&amp;]]>&amp;F</p>"
        ir, raw, _, _ = native_parse(data, "xml")
        self.assertEqual("A\r\nB\rCD\r\nE&amp;&F", raw["text"])
        self.assertEqual(raw["text"], ir.text_projections[0].raw_text)
        self.assertEqual("A\nB\nCD\nE&amp;&F", node_text(ir, ir.nodes[0]))

    def test_utf16_and_declared_latin1_xml_locations_bind_original_bytes(self):
        for data in ("<p>é🙂</p>".encode("utf-16"), b'<?xml version="1.0" encoding="ISO-8859-1"?><p>\xe9</p>'):
            with self.subTest(encoding=data[:8]):
                ir, raw, _, _ = native_parse(data, "xml")
                self.assertEqual("é🙂" if data.startswith(b"\xff\xfe") else "é", node_text(ir, ir.nodes[0]))
                self.assertEqual(len(data), raw["sourceByteLength"])
                self.assertLess(raw["elements"][0]["byteStart"], raw["elements"][0]["byteEnd"])

    def test_foreign_names_never_become_native_paragraphs_references_or_cells(self):
        data = (
            b'<article xmlns:x="urn:foreign"><body><x:p>A</x:p><x:ref id="R">B</x:ref><x:td>C</x:td></body></article>'
        )
        ir, _, _, _ = native_parse(data, "jats")
        self.assertEqual(
            ["unknown"] * 3, [n.kind for n in ir.nodes if n.source_element_type.startswith("{urn:foreign}")]
        )
        self.assertEqual((), ir.references)
        self.assertEqual((), ir.tables)

    def test_reference_ambiguity_missing_targets_and_observed_identifier_stay_explicit(self):
        data = (
            b'<article><body><p><xref ref-type="bibr" rid="R">[A]</xref>'
            b'<xref ref-type="bibr" rid="missing">[B]</xref></p></body><back><ref-list>'
            b'<ref id="R">SYNTHETIC A<pub-id pub-id-type="doi">10.synthetic/a</pub-id></ref>'
            b'<ref id="R">SYNTHETIC B</ref></ref-list></back></article>'
        )
        ir, _, _, _ = native_parse(data, "jats")
        self.assertEqual(["ambiguous", "unresolved"], [c.resolution for c in ir.citations])
        self.assertEqual(2, len(ir.citations[0].reference_candidates))
        self.assertEqual((), ir.citations[1].reference_candidates)
        self.assertEqual("10.synthetic/a", ir.references[0].identifiers[0].observed)
        self.assertGreaterEqual(ir.quality.unresolved_references, 1)

    def test_table_spans_and_nested_tables_keep_distinct_cells(self):
        ir, _, _, _ = native_parse((FIXTURES / "synthetic-jats.xml").read_bytes(), "jats")
        table = ir.tables[0]
        self.assertEqual((2, 2, "reported"), (table.rows, table.columns, table.grid_state))
        self.assertEqual(
            [(0, 0, 2, 1), (0, 1, 1, 1), (1, 1, 1, 1)],
            [(c.row, c.column, c.row_span, c.column_span) for c in table.cells],
        )
        nested = (
            b"<document><table><row><cell>A<table><row><cell>B</cell></row></table></cell></row></table></document>"
        )
        ir, _, _, _ = native_parse(nested, "xml")
        self.assertEqual(2, len(ir.tables))
        self.assertTrue(all(len(t.cells) == 1 for t in ir.tables))
        self.assertNotEqual(ir.tables[0].cells[0].node_id, ir.tables[1].cells[0].node_id)
        self.assertTrue(
            all(
                next(n for n in ir.nodes if n.staged_id == c.node_id).parent_id == t.node_id
                for t in ir.tables
                for c in t.cells
            )
        )

    def test_invalid_cell_geometry_is_retained_without_an_invented_grid(self):
        ir, raw, _, _ = native_parse(
            b'<document><table><row><cell cols="999999999999999999999">A</cell></row></table></document>', "xml"
        )
        self.assertTrue(any(n.kind == "unknown" and node_text(ir, n) == "A" for n in ir.nodes))
        self.assertTrue(any(w.code == "unsupported-table-geometry" for w in ir.quality.warnings))
        self.assertTrue(any(a["value"] == "999999999999999999999" for e in raw["elements"] for a in e["attributes"]))

    def test_hostile_malformed_and_overdeep_inputs_never_produce_partial_output(self):
        worker = importlib.import_module("workers.document.native_parsing")
        for data, kind in (
            (b'<!DOCTYPE p [<!ENTITY x SYSTEM "https://example.invalid/secret">]><p>&x;</p>', "xml"),
            (b"<?evil private?><p>TEXT</p>", "xml"),
            (b"<p>PRIVATE UNFINISHED", "xml"),
            (b"<p>" * 257 + b"X" + b"</p>" * 257, "xml"),
            (b"<html><script>PRIVATE</script></html>", "html"),
            (b'<html><p onclick="PRIVATE">X</p></html>', "html"),
            (b'<html><a href="java&#x73;cript:PRIVATE">X</a></html>', "html"),
        ):
            with self.subTest(format=kind, prefix=data[:16]):
                with self.assertRaises(worker.NativeParseError) as caught:
                    worker.parse_native_structure(data, format=kind, cancelled=lambda: False)
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertIsNone(caught.exception.__context__)

    def test_size_and_cancellation_boundaries_fail_closed(self):
        worker = importlib.import_module("workers.document.native_parsing")
        with self.assertRaises(worker.NativeParseError) as caught:
            worker.parse_native_structure(b"x" * (128 * 1_048_576 + 1), format="xml", cancelled=lambda: False)
        self.assertEqual("oversize", caught.exception.code)
        for callback in (lambda: True, lambda: 1):
            with self.assertRaises(worker.NativeParseError) as caught:
                worker.parse_native_structure(b"<p>X</p>", format="xml", cancelled=callback)
            self.assertEqual("cancelled", caught.exception.code)

    def test_core_rejects_raw_element_aliases_parent_contradictions_and_text_rebinding(self):
        _, value, req, _ = native_parse(b'<p xmlns:x="urn:test">A<x:wrap><x:mark>B</x:mark></x:wrap></p>', "xml")
        adapter = importlib.import_module("research_observatory_core.parsing.native")
        for mutation in (
            lambda v: v["elements"][2].update(index=1),
            lambda v: v["elements"][2].update(parentIndex=0),
            lambda v: v["elements"][2].update(textStart=0),
            lambda v: v.update(sourceSha256="f" * 64),
        ):
            altered = json.loads(json.dumps(value))
            mutation(altered)
            raw = json.dumps(altered).encode()
            with self.assertRaises(ParseProblem) as caught:
                adapter.decode_native_structure(req, native_delivery(req, raw))
            self.assertEqual("parse-output-invalid", caught.exception.code)
            self.assertIsNone(caught.exception.__context__)

    def test_core_requires_independent_producer_attempt_and_raw_artifact_receipt(self):
        _, _, req, raw = native_parse(b"<p>SYNTHETIC</p>", "xml")
        adapter = importlib.import_module("research_observatory_core.parsing.native")
        delivered = native_delivery(req, raw)
        for bad in (
            replace(delivered, job_id=identity(990)),
            replace(delivered, attempt_id=identity(991)),
            replace(delivered, producer=delivered.producer.model_copy(update={"configuration_sha256": "f" * 64})),
            replace(
                delivered, artifact_receipt=delivered.artifact_receipt.model_copy(update={"object_sha256": "f" * 64})
            ),
            replace(delivered, wire=b'{"schemaVersion":"1.0","schemaVersion":"1.0"}'),
        ):
            with self.assertRaises(ParseProblem) as caught:
                adapter.decode_native_structure(req, bad)
            self.assertIsNone(caught.exception.__context__)

    def test_non_ascii_attributes_and_multichunk_content_keep_exact_bytes(self):
        worker = importlib.import_module("workers.document.native_parsing")
        for codec in ("utf-8", "utf-16"):
            content = "é🙂" + "A" * 65_540 + "\r\nB"
            data = f'<p label="é🙂 >">{content}<em>\u030a</em></p>'.encode(codec)
            ir, raw, _, _ = native_parse(data, "xml")
            self.assertEqual(content + "\u030a", raw["text"])
            self.assertEqual("é🙂 >", raw["elements"][0]["attributes"][0]["value"])
            self.assertEqual(len(data), raw["elements"][0]["byteEnd"])
            self.assertEqual("\u030a", ir.text_projections[1].raw_text)
        for kind in ("jats", "tei"):
            with self.assertRaises(worker.NativeParseError) as caught:
                worker.parse_native_structure(b"<p>X</p>", format=kind, cancelled=lambda: False)
            self.assertEqual("format-mismatch", caught.exception.code)

    def test_html_zero_rowspan_rowgroups_duplicate_geometry_and_foreign_names(self):
        data = (
            b'<html><table><tbody><tr><td rowspan="0">A</td><td>B</td></tr>'
            b"<tr><td>C</td></tr></tbody><tbody><tr><td>D</td></tr></tbody></table>"
            b'<p xmlns:x="urn:foreign"><x:p>X</x:p></p></html>'
        )
        ir, _, _, _ = native_parse(data, "html")
        self.assertEqual((3, 2), (ir.tables[0].rows, ir.tables[0].columns))
        self.assertEqual(
            [(0, 0, 2), (0, 1, 1), (1, 1, 1), (2, 0, 1)], [(c.row, c.column, c.row_span) for c in ir.tables[0].cells]
        )
        self.assertEqual("unknown", ir.nodes[-1].kind)
        for attrs in (b'rowspan="2"', b'colspan="2" colspan="3"'):
            malformed = (
                b"<html><table><tbody><tr><td "
                + attrs
                + b">A</td></tr></tbody><tbody><tr><td>B</td></tr></tbody></table></html>"
            )
            ir, _, _, _ = native_parse(malformed, "html")
            self.assertTrue(any(n.kind == "unknown" and node_text(ir, n) == "A" for n in ir.nodes))
            self.assertEqual("ambiguous", ir.tables[0].grid_state)

    def test_worker_cancellation_during_parse_and_output_cap_return_no_partial(self):
        worker = importlib.import_module("workers.document.native_parsing")
        count = 0

        def cancel():
            nonlocal count
            count += 1
            return count == 7

        with self.assertRaises(worker.NativeParseError) as caught:
            worker.parse_native_structure(b"<p>A<em>B</em>C</p>", format="xml", cancelled=cancel)
        self.assertEqual("cancelled", caught.exception.code)
        self.assertIsNone(caught.exception.__context__)

    def test_tei_untyped_explicit_bibliography_target_and_nested_figure_captions(self):
        data = (
            b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div><p>'
            b'<ref target="#R">[F1]</ref><ref target="https://example.invalid">EXTERNAL</ref>'
            b"</p><figure><figure><head>INNER</head></figure><head>OUTER</head></figure>"
            b'</div></body><back><listBibl><bibl xml:id="R">SYNTHETIC</bibl>'
            b"</listBibl></back></text></TEI>"
        )
        ir, _, _, _ = native_parse(data, "tei")
        self.assertEqual(1, len(ir.citations))
        self.assertEqual("candidate", ir.citations[0].resolution)
        self.assertEqual(
            ["OUTER", "INNER"],
            [
                next(p.normalized_text for p in ir.text_projections if p.projection_id == figure.caption.projection_id)
                for figure in ir.figures
            ],
        )

    def test_worker_output_cap_returns_no_partial(self):
        worker = importlib.import_module("workers.document.native_parsing")
        # Exercise the unchanged output-cap mechanism with a small cap. The
        # actual 64-MiB public IR/wire limit is covered by the existing suite.
        with patch.object(worker, "MAX_OUTPUT_BYTES", 256), self.assertRaises(worker.NativeParseError) as caught:
            worker.parse_native_structure(b"<p>" + b"A" * 300 + b"</p>", format="xml", cancelled=lambda: False)
        self.assertEqual("oversize", caught.exception.code)
        self.assertIsNone(caught.exception.__context__)

    def test_raw_text_run_coverage_markup_overlap_and_strict_wire_are_rejected(self):
        _, value, req, raw = native_parse(b"<p>A<em>B</em>C<empty/></p>", "xml")
        adapter = importlib.import_module("research_observatory_core.parsing.native")
        mutations = (
            lambda v: v["textRuns"][1].update(ownerIndex=0),
            lambda v: v["textRuns"][1].update(textStart=0),
            lambda v: v["textRuns"][1].update(byteEnd=v["elements"][1]["byteEnd"]),
            lambda v: v["elements"][2].update(byteStart=v["elements"][1]["contentByteEnd"]),
            lambda v: v["elements"][0].update(textEnd=2),
            lambda v: v["elements"][0].update(byteEnd=v["elements"][0]["contentByteEnd"]),
            lambda v: v.update(textRuns=v["textRuns"][:-1]),
            lambda v: v.update(format="jats"),
            lambda v: v.update(privatePath="PRIVATE SYNTHETIC"),
        )
        for mutation in mutations:
            altered = json.loads(json.dumps(value))
            mutation(altered)
            wire = json.dumps(altered).encode()
            with self.assertRaises(ParseProblem) as caught:
                adapter.decode_native_structure(req, native_delivery(req, wire))
            self.assertEqual("parse-output-invalid", caught.exception.code)
            self.assertIsNone(caught.exception.__context__)
        for wire in (raw.replace(b'"text":"ABC"', b'"text":NaN'), b"\xff", b"[" * 2000 + b"0" + b"]" * 2000):
            with self.assertRaises(ParseProblem) as caught:
                adapter.decode_native_structure(req, native_delivery(req, wire))
            self.assertIsNone(caught.exception.__context__)

    def test_native_adapter_uses_worker_port_and_existing_staged_handoff(self):
        from contextlib import contextmanager
        from io import BytesIO
        from typing import cast

        from research_observatory_core.parsing.native import NativeStructuredParser
        from research_observatory_core.parsing.pipeline import stage_parse
        from research_observatory_core.ports.corpus import CorpusActor
        from research_observatory_core.ports.parsing import ReadOnlyDocumentSource

        data = b"<p>SYNTHETIC</p>"
        req = native_request(data, "xml")
        worker = importlib.import_module("workers.document.native_parsing")
        calls = []

        class Worker:
            def parse_source(self, request, source, *, cancelled):
                calls.append("worker-port")
                raw = worker.parse_native_structure(source.read(), format="xml", cancelled=cancelled)
                return native_delivery(request, raw)

        class Sources:
            @contextmanager
            def read_source(self, source, *, actor, cancelled):
                with BytesIO(data) as stream:
                    yield cast(ReadOnlyDocumentSource, stream)

            def deliver(self, source, *, actor, action):
                calls.append("protected-delivery")
                return action()

        actor = CorpusActor(identity(500), "a" * 32, "2026-10-07T00:00:00.000Z", identity(501), "b" * 64, "c" * 64)
        result = stage_parse(req, NativeStructuredParser(Worker()), Sources(), actor=actor, cancelled=lambda: False)
        self.assertIsInstance(result, ParseSuccess)
        self.assertEqual(["worker-port", "protected-delivery"], calls)
        self.assertFalse(hasattr(NativeStructuredParser(Worker()), "accept"))


if __name__ == "__main__":
    unittest.main()
