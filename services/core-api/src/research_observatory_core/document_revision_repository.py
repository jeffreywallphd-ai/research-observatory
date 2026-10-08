"""Protected retained parse output and explicit human canonical publication.

Inference, queue polling and heartbeats never run in these bounded writers.
Every protected read/publication rechecks the original exact copy and current
human Intent/privacy/rights under the native session guard.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

from .corpus_repository import SqliteCorpusRepository
from .document_attachment_repository import (
    LocalDocumentAttachmentService,
    LocalParserArtifactStager,
    _parser_attempt_intent,
    _sha,
)
from .document_parse_workflow import ACTIVITY_VERSION, DocumentParseInput, bind_claim, submission
from .document_revisions import (
    ACCEPTED_REVISION_MEDIA_TYPE,
    NORMALIZED_RESULT_MEDIA_TYPE,
    AcceptedDocumentRevision,
    DocumentRevisionAcceptance,
    DocumentRevisionProblem,
    RetainedParseResultReceipt,
    acceptance_eligible,
    canonicalize_structure,
    content_sha256,
    protected_json,
)
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .object_store import _LocalObjectStore
from .parsing.contracts import AcquisitionOrigin, LocalOrigin, SourceIdentity
from .parsing.normalization import MAX_IR_BYTES
from .parsing.requests import ParseRequest, ParseSuccess
from .parsing.source import LocalProtectedParseSource, source_identity
from .ports.acquisition import AcquisitionReceipt
from .ports.corpus import CorpusActor
from .ports.document_attachments import DocumentPublicationGuard
from .ports.object_store import ObjectPutCommand
from .ports.repositories import AggregateRevision, AggregateRevisionDraft, AtomicRepositoryEvent, MaterialDependency
from .ports.source_anchors import SourceAnchorRepository
from .ports.workflow_executor import WorkflowActor, WorkflowJobClaim, WorkflowOutputReference
from .repositories import (
    _UNIT_OF_WORKS,
    _projection_content_sha256,
    _SqliteAggregateRepository,
    _SqliteWorkflowQueueRepository,
)
from .storage import CanonicalConnection, open_canonical_database
from .workflow_executor import WorkflowAtomicCompletion


def _publication_step(_step: str) -> None:
    """Deterministic precommit interruption seam, without external I/O."""


@dataclass(frozen=True, slots=True)
class _ProtectedReceipt:
    object_sha256: str
    byte_length: int


class LocalDocumentRevisionRepository:
    def __init__(
        self,
        database: Path,
        project_id: str,
        objects: _LocalObjectStore,
        *,
        actor: Callable[[], CorpusActor],
        guard: DocumentPublicationGuard,
        now: Callable[[], str],
    ) -> None:
        if not database.is_absolute() or not callable(actor) or not callable(guard) or not callable(now):
            raise DocumentRevisionProblem("document-revision-configuration-invalid")
        self.database, self.project, self.objects = database, project_id, objects
        self.actor, self.guard, self.now = actor, guard, now
        self.queue = _SqliteWorkflowQueueRepository(database, project_id)
        self.corpus = SqliteCorpusRepository(database, project_id)

    def source_anchors(self) -> SourceAnchorRepository:
        from .source_anchor_repository import LocalSourceAnchorRepository

        return LocalSourceAnchorRepository(self)

    def _bounded(self, action):
        try:
            return self.guard(action)
        except DocumentRevisionProblem:
            raise
        except Exception:
            raise DocumentRevisionProblem("document-revision-denied") from None

    def bind_admission(self, admission):
        queue = admission.repository
        if (
            not isinstance(queue, _SqliteWorkflowQueueRepository)
            or queue._database != self.database
            or queue._project_id != self.project
        ):
            raise DocumentRevisionProblem("document-parse-admission-invalid")
        admission.validate(queue)
        self.queue = queue

    def source(self, attachment_id):
        def read():
            service = LocalDocumentAttachmentService(self.database, self.project, self.objects)
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
                self._authority(connection, self.actor())
                attachment = service._attachment(connection, attachment_id)
                candidate = service._candidate(connection, attachment.candidate_id)
                acquired = connection.execute(
                    "SELECT location_id,receipt_sha256,receipt_json FROM document_acquisition_sources "
                    "WHERE project_id=? AND candidate_id=?",
                    (self.project, attachment.candidate_id),
                ).fetchone()
                origin: LocalOrigin | AcquisitionOrigin = LocalOrigin(kind="local-import")
                if acquired is not None:
                    receipt = AcquisitionReceipt.model_validate_json(str(acquired[2]))
                    if (
                        _sha(receipt.model_dump(mode="json", by_alias=True)) != acquired[1]
                        or receipt.location_id != acquired[0]
                    ):
                        raise DocumentRevisionProblem("document-parse-source-invalid")
                    origin = AcquisitionOrigin(
                        kind="remote-acquisition", location_id=acquired[0], receipt_sha256=acquired[1]
                    )
                return source_identity(attachment, candidate, origin)

        return self._bounded(read)

    def parser_pipeline(self, context, request, runtime):
        from .document_parser_runtime import InstalledParserPipeline

        stager = LocalParserArtifactStager(
            self.database,
            self.objects,
            claim=context.claim,
            request=request,
            actor=self.actor,
            guard=self.guard,
            now=context.now,
        )
        return InstalledParserPipeline(
            stage_raw=stager, sources=LocalProtectedParseSource(self.objects, guard=self.guard), runtime=runtime
        )

    @contextmanager
    def _aggregates(self, connection: CanonicalConnection):
        token = _UNIT_OF_WORKS.register(connection, self.project)
        try:
            yield _SqliteAggregateRepository(token)
        finally:
            _UNIT_OF_WORKS.unregister(token)

    def _authority(self, connection, actor):
        self.corpus._command(new_uuid_v7(), "0" * 64, actor)
        self.corpus._authority(connection, actor)

    def _source_fenced(self, source: SourceIdentity, action):
        results = []
        actor = self.actor()

        def current(connection):
            self._authority(connection, actor)
            results.append(action(connection, actor))

        stream = self.objects._open_document_attachment(
            source.attachment_id,
            source.document_revision_id,
            actor=actor,
            expected_source=source,
            before_stream=current,
        )
        if stream is None:
            raise DocumentRevisionProblem("document-revision-denied")
        with stream:
            pass
        if len(results) != 1:
            raise DocumentRevisionProblem("document-revision-denied")
        return results[0]

    def _input(self, connection, job_id):
        row = connection.execute(
            "SELECT input_json,input_sha256,source_revision_id,actor_id,session_id,command_id "
            "FROM document_parse_jobs WHERE project_id=? AND job_id=?",
            (self.project, job_id),
        ).fetchone()
        if row is None:
            raise DocumentRevisionProblem("document-parse-job-unavailable")
        inputs = DocumentParseInput.model_validate_json(str(row[0]))
        if (
            inputs.configuration_hash != "sha256:" + str(row[1])
            or (inputs.source.document_revision_id, inputs.actor_id, inputs.session_id, inputs.command_id)
            != tuple(row[2:])
            or inputs.project_id != self.project
        ):
            raise DocumentRevisionProblem("document-parse-job-invalid")
        return inputs

    def submit(self, inputs: DocumentParseInput):
        inputs = DocumentParseInput.model_validate(inputs)

        def publish(connection, actor):
            if (
                inputs.project_id != self.project
                or inputs.actor_id != actor.actor_id
                or inputs.intent.revision_id != actor.intent_revision_id
                or inputs.intent.content_hash != "sha256:" + actor.intent_sha256
                or inputs.policy_sha256 != actor.policy_sha256
            ):
                raise DocumentRevisionProblem("document-parse-authority-changed")
            replay = connection.execute(
                "SELECT job_id,input_sha256 FROM document_parse_jobs WHERE project_id=? AND command_id=?",
                (self.project, inputs.command_id),
            ).fetchone()
            if replay is not None:
                if (
                    inputs.configuration_hash != "sha256:" + str(replay[1])
                    or self._input(connection, replay[0]) != inputs
                ):
                    raise DocumentRevisionProblem("document-parse-command-conflict")
                return self.queue._row(self.queue._select_job(connection, self.project, replay[0]))
            accepted = self.queue._enqueue_with_connection(
                connection,
                submission(inputs, now=self.now()),
                actor=WorkflowActor(actor.actor_id, "human", "researcher"),
            )
            connection.execute(
                "INSERT INTO document_parse_jobs VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    accepted.job_id,
                    self.project,
                    inputs.command_id,
                    inputs.source.document_revision_id,
                    protected_json(inputs).decode(),
                    inputs.configuration_hash.removeprefix("sha256:"),
                    actor.actor_id,
                    inputs.session_id,
                    self.now(),
                ),
            )
            return accepted

        return self._bounded(lambda: self._source_fenced(inputs.source, publish))

    def claim_input(self, claim: WorkflowJobClaim) -> DocumentParseInput:
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
            inputs = self._input(connection, claim.job_id)
        return bind_claim(self.queue.authority(claim.job_id), claim, inputs)

    def _raw_inputs(self, connection, aggregates, request, ir):
        rows = connection.execute(
            "SELECT a.artifact_id,a.revision_id,a.media_type,d.object_sha256,o.byte_length "
            "FROM workflow_attempt_artifacts a JOIN documents d "
            "ON d.project_id=a.project_id AND d.revision_id=a.revision_id "
            "JOIN object_records o ON o.project_id=d.project_id AND o.object_sha256=d.object_sha256 "
            "WHERE a.project_id=? AND a.job_id=? AND a.attempt_id=? AND a.role='diagnostic'",
            (self.project, request.binding.attempt.job_id, request.binding.attempt.attempt_id),
        ).fetchall()
        inputs = [aggregates.get_revision(request.binding.source.document_revision_id)]
        if not ir.raw_artifacts:
            raise DocumentRevisionProblem("document-parse-raw-receipt-missing")
        for receipt in ir.raw_artifacts:
            exact = [
                row
                for row in rows
                if (row[0], row[2], row[3], row[4])
                == (receipt.stage_id, receipt.media_type, receipt.object_sha256, receipt.byte_length)
            ]
            if len(exact) != 1:
                raise DocumentRevisionProblem("document-parse-raw-receipt-invalid")
            raw = self.objects._read_protected_document_artifact(connection, receipt, receipt.media_type)
            manifests = [row for row in rows if row[2] == "application/vnd.research-observatory.parser-attempt+json"]
            authenticated = False
            for row in manifests:
                intent = self.objects._read_parser_manifest(connection, _ProtectedReceipt(row[3], row[4]))
                document = json.loads(intent)
                derivative = document.get("derivative")
                page_index = None if derivative is None else derivative["pageIndex"]
                if intent == _parser_attempt_intent(request, raw, receipt.media_type, page_index):
                    authenticated = True
                    inputs.append(aggregates.get_revision(row[1]))
                    break
            if not authenticated:
                raise DocumentRevisionProblem("document-parse-raw-intent-invalid")
            inputs.append(aggregates.get_revision(exact[0][1]))
        return tuple({item.revision_id: item for item in inputs}.values())

    @staticmethod
    def _dependencies(inputs):
        return tuple(
            MaterialDependency(
                dependency_id=new_uuid_v7(),
                dependency_kind="human-decision" if item.aggregate_kind == "decision" else "source-revision",
                relation_type="direct",
                revision_id=item.revision_id,
                configuration_id=None,
                configuration_version=None,
                fingerprint=_projection_content_sha256(item),
                governing_policy_id="dependency.material.v1",
                governing_policy_version="1.0.0",
            )
            for item in inputs
        )

    @staticmethod
    def _event(actor, now, kind, key, *, worker_id=None):
        return AtomicRepositoryEvent(
            event_id=new_uuid_v7(),
            outbox_id=new_uuid_v7(),
            event_type=kind,
            occurred_at=now,
            available_at=now,
            trace_id=actor.trace_id,
            actor_type="human" if worker_id is None else "worker",
            actor_id=actor.actor_id if worker_id is None else worker_id,
            idempotency_key=key,
        )

    def _put(self, raw, media, source, action, stopped):
        digest = hashlib.sha256(raw).hexdigest()

        def inspect(_stream, observed, length):
            if (observed, length) != (digest, len(raw)):
                raise DocumentRevisionProblem("document-revision-object-invalid")
            return media

        return self.objects.put_parser_artifact(
            BytesIO(raw),
            ObjectPutCommand(
                media_type=media,
                rights_status="allowed",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="local-derivation",
                created_at=self.actor().occurred_at,
                expected_sha256=digest,
            ),
            inspect,
            source=source,
            actor=self.actor(),
            action=action,
            max_plaintext_bytes=MAX_IR_BYTES,
            cancellation_requested=stopped,
        )

    def retain(self, claim, request, result, *, stopped):
        request, result = ParseRequest.model_validate(request), ParseSuccess.model_validate(result)
        if result.binding != request.binding:
            raise DocumentRevisionProblem("document-parse-result-mismatch")
        raw = protected_json(result)

        def publish(connection, stored):
            actor, now = self.actor(), self.now()
            self._authority(connection, actor)
            inputs = self._input(connection, claim.job_id)
            if (
                inputs.request(claim) != request
                or actor.actor_id != inputs.actor_id
                or actor.intent_revision_id != inputs.intent.revision_id
                or actor.policy_sha256 != inputs.policy_sha256
                or stopped()
            ):
                raise DocumentRevisionProblem("document-parse-authority-changed")
            lease = self.queue._lease_row(connection, claim, now, states=("running",))
            self.queue._verify_attempt_capability(connection, claim)
            if lease[3] is not None:
                raise DocumentRevisionProblem("document-parse-cancelled")
            with self._aggregates(connection) as aggregates:
                predecessors = self._raw_inputs(connection, aggregates, request, result.ir)
                revision = aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=new_uuid_v7(),
                        aggregate_id=new_uuid_v7(),
                        aggregate_kind="document",
                        created_at=now,
                        modified_at=now,
                        display_label_observed="Retained normalized parse result",
                        display_label_normalized=None,
                        knowledge_status="extracted",
                        rights_status="allowed",
                        object_sha256=stored.object_sha256,
                        dependency_coverage="complete",
                        provenance_inputs=predecessors,
                        material_dependencies=self._dependencies(predecessors),
                    ),
                    self._event(
                        actor,
                        now,
                        "document.created",
                        "document-parse-result-" + claim.attempt_id,
                        worker_id=claim.worker_id,
                    ),
                    expected_revision=None,
                )
                receipt = RetainedParseResultReceipt(
                    result_id=revision.aggregate_id,
                    revision_id=revision.revision_id,
                    binding=result.binding,
                    object_sha256=stored.object_sha256,
                    byte_length=stored.byte_length,
                )
                connection.execute(
                    "INSERT INTO document_parse_results VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        receipt.result_id,
                        self.project,
                        receipt.revision_id,
                        claim.job_id,
                        claim.attempt_id,
                        receipt.object_sha256,
                        receipt.byte_length,
                        receipt.model_dump_json(by_alias=True),
                        now,
                    ),
                )
                output = WorkflowOutputReference(
                    revision.aggregate_id,
                    revision.revision_id,
                    _projection_content_sha256(revision),
                    NORMALIZED_RESULT_MEDIA_TYPE,
                    revision.aggregate_id,
                )
                self.queue._stage_artifact_with_connection(connection, claim, artifact=output, role="output", now=now)
                self.queue._complete_with_connection(connection, claim, outputs=(output,), now=now)
                _publication_step("normalized-result-completed")
                return receipt, WorkflowAtomicCompletion((output,))

        return self._bounded(
            lambda: self._put(raw, NORMALIZED_RESULT_MEDIA_TYPE, request.binding.source, publish, stopped)
        )

    def _receipt(self, connection, result_id):
        row = connection.execute(
            "SELECT receipt_json,revision_id,job_id,attempt_id,object_sha256,byte_length "
            "FROM document_parse_results WHERE project_id=? AND result_id=?",
            (self.project, result_id),
        ).fetchone()
        if row is None:
            raise DocumentRevisionProblem("document-parse-result-unavailable")
        receipt = RetainedParseResultReceipt.model_validate_json(str(row[0]))
        if (
            receipt.result_id != result_id
            or receipt.binding.source.project_id != self.project
            or receipt.binding.attempt.activity_version != ACTIVITY_VERSION
            or (
                receipt.revision_id,
                receipt.binding.attempt.job_id,
                receipt.binding.attempt.attempt_id,
                receipt.object_sha256,
                receipt.byte_length,
            )
            != tuple(row[1:])
        ):
            raise DocumentRevisionProblem("document-parse-result-invalid")
        return receipt

    def _result(self, connection, receipt):
        job, accepted = self.queue._accepted_status_with_connection(connection, receipt.binding.attempt.job_id)
        with self._aggregates(connection) as aggregates:
            revision = aggregates.get_revision(receipt.revision_id)
            output = WorkflowOutputReference(
                receipt.result_id,
                receipt.revision_id,
                _projection_content_sha256(revision),
                NORMALIZED_RESULT_MEDIA_TYPE,
                receipt.result_id,
            )
            if (
                job.state != "succeeded"
                or job.current_attempt_id != receipt.binding.attempt.attempt_id
                or accepted is None
                or accepted.activity_type != "document-parse"
                or accepted.outputs != (output,)
                or revision.aggregate_id != receipt.result_id
                or revision.object_sha256 != receipt.object_sha256
            ):
                raise DocumentRevisionProblem("document-parse-output-not-successful")
            result = ParseSuccess.model_validate_json(
                self.objects._read_protected_document_artifact(connection, receipt, NORMALIZED_RESULT_MEDIA_TYPE)
            )
            if result.binding != receipt.binding:
                raise DocumentRevisionProblem("document-parse-result-invalid")
            self._raw_inputs(
                connection,
                aggregates,
                ParseRequest(
                    schema_version="1.0",
                    binding=receipt.binding,
                    selection=self._input(connection, receipt.binding.attempt.job_id).selection,
                ),
                result.ir,
            )
            return result

    def _accepted(self, connection, revision_id):
        row = connection.execute(
            "SELECT revision_id,project_id,document_id,previous_revision_id,result_id,decision_id,"
            "decision_revision_id,command_id,command_sha256,object_sha256,"
            "content_sha256,structure_sha256,actor_id,accepted_at "
            "FROM document_normalized_revisions WHERE project_id=? AND revision_id=?",
            (self.project, revision_id),
        ).fetchone()
        if row is None:
            raise DocumentRevisionProblem("document-revision-unavailable")
        metadata = connection.execute(
            "SELECT byte_length FROM object_records WHERE project_id=? AND object_sha256=?", (self.project, row[9])
        ).fetchone()
        result = AcceptedDocumentRevision.model_validate_json(
            self.objects._read_protected_document_artifact(
                connection, _ProtectedReceipt(row[9], metadata[0]), ACCEPTED_REVISION_MEDIA_TYPE
            )
        )
        expected = (
            result.revision_id,
            result.project_id,
            result.document_id,
            result.previous_revision_id,
            result.result.result_id,
            result.decision_id,
            result.decision_revision_id,
            result.command_id,
            result.command_sha256,
            row[9],
            result.content_sha256,
            result.structure_sha256,
            result.accepted_by,
            result.accepted_at,
        )
        if result.project_id != self.project or result.revision_id != revision_id or tuple(row) != expected:
            raise DocumentRevisionProblem("document-revision-invalid")
        with self._aggregates(connection) as aggregates:
            revision = aggregates.get_revision(revision_id)
            previous = aggregates.get_revision(result.previous_revision_id)
            decision = aggregates.get_revision(result.decision_revision_id)
            if (
                revision.aggregate_id != result.document_id
                or revision.object_sha256 != row[9]
                or revision.modified_at != result.accepted_at
                or revision.knowledge_status != "extracted"
                or previous.aggregate_id != result.document_id
                or revision.revision != previous.revision + 1
                or decision.aggregate_id != result.decision_id
                or decision.aggregate_kind != "decision"
                or decision.modified_at != result.accepted_at
            ):
                raise DocumentRevisionProblem("document-revision-invalid")
        indexed = connection.execute(
            "SELECT element_id,project_id,revision_id,role,staged_id,element_order,parent_id,related_node_id,node_kind "
            "FROM document_structure_elements WHERE project_id=? AND revision_id=? ORDER BY element_id",
            (self.project, revision_id),
        ).fetchall()
        if [tuple(item) for item in indexed] != sorted(self._element_rows(result)):
            raise DocumentRevisionProblem("document-structure-index-invalid")
        for identity, kind in (
            (revision_id, "org.research-observatory.document.revision-recorded.v1"),
            (result.decision_revision_id, "org.research-observatory.decision.revision-recorded.v1"),
        ):
            events = connection.execute(
                "SELECT event_type,actor_type,actor_id,occurred_at FROM provenance_events "
                "WHERE project_id=? AND revision_id=?",
                (self.project, identity),
            ).fetchall()
            if [tuple(item) for item in events] != [(kind, "human", result.accepted_by, result.accepted_at)]:
                raise DocumentRevisionProblem("document-revision-decision-invalid")
        if self._receipt(connection, result.result.result_id) != result.result:
            raise DocumentRevisionProblem("document-revision-result-invalid")
        self._result(connection, result.result)
        return result

    def read(self, revision_id):
        if not is_uuid_v7(revision_id):
            raise DocumentRevisionProblem("document-revision-unavailable")

        def read():
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
                row = connection.execute(
                    "SELECT result_id FROM document_normalized_revisions WHERE project_id=? AND revision_id=?",
                    (self.project, revision_id),
                ).fetchone()
                if row is None:
                    raise DocumentRevisionProblem("document-revision-unavailable")
                source = self._receipt(connection, row[0]).binding.source
            return self._source_fenced(source, lambda connection, _actor: self._accepted(connection, revision_id))

        return self._bounded(read)

    def result(self, result_id):
        if not is_uuid_v7(result_id):
            raise DocumentRevisionProblem("document-parse-result-unavailable")

        def read():
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
                receipt = self._receipt(connection, result_id)
            return self._source_fenced(
                receipt.binding.source, lambda connection, _actor: (receipt, self._result(connection, receipt))
            )

        return self._bounded(read)

    def status(self, job_id):
        if not is_uuid_v7(job_id):
            raise DocumentRevisionProblem("document-parse-job-unavailable")

        def read():
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
                inputs = self._input(connection, job_id)

            def current(connection, _actor):
                job, output = self.queue._accepted_status_with_connection(connection, job_id)
                receipt = None
                if output is not None:
                    if len(output.outputs) != 1:
                        raise DocumentRevisionProblem("document-parse-output-not-successful")
                    receipt = self._receipt(connection, output.outputs[0].artifact_id)
                    self._result(connection, receipt)
                return job, receipt

            return self._source_fenced(inputs.source, current)

        return self._bounded(read)

    def history(self, document_id):
        if not is_uuid_v7(document_id):
            raise DocumentRevisionProblem("document-revision-unavailable")
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
            revisions = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT n.revision_id FROM document_normalized_revisions n "
                    "JOIN aggregate_revisions r USING(project_id,revision_id) "
                    "WHERE n.project_id=? AND n.document_id=? ORDER BY r.revision LIMIT 1001",
                    (self.project, document_id),
                )
            )
        if len(revisions) > 1000:
            raise DocumentRevisionProblem("document-history-limit")
        for revision in revisions:
            self.read(revision)
        return revisions

    def accept(self, command: DocumentRevisionAcceptance):
        command = DocumentRevisionAcceptance.model_validate(command)

        def accept():
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
                receipt = self._receipt(connection, command.result_id)

            def prepare(connection, actor):
                result = self._result(connection, receipt)
                if (
                    command.confirmation_sha256
                    != hashlib.sha256(receipt.model_dump_json(by_alias=True).encode()).hexdigest()
                ):
                    raise DocumentRevisionProblem("document-revision-confirmation-mismatch")
                semantic = hashlib.sha256(
                    protected_json(command) + protected_json(receipt) + actor.actor_id.encode()
                ).hexdigest()
                replay = connection.execute(
                    "SELECT revision_id,command_sha256,actor_id FROM document_normalized_revisions "
                    "WHERE project_id=? AND command_id=?",
                    (self.project, command.command_id),
                ).fetchone()
                if replay is not None:
                    if (replay[1], replay[2]) != (semantic, actor.actor_id):
                        raise DocumentRevisionProblem("document-revision-command-conflict")
                    return self._accepted(connection, replay[0])
                if not acceptance_eligible(result.ir):
                    raise DocumentRevisionProblem("document-structure-incomplete")
                with self._aggregates(connection) as aggregates:
                    current = aggregates.get(receipt.binding.source.document_id)
                    if current.revision_id != command.expected_current_revision_id:
                        raise DocumentRevisionProblem("document-revision-predecessor-changed")
                structure, identities = canonicalize_structure(result.ir)
                return (
                    AcceptedDocumentRevision(
                        project_id=self.project,
                        document_id=current.aggregate_id,
                        revision_id=new_uuid_v7(),
                        previous_revision_id=current.revision_id,
                        result=receipt,
                        decision_id=new_uuid_v7(),
                        decision_revision_id=new_uuid_v7(),
                        command_id=command.command_id,
                        command_sha256=semantic,
                        accepted_by=actor.actor_id,
                        accepted_at=actor.occurred_at,
                        intent_revision_id=actor.intent_revision_id,
                        intent_sha256=actor.intent_sha256,
                        policy_sha256=actor.policy_sha256,
                        content_sha256=content_sha256(structure),
                        structure_sha256=hashlib.sha256(protected_json(structure)).hexdigest(),
                        element_identities=identities,
                        structure=structure,
                    ),
                    semantic,
                    current,
                )

            prepared = self._source_fenced(receipt.binding.source, prepare)
            if isinstance(prepared, AcceptedDocumentRevision):
                return prepared
            accepted, semantic, predecessor = prepared
            raw = protected_json(accepted)

            def publish(connection, stored):
                actor = self.actor()
                self._authority(connection, actor)
                self._result(connection, receipt)
                if (actor.actor_id, actor.intent_revision_id, actor.intent_sha256, actor.policy_sha256) != (
                    accepted.accepted_by,
                    accepted.intent_revision_id,
                    accepted.intent_sha256,
                    accepted.policy_sha256,
                ):
                    raise DocumentRevisionProblem("document-revision-authority-changed")
                actor = replace(actor, occurred_at=accepted.accepted_at)
                replay = connection.execute(
                    "SELECT revision_id,command_sha256,actor_id FROM document_normalized_revisions "
                    "WHERE project_id=? AND command_id=?",
                    (self.project, command.command_id),
                ).fetchone()
                if replay is not None:
                    if (replay[1], replay[2]) != (semantic, actor.actor_id):
                        raise DocumentRevisionProblem("document-revision-command-conflict")
                    return self._accepted(connection, replay[0])
                with self._aggregates(connection) as aggregates:
                    current = aggregates.get(accepted.document_id)
                    if current != predecessor:
                        raise DocumentRevisionProblem("document-revision-predecessor-changed")
                    retained = aggregates.get_revision(receipt.revision_id)
                    inputs: tuple[AggregateRevision, ...] = (current, retained)
                    decision = aggregates.append(
                        AggregateRevisionDraft(
                            revision_id=accepted.decision_revision_id,
                            aggregate_id=accepted.decision_id,
                            aggregate_kind="decision",
                            created_at=accepted.accepted_at,
                            modified_at=accepted.accepted_at,
                            display_label_observed="Accept document structure",
                            display_label_normalized=None,
                            knowledge_status="observed",
                            rights_status="allowed",
                            dependency_coverage="complete",
                            provenance_inputs=inputs,
                            material_dependencies=self._dependencies(inputs),
                        ),
                        self._event(
                            actor,
                            accepted.accepted_at,
                            "decision.created",
                            "document-structure-decision-" + command.command_id,
                        ),
                        expected_revision=None,
                    )
                    inputs = (*inputs, decision)
                    aggregates.append(
                        AggregateRevisionDraft(
                            revision_id=accepted.revision_id,
                            aggregate_id=current.aggregate_id,
                            aggregate_kind="document",
                            created_at=current.created_at,
                            modified_at=accepted.accepted_at,
                            display_label_observed=current.display_label_observed,
                            display_label_normalized=current.display_label_normalized,
                            knowledge_status="extracted",
                            rights_status="allowed",
                            object_sha256=stored.object_sha256,
                            dependency_coverage="complete",
                            provenance_inputs=inputs,
                            material_dependencies=self._dependencies(inputs),
                        ),
                        self._event(
                            actor,
                            accepted.accepted_at,
                            "document.updated",
                            "document-structure-accept-" + command.command_id,
                        ),
                        expected_revision=current.revision,
                    )
                    connection.execute(
                        "INSERT INTO document_normalized_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            accepted.revision_id,
                            self.project,
                            accepted.document_id,
                            accepted.previous_revision_id,
                            receipt.result_id,
                            accepted.decision_id,
                            accepted.decision_revision_id,
                            command.command_id,
                            semantic,
                            stored.object_sha256,
                            accepted.content_sha256,
                            accepted.structure_sha256,
                            actor.actor_id,
                            accepted.accepted_at,
                        ),
                    )
                    self._elements(connection, accepted)
                    _publication_step("accepted-structure-complete")
                return accepted

            return self._put(raw, ACCEPTED_REVISION_MEDIA_TYPE, receipt.binding.source, publish, lambda: False)

        return self._bounded(accept)

    def _element_rows(self, accepted):
        mapping = {(item.role, item.canonical_id): item.staged_id for item in accepted.element_identities}
        rows = []

        def insert(role, identity, order, parent=None, related=None, kind=None):
            rows.append(
                (
                    identity,
                    self.project,
                    accepted.revision_id,
                    role,
                    mapping[role, identity],
                    order,
                    parent,
                    related,
                    kind,
                ),
            )

        for index, item in enumerate(accepted.structure.text_projections):
            insert("projection", item.projection_id, index)
        saved = set()
        # The canonical contract already requires parent-before-child order.
        # Retain that order in one pass, including inside the canonical writer.
        for item in accepted.structure.nodes:
            parent = item.parent_id
            if parent is not None and parent not in saved:
                raise DocumentRevisionProblem("document-structure-cycle")
            insert("node", item.node_id, item.order, parent, kind=item.kind)
            saved.add(item.node_id)
        for item in accepted.structure.references:
            insert("reference", item.reference_id, item.order, related=item.node_id)
        for index, item in enumerate(accepted.structure.citations):
            insert("citation", item.citation_id, index, related=item.node_id)
        return rows

    def _elements(self, connection, accepted):
        connection.executemany(
            "INSERT INTO document_structure_elements VALUES (?,?,?,?,?,?,?,?,?)", self._element_rows(accepted)
        )
