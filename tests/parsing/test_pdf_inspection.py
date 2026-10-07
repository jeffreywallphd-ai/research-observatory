"""Inspection-only fallback never turns denied/cancelled parsing into success."""

import hashlib
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "services/core-api/src"), str(REPO)]

from research_observatory_core.parsing.contracts import ParseAttempt, RawParserArtifact  # noqa: E402
from research_observatory_core.parsing.inspection import (  # noqa: E402
    INSPECTION_MEDIA_TYPE,
    decode_inspection,
    prepare_inspection_request,
)
from research_observatory_core.parsing.pipeline import decode_delivery  # noqa: E402
from research_observatory_core.parsing.requests import ParseCancelled, ParseFailure  # noqa: E402
from research_observatory_core.ports.parsing import ParseProblem  # noqa: E402
from research_observatory_core.ports.pdf_inspection import AuthenticatedInspectionDelivery  # noqa: E402

from tests.parsing.contract_fixtures import descriptor, identity  # noqa: E402
from tests.parsing.test_docling_parsing import request  # noqa: E402


class PdfInspectionTests(unittest.TestCase):
    def setUp(self):
        self.prior = request()
        self.producer = descriptor("ro-page-text-fallback", ("pdf",)).model_copy(update={"kind": "degraded-inspection"})
        self.attempt = ParseAttempt(job_id=identity(101), attempt_id=identity(102), activity_version="document-parse-1")
        self.failed = ParseFailure(
            schema_version="1.0", kind="failure", binding=self.prior.binding, code="parser-failed"
        )
        self.request = prepare_inspection_request(self.prior, self.failed, self.producer, self.attempt)

    def delivery(self, *, raw=None):
        if raw is None:
            geometry = {
                "mediaBox": [0, 0, 600, 800],
                "cropBox": [0, 0, 600, 800],
                "rotation": 0,
                "userUnit": 1,
                "imagePixels": 0,
            }
            raw = {
                "schemaVersion": "1.0",
                "documentType": "pdf-inspection-output",
                "inputSha256": self.prior.binding.source.object_sha256,
                "inputLength": self.prior.binding.source.byte_length,
                "pages": [{"geometry": geometry, "text": "Cafe\u0301 \ufffd"}, {"geometry": geometry, "text": ""}],
            }
        wire = json.dumps(raw, ensure_ascii=False).encode()
        return AuthenticatedInspectionDelivery(
            wire,
            self.producer,
            self.attempt.job_id,
            self.attempt.attempt_id,
            RawParserArtifact(
                stage_id=identity(103),
                object_sha256=hashlib.sha256(wire).hexdigest(),
                byte_length=len(wire),
                media_type=INSPECTION_MEDIA_TYPE,
            ),
        )

    def test_degraded_output_preserves_raw_text_and_explicit_missing_quality(self):
        ir = decode_delivery(self.request, decode_inspection(self.request, self.delivery())).ir
        self.assertEqual("inspection-only", ir.disposition)
        self.assertEqual("Cafe\u0301 \ufffd", ir.text_projections[0].raw_text)
        self.assertEqual("Café \ufffd", ir.text_projections[0].normalized_text)
        self.assertEqual((1,), ir.quality.missing_text_pages)
        self.assertEqual("ambiguous", ir.quality.reading_order)
        self.assertEqual(1, ir.quality.replacement_characters)
        self.assertTrue(all(node.confidence.state == "unknown" for node in ir.nodes))
        self.assertEqual("unavailable", ir.nodes[0].locator.kind)
        self.assertIn("inspection-only-fallback", [warning.code for warning in ir.quality.warnings])
        self.assertEqual((), ir.tables)
        self.assertEqual(self.prior.binding.attempt.attempt_id, self.request.selection.fallback_from_attempt_id)

    def test_only_exact_docling_failure_timeout_or_memory_failure_can_select_new_attempt(self):
        for code in ("parser-failed", "parser-timeout", "parser-memory-limit"):
            failed = self.failed.model_copy(update={"code": code})
            self.assertEqual(
                "inspection-only",
                prepare_inspection_request(
                    self.prior,
                    failed,
                    self.producer,
                    self.attempt,
                ).selection.outcome,
            )
        for code in (
            "parse-source-denied",
            "parse-delivery-denied",
            "parser-input-invalid",
            "parser-input-unsupported",
            "parser-resource-limit",
            "parser-assets-unavailable",
            "parse-output-invalid",
            "parse-producer-mismatch",
        ):
            with self.subTest(code=code), self.assertRaises(ParseProblem):
                prepare_inspection_request(
                    self.prior, self.failed.model_copy(update={"code": code}), self.producer, self.attempt
                )
        cancelled = ParseCancelled(schema_version="1.0", kind="cancelled", binding=self.prior.binding, code="cancelled")
        with self.assertRaises(ParseProblem):
            prepare_inspection_request(self.prior, cancelled, self.producer, self.attempt)
        with self.assertRaises(ParseProblem):
            prepare_inspection_request(self.prior, self.failed, self.producer, self.prior.binding.attempt)

    def test_source_attempt_receipt_and_geometry_substitution_are_rejected(self):
        delivered = self.delivery()
        for corrupt in (
            replace(delivered, attempt_id=identity(111)),
            replace(
                delivered, artifact_receipt=delivered.artifact_receipt.model_copy(update={"object_sha256": "f" * 64})
            ),
            replace(delivered, wire=delivered.wire + b"{}"),
        ):
            with self.assertRaises(ParseProblem):
                decode_inspection(self.request, corrupt)
        raw = json.loads(delivered.wire)
        raw["inputSha256"] = "f" * 64
        with self.assertRaises(ParseProblem):
            decode_inspection(self.request, self.delivery(raw=raw))
        raw["inputSha256"] = self.prior.binding.source.object_sha256
        raw["pages"][0]["geometry"]["rotation"] = True
        with self.assertRaises(ParseProblem):
            decode_inspection(self.request, self.delivery(raw=raw))


if __name__ == "__main__":
    unittest.main()
