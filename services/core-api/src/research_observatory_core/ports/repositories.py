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


class RepositoryProblem(RuntimeError):
    """Bounded repository failure that does not disclose canonical content."""

    code = "RO-CORE-REPOSITORY-FAILED"

    def __init__(self, message: str = "canonical repository operation failed") -> None:
        super().__init__(message)


class RepositoryNotFound(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-NOT-FOUND"


class RepositoryConflict(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-CONFLICT"


class RepositoryTransactionFailed(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-TRANSACTION-FAILED"


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
    object_sha256: str | None = None


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


@runtime_checkable
class AggregateRepository(Protocol):
    def get(self, aggregate_id: str) -> AggregateRevision: ...

    def append(
        self,
        draft: AggregateRevisionDraft,
        event: AtomicRepositoryEvent,
        *,
        expected_revision: int | None,
    ) -> AggregateRevision: ...


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
    "ActorType",
    "AggregateKind",
    "AggregateRepository",
    "AggregateRevision",
    "AggregateRevisionDraft",
    "AtomicRepositoryEvent",
    "KnowledgeStatus",
    "PrivacyAuditEvent",
    "PrivacyPolicyRecord",
    "PrivacyPolicyRepository",
    "PrivacySetting",
    "RepositoryConflict",
    "RepositoryNotFound",
    "RepositoryProblem",
    "RepositoryTransactionFailed",
    "RightsStatus",
    "UnitOfWork",
    "UnitOfWorkFactory",
]
