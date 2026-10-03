"""Core-owned, consent-fenced durable execution of signed connector plugins."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .connectors.broker import utc_now
from .connectors.plugin_broker import PluginBrokerCall, PluginBrokerRates
from .connectors.plugin_credentials import PluginCredentialSettings, PluginCredentialStatus
from .connectors.plugin_dispatch import PluginDispatchController, PluginDispatchProblem
from .connectors.plugin_grants import PluginGrantActor
from .connectors.plugin_manifest import Operation, PluginInvocationPlan, PluginInvocationRequest
from .connectors.plugin_scientific_request import (
    PluginScientificRequest,
    PluginScientificRequestProblem,
    parse_plugin_scientific_request,
)
from .connectors.plugin_workflow import ACTIVITY, PluginJobInput, bind_plugin_claim, build_plugin_job
from .domain_contracts import is_uuid_v7
from .logging import emit_log_record
from .plugin_admin_service import PluginAdminService
from .plugin_consent import (
    PluginConsentAuthority,
    PluginConsentProblem,
    PluginConsentService,
    PluginConsentStage,
    PluginConsentStamp,
)
from .plugin_runtime import InstalledPluginRuntime
from .ports.object_store import ObjectPutCommand, ObjectStore, ObjectStoreProblem
from .ports.plugin_jobs import PluginJobRepositoryProblem, PluginJobStore
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
)

_MAX_INPUT = 10 * 1_048_576
_CONFIG = re.compile(r"plugin-connector\.([0-9a-f-]{36})\.([0-9a-f]{32})\Z")


class PluginWorkerProblem(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _assert_scientific_broker_call(input_data: bytes, operation: Operation, call: PluginBrokerCall) -> None:
    """Bind one broker call to the exact consented scientific page."""

    try:
        expected = parse_plugin_scientific_request(input_data, operation).call
    except PluginScientificRequestProblem:
        raise PluginWorkerProblem("plugin-worker-broker-parameters-denied") from None
    if call.model_copy(update={"credential_scope": None}) != expected:
        raise PluginWorkerProblem("plugin-worker-broker-parameters-denied")


@dataclass(frozen=True, slots=True)
class PluginWorkerAdapters:
    jobs: PluginJobStore
    queue: WorkflowQueueRepository
    admission: LocalWorkerAdmission
    objects: ObjectStore


@dataclass(slots=True)
class _Binding:
    path: Path
    project_id: str
    adapters: PluginWorkerAdapters
    stopped: threading.Event = field(default_factory=threading.Event)
    drained: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.drained.set()


class _Cancellation:
    def __init__(self, service: PluginWorkerService, binding: _Binding, context: WorkflowActivityContext) -> None:
        self.service, self.binding, self.context = service, binding, context
        self._next_poll = self._next_heartbeat = 0.0

    def __call__(self) -> bool:
        if self.service._stopped.is_set() or self.binding.stopped.is_set():
            return True
        now = time.monotonic()
        if now < self._next_poll:
            return False
        self._next_poll = now + 0.25
        try:
            self.context.cancellation_safe_point()
            if now >= self._next_heartbeat:
                self.context.heartbeat(
                    {"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None}
                )
                self._next_heartbeat = now + 2.0
            return False
        except Exception:
            return True


class PluginWorkerService:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        admin: PluginAdminService,
        consent: PluginConsentService,
        adapters: Callable[[Path, str], PluginWorkerAdapters],
        *,
        local_actor_id: str,
        runtime: InstalledPluginRuntime | None = None,
        credentials: PluginCredentialSettings | None = None,
        now: Callable[[], str] = utc_now,
    ) -> None:
        if not is_uuid_v7(local_actor_id):
            raise PluginWorkerProblem("plugin-worker-actor-invalid")
        self._projects, self._admin, self._consent, self._adapters = projects, admin, consent, adapters
        self._actor_id, self._runtime, self._now = local_actor_id, runtime or InstalledPluginRuntime(), now
        self._credentials = credentials
        self._rates = PluginBrokerRates()
        self._mutex, self._runner = threading.RLock(), threading.Lock()
        self._bindings: dict[Path, _Binding] = {}
        self._stopped, self._wake = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None

    def _actor(self) -> WorkflowActor:
        return WorkflowActor(self._actor_id, "human", "local-researcher")

    def _action[Result](self, root: str, action: Callable[[_Binding], Result]) -> Result:
        def bound(path: Path, identity: str) -> Result:
            with self._mutex:
                if self._stopped.is_set():
                    raise PluginWorkerProblem("plugin-worker-stopped")
                binding = self._bindings.get(path)
                if binding is None:
                    binding = _Binding(path, identity, self._adapters(path, identity))
                    self._bindings[path] = binding
                if binding.project_id != identity or binding.stopped.is_set():
                    raise PluginWorkerProblem("plugin-worker-project-denied")
            return action(binding)

        return self._projects.perform_open_project_action(root=root, require_write=True, action=bound)

    @staticmethod
    def _stamp(inputs: PluginJobInput, stamp: PluginConsentStamp) -> None:
        if (
            stamp.preview_id != inputs.consent_preview_id
            or stamp.confirmation_sha256 != inputs.consent_confirmation_sha256
            or stamp.retention_sha256 != inputs.consent_retention_sha256
            or stamp.request_sha256 != inputs.authorization_request_sha256
            or stamp.intent != inputs.intent
            or stamp.policy_sha256 != inputs.policy_hash
            or stamp.session_id != inputs.job_epoch
        ):
            raise PluginWorkerProblem("plugin-worker-consent-stale")

    def _guard(
        self,
        authority: PluginConsentAuthority,
        inputs: PluginJobInput,
        stage: PluginConsentStage,
    ) -> None:
        authority.guard(inputs.request, authority.plan, stage, lambda stamp: self._stamp(inputs, stamp))

    def _predecessor(
        self,
        binding: _Binding,
        plan: PluginInvocationPlan,
        scientific: PluginScientificRequest,
    ) -> None:
        """A continuation follows one already published, same-authority page."""

        previous_id = scientific.previous_invocation_id
        if previous_id is None:
            return
        try:
            if plan.operation != "search" or previous_id == plan.invocation_id:
                raise ValueError
            previous = binding.adapters.jobs.input(previous_id)
            page = binding.adapters.jobs.result(previous)
            if page is None:
                raise ValueError
            prior_scientific = parse_plugin_scientific_request(
                self._input_bytes(binding, previous), previous.request.operation
            )
            prior_plan = page.plan
            if (
                previous.project_id != binding.project_id
                or prior_plan.project_id != plan.project_id
                or prior_plan.invocation_id != previous_id
                or prior_plan.plugin_id != plan.plugin_id
                or prior_plan.plugin_version != plan.plugin_version
                or prior_plan.sdk_version != plan.sdk_version
                or prior_plan.required_features != plan.required_features
                or prior_plan.package_sha256 != plan.package_sha256
                or prior_plan.manifest_sha256 != plan.manifest_sha256
                or prior_plan.signature_sha256 != plan.signature_sha256
                or prior_plan.publisher_key_id != plan.publisher_key_id
                or prior_plan.grant_revision != plan.grant_revision
                or prior_plan.permissions != plan.permissions
                or prior_plan.source_id != plan.source_id
                or prior_plan.operation != plan.operation
                or prior_plan.destination != plan.destination
                or prior_scientific.call.query != scientific.call.query
                or prior_scientific.call.page_size != scientific.call.page_size
                or prior_scientific.call.cursor == scientific.call.cursor
                or page.continuation != "next-page"
                or page.next_cursor != scientific.call.cursor
            ):
                raise ValueError
        except PluginJobRepositoryProblem, PluginWorkerProblem, PluginScientificRequestProblem, ValueError:
            raise PluginWorkerProblem("plugin-worker-page-predecessor-denied") from None

    def submit(
        self,
        root: str,
        preview_id: str,
        request: PluginInvocationRequest,
        input_data: bytes,
    ) -> WorkflowJobRecord:
        request = PluginInvocationRequest.model_validate(request)
        if (
            not isinstance(input_data, bytes)
            or len(input_data) > _MAX_INPUT
            or "sha256:" + hashlib.sha256(input_data).hexdigest() != request.scientific_request_sha256
        ):
            raise PluginWorkerProblem("plugin-worker-input-invalid")
        try:
            scientific = parse_plugin_scientific_request(input_data, request.operation)
        except PluginScientificRequestProblem:
            raise PluginWorkerProblem("plugin-worker-input-invalid") from None
        authority = self._consent.authority(root, preview_id)
        plan = authority.plan
        stamp = authority.guard(request, plan, "admission", lambda stamp: stamp)

        def schedule(binding: _Binding) -> WorkflowJobRecord:
            if binding.project_id != plan.project_id:
                raise PluginWorkerProblem("plugin-worker-project-denied")
            authority.guard(request, plan, "admission", lambda current: self._check_stamp(stamp, current))
            self._predecessor(binding, plan, scientific)
            digest = hashlib.sha256(input_data).hexdigest()
            stored = binding.adapters.objects.put(
                io.BytesIO(input_data),
                ObjectPutCommand(
                    media_type="application/octet-stream",
                    rights_status="allowed",  # Only confirmed local processing.
                    protection_profile="project-encrypted-v1",
                    retention_class="project-lifetime",
                    creation_source="local-derivation",
                    created_at=self._now(),
                    expected_sha256=digest,
                ),
            )
            if (stored.object_sha256, stored.byte_length) != (digest, len(input_data)):
                raise PluginWorkerProblem("plugin-worker-input-store-invalid")
            inputs = PluginJobInput(
                request=request,
                plugin_id=plan.plugin_id,
                package_sha256=plan.package_sha256,
                manifest_sha256=plan.manifest_sha256,
                signature_sha256=plan.signature_sha256,
                authorization_request_sha256=plan.request_sha256,
                consent_preview_id=stamp.preview_id,
                consent_confirmation_sha256=stamp.confirmation_sha256,
                consent_retention_sha256=stamp.retention_sha256,
                input_object_sha256=digest,
                input_byte_length=len(input_data),
                intent=stamp.intent,
                policy_hash=stamp.policy_sha256,
                job_epoch=stamp.session_id,
            )
            prior = binding.adapters.queue.find_idempotency(inputs.idempotency_key)
            if prior is not None:
                previous = self._stored(binding, binding.adapters.queue.authority(prior.job_id))
                if previous != inputs:
                    raise PluginWorkerProblem("plugin-worker-invocation-conflict")
                return prior
            binding.adapters.jobs.save_input(inputs, actor_id=self._actor_id, now=self._now())
            authority.guard(request, plan, "admission", lambda current: self._stamp(inputs, current))
            return binding.adapters.queue.enqueue(
                build_plugin_job(inputs, actor=self._actor(), now=self._now()), actor=self._actor()
            )

        job = self._action(root, schedule)
        self._wake.set()
        return job

    @staticmethod
    def _check_stamp(expected: PluginConsentStamp, current: PluginConsentStamp) -> None:
        if current != expected:
            raise PluginWorkerProblem("plugin-worker-consent-stale")

    def _stored(self, binding: _Binding, saved: WorkflowJobAuthority) -> PluginJobInput:
        try:
            snapshot = json.loads(saved.snapshot_json)
            matched = _CONFIG.fullmatch(snapshot["configuration"]["configurationId"])
            if matched is None or not is_uuid_v7(matched[1]):
                raise ValueError
            inputs = binding.adapters.jobs.input(matched[1])
            if (
                inputs.project_id != binding.project_id
                or inputs.job_epoch != matched[2]
                or inputs.configuration_hash != snapshot["configuration"]["configurationHash"]
            ):
                raise ValueError
            return inputs
        except ValueError, KeyError, TypeError, PluginJobRepositoryProblem:
            raise PluginWorkerProblem("plugin-worker-job-invalid") from None

    def status(self, root: str, project_id: str, job_id: str) -> WorkflowJobRecord:
        def status(binding: _Binding) -> WorkflowJobRecord:
            if binding.project_id != project_id:
                raise PluginWorkerProblem("plugin-worker-project-denied")
            self._stored(binding, binding.adapters.queue.authority(job_id))
            return binding.adapters.queue.get(job_id)

        return self._action(root, status)

    def cancel(self, root: str, project_id: str, job_id: str) -> None:
        def cancel(binding: _Binding) -> PluginJobInput:
            if binding.project_id != project_id:
                raise PluginWorkerProblem("plugin-worker-project-denied")
            queue = binding.adapters.queue
            inputs = self._stored(binding, queue.authority(job_id))
            job = queue.get(job_id)
            if job.state not in {"succeeded", "failed", "cancelled"}:
                queue.request_cancellation(
                    job_id,
                    actor=self._actor(),
                    now=self._now(),
                    reason_code="plugin-user-cancelled",
                    interruption_kind="user-cancel",
                )
            return inputs

        inputs = self._action(root, cancel)
        self._consent.revoke(root, inputs.consent_preview_id)
        self._wake.set()

    def _input_bytes(self, binding: _Binding, inputs: PluginJobInput) -> bytes:
        try:
            with binding.adapters.objects.open(inputs.input_object_sha256, purpose="document-analysis") as stream:
                data = stream.read(_MAX_INPUT + 1)
            if len(data) != inputs.input_byte_length or hashlib.sha256(data).hexdigest() != inputs.input_object_sha256:
                raise ValueError
            return data
        except ObjectStoreProblem, ValueError:
            raise PluginWorkerProblem("plugin-worker-input-unavailable") from None

    def credential_status(
        self,
        root: str,
        project_id: str,
        preview_id: str,
        request: PluginInvocationRequest,
        scope: str,
        *,
        trace_id: str,
    ) -> PluginCredentialStatus:
        credentials = self._credentials
        if credentials is None:
            raise PluginWorkerProblem("plugin-credential-unavailable")
        authority = self._consent.authority(root, preview_id)

        def status(binding: _Binding) -> PluginCredentialStatus:
            if binding.project_id != project_id:
                raise PluginWorkerProblem("plugin-worker-project-denied")
            admitted = self._admin.prepare_persisted_invocation(
                root,
                project_id,
                authority.plan.package_sha256,
                authority.plan.manifest_sha256,
                authority.plan.signature_sha256,
                request,
                actor=self._admin.actor(trace_id),
            )
            if admitted.plan != authority.plan or scope not in admitted.package.manifest.credential_scopes:
                raise PluginWorkerProblem("plugin-credential-scope-denied")
            return authority.guard(
                request,
                authority.plan,
                "admission",
                lambda _stamp: credentials.status(scope, authority.plan),
            )

        return self._action(root, status)

    def configure_credential(
        self,
        root: str,
        project_id: str,
        preview_id: str,
        request: PluginInvocationRequest,
        scope: str,
        secret: str,
        *,
        expected_version: str | None,
        trace_id: str,
    ) -> PluginCredentialStatus:
        credentials = self._credentials
        if credentials is None:
            raise PluginWorkerProblem("plugin-credential-unavailable")
        authority = self._consent.authority(root, preview_id)

        def configure(binding: _Binding) -> PluginCredentialStatus:
            plan = authority.plan
            if binding.project_id != project_id or "credential-broker" not in plan.permissions:
                raise PluginWorkerProblem("plugin-credential-denied")
            admitted = self._admin.prepare_persisted_invocation(
                root,
                project_id,
                plan.package_sha256,
                plan.manifest_sha256,
                plan.signature_sha256,
                request,
                actor=self._admin.actor(trace_id),
            )
            if admitted.plan != plan or scope not in admitted.package.manifest.credential_scopes:
                raise PluginWorkerProblem("plugin-credential-scope-denied")
            return authority.guard(
                request,
                plan,
                "admission",
                lambda _stamp: credentials.configure(plan, scope, secret, expected_version=expected_version),
            )

        return self._action(root, configure)

    def _reconcile(self, binding: _Binding) -> None:
        queue = binding.adapters.queue
        after = None
        while True:

            def active_jobs(_binding: _Binding, cursor: str | None = after) -> tuple[WorkflowJobRecord, ...]:
                return queue.active_jobs(activity_type=ACTIVITY, after=cursor)

            page = self._action(str(binding.path), active_jobs)
            if not page:
                return
            for job in page:

                def check(_binding: _Binding, job_id: str = job.job_id) -> None:
                    inputs = self._stored(binding, queue.authority(job_id))
                    try:
                        authority = self._consent.authority(str(binding.path), inputs.consent_preview_id)
                        self._guard(authority, inputs, "admission")
                    except PluginConsentProblem, PluginWorkerProblem:
                        queue.request_cancellation(
                            job_id,
                            actor=self._actor(),
                            now=self._now(),
                            reason_code="plugin-consent-unavailable",
                            interruption_kind="policy",
                        )

                self._action(str(binding.path), check)
            after = page[-1].job_id

    def _run(self, binding: _Binding) -> None:
        self._reconcile(binding)

        def handler(context: WorkflowActivityContext, claim: WorkflowJobClaim):
            try:

                def admit(_binding: _Binding):
                    inputs = self._stored(binding, binding.adapters.queue.authority(claim.job_id))
                    bind_plugin_claim(binding.adapters.queue.authority(claim.job_id), claim, inputs)
                    authority = self._consent.authority(str(binding.path), inputs.consent_preview_id)
                    self._guard(authority, inputs, "dispatch")
                    data = self._input_bytes(binding, inputs)
                    try:
                        scientific = parse_plugin_scientific_request(data, inputs.request.operation)
                    except PluginScientificRequestProblem:
                        raise PluginWorkerProblem("plugin-worker-input-invalid") from None
                    self._predecessor(binding, authority.plan, scientific)
                    return inputs, authority, data

                inputs, authority, data = self._action(str(binding.path), admit)
                cancellation = _Cancellation(self, binding, context)

                def policy(plan, call):
                    if call is not None:
                        _assert_scientific_broker_call(data, plan.operation, call)
                    self._guard(authority, inputs, "broker" if call is not None else "dispatch")

                controller = PluginDispatchController(
                    self._admin,
                    runtime_provider=self._runtime.load,
                    runner=self._runtime.run,
                    object_store=lambda project: binding.adapters.objects if project == binding.project_id else None,
                    current_request=lambda project, invocation: (
                        inputs.request if (project, invocation) == (inputs.project_id, inputs.invocation_id) else None
                    ),
                    policy_recheck=policy,
                    current_credential_origin=lambda scope, plan: (
                        self._credentials.origin(scope, plan) if self._credentials is not None else None
                    ),
                    cancelled=lambda invocation: invocation != inputs.invocation_id or cancellation(),
                    lease_secret=self._credentials.lease if self._credentials is not None else None,
                    rates=self._rates,
                )
                staged = asyncio.run(
                    controller.dispatch_persisted(
                        root=str(binding.path),
                        project_id=binding.project_id,
                        package_sha256=inputs.package_sha256,
                        manifest_sha256=inputs.manifest_sha256,
                        signature_sha256=inputs.signature_sha256,
                        request=inputs.request,
                        input_data=data,
                        actor=PluginGrantActor(
                            self._actor_id, claim.job_id.replace("-", ""), self._now(), actor_type="workload"
                        ),
                    )
                )

                def publish(_binding: _Binding):
                    self._guard(authority, inputs, "publication")
                    self._predecessor(
                        binding,
                        authority.plan,
                        parse_plugin_scientific_request(data, inputs.request.operation),
                    )
                    return binding.adapters.jobs.publish(
                        inputs,
                        authority.plan,
                        staged,
                        context.claim,
                        actor_id=self._actor_id,
                        now=self._now,
                        recheck_current=lambda: self._guard(authority, inputs, "publication"),
                        interrupted=cancellation,
                    )

                output = self._action(str(binding.path), publish)
                return WorkflowAtomicCompletion((output,))
            except PluginConsentProblem, PluginDispatchProblem, PluginJobRepositoryProblem, PluginWorkerProblem:
                raise WorkflowActivityError("plugin-execution-denied") from None

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
        self._action(root, lambda _: None)
        self._wake.set()

    def start(self) -> None:
        with self._mutex:
            if self._thread is not None or self._stopped.is_set():
                return
            self._thread = threading.Thread(target=self._pump, name="ro-plugin-pump", daemon=True)
            self._thread.start()

    def _pump(self) -> None:
        while not self._stopped.is_set():
            self._wake.clear()
            try:
                self.run_pending()
            except Exception:
                emit_log_record(
                    "plugin.worker-unavailable",
                    level="WARNING",
                    fields={"reasonCode": "plugin-worker-unavailable"},
                )
            self._wake.wait(timeout=0.5)

    def detach(self, root: str) -> None:
        self.signal_stop(root)
        with self._mutex:
            binding = self._bindings.get(Path(root))
            if binding is not None:
                binding.drained.wait(timeout=35)
                self._bindings.pop(Path(root), None)
        self._consent.detach(root)

    def signal_stop(self, root: str | None) -> None:
        with self._mutex:
            bindings = self._bindings.values() if root is None else (self._bindings.get(Path(root)),)
            for binding in bindings:
                if binding is None:
                    continue
                binding.stopped.set()
        self._wake.set()

    def shutdown(self) -> None:
        self._stopped.set()
        with self._mutex:
            for binding in self._bindings.values():
                binding.stopped.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=35)
        self._consent.shutdown()
