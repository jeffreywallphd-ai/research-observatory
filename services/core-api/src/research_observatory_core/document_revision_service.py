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
    def __init__(self, attachments, imports, admission_factory, *, repository_factory, runtime=None, now=_now):
        self.attachments, self.imports, self.admission_factory = attachments, imports, admission_factory
        self.runtime, self.now = runtime or InstalledDocumentParserRuntime(), now
        self.repository_factory = repository_factory
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

    def accept(self, command, *, trace_id):
        return self._current(command, trace_id, lambda repository: repository.accept(command.acceptance))

    def read(self, command, *, trace_id):
        return self._current(command, trace_id, lambda repository: repository.read(command.revision_id))

    def history(self, command, *, trace_id):
        return self._current(command, trace_id, lambda repository: repository.history(command.document_id))

    def _anchors(self, command, trace_id, action):
        from .anchors.repository import LocalSourceAnchorRepository

        return self._current(command, trace_id, lambda repository: action(LocalSourceAnchorRepository(repository)))

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
