"""Portable immutable structural revisions, separate from staged parser values.

These values and identity conversion confer no acceptance authority. Only the
trusted revision repository may publish after current human/source/result
authority and an optimistic canonical-head check in one transaction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .parsing.contracts import (
    ConfidenceObservation,
    Count,
    Digest,
    DocumentIR,
    Identity,
    IRFigure,
    IRTable,
    IRValue,
    NodeKind,
    ParseBinding,
    ParseQualityReport,
    ParserWarning,
    ProjectIdentity,
    RawParserArtifact,
    ReferenceIdentifier,
    SourceLocator,
    SourcePage,
    TextProjection,
    TextSpan,
    Token,
)
from .parsing.normalization import MAX_IR_BYTES

NORMALIZED_RESULT_MEDIA_TYPE: Literal["application/vnd.research-observatory.normalized-parse-result+json"] = (
    "application/vnd.research-observatory.normalized-parse-result+json"
)
ACCEPTED_REVISION_MEDIA_TYPE = "application/vnd.research-observatory.document-revision+json"
type Instant = Annotated[str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")]
type ElementRole = Literal["projection", "node", "reference", "citation"]


class DocumentRevisionProblem(ValueError):
    """Content-free failure at the protected document revision boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def protected_json(value: IRValue) -> bytes:
    """One deterministic, bounded encoding for retained protected values."""
    result = json.dumps(
        value.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8", errors="strict")
    if not 0 < len(result) <= MAX_IR_BYTES:
        raise DocumentRevisionProblem("document-revision-oversize")
    return result


class CanonicalTextProjection(TextProjection):
    projection_id: Identity


class CanonicalNode(IRValue):
    node_id: Identity
    kind: NodeKind
    order: Count
    parent_id: Identity | None
    text: TextSpan | None
    locator: SourceLocator
    confidence: ConfidenceObservation
    warnings: tuple[ParserWarning, ...]
    source_element_type: str | None = Field(repr=False)


class CanonicalReference(IRValue):
    reference_id: Identity
    node_id: Identity
    order: Count
    raw_text: TextSpan
    identifiers: tuple[ReferenceIdentifier, ...]


class CanonicalCitation(IRValue):
    citation_id: Identity
    node_id: Identity
    marker: TextSpan
    reference_candidates: tuple[Identity, ...]
    resolution: Literal["candidate", "ambiguous", "unresolved"]


class CanonicalElementIdentity(IRValue):
    role: ElementRole
    staged_id: Token = Field(repr=False)
    canonical_id: Identity


class CanonicalDocumentStructure(IRValue):
    schema_version: Literal["1.0"]
    disposition: Literal["accepted-structure"]
    binding: ParseBinding
    normalization_version: Literal["ro-text-nfc-1"]
    unicode_version: Literal["16.0.0"]
    text_projections: tuple[CanonicalTextProjection, ...] = Field(repr=False)
    pages: tuple[SourcePage, ...] = Field(max_length=500)
    nodes: tuple[CanonicalNode, ...] = Field(repr=False)
    references: tuple[CanonicalReference, ...] = Field(repr=False)
    citations: tuple[CanonicalCitation, ...] = Field(repr=False)
    tables: tuple[IRTable, ...] = Field(repr=False)
    figures: tuple[IRFigure, ...] = Field(repr=False)
    raw_artifacts: tuple[RawParserArtifact, ...]
    quality: ParseQualityReport

    @model_validator(mode="after")
    def exact_relationships(self) -> Self:
        # Reuse all proven NFC/range/geometry/order/semantic-link validators,
        # without broadening the staged IR wire contract to accepted values.
        wire = self.model_dump(mode="json", by_alias=True)
        wire["disposition"] = "staged"
        for rows, identity_key in (
            (wire["nodes"], "nodeId"),
            (wire["references"], "referenceId"),
            (wire["citations"], "citationId"),
        ):
            for row in rows:
                row["stagedId"] = row.pop(identity_key)
        DocumentIR.model_validate(wire)
        ids = [
            *(row.projection_id for row in self.text_projections),
            *(row.node_id for row in self.nodes),
            *(row.reference_id for row in self.references),
            *(row.citation_id for row in self.citations),
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("document-structural-identity-collision")
        return self


class RetainedParseResultReceipt(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    result_id: Identity
    revision_id: Identity
    binding: ParseBinding
    object_sha256: Digest
    byte_length: Annotated[int, Field(strict=True, gt=0, le=MAX_IR_BYTES)]
    media_type: Literal["application/vnd.research-observatory.normalized-parse-result+json"] = (
        NORMALIZED_RESULT_MEDIA_TYPE
    )


class DocumentRevisionAcceptance(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    result_id: Identity
    expected_current_revision_id: Identity
    confirmation_sha256: Digest
    decision: Literal["accept-structure"]


class AcceptedDocumentRevision(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    document_type: Literal["accepted-document-revision"] = "accepted-document-revision"
    project_id: ProjectIdentity
    document_id: Identity
    revision_id: Identity
    previous_revision_id: Identity
    result: RetainedParseResultReceipt
    decision_id: Identity
    decision_revision_id: Identity
    command_id: Identity
    command_sha256: Digest
    accepted_by: Identity
    accepted_actor_type: Literal["human"] = "human"
    accepted_at: Instant
    intent_revision_id: Identity
    intent_sha256: Digest
    policy_sha256: Digest
    rights_status: Literal["allowed"] = "allowed"
    scholarly_verification: Literal["unverified"] = "unverified"
    content_sha256: Digest
    structure_sha256: Digest
    element_identities: tuple[CanonicalElementIdentity, ...] = Field(repr=False)
    structure: CanonicalDocumentStructure = Field(repr=False)

    @model_validator(mode="after")
    def bound_acceptance(self) -> Self:
        datetime.fromisoformat(self.accepted_at)
        source = self.result.binding.source
        if (
            self.structure.binding != self.result.binding
            or (self.project_id, self.document_id) != (source.project_id, source.document_id)
            or self.revision_id in {self.previous_revision_id, source.document_revision_id}
            or self.content_sha256 != content_sha256(self.structure)
            or self.structure_sha256 != hashlib.sha256(protected_json(self.structure)).hexdigest()
        ):
            raise ValueError("document-revision-binding-invalid")
        roles = (
            ("projection", [row.projection_id for row in self.structure.text_projections]),
            ("node", [row.node_id for row in self.structure.nodes]),
            ("reference", [row.reference_id for row in self.structure.references]),
            ("citation", [row.citation_id for row in self.structure.citations]),
        )
        if len({(row.role, row.staged_id) for row in self.element_identities}) != len(self.element_identities):
            raise ValueError("document-element-mapping-duplicate")
        if any(
            [row.canonical_id for row in self.element_identities if row.role == role] != expected
            for role, expected in roles
        ) or len({row.canonical_id for row in self.element_identities}) != len(self.element_identities):
            raise ValueError("document-element-mapping-invalid")
        if not acceptance_eligible(self.structure):
            raise ValueError("document-structure-incomplete")
        return self


def acceptance_eligible(value: DocumentIR | CanonicalDocumentStructure) -> bool:
    """Completeness only; uncertainty is still an explicit human-review observation."""
    return (
        value.disposition in {"staged", "accepted-structure"}
        and value.binding.producer.kind != "degraded-inspection"
        and not value.quality.missing_text_pages
        and not any(
            warning.code in {"parser-partial-output", "missing-text-ocr-disabled"}
            for warning in (*value.quality.warnings, *(warning for node in value.nodes for warning in node.warnings))
        )
        and any(projection.normalized_text.strip() for projection in value.text_projections)
    )


def content_sha256(structure: CanonicalDocumentStructure) -> str:
    content = [
        projection.model_dump(mode="json", by_alias=True, exclude={"projection_id"})
        for projection in structure.text_projections
    ]
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def canonicalize_structure(
    ir: DocumentIR,
    *,
    identity_factory: Callable[[], str] = new_uuid_v7,
) -> tuple[CanonicalDocumentStructure, tuple[CanonicalElementIdentity, ...]]:
    """Mint detached Core IDs; never publish, accept or alter a document head."""
    validated = None
    with suppress(ValueError, TypeError):
        validated = DocumentIR.model_validate(ir)
    if validated is None or not acceptance_eligible(validated):
        raise DocumentRevisionProblem("document-structure-incomplete")
    wire = validated.model_dump(mode="json", by_alias=True)
    mapping: list[CanonicalElementIdentity] = []
    ids: set[str] = set()
    lookup: dict[tuple[str, str], str] = {}
    roles: tuple[tuple[ElementRole, list[str]], ...] = (
        ("projection", [row.projection_id for row in validated.text_projections]),
        ("node", [row.staged_id for row in validated.nodes]),
        ("reference", [row.staged_id for row in validated.references]),
        ("citation", [row.staged_id for row in validated.citations]),
    )
    for role, names in roles:
        for name in names:
            identity = identity_factory()
            if not is_uuid_v7(identity) or identity in ids:
                raise DocumentRevisionProblem("document-structural-identity-invalid")
            ids.add(identity)
            lookup[role, name] = identity
            mapping.append(CanonicalElementIdentity(role=role, staged_id=name, canonical_id=identity))

    def span(row):
        if row is not None:
            row["projectionId"] = lookup["projection", row["projectionId"]]

    def warning(row):
        if row["nodeId"] is not None:
            row["nodeId"] = lookup["node", row["nodeId"]]

    def locator(row):
        if row["kind"] == "text":
            span(row)

    for projection in wire["textProjections"]:
        projection["projectionId"] = lookup["projection", projection["projectionId"]]
    for node in wire["nodes"]:
        node["nodeId"] = lookup["node", node.pop("stagedId")]
        if node["parentId"] is not None:
            node["parentId"] = lookup["node", node["parentId"]]
        span(node["text"])
        locator(node["locator"])
        for item in node["warnings"]:
            warning(item)
    for reference in wire["references"]:
        reference["referenceId"] = lookup["reference", reference.pop("stagedId")]
        reference["nodeId"] = lookup["node", reference["nodeId"]]
        span(reference["rawText"])
    for citation in wire["citations"]:
        citation["citationId"] = lookup["citation", citation.pop("stagedId")]
        citation["nodeId"] = lookup["node", citation["nodeId"]]
        citation["referenceCandidates"] = [lookup["reference", name] for name in citation["referenceCandidates"]]
        span(citation["marker"])
    for table in wire["tables"]:
        table["nodeId"] = lookup["node", table["nodeId"]]
        for cell in table["cells"]:
            cell["nodeId"] = lookup["node", cell["nodeId"]]
            span(cell["rawText"])
    for figure in wire["figures"]:
        figure["nodeId"] = lookup["node", figure["nodeId"]]
        span(figure["caption"])
        locator(figure["locator"])
    for item in wire["quality"]["tableCellConfidence"]:
        item["nodeId"] = lookup["node", item["nodeId"]]
    for item in wire["quality"]["warnings"]:
        warning(item)
    wire["disposition"] = "accepted-structure"
    return CanonicalDocumentStructure.model_validate(wire), tuple(mapping)
