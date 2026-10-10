"""Bounded reparse proposals and differences; no publication or actor authority."""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .anchors.contracts import SourceAnchorTarget
from .document_corrections import (
    CorrectionInheritance,
    CorrectionLabel,
    CorrectionPatch,
    CorrectionPreviewBase,
    HumanReferenceMatch,
    Rationale,
    apply_correction,
    value_sha256,
)
from .document_parse_workflow import DocumentParseInput
from .document_revisions import (
    CanonicalDocumentStructure,
    CanonicalNode,
    CanonicalReference,
    DocumentRevisionProblem,
    Instant,
    RetainedParseResultReceipt,
    canonicalize_structure,
)
from .parsing.contracts import (
    Digest,
    Identity,
    IRValue,
    ProjectIdentity,
    SourceIdentity,
    SourceLocator,
    TextSpan,
    Token,
)
from .parsing.quality import QualityAssessment

REPROCESSING_MEDIA_TYPE = "application/vnd.research-observatory.document-reprocessing+json"
REPROCESSING_VERSION: Literal["document-reprocessing-1"] = "document-reprocessing-1"
MAX_REPROCESSING_BYTES = 8 * 1024 * 1024
MAX_REPROCESSING_ITEMS = 10_000
MAX_REPROCESSING_TEXT = 1_000_000
MAX_REPROCESSING_SECONDS = 5.0
type Count = Annotated[int, Field(strict=True, ge=0, le=100_000)]
type Preview = Annotated[str, Field(strict=True, max_length=160)]
type DifferenceState = Literal["unchanged", "moved", "modified", "added", "removed", "ambiguous", "unresolvable"]
type ItemState = Literal[
    "not-submitted", "processing", "needs-continuation", "failed", "cancelled", "ready", "base-conflict", "accepted"
]


class ReprocessingOutcomeUnknown(DocumentRevisionProblem):
    """A durable mutation may exist, but its protected response is unconfirmed."""

    def __init__(self) -> None:
        super().__init__("document-reprocessing-outcome-unknown")


class ReprocessingCreate(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    base_revision_ids: tuple[Identity, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.base_revision_ids)) != len(self.base_revision_ids):
            raise ValueError("reprocessing-duplicate-document")
        return self


