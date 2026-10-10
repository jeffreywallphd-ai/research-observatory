"""Bounded source-grounded citation values. No I/O, Work merge or verification.

Reported native links and inferred patterns are separate observations. Neither
the position of a reference nor a superscript alone supplies a target identity.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .anchors.contracts import MAX_QUOTE_CODEPOINTS, AnchorSelection, SourceAnchorTarget, build_target
from .document_references import ReferenceEntry, _name, _raw, _span, extract_references
from .document_revisions import AcceptedDocumentRevision, CanonicalNode, Instant
from .parsing.contracts import (
    CodepointRange,
    ConfidenceObservation,
    Digest,
    Identity,
    IRValue,
    ProjectIdentity,
    TextSpan,
)
from .parsing.native_contracts import NativeStructure
from .parsing.normalization import _merge_ranges, normalize_text

CITATION_MEDIA_TYPE = "application/vnd.research-observatory.document-citations+json"
CITATION_EXTRACTION_VERSION: Literal["document-citations/1.0.0"] = "document-citations/1.0.0"
MAX_CITATION_BYTES = 16 * 1024 * 1024
MAX_CITATIONS = 1000
MAX_TARGETS = 128
MAX_CONTEXT_CODEPOINTS = 65536
MAX_CITATION_SECONDS = 5.0
type Resolution = Literal["candidate", "ambiguous", "unresolved"]
type ContextReason = Literal["available", "not-reported", "normalization-boundary", "empty-marker"]


class CitationProblem(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class CitationTargetGroup(IRValue):
    label: Annotated[str, Field(strict=True, min_length=1, max_length=512)] = Field(repr=False)
    reference_ids: tuple[Identity, ...] = Field(max_length=1000)
    resolution: Resolution

    @model_validator(mode="after")
    def target_state(self):
        state = "unresolved" if not self.reference_ids else "candidate" if len(self.reference_ids) == 1 else "ambiguous"
        if state != self.resolution or len(set(self.reference_ids)) != len(self.reference_ids):
            raise ValueError("citation-target-state-invalid")
        return self


class CitationTextContext(IRValue):
    node_id: Identity
    text_span: TextSpan = Field(repr=False)
    raw_text: Annotated[str, Field(strict=True, max_length=MAX_CONTEXT_CODEPOINTS)] = Field(repr=False)
    normalized_text: Annotated[str, Field(strict=True, max_length=MAX_CONTEXT_CODEPOINTS)] = Field(repr=False)
    marker_range: CodepointRange | None
    basis: Literal["source-element", "sentence-pattern"]

    @model_validator(mode="after")
    def exact_context(self):
        span = self.text_span.normalized_range
        if len(self.normalized_text) != span.end - span.start or (
            self.marker_range is not None
            and not span.start <= self.marker_range.start < self.marker_range.end <= span.end
        ):
            raise ValueError("citation-context-range-invalid")
        return self


class CitationContext(IRValue):
    order: Annotated[int, Field(strict=True, ge=0, lt=MAX_CITATIONS)]
    canonical_citation_id: Identity | None
    canonical_order: Annotated[int, Field(strict=True, ge=0, lt=1000)] | None
    node_id: Identity
    marker_span: TextSpan = Field(repr=False)
    raw_marker: Annotated[str, Field(strict=True, max_length=65536)] = Field(repr=False)
    normalized_marker: Annotated[str, Field(strict=True, max_length=65536)] = Field(repr=False)
    style: Literal["reported", "numeric", "author-year", "narrative", "superscript"]
    knowledge_status: Literal["extracted", "inferred"]
    targets: tuple[CitationTargetGroup, ...] = Field(max_length=MAX_TARGETS, repr=False)
    resolution: Resolution
    anchor: SourceAnchorTarget | None = Field(repr=False)
    anchor_truncated: bool
    paragraph: CitationTextContext | None = Field(repr=False)
    sentence: CitationTextContext | None = Field(repr=False)
    context_reason: ContextReason
    confidence: ConfidenceObservation
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def source_and_state(self):
        state = _resolution(self.targets)
        if state != self.resolution or (self.anchor is not None and self.anchor.node_id != self.node_id):
            raise ValueError("citation-context-binding-invalid")
        if (self.knowledge_status == "extracted") != (self.canonical_citation_id is not None):
            raise ValueError("citation-reported-identity-missing")
        if (self.canonical_citation_id is None) != (self.canonical_order is None):
            raise ValueError("citation-reported-identity-missing")
        return self


class CitationEnrichmentCommand(IRValue):
    command_id: Identity
    revision_id: Identity
    reference_collection_revision_id: Identity
    expected_collection_revision_id: Identity | None


class CitationCollection(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    collection_id: Identity
    collection_revision_id: Identity
    previous_collection_revision_id: Identity | None
    document_revision_id: Identity
    content_sha256: Digest
    structure_sha256: Digest
    reference_collection_id: Identity
    reference_collection_revision_id: Identity
    reference_payload_sha256: Digest
    command_id: Identity
    command_sha256: Digest
    actor_id: Identity
    intent_sha256: Digest
    policy_sha256: Digest
    extracted_at: Instant
    extraction_version: Literal["document-citations/1.0.0"] = CITATION_EXTRACTION_VERSION
    entries: tuple[CitationContext, ...] = Field(max_length=MAX_CITATIONS, repr=False)
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def collection_binding(self):
        identities = [e.canonical_citation_id for e in self.entries if e.canonical_citation_id]
        if len(identities) != len(set(identities)):
            raise ValueError("citation-collection-identity-invalid")
        for order, entry in enumerate(self.entries):
            if entry.order != order or (
                entry.anchor is not None
                and (
                    entry.anchor.project_id,
                    entry.anchor.revision_id,
                    entry.anchor.content_sha256,
                    entry.anchor.structure_sha256,
                )
                != (self.project_id, self.document_revision_id, self.content_sha256, self.structure_sha256)
            ):
                raise ValueError("citation-collection-source-invalid")
        if len(self.model_dump_json(by_alias=True).encode()) > MAX_CITATION_BYTES:
            raise ValueError("citation-collection-limit")
        return self


def _resolution(groups):
    if not groups or any(g.resolution == "unresolved" for g in groups):
        return "unresolved"
    return "ambiguous" if any(g.resolution == "ambiguous" for g in groups) else "candidate"


def _group(label, identities):
    unique = tuple(dict.fromkeys(identities))
    return CitationTargetGroup(
        label=label,
        reference_ids=unique,
        resolution="unresolved" if not unique else "candidate" if len(unique) == 1 else "ambiguous",
    )


def _raw_to_normalized(mapping, start, end):
    """Require the exact raw contributors; cross-element composition is unknown."""
    found = []
    for run in mapping.mappings:
        if run.kind == "identity":
            base = run.raw_ranges[0][0] - run.normalized_start
            left, right = max(start - base, run.normalized_start), min(end - base, run.normalized_end)
            if left < right:
                found.append((left, right))
        elif any(left < end and right > start for left, right in run.raw_ranges):
            found.append((run.normalized_start, run.normalized_end))
    if not found:
        return None
    left, right = min(p[0] for p in found), max(p[1] for p in found)
    return CodepointRange(start=left, end=right) if mapping.raw_ranges_for(left, right) == ((start, end),) else None


def extract_citation_contexts(
    accepted: AcceptedDocumentRevision,
    references: tuple[ReferenceEntry, ...],
    *,
    native_artifact: bytes | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[CitationContext, ...]:
    deadline = time.monotonic() + MAX_CITATION_SECONDS

    def checkpoint():
        if cancelled():
            raise CitationProblem("citation-operation-cancelled")
        if time.monotonic() > deadline:
            raise CitationProblem("citation-operation-limit")

    checkpoint()
    # Authenticate retained native source relationships with the same boundary
    # as reference extraction; use independently extracted source fields below.
    trusted = extract_references(accepted, native_artifact=native_artifact, cancelled=cancelled)
    if [(r.reference_id, r.node_id, r.raw_text_span, r.raw_text, r.fields) for r in trusted] != [
        (r.reference_id, r.node_id, r.raw_text_span, r.raw_text, r.fields) for r in references
    ]:
        raise CitationProblem("citation-reference-source-invalid")
    native = NativeStructure.model_validate_json(native_artifact) if native_artifact is not None else None
    structure = accepted.structure
    nodes = {n.node_id: n for n in structure.nodes}
    projections = {p.projection_id: p for p in structure.text_projections}
    reference_nodes = {r.node_id for r in trusted}
    children: dict[str | None, list[CanonicalNode]] = {}
    reported_projections: dict[str, set[str]] = {}
    for node in structure.nodes:
        children.setdefault(node.parent_id, []).append(node)
    for citation in structure.citations:
        ancestor: str | None = citation.node_id
        while ancestor is not None:
            reported_projections.setdefault(ancestor, set()).add(citation.marker.projection_id)
            ancestor = nodes[ancestor].parent_id
    owners: dict[str, str | None] = {}
    descendants: dict[str, list[CanonicalNode]] = {r.node_id: [] for r in trusted}
    for n in structure.nodes:
        checkpoint()
        owner = n.node_id if n.node_id in reference_nodes else owners.get(n.parent_id) if n.parent_id else None
        owners[n.node_id] = owner
        if owner is not None and n.node_id != owner:
            descendants[owner].append(n)
    # Flattened containing text must not turn a known nonbibliographic link or
    # an unreported superscript into a bibliography ordinal. Canonical bibl
    # markers (and their nested superscripts) retain their reported role.
    canonical_nodes = {c.node_id for c in structure.citations}
    callout_spans: list[tuple[str, TextSpan]] = []
    callout_raw: list[tuple[int, int]] = []
    for node in structure.nodes:
        if node.text is None or owners[node.node_id] is not None:
            continue
        _, name = _name(node.source_element_type)
        if name not in {"sup", "xref", "ref", "ptr", "a"}:
            continue
        callout_ancestor: str | None = node.node_id
        reported_role = False
        while callout_ancestor is not None:
            if callout_ancestor in canonical_nodes:
                reported_role = True
                break
            callout_ancestor = nodes[callout_ancestor].parent_id
        if reported_role:
            continue
        callout_spans.append((node.node_id, node.text))
        if native is not None:
            element = native.elements[node.order]
            callout_raw.append((element.text_start, element.text_end))
        else:
            callout_ancestor = node.parent_id
            while callout_ancestor is not None:
                reported_projections.setdefault(callout_ancestor, set()).add(node.text.projection_id)
                callout_ancestor = nodes[callout_ancestor].parent_id
    allowed = {
        "jats": {"", "http://jats.nlm.nih.gov"},
        "tei": {"", "http://www.tei-c.org/ns/1.0"},
        "html": {"", "http://www.w3.org/1999/xhtml"},
    }.get(structure.binding.source.format, set())
    ids: dict[str, list[str]] = {}
    labels: dict[str, list[str]] = {}
    authors: dict[tuple[str, str], list[str]] = {}

    def add(index, key, identity):
        if key:
            index.setdefault(key, []).append(identity)

    for ref in trusted:
        checkpoint()
        ref_node = nodes[ref.node_id]
        if native is not None:
            element = native.elements[ref_node.order]
            for attr in element.attributes:
                if (
                    attr.name in {"id", "{http://www.w3.org/XML/1998/namespace}id"}
                    and sum(a.name == attr.name for a in element.attributes) == 1
                ):
                    add(ids, attr.value, ref.reference_id)
        reported_labels = []
        family_names = []
        for n in descendants[ref.node_id]:
            ns, name = _name(n.source_element_type)
            if ns not in allowed or n.text is None:
                continue
            projection = projections[n.text.projection_id]
            value = projection.normalized_text[n.text.normalized_range.start : n.text.normalized_range.end].strip()
            if name == "label":
                reported_labels.append(value)
            if name == "surname" and native is not None:
                ancestor = n.parent_id
                while ancestor is not None and ancestor != ref.node_id:
                    parent = nodes[ancestor]
                    parent_ns, parent_name = _name(parent.source_element_type)
                    attributes = native.elements[parent.order].attributes
                    author_role = parent_ns in allowed and (
                        (native.format == "tei" and parent_name == "author")
                        or (
                            native.format == "jats"
                            and parent_name == "person-group"
                            and [a.value for a in attributes if a.name == "person-group-type"] == ["author"]
                        )
                    )
                    if author_role:
                        family_names.append(value)
                        break
                    ancestor = parent.parent_id
        if not reported_labels:
            prefix = re.match(r"^\s*(?:\[([0-9]{1,6})\]|([0-9]{1,6})[.)])\s+", ref.normalized_text)
            if prefix:
                reported_labels.append(prefix.group(1) or prefix.group(2))
        for label in reported_labels:
            if re.fullmatch(r"[0-9]{1,6}", label):
                add(labels, str(int(label)), ref.reference_id)
        years = [v.value for f in ref.fields if f.name == "year" for v in f.values]
        if not family_names:
            # Only complete reported/inferred author values, not a surname
            # guessed by trimming concatenated structured names.
            family_names = [v.value for f in ref.fields if f.name == "authors" for v in f.values]
        for author in family_names:
            for year in years:
                add(authors, (author.casefold(), year), ref.reference_id)

    mappings = {}
    projection_order: dict[str, int] = {}
    for node in structure.nodes:
        if node.text is not None:
            projection_order.setdefault(node.text.projection_id, node.order)

    def mapping(projection):
        if projection.projection_id not in mappings:
            mappings[projection.projection_id] = normalize_text(projection.raw_text, cancelled=cancelled)
        return mappings[projection.projection_id]

    def text_context(node, span, marker_range, basis):
        p = projections[span.projection_id]
        start, end = span.normalized_range.start, span.normalized_range.end
        raw, normalized = _raw(p, span), p.normalized_text[start:end]
        if max(len(raw), len(normalized)) > MAX_CONTEXT_CODEPOINTS:
            raise CitationProblem("citation-operation-limit")
        return CitationTextContext(
            node_id=node.node_id,
            text_span=span,
            raw_text=raw,
            normalized_text=normalized,
            marker_range=marker_range,
            basis=basis,
        )

    entries: list[tuple[tuple[int, ...], CitationContext]] = []
    occupied: list[tuple[int, int]] = []
    total_bytes = 0

    def emit(node, span, style, groups, canonical_id=None, canonical_order=None):
        nonlocal total_bytes
        checkpoint()
        if len(entries) >= MAX_CITATIONS:
            raise CitationProblem("citation-operation-limit")
        p = projections[span.projection_id]
        start, end = span.normalized_range.start, span.normalized_range.end
        raw = _raw(p, span)
        para = node
        while para.kind not in {"paragraph", "footnote", "sentence"} and para.parent_id is not None:
            para = nodes[para.parent_id]
        paragraph, sentence = None, None
        reason: ContextReason = "not-reported"
        if para.kind in {"paragraph", "footnote", "sentence"} and para.text is not None:
            pp = projections[para.text.projection_id]
            marker_range = span.normalized_range if pp.projection_id == p.projection_id else None
            if marker_range is None and native is not None:
                origin = native.elements[node.order].text_start - native.elements[para.order].text_start
                ranges = _merge_ranges(tuple((origin + r.start, origin + r.end) for r in span.raw_ranges))
                if len(ranges) == 1:
                    marker_range = _raw_to_normalized(mapping(pp), *ranges[0])
            paragraph = text_context(para, para.text, marker_range, "source-element")
            reason = "available" if marker_range is not None else "normalization-boundary"
            if marker_range is not None:
                pstart, pend = para.text.normalized_range.start, para.text.normalized_range.end
                # Sentence delimitation is an inference; it never creates a
                # canonical sentence ID or pretends abbreviations were parsed.
                boundaries = [pstart] + [
                    m.end() for m in re.finditer(r"[.!?](?:\s+|$)", pp.normalized_text[pstart:pend])
                ]
                boundaries = [pstart] + [pstart + b for b in boundaries[1:]]
                left = max(b for b in boundaries if b <= marker_range.start)
                right = min((b for b in boundaries if b >= marker_range.end), default=pend)
                sentence = text_context(
                    para, _span(pp, left, right, normalized=mapping(pp)), marker_range, "sentence-pattern"
                )
        anchor = (
            build_target(
                accepted,
                AnchorSelection(
                    revision_id=accepted.revision_id,
                    node_id=node.node_id,
                    normalized_range=CodepointRange(start=start, end=min(end, start + MAX_QUOTE_CODEPOINTS)),
                ),
            )
            if start < end
            else None
        )
        entry = CitationContext(
            order=0,
            canonical_citation_id=canonical_id,
            canonical_order=canonical_order,
            node_id=node.node_id,
            marker_span=span,
            raw_marker=raw,
            normalized_marker=p.normalized_text[start:end],
            style=style,
            knowledge_status="extracted" if canonical_id else "inferred",
            targets=groups,
            resolution=_resolution(groups),
            anchor=anchor,
            anchor_truncated=end - start > MAX_QUOTE_CODEPOINTS,
            paragraph=paragraph,
            sentence=sentence,
            context_reason=reason if start < end else "empty-marker",
            confidence=node.confidence,
        )
        total_bytes += len(entry.model_dump_json(by_alias=True).encode())
        if total_bytes > MAX_CITATION_BYTES:
            raise CitationProblem("citation-operation-limit")
        source_order = (
            (native.elements[node.order].text_start + min((r.start for r in span.raw_ranges), default=0), node.order)
            if native
            else (projection_order[p.projection_id], start, node.order)
        )
        entries.append((source_order, entry))
        if native is not None:
            origin = native.elements[node.order].text_start
            occupied.extend((origin + r.start, origin + r.end) for r in span.raw_ranges)

    for canonical_order, citation in enumerate(structure.citations):
        checkpoint()
        node = nodes[citation.node_id]
        style = "reported"
        reported_groups: tuple[CitationTargetGroup, ...] = ()
        if native is not None:
            element = native.elements[node.order]
            ns, name = _name(element.name)
            attrs = {
                a.name: a.value for a in element.attributes if sum(b.name == a.name for b in element.attributes) == 1
            }
            tokens = []
            if ns in allowed:
                if native.format == "jats" and name == "xref" and attrs.get("ref-type") == "bibr":
                    tokens = attrs.get("rid", "").split()
                elif native.format == "tei" and name == "ref":
                    # This loop contains only authenticated, already-reported
                    # canonical citations. TEI's bibliography type is optional.
                    tokens = [token[1:] if token.startswith("#") else "" for token in attrs.get("target", "").split()]
                elif native.format == "html" and name == "a":
                    href = attrs.get("href", "")
                    tokens = [href[1:]] if href.startswith("#") else [""]
            if len(tokens) > MAX_TARGETS:
                raise CitationProblem("citation-operation-limit")
            reported_groups = tuple(_group(token or "target-not-reported", ids.get(token, ())) for token in tokens)
            if any(_name(n.source_element_type)[1] == "sup" for n in children.get(node.node_id, ())):
                style = "superscript"
        else:
            reported_groups = (_group("canonical-target-set", citation.reference_candidates),)
        emit(node, citation.marker, style, reported_groups, citation.citation_id, canonical_order)

    numeric = re.compile(r"\[(?P<body>[0-9]{1,6}(?:\s*(?:[,;]|[-\u2013])\s*[0-9]{1,6})*)\]")
    parenthetical = re.compile(
        r"\((?P<body>[^()\n]{1,512}?,?\s+[0-9]{4}[a-z]?(?:;[^()\n]{1,512}?,?\s+[0-9]{4}[a-z]?){0,31})\)"
    )
    narrative = re.compile(r"(?P<author>[^\W\d_][\w\u2019'\-]{0,127}(?:\s+et\s+al\.)?)\s+\((?P<year>[0-9]{4}[a-z]?)\)")
    for node in structure.nodes:
        checkpoint()
        if node.text is None or owners[node.node_id] is not None:
            continue
        # Scan the nearest textual container only, not its footnote/paragraph
        # ancestors again. Pure superscripts remain explicit unresolved values.
        is_sup = _name(node.source_element_type)[1] == "sup"
        if node.kind not in {"paragraph", "footnote", "sentence"} and not is_sup:
            continue
        if any(n.kind in {"paragraph", "footnote", "sentence"} for n in children.get(node.node_id, ())):
            continue
        if native is None and any(p != node.text.projection_id for p in reported_projections.get(node.node_id, ())):
            # Distinct projections without the raw native receipt cannot prove
            # child→ancestor offset identity. Do not duplicate or reinterpret
            # the reported marker using a parent pattern guess.
            continue
        p = projections[node.text.projection_id]
        left, right = node.text.normalized_range.start, node.text.normalized_range.end
        text = p.normalized_text[left:right]
        matches: list[tuple[int, int, str, re.Match[str] | None]] = []
        for pattern, style in ((numeric, "numeric"), (parenthetical, "author-year"), (narrative, "narrative")):
            for pattern_match in pattern.finditer(text):
                checkpoint()
                matches.append((pattern_match.start(), pattern_match.end(), style, pattern_match))
        if is_sup and text.strip():
            matches = [(0, len(text), "superscript", None)]
        seen: list[tuple[int, int]] = []
        for start, end, style, found in sorted(matches, key=lambda m: (m[0], -m[1])):
            span = _span(p, left + start, left + end, normalized=mapping(p))
            if any(start < b and end > a for a, b in seen):
                continue
            if native is not None:
                origin = native.elements[node.order].text_start
                if any(origin + r.start < b and origin + r.end > a for r in span.raw_ranges for a, b in occupied):
                    continue
                if not is_sup and any(
                    origin + r.start < b and origin + r.end > a for r in span.raw_ranges for a, b in callout_raw
                ):
                    continue
            elif any(
                c.marker.projection_id == p.projection_id
                and start + left < c.marker.normalized_range.end
                and end + left > c.marker.normalized_range.start
                for c in structure.citations
            ):
                continue
            elif not is_sup and any(
                s.projection_id == p.projection_id
                and span.normalized_range.start < s.normalized_range.end
                and span.normalized_range.end > s.normalized_range.start
                for _, s in callout_spans
            ):
                continue
            groups: list[CitationTargetGroup] = []
            if style == "numeric":
                assert found is not None
                for segment in re.split(r"\s*[,;]\s*", found.group("body")):
                    bounds = re.split(r"\s*[-\u2013]\s*", segment)
                    first, last = int(bounds[0]), int(bounds[-1])
                    if last < first or last - first + 1 > MAX_TARGETS or len(groups) + last - first + 1 > MAX_TARGETS:
                        groups = [_group(found.group(0), ())]
                        break
                    groups.extend(_group(str(number), labels.get(str(number), ())) for number in range(first, last + 1))
            elif style in {"author-year", "narrative"}:
                assert found is not None
                parts = (
                    [found.group("author") + ", " + found.group("year")]
                    if style == "narrative"
                    else found.group("body").split(";")
                )
                for part in parts:
                    author_match = re.fullmatch(r"\s*(.+?),?\s+([0-9]{4}[a-z]?)\s*", part)
                    identities = (
                        authors.get((author_match.group(1).rstrip(",").casefold(), author_match.group(2)), ())
                        if author_match
                        else ()
                    )
                    groups.append(_group(part.strip(), identities))
            else:
                groups = [_group("bibliographic-role-not-reported", ())]
            emit(node, span, style, tuple(groups))
            seen.append((start, end))
    checkpoint()
    return tuple(
        CitationContext.model_validate(e.model_dump() | {"order": order})
        for order, (_, e) in enumerate(sorted(entries, key=lambda value: value[0]))
    )
