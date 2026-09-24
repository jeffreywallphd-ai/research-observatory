"""Confirmed one-page operations on the existing local durable workflow executor."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx2

from .connector_service import ConnectorConsentService, _Pending
from .connectors.broker import ConnectorBroker, ProviderRateController, utc_now
from .connectors.providers import ProviderProblem
from .connectors.settings import ConnectorConnectionStatus, ConnectorSettings
from .connectors.transport import PublicHTTPTransport
from .connectors.workflow import ACTIVITY, ConnectorJobInput, bind_connector_claim, build_connector_job
from .domain_contracts import is_uuid_v7
from .logging import emit_log_record
from .ports.connector_runtime import ConnectorAuthority, ConnectorOperationRepository, ConnectorPublication
from .ports.credential_store import SecretAccessContext
from .ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobAuthority,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowQueueRepository,
)
from .projects import ProjectLifecycleService
from .workflow_executor import (
    LocalWorkerAdmission,
    LocalWorkerSupervisor,
    WorkflowActivityContext,
    WorkflowActivityError,
    WorkflowAtomicCompletion,
    WorkflowCancellationRequested,
)


@dataclass(frozen=True, slots=True)
class ConnectorWorkerAdapters:
    pages: ConnectorOperationRepository
    queue: WorkflowQueueRepository
    admission: LocalWorkerAdmission


@dataclass(slots=True)
class _WorkerBinding:
    path: Path
    project_id: str
    adapters: ConnectorWorkerAdapters
    stopped: threading.Event = field(default_factory=threading.Event)
    drained: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.drained.set()


def _configuration(authority: WorkflowJobAuthority) -> tuple[str, str]:
    try:
        snapshot = json.loads(authority.snapshot_json)
        prefix, identity, epoch = snapshot["configuration"]["configurationId"].split(".")
        if prefix != "connector-page" or not is_uuid_v7(identity) or re.fullmatch(r"[0-9a-f]{32}", epoch) is None:
            raise ValueError
        return identity, epoch
    except ValueError, KeyError, TypeError:
        raise ProviderProblem("policy-denied") from None


class _Cancellation:
    def __init__(
        self,
        service: ConnectorWorkerService,
        binding: _WorkerBinding,
        authority: ConnectorAuthority,
        inputs: ConnectorJobInput,
        context: WorkflowActivityContext,
    ):
        self.service, self.binding, self.authority, self.inputs, self.context = (
            service,
            binding,
            authority,
            inputs,
            context,
        )
        self._next_poll = self._next_heartbeat = 0.0

    @property
    def cancelled(self) -> bool:
        if self.service._stopped.is_set() or self.binding.stopped.is_set():
            return True
        now = self.service._clock()
        if now < self._next_poll:
            return False
        self._next_poll = now + 0.25
        try:

            def poll(_stamp):
                self.context.cancellation_safe_point()
                if now >= self._next_heartbeat:
                    self.context.heartbeat(
                        {"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None}
                    )
                    self._next_heartbeat = now + 2.0

            self.authority.guard(self.inputs.preview.request, "admission", poll)
            return False
        except ProviderProblem, WorkflowCancellationRequested:
            return True


class ConnectorWorkerService:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        consent: ConnectorConsentService,
        adapters: Callable[[Path, str], ConnectorWorkerAdapters],
        *,
        local_actor_id: str,
        settings: ConnectorSettings | None = None,
        now: Callable[[], str] = utc_now,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        transport_factory: Callable[[], httpx2.AsyncBaseTransport] = PublicHTTPTransport,
    ):
        if not is_uuid_v7(local_actor_id):
            raise ProviderProblem("policy-denied")
        self.consent, self._projects, self._adapters = consent, projects, adapters
        self.settings = settings if settings is not None else ConnectorSettings(None)
        self._actor_id, self._now, self._clock, self._sleep = local_actor_id, now, clock, sleep
        self._transport_factory, self._rates = transport_factory, ProviderRateController(clock=clock)
        self._mutex, self._runner = threading.RLock(), threading.Lock()
        self._bindings: dict[Path, _WorkerBinding] = {}
        self._stopped, self._wake = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None

    def _actor(self) -> WorkflowActor:
        return WorkflowActor(self._actor_id, "human", "local-researcher")

    def connection_status(self, root: str, project_id: str, provider: str) -> ConnectorConnectionStatus:
        def status(binding: _WorkerBinding) -> ConnectorConnectionStatus:
            if binding.project_id != project_id:
                raise ProviderProblem("policy-denied")
            return self.settings.status(provider)

        return self._action(root, status)

    def configure_connection(
        self,
        root: str,
        project_id: str,
        provider: str,
        *,
        key: str | None,
        contact: str | None,
        expected_version: str | None,
        context: SecretAccessContext,
        preserve_key: bool = False,
        preserve_contact: bool = False,
    ) -> ConnectorConnectionStatus:
        def configure(binding: _WorkerBinding) -> ConnectorConnectionStatus:
            if binding.project_id != project_id:
                raise ProviderProblem("policy-denied")
            return self.settings.replace(
                provider,
                key=key,
                contact=contact,
                expected_version=expected_version,
                context=context,
                preserve_key=preserve_key,
                preserve_contact=preserve_contact,
            )

        return self._action(root, configure)

    def _action[Result](self, root: str, action: Callable[[_WorkerBinding], Result]) -> Result:
        def bound(path: Path, identity: str) -> Result:
            with self._mutex:
                if self._stopped.is_set():
                    raise ProviderProblem("policy-denied")
                binding = self._bindings.get(path)
                if binding is None:
                    binding = _WorkerBinding(path, identity, self._adapters(path, identity))
                    self._bindings[path] = binding
                if binding.project_id != identity or binding.stopped.is_set():
                    raise ProviderProblem("policy-denied")
            return action(binding)

        return self._projects.perform_open_project_action(root=root, require_write=True, action=bound)

    @staticmethod
    def _inputs(pending: _Pending) -> ConnectorJobInput:
        return ConnectorJobInput(
            preview=pending.preview,
            intent=pending.intent,
            session_epoch=pending.stamp.session_id,
            predecessor_revision_id=pending.stamp.expected_checkpoint_revision_id,
        )

    def confirm_and_schedule(self, root: str, preview_id: str, *, confirmation: str) -> WorkflowJobRecord:
        def schedule(binding: _WorkerBinding) -> WorkflowJobRecord:
            self.consent.confirm(root, preview_id, confirmation=confirmation)

            def confirmed(pending: _Pending) -> WorkflowJobRecord:
                inputs = self._inputs(pending)
                prior = binding.adapters.queue.find_idempotency(inputs.idempotency_key)
                if prior is not None:
                    authority = binding.adapters.queue.authority(prior.job_id)
                    if _configuration(authority) != (inputs.preview.preview_id, inputs.session_epoch):
                        raise ProviderProblem("policy-denied")
                    return prior
                binding.adapters.pages.save_operation(inputs, actor_id=self._actor_id, now=self._now())
                return binding.adapters.queue.enqueue(
                    build_connector_job(inputs, actor=self._actor(), now=self._now()), actor=self._actor()
                )

            return self.consent.confirmed_action(root, preview_id, confirmed)

        job = self._action(root, schedule)
        self._wake.set()
        return job

    def _stored(self, binding: _WorkerBinding, authority: WorkflowJobAuthority) -> ConnectorJobInput:
        identity, epoch = _configuration(authority)
        inputs = binding.adapters.pages.operation(identity)
        if inputs.project_id != binding.project_id or inputs.session_epoch != epoch:
            raise ProviderProblem("policy-denied")
        return inputs

    def _current(self, binding: _WorkerBinding, inputs: ConnectorJobInput) -> ConnectorAuthority:
        def confirmed(pending: _Pending) -> None:
            if self._inputs(pending) != inputs:
                raise ProviderProblem("policy-denied")

        self.consent.confirmed_action(str(binding.path), inputs.preview.preview_id, confirmed)
        return self.consent.authority(str(binding.path), inputs.preview.preview_id)

    def cancel(self, root: str, job_id: str) -> None:
        def cancel(binding: _WorkerBinding) -> None:
            queue = binding.adapters.queue
            inputs = self._stored(binding, queue.authority(job_id))
            job = queue.get(job_id)
            if job.state not in {"succeeded", "failed", "cancelled"}:
                queue.request_cancellation(
                    job_id,
                    actor=self._actor(),
                    now=self._now(),
                    reason_code="connector-page-cancelled",
                    interruption_kind="user-cancel",
                )
            self.consent.revoke(root, inputs.preview.preview_id)

        self._action(root, cancel)
        self._wake.set()

    def status(self, root: str, job_id: str) -> WorkflowJobRecord:
        def status(binding: _WorkerBinding) -> WorkflowJobRecord:
            self._stored(binding, binding.adapters.queue.authority(job_id))
            return binding.adapters.queue.get(job_id)

        return self._action(root, status)

    def _reconcile(self, binding: _WorkerBinding) -> None:
        queue = binding.adapters.queue
        after: str | None = None
        while True:

            def active(_binding: _WorkerBinding, cursor: str | None = after) -> tuple[WorkflowJobRecord, ...]:
                return queue.active_jobs(activity_type=ACTIVITY, after=cursor)

            page = self._action(str(binding.path), active)
            if not page:
                break
            for job in page:

                def reconcile(_binding, job_id=job.job_id):
                    inputs = self._stored(binding, queue.authority(job_id))
                    try:
                        self._current(binding, inputs)
                    except ProviderProblem:
                        queue.request_cancellation(
                            job_id,
                            actor=self._actor(),
                            now=self._now(),
                            reason_code="connector-confirmation-unavailable",
                            interruption_kind="policy",
                        )

                self._action(str(binding.path), reconcile)
            after = page[-1].job_id

    def _run(self, binding: _WorkerBinding) -> None:
        self._reconcile(binding)

        def handler(context: WorkflowActivityContext, claim: WorkflowJobClaim):
            def authorize(_binding):
                saved = binding.adapters.queue.authority(claim.job_id)
                inputs = self._stored(binding, saved)
                bind_connector_claim(saved, claim, inputs)
                return inputs, self._current(binding, inputs)

            try:
                inputs, authority = self._action(str(binding.path), authorize)
                cancellation = _Cancellation(self, binding, authority, inputs, context)
                broker = ConnectorBroker(
                    authority=authority,
                    repository=binding.adapters.pages,
                    rates=self._rates,
                    transport=self._transport_factory(),
                    settings=self.settings,
                    now=self._now,
                    sleep=self._sleep,
                    publication=ConnectorPublication(
                        inputs,
                        context.claim,
                        context.now,
                        lambda: self._stopped.is_set() or binding.stopped.is_set(),
                    ),
                )

                async def fetch():
                    try:
                        return await broker.fetch(inputs.preview.request, cancellation=cancellation)
                    finally:
                        await broker.aclose()

                result = asyncio.run(fetch())
                if result.outcome != "complete":
                    context.cancellation_safe_point()
                    raise WorkflowActivityError("connector-" + result.errors[0].code)
                # Keep the project -> object-store lock order even when reading
                # the already committed receipt. This is not a second output
                # acceptance or a cancellable gap before publication.
                output = self._action(
                    str(binding.path), lambda current: current.adapters.pages.output_reference(inputs.preview.request)
                )
                return WorkflowAtomicCompletion((output,))
            except ProviderProblem as error:
                raise WorkflowActivityError("connector-" + error.code) from None

        LocalWorkerSupervisor(
            binding.adapters.queue,
            {ACTIVITY: handler},
            concurrency_limits={"document": 1},
            now=self._now,
            recovery_actor=WorkflowActor(self._actor_id, "system", "workflow-coordinator"),
            admission=binding.adapters.admission,
            activity_types=(ACTIVITY,),
        ).run_available()

    def run_pending(self) -> None:
        # One executor pass at a time. This also keeps shared provider buckets on
        # a single execution lane; async locks are never contended across loops.
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

    def attach(self, root: str) -> None:
        self.consent.attach(root)
        self._action(root, lambda _: None)
        self._wake.set()

    def start(self) -> None:
        with self._mutex:
            if self._thread is not None or self._stopped.is_set():
                return
            self._thread = threading.Thread(target=self._pump, name="ro-connector-pump", daemon=True)
            self._thread.start()

    def _pump(self) -> None:
        while not self._stopped.is_set():
            self._wake.clear()
            try:
                self.run_pending()
            except Exception:
                emit_log_record(
                    "connector.worker-unavailable",
                    level="WARNING",
                    fields={"reasonCode": "scholarly-connector-worker-unavailable"},
                )
            self._wake.wait(timeout=0.5)

    def detach(self, root: str) -> None:
        with self._mutex:
            binding = self._bindings.get(Path(root))
            if binding is not None:
                binding.stopped.set()
        self.consent.detach(root)
        if binding is not None:
            if not binding.drained.wait(timeout=1.0):
                raise ProviderProblem("cancelled")
            with self._mutex:
                if self._bindings.get(binding.path) is binding:
                    self._bindings.pop(binding.path)

    def shutdown(self) -> None:
        self._stopped.set()
        self._wake.set()
        self.consent.shutdown()
        with self._mutex:
            bindings = tuple(self._bindings.values())
            for binding in bindings:
                binding.stopped.set()
        for binding in bindings:
            if not binding.drained.wait(timeout=5.0):
                raise ProviderProblem("cancelled")
        if self._thread is not None:
            self._thread.join(timeout=1.0)