class ReprocessingContinue(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    batch_revision_id: Identity
    item_id: Identity
    expected_job_id: Identity | None


class ReprocessingCancel(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    batch_revision_id: Identity


class ReprocessingMapping(IRValue):
    obligation_id: Digest
    node_id: Identity
    related_node_id: Identity | None
    reference_id: Identity | None


class ReprocessingReconcile(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    comparison_revision_id: Identity
    expected_plan_revision_id: Identity | None
    rationale: Rationale = Field(repr=False)
    mappings: tuple[ReprocessingMapping, ...] = Field(max_length=32)


class ReprocessingAcceptance(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    plan_revision_id: Identity
    expected_current_revision_id: Identity
    confirmation_sha256: Digest
    expected_graph_sha256: Digest
    decision: Literal["accept-reparse"]


class ReprocessingItem(IRValue):
    item_id: Identity
    base_revision_id: Identity
    inputs: DocumentParseInput = Field(repr=False)


class ReprocessingBatch(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    document_type: Literal["document-reprocessing-batch"] = "document-reprocessing-batch"
    reprocessing_version: Literal["document-reprocessing-1"] = REPROCESSING_VERSION
    project_id: ProjectIdentity
    batch_id: Identity
    revision_id: Identity
    previous_revision_id: Identity | None
    command: ReprocessingCreate | ReprocessingContinue | ReprocessingCancel = Field(repr=False)
    command_id: Identity
    command_sha256: Digest
    authored_by: Identity
    authored_at: Instant
    intent_revision_id: Identity
    intent_sha256: Digest
    policy_sha256: Digest
    state: Literal["active", "cancelled"]
    items: tuple[ReprocessingItem, ...] = Field(min_length=1, max_length=10, repr=False)


class ReprocessingComparison(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    document_type: Literal["document-reprocessing-comparison"] = "document-reprocessing-comparison"
    project_id: ProjectIdentity
    comparison_id: Identity
    revision_id: Identity
    batch_revision_id: Identity
    item_id: Identity
    base_revision_id: Identity
    job_id: Identity
    result: RetainedParseResultReceipt
    candidate: CorrectionPreviewBase = Field(repr=False)
    correction_revision_ids: tuple[Identity, ...] = Field(max_length=32)
    created_by: Identity
    created_at: Instant
    command_sha256: Digest


class ReconciledGeneration(IRValue):
    original_draft_revision_id: Identity
    mapped_patch: CorrectionPatch = Field(repr=False)
    mappings: tuple[ReprocessingMapping, ...] = Field(min_length=1, max_length=32)
    next_candidate: CorrectionPreviewBase = Field(repr=False)


class ReprocessingPlan(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    document_type: Literal["document-reprocessing-plan"] = "document-reprocessing-plan"
    project_id: ProjectIdentity
    plan_id: Identity
    revision_id: Identity
    previous_revision_id: Identity | None
    comparison_revision_id: Identity
    command: ReprocessingReconcile = Field(repr=False)
    command_sha256: Digest
    authored_by: Identity
    authored_at: Instant
    intent_revision_id: Identity
    intent_sha256: Digest
    policy_sha256: Digest
    steps: tuple[ReconciledGeneration, ...] = Field(max_length=32, repr=False)


class ReprocessingAccepted(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    document_type: Literal["document-reprocessing-acceptance"] = "document-reprocessing-acceptance"
    project_id: ProjectIdentity
    record_id: Identity
    revision_id: Identity
    command: ReprocessingAcceptance
    command_sha256: Digest
    batch_id: Identity
    batch_revision_id: Identity
    item_id: Identity
    comparison_revision_id: Identity
    plan_revision_id: Identity
    base_revision_id: Identity
    machine_revision_id: Identity
    final_revision_id: Identity
    machine_command_id: Identity
    machine_decision_id: Identity
    machine_decision_revision_id: Identity
    machine_command_sha256: Digest
    nested_draft_revision_ids: tuple[Identity, ...] = Field(max_length=32)
    final_command_ids: tuple[Identity, ...] = Field(max_length=32)
    impact_run_id: Identity
    accepted_by: Identity
    accepted_at: Instant
    intent_revision_id: Identity
    intent_sha256: Digest
    policy_sha256: Digest


type ReprocessingRecord = ReprocessingBatch | ReprocessingComparison | ReprocessingPlan | ReprocessingAccepted


class ReprocessingItemView(IRValue):
    item_id: Identity
    base_revision_id: Identity
    job_id: Identity | None
    state: ItemState
    accepted_revision_id: Identity | None


class ReprocessingBatchView(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    batch_id: Identity
    batch_revision_id: Identity
    state: Literal["active", "cancelled"]
    items: tuple[ReprocessingItemView, ...] = Field(max_length=10)


class ReprocessingQueue(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    items: tuple[ReprocessingBatchView, ...] = Field(max_length=10)
    next_after_batch_id: Identity | None


class ReprocessingDifference(IRValue):
    kind: Literal["node", "reference", "anchor"]
    old_id: Token | None
    new_id: Token | None
    state: DifferenceState
    old_preview: Preview | None = Field(repr=False)
    new_preview: Preview | None = Field(repr=False)
    old_locator: SourceLocator | None
    new_locator: SourceLocator | None


class ReprocessingCounts(IRValue):
    unchanged: Count = 0
    moved: Count = 0
    modified: Count = 0
    added: Count = 0
    removed: Count = 0
    ambiguous: Count = 0
    unresolvable: Count = 0


class ReprocessingObligation(IRValue):
    obligation_id: Digest
    original_draft_revision_id: Identity
    original_base_revision_id: Identity
    operation_index: Count
    operation: Token
    old_node_id: Identity
    old_node_sha256: Digest
    old_preview: Preview = Field(repr=False)
    related_old_node_id: Identity | None
    original_reference_id: Identity | None
    original_author: Identity
    original_rationale: Preview = Field(repr=False)


class ReprocessingNode(IRValue):
    node_id: Identity
    parent_id: Identity | None
    order: Count
    kind: Token
    preview: Preview = Field(repr=False)
    node_sha256: Digest
    reference_id: Identity | None


class ReprocessingImpact(IRValue):
    graph_sha256: Digest
    affected_count: Count
    informational_count: Count
    legacy_unreported_count: Count
    state: Literal["prospective-rechecked-at-acceptance"] = "prospective-rechecked-at-acceptance"


class ReprocessingPage(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    batch_id: Identity
    batch_revision_id: Identity
    item_id: Identity
    base_revision_id: Identity
    current_revision_id: Identity
    source: SourceIdentity
    job_id: Identity
    attempt_id: Identity
    result_id: Identity
    comparison_revision_id: Identity
    candidate_revision_id: Identity
    plan_revision_id: Identity | None
    confirmation_sha256: Digest | None
    generation: Count
    generation_count: Count
    total_obligations: Count
    unresolved_count: Count
    obligations: tuple[ReprocessingObligation, ...] = Field(max_length=32)
    candidate_nodes: tuple[ReprocessingNode, ...] = Field(max_length=20)
    differences: tuple[ReprocessingDifference, ...] = Field(max_length=20)
    difference_counts: ReprocessingCounts
    anchor_candidates: tuple[ReprocessingDifference, ...] = Field(max_length=20)
    anchor_counts: ReprocessingCounts
    next_offset: Count | None
    old_quality: QualityAssessment
    new_quality: QualityAssessment
    impact: ReprocessingImpact
    state: Literal["review", "ready-to-accept", "base-conflict"]
    scholarly_verification: Literal["unverified"] = "unverified"


class ReprocessingAcceptedView(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    batch_id: Identity
    batch_revision_id: Identity
    item_id: Identity
    previous_revision_id: Identity
    revision_id: Identity
    machine_revision_id: Identity
    impact_run_id: Identity
    impact_state: Literal["running", "completed", "cancelled"]
    impact_checkpoint_sha256: Digest
    processed_items: Count
    total_items: Count
    scholarly_verification: Literal["unverified"] = "unverified"


def operation_id(draft_revision_id: str, index: int, operation: IRValue) -> str:
    return hashlib.sha256(
        draft_revision_id.encode() + str(index).encode() + value_sha256(operation).encode()
    ).hexdigest()


def mapped_patch(draft, candidate, mappings):
    """Account for every authenticated old operation, with no inferred target."""
    expected = {operation_id(draft.revision_id, i, op): op for i, op in enumerate(draft.patch.operations)}
    supplied = {m.obligation_id: m for m in mappings}
    if len(supplied) != len(mappings) or set(supplied) != set(expected):
        raise DocumentRevisionProblem("document-reprocessing-incomplete-reconciliation")
    nodes = {n.node_id: n for n in candidate.structure.nodes}
    references = {r.reference_id: r for r in candidate.structure.references}
    operations = []
    for identity, operation in expected.items():
        mapping = supplied[identity]
        node = nodes.get(mapping.node_id)
        if node is None:
            raise DocumentRevisionProblem("document-reprocessing-target-unavailable")
        wire = operation.model_dump(mode="json", by_alias=True)
        wire["nodeId"], wire["expectedNodeSha256"] = node.node_id, value_sha256(node)
        if operation.op in {"reorder", "merge"}:
            old_related = operation.before_node_id if operation.op == "reorder" else operation.with_node_id
            if (mapping.related_node_id is None) != (old_related is None):
                raise DocumentRevisionProblem("document-reprocessing-target-unavailable")
            related = nodes.get(mapping.related_node_id) if mapping.related_node_id else None
            if old_related is not None and related is None:
                raise DocumentRevisionProblem("document-reprocessing-target-unavailable")
            if operation.op == "reorder":
                wire["beforeNodeId"] = mapping.related_node_id
            else:
                assert related is not None
                wire["withNodeId"], wire["expectedWithNodeSha256"] = related.node_id, value_sha256(related)
        elif mapping.related_node_id is not None:
            raise DocumentRevisionProblem("document-reprocessing-target-unavailable")
        if operation.op == "reference-rematch":
            reference = references.get(mapping.reference_id)
            if reference is None or reference.node_id != node.node_id:
                raise DocumentRevisionProblem("document-reprocessing-target-unavailable")
            wire["referenceId"], wire["expectedReferenceSha256"] = reference.reference_id, value_sha256(reference)
        elif mapping.reference_id is not None:
            raise DocumentRevisionProblem("document-reprocessing-target-unavailable")
        operations.append(wire)
    return CorrectionPatch.model_validate(
        {
            "schemaVersion": "1.0",
            "baseRevisionId": candidate.revision_id,
            "expectedStructureSha256": candidate.structure_sha256,
            "operations": operations,
        }
    )


def preview_step(candidate, patch, inherited, *, revision_id, cancelled=lambda: False):
    result = apply_correction(candidate, patch, inherited=inherited, cancelled=cancelled)
    structure, identities = canonicalize_structure(result.ir)
    next_candidate = CorrectionPreviewBase(
        revision_id=revision_id,
        result=candidate.result,
        structure_sha256=value_sha256(structure),
        element_identities=identities,
        structure=structure,
    )
    return next_candidate, result


def preview_inheritance(candidate, result):
    nodes = {m.staged_id: m.canonical_id for m in candidate.element_identities if m.role == "node"}
    references = {m.staged_id: m.canonical_id for m in candidate.element_identities if m.role == "reference"}
    return CorrectionInheritance(
        base_revision_id=candidate.revision_id,
        expected_structure_sha256=candidate.structure_sha256,
        labels=tuple(CorrectionLabel(node_id=nodes[label.node_id], label=label.label) for label in result.labels),
        excluded_node_ids=result.excluded_node_ids,
        reference_matches=tuple(
            HumanReferenceMatch(
                reference_id=references[m.reference_id],
                work_id=m.work_id,
                work_revision_id=m.work_revision_id,
                basis="human-accepted",
            )
            for m in result.reference_matches
        ),
    )


def node_text(structure, node):
    if node.text is None:
        return ""
    projection = next(p for p in structure.text_projections if p.projection_id == node.text.projection_id)
    span = node.text.normalized_range
    return projection.normalized_text[span.start : span.end]


def reference_text(structure, reference):
    projection = next(p for p in structure.text_projections if p.projection_id == reference.raw_text.projection_id)
    span = reference.raw_text.normalized_range
    return projection.normalized_text[span.start : span.end]


def structural_signature(structure):
    """Exclude allocated identities and receipt bindings, retain observed structure."""
    wire = structure.model_dump(mode="json", by_alias=True)
    identities = {}
    for role, rows, field in (
        ("projection", wire["textProjections"], "projectionId"),
        ("node", wire["nodes"], "nodeId"),
        ("reference", wire["references"], "referenceId"),
        ("citation", wire["citations"], "citationId"),
    ):
        for index, row in enumerate(rows):
            identities[row[field]] = f"{role}:{index}"

    def detached(value):
        if isinstance(value, str):
            return identities.get(value, value)
        if isinstance(value, list):
            return [detached(item) for item in value]
        if isinstance(value, dict):
            return {key: detached(item) for key, item in value.items()}
        return value

    wire.pop("binding")
    wire.pop("rawArtifacts")
    return detached(wire)


def node_features(signature):
    result = {
        row["nodeId"]: {key: value for key, value in row.items() if key not in {"nodeId", "order", "locator"}}
        for row in signature["nodes"]
    }
    for field in ("references", "citations", "tables", "figures"):
        for row in signature[field]:
            result[row["nodeId"]].setdefault(field, []).append(row)
    return result


def admit_structures(*structures, cancelled=lambda: False):
    """Count retained collections and strings before any detached copy.

    The span budget bounds repeated copies of overlapping node/reference text;
    source completeness is not inferred from these representation limits.
    """
    deadline = time.monotonic() + MAX_REPROCESSING_SECONDS
    items = text = span_text = 0

    def visit(value):
        nonlocal items, text, span_text
        if cancelled() or time.monotonic() > deadline:
            raise DocumentRevisionProblem("document-reprocessing-limit")
        if isinstance(value, IRValue):
            items += 1
            if isinstance(value, TextSpan):
                span_text += value.normalized_range.end - value.normalized_range.start
            if items > MAX_REPROCESSING_ITEMS or span_text > MAX_REPROCESSING_TEXT:
                raise DocumentRevisionProblem("document-reprocessing-limit")
            for field in value.__dict__.values():
                visit(field)
        elif isinstance(value, (tuple, list)):
            items += len(value)
            if items > MAX_REPROCESSING_ITEMS:
                raise DocumentRevisionProblem("document-reprocessing-limit")
            for field in value:
                visit(field)
        elif isinstance(value, str):
            text += len(value)
            if text > MAX_REPROCESSING_TEXT:
                raise DocumentRevisionProblem("document-reprocessing-limit")

    for structure in structures:
        visit(structure)


def compare_structures(old: CanonicalDocumentStructure, new: CanonicalDocumentStructure, *, cancelled=lambda: False):
    """Hash/block first; duplicate matches remain advisory ambiguity."""
    deadline = time.monotonic() + MAX_REPROCESSING_SECONDS

    def check():
        if cancelled() or time.monotonic() > deadline:
            raise DocumentRevisionProblem("document-reprocessing-limit")

    admit_structures(old, new, cancelled=cancelled)
    old_signature, new_signature = structural_signature(old), structural_signature(new)
    identical = old_signature == new_signature
    old_features, new_features = node_features(old_signature), node_features(new_signature)
    groups: dict[tuple[str, str], list[CanonicalNode]] = {}
    new_text = {}
    for node in new.nodes:
        check()
        text = node_text(new, node)
        new_text[node.node_id] = text
        groups.setdefault((node.kind, hashlib.sha256(text.encode()).hexdigest()), []).append(node)
    old_keys = Counter((n.kind, hashlib.sha256(node_text(old, n).encode()).hexdigest()) for n in old.nodes)
    differences: list[ReprocessingDifference] = []
    used = set()
    for index, node in enumerate(old.nodes):
        check()
        text = node_text(old, node)
        key = (node.kind, hashlib.sha256(text.encode()).hexdigest())
        matches = groups.get(key, [])
        target = None
        state: DifferenceState
        if identical:
            target = new.nodes[len(differences)]
            state = "unchanged"
        elif len(matches) == old_keys[key] == 1:
            target = matches[0]
            target_index = target.order
            if old_features[f"node:{index}"] != new_features[f"node:{target_index}"]:
                state = "modified"
            else:
                state = "unchanged" if (node.order, node.locator) == (target.order, target.locator) else "moved"
        elif matches:
            state = "ambiguous"
        else:
            positional = [
                n for n in new.nodes if n.kind == node.kind and n.order == node.order and n.node_id not in used
            ]
            if len(positional) == 1:
                target, state = positional[0], "modified"
            else:
                state = "removed"
        if target is not None:
            used.add(target.node_id)
        differences.append(
            ReprocessingDifference(
                kind="node",
                old_id=node.node_id,
                new_id=None if target is None else target.node_id,
                state=state,
                old_preview=text[:160],
                new_preview=None if target is None else new_text[target.node_id][:160],
                old_locator=node.locator,
                new_locator=None if target is None else target.locator,
            )
        )
    for node in new.nodes:
        if node.node_id not in used:
            differences.append(
                ReprocessingDifference(
                    kind="node",
                    old_id=None,
                    new_id=node.node_id,
                    state="added",
                    old_preview=None,
                    new_preview=new_text[node.node_id][:160],
                    old_locator=None,
                    new_locator=node.locator,
                )
            )
    refs: dict[str, list[CanonicalReference]] = {}
    for ref in new.references:
        refs.setdefault(reference_text(new, ref), []).append(ref)
    old_refs = Counter(reference_text(old, r) for r in old.references)
    used_refs = set()
    for index, ref in enumerate(old.references):
        check()
        text = reference_text(old, ref)
        reference_matches = refs.get(text, [])
        reference_target = (
            new.references[index]
            if identical
            else reference_matches[0]
            if len(reference_matches) == old_refs[text] == 1
            else None
        )
        if reference_target is not None:
            used_refs.add(reference_target.reference_id)
        differences.append(
            ReprocessingDifference(
                kind="reference",
                old_id=ref.reference_id,
                new_id=None if reference_target is None else reference_target.reference_id,
                state="ambiguous"
                if reference_matches and reference_target is None
                else "removed"
                if reference_target is None
                else "unchanged"
                if ref.identifiers == reference_target.identifiers and ref.order == reference_target.order
                else "modified",
                old_preview=text[:160],
                new_preview=None if reference_target is None else reference_text(new, reference_target)[:160],
                old_locator=None,
                new_locator=None,
            )
        )
    for ref in new.references:
        if ref.reference_id not in used_refs:
            differences.append(
                ReprocessingDifference(
                    kind="reference",
                    old_id=None,
                    new_id=ref.reference_id,
                    state="added",
                    old_preview=None,
                    new_preview=reference_text(new, ref)[:160],
                    old_locator=None,
                    new_locator=None,
                )
            )
    check()
    return tuple(differences)


def anchor_candidates(
    anchor_id: str,
    target: SourceAnchorTarget,
    candidate: CorrectionPreviewBase,
    *,
    old_locator: SourceLocator | None = None,
    cancelled: Callable[[], bool] = lambda: False,
):
    """Unique exact quote with context only; never moves an accepted anchor."""
    admit_structures(candidate.structure, cancelled=cancelled)
    deadline = time.monotonic() + MAX_REPROCESSING_SECONDS
    matches: dict[tuple[str, int], CanonicalNode] = {}
    if target.quote is None:
        return ReprocessingDifference(
            kind="anchor",
            old_id=anchor_id,
            new_id=None,
            state="unresolvable",
            old_preview=None,
            new_preview=None,
            old_locator=old_locator,
            new_locator=None,
        )
    for node in candidate.structure.nodes:
        if cancelled() or time.monotonic() > deadline:
            raise DocumentRevisionProblem("document-reprocessing-limit")
        if node.text is None:
            continue
        text = node_text(candidate.structure, node)
        at = text.find(target.quote.exact)
        while at >= 0:
            end = at + len(target.quote.exact)
            if (
                text[max(0, at - len(target.quote.prefix)) : at] == target.quote.prefix
                and text[end : end + len(target.quote.suffix)] == target.quote.suffix
            ):
                position = (node.text.projection_id, node.text.normalized_range.start + at)
                previous = matches.get(position)
                if (
                    previous is None
                    or previous.text is None
                    or len(text) < (previous.text.normalized_range.end - previous.text.normalized_range.start)
                ):
                    matches[position] = node
                if len(matches) > 1:
                    break
            at = text.find(target.quote.exact, at + 1)
        if len(matches) > 1:
            break
    chosen = next(iter(matches.values())) if len(matches) == 1 else None
    state: DifferenceState = (
        "ambiguous"
        if len(matches) > 1
        else "unresolvable"
        if chosen is None
        else "unchanged"
        if chosen.locator == old_locator
        else "moved"
    )
    return ReprocessingDifference(
        kind="anchor",
        old_id=anchor_id,
        new_id=None if chosen is None else chosen.node_id,
        state=state,
        old_preview=target.quote.exact[:160],
        new_preview=None if chosen is None else target.quote.exact[:160],
        old_locator=old_locator,
        new_locator=None if chosen is None else chosen.locator,
    )
