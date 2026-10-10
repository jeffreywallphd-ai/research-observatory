"""Protected reference values and source-grounded extraction; no I/O or authority.

Publication, current rights, canonical Work matching and dependency registration
belong to the trusted adapters. Extraction never mutates accepted structure v1.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from .anchors.contracts import MAX_QUOTE_CODEPOINTS, AnchorSelection, SourceAnchorTarget, build_target
from .document_revisions import AcceptedDocumentRevision, Instant
from .parsing.contracts import CodepointRange, Digest, Identity, IRValue, ProjectIdentity, TextSpan
from .parsing.native_contracts import NATIVE_MEDIA_TYPE, NativeStructure
from .parsing.normalization import normalize_text
from .reconciliation.candidates import (
    DEFAULT_CONFIG,
    CandidateRecord,
    compare_records,
    prepare_record,
)
from .reconciliation.contracts import CanonicalWorkReference
from .reconciliation.exact import IdentifierAssertion, MatchAssessment
from .reconciliation.identifiers import NORMALIZER_VERSION

REFERENCE_MEDIA_TYPE = "application/vnd.research-observatory.document-references+json"
REFERENCE_EXTRACTION_VERSION: Final = "document-references/1.0.0"
MAX_REFERENCE_BYTES = 16 * 1024 * 1024
MAX_REFERENCES = 1000
MAX_REFERENCE_CODEPOINTS = 65536
MAX_REFERENCE_FIELDS = 256
MAX_REFERENCE_SECONDS = 5.0
type ReferenceFieldName = Literal["title", "authors", "year", "venue"]


class ReferenceProblem(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ReferenceFieldValue(IRValue):
    value: Annotated[str, Field(min_length=1, max_length=65536)] = Field(repr=False)
    source_span: TextSpan = Field(repr=False)
    knowledge_status: Literal["extracted", "inferred"]
    basis: Literal["source-element", "native-reported-author-role", "author-year-title-pattern"]
    native_artifact_sha256: Digest | None = None
    native_element_index: Annotated[int, Field(strict=True, ge=0, lt=1000000)] | None = None

    @model_validator(mode="after")
    def role_evidence(self):
        if (self.native_artifact_sha256 is None) != (self.native_element_index is None):
            raise ValueError("reference-field-evidence-invalid")
        if self.basis == "native-reported-author-role" and self.native_artifact_sha256 is None:
            raise ValueError("reference-field-evidence-invalid")
        if (self.basis == "author-year-title-pattern") != (self.knowledge_status == "inferred"):
            raise ValueError("reference-field-state-invalid")
        return self


class ReferenceFieldAssertion(IRValue):
    name: ReferenceFieldName
    values: tuple[ReferenceFieldValue, ...] = Field(min_length=1, max_length=256, repr=False)


class ReferenceIdentifierAssertion(IRValue):
    assertion: IdentifierAssertion = Field(repr=False)
    source_spans: tuple[TextSpan, ...] = Field(max_length=128, repr=False)

    @model_validator(mode="after")
    def source_support(self):
        if not self.source_spans and self.assertion.active_for_matching:
            raise ValueError("reference-identifier-source-missing")
        return self


class ReferenceFeature(IRValue):
    name: Annotated[str, Field(min_length=1, max_length=64)]
    state: Literal["available", "not-reported", "disputed"]
    score: Annotated[int, Field(strict=True, ge=0, le=10000)] | None
    weight: Annotated[int, Field(strict=True, ge=0, le=10000)]
    conflict: bool


class ReferenceMatchCandidate(IRValue):
    target: CanonicalWorkReference
    score: Annotated[int, Field(strict=True, ge=0, le=10000)]
    features: tuple[ReferenceFeature, ...] = Field(max_length=7)
    flags: tuple[str, ...] = Field(max_length=32)
    review_state: Literal["human-review-required"] = "human-review-required"
    algorithm: Literal["scholarly-duplicate-ranking/1.0.0"] = "scholarly-duplicate-ranking/1.0.0"
    feature_version: Literal["scholarly-duplicate-features/1.0.0"] = "scholarly-duplicate-features/1.0.0"
    configuration_sha256: Digest = DEFAULT_CONFIG.fingerprint


class ReferenceEntry(IRValue):
    reference_id: Identity
    node_id: Identity
    order: Annotated[int, Field(strict=True, ge=0, lt=1000)]
    raw_text_span: TextSpan = Field(repr=False)
    raw_text: Annotated[str, Field(max_length=65536)] = Field(repr=False)
    normalized_text: Annotated[str, Field(max_length=65536)] = Field(repr=False)
    fields: tuple[ReferenceFieldAssertion, ...] = Field(max_length=4, repr=False)
    identifiers: tuple[ReferenceIdentifierAssertion, ...] = Field(max_length=128, repr=False)
    anchor: SourceAnchorTarget | None = Field(repr=False)
    anchor_truncated: bool
    link_state: Literal["exact-linked", "candidate", "ambiguous", "unresolved", "non-scholarly", "rejected"] = (
        "unresolved"
    )
    target: CanonicalWorkReference | None = None
    candidates: tuple[ReferenceMatchCandidate, ...] = Field(default=(), max_length=256, repr=False)
    match_flags: tuple[str, ...] = Field(default=(), max_length=32)
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def state_and_source(self):
        if (self.link_state == "exact-linked") != (self.target is not None):
            raise ValueError("reference-target-state-invalid")
        if self.link_state == "exact-linked" and (self.match_flags or self.candidates):
            raise ValueError("reference-exact-state-invalid")
        if len({item.name for item in self.fields}) != len(self.fields):
            raise ValueError("reference-field-duplicate")
        if self.anchor is not None and self.anchor.node_id != self.node_id:
            raise ValueError("reference-anchor-identity-invalid")
        return self


class ReferenceEnrichmentCommand(IRValue):
    command_id: Identity
    revision_id: Identity
    expected_collection_revision_id: Identity | None


class ReferenceCollection(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    collection_id: Identity
    collection_revision_id: Identity
    previous_collection_revision_id: Identity | None
    document_revision_id: Identity
    content_sha256: Digest
    structure_sha256: Digest
    command_id: Identity
    command_sha256: Digest
    actor_id: Identity
    intent_sha256: Digest
    policy_sha256: Digest
    extracted_at: Instant
    extraction_version: Literal["document-references/1.0.0"] = REFERENCE_EXTRACTION_VERSION
    identifier_normalizer: Literal["scholarly-identifiers/1.0.0"] = NORMALIZER_VERSION
    ranking_configuration_sha256: Digest = DEFAULT_CONFIG.fingerprint
    catalog_sha256: Digest
    entries: tuple[ReferenceEntry, ...] = Field(max_length=1000, repr=False)
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def complete_order_and_binding(self):
        if len({item.reference_id for item in self.entries}) != len(self.entries):
            raise ValueError("reference-collection-identity-invalid")
        for order, item in enumerate(self.entries):
            if item.order != order or (
                item.anchor is not None
                and (
                    item.anchor.project_id != self.project_id
                    or item.anchor.revision_id != self.document_revision_id
                    or item.anchor.content_sha256 != self.content_sha256
                    or item.anchor.structure_sha256 != self.structure_sha256
                )
            ):
                raise ValueError("reference-collection-source-invalid")
        if len(self.model_dump_json(by_alias=True).encode()) > MAX_REFERENCE_BYTES:
            raise ValueError("reference-collection-limit")
        return self


def _name(value: str | None) -> tuple[str, str]:
    if value and value.startswith("{") and "}" in value:
        namespace, local = value[1:].split("}", 1)
        return namespace, local
    return "", value or ""


def _span(projection, start: int, end: int, *, normalized=None) -> TextSpan:
    normalized = normalized or normalize_text(projection.raw_text)
    return TextSpan(
        projection_id=projection.projection_id,
        normalized_range=CodepointRange(start=start, end=end),
        raw_ranges=tuple(
            CodepointRange(start=left, end=right) for left, right in normalized.raw_ranges_for(start, end)
        ),
    )


def _raw(projection, span: TextSpan) -> str:
    # Original source order, not NFC contributor order; never duplicate overlap.
    merged: list[tuple[int, int]] = []
    for start, end in sorted((part.start, part.end) for part in span.raw_ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return "".join(projection.raw_text[start:end] for start, end in merged)


def extract_references(
    accepted: AcceptedDocumentRevision,
    *,
    native_artifact: bytes | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[ReferenceEntry, ...]:
    """Derive values only. Caller authenticates the source and any retained bytes."""
    deadline = time.monotonic() + MAX_REFERENCE_SECONDS

    def checkpoint():
        if cancelled():
            raise ReferenceProblem("reference-operation-cancelled")
        if time.monotonic() > deadline:
            raise ReferenceProblem("reference-operation-limit")

    checkpoint()
    structure = accepted.structure
    if len(structure.references) > MAX_REFERENCES:
        raise ReferenceProblem("reference-operation-limit")
    projections = {item.projection_id: item for item in structure.text_projections}
    nodes = {item.node_id: item for item in structure.nodes}
    native = None
    native_sha = None
    if native_artifact is not None:
        native_sha = hashlib.sha256(native_artifact).hexdigest()
        if len(native_artifact) > MAX_REFERENCE_BYTES or not any(
            item.media_type == NATIVE_MEDIA_TYPE
            and item.object_sha256 == native_sha
            and item.byte_length == len(native_artifact)
            for item in structure.raw_artifacts
        ):
            raise ReferenceProblem("reference-native-binding-invalid")
        native = NativeStructure.model_validate_json(native_artifact)
        if (
            (native.source_sha256, native.source_byte_length, native.format)
            != (
                structure.binding.source.object_sha256,
                structure.binding.source.byte_length,
                structure.binding.source.format,
            )
            or len(native.elements) != len(structure.nodes)
            or any(
                element.name != node.source_element_type
                or element.index != node.order
                or node.text is None
                or projections[node.text.projection_id].raw_text != native.text[element.text_start : element.text_end]
                or (
                    node.kind != "table-cell"
                    and element.parent_index != (nodes[node.parent_id].order if node.parent_id else None)
                )
                for element, node in zip(native.elements, structure.nodes, strict=True)
            )
            or not any(item.raw_text == native.text for item in projections.values())
        ):
            raise ReferenceProblem("reference-native-binding-invalid")
    reference_nodes = {item.node_id for item in structure.references}
    owners: dict[str, str | None] = {}
    descendants: dict[str, list] = {identity: [] for identity in reference_nodes}
    for node in structure.nodes:
        checkpoint()
        owner = (
            node.node_id if node.node_id in reference_nodes else owners.get(node.parent_id) if node.parent_id else None
        )
        owners[node.node_id] = owner
        if owner is not None and node.node_id != owner:
            descendants[owner].append(node)
    entries = []
    total_bytes = 0
    for reference in structure.references:
        checkpoint()
        projection = projections[reference.raw_text.projection_id]
        mapped = None
        start, end = reference.raw_text.normalized_range.start, reference.raw_text.normalized_range.end
        observed, normalized = _raw(projection, reference.raw_text), projection.normalized_text[start:end]
        total_bytes += len(observed.encode()) + len(normalized.encode())
        if max(len(observed), len(normalized)) > MAX_REFERENCE_CODEPOINTS or total_bytes > MAX_REFERENCE_BYTES:
            raise ReferenceProblem("reference-operation-limit")
        grouped: dict[ReferenceFieldName, list[ReferenceFieldValue]] = {}
        format = structure.binding.source.format
        allowed = {"jats": {"", "http://jats.nlm.nih.gov"}, "tei": {"", "http://www.tei-c.org/ns/1.0"}}.get(
            format, set()
        )
        for child in descendants[reference.node_id]:
            checkpoint()
            namespace, local = _name(child.source_element_type)
            if namespace not in allowed or child.text is None:
                continue
            parent_names = []
            parent = child.parent_id
            while parent is not None and parent != reference.node_id:
                parent_names.append((parent, _name(nodes[parent].source_element_type)))
                parent = nodes[parent].parent_id
            name: ReferenceFieldName | None = None
            role_parent = None
            if format == "jats":
                jats_fields: dict[str, ReferenceFieldName] = {
                    "article-title": "title",
                    "year": "year",
                    "source": "venue",
                }
                name = jats_fields.get(local)
                if local == "name" and native is not None:
                    groups = [
                        identity
                        for identity, (ns, element) in parent_names
                        if ns in allowed and element == "person-group"
                    ]
                    if groups:
                        element = native.elements[nodes[groups[0]].order]
                        roles = [attr.value for attr in element.attributes if attr.name == "person-group-type"]
                        if roles == ["author"]:
                            name, role_parent = "authors", element.index
            elif format == "tei":
                ancestry = {element for _, (ns, element) in parent_names if ns in allowed}
                if local == "title":
                    name = "title" if "analytic" in ancestry else "venue" if "monogr" in ancestry else None
                elif local == "persName" and "author" in ancestry:
                    name = "authors"
                elif local == "date":
                    name = "year"
            child_projection = projections[child.text.projection_id]
            text = child_projection.normalized_text[
                child.text.normalized_range.start : child.text.normalized_range.end
            ].strip()
            if name is None or not text or (name == "year" and re.fullmatch(r"[0-9]{4}", text) is None):
                continue
            grouped.setdefault(name, []).append(
                ReferenceFieldValue(
                    value=text,
                    source_span=child.text,
                    knowledge_status="extracted",
                    basis="source-element" if role_parent is None else "native-reported-author-role",
                    native_artifact_sha256=native_sha if role_parent is not None else None,
                    native_element_index=role_parent,
                )
            )
        if not grouped:
            pattern = re.match(
                r"(?P<authors>[^\n]{1,512}?)\s+\((?P<year>[0-9]{4})[a-z]?\)\.\s+(?P<title>[^\n]{1,4096}?)\.(?:\s|$)",
                normalized,
            )
            if pattern:
                mapped = normalize_text(projection.raw_text)
                inferred_names: tuple[ReferenceFieldName, ...] = ("authors", "year", "title")
                for name in inferred_names:
                    grouped[name] = [
                        ReferenceFieldValue(
                            value=pattern.group(name).strip(),
                            source_span=_span(
                                projection, start + pattern.start(name), start + pattern.end(name), normalized=mapped
                            ),
                            knowledge_status="inferred",
                            basis="author-year-title-pattern",
                        )
                    ]
        if sum(len(values) for values in grouped.values()) > MAX_REFERENCE_FIELDS:
            raise ReferenceProblem("reference-operation-limit")
        identifiers = []
        if len(reference.identifiers) > 128:
            raise ReferenceProblem("reference-operation-limit")
        observed_identifiers = [(item.scheme, item.observed) for item in reference.identifiers]
        # Explicit DOI wrappers only; preserve punctuation instead of guessing
        # whether a terminal character belongs to an identifier or a sentence.
        if not reference.identifiers:
            for explicit in re.finditer(
                r"(?i)(?:\bdoi:\s*(10\.[0-9][^\s]*)|\bhttps?://(?:dx\.)?doi\.org/[^\s]+)", normalized
            ):
                if len(observed_identifiers) >= 128:
                    raise ReferenceProblem("reference-operation-limit")
                observed_identifiers.append(("doi", explicit.group(1) or explicit.group(0)))
        for scheme, observed_identifier in observed_identifiers:
            checkpoint()
            needle = normalize_text(observed_identifier).normalized_text
            spans: list[TextSpan] = []
            position = start
            while needle and (position := projection.normalized_text.find(needle, position, end)) >= 0:
                if len(spans) >= 128:
                    raise ReferenceProblem("reference-operation-limit")
                mapped = mapped or normalize_text(projection.raw_text)
                spans.append(_span(projection, position, position + len(needle), normalized=mapped))
                position += len(needle)
            identifiers.append(
                ReferenceIdentifierAssertion(
                    assertion=IdentifierAssertion(
                        scheme=scheme,
                        observed=observed_identifier,
                        active_for_matching=bool(spans),
                        source_selector=reference.reference_id,
                    ),
                    source_spans=tuple(spans),
                )
            )
        anchor = (
            build_target(
                accepted,
                AnchorSelection(
                    revision_id=accepted.revision_id,
                    node_id=reference.node_id,
                    normalized_range=CodepointRange(start=start, end=min(end, start + MAX_QUOTE_CODEPOINTS)),
                ),
            )
            if start < end
            else None
        )
        entries.append(
            ReferenceEntry(
                reference_id=reference.reference_id,
                node_id=reference.node_id,
                order=reference.order,
                raw_text_span=reference.raw_text,
                raw_text=observed,
                normalized_text=normalized,
                fields=tuple(
                    ReferenceFieldAssertion(name=name, values=tuple(values)) for name, values in sorted(grouped.items())
                ),
                identifiers=tuple(identifiers),
                anchor=anchor,
                anchor_truncated=end - start > MAX_QUOTE_CODEPOINTS,
            )
        )
    checkpoint()
    return tuple(entries)


@dataclass(frozen=True, slots=True)
class ReferenceWorkSnapshot:
    """Detached candidate values; their presence is never current authority."""

    target: CanonicalWorkReference
    record: CandidateRecord


def match_reference_entries(
    entries: tuple[ReferenceEntry, ...],
    catalog: tuple[ReferenceWorkSnapshot, ...],
    assessments: tuple[MatchAssessment, ...],
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[ReferenceEntry, ...]:
    """Reuse exact decisions and transparent ranking; never create/merge Works."""
    deadline = time.monotonic() + MAX_REFERENCE_SECONDS

    def checkpoint():
        if cancelled():
            raise ReferenceProblem("reference-operation-cancelled")
        if time.monotonic() > deadline:
            raise ReferenceProblem("reference-operation-limit")

    checkpoint()
    if len(entries) != len(assessments) or len(entries) > MAX_REFERENCES or len(catalog) > DEFAULT_CONFIG.max_records:
        raise ReferenceProblem("reference-match-snapshot-invalid")
    targets = {work.target.work_id: work for work in catalog}
    if (
        len(targets) != len(catalog)
        or any(
            (work.record.key, work.record.revision) != (work.target.work_id, work.target.revision_id)
            for work in catalog
        )
        or any(
            not set(assessment.candidates).issubset(targets)
            or (assessment.target is not None and assessment.target not in targets)
            for assessment in assessments
        )
    ):
        raise ReferenceProblem("reference-match-snapshot-invalid")
    prepared = {}
    for work in catalog:
        checkpoint()
        prepared[work.target.work_id] = prepare_record(work.record)
    matched = []
    comparisons = 0
    total_candidates = 0
    for entry, assessment in zip(entries, assessments, strict=True):
        checkpoint()
        flags: set[str] = set(assessment.flags)
        if any(not identifier.source_spans for identifier in entry.identifiers):
            flags.add("unanchored-identifier")
        if assessment.disposition == "exact-linked" and assessment.target is not None and not flags:
            update = {
                "link_state": "exact-linked",
                "target": targets[assessment.target].target,
                "candidates": (),
                "match_flags": (),
            }
        else:
            record = prepare_record(
                CandidateRecord(
                    entry.reference_id,
                    entry.anchor.revision_id if entry.anchor else entry.node_id,
                    tuple((field.name, tuple(value.value for value in field.values)) for field in entry.fields),
                    tuple(identifier.assertion for identifier in entry.identifiers),
                )
            )
            proposals = []
            # Only reference→Work pairs, not quadratic unrelated Work→Work pairs.
            if entry.fields or entry.identifiers:
                for work in catalog:
                    checkpoint()
                    comparisons += 1
                    if comparisons > DEFAULT_CONFIG.max_comparisons:
                        raise ReferenceProblem("reference-operation-limit")
                    pair = compare_records(record, prepared[work.target.work_id])
                    if pair.score >= DEFAULT_CONFIG.minimum_score or work.target.work_id in assessment.candidates:
                        proposals.append(
                            ReferenceMatchCandidate(
                                target=work.target,
                                score=pair.score,
                                features=tuple(ReferenceFeature(**asdict(feature)) for feature in pair.features),
                                flags=tuple(sorted(set(pair.flags) | flags)),
                                configuration_sha256=pair.configuration_fingerprint,
                            )
                        )
                        if len(proposals) > 256:
                            raise ReferenceProblem("reference-operation-limit")
            total_candidates += len(proposals)
            if total_candidates > DEFAULT_CONFIG.max_candidates:
                raise ReferenceProblem("reference-operation-limit")
            proposals.sort(key=lambda candidate: (-candidate.score, candidate.target.work_id))
            update = {
                "target": None,
                "candidates": tuple(proposals),
                "match_flags": tuple(sorted(flags)),
                "link_state": "ambiguous" if len(proposals) > 1 else "candidate" if proposals else "unresolved",
            }
        # model_copy does not validate updates; validate the complete final value.
        matched.append(ReferenceEntry.model_validate(entry.model_dump() | update))
    checkpoint()
    return tuple(matched)
