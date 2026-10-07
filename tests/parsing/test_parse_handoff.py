"""An echoed binding or syntactically valid JSON is not producer authority."""

import json
import sys
import unittest
from collections.abc import Callable
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.parsing.pipeline import decode_delivery, stage_parse  # noqa: E402
from research_observatory_core.parsing.requests import ParseRequest, ParseSuccess  # noqa: E402
from research_observatory_core.parsing.selection import (  # noqa: E402
    ParserRegistry,
    RegisteredParser,
    SelectionSource,
    select_parser,
    selection_sha256,
)
from research_observatory_core.ports.corpus import CorpusActor  # noqa: E402
from research_observatory_core.ports.parsing import (  # noqa: E402
    AuthenticatedParseDelivery,
    ParseProblem,
    ReadOnlyDocumentSource,
)

from tests.parsing.contract_fixtures import binding, descriptor, identity, ir, rich_ir_wire, source  # noqa: E402


def request():
    selected = source()
    producer = descriptor("ro-native-text", ("plain-text",))
    selection = select_parser(
        (SelectionSource(selected, "available", "primary"),),
        ParserRegistry((RegisteredParser(producer, "available"),)),
        primary_attachment_id=selected.attachment_id,
    )
    bound = binding(selected, producer).model_copy(update={"selection_sha256": selection_sha256(selection)})
    return ParseRequest(schema_version="1.0", binding=bound, selection=selection)


def delivery(req, wire=None, producer=None, job_id=None, attempt_id=None):
    if wire is None:
        value = ir(req.binding)
        wire = (
            ParseSuccess(schema_version="1.0", kind="success", binding=req.binding, ir=value)
            .model_dump_json(by_alias=True)
            .encode()
        )
    return AuthenticatedParseDelivery(
        wire=wire,
        producer=producer or req.binding.producer,
        job_id=job_id or req.binding.attempt.job_id,
        attempt_id=attempt_id or req.binding.attempt.attempt_id,
        artifact_receipts=(),
    )


