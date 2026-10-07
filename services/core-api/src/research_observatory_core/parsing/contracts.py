"""Versioned protected parser values; never grants, paths or accepted revisions.

JSON Schema establishes wire shape. The Core semantic validator additionally
checks graph, mapping, geometry and trusted-attempt relationships. Parser IDs
are staged IDs; only the later revision repository can mint canonical elements.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import ContractModel
from .normalization import (
    MAX_IR_BYTES,
    NORMALIZATION_VERSION,
    UNICODE_VERSION,
    MappingRun,
    NormalizedText,
    normalize_text,
)

type Identity = Annotated[
    str, Field(strict=True, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
]
type ProjectIdentity = Annotated[
    str, Field(strict=True, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
]
type Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
type Token = Annotated[str, Field(strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")]
type Text = Annotated[str, Field(strict=True)]
type Count = Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]
type PositiveCount = Annotated[int, Field(strict=True, gt=0, le=2**53 - 1)]
type Coordinate = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
type Format = Literal["jats", "tei", "xml", "html", "pdf", "docx", "plain-text"]


def _json_default(value: object) -> object:
    if isinstance(value, ContractModel):
        return value.model_dump(mode="json", by_alias=True)
    raise ValueError("ir-value-invalid")


class IRValue(ContractModel):
    model_config = ConfigDict(revalidate_instances="always", hide_input_in_errors=True, validate_default=True)

    @model_validator(mode="before")
    @classmethod
    def scalar_and_size_boundary(cls, value: object) -> object:
        size = 0
        try:
            encoder = json.JSONEncoder(
                ensure_ascii=False, allow_nan=False, default=_json_default, separators=(",", ":")
            )
            for fragment in encoder.iterencode(value):
                size += len(fragment.encode("utf-8", errors="strict"))
                if size > MAX_IR_BYTES:
                    raise ValueError("ir-too-large")
        except TypeError, ValueError, RecursionError, UnicodeError:
            raise ValueError("ir-invalid-or-too-large") from None
        return value


class CodepointRange(IRValue):
    start: Count
    end: Count

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("ir-range-invalid")
        return self


class TextMapping(IRValue):
    kind: Literal["identity", "transform"]
    normalized_range: CodepointRange
    raw_ranges: tuple[CodepointRange, ...]


class TextProjection(IRValue):
    projection_id: Token
    normalization_version: Literal["ro-text-nfc-1"]
    unicode_version: Literal["16.0.0"]
    raw_text: Text = Field(repr=False)
    normalized_text: Text = Field(repr=False)
    mappings: tuple[TextMapping, ...] = Field(repr=False)

    @classmethod
    def from_raw(cls, projection_id: str, raw: str) -> Self:
        result = normalize_text(raw)
        return cls(
            projection_id=projection_id,
            normalization_version=NORMALIZATION_VERSION,
            unicode_version=UNICODE_VERSION,
            raw_text=raw,
            normalized_text=result.normalized_text,
            mappings=tuple(
                TextMapping(
                    kind=mapping.kind,
                    normalized_range=CodepointRange(start=mapping.normalized_start, end=mapping.normalized_end),
                    raw_ranges=tuple(CodepointRange(start=start, end=end) for start, end in mapping.raw_ranges),
                )
                for mapping in result.mappings
            ),
        )

    @model_validator(mode="after")
    def exact_projection(self) -> Self:
        result = normalize_text(self.raw_text)
        supplied = tuple(
            MappingRun(
                item.kind,
                item.normalized_range.start,
                item.normalized_range.end,
                tuple((part.start, part.end) for part in item.raw_ranges),
            )
            for item in self.mappings
        )
        if self.normalized_text != result.normalized_text or supplied != result.mappings:
            raise ValueError("ir-text-projection-invalid")
        return self


class TextSpan(IRValue):
    projection_id: Token
    normalized_range: CodepointRange
    raw_ranges: tuple[CodepointRange, ...]


class TextLocator(IRValue):
    kind: Literal["text"]
    projection_id: Token
    raw_ranges: tuple[CodepointRange, ...]


class PageRegionLocator(IRValue):
    kind: Literal["page-region"]
    page_index: Annotated[int, Field(strict=True, ge=0, lt=500)]
    x0: Coordinate
    y0: Coordinate
    x1: Coordinate
    y1: Coordinate
    unit: Literal["points"]
    origin: Literal["top-left"]
    frame: Literal["unrotated-source-page"]

    @model_validator(mode="after")
    def rectangle(self) -> Self:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("ir-region-invalid")
        return self


class UnavailableLocator(IRValue):
    kind: Literal["unavailable"]
    reason: Literal["not-reported", "format-has-no-pages", "unsupported-location", "parser-unavailable"]


type SourceLocator = Annotated[TextLocator | PageRegionLocator | UnavailableLocator, Field(discriminator="kind")]


class ConfidenceObservation(IRValue):
    state: Literal["reported", "unknown", "not-reported", "not-applicable", "unavailable"]
    value: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None

    @model_validator(mode="after")
    def reported_only(self) -> Self:
        if (self.state == "reported") != (self.value is not None):
            raise ValueError("ir-confidence-state-invalid")
        return self


class ParserWarning(IRValue):
    code: Token
    severity: Literal["information", "warning", "error"]
    node_id: Token | None
    detail: Text | None = Field(repr=False)


class SourcePage(IRValue):
    page_index: Annotated[int, Field(strict=True, ge=0, lt=500)]
    width: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    height: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    rotation: Literal[0, 90, 180, 270]
    unit: Literal["points"]
    origin: Literal["top-left"]
    frame: Literal["unrotated-source-page"]

    @field_validator("rotation", mode="before")
    @classmethod
    def integer_rotation(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("ir-rotation-invalid")
        return value


class LocalOrigin(IRValue):
    kind: Literal["local-import"]


class AcquisitionOrigin(IRValue):
    kind: Literal["remote-acquisition"]
    location_id: Identity
    receipt_sha256: Digest


class SourceIdentity(IRValue):
    project_id: ProjectIdentity
    attachment_id: Identity
    document_id: Identity
    document_revision_id: Identity
    candidate_id: Identity
    source_assertion_revision_id: Identity
    work_id: Identity
    work_revision_id: Identity
    version_id: Identity
    version_revision_id: Identity
    object_sha256: Digest
    byte_length: Annotated[int, Field(strict=True, ge=0, le=128 * 1024 * 1024)]
    format: Format
    provenance: Annotated[LocalOrigin | AcquisitionOrigin, Field(discriminator="kind")]


class ParserAsset(IRValue):
    component: Token
    version: Token
    sha256: Digest


class ParserDescriptor(IRValue):
    parser_id: Token
    version: Token
    kind: Literal["native", "docling-cpu", "degraded-inspection"]
    input_formats: tuple[Format, ...] = Field(min_length=1)
    configuration_version: Token
    configuration_sha256: Digest
    assets: tuple[ParserAsset, ...]

    @model_validator(mode="after")
    def unique_components(self) -> Self:
        if len(set(self.input_formats)) != len(self.input_formats) or len({a.component for a in self.assets}) != len(
            self.assets
        ):
            raise ValueError("parser-descriptor-duplicate")
        return self


class ParseAttempt(IRValue):
    job_id: Identity
    attempt_id: Identity
    activity_version: Token


class ParseBinding(IRValue):
    source: SourceIdentity
    attempt: ParseAttempt
    producer: ParserDescriptor
    selection_sha256: Digest

    @model_validator(mode="after")
    def source_format(self) -> Self:
        if self.source.format not in self.producer.input_formats:
            raise ValueError("parser-source-format-mismatch")
        return self


class RawParserArtifact(IRValue):
    stage_id: Identity
    object_sha256: Digest
    byte_length: Count
    media_type: Annotated[str, Field(strict=True, pattern=r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")]


type NodeKind = Literal[
    "region",
    "title",
    "abstract",
    "section",
    "paragraph",
    "sentence",
    "list",
    "list-item",
    "footnote",
    "reference",
    "citation-marker",
    "table",
    "table-cell",
    "figure",
    "caption",
    "equation",
    "unknown",
]


class IRNode(IRValue):
    staged_id: Token
    kind: NodeKind
    order: Count
    parent_id: Token | None
    text: TextSpan | None
    locator: SourceLocator
    confidence: ConfidenceObservation
    warnings: tuple[ParserWarning, ...]
    source_element_type: Text | None = Field(repr=False)

    @model_validator(mode="after")
    def retain_unknown(self) -> Self:
        if self.kind == "unknown" and (not self.source_element_type or self.text is None):
            raise ValueError("ir-unknown-content-missing")
        return self


class ReferenceIdentifier(IRValue):
    scheme: Token
    observed: Text = Field(repr=False)


class IRReference(IRValue):
    staged_id: Token
    node_id: Token
    order: Count
    raw_text: TextSpan
    identifiers: tuple[ReferenceIdentifier, ...]


class IRCitation(IRValue):
    staged_id: Token
    node_id: Token
    marker: TextSpan
    reference_candidates: tuple[Token, ...]
    resolution: Literal["candidate", "ambiguous", "unresolved"]


class IRTableCell(IRValue):
    node_id: Token
    row: Count
    column: Count
    row_span: PositiveCount
    column_span: PositiveCount
    raw_text: TextSpan
    confidence: ConfidenceObservation


def _overlapping_cells(cells: tuple[IRTableCell, ...]) -> bool:
    # Sweep rows over compressed column endpoints, without expanding spans
    # into a potentially source-controlled number of occupied grid squares.
    if not cells:
        return False
    columns = sorted({edge for cell in cells for edge in (cell.column, cell.column + cell.column_span)})
    indices = {edge: index for index, edge in enumerate(columns)}
    count = len(columns) - 1
    maxima = [0] * (4 * count)
    increments = [0] * (4 * count)

    def update(node: int, low: int, high: int, start: int, end: int, delta: int) -> None:
        if start <= low and high <= end:
            maxima[node] += delta
            increments[node] += delta
            return
        middle = (low + high) // 2
        if start < middle:
            update(node * 2 + 1, low, middle, start, end, delta)
        if end > middle:
            update(node * 2 + 2, middle, high, start, end, delta)
        maxima[node] = increments[node] + max(maxima[node * 2 + 1], maxima[node * 2 + 2])

    events = sorted(
        (row, delta, indices[cell.column], indices[cell.column + cell.column_span])
        for cell in cells
        for row, delta in ((cell.row, 1), (cell.row + cell.row_span, -1))
    )
    for _row, delta, start, end in events:
        update(0, 0, count, start, end, delta)
        if maxima[0] > 1:
            return True
    return False


class IRTable(IRValue):
    node_id: Token
    rows: Count
    columns: Count
    cells: tuple[IRTableCell, ...]
    grid_state: Literal["reported", "ambiguous"]

    @model_validator(mode="after")
    def cell_indices(self) -> Self:
        positions: set[tuple[int, int]] = set()
        nodes: set[str] = set()
        for cell in self.cells:
            position = (cell.row, cell.column)
            if (
                position in positions
                or cell.node_id in nodes
                or cell.row + cell.row_span > self.rows
                or cell.column + cell.column_span > self.columns
            ):
                raise ValueError("ir-table-cell-invalid")
            positions.add(position)
            nodes.add(cell.node_id)
        if self.grid_state == "reported" and _overlapping_cells(self.cells):
            raise ValueError("ir-table-reported-grid-overlap")
        return self


class IRFigure(IRValue):
    node_id: Token
    caption: TextSpan | None
    locator: SourceLocator
    preview_stage_id: Identity | None


class CellConfidence(IRValue):
    node_id: Token
    confidence: ConfidenceObservation


class ParseQualityReport(IRValue):
    missing_text_pages: tuple[Count, ...] | None
    replacement_characters: Count | None
    reading_order: Literal["reported-order", "ambiguous", "unavailable"]
    anchor_coverage: ConfidenceObservation
    unresolved_references: Count | None
    table_cell_confidence: tuple[CellConfidence, ...]
    warnings: tuple[ParserWarning, ...]


class DocumentIR(IRValue):
    schema_version: Literal["1.0"]
    disposition: Literal["staged", "inspection-only"]
    binding: ParseBinding
    normalization_version: Literal["ro-text-nfc-1"]
    unicode_version: Literal["16.0.0"]
    text_projections: tuple[TextProjection, ...] = Field(repr=False)
    pages: tuple[SourcePage, ...] = Field(max_length=500)
    nodes: tuple[IRNode, ...] = Field(repr=False)
    references: tuple[IRReference, ...] = Field(repr=False)
    citations: tuple[IRCitation, ...] = Field(repr=False)
    tables: tuple[IRTable, ...] = Field(repr=False)
    figures: tuple[IRFigure, ...] = Field(repr=False)
    raw_artifacts: tuple[RawParserArtifact, ...]
    quality: ParseQualityReport

    @model_validator(mode="after")
    def semantic_relationships(self) -> Self:
        projections = {p.projection_id: p for p in self.text_projections}
        if len(projections) != len(self.text_projections) or tuple(p.page_index for p in self.pages) != tuple(
            range(len(self.pages))
        ):
            raise ValueError("ir-projection-or-page-identity-invalid")
        nodes: dict[str, IRNode] = {}
        normalized = {
            key: NormalizedText(
                projection.raw_text,
                projection.normalized_text,
                tuple(
                    MappingRun(
                        mapping.kind,
                        mapping.normalized_range.start,
                        mapping.normalized_range.end,
                        tuple((part.start, part.end) for part in mapping.raw_ranges),
                    )
                    for mapping in projection.mappings
                ),
            )
            for key, projection in projections.items()
        }

        def ranges_valid(projection_id: str, ranges: tuple[CodepointRange, ...]) -> TextProjection:
            projection = projections.get(projection_id)
            if projection is None:
                raise ValueError("ir-projection-unavailable")
            previous = -1
            for part in ranges:
                if part.start < previous or part.end <= part.start or part.end > len(projection.raw_text):
                    raise ValueError("ir-raw-range-invalid")
                previous = part.end
            return projection

        def span_valid(span: TextSpan | None) -> None:
            if span is None:
                return
            ranges_valid(span.projection_id, span.raw_ranges)
            expected = normalized[span.projection_id].raw_ranges_for(
                span.normalized_range.start, span.normalized_range.end
            )
            if expected != tuple((part.start, part.end) for part in span.raw_ranges):
                raise ValueError("ir-span-mapping-invalid")

        def locator_valid(locator: SourceLocator) -> None:
            if isinstance(locator, TextLocator):
                ranges_valid(locator.projection_id, locator.raw_ranges)
            elif isinstance(locator, PageRegionLocator):
                if locator.page_index >= len(self.pages):
                    raise ValueError("ir-page-unavailable")
                page = self.pages[locator.page_index]
                if locator.x1 > page.width or locator.y1 > page.height:
                    raise ValueError("ir-page-region-outside-source")

        def node_content_valid(node_id: str, content: TextSpan) -> None:
            span_valid(content)
            text = nodes[node_id].text
            # Both spans have exact contributor mappings. Containment in this
            # projection therefore includes every raw contributor without an
            # additional quadratic scan or a monotone raw-offset assumption.
            if (
                text is None
                or content.projection_id != text.projection_id
                or content.normalized_range.start < text.normalized_range.start
                or content.normalized_range.end > text.normalized_range.end
            ):
                raise ValueError("ir-semantic-node-content-mismatch")

        for order, node in enumerate(self.nodes):
            if (
                node.staged_id in nodes
                or node.order != order
                or (node.parent_id is not None and node.parent_id not in nodes)
            ):
                raise ValueError("ir-node-order-or-parent-invalid")
            nodes[node.staged_id] = node
            span_valid(node.text)
            locator_valid(node.locator)
            if (
                node.text is not None
                and isinstance(node.locator, TextLocator)
                and (
                    node.text.projection_id != node.locator.projection_id
                    or any(
                        not any(
                            location.start <= text.start and text.end <= location.end
                            for location in node.locator.raw_ranges
                        )
                        for text in node.text.raw_ranges
                    )
                )
            ):
                raise ValueError("ir-node-text-location-mismatch")
        references: set[str] = set()
        for order, reference in enumerate(self.references):
            if (
                reference.staged_id in references
                or reference.order != order
                or reference.node_id not in nodes
                or nodes[reference.node_id].kind != "reference"
            ):
                raise ValueError("ir-reference-invalid")
            references.add(reference.staged_id)
            node_content_valid(reference.node_id, reference.raw_text)
        citation_ids: set[str] = set()
        for citation in self.citations:
            if (
                citation.staged_id in citation_ids
                or citation.node_id not in nodes
                or nodes[citation.node_id].kind != "citation-marker"
                or len(set(citation.reference_candidates)) != len(citation.reference_candidates)
                or not set(citation.reference_candidates).issubset(references)
            ):
                raise ValueError("ir-citation-invalid")
            if (
                (citation.resolution == "unresolved" and citation.reference_candidates)
                or (citation.resolution == "candidate" and len(citation.reference_candidates) != 1)
                or (citation.resolution == "ambiguous" and len(citation.reference_candidates) < 2)
            ):
                raise ValueError("ir-citation-state-invalid")
            citation_ids.add(citation.staged_id)
            node_content_valid(citation.node_id, citation.marker)
        table_ids: set[str] = set()
        for table in self.tables:
            if table.node_id in table_ids or table.node_id not in nodes or nodes[table.node_id].kind != "table":
                raise ValueError("ir-table-invalid")
            table_ids.add(table.node_id)
            for cell in table.cells:
                if (
                    cell.node_id not in nodes
                    or nodes[cell.node_id].kind != "table-cell"
                    or nodes[cell.node_id].parent_id != table.node_id
                ):
                    raise ValueError("ir-table-cell-parent-invalid")
                node_content_valid(cell.node_id, cell.raw_text)
        artifacts = {a.stage_id: a for a in self.raw_artifacts}
        if len(artifacts) != len(self.raw_artifacts):
            raise ValueError("ir-artifact-duplicate")
        figure_ids: set[str] = set()
        for figure in self.figures:
            if (
                figure.node_id in figure_ids
                or figure.node_id not in nodes
                or nodes[figure.node_id].kind != "figure"
                or (figure.preview_stage_id is not None and figure.preview_stage_id not in artifacts)
            ):
                raise ValueError("ir-figure-invalid")
            figure_ids.add(figure.node_id)
            span_valid(figure.caption)
            locator_valid(figure.locator)
        quality_cells: set[str] = set()
        for item in self.quality.table_cell_confidence:
            if item.node_id in quality_cells or item.node_id not in nodes or nodes[item.node_id].kind != "table-cell":
                raise ValueError("ir-quality-cell-unavailable")
            quality_cells.add(item.node_id)
        if self.quality.missing_text_pages is not None and (
            len(set(self.quality.missing_text_pages)) != len(self.quality.missing_text_pages)
            or any(page >= len(self.pages) for page in self.quality.missing_text_pages)
        ):
            raise ValueError("ir-quality-page-unavailable")
        for warning in (*self.quality.warnings, *(warning for node in self.nodes for warning in node.warnings)):
            if warning.node_id is not None and warning.node_id not in nodes:
                raise ValueError("ir-warning-node-unavailable")
        if (self.disposition == "inspection-only") != (self.binding.producer.kind == "degraded-inspection"):
            raise ValueError("ir-disposition-producer-mismatch")
        return self
