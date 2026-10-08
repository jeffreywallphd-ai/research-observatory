"""Portable selectors; content is Core-derived, never renderer-supplied authority."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from ..document_revisions import AcceptedDocumentRevision, CanonicalNode, Instant
from ..parsing.contracts import (
    CodepointRange,
    ConfidenceObservation,
    Count,
    Digest,
    Identity,
    IRValue,
    NodeKind,
    ProjectIdentity,
    SourceIdentity,
)
from ..parsing.normalization import normalize_text

MAX_QUOTE_CODEPOINTS = 2048
MAX_CONTEXT_CODEPOINTS = 8192
CONTEXT_MARGIN_CODEPOINTS = 512
QUOTE_MARGIN_CODEPOINTS = 64
ANCHOR_MEDIA_TYPE = "application/vnd.research-observatory.source-anchor+json"
MAX_ANCHOR_BYTES = 32 * 1024

type UnitCoordinate = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
type CoordinatesState = Literal[
    "available", "not-reported", "format-has-no-pages", "unsupported-location", "parser-unavailable"
]


class AnchorSelection(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    revision_id: Identity
    node_id: Identity
    normalized_range: CodepointRange | None = None


class AnchorQuote(IRValue):
    exact: Annotated[str, Field(strict=True, min_length=1, max_length=MAX_QUOTE_CODEPOINTS)] = Field(repr=False)
    prefix: Annotated[str, Field(strict=True, max_length=QUOTE_MARGIN_CODEPOINTS)] = Field(repr=False)
    suffix: Annotated[str, Field(strict=True, max_length=QUOTE_MARGIN_CODEPOINTS)] = Field(repr=False)


class AnchorContext(IRValue):
    # Origin of text in the normalized projection; highlight offsets are relative
    # to this returned text, not the complete projection or UTF-16 DOM string.
    start: Count
    text: Annotated[str, Field(strict=True, max_length=MAX_CONTEXT_CODEPOINTS)] = Field(repr=False)
    highlight: CodepointRange

    @model_validator(mode="after")
    def bounded_normalized_text(self) -> Self:
        if (
            not self.highlight.start < self.highlight.end <= len(self.text)
            or normalize_text(self.text).normalized_text != self.text
        ):
            raise ValueError("anchor-context-invalid")
        return self


class NormalizedPageRegion(IRValue):
    page_index: Annotated[int, Field(strict=True, ge=0, lt=500)]
    page_number: Annotated[int, Field(strict=True, ge=1, le=500)]
    x0: UnitCoordinate
    y0: UnitCoordinate
    x1: UnitCoordinate
    y1: UnitCoordinate
    source_width: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    source_height: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    rotation: Literal[0, 90, 180, 270]
    frame: Literal["unrotated-source-page"] = "unrotated-source-page"
    origin: Literal["top-left"] = "top-left"
    unit: Literal["normalized"] = "normalized"
    granularity: Literal["block"] = "block"

    @field_validator("rotation", mode="before")
    @classmethod
    def integer_rotation(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("anchor-page-rotation-invalid")
        return value

    @model_validator(mode="after")
    def page_and_rectangle(self) -> Self:
        if self.page_number != self.page_index + 1 or self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("anchor-page-region-invalid")
        return self


class SourceAnchorTarget(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    document_id: Identity
    revision_id: Identity
    source: SourceIdentity
    content_sha256: Digest
    structure_sha256: Digest
    node_id: Identity
    node_kind: NodeKind
    block_id: Identity | None
    sentence_id: Identity | None
    projection_id: Identity | None
    normalization_version: Literal["ro-text-nfc-1"] = "ro-text-nfc-1"
    unicode_version: Literal["16.0.0"] = "16.0.0"
    text_position: CodepointRange | None
    quote: AnchorQuote | None = Field(repr=False)
    context: AnchorContext | None = Field(repr=False)
    page_region: NormalizedPageRegion | None
    coordinates_state: CoordinatesState
    confidence: ConfidenceObservation
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def selectors_agree(self) -> Self:
        if (self.project_id, self.document_id) != (self.source.project_id, self.source.document_id):
            raise ValueError("anchor-source-binding-invalid")
        if (self.coordinates_state == "available") != (self.page_region is not None):
            raise ValueError("anchor-coordinate-state-invalid")
        if (self.node_kind == "sentence") != (self.sentence_id is not None):
            raise ValueError("anchor-sentence-binding-invalid")
        if self.sentence_id is not None and self.sentence_id != self.node_id:
            raise ValueError("anchor-sentence-binding-invalid")
        text_parts = (self.projection_id, self.text_position, self.quote, self.context)
        if any(part is None for part in text_parts):
            if not all(part is None for part in text_parts):
                raise ValueError("anchor-text-selector-incomplete")
            return self
        position, quote, context = self.text_position, self.quote, self.context
        assert position is not None and quote is not None and context is not None
        start, end = context.highlight.start, context.highlight.end
        if (
            position.start != context.start + start
            or position.end != context.start + end
            or context.text[start:end] != quote.exact
            or context.text[max(0, start - QUOTE_MARGIN_CODEPOINTS) : start] != quote.prefix
            or context.text[end : end + QUOTE_MARGIN_CODEPOINTS] != quote.suffix
        ):
            raise ValueError("anchor-selector-disagreement")
        return self


class SourceAnchorReceipt(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    anchor_id: Identity
    anchor_revision_id: Identity
    created_at: Instant
    target: SourceAnchorTarget = Field(repr=False)


class SourceDocumentMetadata(IRValue):
    project_id: ProjectIdentity
    document_id: Identity
    revision_id: Identity
    accepted_at: Instant
    display_label: Annotated[str, Field(strict=True, max_length=512)] = Field(repr=False)
    label_origin: Literal["canonical-document-revision"] = "canonical-document-revision"


class AnchorStalePropagation(IRValue):
    run_id: Identity
    state: Literal["completed"]
    total_items: Count
    processed_items: Count
    stale_count: Count
    unknown_count: Count

    @model_validator(mode="after")
    def completed_writes(self) -> Self:
        if self.processed_items != self.total_items or self.stale_count + self.unknown_count > self.processed_items:
            raise ValueError("anchor-stale-propagation-incomplete")
        return self


class SourceAnchorResolution(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    anchor_id: Identity
    anchor_revision_id: Identity
    source: SourceIdentity
    metadata: SourceDocumentMetadata
    status: Literal["exact", "fallback", "missing", "broken"]
    selector_used: Literal["page-region", "structural-text", "not-resolved"]
    reason: Literal["protected-context-unavailable", "readable-text-not-reported"] | None
    target: SourceAnchorTarget | None = Field(repr=False)
    propagation: AnchorStalePropagation | None
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def exact_resolution_binding(self) -> Self:
        if (self.metadata.project_id, self.metadata.document_id) != (self.source.project_id, self.source.document_id):
            raise ValueError("anchor-resolution-source-invalid")
        if self.status in {"exact", "fallback"}:
            if (
                self.target is None
                or self.reason is not None
                or self.propagation is not None
                or self.selector_used == "not-resolved"
                or (self.target.source, self.target.revision_id) != (self.source, self.metadata.revision_id)
                or self.target.context is None
                or (self.status == "exact") != (self.target.page_region is not None)
                or self.selector_used != ("page-region" if self.status == "exact" else "structural-text")
            ):
                raise ValueError("anchor-resolution-target-invalid")
        elif (
            self.target is not None
            or self.selector_used != "not-resolved"
            or (self.status == "broken") != (self.propagation is not None)
            or self.reason
            != ("protected-context-unavailable" if self.status == "broken" else "readable-text-not-reported")
        ):
            raise ValueError("anchor-resolution-failure-invalid")
        return self


class CitationReferenceTarget(IRValue):
    reference_id: Identity
    target: SourceAnchorTarget = Field(repr=False)
    preview_truncated: bool


class CitationLinkResolution(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    citation_id: Identity
    source: SourceIdentity
    metadata: SourceDocumentMetadata
    marker: SourceAnchorTarget = Field(repr=False)
    marker_truncated: bool
    resolution: Literal["candidate", "ambiguous", "unresolved"]
    total_candidates: Count
    targets: tuple[CitationReferenceTarget, ...] = Field(max_length=2, repr=False)
    next_reference_id: Identity | None
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def reference_identity_and_uncertainty(self) -> Self:
        if (
            (self.metadata.project_id, self.metadata.document_id, self.metadata.revision_id)
            != (self.marker.project_id, self.marker.document_id, self.marker.revision_id)
            or self.marker.source != self.source
            or len({row.reference_id for row in self.targets}) != len(self.targets)
            or any(
                (row.target.source, row.target.revision_id) != (self.source, self.metadata.revision_id)
                for row in self.targets
            )
            or self.total_candidates < len(self.targets)
            or (self.resolution == "unresolved" and self.total_candidates != 0)
            or (self.resolution == "candidate" and self.total_candidates != 1)
            or (self.resolution == "ambiguous" and self.total_candidates < 2)
            or (
                self.next_reference_id is not None
                and (
                    not self.targets
                    or self.next_reference_id != self.targets[-1].reference_id
                    or self.total_candidates <= len(self.targets)
                )
            )
        ):
            raise ValueError("citation-link-resolution-invalid")
        return self


class ReaderOutlineNode(IRValue):
    node_id: Identity
    node_kind: NodeKind
    preview: Annotated[str, Field(strict=True, max_length=160)] = Field(repr=False)
    selection: AnchorSelection
    page_number: Annotated[int, Field(strict=True, ge=1, le=500)] | None
    has_text: bool


class DocumentReaderOutline(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    document_id: Identity
    revision_id: Identity
    source: SourceIdentity
    view_kind: Literal["accepted-structured-text"] = "accepted-structured-text"
    scholarly_verification: Literal["unverified"] = "unverified"
    nodes: tuple[ReaderOutlineNode, ...] = Field(max_length=50, repr=False)
    next_node_id: Identity | None


class ReaderRevisionSummary(IRValue):
    revision_id: Identity
    accepted_at: Instant


class DocumentReaderRevisions(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    source: SourceIdentity
    revisions: tuple[ReaderRevisionSummary, ...] = Field(max_length=100)


def build_target(accepted: AcceptedDocumentRevision, selection: AnchorSelection) -> SourceAnchorTarget:
    """Derive selectors only from authenticated accepted structure in Core.

    This pure conversion grants no rights or publication authority. The caller
    must obtain the accepted revision through its protected repository and bind
    the result to canonical provenance/dependencies atomically.
    """
    selection = AnchorSelection.model_validate(selection)
    if selection.revision_id != accepted.revision_id:
        raise ValueError("anchor-revision-mismatch")
    nodes = {node.node_id: node for node in accepted.structure.nodes}
    node = nodes.get(selection.node_id)
    if node is None:
        raise ValueError("anchor-node-unavailable")
    block: CanonicalNode | None = node
    if node.kind == "sentence":
        block = nodes.get(node.parent_id) if node.parent_id is not None else None
        while block is not None and block.kind == "sentence":
            block = nodes.get(block.parent_id) if block.parent_id is not None else None
    block_id = None if block is None else block.node_id
    position = quote = context = projection_id = None
    if node.text is None:
        if selection.normalized_range is not None:
            raise ValueError("anchor-node-has-no-text")
    else:
        projection_id = node.text.projection_id
        projection = next(
            (item for item in accepted.structure.text_projections if item.projection_id == projection_id), None
        )
        if projection is None:
            raise ValueError("anchor-projection-unavailable")
        position = selection.normalized_range or node.text.normalized_range
        start, end = position.start, position.end
        bounds = node.text.normalized_range
        if not bounds.start <= start < end <= bounds.end or end - start > MAX_QUOTE_CODEPOINTS:
            raise ValueError("anchor-text-range-invalid")
        normalized = projection.normalized_text
        context_start = max(bounds.start, start - CONTEXT_MARGIN_CODEPOINTS)
        context_end = min(bounds.end, end + CONTEXT_MARGIN_CODEPOINTS)
        context = AnchorContext(
            start=context_start,
            text=normalized[context_start:context_end],
            highlight=CodepointRange(start=start - context_start, end=end - context_start),
        )
        quote = AnchorQuote(
            exact=normalized[start:end],
            prefix=normalized[max(context_start, start - QUOTE_MARGIN_CODEPOINTS) : start],
            suffix=normalized[end : min(context_end, end + QUOTE_MARGIN_CODEPOINTS)],
        )
    region = None
    coordinates: CoordinatesState = "not-reported" if accepted.structure.pages else "format-has-no-pages"
    if node.locator.kind == "page-region":
        page = next((item for item in accepted.structure.pages if item.page_index == node.locator.page_index), None)
        if page is None:
            raise ValueError("anchor-page-unavailable")
        region = NormalizedPageRegion(
            page_index=page.page_index,
            page_number=page.page_index + 1,
            x0=node.locator.x0 / page.width,
            y0=node.locator.y0 / page.height,
            x1=node.locator.x1 / page.width,
            y1=node.locator.y1 / page.height,
            source_width=page.width,
            source_height=page.height,
            rotation=page.rotation,
        )
        coordinates = "available"
    elif node.locator.kind == "unavailable":
        coordinates = node.locator.reason
    return SourceAnchorTarget(
        project_id=accepted.project_id,
        document_id=accepted.document_id,
        revision_id=accepted.revision_id,
        source=accepted.result.binding.source,
        content_sha256=accepted.content_sha256,
        structure_sha256=accepted.structure_sha256,
        node_id=node.node_id,
        node_kind=node.kind,
        block_id=block_id,
        sentence_id=node.node_id if node.kind == "sentence" else None,
        projection_id=projection_id,
        text_position=position,
        quote=quote,
        context=context,
        page_region=region,
        coordinates_state=coordinates,
        confidence=node.confidence,
    )
