"""Bounded, inert previews; complete evidence remains in encrypted collections."""

from typing import Literal

from pydantic import Field, model_validator

from .anchors.contracts import SourceAnchorTarget
from .document_references import ReferenceCollection, ReferenceMatchCandidate, ReferenceProblem
from .parsing.contracts import Digest, Identity, IRValue, ProjectIdentity, SourceIdentity
from .reconciliation.contracts import CanonicalWorkReference


class ReferenceFieldPreview(IRValue):
    name: Literal["authors", "year", "title", "venue"]
    value: str = Field(max_length=256, repr=False)
    value_count: int = Field(strict=True, ge=1, le=256)
    truncated: bool
    knowledge_status: Literal["extracted", "inferred"]


class ReferenceIdentifierPreview(IRValue):
    scheme: str = Field(min_length=1, max_length=64)
    observed: str = Field(max_length=256, repr=False)
    truncated: bool
    normalized_status: Literal["valid", "invalid", "unsupported"]
    verification_state: Literal["verified", "unverified", "disputed", "invalid", "not-reported"]
    active_for_matching: bool


class ReferenceReaderEntry(IRValue):
    reference_id: Identity
    node_id: Identity
    order: int = Field(strict=True, ge=0, le=999)
    raw_preview: str = Field(max_length=1024, repr=False)
    raw_length: int = Field(strict=True, ge=0, le=65536)
    raw_truncated: bool
    fields: tuple[ReferenceFieldPreview, ...] = Field(max_length=4, repr=False)
    identifiers: tuple[ReferenceIdentifierPreview, ...] = Field(max_length=4, repr=False)
    identifier_count: int = Field(strict=True, ge=0, le=128)
    link_state: Literal["exact-linked", "candidate", "ambiguous", "unresolved", "non-scholarly", "rejected"]
    target: CanonicalWorkReference | None
    candidates: tuple[ReferenceMatchCandidate, ...] = Field(max_length=4)
    candidate_count: int = Field(strict=True, ge=0, le=256)
    match_flags: tuple[str, ...] = Field(max_length=32)
    anchor: SourceAnchorTarget | None = Field(repr=False)
    anchor_truncated: bool

    @model_validator(mode="after")
    def coherent(self):
        if (self.link_state == "exact-linked") != (self.target is not None):
            raise ValueError("reference-reader-target-invalid")
        if self.link_state == "exact-linked" and (self.candidates or self.match_flags or self.candidate_count):
            raise ValueError("reference-reader-target-invalid")
        if self.raw_truncated != (self.raw_length > len(self.raw_preview)) or self.raw_length < len(self.raw_preview):
            raise ValueError("reference-reader-preview-invalid")
        if len(self.identifiers) != min(4, self.identifier_count) or len(self.candidates) != min(
            4, self.candidate_count
        ):
            raise ValueError("reference-reader-preview-invalid")
        if len({f.name for f in self.fields}) != len(self.fields):
            raise ValueError("reference-reader-preview-invalid")
        return self


class ReferenceReaderPage(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    source: SourceIdentity
    document_revision_id: Identity
    collection_id: Identity
    collection_revision_id: Identity
    content_sha256: Digest
    structure_sha256: Digest
    total: int = Field(strict=True, ge=0, le=1000)
    after_order: int | None = Field(strict=True, ge=0, le=999)
    next_after_order: int | None = Field(strict=True, ge=0, le=999)
    entries: tuple[ReferenceReaderEntry, ...] = Field(max_length=1, repr=False)
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        start = 0 if self.after_order is None else self.after_order + 1
        count = min(1, max(0, self.total - start))
        if (
            self.source.project_id != self.project_id
            or self.source.document_revision_id == self.document_revision_id
            or len(self.entries) != count
        ):
            raise ValueError("reference-reader-source-invalid")
        for entry in self.entries:
            if entry.order != start or (
                entry.anchor
                and (
                    entry.anchor.project_id != self.project_id
                    or entry.anchor.source != self.source
                    or entry.anchor.revision_id != self.document_revision_id
                    or entry.anchor.node_id != entry.node_id
                    or entry.anchor.content_sha256 != self.content_sha256
                    or entry.anchor.structure_sha256 != self.structure_sha256
                )
            ):
                raise ValueError("reference-reader-source-invalid")
        if self.next_after_order != (start if count and start + count < self.total else None):
            raise ValueError("reference-reader-page-invalid")
        if len(self.model_dump_json(by_alias=True).encode()) > 65536:
            raise ValueError("reference-reader-limit")
        return self


class ReferenceReaderNotice(IRValue):
    """No protected reference text; current per-copy rights still fence delivery."""

    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    source: SourceIdentity
    document_revision_id: Identity
    collection_id: Identity
    collection_revision_id: Identity
    status: Literal["unavailable"] = "unavailable"
    reason_code: Literal["viewer-resource-limit", "references-unavailable"]
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        if (
            self.project_id != self.source.project_id
            or self.document_revision_id == self.source.document_revision_id
            or self.collection_id == self.collection_revision_id
        ):
            raise ValueError("reference-reader-source-invalid")
        return self


def reader_page(
    collection: ReferenceCollection, source: SourceIdentity, *, after_order: int | None = None
) -> ReferenceReaderPage:
    if after_order is not None and (type(after_order) is not int or not 0 <= after_order < len(collection.entries)):
        raise ReferenceProblem("reference-reader-page-invalid")
    start = 0 if after_order is None else after_order + 1
    previews = []
    for entry in collection.entries[start : start + 1]:
        fields = tuple(
            ReferenceFieldPreview(
                name=field.name,
                value=field.values[0].value[:256],
                value_count=len(field.values),
                truncated=len(field.values[0].value) > 256 or len(field.values) > 1,
                knowledge_status=field.values[0].knowledge_status,
            )
            for field in entry.fields
        )
        identifiers = tuple(
            ReferenceIdentifierPreview(
                scheme=i.assertion.scheme,
                observed=i.assertion.observed[:256],
                truncated=len(i.assertion.observed) > 256,
                normalized_status=i.assertion.normalized.status,
                verification_state=i.assertion.verification_state,
                active_for_matching=i.assertion.active_for_matching,
            )
            for i in entry.identifiers[:4]
        )
        previews.append(
            ReferenceReaderEntry(
                reference_id=entry.reference_id,
                node_id=entry.node_id,
                order=entry.order,
                raw_preview=entry.raw_text[:1024],
                raw_length=len(entry.raw_text),
                raw_truncated=len(entry.raw_text) > 1024,
                fields=fields,
                identifiers=identifiers,
                identifier_count=len(entry.identifiers),
                link_state=entry.link_state,
                target=entry.target,
                candidates=entry.candidates[:4],
                candidate_count=len(entry.candidates),
                match_flags=entry.match_flags,
                anchor=entry.anchor,
                anchor_truncated=entry.anchor_truncated,
            )
        )
    return ReferenceReaderPage(
        project_id=collection.project_id,
        source=source,
        document_revision_id=collection.document_revision_id,
        collection_id=collection.collection_id,
        collection_revision_id=collection.collection_revision_id,
        content_sha256=collection.content_sha256,
        structure_sha256=collection.structure_sha256,
        total=len(collection.entries),
        after_order=after_order,
        next_after_order=start if start + 1 < len(collection.entries) else None,
        entries=tuple(previews),
    )
