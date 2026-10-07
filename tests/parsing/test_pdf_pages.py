"""Lazy page delivery rejects substituted authority and unbounded surfaces."""

import hashlib
import json
import struct
import sys
import unittest
import zlib
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, Mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.document_parser_runtime import InstalledParser, InstalledParserPipeline  # noqa: E402
from research_observatory_core.parsing.contracts import RawParserArtifact  # noqa: E402
from research_observatory_core.parsing.pages import decode_page, png_dimensions, render_page  # noqa: E402
from research_observatory_core.ports.parsing import ParseProblem  # noqa: E402
from research_observatory_core.ports.pdf_pages import AuthenticatedPageDelivery  # noqa: E402

from tests.parsing.contract_fixtures import identity  # noqa: E402
from tests.parsing.test_docling_parsing import request  # noqa: E402


def png(width=2, height=1, *, compressed=None, geometry=None, page_index=1, metadata=True):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    value = {
        "schemaVersion": "1.0",
        "pageIndex": page_index,
        "geometry": geometry
        or {
            "mediaBox": [0, 0, width / 1.5, height / 1.5],
            "cropBox": [0, 0, width / 1.5, height / 1.5],
            "rotation": 0,
            "userUnit": 1,
            "imagePixels": 0,
        },
    }
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + (
            chunk(b"tEXt", b"RO_SOURCE_GEOMETRY\0" + json.dumps(value, separators=(",", ":")).encode("ascii"))
            if metadata
            else b""
        )
        + chunk(b"IDAT", zlib.compress(b"\0" + b"\xff\xff\xff" * 2) if compressed is None else compressed)
        + chunk(b"IEND", b"")
    )


