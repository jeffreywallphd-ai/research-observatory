"""Portable workflow submission preparation and the bounded local worker supervisor."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
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


@dataclass(frozen=True, slots=True)
class WorkerResources:
    """Concurrent upper bounds, not cumulative spend or an OS enforcement limit."""

    cpu_slots: int
    memory_bytes: int
    gpu_bytes: int
    disk_bytes: int

    def values(self) -> tuple[int, int, int, int]:
        return self.cpu_slots, self.memory_bytes, self.gpu_bytes, self.disk_bytes

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 0 for value in self.values()):
            raise ValueError("worker resource amounts must be nonnegative integers")


@dataclass(frozen=True, slots=True)
class WorkerCapacity:
    """Fresh observations: None is unknown; zero is verified zero available capacity."""

    cpu_slots: int | None
    memory_bytes: int | None
    gpu_bytes: int | None
    disk_bytes: int | None

    def values(self) -> tuple[int | None, int | None, int | None, int | None]:
        return self.cpu_slots, self.memory_bytes, self.gpu_bytes, self.disk_bytes


@dataclass(frozen=True, slots=True)
class ProjectWorkerPolicy:
    """Trusted local composition; no job payload can choose its own allowance."""

    project_id: str
    quota: WorkerResources | None
    demands: Mapping[ConcurrencyClass, WorkerResources]
    concurrency_limits: Mapping[ConcurrencyClass, int]

    def __post_init__(self) -> None:
        demands, limits = dict(self.demands), dict(self.concurrency_limits)
        if (
            not is_uuid_v7(self.project_id)
            or (self.quota is not None and not isinstance(self.quota, WorkerResources))
            or any(kind not in _CONCURRENCY_CLASSES for kind in {*demands, *limits})
            or any(type(limit) is not int or limit < 0 for limit in limits.values())
            or any(
                not isinstance(demand, WorkerResources)
                or demand.cpu_slots < 1
                or demand.memory_bytes < 1
                or demand.disk_bytes < 1
                for demand in demands.values()
            )
        ):
            raise ValueError("worker project admission policy is invalid")
        object.__setattr__(self, "demands", MappingProxyType(demands))
        object.__setattr__(self, "concurrency_limits", MappingProxyType(limits))


@dataclass(frozen=True, slots=True)
class LocalWorkerAdmission:
    """Adapter-issued local binding, not a portable contract or untrusted capability.

    The SQLite factory owns identity validation and volume-root composition.
    Trusted Python code must share one controller for one local resource authority.
    """

    repository: WorkflowQueueRepository
    policy: ProjectWorkerPolicy
    controller: LocalAdmissionController
    volume_id: int
    capacity: Callable[[], WorkerCapacity]
    validate_identity: Callable[[WorkflowQueueRepository, ProjectWorkerPolicy, int, LocalAdmissionController], None]

    def validate(self, repository: WorkflowQueueRepository) -> None:
        if repository is not self.repository:
            raise ValueError("worker admission repository identity mismatch")
        self.validate_identity(self.repository, self.policy, self.volume_id, self.controller)
        self.controller.register(self)


@dataclass(frozen=True, slots=True)
class _WorkerReservation:
    project_id: str
    volume_id: int
    concurrency_class: ConcurrencyClass
    demand: WorkerResources


class LocalAdmissionController:
    """One cooperative in-process ledger across project supervisors and calls.

    Reservations precede claims. Shortage is a no-op on durable job history.
    Fresh OS observations can conservatively double-count already resident work;
    they never justify dropping a live reservation. This is not multi-process
    enforcement, and it does not meter cumulative CPU time, tokens or spend.
    """

    def __init__(self, *, interactive_reserve: WorkerResources) -> None:
        if interactive_reserve.cpu_slots < 1 or interactive_reserve.memory_bytes < 1:
            raise ValueError("worker admission requires explicit interactive capacity")
        self._interactive_reserve = interactive_reserve
        self._lock = threading.RLock()
        self._policies: dict[str, tuple[ProjectWorkerPolicy, int]] = {}
        self._reservations: dict[object, _WorkerReservation] = {}

    def register(self, binding: LocalWorkerAdmission) -> None:
        with self._lock:
            if binding.controller is not self:
                raise ValueError("worker admission controller identity mismatch")
            identity = binding.policy.project_id
            registered = (binding.policy, binding.volume_id)
            previous = self._policies.get(identity)
            if previous is not None and previous != registered:
                raise ValueError("worker admission project policy or volume conflict")
            self._policies[identity] = registered

    def reserve(self, binding: LocalWorkerAdmission, kind: ConcurrencyClass, *, local_limit: int) -> object | None:
        with self._lock:
            if binding.controller is not self:
                raise ValueError("worker admission controller identity mismatch")
            binding.validate(binding.repository)
            policy = binding.policy
            demand = policy.demands.get(kind)
            if demand is None or policy.quota is None:
                return None
            reservations = tuple(self._reservations.values())
            project = tuple(row for row in reservations if row.project_id == policy.project_id)
            count = sum(row.concurrency_class == kind for row in project)
            if count >= min(local_limit, policy.concurrency_limits.get(kind, 0)):
                return None
            try:
                capacity = binding.capacity()
                if not isinstance(capacity, WorkerCapacity):
                    return None
                values = capacity.values()
            except Exception:
                return None
            if any(value is not None and (type(value) is not int or value < 0) for value in values):
                return None
            for index, amount in enumerate(demand.values()):
                relevant = tuple(row for row in reservations if index != 3 or row.volume_id == binding.volume_id)
                used = sum(row.demand.values()[index] for row in relevant)
                project_used = sum(row.demand.values()[index] for row in project)
                if project_used + amount > policy.quota.values()[index]:
                    return None
                # Existing interactive work already occupies part of its reserve.
                interactive_used = sum(
                    row.demand.values()[index] for row in relevant if row.concurrency_class == "interactive"
                )
                held = (
                    max(0, self._interactive_reserve.values()[index] - interactive_used) if kind != "interactive" else 0
                )
                available = values[index]
                if amount and (available is None or used + amount + held > available):
                    return None
            token = object()
            self._reservations[token] = _WorkerReservation(policy.project_id, binding.volume_id, kind, demand)
            return token

    def release(self, token: object) -> None:
        with self._lock:
            self._reservations.pop(token, None)


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
        admission: LocalWorkerAdmission | None = None,
    ) -> None:
        if not isinstance(admission, LocalWorkerAdmission):
            raise ValueError("worker supervisor requires explicit resource admission")
        admission.validate(repository)
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
        self._admission = admission

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
        self._admission.validate(self._repository)
        self._repository.recover_expired(
            now=self._now(),
            actor=self._recovery_actor,
            limit=self._recovery_batch_size,
        )
        claims: list[tuple[WorkflowJobClaim, object]] = []
        controller = self._admission.controller
        try:
            for concurrency_class, limit in self._limits.items():
                for _ in range(limit):
                    token = controller.reserve(self._admission, concurrency_class, local_limit=limit)
                    if token is None:
                        break
                    try:
                        worker_id = self._worker_id_factory()
                        if not is_uuid_v7(worker_id):
                            raise ValueError("worker identity factory returned an invalid UUIDv7")
                        self._admission.validate(self._repository)
                        claim = self._repository.claim_next(
                            worker_id=worker_id,
                            concurrency_classes=(concurrency_class,),
                            now=self._now(),
                            lease_duration_ms=self._lease_duration_ms,
                        )
                    except BaseException:
                        controller.release(token)
                        raise
                    if claim is None:
                        controller.release(token)
                        break
                    claims.append((claim, token))
            if not claims:
                return ()
            with ThreadPoolExecutor(max_workers=len(claims), thread_name_prefix="ro-workflow") as pool:
                return tuple(pool.map(self._execute_reserved, claims))
        finally:
            # The pool waits for running handlers before this cleanup; unstarted
            # claimed work remains lease-fenced for existing bounded recovery.
            for _, token in claims:
                controller.release(token)

    def _execute_reserved(self, work: tuple[WorkflowJobClaim, object]) -> WorkflowJobRecord:
        claim, token = work
        try:
            return self._execute(claim)
        finally:
            self._admission.controller.release(token)


__all__ = [
    "LocalAdmissionController",
    "LocalWorkerAdmission",
    "LocalWorkerSupervisor",
    "ProjectWorkerPolicy",
    "WorkerCapacity",
    "WorkerResources",
    "WorkflowActivity",
    "WorkflowActivityContext",
    "WorkflowActivityError",
    "WorkflowCancellationRequested",
    "WorkflowPreparationProblem",
    "prepare_workflow_job",
]
