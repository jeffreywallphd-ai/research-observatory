"""Typed, replayable human proposals over one exact immutable document revision.

These pure values never save, accept, change heads or grant source access. Labels
and human reference matches remain separate from observed parser text/assertions.
The protected adapter must bind author/rationale and recheck current authority.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .document_revisions import AcceptedDocumentRevision, DocumentRevisionProblem, Instant, protected_json
from .parsing.contracts import (
    CodepointRange,
    Digest,
    DocumentIR,
    Identity,
    IRValue,
    PageRegionLocator,
    ProjectIdentity,
    SourceIdentity,
    TextProjection,
    TextSpan,
    Token,
)
from .parsing.normalization import normalize_text

CORRECTION_MEDIA_TYPE = "application/vnd.research-observatory.document-correction+json"
CORRECTION_VERSION: Literal["document-correction-1"] = "document-correction-1"
MAX_CORRECTION_RECORD_BYTES = 128 * 1024
MAX_CORRECTION_ITEMS = 10_000
MAX_CORRECTION_TEXT_CODEPOINTS = 1_000_000
MAX_CORRECTION_SECONDS = 5.0
type Label = Annotated[str, Field(strict=True, min_length=1, max_length=160)]
type Rationale = Annotated[str, Field(strict=True, min_length=1, max_length=1000)]


def value_sha256(value: IRValue) -> str:
    return hashlib.sha256(protected_json(value)).hexdigest()


class NodeCorrection(IRValue):
    node_id: Identity
    expected_node_sha256: Digest


class RelabelCorrection(NodeCorrection):
    op: Literal["relabel"]
    label: Label = Field(repr=False)

    @field_validator("label")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("correction-label-empty")
        return value


class ReorderCorrection(NodeCorrection):
    op: Literal["reorder"]
    before_node_id: Identity | None


class SplitCorrection(NodeCorrection):
    op: Literal["split"]
    at: Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]


class MergeCorrection(NodeCorrection):
    op: Literal["merge"]
    with_node_id: Identity
    expected_with_node_sha256: Digest


class ReferenceRematchCorrection(NodeCorrection):
    op: Literal["reference-rematch"]
    reference_id: Identity
    expected_reference_sha256: Digest
    work_id: Identity
    work_revision_id: Identity


class AnchorCorrection(NodeCorrection):
    op: Literal["adjust-anchor"]
    locator: PageRegionLocator


class ExcludeCorrection(NodeCorrection):
    op: Literal["exclude"]


type CorrectionOperation = Annotated[
    RelabelCorrection
    | ReorderCorrection
    | SplitCorrection
    | MergeCorrection
    | ReferenceRematchCorrection
    | AnchorCorrection
    | ExcludeCorrection,
    Field(discriminator="op"),
]


class CorrectionPatch(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    base_revision_id: Identity
    expected_structure_sha256: Digest
    operations: tuple[CorrectionOperation, ...] = Field(max_length=32)


class CorrectionSave(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    draft_id: Identity | None
    expected_draft_revision_id: Identity | None
    patch: CorrectionPatch
    rationale: Rationale = Field(repr=False)

    @model_validator(mode="after")
    def complete_predecessor(self):
        if (self.draft_id is None) != (self.expected_draft_revision_id is None) or not self.rationale.strip():
            raise ValueError("document-correction-draft-invalid")
        return self


class CorrectionAcceptance(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    draft_revision_id: Identity
    expected_current_revision_id: Identity
    confirmation_sha256: Digest
    decision: Literal["accept-correction"]


class CorrectionDiscard(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    draft_revision_id: Identity
    confirmation_sha256: Digest
    rationale: Rationale = Field(repr=False)

    @field_validator("rationale")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("correction-rationale-empty")
        return value


class CorrectionDraft(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    document_type: Literal["document-correction-draft"] = "document-correction-draft"
    correction_version: Literal["document-correction-1"] = CORRECTION_VERSION
    project_id: ProjectIdentity
    draft_id: Identity
    revision_id: Identity
    previous_draft_revision_id: Identity | None
    source: SourceIdentity
    patch: CorrectionPatch = Field(repr=False)
    rationale: Rationale = Field(repr=False)
    authored_by: Identity
    authored_actor_type: Literal["human"] = "human"
    authored_at: Instant
    intent_revision_id: Identity
    intent_sha256: Digest
    policy_sha256: Digest
    command_id: Identity
    command_kind: Literal["save", "discard"] = "save"
    command_sha256: Digest
    preview_sha256: Digest
    state: Literal["draft", "discarded"] = "draft"

    @model_validator(mode="after")
    def source_binding(self):
        if (
            self.project_id != self.source.project_id
            or not self.rationale.strip()
            or self.revision_id
            in {
                self.draft_id,
                self.patch.base_revision_id,
                self.source.document_revision_id,
            }
        ):
            raise ValueError("document-correction-draft-invalid")
        if (self.command_kind == "discard") != (self.state == "discarded") or (
            self.command_kind == "discard" and self.previous_draft_revision_id is None
        ):
            raise ValueError("document-correction-draft-invalid")
        return self


class CorrectionLabel(IRValue):
    node_id: Token
    label: Label = Field(repr=False)


class CorrectionNodeOrigin(IRValue):
    result_node_id: Token
    source_node_id: Identity
    result_range: CodepointRange | None
    source_range: CodepointRange | None


class HumanReferenceMatch(IRValue):
    reference_id: Identity
    work_id: Identity
    work_revision_id: Identity
    basis: Literal["human-proposed", "human-accepted"] = "human-proposed"
    scholarly_verification: Literal["unverified"] = "unverified"


class CorrectionInheritance(IRValue):
    base_revision_id: Identity
    expected_structure_sha256: Digest
    labels: tuple[CorrectionLabel, ...] = Field(max_length=MAX_CORRECTION_ITEMS)
    excluded_node_ids: tuple[Identity, ...] = Field(max_length=MAX_CORRECTION_ITEMS)
    reference_matches: tuple[HumanReferenceMatch, ...] = Field(max_length=1000)


class CorrectionResult(IRValue):
    ir: DocumentIR = Field(repr=False)
    labels: tuple[CorrectionLabel, ...]
    origins: tuple[CorrectionNodeOrigin, ...]
    excluded_node_ids: tuple[Identity, ...]
    reference_matches: tuple[HumanReferenceMatch, ...]

    @property
    def result_sha256(self):
        return value_sha256(self)


def staged_structure(base: AcceptedDocumentRevision) -> dict:
    """Use exact prior canonical IDs as detached staged keys for a successor."""
    wire = base.structure.model_dump(mode="json", by_alias=True)
    wire["disposition"] = "staged"
    for rows, field in (
        (wire["nodes"], "nodeId"),
        (wire["references"], "referenceId"),
        (wire["citations"], "citationId"),
    ):
        for row in rows:
            row["stagedId"] = row.pop(field)
    return wire


def apply_correction(
    base: AcceptedDocumentRevision,
    patch: CorrectionPatch,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    inherited: CorrectionInheritance | None = None,
) -> CorrectionResult:
    """Apply all operations or refuse; no mutation of parser output or base."""
    deadline = time.monotonic() + MAX_CORRECTION_SECONDS

    def checkpoint():
        if cancelled():
            raise DocumentRevisionProblem("document-correction-cancelled")
        if time.monotonic() > deadline:
            raise DocumentRevisionProblem("document-correction-limit")

    try:
        checkpoint()
        # Admission precedes detached models, normalization and JSON copies.
        if not isinstance(base, AcceptedDocumentRevision) or (
            sum(
                len(rows)
                for rows in (
                    base.structure.nodes,
                    base.structure.references,
                    base.structure.citations,
                    base.structure.text_projections,
                    base.structure.figures,
                    base.structure.tables,
                )
            )
            + sum(len(t.cells) for t in base.structure.tables)
            > MAX_CORRECTION_ITEMS
            or sum(len(p.raw_text) + len(p.normalized_text) for p in base.structure.text_projections)
            > MAX_CORRECTION_TEXT_CODEPOINTS
        ):
            raise DocumentRevisionProblem("document-correction-limit")
        base = AcceptedDocumentRevision.model_validate(base)
        patch = CorrectionPatch.model_validate(patch)
        if (patch.base_revision_id, patch.expected_structure_sha256) != (base.revision_id, base.structure_sha256):
            raise DocumentRevisionProblem("document-correction-base-changed")
        originals = {node.node_id: node for node in base.structure.nodes}
        projections: dict[str, TextProjection] = {p.projection_id: p for p in base.structure.text_projections}
        wire = staged_structure(base)
        labels = {}
        matches = {}
        excluded = []
        if inherited is not None:
            inherited = CorrectionInheritance.model_validate(inherited)
            if (inherited.base_revision_id, inherited.expected_structure_sha256) != (
                base.revision_id,
                base.structure_sha256,
            ):
                raise DocumentRevisionProblem("document-correction-inheritance-invalid")
            labels = {item.node_id: item.label for item in inherited.labels}
            matches = {item.reference_id: item for item in inherited.reference_matches}
            excluded = list(inherited.excluded_node_ids)
            if (
                len(labels) != len(inherited.labels)
                or not set(labels).issubset(originals)
                or len(matches) != len(inherited.reference_matches)
                or not set(matches).issubset({r.reference_id for r in base.structure.references})
                or len(set(excluded)) != len(excluded)
                or set(excluded).intersection(originals)
            ):
                raise DocumentRevisionProblem("document-correction-inheritance-invalid")
        origins = [
            CorrectionNodeOrigin(
                result_node_id=n.node_id,
                source_node_id=n.node_id,
                result_range=n.text.normalized_range if n.text else None,
                source_range=n.text.normalized_range if n.text else None,
            )
            for n in base.structure.nodes
        ]

        def descendants(key):
            found = {key}
            for node in wire["nodes"]:
                checkpoint()
                if node["parentId"] in found:
                    found.add(node["stagedId"])
            return found

        def span(projection_id, start, end):
            mapped = normalize_text(projections[projection_id].raw_text, cancelled=cancelled)
            return TextSpan(
                projection_id=projection_id,
                normalized_range=CodepointRange(start=start, end=end),
                raw_ranges=tuple(CodepointRange(start=a, end=b) for a, b in mapped.raw_ranges_for(start, end)),
            ).model_dump(mode="json", by_alias=True)

        for index, operation in enumerate(patch.operations):
            checkpoint()
            key = operation.node_id
            original = originals.get(key)
            nodes = {n["stagedId"]: n for n in wire["nodes"]}
            if original is None or value_sha256(original) != operation.expected_node_sha256 or key not in nodes:
                raise DocumentRevisionProblem("document-correction-target-changed")
            node = nodes[key]
            if isinstance(operation, RelabelCorrection):
                labels[key] = operation.label
            elif isinstance(operation, ReorderCorrection):
                before = operation.before_node_id
                group = descendants(key)
                if before is not None and (
                    before not in nodes or before in group or nodes[before]["parentId"] != node["parentId"]
                ):
                    raise DocumentRevisionProblem("document-correction-order-conflict")
                moving = [n for n in wire["nodes"] if n["stagedId"] in group]
                rest = [n for n in wire["nodes"] if n["stagedId"] not in group]
                if before is not None:
                    position = next(i for i, n in enumerate(rest) if n["stagedId"] == before)
                else:
                    siblings = [n["stagedId"] for n in rest if n["parentId"] == node["parentId"]]
                    last = descendants(siblings[-1]) if siblings else set()
                    position = max((i + 1 for i, n in enumerate(rest) if n["stagedId"] in last), default=len(rest))
                wire["nodes"] = rest[:position] + moving + rest[position:]
            elif isinstance(operation, SplitCorrection):
                if len(wire["nodes"]) + 1 > MAX_CORRECTION_ITEMS:
                    raise DocumentRevisionProblem("document-correction-limit")
                text = node["text"]
                if text is None or node["kind"] not in {
                    "title",
                    "heading",
                    "paragraph",
                    "caption",
                    "list-item",
                    "equation",
                    "unknown",
                }:
                    raise DocumentRevisionProblem("document-correction-split-ambiguous")
                start, end = text["normalizedRange"]["start"], text["normalizedRange"]["end"]
                if not start < operation.at < end:
                    raise DocumentRevisionProblem("document-correction-split-range")
                left, right = (
                    span(text["projectionId"], start, operation.at),
                    span(text["projectionId"], operation.at, end),
                )
                if any(
                    a["start"] < b["end"] and b["start"] < a["end"]
                    for a in left["rawRanges"]
                    for b in right["rawRanges"]
                ):
                    raise DocumentRevisionProblem("document-correction-split-ambiguous")
                second_key = f"correction-split-{index}"
                if second_key in nodes:
                    raise DocumentRevisionProblem("document-correction-identity-conflict")
                group = descendants(key)
                direct_children = [n for n in wire["nodes"] if n["parentId"] == key]
                right_ids = set()
                for child in direct_children:
                    content = child["text"]
                    if content is None or content["projectionId"] != text["projectionId"]:
                        raise DocumentRevisionProblem("document-correction-split-ambiguous")
                    lower, upper = content["normalizedRange"]["start"], content["normalizedRange"]["end"]
                    if lower < start or upper > end or lower < operation.at < upper:
                        raise DocumentRevisionProblem("document-correction-split-ambiguous")
                    if lower >= operation.at:
                        right_ids.update(descendants(child["stagedId"]))
                        child["parentId"] = second_key
                first = {**node, "text": left}
                second = {
                    **node,
                    "stagedId": second_key,
                    "text": right,
                    "warnings": [
                        {**w, "nodeId": second_key if w["nodeId"] == key else w["nodeId"]} for w in node["warnings"]
                    ],
                }
                for fragment in (first, second):
                    if fragment["locator"]["kind"] == "text":
                        fragment["locator"] = {
                            "kind": "text",
                            "projectionId": text["projectionId"],
                            "rawRanges": fragment["text"]["rawRanges"],
                        }
                replacement = [first] + [n for n in wire["nodes"] if n["stagedId"] in group - right_ids - {key}]
                replacement += [second] + [n for n in wire["nodes"] if n["stagedId"] in right_ids]
                position = next(i for i, n in enumerate(wire["nodes"]) if n["stagedId"] == key)
                rest = [n for n in wire["nodes"] if n["stagedId"] not in group]
                wire["nodes"] = rest[:position] + replacement + rest[position:]
                old_origins = [o for o in origins if o.result_node_id == key]
                origins = [o for o in origins if o.result_node_id != key]
                for origin in old_origins:
                    if origin.result_range is None or origin.source_range is None:
                        raise DocumentRevisionProblem("document-correction-split-ambiguous")
                    for fragment_key, a, b in ((key, start, operation.at), (second_key, operation.at, end)):
                        low, high = max(a, origin.result_range.start), min(b, origin.result_range.end)
                        if low < high:
                            delta = origin.source_range.start - origin.result_range.start
                            origins.append(
                                CorrectionNodeOrigin(
                                    result_node_id=fragment_key,
                                    source_node_id=origin.source_node_id,
                                    result_range=CodepointRange(start=low, end=high),
                                    source_range=CodepointRange(start=low + delta, end=high + delta),
                                )
                            )
            elif isinstance(operation, MergeCorrection):
                other = nodes.get(operation.with_node_id)
                prior = originals.get(operation.with_node_id)
                siblings = [n["stagedId"] for n in wire["nodes"] if n["parentId"] == node["parentId"]]
                if (
                    other is None
                    or prior is None
                    or value_sha256(prior) != operation.expected_with_node_sha256
                    or node["kind"]
                    not in {"title", "heading", "paragraph", "caption", "list-item", "equation", "unknown"}
                    or node["kind"] != other["kind"]
                    or other["parentId"] != node["parentId"]
                    or descendants(key) != {key}
                    or descendants(other["stagedId"]) != {other["stagedId"]}
                    or siblings[siblings.index(key) + 1 : siblings.index(key) + 2] != [other["stagedId"]]
                    or node["text"] is None
                    or other["text"] is None
                ):
                    raise DocumentRevisionProblem("document-correction-merge-ambiguous")
                left, right = node["text"], other["text"]
                same = (
                    left["projectionId"] == right["projectionId"]
                    and left["normalizedRange"]["end"] == right["normalizedRange"]["start"]
                )
                first_length = left["normalizedRange"]["end"] - left["normalizedRange"]["start"]
                result_start = left["normalizedRange"]["start"] if same else 0
                if same:
                    joined = span(left["projectionId"], result_start, right["normalizedRange"]["end"])
                else:
                    if left["projectionId"] == right["projectionId"] and any(
                        a["start"] < b["end"] and b["start"] < a["end"]
                        for a in left["rawRanges"]
                        for b in right["rawRanges"]
                    ):
                        raise DocumentRevisionProblem("document-correction-merge-ambiguous")
                    extra_text = sum(
                        sum(r["end"] - r["start"] for r in t["rawRanges"])
                        + t["normalizedRange"]["end"]
                        - t["normalizedRange"]["start"]
                        for t in (left, right)
                    )
                    if (
                        sum(len(p.raw_text) + len(p.normalized_text) for p in projections.values()) + extra_text
                        > MAX_CORRECTION_TEXT_CODEPOINTS
                        or len(projections) + 1 > MAX_CORRECTION_ITEMS
                    ):
                        raise DocumentRevisionProblem("document-correction-limit")
                    raw_parts = [
                        "".join(projections[t["projectionId"]].raw_text[r["start"] : r["end"]] for r in t["rawRanges"])
                        for t in (left, right)
                    ]
                    normalized_parts = [
                        projections[t["projectionId"]].normalized_text[
                            t["normalizedRange"]["start"] : t["normalizedRange"]["end"]
                        ]
                        for t in (left, right)
                    ]
                    projection = TextProjection.from_raw(f"correction-merge-projection-{index}", "".join(raw_parts))
                    if projection.normalized_text != "".join(normalized_parts):
                        raise DocumentRevisionProblem("document-correction-merge-ambiguous")
                    projections[projection.projection_id] = projection
                    wire["textProjections"].append(projection.model_dump(mode="json", by_alias=True))
                    joined = span(projection.projection_id, 0, len(projection.normalized_text))
                node["text"] = joined
                if node["locator"]["kind"] == "text":
                    node["locator"] = {
                        "kind": "text",
                        "projectionId": joined["projectionId"],
                        "rawRanges": joined["rawRanges"],
                    }
                elif node["locator"] != other["locator"]:
                    node["locator"] = {"kind": "unavailable", "reason": "unsupported-location"}
                node["sourceElementType"] = None if node["kind"] != "unknown" else "human-merged-block"
                node["warnings"].extend(
                    {**w, "nodeId": key if w["nodeId"] == other["stagedId"] else w["nodeId"]} for w in other["warnings"]
                )
                wire["nodes"] = [n for n in wire["nodes"] if n["stagedId"] != other["stagedId"]]
                updated = []
                for origin in origins:
                    if origin.result_node_id not in {key, other["stagedId"]}:
                        updated.append(origin)
                        continue
                    if origin.result_range is None:
                        raise DocumentRevisionProblem("document-correction-merge-ambiguous")
                    part = left if origin.result_node_id == key else right
                    offset = (
                        result_start
                        + (0 if origin.result_node_id == key else first_length)
                        - part["normalizedRange"]["start"]
                    )
                    updated.append(
                        origin.model_copy(
                            update={
                                "result_node_id": key,
                                "result_range": CodepointRange(
                                    start=origin.result_range.start + offset, end=origin.result_range.end + offset
                                ),
                            }
                        )
                    )
                origins = updated
                if other["stagedId"] in labels:
                    raise DocumentRevisionProblem("document-correction-merge-label-ambiguous")
            elif isinstance(operation, ReferenceRematchCorrection):
                reference = next(
                    (r for r in base.structure.references if r.reference_id == operation.reference_id), None
                )
                if (
                    reference is None
                    or reference.node_id != key
                    or value_sha256(reference) != operation.expected_reference_sha256
                ):
                    raise DocumentRevisionProblem("document-correction-reference-changed")
                matches[operation.reference_id] = HumanReferenceMatch(
                    reference_id=operation.reference_id,
                    work_id=operation.work_id,
                    work_revision_id=operation.work_revision_id,
                )
            elif isinstance(operation, AnchorCorrection):
                node["locator"] = operation.locator.model_dump(mode="json", by_alias=True)
                for figure in wire["figures"]:
                    if figure["nodeId"] == key:
                        figure["locator"] = node["locator"]
            elif isinstance(operation, ExcludeCorrection):
                group = descendants(key)
                excluded.extend(n["stagedId"] for n in wire["nodes"] if n["stagedId"] in group)
                warning_rows = [w for n in wire["nodes"] if n["stagedId"] in group for w in n["warnings"]]
                wire["quality"]["warnings"].extend({**w, "nodeId": None} for w in warning_rows)
                wire["nodes"] = [n for n in wire["nodes"] if n["stagedId"] not in group]
                wire["references"] = [r for r in wire["references"] if r["nodeId"] not in group]
                wire["citations"] = [c for c in wire["citations"] if c["nodeId"] not in group]
                wire["tables"] = [t for t in wire["tables"] if t["nodeId"] not in group]
                for table in wire["tables"]:
                    if any(c["nodeId"] in group for c in table["cells"]):
                        table["cells"] = [c for c in table["cells"] if c["nodeId"] not in group]
                        table["gridState"] = "ambiguous"
                wire["figures"] = [f for f in wire["figures"] if f["nodeId"] not in group]
                wire["quality"]["tableCellConfidence"] = [
                    c for c in wire["quality"]["tableCellConfidence"] if c["nodeId"] not in group
                ]
                origins = [o for o in origins if o.result_node_id not in group]
                labels = {k: v for k, v in labels.items() if k not in group}
                remaining = {r["stagedId"] for r in wire["references"]}
                matches = {k: v for k, v in matches.items() if k in remaining}
                for citation in wire["citations"]:
                    citation["referenceCandidates"] = [k for k in citation["referenceCandidates"] if k in remaining]
                    count = len(citation["referenceCandidates"])
                    citation["resolution"] = "unresolved" if count == 0 else "candidate" if count == 1 else "ambiguous"
            for order, current in enumerate(wire["nodes"]):
                current["order"] = order
            for order, reference in enumerate(wire["references"]):
                reference["order"] = order
            active_ids = {n["stagedId"] for n in wire["nodes"]}
            for warning in wire["quality"]["warnings"]:
                if warning["nodeId"] is not None and warning["nodeId"] not in active_ids:
                    warning["nodeId"] = None
        if not wire["nodes"] or len(wire["nodes"]) + len(wire["textProjections"]) > MAX_CORRECTION_ITEMS:
            raise DocumentRevisionProblem("document-correction-limit")
        result = CorrectionResult(
            ir=DocumentIR.model_validate(wire),
            labels=tuple(CorrectionLabel(node_id=k, label=v) for k, v in sorted(labels.items())),
            origins=tuple(origins),
            excluded_node_ids=tuple(excluded),
            reference_matches=tuple(matches[k] for k in sorted(matches)),
        )
        checkpoint()
        return result
    except DocumentRevisionProblem:
        raise
    except Exception:
        raise DocumentRevisionProblem("document-correction-invalid") from None
