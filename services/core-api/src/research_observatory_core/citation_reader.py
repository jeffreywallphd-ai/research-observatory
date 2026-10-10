"""One inert citation/context preview; full source values stay protected."""

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .anchors.contracts import SourceAnchorTarget
from .document_citations import CitationProblem, Resolution
from .document_revisions import protected_json
from .parsing.contracts import (
    CodepointRange,
    ConfidenceObservation,
    Digest,
    Identity,
    IRValue,
    ProjectIdentity,
    SourceIdentity,
)
from .reconciliation.contracts import CanonicalWorkReference


class CitationReferencePreview(IRValue):
    reference_id: Identity
    node_id: Identity
    order: int = Field(strict=True, ge=0, le=999)
    link_state: Literal["exact-linked", "candidate", "ambiguous", "unresolved", "non-scholarly", "rejected"]
    target: CanonicalWorkReference | None

    @model_validator(mode="after")
    def coherent(self):
        if (self.link_state == "exact-linked") != (self.target is not None):
            raise ValueError("citation-reader-reference-invalid")
        return self


class CitationTargetPreview(IRValue):
    label: str = Field(strict=True, min_length=1, max_length=512, repr=False)
    resolution: Resolution
    reference_count: int = Field(strict=True, ge=0, le=1000)
    references: tuple[CitationReferencePreview, ...] = Field(max_length=4)

    @model_validator(mode="after")
    def coherent(self):
        if (
            len(self.references) != min(4, self.reference_count)
            or self.resolution
            != ("unresolved" if not self.reference_count else "candidate" if self.reference_count == 1 else "ambiguous")
            or len({r.reference_id for r in self.references}) != len(self.references)
        ):
            raise ValueError("citation-reader-target-invalid")
        return self


class CitationContextPreview(IRValue):
    node_id: Identity
    projection_id: Identity
    normalized_range: CodepointRange
    marker_range: CodepointRange | None
    text_preview: str = Field(strict=True, max_length=1024, repr=False)
    text_length: int = Field(strict=True, ge=0, le=65536)
    preview_start: int = Field(strict=True, ge=0)
    truncated: bool
    basis: Literal["source-element", "sentence-pattern"]

    @model_validator(mode="after")
    def coherent(self):
        span = self.normalized_range
        if (
            self.text_length != span.end - span.start
            or not span.start <= self.preview_start <= span.end
            or (
                self.preview_start + len(self.text_preview) > span.end
                or self.truncated != (self.text_length > len(self.text_preview))
            )
            or (
                self.marker_range is not None
                and not span.start <= self.marker_range.start < self.marker_range.end <= span.end
            )
        ):
            raise ValueError("citation-reader-context-invalid")
        return self


class CitationReaderEntry(IRValue):
    order: int = Field(strict=True, ge=0, le=999)
    canonical_citation_id: Identity | None
    node_id: Identity
    text_offset: int = Field(strict=True, ge=0)
    node_text_start: int = Field(strict=True, ge=0)
    marker_preview: str = Field(strict=True, max_length=256, repr=False)
    marker_length: int = Field(strict=True, ge=0, le=65536)
    marker_truncated: bool
    style: Literal["reported", "numeric", "author-year", "narrative", "superscript"]
    knowledge_status: Literal["extracted", "inferred"]
    resolution: Resolution
    targets: tuple[CitationTargetPreview, ...] = Field(max_length=4, repr=False)
    target_count: int = Field(strict=True, ge=0, le=128)
    anchor: SourceAnchorTarget | None = Field(repr=False)
    anchor_truncated: bool
    paragraph: CitationContextPreview | None = Field(repr=False)
    sentence: CitationContextPreview | None = Field(repr=False)
    context_reason: Literal["available", "not-reported", "normalization-boundary", "empty-marker"]
    confidence: ConfidenceObservation

    @model_validator(mode="after")
    def coherent(self):
        if (
            len(self.targets) != min(4, self.target_count)
            or self.marker_length < len(self.marker_preview)
            or (self.marker_truncated != (self.marker_length > len(self.marker_preview)))
            or ((self.knowledge_status == "extracted") != (self.canonical_citation_id is not None))
        ):
            raise ValueError("citation-reader-entry-invalid")
        if self.target_count == len(self.targets):
            expected = (
                "unresolved"
                if not self.targets or any(t.resolution == "unresolved" for t in self.targets)
                else ("ambiguous" if any(t.resolution == "ambiguous" for t in self.targets) else "candidate")
            )
            if self.resolution != expected:
                raise ValueError("citation-reader-entry-invalid")
        if (
            self.anchor is not None
            and self.anchor.text_position is not None
            and self.anchor.text_position.start != self.node_text_start + self.text_offset
        ):
            raise ValueError("citation-reader-entry-offset-invalid")
        return self