class ParseHandoffTests(unittest.TestCase):
    def test_authenticated_wire_still_refuses_contradictory_citation_text(self):
        req = request()
        value = rich_ir_wire()
        value["binding"] = req.binding.model_dump(mode="json", by_alias=True)
        value["rawArtifacts"] = []
        value["figures"][0]["previewStageId"] = None
        envelope = {"schemaVersion": "1.0", "kind": "success", "binding": value["binding"], "ir": value}
        self.assertEqual("success", decode_delivery(req, delivery(req, json.dumps(envelope).encode())).kind)
        value["citations"][0]["marker"] = value["references"][0]["rawText"]
        with self.assertRaises(ParseProblem) as caught:
            decode_delivery(req, delivery(req, json.dumps(envelope).encode()))
        self.assertEqual("parse-output-invalid", caught.exception.code)
        self.assertIsNone(caught.exception.__context__)

    def test_cancellation_is_monotonic_and_callback_errors_fail_closed(self):
        req = request()
        actor = CorpusActor(identity(500), "a" * 32, "2026-10-07T00:00:00.000Z", identity(501), "b" * 64, "c" * 64)
        calls = []

        class Sources:
            @contextmanager
            def read_source(self, source, *, actor, cancelled):
                with BytesIO(b"abc") as stream:
                    yield cast(ReadOnlyDocumentSource, stream)  # Synthetic port; no isolated-worker claim.

            def deliver(self, source, *, actor, action):
                return action()

        class Parser:
            def parse(self, request, source, *, cancelled):
                calls.append("parser")
                self_was_cancelled = cancelled()
                self_is_still_cancelled = cancelled()
                if not self_was_cancelled or not self_is_still_cancelled:
                    raise AssertionError("cancellation was forgotten")
                return delivery(request)

        observations = iter((False, False, True, False, False))
        result = stage_parse(req, Parser(), Sources(), actor=actor, cancelled=lambda: next(observations))
        self.assertEqual("cancelled", result.kind)
        self.assertEqual(["parser"], calls)
        self.assertFalse(hasattr(result, "ir"))

        def broken():
            raise RuntimeError("PRIVATE-SYNTHETIC-CANCELLATION-ERROR")

        for callback in (broken, lambda: 1):
            result = stage_parse(req, Parser(), Sources(), actor=actor, cancelled=cast(Callable[[], bool], callback))
            self.assertEqual("cancelled", result.kind)
            self.assertNotIn("PRIVATE-SYNTHETIC", str(result))
        self.assertEqual(["parser"], calls)

    def test_public_wire_round_trip_preserves_staged_only_output(self):
        req = request()
        value = decode_delivery(req, delivery(req))
        self.assertEqual("success", value.kind)
        assert isinstance(value, ParseSuccess)
        self.assertEqual("staged", value.ir.disposition)
        self.assertEqual(req.binding, value.binding)
        self.assertEqual("abc", value.ir.text_projections[0].raw_text)

    def test_authenticated_producer_is_distinct_from_worker_echo(self):
        req = request()
        for delivered in (
            delivery(req, job_id=identity(999)),
            delivery(req, attempt_id=identity(998)),
            delivery(req, producer=req.binding.producer.model_copy(update={"configuration_sha256": "f" * 64})),
        ):
            with self.subTest(attempt=delivered.attempt_id), self.assertRaises(ParseProblem):
                decode_delivery(req, delivered)

    def test_stale_or_substituted_binding_and_partial_failure_cannot_pass(self):
        req = request()
        original = json.loads(delivery(req).wire)
        changes = (
            lambda v: v["binding"]["attempt"].update(attemptId=identity(999)),
            lambda v: v["binding"]["source"].update(projectId=identity(999)),
            lambda v: v["binding"]["source"].update(attachmentId=identity(999)),
            lambda v: v["binding"]["source"].update(objectSha256="f" * 64),
            lambda v: v["binding"]["source"].update(workRevisionId=identity(999)),
            lambda v: v["binding"]["source"].update(versionRevisionId=identity(999)),
            lambda v: v["binding"]["producer"].update(configurationSha256="f" * 64),
            lambda v: v.update(kind="failure", code="parser-failed"),
            lambda v: v.update(kind="cancelled", code="cancelled"),
            lambda v: v["ir"].update(disposition="accepted"),
            lambda v: v.update(schemaVersion="99.0"),
        )
        for index, change in enumerate(changes):
            value = json.loads(json.dumps(original))
            change(value)
            with self.subTest(index=index), self.assertRaises(ParseProblem):
                decode_delivery(req, delivery(req, json.dumps(value).encode()))

    def test_failed_and_cancelled_values_have_no_ir(self):
        req = request()
        for kind, code in (("failure", "parser-failed"), ("cancelled", "cancelled")):
            wire = json.dumps(
                {
                    "schemaVersion": "1.0",
                    "kind": kind,
                    "binding": req.binding.model_dump(mode="json", by_alias=True),
                    "code": code,
                }
            ).encode()
            result = decode_delivery(req, delivery(req, wire))
            self.assertEqual(kind, result.kind)
            self.assertFalse(hasattr(result, "ir"))

    def test_wire_denial_is_content_free_without_retained_private_exception(self):
        req = request()
        valid = delivery(req).wire
        invalids = (
            b'{"kind":"PRIVATE-SYNTHETIC-DATA"}',
            valid.replace(b'"kind":"success"', b'"kind":"failure","kind":"success"', 1),
            b"[" * 2000 + b"0" + b"]" * 2000,
            b" " * (64 * 1024 * 1024 + 1),
        )
        for wire in invalids:
            with self.subTest(length=len(wire)), self.assertRaises(ParseProblem) as caught:
                decode_delivery(req, delivery(req, wire))
            self.assertNotIn("PRIVATE-SYNTHETIC", str(caught.exception))
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNone(caught.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
