"""Bounded local scholarly derivation under current Core project authority."""

from collections.abc import Callable
from pathlib import Path

from .connectors.broker import utc_now
from .domain_contracts import is_uuid_v7
from .ingestion.preview_workflow import fingerprint
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
from .research_intents import validated_workflow_authority


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
    ):
        if not is_uuid_v7(actor_id):
            raise ReconciliationProblem("reconciliation-actor-unavailable")
        self._projects, self._privacy = projects, privacy
        self._imports, self._connectors = imports, connectors
        self._repository, self._intents = repository_factory, intent_factory
        self._actor, self._now = actor_id, now

    def _action(self, root, trace_id, action):
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

                return action(self._repository(path, identity), actor, resolve)
            except RepositoryProblem, PrivacyPolicyProblem:
                raise ReconciliationProblem("reconciliation-authority-unavailable") from None

        # Keep current policy/Intent, local rights resolution and publication in
        # one lifecycle critical section. No network operation is admitted here.
        return self._projects.perform_open_project_action(root=root, require_write=True, action=guarded)

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
