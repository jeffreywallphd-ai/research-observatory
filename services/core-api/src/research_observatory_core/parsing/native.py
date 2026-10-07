"""Validate authenticated native output and construct staged values in Core.

Original XML/HTML parsing remains behind NativeStructureWorkerPort. This module
does not open original files or provide a canonical revision writer.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Literal

from ..ports.native_parsing import AuthenticatedNativeDelivery, NativeStructureWorkerPort
from ..ports.parsing import AuthenticatedParseDelivery, ParseProblem, ReadOnlyDocumentSource
from .contracts import (
    CellConfidence,
    CodepointRange,
    ConfidenceObservation,
    DocumentIR,
    IRCitation,
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
    ReferenceIdentifier,
    TextLocator,
    TextProjection,
    TextSpan,
)
from .native_contracts import NATIVE_MEDIA_TYPE, NativeElement, NativeStructure
from .normalization import MAX_IR_BYTES, NORMALIZATION_VERSION, UNICODE_VERSION
from .pipeline import _nonfinite, _unique_object
from .requests import ParseRequest, ParseSuccess

UNKNOWN = ConfidenceObservation(state="unknown", value=None)


def _name(element: NativeElement) -> tuple[str, str]:
    if element.name.startswith("{") and "}" in element.name:
        namespace, local = element.name[1:].split("}", 1)
        return namespace, local
    return "", element.name


def _attrs(element: NativeElement) -> dict[str, str]:
    # Duplicate HTML attributes remain in the raw receipt and cannot silently
    # supply semantic identity, link targets, roles or table geometry.
    result: dict[str, str] = {}
    duplicates: set[str] = set()
    for attribute in element.attributes:
        if attribute.name in result:
            duplicates.add(attribute.name)
        result[attribute.name] = attribute.value
    for name in duplicates:
        del result[name]
    return result


def _kind(raw: NativeStructure, element: NativeElement) -> NodeKind:
    namespace, local = _name(element)
    allowed = {
        "jats": {"", "http://jats.nlm.nih.gov"},
        "tei": {"", "http://www.tei-c.org/ns/1.0"},
        "xml": {""},
        "html": {"", "http://www.w3.org/1999/xhtml"},
    }
    if namespace not in allowed[raw.format]:
        return "unknown"
    attrs = _attrs(element)
    maps: dict[str, dict[str, NodeKind]] = {
        "jats": {
            "article-title": "title",
            "title": "title",
            "abstract": "abstract",
            "sec": "section",
            "p": "paragraph",
            "list": "list",
            "list-item": "list-item",
            "fn": "footnote",
            "ref": "reference",
            "table": "table",
            "td": "table-cell",
            "th": "table-cell",
            "fig": "figure",
            "caption": "caption",
        },
        "tei": {
            "title": "title",
            "head": "title",
            "div": "section",
            "p": "paragraph",
            "list": "list",
            "item": "list-item",
            "bibl": "reference",
            "biblStruct": "reference",
            "table": "table",
            "cell": "table-cell",
            "figure": "figure",
            "figDesc": "caption",
            "abstract": "abstract",
        },
        "xml": {
            "title": "title",
            "abstract": "abstract",
            "section": "section",
            "p": "paragraph",
            "paragraph": "paragraph",
            "list": "list",
            "item": "list-item",
            "footnote": "footnote",
            "reference": "reference",
            "table": "table",
            "cell": "table-cell",
            "figure": "figure",
            "caption": "caption",
        },
        "html": {
            "title": "title",
            "h1": "title",
            "h2": "title",
            "h3": "title",
            "h4": "title",
            "h5": "title",
            "h6": "title",
            "article": "section",
            "section": "section",
            "p": "paragraph",
            "ul": "list",
            "ol": "list",
            "li": "list-item",
            "table": "table",
            "td": "table-cell",
            "th": "table-cell",
            "figure": "figure",
            "figcaption": "caption",
        },
    }
    if raw.format == "jats" and local == "xref" and attrs.get("ref-type") == "bibr":
        return "citation-marker"
    if raw.format == "tei":
        if local == "div" and attrs.get("type") == "abstract":
            return "abstract"
        if local == "note" and attrs.get("place") in {"foot", "bottom"}:
            return "footnote"
        if local == "ref" and attrs.get("type") == "bibl":
            return "citation-marker"
        if (
            local == "head"
            and element.parent_index is not None
            and _name(raw.elements[element.parent_index])[1] == "figure"
        ):
            return "caption"
    if raw.format == "html":
        roles: dict[str, NodeKind] = {
            "doc-abstract": "abstract",
            "doc-footnote": "footnote",
            "doc-biblioentry": "reference",
            "doc-biblioref": "citation-marker",
        }
        if attrs.get("role") in roles:
            return roles[attrs["role"]]
    if local in maps[raw.format]:
        return maps[raw.format][local]
    wrappers = {
        "jats": (
            "article front journal-meta article-meta title-group body back ref-list mixed-citation "
            "element-citation pub-id table-wrap tbody thead tfoot tr italic bold sup sub ext-link graphic label"
        ),
        "tei": (
            "TEI teiHeader fileDesc titleStmt publicationStmt sourceDesc text front body back "
            "listBibl row hi ref note idno ptr graphic"
        ),
        "xml": "document report root row em strong inline empty",
        "html": (
            "html head body div span em strong b i u s sup sub a aside header footer nav main "
            "blockquote tbody thead tfoot tr br hr code pre"
        ),
    }
    return "region" if local in wrappers[raw.format].split() else "unknown"


def _node_id(index: int) -> str:
    return f"native-node-{index}"


def _build_ir(request: ParseRequest, raw: NativeStructure, artifact: RawParserArtifact) -> DocumentIR:
    projections: list[TextProjection] = []
    spans: list[TextSpan] = []
    kinds = [_kind(raw, element) for element in raw.elements]
    # TEI permits an untyped <ref target="#...">. Classify it as a citation
    # only when an explicit target names an observed bibliography entry.
    bibliography_ids = {
        value
        for element in raw.elements
        if kinds[element.index] == "reference"
        if (value := _attrs(element).get("id", _attrs(element).get("{http://www.w3.org/XML/1998/namespace}id")))
    }
    if raw.format == "tei":
        for element in raw.elements:
            namespace, local = _name(element)
            if (
                namespace in {"", "http://www.tei-c.org/ns/1.0"}
                and local == "ref"
                and any(
                    target.startswith("#") and target[1:] in bibliography_ids
                    for target in _attrs(element).get("target", "").split()
                )
            ):
                kinds[element.index] = "citation-marker"
    warnings: list[ParserWarning] = []
    nearest_tables: list[int | None] = []
    nearest_rows: list[int | None] = []
    nearest_figures: list[int | None] = []
    rows_by_table: dict[int, list[int]] = {}
    cells_by_table: dict[int, list[NativeElement]] = {}
    total = 0
    for element in raw.elements:
        content = raw.text[element.text_start : element.text_end]
        total += len(content.encode("utf-8"))
        if total > MAX_IR_BYTES:
            raise ValueError("native-projections-too-large")
        projection = TextProjection.from_raw(f"native-text-{element.index}", content)
        projections.append(projection)
        spans.append(
            TextSpan(
                projection_id=projection.projection_id,
                normalized_range=CodepointRange(start=0, end=len(projection.normalized_text)),
                raw_ranges=(CodepointRange(start=0, end=len(content)),) if content else (),
            )
        )
        parent = element.parent_index
        table = (
            parent
            if parent is not None and kinds[parent] == "table"
            else (nearest_tables[parent] if parent is not None else None)
        )
        row = (
            parent
            if parent is not None and _name(raw.elements[parent])[1] in {"tr", "row"}
            else (nearest_rows[parent] if parent is not None else None)
        )
        nearest_tables.append(table)
        nearest_rows.append(row)
        figure = (
            parent
            if parent is not None and kinds[parent] == "figure"
            else (nearest_figures[parent] if parent is not None else None)
        )
        nearest_figures.append(figure)
        if table is not None:
            if _name(element)[1] in {"row", "tr"} and kinds[element.index] == "region":
                rows_by_table.setdefault(table, []).append(element.index)
            if kinds[element.index] == "table-cell":
                cells_by_table.setdefault(table, []).append(element)
        if kinds[element.index] == "unknown" or element.close_kind == "implicit":
            warnings.append(
                ParserWarning(
                    code="unsupported-element" if kinds[element.index] == "unknown" else "implicit-html-close",
                    severity="information",
                    node_id=_node_id(element.index),
                    detail=None,
                )
            )
    tables: list[IRTable] = []
    cell_parents: dict[int, int] = {}
    for table_index, kind in enumerate(kinds):
        if kind != "table":
            continue
        rows = rows_by_table.get(table_index, [])
        row_numbers = {index: order for order, index in enumerate(rows)}
        cells: list[IRTableCell] = []
        row_cursors: dict[int, int] = {}
        spanning: list[IRTableCell] = []
        columns = 0
        ambiguous = False
        for element in cells_by_table.get(table_index, []):
            index = element.index
            if kinds[index] != "table-cell" or nearest_tables[index] != table_index:
                continue
            attrs = _attrs(element)
            source_row = nearest_rows[index]
            row = row_numbers.get(source_row) if source_row is not None else None
            rs, cs = attrs.get("rowspan", attrs.get("rows", "1")), attrs.get("colspan", attrs.get("cols", "1"))
            geometry = {"rowspan", "colspan", "rows", "cols"}
            duplicate_geometry = len([a.name for a in element.attributes if a.name in geometry]) != len(
                {a.name for a in element.attributes if a.name in geometry}
            )
            valid = (
                not duplicate_geometry
                and row is not None
                and all(v.isascii() and v.isdecimal() and len(v) <= 16 for v in (rs, cs))
            )
            row_span, column_span = (int(rs), int(cs)) if valid else (0, 0)
            # HTML zero spans the remainder of the current source row group.
            group_end = len(rows)
            if source_row is not None and raw.format in {"html", "jats"}:
                group = raw.elements[source_row].parent_index
                group_end = next(
                    (
                        number
                        for number in range((row or 0) + 1, len(rows))
                        if raw.elements[rows[number]].parent_index != group
                    ),
                    len(rows),
                )
                if raw.format == "html" and row_span == 0 and valid:
                    row_span = group_end - (row or 0)
            if (
                not valid
                or row_span < 1
                or column_span < 1
                or row_span > group_end - (row or 0)
                or column_span > 2**53 - 1
                or (raw.format == "html" and (column_span > 1000 or row_span > 65534))
            ):
                kinds[index] = "unknown"
                ambiguous = True
                warnings.append(
                    ParserWarning(
                        code="unsupported-table-geometry", severity="warning", node_id=_node_id(index), detail=None
                    )
                )
                continue
            assert row is not None
            column = row_cursors.get(row, 0)
            occupied = sorted(
                (cell.column, cell.column + cell.column_span)
                for cell in spanning
                if cell.row <= row < cell.row + cell.row_span
            )
            for left, right in occupied:
                if column + column_span <= left:
                    break
                if column < right:
                    column = right
            if column + column_span > 2**53 - 1:
                raise ValueError("native-table-too-wide")
            cells.append(
                IRTableCell(
                    node_id=_node_id(index),
                    row=row,
                    column=column,
                    row_span=row_span,
                    column_span=column_span,
                    raw_text=spans[index],
                    confidence=UNKNOWN,
                )
            )
            cell_parents[index] = table_index
            row_cursors[row] = column + column_span
            if row_span > 1:
                spanning.append(cells[-1])
            columns = max(columns, column + column_span)
        tables.append(
            IRTable(
                node_id=_node_id(table_index),
                rows=len(rows),
                columns=columns,
                cells=tuple(cells),
                grid_state="ambiguous" if ambiguous else "reported",
            )
        )
    for index, kind in enumerate(kinds):
        if kind == "table-cell" and index not in cell_parents:
            kinds[index] = "unknown"
            warnings.append(
                ParserWarning(
                    code="unsupported-table-geometry", severity="warning", node_id=_node_id(index), detail=None
                )
            )
    parents = [cell_parents.get(e.index, e.parent_index) for e in raw.elements]
    nodes = tuple(
        IRNode(
            staged_id=_node_id(e.index),
            kind=kinds[e.index],
            order=e.index,
            parent_id=_node_id(parent) if (parent := parents[e.index]) is not None else None,
            text=spans[e.index],
            locator=TextLocator(
                kind="text", projection_id=spans[e.index].projection_id, raw_ranges=spans[e.index].raw_ranges
            ),
            confidence=UNKNOWN,
            warnings=(),
            source_element_type=e.name,
        )
        for e in raw.elements
    )
    references: list[IRReference] = []
    source_ids: dict[str, list[str]] = {}
    for element in raw.elements:
        index = element.index
        if kinds[index] != "reference":
            continue
        identifiers: list[ReferenceIdentifier] = []
        for child_index in range(index + 1, len(raw.elements)):
            child = raw.elements[child_index]
            if child.byte_start >= element.content_byte_end:
                break
            namespace, local = _name(child)
            if (raw.format == "jats" and namespace in {"", "http://jats.nlm.nih.gov"} and local == "pub-id") or (
                raw.format == "tei" and namespace in {"", "http://www.tei-c.org/ns/1.0"} and local == "idno"
            ):
                attrs = _attrs(child)
                scheme = attrs.get("pub-id-type", attrs.get("type", "unknown")).lower()
                if scheme not in {"doi", "pmid", "pmcid", "isbn", "issn", "arxiv", "uri", "url"}:
                    scheme = "unknown"
                identifiers.append(
                    ReferenceIdentifier(scheme=scheme, observed=raw.text[child.text_start : child.text_end])
                )
        reference = IRReference(
            staged_id=f"native-reference-{index}",
            node_id=_node_id(index),
            order=len(references),
            raw_text=spans[index],
            identifiers=tuple(identifiers),
        )
        references.append(reference)
        attrs = _attrs(element)
        source_id = attrs.get("id", attrs.get("{http://www.w3.org/XML/1998/namespace}id"))
        if source_id:
            source_ids.setdefault(source_id, []).append(reference.staged_id)
    citations: list[IRCitation] = []
    for element in raw.elements:
        index = element.index
        if kinds[index] != "citation-marker":
            continue
        attrs = _attrs(element)
        target = attrs.get("rid", "") if raw.format == "jats" else attrs.get("target", attrs.get("href", ""))
        targets = target.split()
        candidates: list[str] = []
        missing = not targets
        for target in targets:
            if raw.format != "jats":
                if not target.startswith("#"):
                    missing = True
                    continue
                target = target[1:]
            found = source_ids.get(target, [])
            missing |= not found
            candidates.extend(item for item in found if item not in candidates)
        resolution: Literal["candidate", "ambiguous", "unresolved"] = (
            "unresolved" if not candidates else "ambiguous" if missing or len(candidates) != 1 else "candidate"
        )
        citations.append(
            IRCitation(
                staged_id=f"native-citation-{index}",
                node_id=_node_id(index),
                marker=spans[index],
                reference_candidates=tuple(candidates),
                resolution=resolution,
            )
        )
    figures: list[IRFigure] = []
    for element in raw.elements:
        if kinds[element.index] != "figure":
            continue
        caption = next(
            (
                spans[e.index]
                for e in (raw.elements[index] for index in range(element.index + 1, len(raw.elements)))
                if nearest_figures[e.index] == element.index and kinds[e.index] == "caption"
            ),
            None,
        )
        figures.append(
            IRFigure(
                node_id=_node_id(element.index),
                caption=caption,
                locator=nodes[element.index].locator,
                preview_stage_id=None,
            )
        )
    return DocumentIR(
        schema_version="1.0",
        disposition="staged",
        binding=request.binding,
        normalization_version=NORMALIZATION_VERSION,
        unicode_version=UNICODE_VERSION,
        text_projections=tuple(projections),
        pages=(),
        nodes=nodes,
        references=tuple(references),
        citations=tuple(citations),
        tables=tuple(tables),
        figures=tuple(figures),
        raw_artifacts=(artifact,),
        quality=ParseQualityReport(
            missing_text_pages=None,
            replacement_characters=raw.text.count("\ufffd"),
            reading_order="reported-order",
            anchor_coverage=UNKNOWN,
            unresolved_references=sum(c.resolution != "candidate" for c in citations),
            table_cell_confidence=tuple(
                CellConfidence(node_id=cell.node_id, confidence=UNKNOWN) for table in tables for cell in table.cells
            ),
            warnings=tuple(warnings),
        ),
    )


def decode_native_structure(request: ParseRequest, delivery: AuthenticatedNativeDelivery) -> AuthenticatedParseDelivery:
    bad_request = False
    try:
        request = ParseRequest.model_validate(request)
    except ValueError:
        bad_request = True
    if bad_request:
        raise ParseProblem("parse-request-invalid")
    mismatch = True
    artifact = None
    try:
        producer = ParserDescriptor.model_validate(delivery.producer)
        artifact = RawParserArtifact.model_validate(delivery.artifact_receipt)
        mismatch = (
            producer != request.binding.producer
            or producer.kind != "native"
            or delivery.job_id != request.binding.attempt.job_id
            or delivery.attempt_id != request.binding.attempt.attempt_id
        )
    except ValueError, TypeError, AttributeError:
        pass
    if mismatch:
        raise ParseProblem("parse-producer-mismatch")
    if type(delivery.wire) is not bytes or len(delivery.wire) > MAX_IR_BYTES or artifact is None:
        raise ParseProblem("parse-output-invalid")
    result = None
    try:
        if (
            artifact.media_type != NATIVE_MEDIA_TYPE
            or artifact.byte_length != len(delivery.wire)
            or artifact.object_sha256 != hashlib.sha256(delivery.wire).hexdigest()
        ):
            raise ValueError("native-artifact-mismatch")
        raw = NativeStructure.model_validate(
            json.loads(
                delivery.wire.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_object,
                parse_constant=_nonfinite,
            )
        )
        source = request.binding.source
        if (raw.source_sha256, raw.source_byte_length, raw.format) != (
            source.object_sha256,
            source.byte_length,
            source.format,
        ):
            raise ValueError("native-source-mismatch")
        ir = _build_ir(request, raw, artifact)
        result = (
            ParseSuccess(schema_version="1.0", kind="success", binding=request.binding, ir=ir)
            .model_dump_json(by_alias=True)
            .encode("utf-8")
        )
        if len(result) > MAX_IR_BYTES:
            result = None
    except ValueError, TypeError, RecursionError, UnicodeError:
        result = None
    if result is None:
        raise ParseProblem("parse-output-invalid")
    return AuthenticatedParseDelivery(
        wire=result,
        producer=delivery.producer,
        job_id=delivery.job_id,
        attempt_id=delivery.attempt_id,
        artifact_receipts=(artifact,),
    )


class NativeStructuredParser:
    def __init__(self, worker: NativeStructureWorkerPort) -> None:
        self.worker = worker

    def parse(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedParseDelivery:
        return decode_native_structure(request, self.worker.parse_source(request, source, cancelled=cancelled))
