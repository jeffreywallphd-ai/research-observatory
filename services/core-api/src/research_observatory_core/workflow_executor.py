"""Portable workflow submission preparation and the bounded local worker supervisor."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.workflow_executor import (
    ConcurrencyClass,
    WorkflowActor,
    WorkflowArtifactRole,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowJobSubmission,
    WorkflowLeaseRejected,
    WorkflowOutputReference,
    WorkflowQueueRepository,
)
from .workflow_contracts import (
    canonical_workflow_json,
    workflow_definition_errors,
    workflow_record_sha256,
    workflow_snapshot_errors,
)

_STABLE_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
_CONCURRENCY_CLASSES = frozenset({"interactive", "document", "ai", "maintenance"})


class WorkflowPreparationProblem(ValueError):
    """The untrusted workflow authority cannot be admitted to local execution."""


class WorkflowActivityError(RuntimeError):
    """A bounded activity failure classified by its portable error code."""

    def __init__(self, error_code: str) -> None:
        if not _stable_code(error_code):
            raise ValueError("activity error code is invalid")
        super().__init__(error_code)
        self.error_code = error_code


class WorkflowCancellationRequested(RuntimeError):
    """Cooperative activity cancellation reached a safe point."""


def _stable_code(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 96 and _STABLE_CODE.fullmatch(value) is not None


def _utc_millisecond(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value):
        raise WorkflowPreparationProblem("workflow timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WorkflowPreparationProblem("workflow timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise WorkflowPreparationProblem("workflow timestamp is invalid")
    return value


def prepare_workflow_job(
    definition_value: object,
    snapshot_value: object,
    *,
    job_id: str,
    concurrency_class: ConcurrencyClass,
    priority: int,
    available_at: str,
) -> WorkflowJobSubmission:
    """Validate exact T01 authority and derive one local queue admission record."""

    definition_errors = workflow_definition_errors(definition_value)
    snapshot_errors = workflow_snapshot_errors(definition_value, snapshot_value)
    if definition_errors or snapshot_errors:
        raise WorkflowPreparationProblem("workflow authority is invalid")
    definition = cast(Mapping[str, object], definition_value)
    snapshot = cast(Mapping[str, object], snapshot_value)
    if snapshot.get("executor") is None or cast(Mapping[str, object], snapshot["executor"]).get("profile") != "local":
        raise WorkflowPreparationProblem("workflow executor profile is not local")
    if not is_uuid_v7(job_id) or concurrency_class not in _CONCURRENCY_CLASSES:
        raise WorkflowPreparationProblem("workflow queue identity or concurrency class is invalid")
    if not isinstance(priority, int) or isinstance(priority, bool) or not -1_000 <= priority <= 1_000:
        raise WorkflowPreparationProblem("workflow priority is invalid")
    available_at = _utc_millisecond(available_at)

    jobs = [cast(Mapping[str, object], item) for item in cast(tuple[object, ...] | list[object], snapshot["jobs"])]
    matching_jobs = [item for item in jobs if item.get("jobId") == job_id]
    if len(matching_jobs) != 1 or matching_jobs[0].get("state") not in {"runnable", "retry-scheduled"}:
        raise WorkflowPreparationProblem("workflow job is not runnable")
    job = matching_jobs[0]
    step_run_id = cast(str, job["stepRunId"])
    step_runs = [
        cast(Mapping[str, object], item)
        for item in cast(tuple[object, ...] | list[object], snapshot["stepRuns"])
        if cast(Mapping[str, object], item).get("stepRunId") == step_run_id
    ]
    if len(step_runs) != 1:
        raise WorkflowPreparationProblem("workflow job step authority is invalid")
    step_key = step_runs[0].get("stepKey")
    steps = [
        cast(Mapping[str, object], item)
        for item in cast(tuple[object, ...] | list[object], definition["steps"])
        if cast(Mapping[str, object], item).get("stepKey") == step_key
    ]
    if len(steps) != 1 or steps[0].get("kind") != "activity" or not _stable_code(steps[0].get("activityType")):
        raise WorkflowPreparationProblem("workflow job activity authority is invalid")
    retry = cast(Mapping[str, object], steps[0]["retryPolicy"])
    progress = cast(Mapping[str, object], steps[0]["progress"])
    checkpoint_policy = cast(Mapping[str, object], steps[0]["checkpointPolicy"])
    cancellation_policy = cast(Mapping[str, object], steps[0]["cancellationPolicy"])
    jitter = retry["jitter"] == "deterministic"
    definition_json = canonical_workflow_json(definition_value)
    snapshot_json = canonical_workflow_json(snapshot_value)
    return WorkflowJobSubmission(
        project_id=cast(str, snapshot["projectId"]),
        workflow_run_id=cast(str, snapshot["workflowRunId"]),
        snapshot_id=cast(str, snapshot["snapshotId"]),
        snapshot_revision=cast(int, snapshot["snapshotRevision"]),
        definition_revision_id=cast(str, definition["definitionRevisionId"]),
        job_id=job_id,
        step_run_id=step_run_id,
        activity_type=cast(str, steps[0]["activityType"]),
        concurrency_class=concurrency_class,
        progress_unit=cast(str, progress["unit"]),
        progress_total_kind=cast(Any, progress["totalKind"]),
        progress_total_units=cast(int | None, progress["totalUnits"]),
        checkpoint_mode=cast(Any, checkpoint_policy["mode"]),
        partial_artifact_disposition=cast(Any, cancellation_policy["partialArtifactDisposition"]),
        priority=priority,
        available_at=available_at,
        max_attempts=cast(int, retry["maxAttempts"]),
        initial_backoff_ms=cast(int, retry["initialBackoffMs"]),
        maximum_backoff_ms=cast(int, retry["maximumBackoffMs"]),
        multiplier_basis_points=cast(int, retry["multiplierBasisPoints"]),
        deterministic_jitter=jitter,
        retryable_error_codes=tuple(cast(list[str] | tuple[str, ...], retry["retryableErrorCodes"])),
        non_retryable_error_codes=tuple(cast(list[str] | tuple[str, ...], retry["nonRetryableErrorCodes"])),
        idempotency_key=cast(str, job["idempotencyKey"]),
        command_fingerprint=cast(str, job["commandFingerprint"]),
        definition_json=definition_json,
        snapshot_json=snapshot_json,
        definition_record_sha256=workflow_record_sha256(json.loads(definition_json)),
        snapshot_record_sha256=workflow_record_sha256(json.loads(snapshot_json)),
    )


class WorkflowActivity(Protocol):
    def __call__(
        self,
        context: WorkflowActivityContext,
        claim: WorkflowJobClaim,
    ) -> tuple[WorkflowOutputReference, ...]: ...


@dataclass(slots=True)
class WorkflowActivityContext:
    """Capability-limited activity context; it exposes no database handle or key."""

    repository: WorkflowQueueRepository
    claim: WorkflowJobClaim
    now: Callable[[], str]
    lease_duration_ms: int

    def heartbeat(self, progress: Mapping[str, object]) -> None:
        self.claim = self.repository.heartbeat(
            self.claim,
            now=self.now(),
            lease_duration_ms=self.lease_duration_ms,
            progress=progress,
        )

    def checkpoint(
        self,
        *,
        checkpoint_id: str,
        artifact: WorkflowOutputReference,
        progress: Mapping[str, object],
    ) -> None:
        self.stage_artifact(artifact, role="checkpoint")
        self.repository.checkpoint(
            self.claim,
            checkpoint_id=checkpoint_id,
            state_hash=artifact.content_hash,
            payload_artifact_id=artifact.artifact_id,
            now=self.now(),
            progress=progress,
        )

    def stage_artifact(
        self,
        artifact: WorkflowOutputReference,
        *,
        role: WorkflowArtifactRole = "output",
    ) -> None:
        self.repository.stage_artifact(
            self.claim,
            artifact=artifact,
            role=role,
            now=self.now(),
        )

    def cancellation_safe_point(self) -> None:
        if self.repository.cancellation_requested(self.claim, now=self.now()):
            raise WorkflowCancellationRequested("workflow cancellation reached a safe point")


class LocalWorkerSupervisor:
    """Bounded local activity supervisor with class admission and no long database transaction."""

    def __init__(
        self,
        repository: WorkflowQueueRepository,
        handlers: Mapping[str, WorkflowActivity],
        *,
        concurrency_limits: Mapping[ConcurrencyClass, int],
        now: Callable[[], str],
        recovery_actor: WorkflowActor,
        worker_id_factory: Callable[[], str] = new_uuid_v7,
        lease_duration_ms: int = 30_000,
        recovery_batch_size: int = 100,
    ) -> None:
        if (
            not handlers
            or not concurrency_limits
            or any(kind not in _CONCURRENCY_CLASSES for kind in concurrency_limits)
            or any(
                not isinstance(limit, int) or isinstance(limit, bool) or limit < 0
                for limit in concurrency_limits.values()
            )
            or not 1_000 <= lease_duration_ms <= 3_600_000
            or not isinstance(recovery_batch_size, int)
            or isinstance(recovery_batch_size, bool)
            or not 1 <= recovery_batch_size <= 1_000
        ):
            raise ValueError("worker supervisor configuration is invalid")
        self._repository = repository
        self._handlers = dict(handlers)
        self._limits = dict(concurrency_limits)
        self._now = now
        self._recovery_actor = recovery_actor
        self._worker_id_factory = worker_id_factory
        self._lease_duration_ms = lease_duration_ms
        self._recovery_batch_size = recovery_batch_size

    def _execute(self, claim: WorkflowJobClaim) -> WorkflowJobRecord:
        context = WorkflowActivityContext(self._repository, claim, self._now, self._lease_duration_ms)
        try:
            self._repository.start(claim, now=self._now())
            context.cancellation_safe_point()
            handler = self._handlers.get(claim.activity_type)
            if handler is None:
                raise WorkflowActivityError("activity-unregistered")
            outputs = handler(context, claim)
            for output in outputs:
                context.stage_artifact(output)
            context.cancellation_safe_point()
            self._repository.complete(context.claim, now=self._now(), outputs=outputs)
        except WorkflowCancellationRequested:
            self._converge_cancellation(context.claim)
        except WorkflowActivityError as error:
            self._converge_failure(context.claim, error.error_code)
        except Exception:
            self._converge_failure(context.claim, "activity-failed")
        return self._repository.get(claim.job_id)

    def _converge_cancellation(self, claim: WorkflowJobClaim) -> None:
        try:
            self._repository.cancel(claim, now=self._now(), reason_code="safe-point")
        except WorkflowLeaseRejected:
            state = self._repository.get(claim.job_id).state
            if state == "cancelling":
                self._repository.cancel(claim, now=self._now(), reason_code="safe-point")
            elif state not in {"cancelled", "failed", "succeeded"}:
                raise

    def _converge_failure(self, claim: WorkflowJobClaim, error_code: str) -> None:
        try:
            self._repository.fail(claim, now=self._now(), error_code=error_code)
        except WorkflowLeaseRejected:
            state = self._repository.get(claim.job_id).state
            if state == "cancelling":
                self._converge_cancellation(claim)
            elif state not in {"cancelled", "failed", "succeeded"}:
                raise

    def run_available(self) -> tuple[WorkflowJobRecord, ...]:
        self._repository.recover_expired(
            now=self._now(),
            actor=self._recovery_actor,
            limit=self._recovery_batch_size,
        )
        claims: list[WorkflowJobClaim] = []
        for concurrency_class, limit in self._limits.items():
            for _ in range(limit):
                worker_id = self._worker_id_factory()
                if not is_uuid_v7(worker_id):
                    raise ValueError("worker identity factory returned an invalid UUIDv7")
                claim = self._repository.claim_next(
                    worker_id=worker_id,
                    concurrency_classes=(concurrency_class,),
                    now=self._now(),
                    lease_duration_ms=self._lease_duration_ms,
                )
                if claim is None:
                    break
                claims.append(claim)
        if not claims:
            return ()
        with ThreadPoolExecutor(max_workers=len(claims), thread_name_prefix="ro-workflow") as pool:
            return tuple(pool.map(self._execute, claims))


__all__ = [
    "LocalWorkerSupervisor",
    "WorkflowActivity",
    "WorkflowActivityContext",
    "WorkflowActivityError",
    "WorkflowCancellationRequested",
    "WorkflowPreparationProblem",
    "prepare_workflow_job",
]
