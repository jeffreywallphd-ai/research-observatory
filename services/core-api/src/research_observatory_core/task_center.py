"""Project-authorized Task Center projection and command boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from .models import (
    WorkflowProgress,
    WorkflowTaskCenterEvent,
    WorkflowTaskCenterHumanTask,
    WorkflowTaskCenterJob,
    WorkflowTaskCenterPage,
    WorkflowTaskCenterRun,
    WorkflowTaskCenterStep,
)
from .ports.workflow_executor import (
    WorkflowActor,
    WorkflowHumanDisposition,
    WorkflowProgressRecord,
    WorkflowQueueConflict,
    WorkflowQueueNotFound,
    WorkflowQueueProblem,
    WorkflowQueueRepository,
    WorkflowTaskCenterRunRecord,
)
from .projects import ProjectLifecycleService

RepositoryFactory = Callable[[Path, str], WorkflowQueueRepository]


@dataclass(slots=True)
class TaskCenterProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    remediation: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _timestamp(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


def _decision_id(human_task_id: str, actor_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(
        f"workflow-human-decision\0{human_task_id}\0{actor_id}\0{idempotency_key}".encode()
    ).digest()
    value = bytearray(UUID(human_task_id).bytes[:6] + digest[:10])
    value[6] = 0x70 | (value[6] & 0x0F)
    value[8] = 0x80 | (value[8] & 0x3F)
    return str(UUID(bytes=bytes(value)))


def _progress(record: WorkflowProgressRecord) -> WorkflowProgress:
    return WorkflowProgress(
        kind=record.kind,
        unit=record.unit,
        completed_units=record.completed_units,
        total_units=record.total_units,
    )


def _projection(record: WorkflowTaskCenterRunRecord) -> WorkflowTaskCenterRun:
    return WorkflowTaskCenterRun(
        workflow_run_id=record.workflow_run_id,
        workflow_key=record.workflow_key,
        definition_revision_id=record.definition_revision_id,
        definition_version=record.definition_version,
        snapshot_id=record.snapshot_id,
        snapshot_revision=record.snapshot_revision,
        state=record.state,
        active_compute=record.active_compute,
        progress=_progress(record.progress),
        revision=record.revision,
        interruption_kind=record.interruption_kind,
        updated_at=cast(datetime, _timestamp(record.updated_at)),
        steps=tuple(
            WorkflowTaskCenterStep(
                step_run_id=item.step_run_id,
                step_key=item.step_key,
                kind=item.kind,
                state=item.state,
                depends_on=item.depends_on,
            )
            for item in record.steps
        ),
        jobs=tuple(
            WorkflowTaskCenterJob(
                job_id=item.job_id,
                state=item.state,
                activity_type=item.activity_type,
                resource_pool=item.resource_pool,
                priority=item.priority,
                attempt_count=item.attempt_count,
                max_attempts=item.max_attempts,
                current_attempt_id=item.current_attempt_id,
                worker_id=item.worker_id,
                progress=_progress(item.progress),
                latest_checkpoint_id=item.latest_checkpoint_id,
                latest_checkpoint_at=_timestamp(item.latest_checkpoint_at),
                diagnostic_code=item.diagnostic_code,
                updated_at=cast(datetime, _timestamp(item.updated_at)),
            )
            for item in record.jobs
        ),
        human_tasks=tuple(
            WorkflowTaskCenterHumanTask(
                human_task_id=item.human_task_id,
                step_run_id=item.step_run_id,
                state=item.state,
                required_role=item.required_role,
                assigned_actor_id=item.assigned_actor_id,
                requested_at=cast(datetime, _timestamp(item.requested_at)),
                evidence_artifact_ids=item.evidence_artifact_ids,
                allowed_dispositions=item.allowed_dispositions,
                consequences_by_disposition=dict(item.consequences_by_disposition),
                decision_id=item.decision_id,
                disposition=item.disposition,
                decided_at=_timestamp(item.decided_at),
            )
            for item in record.human_tasks
        ),
        retained_artifacts=record.retained_artifacts,
        events=tuple(
            WorkflowTaskCenterEvent(
                sequence=item.sequence,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                to_state=item.to_state,
                occurred_at=cast(datetime, _timestamp(item.occurred_at)),
                reason_code=item.reason_code,
            )
            for item in record.events
        ),
    )


def _task_problem(error: WorkflowQueueProblem) -> TaskCenterProblem:
    if isinstance(error, WorkflowQueueNotFound):
        return TaskCenterProblem(
            404,
            "RO-CORE-WORKFLOW-NOT-FOUND",
            "Workflow was not found",
            "The requested workflow item is not part of the open project.",
            "Refresh Task Center and select an available item.",
        )
    if isinstance(error, WorkflowQueueConflict):
        return TaskCenterProblem(
            412,
            "RO-CORE-WORKFLOW-PRECONDITION-FAILED",
            "Workflow authority changed",
            "The workflow changed or the requested action is not authorized by its exact definition.",
            "Refresh Task Center, review the current state and consequences, then retry if still appropriate.",
            True,
        )
    return TaskCenterProblem(
        409,
        "RO-CORE-WORKFLOW-ACTION-FAILED",
        "Workflow action is unavailable",
        "The local workflow boundary could not complete the requested action safely.",
        "Keep the project unchanged, refresh Task Center, and inspect local diagnostics if the problem continues.",
        False,
    )


class TaskCenterService:
    """Expose durable workflow state without leaking persistence or lease capabilities."""

    def __init__(
        self,
        projects: ProjectLifecycleService,
        repository_factory: RepositoryFactory | None,
        local_actor_id: str | None,
    ) -> None:
        self._projects = projects
        self._repository_factory = repository_factory
        self._local_actor_id = local_actor_id

    @classmethod
    def unavailable(cls, projects: ProjectLifecycleService) -> TaskCenterService:
        return cls(projects, None, None)

    def _repository(self, path: Path, project_id: str) -> WorkflowQueueRepository:
        if self._repository_factory is None:
            raise TaskCenterProblem(
                503,
                "RO-CORE-WORKFLOW-TASK-CENTER-UNAVAILABLE",
                "Task Center is unavailable",
                "The durable local workflow adapter is not composed in this Core runtime.",
                "Restart the packaged desktop runtime and retry.",
                True,
            )
        return self._repository_factory(path, project_id)

    def _actor(self) -> WorkflowActor:
        if self._local_actor_id is None:
            raise TaskCenterProblem(
                503,
                "RO-CORE-WORKFLOW-ACTOR-UNAVAILABLE",
                "Local decision identity is unavailable",
                "A trusted same-user identity is required for workflow commands.",
                "Restore the Windows profile identity and retry from Task Center.",
                False,
            )
        return WorkflowActor(self._local_actor_id, "human", "researcher")

    def list(self, *, root: str, limit: int) -> WorkflowTaskCenterPage:
        def read(path: Path, project_id: str) -> WorkflowTaskCenterPage:
            try:
                return WorkflowTaskCenterPage(
                    items=tuple(
                        _projection(item) for item in self._repository(path, project_id).task_center(limit=limit)
                    )
                )
            except WorkflowQueueProblem as error:
                raise _task_problem(error) from error

        return self._projects.perform_open_project_action(root=root, require_write=False, action=read)

    def cancel(
        self,
        *,
        root: str,
        job_id: str,
        expected_run_id: str,
        expected_revision: int,
        reason_code: str,
    ) -> WorkflowTaskCenterRun:
        actor = self._actor()

        def mutate(path: Path, project_id: str) -> WorkflowTaskCenterRun:
            repository = self._repository(path, project_id)
            try:
                bound = next(
                    item for item in repository.task_center(limit=100) if any(job.job_id == job_id for job in item.jobs)
                )
                if bound.workflow_run_id != expected_run_id:
                    raise WorkflowQueueConflict("workflow cancellation run authority differs")
                job = repository.request_cancellation(
                    job_id,
                    actor=actor,
                    now=_now(),
                    reason_code=reason_code,
                    interruption_kind="user-cancel",
                    expected_history_sequence=expected_revision,
                )
                run = next(
                    item for item in repository.task_center(limit=100) if item.workflow_run_id == job.workflow_run_id
                )
                return _projection(run)
            except (StopIteration, WorkflowQueueProblem) as error:
                if isinstance(error, WorkflowQueueProblem):
                    raise _task_problem(error) from error
                raise _task_problem(WorkflowQueueNotFound("workflow run was not found")) from error

        return self._projects.perform_open_project_action(root=root, require_write=True, action=mutate)

    def retry(
        self,
        *,
        root: str,
        job_id: str,
        expected_run_id: str,
        expected_revision: int,
        idempotency_key: str,
    ) -> WorkflowTaskCenterRun:
        actor = self._actor()

        def mutate(path: Path, project_id: str) -> WorkflowTaskCenterRun:
            try:
                repository = self._repository(path, project_id)
                bound = next(
                    item for item in repository.task_center(limit=100) if any(job.job_id == job_id for job in item.jobs)
                )
                if bound.workflow_run_id != expected_run_id:
                    raise WorkflowQueueConflict("workflow retry run authority differs")
                return _projection(
                    repository.retry_as_continuation(
                        job_id,
                        expected_history_sequence=expected_revision,
                        idempotency_key=idempotency_key,
                        actor=actor,
                        now=_now(),
                    )
                )
            except (StopIteration, WorkflowQueueProblem) as error:
                if isinstance(error, WorkflowQueueProblem):
                    raise _task_problem(error) from error
                raise _task_problem(WorkflowQueueNotFound("workflow run was not found")) from error

        return self._projects.perform_open_project_action(root=root, require_write=True, action=mutate)

    def decide(
        self,
        *,
        root: str,
        human_task_id: str,
        expected_run_id: str,
        expected_snapshot_revision: int,
        expected_history_sequence: int,
        disposition: WorkflowHumanDisposition,
        idempotency_key: str,
    ) -> WorkflowTaskCenterRun:
        actor = self._actor()

        def mutate(path: Path, project_id: str) -> WorkflowTaskCenterRun:
            try:
                repository = self._repository(path, project_id)
                bound = next(
                    item
                    for item in repository.task_center(limit=100)
                    if any(task.human_task_id == human_task_id for task in item.human_tasks)
                )
                if bound.workflow_run_id != expected_run_id:
                    raise WorkflowQueueConflict("workflow human decision run authority differs")
                return _projection(
                    repository.complete_human_task(
                        human_task_id,
                        expected_snapshot_revision=expected_snapshot_revision,
                        expected_history_sequence=expected_history_sequence,
                        decision_id=_decision_id(human_task_id, actor.actor_id, idempotency_key),
                        disposition=disposition,
                        actor=actor,
                        now=_now(),
                    )
                )
            except (StopIteration, WorkflowQueueProblem) as error:
                if isinstance(error, WorkflowQueueProblem):
                    raise _task_problem(error) from error
                raise _task_problem(WorkflowQueueNotFound("workflow run was not found")) from error

        return self._projects.perform_open_project_action(root=root, require_write=True, action=mutate)


__all__ = ["TaskCenterProblem", "TaskCenterService"]