class CitationReaderPage(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    source: SourceIdentity
    document_revision_id: Identity
    collection_id: Identity
    collection_revision_id: Identity
    reference_collection_id: Identity
    reference_collection_revision_id: Identity
    content_sha256: Digest
    structure_sha256: Digest
    total: int = Field(strict=True, ge=0, le=1000)
    after_order: int | None = Field(strict=True, ge=0, le=999)
    next_after_order: int | None = Field(strict=True, ge=0, le=999)
    entries: tuple[CitationReaderEntry, ...] = Field(max_length=1, repr=False)
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        start = 0 if self.after_order is None else self.after_order + 1
        count = min(1, max(0, self.total - start))
        if (
            self.source.project_id != self.project_id
            or self.source.document_revision_id == self.document_revision_id
            or (
                len(self.entries) != count
                or self.collection_id == self.collection_revision_id
                or self.reference_collection_id == self.reference_collection_revision_id
                or self.next_after_order != (start if count and start + 1 < self.total else None)
            )
        ):
            raise ValueError("citation-reader-page-invalid")
        for entry in self.entries:
            if entry.order != start or (
                entry.anchor is not None
                and (
                    entry.anchor.project_id,
                    entry.anchor.revision_id,
                    entry.anchor.source,
                    entry.anchor.node_id,
                    entry.anchor.content_sha256,
                    entry.anchor.structure_sha256,
                )
                != (
                    self.project_id,
                    self.document_revision_id,
                    self.source,
                    entry.node_id,
                    self.content_sha256,
                    self.structure_sha256,
                )
            ):
                raise ValueError("citation-reader-source-invalid")
        if len(self.model_dump_json(by_alias=True).encode()) > 65536:
            raise ValueError("citation-reader-limit")
        return self


class CitationReaderNotice(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    source: SourceIdentity
    document_revision_id: Identity
    collection_id: Identity
    collection_revision_id: Identity
    status: Literal["unavailable"] = "unavailable"
    reason_code: Literal["viewer-resource-limit", "citations-unavailable"]
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        if (
            self.source.project_id != self.project_id
            or self.source.document_revision_id == self.document_revision_id
            or self.collection_id == self.collection_revision_id
        ):
            raise ValueError("citation-reader-source-invalid")
        return self


def _preview(context):
    if context is None:
        return None
    span = context.text_span.normalized_range
    offset = max(0, context.marker_range.start - span.start - 256) if context.marker_range else 0
    return CitationContextPreview(
        node_id=context.node_id,
        projection_id=context.text_span.projection_id,
        normalized_range=span,
        marker_range=context.marker_range,
        text_preview=context.normalized_text[offset : offset + 1024],
        text_length=len(context.normalized_text),
        preview_start=span.start + offset,
        truncated=len(context.normalized_text) > 1024,
        basis=context.basis,
    )


def reader_page(collection, source, references, accepted, *, after_order=None):
    if (
        references.collection_id,
        references.collection_revision_id,
        hashlib.sha256(protected_json(references)).hexdigest(),
    ) != (
        collection.reference_collection_id,
        collection.reference_collection_revision_id,
        collection.reference_payload_sha256,
    ) or (accepted.revision_id, accepted.content_sha256, accepted.structure_sha256) != (
        collection.document_revision_id,
        collection.content_sha256,
        collection.structure_sha256,
    ):
        raise CitationProblem("citation-reader-reference-changed")
    if after_order is not None and (type(after_order) is not int or not 0 <= after_order < len(collection.entries)):
        raise CitationProblem("citation-reader-page-invalid")
    refs = {r.reference_id: r for r in references.entries}
    nodes = {n.node_id: n for n in accepted.structure.nodes}
    start = 0 if after_order is None else after_order + 1
    previews = []
    for entry in collection.entries[start : start + 1]:
        targets = []
        for group in entry.targets[:4]:
            targets.append(
                CitationTargetPreview(
                    label=group.label,
                    resolution=group.resolution,
                    reference_count=len(group.reference_ids),
                    references=tuple(
                        CitationReferencePreview(
                            reference_id=identity,
                            node_id=refs[identity].node_id,
                            order=refs[identity].order,
                            link_state=refs[identity].link_state,
                            target=refs[identity].target,
                        )
                        for identity in group.reference_ids[:4]
                    ),
                )
            )
        previews.append(
            CitationReaderEntry(
                order=entry.order,
                canonical_citation_id=entry.canonical_citation_id,
                node_id=entry.node_id,
                text_offset=entry.marker_span.normalized_range.start - nodes[entry.node_id].text.normalized_range.start,
                node_text_start=nodes[entry.node_id].text.normalized_range.start,
                marker_preview=entry.raw_marker[:256],
                marker_length=len(entry.raw_marker),
                marker_truncated=len(entry.raw_marker) > 256,
                style=entry.style,
                knowledge_status=entry.knowledge_status,
                resolution=entry.resolution,
                targets=tuple(targets),
                target_count=len(entry.targets),
                anchor=entry.anchor,
                anchor_truncated=entry.anchor_truncated,
                paragraph=_preview(entry.paragraph),
                sentence=_preview(entry.sentence),
                context_reason=entry.context_reason,
                confidence=entry.confidence,
            )
        )
    return CitationReaderPage(
        project_id=collection.project_id,
        source=source,
        document_revision_id=collection.document_revision_id,
        collection_id=collection.collection_id,
        collection_revision_id=collection.collection_revision_id,
        reference_collection_id=references.collection_id,
        reference_collection_revision_id=references.collection_revision_id,
        content_sha256=collection.content_sha256,
        structure_sha256=collection.structure_sha256,
        total=len(collection.entries),
        after_order=after_order,
        next_after_order=start if start + 1 < len(collection.entries) else None,
        entries=tuple(previews),
    )
