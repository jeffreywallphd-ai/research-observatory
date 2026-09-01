"""Dependency-neutral local workflow queue and activity execution ports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

ConcurrencyClass = Literal["interactive", "document", "ai", "maintenance"]
WorkflowArtifactRole = Literal["output", "checkpoint", "diagnostic"]
WorkflowArtifactDisposition = Literal["committed", "retained-incomplete", "quarantined", "discarded"]
WorkflowJobState = Literal[
    "runnable",
    "claimed",
    "running",
    "retry-scheduled",
    "cancelling",
    "cancelled",
    "failed",
    "succeeded",
]
WorkflowActorType = Literal["human", "system", "workload"]
WorkflowInterruptionKind = Literal["ordinary-restart", "user-cancel", "security-lock", "policy", "dependency"]


class WorkflowQueueProblem(RuntimeError):
    """Bounded local workflow failure without research content or lease disclosure."""

    code = "RO-WORKFLOW-QUEUE-FAILED"


class WorkflowQueueNotFound(WorkflowQueueProblem):
    code = "RO-WORKFLOW-QUEUE-NOT-FOUND"


class WorkflowQueueConflict(WorkflowQueueProblem):
    code = "RO-WORKFLOW-QUEUE-CONFLICT"


class WorkflowLeaseRejected(WorkflowQueueConflict):
    code = "RO-WORKFLOW-LEASE-REJECTED"


class WorkflowQueueCorrupt(WorkflowQueueProblem):
    code = "RO-WORKFLOW-QUEUE-CORRUPT"


@dataclass(frozen=True, slots=True)
class WorkflowActor:
    actor_id: str
    actor_type: WorkflowActorType
    role: str


@dataclass(frozen=True, slots=True)
class WorkflowJobSubmission:
    project_id: str
    workflow_run_id: str
    snapshot_id: str
    snapshot_revision: int
    definition_revision_id: str
    job_id: str
    step_run_id: str
    activity_type: str
    concurrency_class: ConcurrencyClass
    progress_unit: str
    progress_total_kind: Literal["known", "unknown", "not-applicable"]
    progress_total_units: int | None
    checkpoint_mode: Literal["forbidden", "optional", "required"]
    partial_artifact_disposition: Literal["retained-incomplete", "quarantined", "discarded"]
    priority: int
    available_at: str
    max_attempts: int
    initial_backoff_ms: int
    maximum_backoff_ms: int
    multiplier_basis_points: int
    deterministic_jitter: bool
    retryable_error_codes: tuple[str, ...]
    non_retryable_error_codes: tuple[str, ...]
    idempotency_key: str
    command_fingerprint: str
    definition_json: str
    snapshot_json: str
    definition_record_sha256: str
    snapshot_record_sha256: str


@dataclass(frozen=True, slots=True)
class WorkflowJobAuthority:
    definition_json: str
    snapshot_json: str
    definition_record_sha256: str
    snapshot_record_sha256: str


@dataclass(frozen=True, slots=True)
class WorkflowJobRecord:
    job_id: str
    workflow_run_id: str
    state: WorkflowJobState
    concurrency_class: ConcurrencyClass
    priority: int
    available_at: str
    attempt_count: int
    max_attempts: int
    current_attempt_id: str | None
    lease_generation: int
    cancellation_requested_at: str | None
    interruption_kind: WorkflowInterruptionKind | None
    diagnostic_code: str | None
    committed_output_sha256: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class WorkflowJobClaim:
    project_id: str
    workflow_run_id: str
    job_id: str
    step_run_id: str
    activity_type: str
    concurrency_class: ConcurrencyClass
    attempt_id: str
    attempt_number: int
    worker_id: str
    lease_token: str
    lease_generation: int
    lease_expires_at: str
    idempotency_key: str
    command_fingerprint: str
    latest_checkpoint: WorkflowCheckpointRecord | None


@dataclass(frozen=True, slots=True)
class WorkflowCheckpointRecord:
    checkpoint_id: str
    attempt_id: str
    checkpoint_sequence: int
    history_sequence: int
    created_at: str
    state_hash: str
    payload_artifact_id: str
    payload: WorkflowArtifactRecord


@dataclass(frozen=True, slots=True)
class WorkflowOutputReference:
    artifact_id: str
    revision_id: str
    content_hash: str
    media_type: str
    provenance_entity_id: str | None


@dataclass(frozen=True, slots=True)
class WorkflowCompletionReceipt:
    job_id: str
    attempt_id: str
    output_record_sha256: str
    committed_at: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class WorkflowArtifactRecord:
    attempt_id: str
    job_id: str
    artifact_id: str
    revision_id: str
    role: WorkflowArtifactRole
    disposition: WorkflowArtifactDisposition
    content_hash: str
    media_type: str
    provenance_entity_id: str | None


@runtime_checkable
class WorkflowQueueRepository(Protocol):
    def enqueue(self, submission: WorkflowJobSubmission, *, actor: WorkflowActor) -> WorkflowJobRecord: ...

    def get(self, job_id: str) -> WorkflowJobRecord: ...

    def authority(self, job_id: str) -> WorkflowJobAuthority: ...

    def claim_next(
        self,
        *,
        worker_id: str,
        concurrency_classes: tuple[ConcurrencyClass, ...],
        now: str,
        lease_duration_ms: int,
    ) -> WorkflowJobClaim | None: ...

    def start(self, claim: WorkflowJobClaim, *, now: str) -> WorkflowJobRecord: ...

    def heartbeat(
        self,
        claim: WorkflowJobClaim,
        *,
        now: str,
        lease_duration_ms: int,
        progress: Mapping[str, object],
    ) -> WorkflowJobClaim: ...

    def checkpoint(
        self,
        claim: WorkflowJobClaim,
        *,
        checkpoint_id: str,
        state_hash: str,
        payload_artifact_id: str,
        now: str,
        progress: Mapping[str, object],
    ) -> WorkflowCheckpointRecord: ...

    def stage_artifact(
        self,
        claim: WorkflowJobClaim,
        *,
        artifact: WorkflowOutputReference,
        role: WorkflowArtifactRole,
        now: str,
    ) -> WorkflowArtifactRecord: ...

    def request_cancellation(
        self,
        job_id: str,
        *,
        actor: WorkflowActor,
        now: str,
        reason_code: str,
        interruption_kind: WorkflowInterruptionKind,
    ) -> WorkflowJobRecord: ...

    def cancellation_requested(self, claim: WorkflowJobClaim, *, now: str) -> bool: ...

    def complete(
        self,
        claim: WorkflowJobClaim,
        *,
        now: str,
        outputs: tuple[WorkflowOutputReference, ...],
    ) -> WorkflowCompletionReceipt: ...

    def fail(self, claim: WorkflowJobClaim, *, now: str, error_code: str) -> WorkflowJobRecord: ...

    def cancel(self, claim: WorkflowJobClaim, *, now: str, reason_code: str) -> WorkflowJobRecord: ...

    def recover_expired(self, *, now: str, actor: WorkflowActor, limit: int = 100) -> int: ...


__all__ = [
    "ConcurrencyClass",
    "WorkflowActor",
    "WorkflowActorType",
    "WorkflowArtifactDisposition",
    "WorkflowArtifactRecord",
    "WorkflowArtifactRole",
    "WorkflowCheckpointRecord",
    "WorkflowCompletionReceipt",
    "WorkflowInterruptionKind",
    "WorkflowJobAuthority",
    "WorkflowJobClaim",
    "WorkflowJobRecord",
    "WorkflowJobState",
    "WorkflowJobSubmission",
    "WorkflowLeaseRejected",
    "WorkflowOutputReference",
    "WorkflowQueueConflict",
    "WorkflowQueueCorrupt",
    "WorkflowQueueNotFound",
    "WorkflowQueueProblem",
    "WorkflowQueueRepository",
]
