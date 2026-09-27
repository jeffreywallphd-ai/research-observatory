"""Existing-queue batch execution with current authority and stop-before-lock draining."""

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Protocol, cast

from pydantic import TypeAdapter

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ingestion.preview_workflow import PreviewIntentContext, ResumeEpoch
from .logging import emit_log_record
from .ports.reconciliation import (
    ReconciliationActor,
    ReconciliationRepository,
    ReconciliationSourceResolver,
    ReconciliationSourceService,
)
from .ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobAuthority,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowOutputReference,
    WorkflowQueueConflict,
    WorkflowQueueRepository,
)
from .projects import ProjectLifecycleService
from .reconciliation.batch import BATCH_ACTIVITY, SOURCE_ACTIVITIES, BatchInput, InventorySnapshot
from .reconciliation.batch_inventory import collect_batch_sources
from .reconciliation.contracts import ReconciliationProblem
from .reconciliation.workflow import _definition, bind_batch_claim, build_batch_job
from .workflow_contracts import workflow_record_sha256, workflow_snapshot_errors
from .workflow_executor import (
    LocalWorkerAdmission,
    LocalWorkerSupervisor,
    WorkflowActivityError,
    WorkflowAtomicCompletion,
    WorkflowCancellationRequested,
)


class ReconciliationAuthorityAction(Protocol):
    def __call__[Result](
        self,
        root: str,
        trace_id: str,
        action: Callable[
            [ReconciliationRepository, ReconciliationActor, ReconciliationSourceResolver, PreviewIntentContext, Path],
            Result,
        ],
    ) -> Result: ...


@dataclass(frozen=True, slots=True)
class ReconciliationBatchAdapters:
    repository: ReconciliationRepository
    queue: WorkflowQueueRepository
    admission: LocalWorkerAdmission


@dataclass(slots=True)
class _Binding:
    path: Path
    project_id: str
    adapters: ReconciliationBatchAdapters
    stopped: threading.Event = field(default_factory=threading.Event)
    drained: threading.Event = field(default_factory=threading.Event)
    controls_idle: threading.Event = field(default_factory=threading.Event)
    controls: int = 0

    def __post_init__(self):
        self.drained.set()
        self.controls_idle.set()


@dataclass(slots=True)
class _Cancellation:
    action: Callable[[], object]
    finished: threading.Event = field(default_factory=threading.Event)
    result: object = None
    error: Exception | None = None

    def run(self) -> None:
        # Only the publication owner consumes this mailbox, once, after rollback
        # or commit. A caller timeout never transfers ownership or retries it.
        try:
            self.result = self.action()
        except Exception as error:
            self.error = error
        finally:
            self.finished.set()


@dataclass(slots=True)
class _Publication:
    binding: _Binding
    inputs: BatchInput
    claim: WorkflowJobClaim
    requested: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)
    reason: str | None = None
    cancellation: _Cancellation | None = None
    fenced: bool = False


