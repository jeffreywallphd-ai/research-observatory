"""Project-authorized local import intake and a bounded background worker pump.

Adapters are composed by the runtime, never supplied by an API caller. Every
bounded operation revalidates the open project. Recovery is reconciled before
the executor may recover leases or claim import work. Explicit commit requests
publish canonical source assertions, not reconciled Works.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from pydantic import TypeAdapter

from .domain_contracts import is_uuid_v7
from .import_review import ImportPreviewPage, ImportReview, bounded, preview_item
from .ingestion.commit_activity import ImportCommitActivity
from .ingestion.commit_workflow import (
    COMMIT_ACTIVITY,
    CommitJobInput,
    bind_commit_claim,
    build_commit_job,
    commit_job_input,
)
from .ingestion.import_summaries import SUMMARY_ACTIVITY
from .ingestion.preview_activity import ImportPreviewActivity
from .ingestion.preview_workflow import (
    ACTIVITY,
    PreviewIntentContext,
    ResumeEpoch,
    bind_preview_claim,
    build_preview_job,
    fingerprint,
    preview_job_input,
)
from .ingestion.source_chunks import put_source_chunk
from .ingestion.summary_activity import ImportSummaryActivity
from .ingestion.summary_workflow import SummaryJobInput, bind_summary_claim, build_summary_job, summary_job_input
from .logging import emit_log_record
from .ports.import_commits import ImportRepository
from .ports.import_previews import PreviewActor, PreviewCreate, PreviewProblem, PreviewState
from .ports.object_store import ObjectStore
from .ports.repositories import IntentRevisionRepository, UnitOfWorkFactory
from .ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobAuthority,
    WorkflowJobRecord,
    WorkflowQueueConflict,
    WorkflowQueueRepository,
)
from .privacy import ProjectPrivacyService
from .projects import ProjectLifecycleService
from .research_intents import validated_workflow_authority
from .workflow_executor import LocalWorkerAdmission, LocalWorkerSupervisor, WorkflowActivityError


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ImportProjectAdapters:
    previews: ImportRepository
    intents: IntentRevisionRepository
    queue: WorkflowQueueRepository
    store: ObjectStore
    units: UnitOfWorkFactory
    admission: LocalWorkerAdmission


@dataclass(slots=True)
class _Binding:
    path: Path
    project_id: str
    adapters: ImportProjectAdapters
    session_id: str = field(default_factory=lambda: secrets.token_hex(16))
    stopped: threading.Event = field(default_factory=threading.Event)
    drained: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.drained.set()


def _configuration(authority: WorkflowJobAuthority) -> tuple[str, str, str]:
    try:
        snapshot = json.loads(authority.snapshot_json)
        prefix, preview, epoch = snapshot["configuration"]["configurationId"].split(".")
        if prefix != "import-preview" or not is_uuid_v7(preview):
            raise ValueError
        TypeAdapter(ResumeEpoch).validate_python(epoch)
        revision = snapshot["intent"]["revisionId"]
        if not is_uuid_v7(revision):
            raise ValueError
        return preview, epoch, revision
    except ValueError, KeyError, TypeError:
        raise PreviewProblem("preview-runtime-configuration-invalid") from None


def _summary_configuration(authority: WorkflowJobAuthority) -> tuple[str, int, str, str]:
    try:
        snapshot = json.loads(authority.snapshot_json)
        prefix, preview, revision, epoch = snapshot["configuration"]["configurationId"].split(".")
        if prefix != "import-summary" or not is_uuid_v7(preview) or not revision.isascii() or not revision.isdecimal():
            raise ValueError
        number = int(revision)
        if str(number) != revision or not 1 <= number <= 2147483647:
            raise ValueError
        TypeAdapter(ResumeEpoch).validate_python(epoch)
        intent = snapshot["intent"]["revisionId"]
        if not is_uuid_v7(intent):
            raise ValueError
        return preview, number, epoch, intent
    except ValueError, KeyError, TypeError:
        raise PreviewProblem("preview-summary-configuration-invalid") from None


class ImportPreviewService:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        privacy: ProjectPrivacyService,
        adapters: Callable[[Path, str], ImportProjectAdapters],
        *,
        local_actor_id: str,
        resume_epoch: str,
        now: Callable[[], str] = _now,
    ):
        if not is_uuid_v7(local_actor_id):
            raise PreviewProblem("preview-local-actor-unavailable")
        self._epoch: str = TypeAdapter(ResumeEpoch).validate_python(resume_epoch)
        self._projects, self._privacy, self._adapters = projects, privacy, adapters
        self._actor_id, self._now = local_actor_id, now
        self._bindings: dict[Path, _Binding] = {}
        self._mutex = threading.RLock()
        self._runner = threading.Lock()
        self._stopped, self._wake = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None

    def actor(self, trace_id: str) -> PreviewActor:
        return PreviewActor(actor_id=self._actor_id, trace_id=trace_id, occurred_at=self._now())

    def _workflow_actor(self) -> WorkflowActor:
        return WorkflowActor(self._actor_id, "human", "local-researcher")

    def _binding(self, path: Path, identity: str) -> _Binding:
        with self._mutex:
            if self._stopped.is_set():
                raise PreviewProblem("preview-runtime-stopped")
            binding = self._bindings.get(path)
            if binding is None:
                binding = _Binding(path, identity, self._adapters(path, identity))
                self._bindings[path] = binding
            if binding.project_id != identity or binding.stopped.is_set():
                raise PreviewProblem("preview-project-session-changed")
            return binding

    def _action[Result](self, root: str, action: Callable[[_Binding], Result]) -> Result:
        return self._projects.perform_open_project_action(
            root=root,
            require_write=True,
            action=lambda path, identity: action(self._binding(path, identity)),
        )

    def _guard[Result](self, binding: _Binding, action: Callable[[], Result]) -> Result:
        def guarded(path: Path, identity: str) -> Result:
            if self._stopped.is_set() or binding.stopped.is_set():
                # Ordinary close drains the worker while the project remains
                # open; the fenced attempt may retry after explicit reopen.
                raise WorkflowActivityError("dependency-unavailable")
            if path != binding.path or identity != binding.project_id:
                raise PreviewProblem("preview-project-session-changed")
            return action()

        return self._projects.perform_open_project_action(root=str(binding.path), require_write=True, action=guarded)

    def attach(self, root: str) -> None:
        self._action(root, lambda _binding: None)
        self._wake.set()

    def native_context(self, root: str, project_id: str) -> str:
        def context(binding: _Binding) -> str:
            if binding.project_id != project_id:
                raise PreviewProblem("preview-project-session-changed")
            return binding.session_id

        return self._action(root, context)

    def in_native_session[Result](
        self, root: str, project_id: str, session_id: str, action: Callable[[], Result]
    ) -> Result:
        def guarded(binding: _Binding) -> Result:
            if binding.project_id != project_id or not secrets.compare_digest(binding.session_id, session_id):
                raise PreviewProblem("preview-project-session-changed")
            # Retain the project's reentrant lifecycle mutex through the bounded
            # action. Close/reopen cannot interleave between this check and I/O.
            return action()

        return self._action(root, guarded)

    def intake_status(self, root: str, preview_id: str) -> tuple[PreviewState, WorkflowJobRecord | None]:
        def status(binding: _Binding):
            state = binding.adapters.previews.read(preview_id)
            if not state.rights.permits("inspect"):
                raise PreviewProblem("preview-rights-denied")
            return state, binding.adapters.queue.find_idempotency(fingerprint(["import-preview/1", preview_id]))

        return self._action(root, status)

    def create(self, root: str, command: PreviewCreate):
        command = PreviewCreate.model_validate(command)
        trusted = command.model_copy(update={"actor": self.actor(command.actor.trace_id)})
        return self._action(root, lambda binding: binding.adapters.previews.create(trusted))

    def previews_page(self, root: str, *, after: str | None, limit: int) -> ImportPreviewPage:
        def page(binding: _Binding):
            states = binding.adapters.previews.previews_page(after=after, limit=limit)
            # The scan cursor is only an opaque preview identity. Names/content
            # of inspection-denied previews never cross this boundary.
            items = [
                preview_item(
                    state, binding.adapters.queue.find_idempotency(fingerprint(["import-preview/1", state.preview_id]))
                )
                for state in states
                if state.rights.permits("inspect")
            ]
            return bounded(
                ImportPreviewPage(
                    items=items, next_after=states[-1].preview_id if states else after, complete=len(states) < limit
                )
            )

        return self._action(root, page)

    def append_chunk(self, root: str, preview_id: str, *, ordinal: int, data: bytes) -> None:
        def append(binding: _Binding) -> None:
            state = binding.adapters.previews.read(preview_id)
            if state.state != "created":
                raise PreviewProblem("preview-intake-closed")
            chunk = put_source_chunk(binding.adapters.store, data, rights=state.rights, created_at=self._now())
            binding.adapters.previews.append_chunk(preview_id, ordinal=ordinal, chunk=chunk)

        self._action(root, append)

    def seal(
        self, root: str, preview_id: str, *, source_sha256: str, byte_length: int, chunk_count: int, trace_id: str
    ):
        return self._action(
            root,
            lambda binding: binding.adapters.previews.seal(
                preview_id,
                source_sha256=source_sha256,
                byte_length=byte_length,
                chunk_count=chunk_count,
                actor=self.actor(trace_id),
            ),
        )

    def _intent(self, binding: _Binding, revision: str | None = None) -> PreviewIntentContext:
        bridge = binding.adapters.intents.project_identity()
        if bridge is None or bridge.manifest_project_id != binding.project_id:
            raise PreviewProblem("preview-intent-project-mismatch")
        _, revisions, _, _ = validated_workflow_authority(
            binding.adapters.intents,
            expected_project_id=bridge.domain_project_id,
        )
        selected = next((item for item in revisions if revision is None or item["revisionId"] == revision), None)
        if selected is None or selected.get("projectId") != bridge.domain_project_id:
            raise PreviewProblem("preview-intent-context-unavailable")
        return PreviewIntentContext.model_validate(
            {
                "projectId": bridge.manifest_project_id,
                "domainProjectId": selected["projectId"],
                "intentId": selected["intentId"],
                "revisionId": selected["revisionId"],
                "contentHash": selected["revisionContentHash"],
                "status": selected["status"],
            }
        )

    def _inputs(self, binding: _Binding, preview: str, revision: str | None = None):
        policy = self._privacy.get(str(binding.path))
        if policy.project_id != binding.project_id:
            raise PreviewProblem("preview-policy-project-mismatch")
        return preview_job_input(
            binding.adapters.previews.read(preview),
            self._intent(binding, revision),
            fingerprint(policy.model_dump(mode="json", by_alias=True)),
            self._epoch,
        )

    def schedule(self, root: str, preview_id: str) -> WorkflowJobRecord:
        def schedule(binding: _Binding) -> WorkflowJobRecord:
            queue = binding.adapters.queue
            prior = queue.find_idempotency(fingerprint(["import-preview/1", preview_id]))
            if prior is not None:
                preview, epoch, _ = _configuration(queue.authority(prior.job_id))
                if preview != preview_id or epoch != self._epoch:
                    raise PreviewProblem("preview-resume-authority-changed")
                return prior
            inputs = self._inputs(binding, preview_id)
            submission = build_preview_job(inputs, actor=self._workflow_actor(), now=self._now())
            return queue.enqueue(submission, actor=self._workflow_actor())

        result = self._action(root, schedule)
        self._wake.set()
        return result

    def records_page(self, root: str, preview_id: str, *, after: int, limit: int):
        return self._action(
            root, lambda binding: binding.adapters.previews.records_page(preview_id, after=after, limit=limit)
        )

    def _summary_inputs(
        self, binding: _Binding, preview: str, revision: int, intent_revision: str | None = None
    ) -> SummaryJobInput:
        draft = binding.adapters.previews.draft(preview)
        if type(revision) is not int or draft.revision != revision:
            raise PreviewProblem("preview-draft-revision-conflict")
        policy = self._privacy.get(str(binding.path))
        if policy.project_id != binding.project_id:
            raise PreviewProblem("preview-policy-project-mismatch")
        return summary_job_input(
            binding.adapters.previews.read(preview),
            draft,
            self._intent(binding, intent_revision),
            fingerprint(policy.model_dump(mode="json", by_alias=True)),
            self._epoch,
        )

    def _active_summaries(self, binding: _Binding):
        after = None
        while page := binding.adapters.queue.active_jobs(activity_type=SUMMARY_ACTIVITY, after=after):
            yield from page
            after = page[-1].job_id

    def _active_commits(self, binding: _Binding):
        after = None
        while page := binding.adapters.queue.active_jobs(activity_type=COMMIT_ACTIVITY, after=after):
            yield from page
            after = page[-1].job_id

    def _summary_job(self, binding: _Binding, inputs: SummaryJobInput) -> WorkflowJobRecord | None:
        accepted = binding.adapters.previews.summary(inputs.preview.preview_id, revision=inputs.draft_revision)
        if accepted is not None:
            return binding.adapters.queue.get(accepted.job_id)
        queue = binding.adapters.queue
        selected = queue.find_idempotency(inputs.idempotency_key)
        if selected is not None and (job := queue.latest_continuation(selected.job_id)) is not None:
            authority = queue.authority(job.job_id)
            snapshot = json.loads(authority.snapshot_json)
            if snapshot["configuration"] != {
                "configurationId": inputs.configuration_id,
                "configurationVersion": inputs.configuration_version,
                "configurationHash": inputs.configuration_hash,
            }:
                raise PreviewProblem("preview-summary-job-authority-mismatch")
            selected = job
        return selected

    def schedule_summary(self, root: str, preview_id: str, *, revision: int) -> WorkflowJobRecord:
        def schedule(binding: _Binding) -> WorkflowJobRecord:
            inputs = self._summary_inputs(binding, preview_id, revision)
            prior = self._summary_job(binding, inputs)
            if prior is not None:
                return prior
            return binding.adapters.queue.enqueue(
                build_summary_job(inputs, actor=self._workflow_actor(), now=self._now()), actor=self._workflow_actor()
            )

        result = self._action(root, schedule)
        self._wake.set()
        return result

    def _commit_inputs(
        self,
        binding: _Binding,
        preview: str,
        revision: int,
        request_id: str,
        previous: str | None,
        intent_revision: str | None = None,
    ) -> CommitJobInput:
        summary = self._summary_inputs(binding, preview, revision, intent_revision)
        return commit_job_input(
            binding.adapters.previews.read(preview),
            binding.adapters.previews.draft(preview),
            summary.intent,
            summary.preview.policy_hash,
            self._epoch,
            request_id=request_id,
            previous_manifest_revision_id=previous,
        )

    def _stored_commit(self, binding: _Binding, authority: WorkflowJobAuthority) -> CommitJobInput:
        try:
            snapshot = json.loads(authority.snapshot_json)
            prefix, preview, request = snapshot["configuration"]["configurationId"].split(".")
            if prefix != "import-commit" or not is_uuid_v7(preview) or not is_uuid_v7(request):
                raise ValueError
            stored = binding.adapters.previews.commit_request(request)
            if stored is None or stored.inputs.preview.preview_id != preview:
                raise ValueError
            inputs = stored.inputs
            if snapshot["configuration"] != {
                "configurationId": inputs.configuration_id,
                "configurationVersion": inputs.configuration_version,
                "configurationHash": inputs.configuration_hash,
            }:
                raise ValueError
            return inputs
        except ValueError, KeyError, TypeError:
            raise PreviewProblem("preview-commit-request-authority-invalid") from None

    def _current_commit(self, binding: _Binding, inputs: CommitJobInput) -> None:
        if (
            self._commit_inputs(
                binding,
                inputs.preview.preview_id,
                inputs.draft_revision,
                inputs.request_id,
                inputs.previous_manifest_revision_id,
                inputs.intent.revision_id,
            )
            != inputs
        ):
            raise PreviewProblem("preview-commit-authority-changed")

    def _commit_job(self, binding: _Binding, inputs: CommitJobInput) -> WorkflowJobRecord | None:
        queue = binding.adapters.queue
        job = queue.find_idempotency(inputs.idempotency_key)
        if job is not None:
            job = queue.latest_continuation(job.job_id) or job
            if self._stored_commit(binding, queue.authority(job.job_id)) != inputs:
                raise PreviewProblem("preview-commit-job-authority-mismatch")
        return job

    def schedule_commit(
        self,
        root: str,
        preview_id: str,
        *,
        revision: int,
        request_id: str,
        previous_manifest_revision_id: str | None = None,
    ) -> WorkflowJobRecord:
        def schedule(binding: _Binding) -> WorkflowJobRecord:
            repository, queue = binding.adapters.previews, binding.adapters.queue
            stored = repository.commit_request(request_id)
            inputs = self._commit_inputs(
                binding,
                preview_id,
                revision,
                request_id,
                previous_manifest_revision_id,
                stored.inputs.intent.revision_id if stored else None,
            )
            repository.save_commit_request(inputs, actor=self.actor(request_id.replace("-", "")))
            prior = self._commit_job(binding, inputs)
            if prior is not None:
                return prior
            try:
                return queue.enqueue(
                    build_commit_job(inputs, actor=self._workflow_actor(), now=self._now()),
                    actor=self._workflow_actor(),
                )
            except WorkflowQueueConflict:
                # Another caller may have admitted this exact request after our
                # absence check. Authenticate its durable authority before reuse.
                winner = self._commit_job(binding, inputs)
                if winner is None:
                    raise
                return winner

        result = self._action(root, schedule)
        self._wake.set()
        return result

    def summary_status(self, root: str, preview_id: str, *, revision: int):
        def status(binding: _Binding):
            inputs = self._summary_inputs(binding, preview_id, revision)
            return binding.adapters.previews.summary(preview_id, revision=revision), self._summary_job(binding, inputs)

        return self._action(root, status)

    def cancel_summary(self, root: str, preview_id: str, *, revision: int, job_id: str) -> None:
        def cancel(binding: _Binding) -> None:
            queue = binding.adapters.queue
            preview, bound_revision, _, _ = _summary_configuration(queue.authority(job_id))
            if preview != preview_id or bound_revision != revision:
                raise PreviewProblem("preview-summary-job-authority-mismatch")
            job = queue.get(job_id)
            if job.state not in {"succeeded", "failed", "cancelled"}:
                queue.request_cancellation(
                    job_id,
                    actor=self._workflow_actor(),
                    now=self._now(),
                    reason_code="import-summary-cancelled",
                    interruption_kind="user-cancel",
                )

        self._action(root, cancel)
        self._wake.set()

    def review_action[Result](self, root: str, action: Callable[[ImportReview], Result]) -> Result:
        return self._action(root, lambda binding: action(ImportReview(binding.adapters.previews)))

    def cancel(self, root: str, preview_id: str, *, trace_id: str) -> None:
        def cancel(binding: _Binding) -> None:
            queue = binding.adapters.queue
            job = queue.find_idempotency(fingerprint(["import-preview/1", preview_id]))
            if job is not None and job.state not in {"succeeded", "failed", "cancelled"}:
                queue.request_cancellation(
                    job.job_id,
                    actor=self._workflow_actor(),
                    now=self._now(),
                    reason_code="import-preview-cancelled",
                    interruption_kind="user-cancel",
                )
            binding.adapters.previews.cancel(preview_id, actor=self.actor(trace_id))
            for summary in self._active_summaries(binding):
                preview, _, _, _ = _summary_configuration(queue.authority(summary.job_id))
                if preview == preview_id:
                    queue.request_cancellation(
                        summary.job_id,
                        actor=self._workflow_actor(),
                        now=self._now(),
                        reason_code="import-preview-cancelled",
                        interruption_kind="user-cancel",
                    )
            for commit in self._active_commits(binding):
                inputs = self._stored_commit(binding, queue.authority(commit.job_id))
                if inputs.preview.preview_id == preview_id:
                    queue.request_cancellation(
                        commit.job_id,
                        actor=self._workflow_actor(),
                        now=self._now(),
                        reason_code="import-preview-cancelled",
                        interruption_kind="user-cancel",
                    )

        self._action(root, cancel)

    def _reconcile(self, binding: _Binding) -> None:
        queue = binding.adapters.queue
        for activity in (ACTIVITY, SUMMARY_ACTIVITY, COMMIT_ACTIVITY):
            after: str | None = None
            while page := self._guard(binding, partial(queue.active_jobs, activity_type=activity, after=after)):
                for job in page:

                    def reconcile(job_id=job.job_id, kind=activity) -> None:
                        authority = queue.authority(job_id)
                        if kind == COMMIT_ACTIVITY:
                            epoch = self._stored_commit(binding, authority).preview.resume_epoch
                        else:
                            epoch = (
                                _configuration(authority)[1]
                                if kind == ACTIVITY
                                else _summary_configuration(authority)[2]
                            )
                        if epoch != self._epoch:
                            queue.request_cancellation(
                                job_id,
                                actor=self._workflow_actor(),
                                now=self._now(),
                                reason_code="resume-authority-changed",
                                interruption_kind="policy",
                            )

                    self._guard(binding, reconcile)
                after = page[-1].job_id

    def _run(self, binding: _Binding) -> None:
        adapters = binding.adapters
        self._reconcile(binding)

        def handler(context, claim):
            def authorize():
                authority = adapters.queue.authority(claim.job_id)
                preview, epoch, revision = _configuration(authority)
                if epoch != self._epoch:
                    raise PreviewProblem("preview-resume-authority-changed")
                return bind_preview_claim(authority, claim, self._inputs(binding, preview, revision))

            inputs = self._guard(binding, authorize)
            return ImportPreviewActivity(
                preview_id=inputs.preview_id,
                repository=adapters.previews,
                store=adapters.store,
                unit_of_work=adapters.units,
                guard=lambda action: self._guard(binding, action),
                trace_id=claim.job_id.replace("-", ""),
            )(context, claim)

        def summary_handler(context, claim):
            def authorize():
                authority = adapters.queue.authority(claim.job_id)
                preview, revision, epoch, intent = _summary_configuration(authority)
                if epoch != self._epoch:
                    raise PreviewProblem("preview-resume-authority-changed")
                continuation = json.loads(authority.snapshot_json).get("continuation")
                predecessor = None
                if continuation is not None:
                    source = continuation["sourceJobId"]
                    predecessor = (adapters.queue.get(source), adapters.queue.authority(source))
                return bind_summary_claim(
                    authority, claim, self._summary_inputs(binding, preview, revision, intent), predecessor=predecessor
                )

            inputs = self._guard(binding, authorize)

            def guarded(action):
                def current():
                    if (
                        self._summary_inputs(
                            binding, inputs.preview.preview_id, inputs.draft_revision, inputs.intent.revision_id
                        )
                        != inputs
                    ):
                        raise PreviewProblem("preview-summary-authority-changed")
                    return action()

                return self._guard(binding, current)

            return ImportSummaryActivity(
                inputs=inputs,
                repository=adapters.previews,
                unit_of_work=adapters.units,
                guard=guarded,
                trace_id=claim.job_id.replace("-", ""),
            )(context, claim)

        def commit_handler(context, claim):
            def authorize():
                authority = adapters.queue.authority(claim.job_id)
                inputs = self._stored_commit(binding, authority)
                self._current_commit(binding, inputs)
                continuation = json.loads(authority.snapshot_json).get("continuation")
                predecessor = None
                if continuation is not None:
                    source = continuation["sourceJobId"]
                    predecessor = adapters.queue.get(source), adapters.queue.authority(source)
                return bind_commit_claim(authority, claim, inputs, predecessor=predecessor)

            inputs = self._guard(binding, authorize)

            def guarded(action):
                def current():
                    self._current_commit(binding, inputs)
                    return action()

                return self._guard(binding, current)

            return ImportCommitActivity(
                inputs=inputs,
                repository=adapters.previews,
                guard=guarded,
                trace_id=claim.job_id.replace("-", ""),
            )(context, claim)

        supervisor = LocalWorkerSupervisor(
            adapters.queue,
            {ACTIVITY: handler, SUMMARY_ACTIVITY: summary_handler, COMMIT_ACTIVITY: commit_handler},
            concurrency_limits={"document": 1},
            now=self._now,
            recovery_actor=WorkflowActor(self._actor_id, "system", "workflow-coordinator"),
            admission=adapters.admission,
            activity_types=(ACTIVITY, SUMMARY_ACTIVITY, COMMIT_ACTIVITY),
        )
        supervisor.run_available()

    def run_pending(self) -> None:
        """One serialized pump pass, also usable in deterministic service tests."""
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
            if self._thread is not None or self._stopped.is_set():
                return
            self._thread = threading.Thread(target=self._pump, name="ro-import-pump", daemon=True)
            self._thread.start()

    def _pump(self) -> None:
        while not self._stopped.is_set():
            self._wake.clear()
            try:
                self.run_pending()
            except Exception:
                emit_log_record(
                    "import.worker-unavailable",
                    level="WARNING",
                    fields={"reasonCode": "local-import-worker-unavailable"},
                )
            self._wake.wait(0.5)

    def detach(self, root: str) -> None:
        # Resolve while still open, then signal/drain outside lifecycle locks.
        def resolve(path: Path, identity: str) -> _Binding | None:
            with self._mutex:
                binding = self._bindings.get(path)
                if binding is not None:
                    if binding.project_id != identity:
                        raise PreviewProblem("preview-project-session-changed")
                    binding.stopped.set()
                return binding

        binding = self._projects.perform_open_project_action(root=root, require_write=False, action=resolve)
        if binding is None:
            return
        if not binding.drained.wait(timeout=1.0):
            raise PreviewProblem("preview-worker-drain-pending")
        with self._mutex:
            if self._bindings.get(binding.path) is binding:
                self._bindings.pop(binding.path, None)

    def shutdown(self) -> None:
        self._stopped.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                raise PreviewProblem("preview-worker-drain-pending")
        if not self._runner.acquire(timeout=1.0):
            raise PreviewProblem("preview-worker-drain-pending")
        self._runner.release()
