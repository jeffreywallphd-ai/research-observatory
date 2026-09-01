"""Dependency-neutral canonical repository and unit-of-work ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

AggregateKind = Literal["record", "document", "workflow", "evidence", "ontology", "decision"]
KnowledgeStatus = Literal[
    "observed",
    "extracted",
    "inferred",
    "verified",
    "disputed",
    "adjudicated",
    "stale",
    "unknown",
    "not-reported",
    "not-applicable",
    "ambiguous",
    "unavailable",
]
RightsStatus = Literal["allowed", "denied", "unknown", "not-applicable"]
ActorType = Literal["human", "system", "worker", "model"]
LineageDirection = Literal["ancestors", "descendants"]
DependencyCoverage = Literal["not-applicable", "complete", "legacy-unreported"]
DependencyKind = Literal[
    "source-revision",
    "evidence-record",
    "ontology-version",
    "prompt-version",
    "model-version",
    "parameter-set",
    "schema-version",
    "template-version",
    "code-version",
    "human-decision",
]
DependencyRelationType = Literal["direct", "conditional", "non-material"]
StalenessReason = Literal[
    "SOURCE_VERSION",
    "RIGHTS_POLICY",
    "SCHEMA_VERSION",
    "MODEL_OR_PROMPT",
    "ONTOLOGY_MAPPING",
    "HUMAN_DECISION",
]
DependencyImpactDisposition = Literal["stale", "unknown-impact", "informational"]
ConditionalDependencyDisposition = Literal["propagate", "ignore"]
DependencyPropagationState = Literal["running", "completed", "cancelled"]


class RepositoryProblem(RuntimeError):
    """Bounded repository failure that does not disclose canonical content."""

    code = "RO-CORE-REPOSITORY-FAILED"

    def __init__(self, message: str = "canonical repository operation failed") -> None:
        super().__init__(message)


class RepositoryNotFound(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-NOT-FOUND"


class RepositoryConflict(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-CONFLICT"


class RepositoryIdempotencyConflict(RepositoryConflict):
    code = "RO-CORE-REPOSITORY-IDEMPOTENCY-CONFLICT"


class RepositoryTransactionFailed(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-TRANSACTION-FAILED"


class DependencyRegistrationRequired(RepositoryProblem):
    code = "RO-CORE-DEPENDENCY-REGISTRATION-REQUIRED"


class DependencyImpactLimitExceeded(RepositoryProblem):
    code = "RO-CORE-DEPENDENCY-IMPACT-LIMIT"


@dataclass(frozen=True, slots=True)
class AggregateRevision:
    """Detached domain projection returned across the persistence boundary."""

    revision_id: str
    aggregate_id: str
    aggregate_kind: AggregateKind
    project_id: str
    revision: int
    contract_version: str
    created_at: str
    modified_at: str
    display_label_observed: str
    display_label_normalized: str | None
    knowledge_status: KnowledgeStatus
    rights_status: RightsStatus
    object_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class AggregateRevisionDraft:
    """Caller-owned values for one immutable aggregate revision."""

    revision_id: str
    aggregate_id: str
    aggregate_kind: AggregateKind
    created_at: str
    modified_at: str
    display_label_observed: str
    display_label_normalized: str | None
    knowledge_status: KnowledgeStatus
    rights_status: RightsStatus
    dependency_coverage: DependencyCoverage
    object_sha256: str | None = None
    provenance_inputs: tuple[AggregateRevision, ...] = ()
    material_dependencies: tuple[MaterialDependency, ...] = ()


@dataclass(frozen=True, slots=True)
class MaterialDependency:
    """One direct typed input to an exact recalculable output revision."""

    dependency_id: str
    dependency_kind: DependencyKind
    relation_type: DependencyRelationType
    revision_id: str | None
    configuration_id: str | None
    configuration_version: str | None
    fingerprint: str
    governing_policy_id: str
    governing_policy_version: str


@dataclass(frozen=True, slots=True)
class MaterialDependencyRegistration:
    """Detached dependency coverage and edges for one exact output revision."""

    output_revision_id: str
    output_aggregate_id: str
    output_kind: AggregateKind
    project_id: str
    coverage: DependencyCoverage
    registration_event_id: str | None
    registered_at: str | None
    dependencies: tuple[MaterialDependency, ...]


@dataclass(frozen=True, slots=True)
class DependencyAuditDiagnostic:
    """Content-free durable diagnostic for a denied dependency-sensitive action."""

    diagnostic_id: str
    project_id: str
    output_revision_id: str
    workflow_run_id: str
    job_id: str
    attempt_id: str
    diagnostic_code: Literal["dependency-registration-missing"]
    detected_at: str


@dataclass(frozen=True, slots=True)
class DependencyChange:
    """Exact immutable endpoint change whose downstream impact is evaluated."""

    change_id: str
    idempotency_key: str
    reason: StalenessReason
    dependency_kind: DependencyKind
    previous_revision_id: str | None
    replacement_revision_id: str | None
    configuration_id: str | None
    previous_configuration_version: str | None
    replacement_configuration_version: str | None
    previous_fingerprint: str
    replacement_fingerprint: str | None
    propagation_policy_id: str
    propagation_policy_version: str
    actor_id: str
    trace_id: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class ConditionalDependencyDecision:
    """Versioned human or policy disposition for one conditional edge."""

    dependency_id: str
    decision_id: str
    disposition: ConditionalDependencyDisposition
    governing_policy_id: str
    governing_policy_version: str
    actor_id: str
    decided_at: str


@dataclass(frozen=True, slots=True)
class DependencyImpactLimits:
    """Hard resource bounds for one deterministic impact traversal."""

    max_nodes: int = 20_000
    max_edges: int = 100_000
    max_depth: int = 128
    max_path_samples: int = 64
    max_legacy_samples: int = 100


DEFAULT_DEPENDENCY_IMPACT_LIMITS = DependencyImpactLimits()


@dataclass(frozen=True, slots=True)
class DependencyImpactItem:
    output_revision_id: str
    output_kind: AggregateKind
    disposition: DependencyImpactDisposition
    depth: int
    relation_type: DependencyRelationType
    path_revision_ids: tuple[str, ...]
    path_length: int
    path_truncated: bool
    cycle_group_id: str | None
    confidence: Literal["confirmed", "conditional", "unknown"]
    review_required: bool


@dataclass(frozen=True, slots=True)
class DependencyCycleGroup:
    cycle_group_id: str
    member_revision_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DependencyImpactPreview:
    project_id: str
    change_id: str
    graph_sha256: str
    preview_sha256: str
    impacts: tuple[DependencyImpactItem, ...]
    cycle_groups: tuple[DependencyCycleGroup, ...]
    legacy_unreported_count: int
    legacy_unreported_samples: tuple[str, ...]
    visited_nodes: int
    visited_edges: int

    @property
    def affected_output_revision_ids(self) -> tuple[str, ...]:
        return tuple(item.output_revision_id for item in self.impacts if item.disposition != "informational")

    @property
    def informational_output_revision_ids(self) -> tuple[str, ...]:
        return tuple(item.output_revision_id for item in self.impacts if item.disposition == "informational")


@dataclass(frozen=True, slots=True)
class DependencyPropagationRun:
    run_id: str
    project_id: str
    change_id: str
    state: DependencyPropagationState
    total_items: int
    processed_items: int
    stale_count: int
    unknown_count: int
    checkpoint_sha256: str
    preview_sha256: str


@dataclass(frozen=True, slots=True)
class DependencyStaleState:
    cause_id: str
    run_id: str
    change_id: str
    output_revision_id: str
    disposition: Literal["stale", "unknown-impact"]
    reason: StalenessReason
    propagation_policy_id: str
    propagation_policy_version: str
    depth: int
    path_revision_ids: tuple[str, ...]
    path_length: int
    path_truncated: bool
    cycle_group_id: str | None
    confidence: Literal["confirmed", "conditional", "unknown"]
    review_required: bool
    detected_at: str
    resolution_state: Literal["open"]


@dataclass(frozen=True, slots=True)
class DependencyImpactAuditEvent:
    event_id: str
    run_id: str
    sequence: int
    event_type: Literal["started", "checkpoint", "failed-attempt", "completed", "cancelled"]
    processed_items: int
    stale_count: int
    unknown_count: int
    checkpoint_sha256: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class AtomicRepositoryEvent:
    """Provenance and outbox identities committed with a revision."""

    event_id: str
    outbox_id: str
    event_type: str
    occurred_at: str
    available_at: str
    trace_id: str
    actor_type: ActorType
    actor_id: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class PrivacySetting:
    """One detached scalar setting in a complete project privacy revision."""

    key: str
    value: str | int


@dataclass(frozen=True, slots=True)
class PrivacyPolicyRecord:
    """Complete detached privacy revision returned by a persistence adapter."""

    revision: int
    settings: tuple[PrivacySetting, ...]


@dataclass(frozen=True, slots=True)
class PrivacyAuditEvent:
    """Content-free provenance event committed by the privacy adapter."""

    event_id: str
    event_type: str
    occurred_at: str
    trace_id: str
    record_sha256: str


@dataclass(frozen=True, slots=True)
class IntentRevisionRecord:
    """One detached immutable Research Intent revision document."""

    revision: int
    content_json: str


@dataclass(frozen=True, slots=True)
class IntentAuditEvent:
    """Content-free provenance and outbox fact committed with one intent revision."""

    event_id: str
    outbox_id: str
    event_type: str
    occurred_at: str
    trace_id: str
    actor_type: Literal["human"]
    actor_id: str
    record_sha256: str
    command_sha256: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class IntentPolicyDecisionRecord:
    """One content-free, governing-reference-bound policy decision."""

    decision_id: str
    content_json: str


@dataclass(frozen=True, slots=True)
class IntentPolicyAuditEvent:
    """Provenance fact committed with one content-free policy decision."""

    event_id: str
    occurred_at: str
    trace_id: str
    actor_type: Literal["human"]
    actor_id: str
    record_sha256: str


@dataclass(frozen=True, slots=True)
class LineageNode:
    """Content-free production context for one exact immutable revision."""

    fact_id: str
    relation_type: Literal[
        "used", "wasGeneratedBy", "wasAssociatedWith", "wasDerivedFrom", "wasInvalidatedBy", "wasAttributedTo"
    ]
    entity_direction: Literal["input", "output"]
    revision_id: str
    entity_id: str
    entity_kind: str
    related_revision_id: str | None
    knowledge_status: KnowledgeStatus
    rights_status: RightsStatus
    depth: int
    event_id: str
    event_type: str
    activity_id: str
    activity_type: str
    activity_status: Literal["succeeded", "failed", "cancelled", "denied"]
    configuration_id: str
    configuration_version: str
    configuration_hash: str
    agent_id: str
    agent_type: Literal["human", "model", "software", "system"]
    agent_role: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class LineagePage:
    """Bounded, integrity-labelled traversal result returned by persistence."""

    revision_id: str
    direction: LineageDirection
    items: tuple[LineageNode, ...]
    missing_revision_ids: tuple[str, ...]
    next_cursor: int | None
    truncated: bool
    truncation_reason: Literal["cursor-limit", "scan-limit"] | None
    integrity_state: Literal["verified", "integrity-review"]
    legacy_event_count: int
    export_allowed: bool
    export_denial_reason: Literal["integrity-review", "rights-restricted"] | None


@runtime_checkable
class AggregateRepository(Protocol):
    def get(self, aggregate_id: str) -> AggregateRevision: ...

    def get_revision(self, revision_id: str) -> AggregateRevision: ...

    def history(self, aggregate_id: str, *, limit: int = 100) -> tuple[AggregateRevision, ...]: ...

    def append(
        self,
        draft: AggregateRevisionDraft,
        event: AtomicRepositoryEvent,
        *,
        expected_revision: int | None,
    ) -> AggregateRevision: ...

    def invalidate(self, revision_id: str, event: AtomicRepositoryEvent) -> None: ...


@runtime_checkable
class PrivacyPolicyRepository(Protocol):
    def read(self) -> PrivacyPolicyRecord | None: ...

    def append(
        self,
        *,
        expected_revision: int,
        revision: int,
        settings: tuple[PrivacySetting, ...],
        event: PrivacyAuditEvent,
    ) -> None: ...

    def append_event(self, event: PrivacyAuditEvent) -> None: ...


@runtime_checkable
class IntentRevisionRepository(Protocol):
    def read(self) -> tuple[IntentRevisionRecord, ...]: ...

    def replay(
        self,
        *,
        manifest_project_id: str,
        actor_id: str,
        idempotency_key: str,
        command_sha256: str,
        event_type: str = "intent.draft.saved",
    ) -> IntentRevisionRecord | None: ...

    def append(
        self,
        *,
        expected_revision: int,
        domain_project_id: str,
        manifest_project_id: str,
        record: IntentRevisionRecord,
        event: IntentAuditEvent,
    ) -> IntentRevisionRecord: ...

    def append_policy_decision(
        self,
        *,
        record: IntentPolicyDecisionRecord,
        event: IntentPolicyAuditEvent,
    ) -> None: ...


@runtime_checkable
class ProvenanceLedgerRepository(Protocol):
    def lineage(
        self,
        *,
        revision_id: str,
        direction: LineageDirection,
        cursor: int,
        page_size: int,
        max_depth: int,
    ) -> LineagePage: ...


@runtime_checkable
class MaterialDependencyRepository(Protocol):
    def registration(self, output_revision_id: str) -> MaterialDependencyRegistration: ...

    def diagnostics(self, *, output_revision_id: str | None = None) -> tuple[DependencyAuditDiagnostic, ...]: ...


@runtime_checkable
class DependencyImpactRepository(Protocol):
    def preview(
        self,
        change: DependencyChange,
        *,
        decisions: tuple[ConditionalDependencyDecision, ...] = (),
        limits: DependencyImpactLimits = DEFAULT_DEPENDENCY_IMPACT_LIMITS,
    ) -> DependencyImpactPreview: ...

    def begin(
        self,
        change: DependencyChange,
        *,
        preview_sha256: str,
        run_id: str,
        batch_size: int,
        decisions: tuple[ConditionalDependencyDecision, ...] = (),
        limits: DependencyImpactLimits = DEFAULT_DEPENDENCY_IMPACT_LIMITS,
    ) -> DependencyPropagationRun: ...

    def advance(self, run_id: str, *, expected_checkpoint_sha256: str) -> DependencyPropagationRun: ...

    def cancel(
        self,
        run_id: str,
        *,
        expected_checkpoint_sha256: str,
        occurred_at: str,
    ) -> DependencyPropagationRun: ...

    def run(self, run_id: str) -> DependencyPropagationRun: ...

    def change(self, change_id: str) -> DependencyChange: ...

    def decisions(self, run_id: str) -> tuple[ConditionalDependencyDecision, ...]: ...

    def stale_states(self, *, output_revision_id: str | None = None) -> tuple[DependencyStaleState, ...]: ...

    def audit(self, *, run_id: str) -> tuple[DependencyImpactAuditEvent, ...]: ...


@runtime_checkable
class UnitOfWork(Protocol):
    @property
    def aggregates(self) -> AggregateRepository: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


@runtime_checkable
class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


__all__ = [
    "DEFAULT_DEPENDENCY_IMPACT_LIMITS",
    "ActorType",
    "AggregateKind",
    "AggregateRepository",
    "AggregateRevision",
    "AggregateRevisionDraft",
    "AtomicRepositoryEvent",
    "ConditionalDependencyDecision",
    "DependencyAuditDiagnostic",
    "DependencyChange",
    "DependencyCoverage",
    "DependencyCycleGroup",
    "DependencyImpactAuditEvent",
    "DependencyImpactDisposition",
    "DependencyImpactItem",
    "DependencyImpactLimitExceeded",
    "DependencyImpactLimits",
    "DependencyImpactPreview",
    "DependencyImpactRepository",
    "DependencyKind",
    "DependencyPropagationRun",
    "DependencyPropagationState",
    "DependencyRegistrationRequired",
    "DependencyRelationType",
    "DependencyStaleState",
    "IntentAuditEvent",
    "IntentRevisionRecord",
    "IntentRevisionRepository",
    "KnowledgeStatus",
    "LineageDirection",
    "LineageNode",
    "LineagePage",
    "MaterialDependency",
    "MaterialDependencyRegistration",
    "MaterialDependencyRepository",
    "PrivacyAuditEvent",
    "PrivacyPolicyRecord",
    "PrivacyPolicyRepository",
    "PrivacySetting",
    "ProvenanceLedgerRepository",
    "RepositoryConflict",
    "RepositoryIdempotencyConflict",
    "RepositoryNotFound",
    "RepositoryProblem",
    "RepositoryTransactionFailed",
    "RightsStatus",
    "StalenessReason",
    "UnitOfWork",
    "UnitOfWorkFactory",
]