class PdfPageTests(unittest.TestCase):
    def setUp(self):
        self.request = request()
        self.wire = png()
        self.delivery = AuthenticatedPageDelivery(
            self.wire,
            self.request.binding.producer,
            self.request.binding.attempt.job_id,
            self.request.binding.attempt.attempt_id,
            1,
            RawParserArtifact(
                stage_id=identity(201),
                object_sha256=hashlib.sha256(self.wire).hexdigest(),
                byte_length=len(self.wire),
                media_type="image/png",
            ),
        )

    def test_one_page_preserves_exact_bytes_and_request_binding(self):
        result = decode_page(self.request, self.delivery, 1)
        self.assertEqual((2, 1), (result.width_pixels, result.height_pixels))
        self.assertEqual(self.wire, result.png)
        self.assertEqual(self.request.binding, result.binding)
        self.assertEqual(1, result.page_index)
        self.assertEqual(1, result.geometry.user_unit)
        self.assertNotIn("PNG", repr(result))

    def test_receipt_attempt_page_and_surface_substitution_are_denied(self):
        for delivery in (
            replace(self.delivery, attempt_id=identity(202)),
            replace(self.delivery, page_index=0),
            replace(self.delivery, page_index=True),
            replace(self.delivery, wire=self.wire + b"private"),
            replace(
                self.delivery,
                artifact_receipt=self.delivery.artifact_receipt.model_copy(update={"object_sha256": "f" * 64}),
            ),
        ):
            with self.subTest(delivery=repr(delivery)), self.assertRaises(ParseProblem) as failure:
                decode_page(self.request, delivery, 1)
            self.assertIsNone(failure.exception.__context__)
        for raw in (
            png(40000001, 1),
            png(0, 1),
            self.wire[:-1],
            self.wire + self.wire,
            self.wire[:20] + b"\xff" + self.wire[21:],
        ):
            with self.assertRaises(ValueError):
                png_dimensions(raw)

    def test_current_authority_and_monotonic_cancellation_fence_delivery(self):
        worker = Mock()
        worker.render_page.return_value = self.delivery
        test = self

        class Sources:
            denied = False
            stopped = False

            @contextmanager
            def read_source(self, source, **kwargs):
                test.assertEqual(test.request.binding.source, source)
                yield Mock()

            def deliver(self, source, *, actor, action):
                if self.denied:
                    raise RuntimeError("private revoked session")
                return action()

        sources = Sources()
        self.assertEqual(
            self.wire, render_page(self.request, 1, worker, sources, actor=Mock(), cancelled=lambda: False).png
        )
        sources.denied = True
        with self.assertRaises(ParseProblem) as failure:
            render_page(self.request, 1, worker, sources, actor=Mock(), cancelled=lambda: False)
        self.assertEqual("parse-delivery-denied", failure.exception.code)
        self.assertIsNone(failure.exception.__context__)
        worker.reset_mock()
        for cancellation in (lambda: True, lambda: "invalid"):
            with self.assertRaises(ParseProblem):
                render_page(self.request, 1, worker, sources, actor=Mock(), cancelled=cancellation)
        worker.render_page.assert_not_called()
        sources.denied = False
        observations = iter((False, True, False))
        with self.assertRaises(ParseProblem):
            render_page(self.request, 1, worker, sources, actor=Mock(), cancelled=lambda: next(observations, False))

    def test_crc_correct_empty_truncated_expanding_or_trailing_pixel_stream_is_rejected(self):
        valid = zlib.compress(b"\0\xff\xff\xff")
        for compressed in (
            b"",
            valid[:-1],
            valid + valid,
            zlib.compress(b"\0" * 100000),
            zlib.compress(b"\x05\xff\xff\xff"),
        ):
            with self.subTest(length=len(compressed)), self.assertRaises(ValueError):
                png_dimensions(png(1, 1, compressed=compressed))

    def test_pipeline_reuses_one_authenticated_installed_runtime_for_rendering(self):
        installed = InstalledParser(object(), self.request.binding.producer)
        substituted = InstalledParser(
            object(), self.request.binding.producer.model_copy(update={"configuration_sha256": "f" * 64})
        )
        runtime = Mock()
        runtime.load.side_effect = (installed, substituted)
        runtime.run.return_value = self.wire
        stager = Mock()
        stager.return_value = self.delivery.artifact_receipt
        sources = Mock()
        sources.read_source.return_value = MagicMock()
        sources.read_source.return_value.__enter__.return_value = Mock()
        sources.deliver.side_effect = lambda source, actor, action: action()
        pipeline = InstalledParserPipeline(stage_raw=stager, sources=sources, runtime=runtime)
        self.assertEqual(self.wire, pipeline.render(self.request, 1, actor=Mock(), cancelled=lambda: False).png)
        self.assertEqual(1, runtime.load.call_count)
        self.assertIs(installed, runtime.run.call_args.args[0])

    def test_missing_substituted_geometry_or_wrong_requested_page_cannot_be_delivered(self):
        def delivered(wire):
            return replace(
                self.delivery,
                wire=wire,
                artifact_receipt=self.delivery.artifact_receipt.model_copy(
                    update={"object_sha256": hashlib.sha256(wire).hexdigest(), "byte_length": len(wire)}
                ),
            )

        for wire in (
            png(metadata=False),
            png(page_index=0),
            png(page_index=True),
            png(
                geometry={
                    "mediaBox": [0, 0, 10, 10],
                    "cropBox": [0, 0, 10, 10],
                    "rotation": 0,
                    "userUnit": 1,
                    "imagePixels": 0,
                }
            ),
        ):
            with self.assertRaises(ParseProblem):
                decode_page(self.request, delivered(wire), 1)

    def test_rotated_cropped_scaled_page_retains_mapping_to_original_ir_points(self):
        geometry = {
            "mediaBox": [-20, -30, 592, 762],
            "cropBox": [10, 20, 550, 730],
            "rotation": 90,
            "userUnit": 2,
            "imagePixels": 0,
        }
        width, height = 1065, 810
        pixels = zlib.compress((b"\0" + b"\xff\xff\xff" * width) * height)
        wire = png(width, height, compressed=pixels, geometry=geometry)
        delivery = replace(
            self.delivery,
            wire=wire,
            artifact_receipt=self.delivery.artifact_receipt.model_copy(
                update={"object_sha256": hashlib.sha256(wire).hexdigest(), "byte_length": len(wire)}
            ),
        )
        result = decode_page(self.request, delivery, 1)
        self.assertEqual((1065, 810), (result.width_pixels, result.height_pixels))
        self.assertEqual(
            (100.0, 1344.0, 180.0, 1444.0),
            result.geometry.region(
                {"l": 20, "t": 520, "r": 70, "b": 480, "coord_origin": "BOTTOMLEFT"}, result.geometry.display_size
            ),
        )


if __name__ == "__main__":
    unittest.main()
