"""Bounded single-page validation and protected delivery; no viewer cache."""

import hashlib
import json
import zlib
from collections.abc import Callable

from ..ports.corpus import CorpusActor
from ..ports.parsing import ParseProblem, ProtectedParseSourcePort
from ..ports.pdf_pages import AuthenticatedPageDelivery, PagePreview, PdfPageWorkerPort
from .contracts import RawParserArtifact
from .normalization import MAX_IR_BYTES
from .pdf_geometry import PdfPageGeometry
from .pipeline import _nonfinite, _unique_object
from .requests import ParseRequest

GEOMETRY_KEY = b"RO_SOURCE_GEOMETRY\0"


def _png(raw: bytes) -> tuple[tuple[int, int], bytes | None]:
    if type(raw) is not bytes or not 45 <= len(raw) <= MAX_IR_BYTES or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError
    offset, chunks, dimensions, image_data = 8, 0, None, False
    pixels = zlib.decompressobj()
    observed = 0
    stride = expected = 0
    metadata = None

    def validate_pixels(data):
        nonlocal observed
        # Validate the closed noninterlaced RGB/RGBA shape with at most 64 KiB
        # of decoded data held at once. Do not allocate a bitmap in Core.
        for position in range(0, len(data), 65536):
            pending = data[position : position + 65536]
            while pending:
                decoded = pixels.decompress(pending, 65536)
                pending = pixels.unconsumed_tail
                if pixels.unused_data or observed + len(decoded) > expected:
                    raise ValueError
                first_filter = (-observed) % stride
                if any(decoded[i] > 4 for i in range(first_filter, len(decoded), stride)):
                    raise ValueError
                observed += len(decoded)

    while offset < len(raw):
        chunks += 1
        if chunks > 100000 or len(raw) - offset < 12:
            raise ValueError
        size = int.from_bytes(raw[offset : offset + 4], "big")
        kind = raw[offset + 4 : offset + 8]
        end = offset + 12 + size
        if end > len(raw) or kind not in {b"IHDR", b"IDAT", b"IEND", b"tEXt"}:
            raise ValueError
        body = raw[offset + 8 : end - 4]
        if zlib.crc32(kind + body) != int.from_bytes(raw[end - 4 : end], "big"):
            raise ValueError
        if kind == b"IHDR":
            if offset != 8 or size != 13 or body[8] != 8 or body[9] not in {2, 6} or body[10:] != b"\0\0\0":
                raise ValueError
            width, height = int.from_bytes(body[:4], "big"), int.from_bytes(body[4:8], "big")
            if width <= 0 or height <= 0 or width * height > 40000000:
                raise ValueError
            dimensions = width, height
            stride = width * (3 if body[9] == 2 else 4) + 1
            expected = stride * height
        elif dimensions is None:
            raise ValueError
        elif kind == b"tEXt":
            if image_data or metadata is not None or size > 4096 or not body.startswith(GEOMETRY_KEY):
                raise ValueError
            metadata = body[len(GEOMETRY_KEY) :]
        elif kind == b"IDAT":
            validate_pixels(body)
            image_data = True
        elif kind == b"IEND":
            if (
                size
                or end != len(raw)
                or not image_data
                or not pixels.eof
                or pixels.unconsumed_tail
                or pixels.unused_data
                or observed != expected
            ):
                raise ValueError
            return dimensions, metadata
        offset = end
    raise ValueError


def png_dimensions(raw: bytes) -> tuple[int, int]:
    return _png(raw)[0]


def decode_png_page(raw: bytes, page_index: int) -> tuple[int, int, PdfPageGeometry]:
    dimensions, metadata = _png(raw)
    if metadata is None:
        raise ValueError
    value = json.loads(metadata.decode("ascii"), object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    if (
        type(value) is not dict
        or set(value) != {"schemaVersion", "pageIndex", "geometry"}
        or value["schemaVersion"] != "1.0"
        or type(value["pageIndex"]) is not int
        or value["pageIndex"] != page_index
        or type(page_index) is not int
        or not 0 <= page_index < 500
    ):
        raise ValueError
    geometry = PdfPageGeometry.from_native(value["geometry"])
    if dimensions != geometry.admit_render():
        raise ValueError
    return *dimensions, geometry


def decode_page(request: ParseRequest, delivery: AuthenticatedPageDelivery, page_index: int) -> PagePreview:
    result = None
    try:
        request = ParseRequest.model_validate(request)
        receipt = RawParserArtifact.model_validate(delivery.artifact_receipt)
        if (
            request.binding.source.format != "pdf"
            or type(page_index) is not int
            or not 0 <= page_index < 500
            or type(delivery.page_index) is not int
            or delivery.page_index != page_index
            or delivery.producer != request.binding.producer
            or (delivery.job_id, delivery.attempt_id)
            != (
                request.binding.attempt.job_id,
                request.binding.attempt.attempt_id,
            )
            or (receipt.object_sha256, receipt.byte_length, receipt.media_type)
            != (
                hashlib.sha256(delivery.wire).hexdigest(),
                len(delivery.wire),
                "image/png",
            )
        ):
            raise ValueError
        width, height, geometry = decode_png_page(delivery.wire, page_index)
        result = PagePreview(request.binding, page_index, width, height, geometry, receipt, delivery.wire)
    except Exception:
        pass
    if result is None:
        raise ParseProblem("parse-output-invalid")
    return result


def render_page(
    request: ParseRequest,
    page_index: int,
    worker: PdfPageWorkerPort,
    sources: ProtectedParseSourcePort,
    *,
    actor: CorpusActor,
    cancelled: Callable[[], bool],
) -> PagePreview:
    result = None
    failure = "parse-delivery-denied"
    stopped = False

    def cancellation():
        nonlocal stopped
        try:
            value = cancelled()
            stopped = stopped or type(value) is not bool or value
        except Exception:
            stopped = True
        return stopped

    try:
        request = ParseRequest.model_validate(request)
        if request.binding.source.format != "pdf" or type(page_index) is not int or not 0 <= page_index < 500:
            raise ParseProblem("parse-request-invalid")
        if cancellation():
            raise ParseProblem("parser-failed")
        with sources.read_source(request.binding.source, actor=actor, cancelled=cancellation) as source:
            delivery = worker.render_page(request, source, page_index, cancelled=cancellation)
        preview = decode_page(request, delivery, page_index)
        if not cancellation():
            result = sources.deliver(
                request.binding.source, actor=actor, action=lambda: None if cancellation() else preview
            )
    except ParseProblem as problem:
        if problem.code in {
            "parser-timeout",
            "parser-memory-limit",
            "parser-input-invalid",
            "parser-input-unsupported",
            "parser-resource-limit",
            "parser-assets-unavailable",
            "parser-runtime-unavailable",
            "parse-source-denied",
            "parse-output-invalid",
            "parse-request-invalid",
        }:
            failure = problem.code
    except Exception:
        pass
    if result is None:
        raise ParseProblem(failure)
    return result
