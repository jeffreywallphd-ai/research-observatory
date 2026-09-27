"""Bounded local scholarly derivation under current Core project authority."""

from collections.abc import Callable
from pathlib import Path

from .connectors.broker import utc_now
from .domain_contracts import is_uuid_v7
from .ingestion.preview_workflow import PreviewIntentContext, fingerprint
from .ports.reconciliation import (
    ReconciliationActor,
    ReconciliationConnectorSourceService,
    ReconciliationRepository,
    ReconciliationSourceService,
)
from .ports.repositories import IntentRevisionRepository, RepositoryProblem
from .privacy import PrivacyPolicyProblem, ProjectPrivacyService
from .projects import ProjectLifecycleService
from .reconciliation.contracts import (
    ReconciliationInspection,
    ReconciliationProblem,
    ReconciliationResult,
    SourceAddress,
)
from .reconciliation.decisions import ReviewCommand, ReviewContext, ReviewOutcome, ReviewPlan, ReviewPreview
from .reconciliation_worker import ReconciliationBatchAdapters, ReconciliationBatchWorker
from .research_intents import validated_workflow_authority
from .task_center import TaskCenterService


class ReconciliationService:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        privacy: ProjectPrivacyService,
        *,
        imports: ReconciliationSourceService,
        connectors: ReconciliationConnectorSourceService,
        repository_factory: Callable[[Path, str], ReconciliationRepository],
        intent_factory: Callable[[Path, str], IntentRevisionRepository],
        actor_id: str,
        now: Callable[[], str] = utc_now,
        batch_adapter_factory: Callable[[Path, str], ReconciliationBatchAdapters] | None = None,
        resume_epoch: str | None = None,
    ):
        if not is_uuid_v7(actor_id):
            raise ReconciliationProblem("reconciliation-actor-unavailable")
        self._projects, self._privacy = projects, privacy
        self._imports, self._connectors = imports, connectors
        self._repository, self._intents = repository_factory, intent_factory
        self._actor, self._now = actor_id, now
        if (batch_adapter_factory is None) != (resume_epoch is None):
            raise ReconciliationProblem("reconciliation-runtime-authority-unavailable")
        self._batch = (
            ReconciliationBatchWorker(
                projects,
                self._with_authority,
                batch_adapter_factory,
                imports=imports,
                connectors=connectors,
                actor_id=actor_id,
                resume_epoch=resume_epoch,
                now=now,
            )
            if batch_adapter_factory is not None and resume_epoch is not None
            else None
        )

    def _with_authority(self, root, trace_id, action):
        def guarded(path: Path, identity: str):
            try:
                intents = self._intents(path, identity)
                bridge = intents.project_identity()
                if bridge is None or bridge.manifest_project_id != identity:
                    raise ReconciliationProblem("reconciliation-intent-unavailable")
                _, revisions, _, _ = validated_workflow_authority(intents, expected_project_id=bridge.domain_project_id)
                if (
                    not revisions
                    or revisions[0].get("status") != "accepted"
                    or revisions[0].get("projectId") != bridge.domain_project_id
                ):
                    raise ReconciliationProblem("reconciliation-intent-unavailable")
                policy = self._privacy.get(str(path))
                if policy.project_id != identity:
                    raise ReconciliationProblem("reconciliation-policy-unavailable")
                actor = ReconciliationActor(
                    self._actor,
                    trace_id,
                    self._now(),
                    str(revisions[0]["revisionContentHash"]).removeprefix("sha256:"),
                    fingerprint(policy.model_dump(mode="json", by_alias=True)).removeprefix("sha256:"),
                )

                def resolve(address):
                    service = self._imports if address.kind == "import-member" else self._connectors
                    return service.reconciliation_source(str(path), address)

                intent = PreviewIntentContext.model_validate(
                    {
                        "projectId": identity,
                        "domainProjectId": bridge.domain_project_id,
                        "intentId": revisions[0]["intentId"],
                        "revisionId": revisions[0]["revisionId"],
                        "contentHash": revisions[0]["revisionContentHash"],
                        "status": revisions[0]["status"],
                    }
                )
                return action(self._repository(path, identity), actor, resolve, intent, path)
            except RepositoryProblem, PrivacyPolicyProblem:
                raise ReconciliationProblem("reconciliation-authority-unavailable") from None

        # Keep current policy/Intent, local rights resolution and publication in
        # one lifecycle critical section. No network operation is admitted here.
        return self._projects.perform_open_project_action(root=root, require_write=True, action=guarded)

    def _action(self, root, trace_id, action):
        return self._with_authority(
            root, trace_id, lambda repository, actor, resolve, _intent, _path: action(repository, actor, resolve)
        )

    def _worker(self) -> ReconciliationBatchWorker:
        if self._batch is None:
            raise ReconciliationProblem("reconciliation-runtime-unavailable")
        return self._batch

    def prepare_batch(self, root: str, *, trace_id: str) -> str:
        return self._worker().prepare(root, trace_id)

    def schedule_batch(self, root: str, request_id: str, *, trace_id: str):
        return self._worker().schedule(root, request_id, trace_id)

    def batch_status(self, root: str, *, request_id: str, job_id: str):
        return self._worker().status(root, request_id, job_id)

    def cancel_batch(self, root: str, *, request_id: str, job_id: str) -> None:
        self._worker().cancel(root, request_id, job_id)

    def cancel_workflow[Result](self, root: str, *, action: Callable[[], Result], **authority) -> Result:
        if self._batch is None:
            return action()
        return self._batch.cancel_workflow(root, action=action, **authority)

    def request_publication_stop(self, root: str, **authority) -> None:
        if self._batch is not None:
            self._batch.request_publication_stop(root, **authority)

    def active_task_center(self, root: str, *, limit: int):
        if self._batch is None:
            return None
        return self._batch.read_active_queue(
            root, lambda queue: TaskCenterService.page_from_authorized_queue(queue, limit=limit)
        )

    def signal_stop(self, root: str | None = None) -> None:
        if self._batch is not None:
            self._batch.signal_stop(root)

    def attach(self, root: str) -> None:
        if self._batch is not None:
            self._batch.attach(root)

    def detach(self, root: str) -> None:
        if self._batch is not None:
            self._batch.detach(root)

    def start(self) -> None:
        if self._batch is not None:
            self._batch.start()

    def shutdown(self) -> None:
        if self._batch is not None:
            self._batch.shutdown()

    def run_pending(self) -> None:
        self._worker().run_pending()

    def reconcile(self, root: str, source: SourceAddress, *, command_id: str, trace_id: str) -> ReconciliationResult:
        return self._action(
            root,
            trace_id,
            lambda repository, actor, resolve: repository.reconcile(
                source, command_id=command_id, actor=actor, resolve=resolve
            ),
        )

    def inspect(self, root: str, revision_id: str, *, trace_id: str) -> ReconciliationInspection:
        return self._action(
            root, trace_id, lambda repository, actor, resolve: repository.inspect(revision_id, resolve=resolve)
        )

    def inspect_candidates(self, root: str, revision_id: str, *, after: int, limit: int, trace_id: str):
        return self._action(
            root,
            trace_id,
            lambda repository, actor, resolve: repository.inspect_candidates(
                revision_id, after=after, limit=limit, resolve=resolve
            ),
        )

    def connector_address(self, root: str, preview_id: str, ordinal: int, *, trace_id: str) -> SourceAddress:
        return self._action(
            root,
            trace_id,
            lambda repository, actor, resolve: self._connectors.reconciliation_address(root, preview_id, ordinal),
        )

    def review_context(
        self, root: str, work_ids: tuple[str, ...], *, unassigned: tuple[str, ...], trace_id: str
    ) -> ReviewContext:
        return self._action(
            root,
            trace_id,
            lambda repository, actor, resolve: repository.review_context(
                work_ids, unassigned=unassigned, resolve=resolve
            ),
        )

    def preview_review(self, root: str, plan: ReviewPlan, *, trace_id: str) -> ReviewPreview:
        return self._action(
            root,
            trace_id,
            lambda repository, actor, resolve: repository.preview_review(plan, actor=actor, resolve=resolve),
        )

    def review(self, root: str, command: ReviewCommand, *, trace_id: str) -> ReviewOutcome:
        return self._action(
            root, trace_id, lambda repository, actor, resolve: repository.review(command, actor=actor, resolve=resolve)
        )
