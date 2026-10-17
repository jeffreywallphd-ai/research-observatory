"""Private Native-scoped search data adapter, composed only at Core startup."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .ingestion.preview_workflow import PreviewIntentContext
from .lexical_delivery import CoreLexicalResultService
from .lexical_index_repository import CoreLexicalIndexService
from .lexical_run_repository import SqliteLexicalRunRepository
from .lexical_search_worker import LexicalSearchActivity
from .lexical_source_repository import CanonicalIndexSources
from .ports.import_previews import PreviewProblem
from .ports.workflow_executor import WorkflowActor
from .repositories import sqlite_intent_authority_snapshot
from .research_intents import validated_workflow_authority
from .search import parse_query
from .search.delivery_values import SearchJob
from .search.run_values import SearchRequestInput


@dataclass(frozen=True, slots=True)
class _SessionScope:
    root: str
    project_id: str
    session_id: str


def _job(runs, record, command_id):
    return SearchJob(
        project_id=runs.project,
        command_id=command_id,
        job_id=record.job_id,
        workflow_run_id=record.workflow_run_id,
        state=record.state,
        attempt_count=record.attempt_count,
        cancellation_requested=record.cancellation_requested_at is not None,
        diagnostic_code=record.diagnostic_code,
    )


class SqliteLexicalSearchRepository:
    def __init__(self, documents, *, derivative_keys, database_keys):
        self.documents, self.derivative_keys, self.database_keys = documents, derivative_keys, database_keys

    def _intent(self, root):
        def current(binding):
            # Fresh for this guarded phase. All three authority components
            # share one canonical snapshot; nothing survives into a later call.
            reader = sqlite_intent_authority_snapshot(binding.path, binding.project_id)
            bridge = reader.project_identity()
            if bridge is None or bridge.manifest_project_id != binding.project_id:
                raise PreviewProblem("preview-intent-project-mismatch")
            _, revisions, _, _ = validated_workflow_authority(reader, expected_project_id=bridge.domain_project_id)
            selected = next(iter(revisions), None)
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

        return self.documents.imports._action(root, current)

    def _using(self, repository, root, session, action, *, orchestration=None):
        sources = CanonicalIndexSources(
            repository,
            resolve=lambda address: self.documents.attachments._corpus._source(Path(root), repository.project, address)[
                0
            ],
        )
        index = CoreLexicalIndexService(sources, self.derivative_keys, self.database_keys, orchestration=orchestration)
        index.catalog.now = self.documents.now
        runs = SqliteLexicalRunRepository(
            index,
            session_id=session,
            now=self.documents.now,
            intent=lambda: self._intent(root),
        )
        try:
            return action(runs)
        finally:
            index.close()

    def _scope(self, command, trace_id, action):
        # Core resolves current Native authority, as for the existing corpus
        # API; the renderer cannot supply a claimed session or actor.
        scope = _SessionScope(
            command.root, command.project_id, self.documents.imports.native_context(command.root, command.project_id)
        )
        return self.documents._scoped_repository(
            scope,
            trace_id,
            lambda repository, actor, stopped: self._using(
                repository, command.root, scope.session_id, lambda runs: action(runs, actor, stopped)
            ),
        )

    def submit(self, command, *, trace_id):
        query = parse_query(command.query)

        def submit(runs, actor, stopped):
            runs.index._check_cancel(stopped)
            inputs = SearchRequestInput(
                project_id=command.project_id,
                command_id=command.command_id,
                actor_id=actor.actor_id,
                session_id=runs.session_id,
                intent=runs.intent(),
                policy_sha256=actor.policy_sha256,
                query_document=query.to_json(),
                filters=command.filters,
            )
            return _job(runs, runs.submit(inputs), inputs.command_id)

        result = self._scope(command, trace_id, submit)
        self.documents.attach(command.root)
        return result

    def status(self, command, *, trace_id):
        def status(runs, _actor, stopped):
            runs.index._check_cancel(stopped)
            with runs.index.sources.corpus._transaction(write=True) as (db, _aggregates):
                inputs = runs._input(db, command.job_id)
                record = runs.queue._row(runs.queue._select_job(db, runs.project, command.job_id))
            if record.state == "succeeded":
                runs.result(command.job_id)
            return _job(runs, record, inputs.command_id)

        return self._scope(command, trace_id, status)

    def page(self, command, *, trace_id):
        return self._scope(
            command,
            trace_id,
            lambda runs, _actor, stopped: CoreLexicalResultService(runs).page(
                command.job_id, after=command.after, limit=command.limit, cancelled=stopped
            ),
        )

    def explain(self, command, *, trace_id):
        return self._scope(
            command,
            trace_id,
            lambda runs, _actor, stopped: CoreLexicalResultService(runs).explain(
                command.job_id, command.item_id, cancelled=stopped
            ),
        )

    def cancel(self, command, *, trace_id):
        def cancel(runs, actor, stopped):
            runs.index._check_cancel(stopped)
            with runs.index.sources.corpus._transaction(write=True) as (db, _aggregates):
                inputs = runs._input(db, command.job_id)
            return _job(
                runs,
                runs.queue.request_cancellation(
                    command.job_id,
                    actor=WorkflowActor(actor.actor_id, "human", "researcher"),
                    now=self.documents.now(),
                    reason_code="search-user-cancelled",
                    interruption_kind="user-cancel",
                ),
                inputs.command_id,
            )

        result = self._scope(command, trace_id, cancel)
        self.documents.wake.set()
        return result

    def run_activity(self, registration, context, claim, *, admission, trace_id):
        repository, _attachments, _actor = self.documents._repository(
            registration.root, registration.project_id, registration.session_id, trace_id
        )
        repository.bind_admission(admission)

        def orchestrate[T](action: Callable[[], T]) -> T:
            if registration.stopped():
                raise RuntimeError("search-session-stopped")
            repository.guard(lambda: None)
            result = action()
            if registration.stopped():
                raise RuntimeError("search-session-stopped")
            repository.guard(lambda: None)
            return result

        # The existing runner and registration own/drain this activity. Every
        # bounded source/catalog/read/publication guard reacquires exact current
        # Native/actor authority. Slow orchestration and joins retain protected
        # store/key/path holds, while foreground status/cancel can take the mutex.
        return self._using(
            repository,
            registration.root,
            registration.session_id,
            lambda runs: LexicalSearchActivity(runs, session_stopped=registration.stopped)(context, claim),
            orchestration=orchestrate,
        )
