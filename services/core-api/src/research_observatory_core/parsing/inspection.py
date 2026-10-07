"""Degraded text/page inspection is a separate attempt, never accepted structure."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from ..ports.parsing import AuthenticatedParseDelivery, ParseProblem, ReadOnlyDocumentSource
from ..ports.pdf_inspection import AuthenticatedInspectionDelivery, PdfInspectionWorkerPort
from .contracts import (
    CodepointRange,
    ConfidenceObservation,
    DocumentIR,
    IRNode,
    ParseAttempt,
    ParseBinding,
    ParseQualityReport,
    ParserDescriptor,
    ParserWarning,
    RawParserArtifact,
    SourcePage,
    TextProjection,
    TextSpan,
    UnavailableLocator,
)
from .normalization import MAX_IR_BYTES, NORMALIZATION_VERSION, UNICODE_VERSION, normalize_text
from .pdf_geometry import PdfPageGeometry
from .pipeline import _nonfinite, _unique_object
from .requests import ParseFailure, ParseRequest, ParseResult, ParseSuccess
from .selection import ParserRegistry, RegisteredParser, SelectionSource, select_parser, selection_sha256

INSPECTION_MEDIA_TYPE = "application/vnd.research-observatory.pdf-inspection+json"
UNKNOWN = ConfidenceObservation(state="unknown", value=None)


def prepare_inspection_request(
    prior: ParseRequest,
    result: ParseResult,
    producer: ParserDescriptor,
    attempt: ParseAttempt,
) -> ParseRequest:
    """Core calls this with its actual terminal result and a new durable attempt.

    This returns a selection value, not a workflow lease, source grant or launch.
    The installed adapter and encrypted stager independently enforce those.
    """
    request = None
    try:
        prior = ParseRequest.model_validate(prior)
        producer = ParserDescriptor.model_validate(producer)
        attempt = ParseAttempt.model_validate(attempt)
        if not isinstance(result, ParseFailure):
            raise ValueError
        result = ParseFailure.model_validate(result)
        if (
            result.binding != prior.binding
            or producer.kind != "degraded-inspection"
            or prior.binding.producer.kind != "docling-cpu"
            or attempt.attempt_id == prior.binding.attempt.attempt_id
        ):
            raise ValueError
        source = prior.binding.source
        selection = select_parser(
            (SelectionSource(source, "available", "primary"),),
            ParserRegistry((RegisteredParser(producer, "available"),)),
            primary_attachment_id=source.attachment_id,
            fallback_from=(prior.binding.attempt.attempt_id, result.code, prior.selection),
        )
        request = ParseRequest(
            schema_version="1.0",
            selection=selection,
            binding=ParseBinding(
                source=source, producer=producer, selection_sha256=selection_sha256(selection), attempt=attempt
            ),
        )
    except Exception:
        pass
    if request is None:
        raise ParseProblem("parse-producer-mismatch")
    return request


def _ir(request, raw, artifact):
    if (
        type(raw) is not dict
        or set(raw)
        != {
            "schemaVersion",
            "documentType",
            "inputSha256",
            "inputLength",
            "pages",
        }
        or raw["schemaVersion"] != "1.0"
        or raw["documentType"] != "pdf-inspection-output"
        or (raw["inputSha256"], raw["inputLength"])
        != (
            request.binding.source.object_sha256,
            request.binding.source.byte_length,
        )
        or type(raw["inputLength"]) is not int
        or type(raw["pages"]) is not list
        or not 0 < len(raw["pages"]) <= 500
    ):
        raise ValueError
    pages, projections, nodes, missing = [], [], [], []
    for index, item in enumerate(raw["pages"]):
        if type(item) is not dict or set(item) != {"geometry", "text"} or type(item["text"]) is not str:
            raise ValueError
        geometry = PdfPageGeometry.from_native(item["geometry"])
        geometry.admit_render()
        pages.append(
            SourcePage(
                page_index=index,
                width=geometry.width_points,
                height=geometry.height_points,
                rotation=geometry.rotation,
                unit="points",
                origin="top-left",
                frame="unrotated-source-page",
            )
        )
        text = TextProjection.from_raw("inspection-text-" + str(index), item["text"])
        projections.append(text)
        length = len(text.normalized_text)
        ranges = normalize_text(item["text"]).raw_ranges_for(0, length)
        if not item["text"].strip():
            missing.append(index)
        # Page order is observed; no block geometry or scholarly order is invented.
        nodes.append(
            IRNode(
                staged_id="inspection-page-text-" + str(index),
                kind="paragraph",
                order=index,
                parent_id=None,
                text=TextSpan(
                    projection_id=text.projection_id,
                    normalized_range=CodepointRange(start=0, end=length),
                    raw_ranges=tuple(CodepointRange(start=a, end=b) for a, b in ranges),
                ),
                locator=UnavailableLocator(kind="unavailable", reason="not-reported"),
                confidence=UNKNOWN,
                warnings=(),
                source_element_type="pdf-page-text",
            )
        )
    warnings = [ParserWarning(code="inspection-only-fallback", severity="warning", node_id=None, detail=None)]
    if missing:
        warnings.append(ParserWarning(code="missing-text-ocr-disabled", severity="warning", node_id=None, detail=None))
    return DocumentIR(
        schema_version="1.0",
        disposition="inspection-only",
        binding=request.binding,
        normalization_version=NORMALIZATION_VERSION,
        unicode_version=UNICODE_VERSION,
        text_projections=tuple(projections),
        pages=tuple(pages),
        nodes=tuple(nodes),
        references=(),
        citations=(),
        tables=(),
        figures=(),
        raw_artifacts=(artifact,),
        quality=ParseQualityReport(
            missing_text_pages=tuple(missing),
            replacement_characters=sum(t.raw_text.count("\ufffd") for t in projections),
            reading_order="ambiguous",
            anchor_coverage=UNKNOWN,
            unresolved_references=None,
            table_cell_confidence=(),
            warnings=tuple(warnings),
        ),
    )


def decode_inspection(request: ParseRequest, delivery: AuthenticatedInspectionDelivery) -> AuthenticatedParseDelivery:
    output = None
    try:
        request = ParseRequest.model_validate(request)
        artifact = RawParserArtifact.model_validate(delivery.artifact_receipt)
        if (
            request.selection.outcome != "inspection-only"
            or request.binding.source.format != "pdf"
            or request.binding.producer.kind != "degraded-inspection"
            or delivery.producer != request.binding.producer
            or (delivery.job_id, delivery.attempt_id)
            != (
                request.binding.attempt.job_id,
                request.binding.attempt.attempt_id,
            )
            or type(delivery.wire) is not bytes
            or not 0 < len(delivery.wire) <= MAX_IR_BYTES
            or (artifact.media_type, artifact.object_sha256, artifact.byte_length)
            != (
                INSPECTION_MEDIA_TYPE,
                hashlib.sha256(delivery.wire).hexdigest(),
                len(delivery.wire),
            )
        ):
            raise ValueError
        raw = json.loads(
            delivery.wire.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object, parse_constant=_nonfinite
        )
        value = ParseSuccess(
            schema_version="1.0", kind="success", binding=request.binding, ir=_ir(request, raw, artifact)
        )
        output = AuthenticatedParseDelivery(
            value.model_dump_json(by_alias=True).encode(),
            delivery.producer,
            delivery.job_id,
            delivery.attempt_id,
            (artifact,),
        )
    except Exception:
        pass
    if output is None:
        raise ParseProblem("parse-output-invalid")
    return output


class PdfInspectionAdapter:
    def __init__(self, worker: PdfInspectionWorkerPort) -> None:
        self._worker = worker

    def parse(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedParseDelivery:
        return decode_inspection(request, self._worker.parse_source(request, source, cancelled=cancelled))
