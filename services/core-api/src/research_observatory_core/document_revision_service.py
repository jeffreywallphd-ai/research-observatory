"""Native document revision composition and one durable local parse pump."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .document_parse_worker import DocumentParseActivity
from .document_parse_workflow import DocumentParseInput
from .document_parser_runtime import InstalledDocumentParserRuntime
from .document_revisions import DocumentRevisionProblem
from .parsing.selection import ParserRegistry, RegisteredParser, SelectionSource, select_parser
from .ports.import_previews import PreviewProblem
from .ports.workflow_executor import WorkflowActor
from .workflow_executor import LocalWorkerSupervisor


def _now():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(slots=True)
class _Registration:
    root: str
    project_id: str
    session_id: str
    stop: Callable[[], bool]
    requested: threading.Event = field(default_factory=threading.Event)
    drained: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self):
        self.drained.set()

    def stopped(self):
        return self.requested.is_set() or self.stop()


class DocumentRevisionService:
    def __init__(
        self,
        attachments,
        imports,
        admission_factory,
        *,
        repository_factory,
        runtime=None,
        now=_now,
        reconciliation=None,
    ):
        self.attachments, self.imports, self.admission_factory = attachments, imports, admission_factory
        self.runtime, self.now = runtime or InstalledDocumentParserRuntime(), now
        self.repository_factory = repository_factory
        self.reconciliation = reconciliation
        self.registrations = {}
        self.mutex, self.runner = threading.RLock(), threading.Lock()
        self.stopped, self.wake = threading.Event(), threading.Event()
        self.thread = None

    def _repository(self, root, project, session, trace):
        selected, actor = self.attachments._action(
            root, project, session, trace, lambda service, actor: (service, actor)
        )
        current_actor = [actor]

        def guard(action):
            def current(_service, observed):
                if (observed.actor_id, observed.intent_revision_id, observed.intent_sha256, observed.policy_sha256) != (
                    actor.actor_id,
                    actor.intent_revision_id,
                    actor.intent_sha256,
                    actor.policy_sha256,
                ):
                    raise DocumentRevisionProblem("document-revision-authority-changed")
                current_actor[0] = observed
                return action()

            return self.attachments._action(root, project, session, trace, current)

        return (
            self.repository_factory(
                selected._database,
                project,
                selected._objects,
                actor=lambda: current_actor[0],
                guard=guard,
                now=self.now,
            ),
            selected,
            actor,
        )

    def attach(self, root):
        def current(binding):
            session = binding.session_id
            registration = _Registration(
                str(binding.path),
                binding.project_id,
                session,
                self.imports.native_stop_latch(str(binding.path), binding.project_id, session),
            )
            with self.mutex:
                prior = self.registrations.get(binding.path)
                if prior is not None:
                    if (prior.project_id, prior.session_id) != (binding.project_id, session):
                        raise PreviewProblem("preview-project-session-changed")
                    return
                self.registrations[binding.path] = registration

        self.imports._action(root, current)
        self.wake.set()

    def parse(self, command, *, trace_id):
        repository, _, actor = self._repository(command.root, command.project_id, command.session_id, trace_id)
        source = repository.source(command.attachment_id)
        installed = (
            self.runtime.load_text()
            if source.format == "plain-text"
            else self.runtime.load_native()
            if source.format in {"jats", "tei", "xml", "html"}
            else self.runtime.load()
        )
        selection = select_parser(
            (SelectionSource(source, "available", "primary"),),
            ParserRegistry((RegisteredParser(installed.descriptor, "available"),)),
            primary_attachment_id=source.attachment_id,
        )
        intent = self.imports._action(
            command.root, lambda binding: self.imports._intent(binding, actor.intent_revision_id)
        )
        inputs = DocumentParseInput(
            project_id=command.project_id,
            command_id=command.command_id,
            actor_id=actor.actor_id,
            session_id=command.session_id,
            source=source,
            selection=selection,
            intent=intent,
            policy_sha256=actor.policy_sha256,
        )
        result = repository.submit(inputs)
        self.attach(command.root)
        return result

    def _current(self, command, trace_id, action):
        repository, _, _ = self._repository(command.root, command.project_id, command.session_id, trace_id)
        return action(repository)

    def status(self, command, *, trace_id):
        return self._current(command, trace_id, lambda repository: repository.status(command.job_id))

    def result(self, command, *, trace_id):
        return self._current(command, trace_id, lambda repository: repository.result(command.result_id))

    def quality(self, command, *, trace_id):
        # Keep report materialization within the current Native lifecycle scope;
        # the stop latch is checked again before any derived projection escapes.
        return self._scoped_repository(
            command,
            trace_id,
            lambda repository, _actor, stopped: repository.quality(command.job_id, cancelled=stopped).model_dump(
                mode="json", by_alias=True
            ),
        )

    def _corrections(self, command, trace_id, action):
        from .document_corrections import MAX_CORRECTION_RECORD_BYTES
        from .document_revisions import protected_json
        from .document_viewer_allocations import viewer_revision_reads

        def scoped(repository, actor, stopped):
            correction = repository.corrections()
            # Metadata selects the exact original before any artifact is
            # decoded. Each adapter still enters its inspect+derive fence.
            source = correction.source_for_command(command)
            bounded = viewer_revision_reads(repository, source.byte_length) if source else repository

            def project_action(reconciler=None, observed=None, resolve=None, intent=None, path=None):
                if reconciler is not None and (
                    observed.actor_id,
                    observed.intent_sha256,
                    observed.policy_sha256,
                    intent.revision_id,
                    reconciler._project,
                    reconciler._database,
                    path,
                ) != (
                    actor.actor_id,
                    actor.intent_sha256,
                    actor.policy_sha256,
                    actor.intent_revision_id,
                    repository.project,
                    repository.database,
                    Path(command.root),
                ):
                    raise DocumentRevisionProblem("document-correction-authority-mismatch")

                def target(connection, match):
                    if reconciler is None or resolve is None:
                        raise DocumentRevisionProblem("document-correction-reference-authority-unavailable")
                    state = reconciler._state(connection, match.work_id)
                    if state.disposition != "active" or state.revision_id != match.work_revision_id:
                        raise DocumentRevisionProblem("document-correction-reference-authority-changed")
                    sources = reconciler._work_sources(connection, match.work_id, resolve)
                    if not sources:
                        raise DocumentRevisionProblem("document-correction-reference-authority-unavailable")
                    with bounded._aggregates(connection) as aggregates:
                        return aggregates.get_revision(state.revision_id)

                selected = bounded.corrections(target_resolver=target)
                result = action(selected, stopped, reconciler, resolve)
                wire = result.model_dump(mode="json", by_alias=True)
                if len(protected_json(result)) > MAX_CORRECTION_RECORD_BYTES or stopped():
                    raise DocumentRevisionProblem("document-correction-stopped-or-resource-limit")
                return wire

            if self.reconciliation is not None:
                return self.reconciliation._with_authority(command.root, trace_id, project_action)
            return project_action()

        return self._scoped_repository(command, trace_id, scoped)

    def correction_queue(self, command, *, trace_id):
        return self._corrections(
            command,
            trace_id,
            lambda repo, stopped, _r, _s: repo.queue(after_job_id=command.after_job_id, cancelled=stopped),
        )

    def correction_page(self, command, *, trace_id):
        return self._corrections(
            command,
            trace_id,
            lambda repo, stopped, _r, _s: repo.page(
                command.revision_id,
                draft_revision_id=command.draft_revision_id,
                offset=command.offset,
                cancelled=stopped,
            ),
        )

    def correction_save(self, command, *, trace_id):
        return self._corrections(
            command,
            trace_id,
            lambda repo, stopped, _r, _s: repo.draft_view(repo.save(command.correction, cancelled=stopped)),
        )

    def correction_accept(self, command, *, trace_id):
        return self._corrections(
            command,
            trace_id,
            lambda repo, stopped, _r, _s: repo.accepted_view(repo.accept(command.acceptance, cancelled=stopped)),
        )

    def correction_discard(self, command, *, trace_id):
        return self._corrections(
            command,
            trace_id,
            lambda repo, stopped, _r, _s: repo.draft_view(repo.discard(command.discard, cancelled=stopped)),
        )

    def correction_draft(self, command, *, trace_id):
        return self._corrections(
            command,
            trace_id,
            lambda repo, stopped, _r, _s: repo.draft_view(repo.read(command.draft_revision_id, cancelled=stopped)),
        )

    def correction_impact(self, command, *, trace_id):
        return self._corrections(
            command, trace_id, lambda repo, stopped, _r, _s: repo.impact(command.draft_revision_id, cancelled=stopped)
        )

    def correction_targets(self, command, *, trace_id):
        return self._corrections(
            command,
            trace_id,
            lambda repo, stopped, reconciler, resolve: repo.work_targets(
                command.after_work_id, reconciler, resolve, cancelled=stopped
            ),
        )

    def accept(self, command, *, trace_id):
        return self._current(command, trace_id, lambda repository: repository.accept(command.acceptance))

    def _reprocessing(self, command, trace_id, action):
        from .document_revisions import protected_json
        from .document_viewer_allocations import viewer_revision_reads

        def scoped(repository, actor, stopped):
            source = repository.reprocessing().source_for_command(command)
            bounded = viewer_revision_reads(repository, source.byte_length) if source else repository

            def project_action(reconciler=None, observed=None, resolve=None, intent=None, path=None):
                if reconciler is not None and (
                    observed.actor_id,
                    observed.intent_sha256,
                    observed.policy_sha256,
                    intent.revision_id,
                    reconciler._project,
                    reconciler._database,
                    path,
                ) != (
                    actor.actor_id,
                    actor.intent_sha256,
                    actor.policy_sha256,
                    actor.intent_revision_id,
                    repository.project,
                    repository.database,
                    Path(command.root),
                ):
                    raise DocumentRevisionProblem("document-reprocessing-authority-mismatch")

                def target(connection, match):
                    if reconciler is None or resolve is None:
                        raise DocumentRevisionProblem("document-reprocessing-reference-authority-unavailable")
                    state = reconciler._state(connection, match.work_id)
                    if (
                        state.disposition != "active"
                        or state.revision_id != match.work_revision_id
                        or not reconciler._work_sources(connection, match.work_id, resolve)
                    ):
                        raise DocumentRevisionProblem("document-reprocessing-reference-authority-changed")
                    with bounded._aggregates(connection) as aggregates:
                        return aggregates.get_revision(state.revision_id)

                selected = bounded.reprocessing(target_resolver=target)
                selected.session_id = command.session_id
                result = action(selected, stopped, lambda base: self._reprocessing_input(command, base, actor))
                wire = result.model_dump(mode="json", by_alias=True)
                if len(protected_json(result)) > 128 * 1024 or stopped():
                    raise DocumentRevisionProblem("document-reprocessing-stopped-or-resource-limit")
                return wire

            if self.reconciliation is not None:
                return self.reconciliation._with_authority(command.root, trace_id, project_action)
            return project_action()

        return self._scoped_repository(command, trace_id, scoped)

    def _reprocessing_input(self, command, base, actor):
        from .domain_contracts import new_uuid_v7

        source = base.result.binding.source
        installed = (
            self.runtime.load_text()
            if source.format == "plain-text"
            else self.runtime.load_native()
            if source.format in {"jats", "tei", "xml", "html"}
            else self.runtime.load()
        )
        selection = select_parser(
            (SelectionSource(source, "available", "primary"),),
            ParserRegistry((RegisteredParser(installed.descriptor, "available"),)),
            primary_attachment_id=source.attachment_id,
        )
        intent = self.imports._action(
            command.root, lambda binding: self.imports._intent(binding, actor.intent_revision_id)
        )
        return DocumentParseInput(
            project_id=command.project_id,
            command_id=new_uuid_v7(),
            actor_id=actor.actor_id,
            session_id=command.session_id,
            source=source,
            selection=selection,
            intent=intent,
            policy_sha256=actor.policy_sha256,
        )

    def reprocessing_queue(self, command, *, trace_id):
        return self._reprocessing(
            command, trace_id, lambda r, s, _f: r.queue(after_batch_id=command.after_batch_id, cancelled=s)
        )

    def reprocessing_create(self, command, *, trace_id):
        result = self._reprocessing(
            command, trace_id, lambda r, s, f: r.create(command.batch, input_factory=f, cancelled=s)
        )
        self.attach(command.root)
        return result

    def reprocessing_read(self, command, *, trace_id):
        return self._reprocessing(command, trace_id, lambda r, s, _f: r.read(command.batch_revision_id, cancelled=s))

    def reprocessing_compare(self, command, *, trace_id):
        return self._reprocessing(
            command,
            trace_id,
            lambda r, s, _f: r.compare(command.batch_revision_id, command.item_id, offset=command.offset, cancelled=s),
        )

    def reprocessing_reconcile(self, command, *, trace_id):
        return self._reprocessing(command, trace_id, lambda r, s, _f: r.reconcile(command.reconciliation, cancelled=s))

    def reprocessing_accept(self, command, *, trace_id):
        return self._reprocessing(command, trace_id, lambda r, s, _f: r.accept(command.acceptance, cancelled=s))

    def reprocessing_continue(self, command, *, trace_id):
        result = self._reprocessing(
            command, trace_id, lambda r, s, f: r.continue_item(command.continuation, input_factory=f, cancelled=s)
        )
        self.attach(command.root)
        return result

    def reprocessing_cancel(self, command, *, trace_id):
        return self._reprocessing(command, trace_id, lambda r, s, _f: r.cancel(command.cancellation, cancelled=s))

    def reprocessing_read_impact(self, command, *, trace_id):
        return self._reprocessing(
            command, trace_id, lambda r, s, _f: r.read_impact(command.batch_revision_id, command.item_id, cancelled=s)
        )

    def reprocessing_resume_impact(self, command, *, trace_id):
        return self._reprocessing(
            command,
            trace_id,
            lambda r, s, _f: r.resume_impact(
                command.batch_revision_id, command.item_id, command.expected_checkpoint_sha256, cancelled=s
            ),
        )

    def read(self, command, *, trace_id):
        return self._current(command, trace_id, lambda repository: repository.read(command.revision_id))

    def history(self, command, *, trace_id):
        return self._current(command, trace_id, lambda repository: repository.history(command.document_id))

    def _scoped_repository(self, command, trace_id, action):
        session_stop: list[Callable[[], bool]] = [lambda: True]

        def scoped(selected, actor):
            active = [True]
            stopped = session_stop[0]

            def guard(read):
                if not active[0] or stopped():
                    raise DocumentRevisionProblem("source-anchor-authority-scope-ended")
                # The enclosing _action holds the current native/project guard.
                # Repository writers still revalidate durable Intent/privacy/rights.
                return read()

            repository = self.repository_factory(
                selected._database,
                command.project_id,
                selected._objects,
                actor=lambda: guard(lambda: actor),
                guard=guard,
                now=self.now,
            )
            try:
                result = action(repository, actor, stopped)
                if stopped():
                    raise DocumentRevisionProblem("source-anchor-authority-scope-ended")
                return result
            finally:
                active[0] = False

        return self.attachments._action(
            command.root,
            command.project_id,
            command.session_id,
            trace_id,
            scoped,
            session_stop=lambda stopped: session_stop.__setitem__(0, stopped),
        )

    def _anchors(self, command, trace_id, action):
        return self._scoped_repository(
            command, trace_id, lambda repository, _actor, _stopped: action(repository.source_anchors())
        )

    def _references(self, command, trace_id, action, *, repository_factory=None):
        from .document_reference_repository import LocalDocumentReferenceRepository

        factory = repository_factory or LocalDocumentReferenceRepository

        if self.reconciliation is None:
            raise DocumentRevisionProblem("document-references-unavailable")

        def scoped(repository, actor, stopped):
            def current(reconciler, observed, resolve, intent, path):
                from .document_viewer_allocations import viewer_revision_reads

                if (
                    observed.actor_id,
                    observed.intent_sha256,
                    observed.policy_sha256,
                    intent.revision_id,
                    reconciler._project,
                    reconciler._database,
                    path,
                ) != (
                    actor.actor_id,
                    actor.intent_sha256,
                    actor.policy_sha256,
                    actor.intent_revision_id,
                    repository.project,
                    repository.database,
                    Path(command.root),
                ):
                    raise DocumentRevisionProblem("document-references-authority-mismatch")
                selected = factory(repository, resolve=resolve)
                source = selected._source(
                    command.enrichment.revision_id if hasattr(command, "enrichment") else command.revision_id
                )
                bounded = viewer_revision_reads(repository, source.byte_length)
                result = action(
                    factory(bounded, resolve=resolve, admit=bounded.objects.admit_bytes),
                    stopped,
                )
                if stopped():
                    raise DocumentRevisionProblem("document-references-scope-ended")
                return result

            # Reentrant lifecycle fence: actual import/connector rights resolver
            # remains current and never escapes the Native-owned source scope.
            return self.reconciliation._with_authority(command.root, trace_id, current)

        return self._scoped_repository(command, trace_id, scoped)

    def reference_enrich(self, command, *, trace_id):
        from .reference_reader import reader_page

        def enrich(repository, stopped):
            collection = repository.enrich(command.enrichment, cancelled=stopped)
            return reader_page(collection, repository._source(collection.document_revision_id))

        return self._references(command, trace_id, enrich)

    def references_read(self, command, *, trace_id):
        from .reference_reader import ReferenceReaderNotice, reader_page

        def read(repository, stopped):
            try:
                collection = repository.read(command.revision_id, cancelled=stopped)
            except DocumentRevisionProblem as problem:
                # Return only a current, rights-fenced opaque head so the user
                # can request a CAS refresh. No old protected reference leaks
                # through a stale, corrupted or unavailable matching snapshot.
                if stopped():
                    raise
                head = repository.current_head(command.revision_id)
                if head is None:
                    raise
                return ReferenceReaderNotice(
                    project_id=command.project_id,
                    source=repository._source(command.revision_id),
                    document_revision_id=command.revision_id,
                    collection_id=head[1],
                    collection_revision_id=head[0],
                    reason_code="viewer-resource-limit"
                    if problem.code == "viewer-resource-limit"
                    else "references-unavailable",
                )
            if collection is None:
                if command.expected_collection_revision_id is not None or command.after_order is not None:
                    raise DocumentRevisionProblem("document-references-page-unavailable")
                return None
            if (
                command.expected_collection_revision_id is not None
                and collection.collection_revision_id != command.expected_collection_revision_id
            ) or (command.after_order is not None and command.expected_collection_revision_id is None):
                raise DocumentRevisionProblem("document-references-page-changed")
            return reader_page(collection, repository._source(command.revision_id), after_order=command.after_order)

        return self._references(command, trace_id, read)

    def _citation_page(self, repository, collection, stopped, after_order=None):
        from .citation_reader import reader_page

        reference = repository.references.read(collection.document_revision_id, cancelled=stopped)
        accepted = repository.revisions.read(collection.document_revision_id)
        return reader_page(
            collection,
            repository._source(collection.document_revision_id),
            reference,
            accepted,
            after_order=after_order,
        )

    def citation_enrich(self, command, *, trace_id):
        from .citation_reader import reader_page
        from .document_citation_repository import LocalDocumentCitationRepository

        def enrich(repository, stopped):
            return repository.enrich(command.enrichment, cancelled=stopped, _deliver=reader_page)

        return self._references(command, trace_id, enrich, repository_factory=LocalDocumentCitationRepository)

    def citations_read(self, command, *, trace_id):
        from .citation_reader import CitationReaderNotice
        from .document_citation_repository import LocalDocumentCitationRepository

        def read(repository, stopped):
            try:
                collection = repository.read(command.revision_id, cancelled=stopped)
                if collection is None:
                    if command.expected_collection_revision_id is not None or command.after_order is not None:
                        raise DocumentRevisionProblem("document-citations-page-unavailable")
                    return None
                if (
                    command.expected_collection_revision_id is not None
                    and collection.collection_revision_id != command.expected_collection_revision_id
                ) or (command.after_order is not None and command.expected_collection_revision_id is None):
                    raise DocumentRevisionProblem("document-citations-page-changed")
                return self._citation_page(repository, collection, stopped, command.after_order)
            except DocumentRevisionProblem as problem:
                if stopped():
                    raise
                head = repository.current_head(command.revision_id)
                if head is None:
                    raise
                return CitationReaderNotice(
                    project_id=command.project_id,
                    source=repository._source(command.revision_id),
                    document_revision_id=command.revision_id,
                    collection_id=head[1],
                    collection_revision_id=head[0],
                    reason_code="viewer-resource-limit"
                    if problem.code == "viewer-resource-limit"
                    else "citations-unavailable",
                )

        return self._references(command, trace_id, read, repository_factory=LocalDocumentCitationRepository)

    def _table_figure_page(self, repository, collection, *, after_order=None, after_cell=None, cell_object_id=None):
        from .table_figure_reader import reader_page

        return reader_page(
            collection,
            repository._source(collection.document_revision_id),
            repository.revisions.read(collection.document_revision_id),
            after_order=after_order,
            after_cell=after_cell,
            cell_object_id=cell_object_id,
        )

    def table_figures_enrich(self, command, *, trace_id):
        from .document_table_figure_repository import LocalDocumentTableFigureRepository

        def enrich(repository, stopped):
            return self._table_figure_page(repository, repository.enrich(command.enrichment, cancelled=stopped))

        return self._references(command, trace_id, enrich, repository_factory=LocalDocumentTableFigureRepository)

    def table_figures_exclude(self, command, *, trace_id):
        from .document_table_figure_repository import LocalDocumentTableFigureRepository

        def exclude(repository, stopped):
            collection = repository.exclude(command.enrichment, cancelled=stopped)
            index = next(e.order for e in collection.entries if e.node_id == command.enrichment.node_id)
            return self._table_figure_page(repository, collection, after_order=index - 1 if index else None)

        return self._references(command, trace_id, exclude, repository_factory=LocalDocumentTableFigureRepository)

    def table_figures_read(self, command, *, trace_id):
        from .document_table_figure_repository import LocalDocumentTableFigureRepository
        from .table_figure_reader import TableFigureReaderNotice

        def read(repository, stopped):
            try:
                collection = repository.read(command.revision_id, cancelled=stopped)
                if collection is None:
                    if (
                        command.expected_collection_revision_id is not None
                        or command.after_order is not None
                        or command.after_cell is not None
                    ):
                        raise DocumentRevisionProblem("document-table-figures-page-unavailable")
                    return None
                if (
                    command.expected_collection_revision_id is not None
                    and collection.collection_revision_id != command.expected_collection_revision_id
                ):
                    raise DocumentRevisionProblem("document-table-figures-page-changed")
                return self._table_figure_page(
                    repository,
                    collection,
                    after_order=command.after_order,
                    after_cell=command.after_cell,
                    cell_object_id=command.cell_object_id,
                )
            except DocumentRevisionProblem as problem:
                if stopped():
                    raise
                head = repository.current_head(command.revision_id)
                if head is None:
                    raise
                return TableFigureReaderNotice(
                    project_id=command.project_id,
                    source=repository._source(command.revision_id),
                    document_revision_id=command.revision_id,
                    collection_id=head[1],
                    collection_revision_id=head[0],
                    reason_code="viewer-resource-limit"
                    if problem.code == "viewer-resource-limit"
                    else "table-figures-unavailable",
                )

        return self._references(command, trace_id, read, repository_factory=LocalDocumentTableFigureRepository)

    def anchor_create(self, command, *, trace_id):
        return self._anchors(
            command, trace_id, lambda repository: repository.create(command.command_id, command.selection)
        )

    def anchor_read(self, command, *, trace_id):
        def read(repository):
            anchor = repository.read(command.anchor_id)
            if anchor.target.revision_id != command.expected_revision_id:
                raise DocumentRevisionProblem("source-anchor-revision-mismatch")
            return anchor

        return self._anchors(command, trace_id, read)

    def anchor_resolve(self, command, *, trace_id):
        return self._anchors(
            command,
            trace_id,
            lambda repository: repository.resolve(command.anchor_id, expected_revision_id=command.expected_revision_id),
        )

    def citation_links(self, command, *, trace_id):
        return self._anchors(
            command,
            trace_id,
            lambda repository: repository.citation_links(
                command.revision_id,
                command.citation_id,
                after_reference_id=command.after_reference_id,
                limit=command.limit,
            ),
        )

    def reader_revisions(self, command, *, trace_id):
        return self._anchors(command, trace_id, lambda repository: repository.reader_revisions(command.attachment_id))

    def anchor_list(self, command, *, trace_id):
        return self._anchors(
            command,
            trace_id,
            lambda repository: repository.list(command.revision_id, after_id=command.after_id, limit=command.limit),
        )

    def reader_outline(self, command, *, trace_id):
        return self._anchors(
            command,
            trace_id,
            lambda repository: repository.outline(
                command.revision_id, after_node_id=command.after_node_id, limit=command.limit
            ),
        )

    def run_pending(self):
        with self.runner:
            with self.mutex:
                registrations = tuple(self.registrations.values())
            for registration in registrations:
                with self.mutex:
                    if self.stopped.is_set() or registration.stopped():
                        continue
                    registration.drained.clear()
                try:
                    trace = hashlib.sha256((registration.project_id + ":document-parse").encode()).hexdigest()[:32]
                    repository, _, actor = self._repository(
                        registration.root, registration.project_id, registration.session_id, trace
                    )
                    admission = self.admission_factory(Path(registration.root), registration.project_id)
                    repository.bind_admission(admission)

                    def execute(context, claim, repository=repository, registration=registration, actor=actor):
                        inputs = repository.claim_input(claim)
                        if inputs.session_id != registration.session_id or inputs.actor_id != actor.actor_id:
                            raise DocumentRevisionProblem("document-parse-session-changed")
                        return DocumentParseActivity(
                            repository, session_stopped=registration.stopped, runtime=self.runtime
                        )(context, claim)

                    LocalWorkerSupervisor(
                        repository.queue,
                        {"document-parse": execute},
                        concurrency_limits={"document": 1},
                        now=self.now,
                        recovery_actor=WorkflowActor(actor.actor_id, "system", "workflow-coordinator"),
                        admission=admission,
                        activity_types=("document-parse",),
                    ).run_available()
                finally:
                    registration.drained.set()

    def start(self):
        with self.mutex:
            if self.thread is None and not self.stopped.is_set():
                self.thread = threading.Thread(target=self._pump, name="ro-document-parse", daemon=True)
                self.thread.start()

    def _pump(self):
        while not self.stopped.is_set():
            self.wake.clear()
            try:
                self.run_pending()
            except Exception:
                from .logging import emit_log_record

                emit_log_record(
                    "document.parse-worker-unavailable",
                    level="WARNING",
                    fields={"reasonCode": "document-parse-worker-unavailable"},
                )
            self.wake.wait(0.5)

    def signal_stop(self, root=None):
        if root is None:
            self.stopped.set()
        with self.mutex:
            for registration in self.registrations.values():
                if root is None or Path(registration.root) == Path(root):
                    registration.requested.set()
        self.wake.set()

    def detach(self, root):
        self.signal_stop(root)
        with self.mutex:
            registration = self.registrations.get(Path(root))
        if registration is not None and not registration.drained.wait(timeout=1):
            raise PreviewProblem("preview-worker-drain-pending")
        with self.mutex:
            self.registrations.pop(Path(root), None)

    def shutdown(self):
        self.signal_stop()
        if self.thread is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise PreviewProblem("preview-worker-drain-pending")
