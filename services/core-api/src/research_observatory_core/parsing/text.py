"""Bounded UTF-8 native text output, with authenticated raw retention."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from ..ports.native_parsing import AuthenticatedNativeDelivery, NativeStructureWorkerPort
from ..ports.parsing import AuthenticatedParseDelivery, ParseProblem, ReadOnlyDocumentSource
from .contracts import (
    CodepointRange,
    ConfidenceObservation,
    DocumentIR,
    IRNode,
    ParseQualityReport,
    ParserWarning,
    RawParserArtifact,
    TextLocator,
    TextProjection,
    TextSpan,
)
from .normalization import MAX_IR_BYTES, NORMALIZATION_VERSION, UNICODE_VERSION, normalize_text
from .pipeline import _nonfinite, _unique_object
from .requests import ParseRequest, ParseSuccess

TEXT_MEDIA_TYPE = "application/vnd.research-observatory.text-parser-output+json"
UNKNOWN = ConfidenceObservation(state="unknown", value=None)


def _ir(
    request: ParseRequest, raw: object, artifact: RawParserArtifact, cancelled: Callable[[], bool] | None
) -> DocumentIR:
    if (
        type(raw) is not dict
        or set(raw) != {"schemaVersion", "documentType", "text"}
        or raw["schemaVersion"] != "1.0"
        or raw["documentType"] != "bounded-text-parser-output"
        or type(raw["text"]) is not str
    ):
        raise ValueError("text-output-invalid")

    def checkpoint() -> None:
        if cancelled is not None and cancelled():
            raise ValueError("text-decode-cancelled")

    def string_size(value: str) -> int:
        size = 2
        for offset in range(0, len(value), 4096):
            checkpoint()
            size += len(json.dumps(value[offset : offset + 4096], ensure_ascii=False).encode()) - 2
            if size > MAX_IR_BYTES:
                raise ValueError("text-ir-oversize")
        return size

    # Charge actual escaped raw/normalized strings and wire mappings before
    # allocating the Pydantic graph. This is a necessary lower bound on the
    # existing serialized IR budget, not another format or character quota.
    size = string_size(raw["text"])
    normalized = normalize_text(raw["text"], cancelled=cancelled)
    size += string_size(normalized.normalized_text)
    for mapping in normalized.mappings:
        checkpoint()
        value = {
            "kind": mapping.kind,
            "normalizedRange": {"start": mapping.normalized_start, "end": mapping.normalized_end},
            "rawRanges": [{"start": start, "end": end} for start, end in mapping.raw_ranges],
        }
        size += len(json.dumps(value, separators=(",", ":")).encode())
        if size > MAX_IR_BYTES:
            raise ValueError("text-ir-oversize")
    checkpoint()
    text = TextProjection.from_raw("source-text", raw["text"])
    length = len(text.normalized_text)
    ranges = tuple(CodepointRange(start=start, end=end) for start, end in normalized.raw_ranges_for(0, length))
    return DocumentIR(
        schema_version="1.0",
        disposition="staged",
        binding=request.binding,
        normalization_version=NORMALIZATION_VERSION,
        unicode_version=UNICODE_VERSION,
        text_projections=(text,),
        pages=(),
        nodes=(
            IRNode(
                staged_id="source-text",
                kind="paragraph",
                order=0,
                parent_id=None,
                text=TextSpan(
                    projection_id=text.projection_id,
                    normalized_range=CodepointRange(start=0, end=length),
                    raw_ranges=ranges,
                ),
                locator=TextLocator(kind="text", projection_id=text.projection_id, raw_ranges=ranges),
                confidence=UNKNOWN,
                warnings=(),
                source_element_type="plain-text",
            ),
        ),
        references=(),
        citations=(),
        tables=(),
        figures=(),
        raw_artifacts=(artifact,),
        quality=ParseQualityReport(
            missing_text_pages=(),
            replacement_characters=raw["text"].count("\ufffd"),
            reading_order="reported-order",
            anchor_coverage=UNKNOWN,
            unresolved_references=None,
            table_cell_confidence=(),
            warnings=(
                ParserWarning(code="plain-text-structure-unavailable", severity="warning", node_id=None, detail=None),
            ),
        ),
    )


def decode_text(
    request: ParseRequest, delivery: AuthenticatedNativeDelivery, *, cancelled: Callable[[], bool] | None = None
) -> AuthenticatedParseDelivery:
    output = None
    try:
        request = ParseRequest.model_validate(request)
        artifact = RawParserArtifact.model_validate(delivery.artifact_receipt)
        if (
            request.selection.outcome != "selected"
            or request.binding.source.format != "plain-text"
            or request.binding.producer.parser_id != "ro-native-text"
            or request.binding.producer.kind != "native"
            or delivery.producer != request.binding.producer
            or (delivery.job_id, delivery.attempt_id)
            != (request.binding.attempt.job_id, request.binding.attempt.attempt_id)
            or type(delivery.wire) is not bytes
            or not 0 < len(delivery.wire) <= MAX_IR_BYTES
            or (artifact.media_type, artifact.object_sha256, artifact.byte_length)
            != (TEXT_MEDIA_TYPE, hashlib.sha256(delivery.wire).hexdigest(), len(delivery.wire))
        ):
            raise ValueError("text-delivery-invalid")
        raw = json.loads(
            delivery.wire.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object, parse_constant=_nonfinite
        )
        value = ParseSuccess(
            schema_version="1.0", kind="success", binding=request.binding, ir=_ir(request, raw, artifact, cancelled)
        )
        wire = value.model_dump_json(by_alias=True).encode()
        if len(wire) > MAX_IR_BYTES:
            raise ValueError("text-ir-oversize")
        output = AuthenticatedParseDelivery(wire, delivery.producer, delivery.job_id, delivery.attempt_id, (artifact,))
    except Exception:
        pass
    if output is None:
        raise ParseProblem("parse-output-invalid")
    return output


class BoundedTextParser:
    def __init__(self, worker: NativeStructureWorkerPort) -> None:
        self._worker = worker

    def parse(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedParseDelivery:
        return decode_text(
            request, self._worker.parse_source(request, source, cancelled=cancelled), cancelled=cancelled
        )