class ReconciliationBatchWorker:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        authorize: ReconciliationAuthorityAction,
        adapters: Callable[[Path, str], ReconciliationBatchAdapters],
        *,
        imports: ReconciliationSourceService,
        connectors: ReconciliationSourceService,
        actor_id: str,
        resume_epoch: str,
        now: Callable[[], str],
    ):
        self._epoch: str = TypeAdapter(ResumeEpoch).validate_python(resume_epoch)
        self._projects, self._authorize, self._adapters = projects, authorize, adapters
        self._imports, self._connectors = imports, connectors
        self._actor, self._now = actor_id, now
        self._mutex, self._runner = threading.RLock(), threading.Lock()
        self._bindings: dict[Path, _Binding] = {}
        self._publications: dict[Path, _Publication] = {}
        self._stopped, self._wake = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None

    def _binding(self, path: Path, identity: str) -> _Binding:
        with self._mutex:
            if self._stopped.is_set():
                raise ReconciliationProblem("reconciliation-runtime-stopped")
            binding = self._bindings.get(path)
            if binding is None:
                binding = _Binding(path, identity, self._adapters(path, identity))
                self._bindings[path] = binding
            if binding.project_id != identity or binding.stopped.is_set():
                raise ReconciliationProblem("reconciliation-project-session-changed")
            return binding

    def _guard[Result](self, binding: _Binding, action: Callable[[], Result], *, stopping: bool = False) -> Result:
        def guarded(path, identity):
            with self._mutex:
                if self._bindings.get(path) is not binding or identity != binding.project_id:
                    raise ReconciliationProblem("reconciliation-project-session-changed")
                if not stopping and (binding.stopped.is_set() or self._stopped.is_set()):
                    raise ReconciliationProblem("reconciliation-runtime-stopped")
            return action()

        return self._projects.perform_open_project_action(root=str(binding.path), require_write=True, action=guarded)

    def _current(self, inputs: BatchInput, actor: ReconciliationActor, intent: PreviewIntentContext) -> None:
        if (inputs.intent, inputs.project_id, inputs.actor_id, inputs.policy_sha256, inputs.session_epoch) != (
            intent,
            intent.project_id,
            actor.actor_id,
            "sha256:" + actor.policy_sha256,
            self._epoch,
        ):
            raise ReconciliationProblem("reconciliation-batch-current-authority-changed")

    @staticmethod
    def _stored(binding: _Binding, authority: WorkflowJobAuthority) -> BatchInput:
        try:
            snapshot = json.loads(authority.snapshot_json)
            definition = json.loads(authority.definition_json)
            prefix, request, epoch = snapshot["configuration"]["configurationId"].split(".")
            if prefix != "reconciliation-batch" or not is_uuid_v7(request):
                raise ValueError
            inputs = binding.adapters.repository.batch_request(request)
            if (
                inputs is None
                or inputs.project_id != binding.project_id
                or inputs.session_epoch != epoch
                or definition
                != _definition(
                    definition["workflowDefinitionId"], definition["definitionRevisionId"], definition["createdAt"]
                )
                or workflow_snapshot_errors(definition, snapshot)
                or workflow_record_sha256(definition) != authority.definition_record_sha256
                or workflow_record_sha256(snapshot) != authority.snapshot_record_sha256
                or snapshot["projectId"] != inputs.project_id
                or snapshot["intent"] != inputs.intent.reference()
                or snapshot["policy"] != inputs.policy_reference()
                or snapshot["executor"]["profile"] != "local"
                or snapshot["configuration"]
                != {
                    "configurationId": inputs.configuration_id,
                    "configurationVersion": inputs.configuration_version,
                    "configurationHash": inputs.configuration_hash,
                }
            ):
                raise ValueError
            return inputs
        except ValueError, KeyError, TypeError:
            raise ReconciliationProblem("reconciliation-batch-request-authority-invalid") from None

    def prepare(self, root: str, trace_id: str) -> str:
        def prepare(repository, actor, _resolve, intent, path):
            binding = self._binding(path, intent.project_id)
            inputs = BatchInput(
                request_id=new_uuid_v7(),
                project_id=intent.project_id,
                actor_id=actor.actor_id,
                intent=intent,
                policy_sha256="sha256:" + actor.policy_sha256,
                session_epoch=self._epoch,
                inventory=InventorySnapshot.from_queue(
                    binding.adapters.queue.accepted_snapshot(activity_types=SOURCE_ACTIVITIES)
                ),
            )
            repository.save_batch_request(inputs, actor=actor)
            return inputs.request_id

        return self._authorize(root, trace_id, prepare)

    def schedule(self, root: str, request_id: str, trace_id: str) -> WorkflowJobRecord:
        def schedule(repository, actor, _resolve, intent, path):
            binding = self._binding(path, intent.project_id)
            inputs = repository.batch_request(request_id)
            if inputs is None:
                raise ReconciliationProblem("reconciliation-batch-request-unavailable")
            self._current(inputs, actor, intent)
            queue = binding.adapters.queue
            previous = queue.find_idempotency(inputs.idempotency_key)
            if previous is not None:
                if self._stored(binding, queue.authority(previous.job_id)) != inputs:
                    raise ReconciliationProblem("reconciliation-batch-command-conflict")
                return previous
            principal = WorkflowActor(self._actor, "human", "local-researcher")
            return queue.enqueue(build_batch_job(inputs, actor=principal, now=self._now()), actor=principal)

        result = self._authorize(root, trace_id, schedule)
        self._wake.set()
        return result

    def status(
        self, root: str, request_id: str, job_id: str
    ) -> tuple[WorkflowJobRecord, WorkflowOutputReference | None]:
        def read(binding):
            queue = binding.adapters.queue
            inputs = self._stored(binding, queue.authority(job_id))
            if inputs.request_id != request_id:
                raise ReconciliationProblem("reconciliation-batch-job-authority-mismatch")
            job, accepted = queue.accepted_status(job_id)
            if accepted is not None and (
                len(accepted.outputs) != 1
                or accepted.activity_type != BATCH_ACTIVITY
                or accepted.outputs[0].media_type != "application/vnd.research-observatory.duplicate-candidate-set+json"
            ):
                raise ReconciliationProblem("reconciliation-batch-output-mismatch")
            return job, accepted.outputs[0] if accepted is not None else None

        current = self.read_active_queue(root, lambda _queue: read(self._bindings[Path(os.path.normpath(root))]))
        if current is not None:
            return current
        return self._projects.perform_open_project_action(
            root=root, require_write=False, action=lambda path, identity: read(self._binding(path, identity))
        )

    def request_publication_stop(
        self,
        root: str,
        *,
        request_id: str | None = None,
        job_id: str | None = None,
        workflow_run_id: str | None = None,
        closing: bool = False,
    ) -> None:
        """Authenticated stop-only hint. Exact-job mismatch never stops another job."""
        path = Path(os.path.normpath(root))
        with self._mutex:
            binding = self._bindings.get(path)
            if binding is None:
                return
            if closing:
                # Fence even an idle binding before waiting for the lifecycle lock.
                binding.stopped.set()
            active = self._publications.get(path)
            if active is None:
                return
            if not closing and (
                active.claim.job_id != job_id
                or (request_id is not None and active.inputs.request_id != request_id)
                or (workflow_run_id is not None and active.claim.workflow_run_id != workflow_run_id)
            ):
                return
            active.reason = active.reason or ("close" if closing else "cancel")
            active.requested.set()
        if not active.finished.wait(1.0):
            raise ReconciliationProblem("reconciliation-worker-drain-pending")

    def _persist_cancel(self, binding: _Binding, request_id: str, job_id: str, *, closing: bool = False) -> None:
        def cancel():
            inputs = self._stored(binding, binding.adapters.queue.authority(job_id))
            if inputs.request_id != request_id:
                raise ReconciliationProblem("reconciliation-batch-job-authority-mismatch")
            binding.adapters.queue.request_cancellation(
                job_id,
                actor=WorkflowActor(self._actor, "human", "local-researcher"),
                now=self._now(),
                reason_code="reconciliation-project-closed" if closing else "reconciliation-batch-cancelled",
                interruption_kind="security-lock" if closing else "user-cancel",
            )
            self._recover_cancelled(binding)

        self._guard(binding, cancel, stopping=True)

    def _recover_cancelled(self, binding: _Binding) -> None:
        binding.adapters.queue.recover_expired(
            now=self._now(),
            actor=WorkflowActor(self._actor, "system", "workflow-coordinator"),
            limit=100,
            activity_types=(BATCH_ACTIVITY,),
        )

    def read_active_queue[Result](self, root: str, read: Callable[[WorkflowQueueRepository], Result]) -> Result | None:
        with self._mutex:
            binding = self._bindings.get(Path(os.path.normpath(root)))
            active = self._publications.get(binding.path) if binding is not None else None
            if (
                binding is None
                or active is None
                or not active.fenced
                or binding.stopped.is_set()
                or self._stopped.is_set()
            ):
                return None
            # The publication owns the validated project lifecycle fence and
            # cannot release it while this mutex pins its fenced state. This is
            # a read-only WAL projection, never a second mutation authority.
            return read(binding.adapters.queue)

    def cancel(self, root: str, request_id: str, job_id: str) -> None:
        self.request_publication_stop(root, request_id=request_id, job_id=job_id)
        binding = self._projects.perform_open_project_action(
            root=root,
            require_write=True,
            action=lambda path, identity: self._binding(path, identity),
        )
        self._persist_cancel(binding, request_id, job_id)

    def cancel_workflow[Result](
        self,
        root: str,
        *,
        job_id: str,
        workflow_run_id: str,
        expected_snapshot_revision: int,
        expected_revision: int,
        action: Callable[[], Result],
    ) -> Result:
        binding = None
        command = None
        try:
            with self._mutex:
                binding = self._bindings.get(Path(os.path.normpath(root)))
                if binding is not None:
                    # Gate new registration even when no publication is active.
                    # The authorized command then wins the lifecycle lock first.
                    binding.controls += 1
                    binding.controls_idle.clear()
                    active = self._publications.get(binding.path)
                    if active is not None and (active.claim.job_id, active.claim.workflow_run_id) == (
                        job_id,
                        workflow_run_id,
                    ):
                        if active.cancellation is not None:
                            raise ReconciliationProblem("reconciliation-cancellation-pending")
                        # A separate WAL reader sees committed history, not the
                        # writer's provisional heartbeats. Reject stale commands
                        # before discarding those heartbeats and their lease.
                        run = next(
                            (
                                item
                                for item in binding.adapters.queue.task_center(limit=100)
                                if item.workflow_run_id == workflow_run_id
                            ),
                            None,
                        )
                        if run is None or (run.snapshot_revision, run.revision) != (
                            expected_snapshot_revision,
                            expected_revision,
                        ):
                            raise WorkflowQueueConflict("workflow cancellation precondition differs")
                        command = _Cancellation(action)
                        active.cancellation = command
                        active.requested.set()
            if command is None:
                return action()
            if not command.finished.wait(2.0):
                raise ReconciliationProblem("reconciliation-worker-drain-pending")
            if command.error is not None:
                raise command.error
            return cast(Result, command.result)
        finally:
            if binding is not None:
                with self._mutex:
                    binding.controls -= 1
                    if binding.controls == 0:
                        binding.controls_idle.set()

    def attach(self, root: str) -> None:
        self._projects.perform_open_project_action(
            root=root,
            require_write=True,
            action=lambda path, identity: self._binding(path, identity),
        )
        self._wake.set()

    def _run(self, binding: _Binding) -> None:
        queue = binding.adapters.queue
        after = None
        while page := self._guard(binding, partial(queue.active_jobs, activity_type=BATCH_ACTIVITY, after=after)):
            for job in page:

                def reconcile(job=job):
                    inputs = self._stored(binding, queue.authority(job.job_id))
                    if inputs.session_epoch != self._epoch:
                        queue.request_cancellation(
                            job.job_id,
                            actor=WorkflowActor(self._actor, "system", "workflow-coordinator"),
                            now=self._now(),
                            reason_code="resume-authority-changed",
                            interruption_kind="policy",
                        )

                self._guard(binding, reconcile)
            after = page[-1].job_id

        def handler(context, claim):
            inputs = self._guard(binding, lambda: self._stored(binding, queue.authority(claim.job_id)), stopping=True)
            active = _Publication(binding, inputs, claim)

            def execute_authorized(repository, actor, resolve, intent, path):
                self._current(inputs, actor, intent)
                if path != binding.path:
                    raise ReconciliationProblem("reconciliation-project-session-changed")
                with self._mutex:
                    if binding.controls and self._publications.get(path) is not active:
                        raise ReconciliationProblem("reconciliation-control-pending")
                    if (
                        self._bindings.get(path) is not binding
                        or binding.stopped.is_set()
                        or self._stopped.is_set()
                        or (path in self._publications and self._publications[path] is not active)
                    ):
                        raise ReconciliationProblem("reconciliation-project-session-changed")
                    self._publications[path] = active
                    active.fenced = True
                authority = queue.authority(claim.job_id)
                continuation = json.loads(authority.snapshot_json).get("continuation")
                predecessor = (
                    (queue.get(continuation["sourceJobId"]), queue.authority(continuation["sourceJobId"]))
                    if continuation
                    else None
                )
                bind_batch_claim(authority, claim, inputs, predecessor=predecessor)
                last_heartbeat = time.monotonic()

                def interrupted():
                    return active.requested.is_set() or binding.stopped.is_set() or self._stopped.is_set()

                def poll():
                    nonlocal last_heartbeat
                    if interrupted():
                        raise ReconciliationProblem("reconciliation-batch-interrupted")
                    context.cancellation_safe_point()
                    current = time.monotonic()
                    if current - last_heartbeat >= min(5.0, context.lease_duration_ms / 3000):
                        context.heartbeat(
                            {"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None}
                        )
                        last_heartbeat = current

                addresses = collect_batch_sources(
                    inputs.inventory,
                    root=str(path),
                    queue=queue,
                    imports=self._imports,
                    connectors=self._connectors,
                    checkpoint=poll,
                )

                def publish(current_repository, current_actor, current_resolve, current_intent, current_path):
                    self._current(inputs, current_actor, current_intent)
                    if current_path != path:
                        raise ReconciliationProblem("reconciliation-project-session-changed")
                    output = current_repository.publish_batch(
                        inputs,
                        addresses,
                        claim=context.claim,
                        actor=current_actor,
                        resolve=current_resolve,
                        now=self._now,
                        interrupted=interrupted,
                        lease_duration_ms=context.lease_duration_ms,
                    )
                    return WorkflowAtomicCompletion((output,))

                return self._authorize(str(path), claim.job_id.replace("-", ""), publish)

            def execute(*args):
                try:
                    return execute_authorized(*args)
                finally:
                    with self._mutex:
                        active.fenced = False

            try:
                while True:
                    try:
                        return self._authorize(str(binding.path), claim.job_id.replace("-", ""), execute)
                    except ReconciliationProblem as error:
                        if binding.stopped.is_set() or self._stopped.is_set():
                            self._persist_cancel(binding, inputs.request_id, claim.job_id, closing=True)
                            raise WorkflowCancellationRequested("reconciliation project stopped") from None
                        if error.code == "reconciliation-control-pending":
                            if not binding.controls_idle.wait(2.0):
                                raise WorkflowActivityError("reconciliation-control-unavailable") from None
                            context.cancellation_safe_point()
                            continue
                        if error.code == "reconciliation-batch-interrupted":
                            if active.reason in {"cancel", "close"}:
                                self._persist_cancel(
                                    binding, inputs.request_id, claim.job_id, closing=active.reason == "close"
                                )
                                raise WorkflowCancellationRequested("reconciliation publication stopped") from None
                            with self._mutex:
                                command = active.cancellation
                            if command is not None:
                                command.run()
                                with self._mutex:
                                    active.cancellation = None
                                    if active.reason is None:
                                        active.requested.clear()
                                if command.error is None:
                                    self._recover_cancelled(binding)
                                    raise WorkflowCancellationRequested("reconciliation publication stopped") from None
                                context.cancellation_safe_point()
                                # A racing committed heartbeat can invalidate a
                                # pre-writer command; full authority is rechecked.
                                continue
                        if "rights" in error.code:
                            raise WorkflowActivityError("rights-denied") from None
                        if any(word in error.code for word in ("authority", "session", "request", "intent", "policy")):
                            raise WorkflowActivityError("stale-authority") from None
                        raise WorkflowActivityError("reconciliation-batch-failed") from None
            finally:
                with self._mutex:
                    command = active.cancellation
                    active.cancellation = None
                    if self._publications.get(binding.path) is active:
                        self._publications.pop(binding.path)
                if command is not None:
                    # Includes commit-wins and unrelated failure. The original
                    # mutator still checks the exact durable run/history state.
                    command.run()
                with self._mutex:
                    active.finished.set()

        LocalWorkerSupervisor(
            queue,
            {BATCH_ACTIVITY: handler},
            concurrency_limits={"document": 1},
            now=self._now,
            recovery_actor=WorkflowActor(self._actor, "system", "workflow-coordinator"),
            admission=binding.adapters.admission,
            activity_types=(BATCH_ACTIVITY,),
        ).run_available()

    def run_pending(self) -> None:
        with self._runner:
            with self._mutex:
                bindings = tuple(self._bindings.values())
            for binding in bindings:
                with self._mutex:
                    if self._stopped.is_set() or binding.stopped.is_set():
                        continue
                    binding.drained.clear()
                try:
                    self._run(binding)
                finally:
                    binding.drained.set()

    def start(self) -> None:
        with self._mutex:
            if self._thread is None and not self._stopped.is_set():
                self._thread = threading.Thread(target=self._pump, name="ro-reconciliation-pump", daemon=True)
                self._thread.start()

    def _pump(self) -> None:
        while not self._stopped.is_set():
            self._wake.clear()
            try:
                self.run_pending()
            except Exception:
                emit_log_record(
                    "reconciliation.worker-unavailable",
                    level="WARNING",
                    fields={"reasonCode": "local-reconciliation-worker-unavailable"},
                )
            self._wake.wait(0.5)

    def detach(self, root: str) -> None:
        self.request_publication_stop(root, closing=True)
        with self._mutex:
            binding = self._bindings.get(Path(os.path.normpath(root)))
        if binding is None:
            return
        if not binding.drained.wait(1.0):
            raise ReconciliationProblem("reconciliation-worker-drain-pending")
        self._projects.perform_open_project_action(root=root, require_write=False, action=lambda path, identity: None)
        with self._mutex:
            if self._bindings.get(binding.path) is binding:
                self._bindings.pop(binding.path)

    def signal_stop(self, root: str | None = None) -> None:
        if root is None:
            self._stopped.set()
            self._wake.set()
        path = Path(os.path.normpath(root)) if root is not None else None
        with self._mutex:
            for binding in self._bindings.values():
                if path is None or binding.path == path:
                    binding.stopped.set()
            for active in self._publications.values():
                if path is None or active.binding.path == path:
                    active.reason = active.reason or "close"
                    active.requested.set()

    def shutdown(self) -> None:
        self.signal_stop()
        if self._thread is not None:
            self._thread.join(2.0)
            if self._thread.is_alive():
                raise ReconciliationProblem("reconciliation-worker-drain-pending")
        if not self._runner.acquire(timeout=1.0):
            raise ReconciliationProblem("reconciliation-worker-drain-pending")
        self._runner.release()
