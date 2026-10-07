"""Installed family regressions; delivery doubles are not native proof."""

import hashlib
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "services/core-api/src")]
from research_observatory_core.document_parser_runtime import (  # noqa: E402
    InstalledDocumentParserRuntime,
    InstalledParser,
    InstalledParserPipeline,
    _run_installed,
)
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
from research_observatory_core.ports.native_parsing import AuthenticatedNativeDelivery  # noqa: E402
from research_observatory_core.ports.parsing import ParseProblem, RawParserStagerPort  # noqa: E402

from tests.parsing.contract_fixtures import binding, descriptor, identity, source  # noqa: E402
from tests.parsing.test_docling_parsing import request as pdf_request  # noqa: E402
from workers.windows.runtime_inventory import SignedWorkerRuntime  # noqa: E402


def text_request():
    selected = source("plain-text")
    producer = descriptor("ro-native-text", ("plain-text",))
    selection = select_parser(
        (SelectionSource(selected, "available", "primary"),),
        ParserRegistry((RegisteredParser(producer, "available"),)),
        primary_attachment_id=selected.attachment_id,
    )
    return ParseRequest(
        schema_version="1.0",
        selection=selection,
        binding=binding(selected, producer).model_copy(update={"selection_sha256": selection_sha256(selection)}),
    )


class InstalledFamilyTests(unittest.TestCase):
    def test_installed_fallback_descriptor_is_admitted_by_existing_registry(self):
        runtime = InstalledDocumentParserRuntime()
        base = InstalledParser(object(), pdf_request().binding.producer)
        with patch.object(runtime, "load", return_value=base):
            loaded = runtime.load_inspection()
        ParserRegistry((RegisteredParser(loaded.descriptor, "available"),))
        self.assertEqual("1.0.0", loaded.descriptor.version)
        self.assertEqual("degraded-inspection", loaded.descriptor.kind)

    def test_text_family_has_its_own_installed_composition(self):
        selected = text_request()
        loaded = InstalledParser(object(), selected.binding.producer)

        class Runtime:
            def load(self):
                raise AssertionError("wrong Docling family")

            def load_inspection(self):
                raise AssertionError("wrong inspection family")

            def load_text(self):
                return loaded

            def load_native(self):
                raise AssertionError("wrong structured family")

        # Selection never calls either persistence port in this regression.
        pipeline = InstalledParserPipeline(
            stage_raw=cast(RawParserStagerPort, object()), sources=object(), runtime=Runtime()
        )
        self.assertEqual(loaded, pipeline._selection(selected)[0])

    def test_only_plain_text_is_mapped_to_existing_txt_worker_wire_format(self):
        selected = text_request()
        installed = InstalledParser(
            SignedWorkerRuntime(Path("fixed"), b"inventory", b"sig", b"key"), selected.binding.producer
        )

        class Reply:
            output = b"synthetic raw"

        with patch("workers.windows.parsing_launcher.parse_document", return_value=Reply()) as launch:
            self.assertEqual(
                b"synthetic raw", _run_installed(installed, selected, object(), cancelled=lambda: False)[0]
            )
        self.assertEqual("txt", launch.call_args.kwargs["format"])


class BoundedTextTests(unittest.TestCase):
    def setUp(self):
        self.request = text_request()

    def delivery(self, wire=None):
        if wire is None:
            wire = json.dumps(
                {
                    "schemaVersion": "1.0",
                    "documentType": "bounded-text-parser-output",
                    "text": "Cafe\u0301\r\n\U0001f642 \ufffd",
                },
                ensure_ascii=False,
            ).encode()
        return AuthenticatedNativeDelivery(
            wire,
            self.request.binding.producer,
            self.request.binding.attempt.job_id,
            self.request.binding.attempt.attempt_id,
            RawParserArtifact(
                stage_id=identity(777),
                object_sha256=hashlib.sha256(wire).hexdigest(),
                byte_length=len(wire),
                media_type="application/vnd.research-observatory.text-parser-output+json",
            ),
        )

    def decode(self, delivered):
        from research_observatory_core.parsing.text import decode_text

        result = decode_delivery(self.request, decode_text(self.request, delivered))
        assert isinstance(result, ParseSuccess)
        return result.ir

    def test_raw_nfc_mapping_and_unavailable_scholarly_structure_are_truthful(self):
        ir = self.decode(self.delivery())
        self.assertEqual("Cafe\u0301\r\n\U0001f642 \ufffd", ir.text_projections[0].raw_text)
        self.assertEqual("Café\n\U0001f642 \ufffd", ir.text_projections[0].normalized_text)
        self.assertEqual("staged", ir.disposition)
        self.assertEqual("text", ir.nodes[0].locator.kind)
        self.assertEqual("unknown", ir.nodes[0].confidence.state)
        self.assertEqual(1, ir.quality.replacement_characters)
        self.assertIsNone(ir.quality.unresolved_references)
        self.assertEqual(((), (), (), ()), (ir.pages, ir.tables, ir.references, ir.citations))

    def test_wire_expansion_is_rejected_before_projection_models(self):
        from research_observatory_core.parsing import text

        wire = json.dumps(
            {"schemaVersion": "1.0", "documentType": "bounded-text-parser-output", "text": "a" * 150}
        ).encode()
        self.assertLess(len(wire), 256)
        with (
            patch.object(text, "MAX_IR_BYTES", 256),
            patch.object(text.TextProjection, "from_raw") as allocate,
            self.assertRaises(ParseProblem),
        ):
            text.decode_text(self.request, self.delivery(wire))
        allocate.assert_not_called()

    def test_cancellation_during_text_decode_cannot_return_a_delivery(self):
        from research_observatory_core.parsing.text import decode_text

        with self.assertRaises(ParseProblem) as raised:
            decode_text(self.request, self.delivery(), cancelled=lambda: True)
        self.assertIsNone(raised.exception.__context__)

    def test_malformed_schema_duplicate_fields_and_substituted_authority_deny(self):
        original = self.delivery()
        variants = [
            replace(original, attempt_id=identity(778)),
            replace(original, job_id=identity(779)),
            replace(original, producer=descriptor("ro-native-structured", ("jats", "tei", "xml", "html"))),
            replace(
                original, artifact_receipt=original.artifact_receipt.model_copy(update={"object_sha256": "f" * 64})
            ),
            replace(
                original,
                artifact_receipt=original.artifact_receipt.model_copy(update={"media_type": "application/json"}),
            ),
            self.delivery(original.wire + b"{}"),
            self.delivery(b'{"schemaVersion":"1.0","documentType":"bounded-text-parser-output","text":"a","text":"b"}'),
            self.delivery(b'{"schemaVersion":"1.0","documentType":"bounded-text-parser-output","text":0}'),
            self.delivery(b'{"schemaVersion":"2.0","documentType":"bounded-text-parser-output","text":"a"}'),
        ]
        for delivered in variants:
            with self.subTest(delivered=delivered), self.assertRaises(ParseProblem) as raised:
                self.decode(delivered)
            self.assertIsNone(raised.exception.__context__)


if __name__ == "__main__":
    unittest.main(verbosity=2)
