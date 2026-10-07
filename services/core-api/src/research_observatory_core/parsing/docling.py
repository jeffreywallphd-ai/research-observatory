"""Validate pinned raw output and create staged IR, with no revision writer."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import TypeAdapter

from ..ports.docling_parsing import AuthenticatedDoclingDelivery, DoclingWorkerPort
from ..ports.parsing import AuthenticatedParseDelivery, ParseProblem, ReadOnlyDocumentSource
from .contracts import (
    CellConfidence,
    CodepointRange,
    ConfidenceObservation,
    DocumentIR,
    IRFigure,
    IRNode,
    IRReference,
    IRTable,
    IRTableCell,
    NodeKind,
    ParseQualityReport,
    ParserDescriptor,
    ParserWarning,
    RawParserArtifact,
    SourceLocator,
    SourcePage,
    TextProjection,
    TextSpan,
    UnavailableLocator,
)
from .normalization import MAX_IR_BYTES, NORMALIZATION_VERSION, UNICODE_VERSION
from .pdf_geometry import PdfGeometryError, PdfPageGeometry
from .pipeline import _nonfinite, _unique_object
from .requests import ParseRequest, ParseSuccess

DOCLING_MEDIA_TYPE = "application/vnd.research-observatory.docling-output+json"
UNKNOWN = ConfidenceObservation(state="unknown", value=None)
MAX_DOCLING_ENTRIES = 100000
_LOCATOR: TypeAdapter[SourceLocator] = TypeAdapter(SourceLocator)
_REF = re.compile(r"#/(?:body|furniture|(?:groups|texts|pictures|tables|key_value_items|form_items)/[0-9]+)\Z")
_LABELS: dict[str, NodeKind] = {
    "title": "title",
    "section_header": "title",
    "text": "paragraph",
    "paragraph": "paragraph",
    "list_item": "list-item",
    "footnote": "footnote",
    "caption": "caption",
    "reference": "reference",
    "table": "table",
    "picture": "figure",
    "formula": "equation",
    "list": "list",
    "ordered_list": "list",
    "unordered_list": "list",
    "unspecified": "region",
}


def _dict(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("docling-value-invalid")
    return value


def _list(value: object) -> list[Any]:
    if type(value) is not list or len(value) > MAX_DOCLING_ENTRIES:
        raise ValueError("docling-array-invalid")
    return value


def _text(value: object) -> str:
    if type(value) is not str:
        raise ValueError("docling-text-invalid")
    return value


def _count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 100000:
        raise ValueError("docling-count-invalid")
    return value


def _ref(value: object) -> str:
    record = _dict(value)
    if set(record) != {"$ref"} or not isinstance(record["$ref"], str) or _REF.fullmatch(record["$ref"]) is None:
        raise ValueError("docling-reference-invalid")
    return record["$ref"]


def _preflight_expansion(document: dict[str, Any], checkpoint: Callable[[], None]) -> None:
    entries = relationships = 0
    for group in ("body", "furniture", "groups", "texts", "pictures", "tables", "key_value_items", "form_items"):
        items = [document[group]] if group in {"body", "furniture"} else _list(document[group])
        entries += len(items)
        if entries > MAX_DOCLING_ENTRIES:
            raise ValueError("docling-expansion-oversize")
        for record in items:
            checkpoint()
            item = _dict(record)
            relationships += len(_list(item.get("children")))
            if item.get("label") == "table":
                entries += len(_list(_dict(item.get("data")).get("table_cells")))
            if item.get("label") == "picture":
                relationships += len(_list(item.get("captions", [])))
            if entries > MAX_DOCLING_ENTRIES or relationships > MAX_DOCLING_ENTRIES:
                raise ValueError("docling-expansion-oversize")


def _build_ir(
    request: ParseRequest,
    raw: dict[str, Any],
    artifact: RawParserArtifact,
    cancelled: Callable[[], bool] | None = None,
) -> DocumentIR:
    steps = 0

    def checkpoint(*, force: bool = False) -> None:
        nonlocal steps
        steps += 1
        if (force or steps % 256 == 0) and cancelled is not None and cancelled():
            raise ValueError("docling-decode-cancelled")

    checkpoint(force=True)
    if set(raw) != {
        "schemaVersion",
        "documentType",
        "inputSha256",
        "inputLength",
        "format",
        "status",
        "document",
        "sourcePages",
        "locations",
        "geometryWarnings",
    } or (
        raw["schemaVersion"] != "2.0"
        or raw["documentType"] != "docling-parser-output"
        or raw["status"] not in {"success", "partial_success"}
        or (raw["inputSha256"], raw["inputLength"], raw["format"])
        != (request.binding.source.object_sha256, request.binding.source.byte_length, request.binding.source.format)
        or type(raw["inputLength"]) is not int
    ):
        raise ValueError("docling-source-invalid")
    document = _dict(raw["document"])
    if document.get("schema_name") != "DoclingDocument" or document.get("version") != "1.10.0":
        raise ValueError("docling-version-invalid")
    if set(document) != {
        "schema_name",
        "version",
        "name",
        "origin",
        "furniture",
        "body",
        "groups",
        "texts",
        "pictures",
        "tables",
        "key_value_items",
        "form_items",
        "pages",
    }:
        raise ValueError("docling-document-invalid")
    _preflight_expansion(document, checkpoint)
    checkpoint(force=True)
    geometries = tuple(PdfPageGeometry.from_native(_dict(page)) for page in _list(raw["sourcePages"]))
    display_pages = _dict(document["pages"])
    if request.binding.source.format == "pdf":
        if (
            not geometries
            or len(geometries) > 500
            or set(display_pages) != {str(i + 1) for i in range(len(geometries))}
        ):
            raise ValueError("docling-pages-invalid")
    elif geometries or display_pages:
        raise ValueError("docling-pages-invalid")
    pages = tuple(
        SourcePage(
            page_index=i,
            width=page.width_points,
            height=page.height_points,
            rotation=page.rotation,
            unit="points",
            origin="top-left",
            frame="unrotated-source-page",
        )
        for i, page in enumerate(geometries)
    )
    locations = _dict(raw["locations"])
    geometry_warnings = {_text(value) for value in _list(raw["geometryWarnings"])}
    index: dict[str, dict[str, Any]] = {}
    for group in ("body", "furniture", "groups", "texts", "pictures", "tables", "key_value_items", "form_items"):
        items = [document[group]] if group in {"body", "furniture"} else _list(document[group])
        for position, record in enumerate(items):
            checkpoint()
            item = _dict(record)
            key = f"#/{group}" if group in {"body", "furniture"} else f"#/{group}/{position}"
            if item.get("self_ref") != key or key in index:
                raise ValueError("docling-node-identity-invalid")
            _text(item.get("label"))
            _list(item.get("children"))
            if key not in {"#/body", "#/furniture"}:
                _ref(item.get("parent"))
            index[key] = item
    ordered: list[tuple[str, str | None]] = []
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[tuple[str, str | None, bool]] = [("#/furniture", None, False), ("#/body", None, False)]
    while stack:
        checkpoint()
        key, parent, end = stack.pop()
        if end:
            active.remove(key)
            continue
        if key in visited or key in active or key not in index or len(ordered) >= MAX_DOCLING_ENTRIES:
            raise ValueError("docling-node-graph-invalid")
        item = index[key]
        if parent is not None and _ref(item["parent"]) != parent:
            raise ValueError("docling-node-parent-invalid")
        visited.add(key)
        active.add(key)
        ordered.append((key, parent))
        stack.append((key, parent, True))
        for child in reversed(item["children"]):
            stack.append((_ref(child), key, False))
    if visited != set(index):
        raise ValueError("docling-node-unreachable")
    ids: dict[str, str] = {}
    spans: dict[str, TextSpan] = {}
    nodes: list[IRNode] = []
    projections: list[TextProjection] = []
    tables: list[IRTable] = []
    warnings = [ParserWarning(code="machine-layout-unverified", severity="warning", node_id=None, detail=None)]
    if raw["status"] == "partial_success":
        warnings.append(ParserWarning(code="parser-partial-output", severity="warning", node_id=None, detail=None))
    text_pages: set[int] = set()
    total_text_bytes = 0
    used_locations: set[str] = set()
    node_locations: dict[str, SourceLocator] = {}

    def content(key: str, text: str) -> TextSpan:
        nonlocal total_text_bytes
        total_text_bytes += len(text.encode("utf-8"))
        if total_text_bytes > MAX_IR_BYTES:
            raise ValueError("docling-text-oversize")
        projection = TextProjection.from_raw(f"docling-text-{len(projections)}", text)
        projections.append(projection)
        span = TextSpan(
            projection_id=projection.projection_id,
            normalized_range=CodepointRange(start=0, end=len(projection.normalized_text)),
            raw_ranges=(CodepointRange(start=0, end=len(text)),) if text else (),
        )
        spans[key] = span
        return span

    def locator(key: str, item: dict[str, Any], *, cell: bool = False) -> SourceLocator:
        supplied = locations.get(key)
        prov = _list(item.get("prov", []))
        if supplied is None:
            return UnavailableLocator(
                kind="unavailable", reason="not-reported" if geometries else "format-has-no-pages"
            )
        used_locations.add(key)
        location = _LOCATOR.validate_python(supplied)
        if len(prov) != 1 or type(prov[0].get("page_no")) is not int or not 0 < prov[0]["page_no"] <= len(geometries):
            raise ValueError("docling-location-page-invalid")
        page_index = prov[0]["page_no"] - 1
        geometry = geometries[page_index]
        page = _dict(display_pages[str(page_index + 1)])
        size = _dict(page["size"])
        box = item["bbox"] if cell else prov[0]["bbox"]
        try:
            expected = geometry.region(_dict(box), (size["width"], size["height"]))
            if (
                expected[0] < 0
                or expected[1] < 0
                or expected[2] > geometry.width_points
                or expected[3] > geometry.height_points
            ):
                raise PdfGeometryError("parser-geometry-outside-page")
        except PdfGeometryError:
            if location != UnavailableLocator(kind="unavailable", reason="unsupported-location"):
                raise ValueError("docling-location-invalid") from None
        else:
            if (
                location.kind != "page-region"
                or location.page_index != page_index
                or (location.x0, location.y0, location.x1, location.y1) != expected
            ):
                raise ValueError("docling-location-mismatch")
        return location

    for key, parent in ordered:
        checkpoint()
        item = index[key]
        node_id = f"docling-node-{len(nodes)}"
        ids[key] = node_id
        label = item["label"]
        kind = _LABELS.get(label, "unknown")
        text = _text(item.get("orig", item.get("text", "")))
        span = content(key, text)
        location = locator(key, item)
        node_locations[key] = location
        item_warnings = []
        if kind == "unknown":
            item_warnings.append(
                ParserWarning(code="unsupported-parser-block", severity="warning", node_id=node_id, detail=None)
            )
        if key in geometry_warnings:
            item_warnings.append(
                ParserWarning(code="source-geometry-unavailable", severity="warning", node_id=node_id, detail=None)
            )
        nodes.append(
            IRNode(
                staged_id=node_id,
                kind=kind,
                order=len(nodes),
                parent_id=ids.get(parent) if parent is not None else None,
                text=span,
                locator=location,
                confidence=UNKNOWN,
                warnings=tuple(item_warnings),
                source_element_type=label,
            )
        )
        if text.strip():
            for prov in _list(item.get("prov", [])):
                page_no = _dict(prov).get("page_no")
                if type(page_no) is int and 0 < page_no <= len(pages):
                    text_pages.add(page_no - 1)
        if kind != "table":
            continue
        data = _dict(item.get("data"))
        rows, columns = _count(data.get("num_rows")), _count(data.get("num_cols"))
        cells = []
        for cell_index, raw_cell in enumerate(_list(data.get("table_cells"))):
            checkpoint()
            cell = _dict(raw_cell)
            cell_key = f"{key}/cell/{cell_index}"
            cell_id = f"docling-node-{len(nodes)}"
            ids[cell_key] = cell_id
            cell_text = _text(cell.get("text"))
            cell_span = content(cell_key, cell_text)
            cell_location = locator(cell_key, dict(cell, prov=item.get("prov", [])), cell=True)
            nodes.append(
                IRNode(
                    staged_id=cell_id,
                    kind="table-cell",
                    order=len(nodes),
                    parent_id=node_id,
                    text=cell_span,
                    locator=cell_location,
                    confidence=UNKNOWN,
                    warnings=(),
                    source_element_type="table-cell",
                )
            )
            row, column = _count(cell.get("start_row_offset_idx")), _count(cell.get("start_col_offset_idx"))
            row_span, col_span = _count(cell.get("row_span")), _count(cell.get("col_span"))
            if (_count(cell.get("end_row_offset_idx")), _count(cell.get("end_col_offset_idx"))) != (
                row + row_span,
                column + col_span,
            ):
                raise ValueError("docling-table-span-invalid")
            cells.append(
                IRTableCell(
                    node_id=cell_id,
                    row=row,
                    column=column,
                    row_span=row_span,
                    column_span=col_span,
                    raw_text=cell_span,
                    confidence=UNKNOWN,
                )
            )
            if cell_text.strip() and cell_location.kind == "page-region":
                text_pages.add(cell_location.page_index)
        tables.append(IRTable(node_id=node_id, rows=rows, columns=columns, cells=tuple(cells), grid_state="ambiguous"))
        warnings.append(ParserWarning(code="table-layout-unverified", severity="warning", node_id=node_id, detail=None))
    if used_locations != set(locations) or not geometry_warnings <= index.keys():
        raise ValueError("docling-location-identity-invalid")
    references: list[IRReference] = []
    for key, _parent in ordered:
        checkpoint()
        if index[key]["label"] == "reference":
            order = len(references)
            references.append(
                IRReference(
                    staged_id=f"docling-reference-{order}",
                    node_id=ids[key],
                    order=order,
                    raw_text=spans[key],
                    identifiers=(),
                )
            )
    figures = []
    for key, _parent in ordered:
        checkpoint()
        item = index[key]
        if item["label"] != "picture":
            continue
        captions = [_ref(value) for value in _list(item.get("captions", []))]
        if any(caption not in spans or index[caption]["label"] != "caption" for caption in captions):
            raise ValueError("docling-caption-invalid")
        figures.append(
            IRFigure(
                node_id=ids[key],
                caption=spans[captions[0]] if len(captions) == 1 else None,
                locator=node_locations[key],
                preview_stage_id=None,
            )
        )
    missing = tuple(i for i in range(len(pages)) if i not in text_pages)
    if missing:
        warnings.append(ParserWarning(code="missing-text-ocr-disabled", severity="warning", node_id=None, detail=None))
    checkpoint(force=True)
    return DocumentIR(
        schema_version="1.0",
        disposition="staged",
        binding=request.binding,
        normalization_version=NORMALIZATION_VERSION,
        unicode_version=UNICODE_VERSION,
        text_projections=tuple(projections),
        pages=pages,
        nodes=tuple(nodes),
        references=tuple(references),
        citations=(),
        tables=tuple(tables),
        figures=tuple(figures),
        raw_artifacts=(artifact,),
        quality=ParseQualityReport(
            missing_text_pages=missing if pages else None,
            replacement_characters=sum(p.raw_text.count("\ufffd") for p in projections),
            reading_order="ambiguous",
            anchor_coverage=UNKNOWN,
            unresolved_references=None,
            table_cell_confidence=tuple(
                CellConfidence(node_id=cell.node_id, confidence=UNKNOWN) for table in tables for cell in table.cells
            ),
            warnings=tuple(warnings),
        ),
    )


def decode_docling(
    request: ParseRequest,
    delivery: AuthenticatedDoclingDelivery,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> AuthenticatedParseDelivery:
    invalid_request = False
    try:
        request = ParseRequest.model_validate(request)
    except ValueError:
        invalid_request = True
    if invalid_request:
        raise ParseProblem("parse-request-invalid")
    mismatch = True
    artifact = None
    try:
        producer = ParserDescriptor.model_validate(delivery.producer)
        artifact = RawParserArtifact.model_validate(delivery.artifact_receipt)
        mismatch = (
            producer != request.binding.producer
            or producer.kind != "docling-cpu"
            or producer.version != "2.126.0"
            or request.binding.source.format not in {"pdf", "docx"}
            or delivery.job_id != request.binding.attempt.job_id
            or delivery.attempt_id != request.binding.attempt.attempt_id
        )
    except ValueError, TypeError, AttributeError:
        pass
    if mismatch:
        raise ParseProblem("parse-producer-mismatch")
    result = None
    if type(delivery.wire) is bytes and 0 < len(delivery.wire) <= MAX_IR_BYTES and artifact is not None:
        try:
            if (artifact.media_type, artifact.byte_length, artifact.object_sha256) != (
                DOCLING_MEDIA_TYPE,
                len(delivery.wire),
                hashlib.sha256(delivery.wire).hexdigest(),
            ):
                raise ValueError("docling-receipt-invalid")
            value = json.loads(
                delivery.wire.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_nonfinite
            )
            ir = _build_ir(request, _dict(value), artifact, cancelled)
            if cancelled is not None and cancelled():
                raise ValueError("docling-decode-cancelled")
            result = (
                ParseSuccess(schema_version="1.0", kind="success", binding=request.binding, ir=ir)
                .model_dump_json(by_alias=True)
                .encode()
            )
            if len(result) > MAX_IR_BYTES:
                result = None
        except ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError, UnicodeError:
            result = None
    if result is None or artifact is None:
        raise ParseProblem("parse-output-invalid")
    return AuthenticatedParseDelivery(
        wire=result,
        producer=delivery.producer,
        job_id=delivery.job_id,
        attempt_id=delivery.attempt_id,
        artifact_receipts=(artifact,),
    )


class DoclingDocumentParser:
    def __init__(self, worker: DoclingWorkerPort) -> None:
        self.worker = worker

    def parse(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedParseDelivery:
        return decode_docling(
            request, self.worker.parse_source(request, source, cancelled=cancelled), cancelled=cancelled
        )
