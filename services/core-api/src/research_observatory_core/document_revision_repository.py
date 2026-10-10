"""Protected retained parse output and explicit human canonical publication.

Inference, queue polling and heartbeats never run in these bounded writers.
Every protected read/publication rechecks the original exact copy and current
human Intent/privacy/rights under the native session guard.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import dataclass, field, replace
from io import BytesIO
from pathlib import Path
from typing import Literal

from . import document_reprocessing as reprocessing
from .corpus_repository import SqliteCorpusRepository
from .document_attachment_repository import (
    LocalDocumentAttachmentService,
    LocalParserArtifactStager,
    _parser_attempt_intent,
    _sha,
)
from .document_correction_lineage import CorrectionSourceLineage
from .document_correction_views import (
    CorrectionAcceptedView,
    CorrectionDraftSelector,
    CorrectionDraftView,
    CorrectionImpactItem,
    CorrectionImpactView,
    CorrectionNodeView,
    CorrectionPage,
    CorrectionQueue,
    CorrectionQueueItem,
)
from .document_corrections import (
    CORRECTION_MEDIA_TYPE,
    MAX_CORRECTION_ITEMS,
    MAX_CORRECTION_RECORD_BYTES,
    CorrectionAcceptance,
    CorrectionDiscard,
    CorrectionDraft,
    CorrectionInheritance,
    CorrectionPreviewBase,
    CorrectionSave,
    apply_correction,
    value_sha256,
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
from .parsing.quality import ParsingQualityReport, assess_ir, unavailable_assessment
from .parsing.requests import ParseRequest, ParseSuccess
from .parsing.selection import selected_values, selection_sha256
from .parsing.source import LocalProtectedParseSource, source_identity
from .ports.acquisition import AcquisitionReceipt
from .ports.corpus import CorpusActor
from .ports.document_attachments import DocumentPublicationGuard
from .ports.object_store import ObjectPutCommand
from .ports.repositories import (
    DEFAULT_DEPENDENCY_IMPACT_LIMITS,
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyChange,
    MaterialDependency,
)
from .ports.source_anchors import SourceAnchorRepository
from .ports.workflow_executor import WorkflowActor, WorkflowJobClaim, WorkflowOutputReference
from .repositories import (
    _UNIT_OF_WORKS,
    _projection_content_sha256,
    _SqliteAggregateRepository,
    _SqliteDependencyImpactRepository,
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


@dataclass(slots=True)
class _CorrectionReadContext:
    """Only immutable authenticated values in one held connection/read fence.

    Never memoizes current heads, rights, project/session authority or a writer.
    It is detached at the end of this bounded call, not a process/global cache.
    """

    connection: CanonicalConnection
    project_id: str
    accepted: dict[str, AcceptedDocumentRevision] = field(default_factory=dict)
    drafts: dict[str, CorrectionDraft] = field(default_factory=dict)
    inheritance: dict[str, CorrectionInheritance] = field(default_factory=dict)
    accepted_drafts: dict[str, CorrectionDraft] = field(default_factory=dict)
    lineages: dict[str, CorrectionSourceLineage] = field(default_factory=dict)
    deadline: float = field(default_factory=lambda: time.monotonic() + 5.0)

    def check(self, connection, project_id):
        if connection is not self.connection or project_id != self.project_id or time.monotonic() > self.deadline:
            raise DocumentRevisionProblem("document-correction-read-scope-invalid")


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

    def corrections(self, *, target_resolver=None):
        return LocalDocumentCorrectionRepository(self, target_resolver=target_resolver)

    def reprocessing(self, *, target_resolver=None):
        return LocalDocumentReprocessingRepository(self, target_resolver=target_resolver)

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

    def submit(self, inputs: DocumentParseInput, *, admission=None):
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
            if admission is not None:
                # Reprocessing owns this internal admission condition. It runs
                # in the same source-fenced writer as the new queue/input rows;
                # ordinary parse submission retains its existing contract.
                admission(connection, actor)
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

    def _accepted(self, connection, revision_id, *, correction_depth=0, correction_context=None):
        if correction_depth > 32:
            raise DocumentRevisionProblem("document-correction-history-limit")
        if correction_context is None:
            correction_context = _CorrectionReadContext(connection, self.project)
        correction_context.check(connection, self.project)
        if revision_id in correction_context.accepted:
            return correction_context.accepted[revision_id]
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
        parsed = self._result(connection, result.result)
        if decision.display_label_observed == "Accept document correction":
            LocalDocumentCorrectionRepository(self)._verify_accepted(
                connection, result, depth=correction_depth, context=correction_context
            )
        else:
            # A correction cannot evade its protected patch/rationale proof by
            # relabeling the decision as an ordinary parser acceptance.
            factory = iter(m.canonical_id for m in result.element_identities)
            machine, mapping = canonicalize_structure(parsed.ir, identity_factory=lambda: next(factory))
            if (machine, mapping) != (result.structure, result.element_identities):
                raise DocumentRevisionProblem("document-revision-machine-binding-invalid")
            if decision.display_label_observed == "Accept document reparse":
                LocalDocumentReprocessingRepository(self)._verify_machine(connection, result)
        if correction_context is not None:
            correction_context.check(connection, self.project)
            correction_context.accepted[revision_id] = result
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

    def quality(self, job_id, *, cancelled: Callable[[], bool] = lambda: False) -> ParsingQualityReport:
        """Read-only versioned triage, including unaccepted/failed durable jobs.

        Reuse encrypted retained results and immutable attempt/source bindings.
        Re-evaluation never publishes a revision, acceptance, event or new head.
        """
        from .document_viewer_allocations import viewer_revision_reads
        from .parsing.native_contracts import NATIVE_MEDIA_TYPE

        if not is_uuid_v7(job_id):
            raise DocumentRevisionProblem("document-parse-job-unavailable")
        deadline = time.monotonic() + 5.0

        def stopped():
            if cancelled() or time.monotonic() > deadline:
                raise DocumentRevisionProblem("parsing-quality-stopped-or-resource-limit")

        def read():
            stopped()
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
                inputs = self._input(connection, job_id)
            bounded = viewer_revision_reads(self, inputs.source.byte_length)

            def current(connection, _actor):
                stopped()
                job, output = bounded.queue._accepted_status_with_connection(connection, job_id)
                source, producer = selected_values(inputs.selection)
                if len(producer.assets) > 32:
                    raise DocumentRevisionProblem("parsing-quality-resource-limit")
                receipt = None
                assessment = unavailable_assessment(job.state)
                if output is not None:
                    if len(output.outputs) != 1:
                        raise DocumentRevisionProblem("document-parse-output-not-successful")
                    receipt = bounded._receipt(connection, output.outputs[0].artifact_id)
                    result = bounded._result(connection, receipt)
                    if (
                        receipt.binding.source,
                        receipt.binding.producer,
                        receipt.binding.selection_sha256,
                        receipt.binding.attempt.job_id,
                        receipt.binding.attempt.attempt_id,
                    ) != (
                        source,
                        producer,
                        selection_sha256(inputs.selection),
                        job.job_id,
                        job.current_attempt_id,
                    ):
                        raise DocumentRevisionProblem("parsing-quality-result-binding-invalid")
                    stopped()
                    native_receipts = [item for item in result.ir.raw_artifacts if item.media_type == NATIVE_MEDIA_TYPE]
                    if len(native_receipts) > 1:
                        raise DocumentRevisionProblem("parsing-quality-native-binding-invalid")
                    native = (
                        None
                        if not native_receipts
                        else bounded.objects._read_protected_document_artifact(
                            connection,
                            native_receipts[0],
                            NATIVE_MEDIA_TYPE,
                        )
                    )
                    assessment = assess_ir(result.ir, native_artifact=native, cancelled=cancelled)
                report = ParsingQualityReport(
                    source=source,
                    producer=producer,
                    selection_sha256=selection_sha256(inputs.selection),
                    input_sha256=inputs.configuration_hash.removeprefix("sha256:"),
                    job_id=job.job_id,
                    attempt_id=job.current_attempt_id,
                    job_state=job.state,
                    diagnostic_code=job.diagnostic_code,
                    result_id=None if receipt is None else receipt.result_id,
                    result_revision_id=None if receipt is None else receipt.revision_id,
                    result_sha256=None if receipt is None else receipt.object_sha256,
                    assessment=assessment,
                )
                if len(protected_json(report)) > 64 * 1024:
                    raise DocumentRevisionProblem("parsing-quality-resource-limit")
                stopped()
                return report

            report = bounded._source_fenced(inputs.source, current)
            stopped()
            return report

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
                    if (
                        connection.execute(
                            "SELECT 1 FROM document_normalized_revisions WHERE project_id=? AND revision_id=?",
                            (self.project, current.revision_id),
                        ).fetchone()
                        is not None
                    ):
                        raise DocumentRevisionProblem("document-revision-reprocessing-required")
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
                    if (
                        connection.execute(
                            "SELECT 1 FROM document_normalized_revisions WHERE project_id=? AND revision_id=?",
                            (self.project, current.revision_id),
                        ).fetchone()
                        is not None
                    ):
                        raise DocumentRevisionProblem("document-revision-reprocessing-required")
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


class LocalDocumentCorrectionRepository:
    """Protected drafts and explicit, atomic correction acceptance on v1 storage.

    The base and draft are immutable historical inputs, not promises that their
    aggregate heads stay current. Save/accept enforce those heads explicitly.
    Non-material history edges avoid incorrectly invalidating the new successor
    by the very base change its researcher just accepted.
    """

    def __init__(self, revisions, *, target_resolver=None):
        self.revisions = revisions
        self.target_resolver = target_resolver

    @staticmethod
    def _check(cancelled):
        if cancelled():
            raise DocumentRevisionProblem("document-correction-cancelled")

    @staticmethod
    def draft_view(record):
        return CorrectionDraftView(record=record, confirmation_sha256=value_sha256(record))

    @staticmethod
    def accepted_view(accepted):
        return CorrectionAcceptedView(
            project_id=accepted.project_id,
            document_id=accepted.document_id,
            revision_id=accepted.revision_id,
            previous_revision_id=accepted.previous_revision_id,
            structure_sha256=accepted.structure_sha256,
            content_sha256=accepted.content_sha256,
            decision_revision_id=accepted.decision_revision_id,
            accepted_by=accepted.accepted_by,
            accepted_at=accepted.accepted_at,
        )

    def queue(self, *, after_job_id=None, cancelled=lambda: False):
        def read():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as connection:
                self.revisions._authority(connection, self.revisions.actor())
                rows = connection.execute(
                    "SELECT job_id FROM document_parse_jobs WHERE project_id=? AND (? IS NULL OR job_id>?) "
                    "ORDER BY job_id LIMIT 11",
                    (self.revisions.project, after_job_id, after_job_id),
                ).fetchall()
                sources = tuple((row[0], self.revisions._input(connection, row[0]).source) for row in rows[:10])
            items = []
            for job_id, source in sources:
                self._check(cancelled)

                def current(connection, _actor, job_id=job_id, source=source):
                    with self.revisions._aggregates(connection) as aggregates:
                        head = aggregates.get(source.document_id)
                    # Opaque recovery selector only. Page/read subsequently
                    # authenticates the complete accepted structure and patch.
                    normalized = connection.execute(
                        "SELECT 1 FROM document_normalized_revisions n JOIN document_parse_results p "
                        "ON p.project_id=n.project_id AND p.result_id=n.result_id "
                        "WHERE n.project_id=? AND n.revision_id=? AND p.job_id=?",
                        (self.revisions.project, head.revision_id, job_id),
                    ).fetchone()
                    return CorrectionQueueItem(
                        job_id=job_id,
                        attachment_id=source.attachment_id,
                        revision_id=head.revision_id if normalized else None,
                    )

                items.append(self.revisions._source_fenced(source, current))
            self._check(cancelled)
            return CorrectionQueue(
                project_id=self.revisions.project,
                items=tuple(items),
                next_after_job_id=rows[9][0] if len(rows) == 11 else None,
            )

        return self.revisions._bounded(read)

    @staticmethod
    def _nodes_view(structure, labels, offset, *, proposed):
        projections = {p.projection_id: p for p in structure.text_projections}
        references = {r.node_id: r for r in structure.references}
        values = []
        for node in structure.nodes[offset : offset + 20]:
            key = node.staged_id if proposed else node.node_id
            text = node.text
            reference = references.get(key)
            values.append(
                CorrectionNodeView(
                    node_id=key,
                    parent_id=node.parent_id,
                    order=node.order,
                    kind=node.kind,
                    expected_node_sha256=None if proposed else value_sha256(node),
                    preview=projections[text.projection_id].normalized_text[
                        text.normalized_range.start : min(text.normalized_range.end, text.normalized_range.start + 160)
                    ]
                    if text
                    else "",
                    label=labels.get(key),
                    text_start=text.normalized_range.start if text else None,
                    text_end=text.normalized_range.end if text else None,
                    locator=node.locator,
                    reference_id=(reference.staged_id if proposed else reference.reference_id) if reference else None,
                    expected_reference_sha256=value_sha256(reference) if reference else None,
                    state="proposed" if proposed else "accepted",
                )
            )
        return tuple(values)

    def page(self, revision_id, *, draft_revision_id=None, offset=0, cancelled=lambda: False):
        if type(offset) is not int or not 0 <= offset < MAX_CORRECTION_ITEMS:
            raise DocumentRevisionProblem("document-correction-page-invalid")

        def read():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as connection:
                source = self._source_for_revision(connection, revision_id)

            def current(connection, _actor):
                from .document_viewer_allocations import viewer_revision_reads

                bounded = type(self)(
                    viewer_revision_reads(self.revisions, source.byte_length), target_resolver=self.target_resolver
                )
                context = bounded._context(connection, None)
                base = bounded.revisions._accepted(connection, revision_id, correction_context=context)
                inherited = bounded._inheritance(connection, base, context=context)
                lineage = bounded._lineage(connection, base, context=context)
                with bounded.revisions._aggregates(connection) as aggregates:
                    head = aggregates.get(base.document_id)
                rows = connection.execute(
                    "SELECT d.output_revision_id,n.revision_id FROM material_dependencies d "
                    "JOIN document_normalized_revisions n ON n.project_id=d.project_id "
                    "AND n.revision_id=d.dependency_revision_id "
                    "JOIN documents a ON a.project_id=d.project_id AND a.revision_id=d.output_revision_id "
                    "JOIN aggregate_revisions g ON g.project_id=a.project_id AND g.revision_id=a.revision_id "
                    "JOIN object_records o ON o.project_id=a.project_id AND o.object_sha256=a.object_sha256 "
                    "WHERE n.project_id=? AND n.document_id=? AND o.media_type=? AND NOT EXISTS "
                    "(SELECT 1 FROM aggregate_revisions newer WHERE newer.project_id=a.project_id "
                    "AND newer.aggregate_id=g.aggregate_id AND newer.revision>g.revision) "
                    "ORDER BY d.output_revision_id DESC LIMIT 10",
                    (bounded.revisions.project, base.document_id, CORRECTION_MEDIA_TYPE),
                ).fetchall()
                selectors = tuple(CorrectionDraftSelector(draft_revision_id=r[0], base_revision_id=r[1]) for r in rows)
                selected = draft_revision_id or next(
                    (s.draft_revision_id for s in selectors if s.base_revision_id == revision_id), None
                )
                record, preview = None, None
                if selected:
                    record = bounded._record(connection, selected, context=context)
                    if record.patch.base_revision_id != revision_id:
                        raise DocumentRevisionProblem("document-correction-draft-base-mismatch")
                    preview = bounded._apply(connection, base, record.patch, context=context, cancelled=cancelled)
                accepted_decision = context.accepted_drafts.get(base.revision_id)
                nodes = bounded._nodes_view(
                    base.structure, {label.node_id: label.label for label in inherited.labels}, offset, proposed=False
                )
                references = {n.reference_id for n in nodes if n.reference_id}
                result = CorrectionPage(
                    project_id=base.project_id,
                    source=source,
                    document_id=base.document_id,
                    revision_id=base.revision_id,
                    current_revision_id=head.revision_id,
                    accepted_by=base.accepted_by,
                    accepted_at=base.accepted_at,
                    machine_revision_id=lineage.machine_revision.revision_id,
                    attachment_id=source.attachment_id,
                    job_id=base.result.binding.attempt.job_id,
                    structure_sha256=base.structure_sha256,
                    nodes=nodes,
                    preview_nodes=bounded._nodes_view(
                        preview.ir, {label.node_id: label.label for label in preview.labels}, offset, proposed=True
                    )
                    if preview
                    else (),
                    next_offset=offset + 20
                    if max(len(base.structure.nodes), len(preview.ir.nodes) if preview else 0) > offset + 20
                    else None,
                    draft=bounded.draft_view(record) if record else None,
                    drafts=selectors,
                    accepted_labels=tuple(
                        label for label in inherited.labels if label.node_id in {n.node_id for n in nodes}
                    ),
                    accepted_reference_matches=tuple(
                        m for m in inherited.reference_matches if m.reference_id in references
                    ),
                    accepted_decision=bounded.draft_view(accepted_decision) if accepted_decision else None,
                )
                self._check(cancelled)
                return result

            return self.revisions._source_fenced(source, current)

        return self.revisions._bounded(read)

    def impact(self, draft_revision_id, *, cancelled=lambda: False):
        def read():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as connection:
                source = self._source_for_draft(connection, draft_revision_id)

            def current(connection, actor):
                context = self._context(connection, None)
                record = self._record(connection, draft_revision_id, context=context)
                base = self.revisions._accepted(connection, record.patch.base_revision_id, correction_context=context)
                with self.revisions._aggregates(connection) as aggregates:
                    prior = aggregates.get(base.document_id)
                    draft = aggregates.get(record.draft_id)
                if (
                    prior.revision_id != base.revision_id
                    or draft.revision_id != record.revision_id
                    or record.state != "draft"
                ):
                    raise DocumentRevisionProblem("document-correction-base-changed")
                # A detached prospective endpoint, as in existing scholarly
                # review previews. It is never stored as a canonical revision.
                # Acceptance uses two real authenticated endpoint fingerprints.
                change = DependencyChange(
                    change_id=new_uuid_v7(),
                    idempotency_key="correction-preview-" + new_uuid_v7(),
                    reason="HUMAN_DECISION",
                    dependency_kind="source-revision",
                    previous_revision_id=base.revision_id,
                    replacement_revision_id=new_uuid_v7(),
                    configuration_id=None,
                    previous_configuration_version=None,
                    replacement_configuration_version=None,
                    previous_fingerprint=_projection_content_sha256(prior),
                    replacement_fingerprint="sha256:" + record.preview_sha256,
                    propagation_policy_id="dependency.propagation.v1",
                    propagation_policy_version="1.0.0",
                    actor_id=actor.actor_id,
                    trace_id=actor.trace_id,
                    occurred_at=actor.occurred_at,
                )
                impacts = _SqliteDependencyImpactRepository(self.revisions.database, self.revisions.project)
                preview = impacts._plan_with_connection(
                    connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
                )
                self._check(cancelled)
                return CorrectionImpactView(
                    project_id=self.revisions.project,
                    base_revision_id=base.revision_id,
                    draft_revision_id=record.revision_id,
                    graph_sha256=preview.graph_sha256.removeprefix("sha256:"),
                    affected_count=len(preview.affected_output_revision_ids),
                    informational_count=len(preview.informational_output_revision_ids),
                    legacy_unreported_count=preview.legacy_unreported_count,
                    items=tuple(
                        CorrectionImpactItem(
                            revision_id=i.output_revision_id, kind=i.output_kind, disposition=i.disposition
                        )
                        for i in preview.impacts[:20]
                    ),
                    truncated=len(preview.impacts) > 20,
                )

            return self.revisions._source_fenced(source, current)

        return self.revisions._bounded(read)

    def _source_for_revision(self, connection, revision_id):
        row = connection.execute(
            "SELECT p.job_id FROM document_normalized_revisions r JOIN document_parse_results p "
            "ON p.project_id=r.project_id AND p.result_id=r.result_id "
            "WHERE r.project_id=? AND r.revision_id=?",
            (self.revisions.project, revision_id),
        ).fetchone()
        if row is None:
            raise DocumentRevisionProblem("document-correction-base-unavailable")
        return self.revisions._input(connection, row[0]).source

    def source_for_command(self, command):
        """Metadata-only selector for cumulative admission; grants no authority."""
        with closing(
            open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
        ) as db:
            if hasattr(command, "correction"):
                return self._source_for_revision(db, command.correction.patch.base_revision_id)
            if hasattr(command, "revision_id"):
                return self._source_for_revision(db, command.revision_id)
            if hasattr(command, "acceptance"):
                return self._source_for_draft(db, command.acceptance.draft_revision_id)
            if hasattr(command, "discard"):
                return self._source_for_draft(db, command.discard.draft_revision_id)
            if hasattr(command, "draft_revision_id"):
                return self._source_for_draft(db, command.draft_revision_id)
            return None

    def work_targets(self, after_work_id, reconciler, resolve, *, cancelled):
        from .document_correction_views import CorrectionWorkTarget, CorrectionWorkTargets

        if reconciler is None or resolve is None:
            raise DocumentRevisionProblem("document-correction-reference-authority-unavailable")
        with closing(
            open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
        ) as db:
            rows = db.execute(
                "SELECT DISTINCT work_id FROM reconciliation_work_states WHERE project_id=? "
                "AND (? IS NULL OR work_id>?) ORDER BY work_id LIMIT 11",
                (self.revisions.project, after_work_id, after_work_id),
            ).fetchall()
            items = []
            for (work_id,) in rows[:10]:
                self._check(cancelled)
                state = reconciler._state(db, work_id)
                if state.disposition != "active":
                    continue
                sources = reconciler._work_sources(db, work_id, resolve)
                if not sources:
                    raise DocumentRevisionProblem("document-correction-reference-authority-unavailable")
                title = next(
                    (
                        field.observed
                        for source in sources
                        for field in source.assertion.fields
                        if field.name == "title" and field.observed
                    ),
                    "Title not reported",
                )
                items.append(
                    CorrectionWorkTarget(work_id=work_id, work_revision_id=state.revision_id, title=title[:160])
                )
            return CorrectionWorkTargets(
                project_id=self.revisions.project,
                items=tuple(items),
                next_after_work_id=rows[9][0] if len(rows) == 11 else None,
            )

    def _source_for_draft(self, connection, revision_id):
        rows = connection.execute(
            "SELECT r.revision_id FROM material_dependencies d JOIN document_normalized_revisions r "
            "ON r.project_id=d.project_id AND r.revision_id=d.dependency_revision_id "
            "WHERE d.project_id=? AND d.output_revision_id=? LIMIT 2",
            (self.revisions.project, revision_id),
        ).fetchall()
        if len(rows) != 1:
            raise DocumentRevisionProblem("document-correction-draft-unavailable")
        return self._source_for_revision(connection, rows[0][0])

    @staticmethod
    def _semantic_values(command, actor_id, intent_revision_id, intent_sha256, policy_sha256):
        return hashlib.sha256(
            protected_json(command)
            + actor_id.encode()
            + intent_revision_id.encode()
            + intent_sha256.encode()
            + policy_sha256.encode()
        ).hexdigest()

    @classmethod
    def _semantic(cls, command, actor):
        return cls._semantic_values(
            command, actor.actor_id, actor.intent_revision_id, actor.intent_sha256, actor.policy_sha256
        )

    def _context(self, connection, context):
        if context is None:
            context = _CorrectionReadContext(connection, self.revisions.project)
        context.check(connection, self.revisions.project)
        return context

    def _inheritance(self, connection, accepted, *, depth=0, context=None):
        context = self._context(connection, context)
        if accepted.revision_id not in context.inheritance:
            with self.revisions._aggregates(connection) as aggregates:
                decision = aggregates.get_revision(accepted.decision_revision_id)
            if decision.display_label_observed == "Accept document correction":
                self._verify_accepted(connection, accepted, depth=depth, context=context)
            else:
                context.inheritance[accepted.revision_id] = CorrectionInheritance(
                    base_revision_id=accepted.revision_id,
                    expected_structure_sha256=accepted.structure_sha256,
                    labels=(),
                    excluded_node_ids=(),
                    reference_matches=(),
                )
        return context.inheritance[accepted.revision_id]

    def _lineage(self, connection, accepted, *, depth=0, context=None):
        context = self._context(connection, context)
        if accepted.revision_id not in context.lineages:
            with self.revisions._aggregates(connection) as aggregates:
                decision = aggregates.get_revision(accepted.decision_revision_id)
            if decision.display_label_observed == "Accept document correction":
                self._verify_accepted(connection, accepted, depth=depth, context=context)
            else:
                context.lineages[accepted.revision_id] = CorrectionSourceLineage.machine(accepted)
        return context.lineages[accepted.revision_id]

    def bound_lineage(self, connection, accepted, *, context=None):
        """One current source-fenced adapter call, never client-supplied input."""
        with self.revisions._aggregates(connection) as aggregates:
            decision = aggregates.get_revision(accepted.decision_revision_id)
        if decision.display_label_observed != "Accept document correction":
            return None
        return self._lineage(connection, accepted, context=context)

    def _apply(self, connection, base, patch, *, depth=0, context=None, cancelled=lambda: False):
        return apply_correction(
            base,
            patch,
            cancelled=cancelled,
            inherited=self._inheritance(connection, base, depth=depth, context=context),
        )

    def _targets(self, connection, result, *, fresh):
        targets = {}
        with self.revisions._aggregates(connection) as aggregates:
            for match in result.reference_matches:
                if fresh:
                    if self.target_resolver is None:
                        raise DocumentRevisionProblem("document-correction-reference-authority-unavailable")
                    target = self.target_resolver(connection, match)
                else:
                    target = aggregates.get_revision(match.work_revision_id)
                # Work aggregate metadata deliberately retains rights_status
                # "unknown". It is not a permission receipt. Fresh target
                # authority comes from the current Reconciliation source
                # resolver above, which checks every active Work assertion.
                if (target.aggregate_id, target.revision_id, target.project_id) != (
                    match.work_id,
                    match.work_revision_id,
                    self.revisions.project,
                ) or target.aggregate_kind != "record":
                    raise DocumentRevisionProblem("document-correction-reference-authority-changed")
                targets[target.revision_id] = target
        return tuple(targets[key] for key in sorted(targets))

    def _dependencies(self, inputs, historical):
        return tuple(
            replace(edge, relation_type="non-material") if edge.revision_id in historical else edge
            for edge in self.revisions._dependencies(inputs)
        )

    def _validate_inputs(self, connection, revision_id, inputs, historical):
        rows = connection.execute(
            "SELECT dependency_revision_id,dependency_kind,relation_type,fingerprint,governing_policy_id,"
            "governing_policy_version,configuration_id,configuration_version FROM material_dependencies "
            "WHERE project_id=? AND output_revision_id=? ORDER BY dependency_revision_id LIMIT 65",
            (self.revisions.project, revision_id),
        ).fetchall()
        expected = sorted(
            (
                item.revision_id,
                "human-decision" if item.aggregate_kind == "decision" else "source-revision",
                "non-material" if item.revision_id in historical else "direct",
                _projection_content_sha256(item),
                "dependency.material.v1",
                "1.0.0",
                None,
                None,
            )
            for item in inputs
        )
        if [tuple(row) for row in rows] != expected:
            raise DocumentRevisionProblem("document-correction-inputs-invalid")

    def _record(self, connection, revision_id, *, depth=0, context=None):
        context = self._context(connection, context)
        if revision_id in context.drafts:
            return context.drafts[revision_id]
        with self.revisions._aggregates(connection) as aggregates:
            revision = aggregates.get_revision(revision_id)
            if revision.aggregate_kind != "document" or revision.object_sha256 is None:
                raise DocumentRevisionProblem("document-correction-draft-invalid")
            metadata = connection.execute(
                "SELECT byte_length,media_type FROM object_records WHERE project_id=? AND object_sha256=?",
                (self.revisions.project, revision.object_sha256),
            ).fetchone()
            if (
                metadata is None
                or metadata[1] != CORRECTION_MEDIA_TYPE
                or not 0 < metadata[0] <= MAX_CORRECTION_RECORD_BYTES
            ):
                raise DocumentRevisionProblem("document-correction-draft-invalid")
            record = CorrectionDraft.model_validate_json(
                self.revisions.objects._read_protected_document_artifact(
                    connection, _ProtectedReceipt(revision.object_sha256, metadata[0]), CORRECTION_MEDIA_TYPE
                )
            )
            if record.command_kind == "discard":
                previous_record = self._record(
                    connection, record.previous_draft_revision_id, depth=depth, context=context
                )
                if (previous_record.draft_id, previous_record.patch, previous_record.source, previous_record.state) != (
                    record.draft_id,
                    record.patch,
                    record.source,
                    "draft",
                ):
                    raise DocumentRevisionProblem("document-correction-discard-invalid")
                semantic_command: CorrectionDiscard | CorrectionSave = CorrectionDiscard(
                    command_id=record.command_id,
                    draft_revision_id=previous_record.revision_id,
                    confirmation_sha256=value_sha256(previous_record),
                    rationale=record.rationale,
                )
            else:
                semantic_command = CorrectionSave(
                    command_id=record.command_id,
                    draft_id=record.draft_id if record.previous_draft_revision_id else None,
                    expected_draft_revision_id=record.previous_draft_revision_id,
                    patch=record.patch,
                    rationale=record.rationale,
                )
            if (record.project_id, record.draft_id, record.revision_id, record.authored_at) != (
                revision.project_id,
                revision.aggregate_id,
                revision.revision_id,
                revision.modified_at,
            ) or record.command_sha256 != self._semantic_values(
                semantic_command,
                record.authored_by,
                record.intent_revision_id,
                record.intent_sha256,
                record.policy_sha256,
            ):
                raise DocumentRevisionProblem("document-correction-draft-invalid")
            base = self.revisions._accepted(
                connection, record.patch.base_revision_id, correction_depth=depth + 1, correction_context=context
            )
            if record.source != base.result.binding.source:
                raise DocumentRevisionProblem("document-correction-source-invalid")
            result = self._apply(connection, base, record.patch, depth=depth + 1, context=context)
            if result.result_sha256 != record.preview_sha256:
                raise DocumentRevisionProblem("document-correction-preview-invalid")
            previous: tuple[AggregateRevision, ...] = ()
            historical = {base.revision_id}
            if record.previous_draft_revision_id:
                prior = aggregates.get_revision(record.previous_draft_revision_id)
                if (prior.aggregate_id, prior.aggregate_kind, prior.revision + 1) != (
                    revision.aggregate_id,
                    "document",
                    revision.revision,
                ):
                    raise DocumentRevisionProblem("document-correction-draft-predecessor-invalid")
                previous = (prior,)
                historical.add(prior.revision_id)
            elif revision.revision != 0:
                raise DocumentRevisionProblem("document-correction-draft-predecessor-invalid")
            inputs = (
                aggregates.get_revision(base.revision_id),
                aggregates.get_revision(base.result.revision_id),
                *previous,
                *self._targets(connection, result, fresh=False),
            )
            self._validate_inputs(connection, revision_id, inputs, historical)
            events = connection.execute(
                "SELECT actor_type,actor_id,occurred_at FROM provenance_events WHERE project_id=? AND revision_id=?",
                (self.revisions.project, revision_id),
            ).fetchall()
            if [tuple(e) for e in events] != [("human", record.authored_by, record.authored_at)]:
                raise DocumentRevisionProblem("document-correction-author-invalid")
            context.check(connection, self.revisions.project)
            context.drafts[revision_id] = record
            return record

    def _saved_replay(self, connection, command, actor):
        row = connection.execute(
            "SELECT revision_id FROM outbox_events WHERE project_id=? AND idempotency_key=?",
            (self.revisions.project, "document-correction-save-" + command.command_id),
        ).fetchone()
        if row is None:
            return None
        record = self._record(connection, row[0])
        if record.command_id != command.command_id or record.command_sha256 != self._semantic(command, actor):
            raise DocumentRevisionProblem("document-correction-command-conflict")
        return record

    def save(self, command: CorrectionSave, *, cancelled=lambda: False):
        command = CorrectionSave.model_validate(command)
        return self._save_proposal(command, semantic_command=command, state="draft", cancelled=cancelled)

    def discard(self, command: CorrectionDiscard, *, cancelled=lambda: False):
        command = CorrectionDiscard.model_validate(command)

        def discard():
            record = self.read(command.draft_revision_id, cancelled=cancelled)
            if command.confirmation_sha256 != value_sha256(record) or record.state != "draft":
                raise DocumentRevisionProblem("document-correction-confirmation-mismatch")
            save = CorrectionSave(
                command_id=command.command_id,
                draft_id=record.draft_id,
                expected_draft_revision_id=record.revision_id,
                patch=record.patch,
                rationale=command.rationale,
            )
            return self._save_proposal(save, semantic_command=command, state="discarded", cancelled=cancelled)

        return self.revisions._bounded(discard)

    def _save_proposal(self, command, *, semantic_command, state, cancelled):

        def save():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                source = self._source_for_revision(db, command.patch.base_revision_id)

            def prepare(connection, actor):
                self._check(cancelled)
                replay = self._saved_replay(connection, semantic_command, actor)
                if replay:
                    return replay
                base = self.revisions._accepted(connection, command.patch.base_revision_id)
                result = self._apply(connection, base, command.patch, cancelled=cancelled)
                with self.revisions._aggregates(connection) as aggregates:
                    current = aggregates.get(base.document_id)
                    if state == "draft" and current.revision_id != base.revision_id:
                        raise DocumentRevisionProblem("document-correction-base-changed")
                    previous = None
                    if command.draft_id:
                        previous = aggregates.get(command.draft_id)
                        if previous.revision_id != command.expected_draft_revision_id:
                            raise DocumentRevisionProblem("document-correction-draft-changed")
                        prior = self._record(connection, previous.revision_id)
                        if prior.state != "draft" or (prior.source, prior.patch.base_revision_id) != (
                            source,
                            base.revision_id,
                        ):
                            raise DocumentRevisionProblem("document-correction-draft-changed")
                targets = self._targets(connection, result, fresh=state == "draft")
                record = CorrectionDraft(
                    project_id=self.revisions.project,
                    draft_id=command.draft_id or new_uuid_v7(),
                    revision_id=new_uuid_v7(),
                    previous_draft_revision_id=command.expected_draft_revision_id,
                    source=source,
                    patch=command.patch,
                    rationale=command.rationale,
                    authored_by=actor.actor_id,
                    authored_at=actor.occurred_at,
                    intent_revision_id=actor.intent_revision_id,
                    intent_sha256=actor.intent_sha256,
                    policy_sha256=actor.policy_sha256,
                    command_id=command.command_id,
                    command_kind="save" if state == "draft" else "discard",
                    command_sha256=self._semantic(semantic_command, actor),
                    preview_sha256=result.result_sha256,
                    state=state,
                )
                return record, base, previous, targets, actor

            prepared = self.revisions._source_fenced(source, prepare)
            if isinstance(prepared, CorrectionDraft):
                return prepared
            record, base, predecessor, targets, owner = prepared
            raw = protected_json(record)
            if len(raw) > MAX_CORRECTION_RECORD_BYTES:
                raise DocumentRevisionProblem("document-correction-limit")

            def publish(connection, stored):
                self._check(cancelled)
                actor = self.revisions.actor()
                self.revisions._authority(connection, actor)
                if actor != owner:
                    raise DocumentRevisionProblem("document-correction-authority-changed")
                replay = self._saved_replay(connection, semantic_command, actor)
                if replay:
                    return replay
                if self.revisions._accepted(connection, base.revision_id) != base:
                    raise DocumentRevisionProblem("document-correction-base-changed")
                result = self._apply(connection, base, command.patch, cancelled=cancelled)
                if self._targets(connection, result, fresh=state == "draft") != targets:
                    raise DocumentRevisionProblem("document-correction-reference-authority-changed")
                with self.revisions._aggregates(connection) as aggregates:
                    if state == "draft" and aggregates.get(base.document_id).revision_id != base.revision_id:
                        raise DocumentRevisionProblem("document-correction-base-changed")
                    if predecessor is not None and aggregates.get(record.draft_id) != predecessor:
                        raise DocumentRevisionProblem("document-correction-draft-changed")
                    inputs = (
                        aggregates.get_revision(base.revision_id),
                        aggregates.get_revision(base.result.revision_id),
                        *((predecessor,) if predecessor else ()),
                        *targets,
                    )
                    historical = {base.revision_id, *(p.revision_id for p in (predecessor,) if p is not None)}
                    aggregates.append(
                        AggregateRevisionDraft(
                            revision_id=record.revision_id,
                            aggregate_id=record.draft_id,
                            aggregate_kind="document",
                            created_at=predecessor.created_at if predecessor else record.authored_at,
                            modified_at=record.authored_at,
                            display_label_observed="Document correction draft",
                            display_label_normalized=None,
                            knowledge_status="observed",
                            rights_status="allowed",
                            dependency_coverage="complete",
                            object_sha256=stored.object_sha256,
                            provenance_inputs=inputs,
                            material_dependencies=self._dependencies(inputs, historical),
                        ),
                        self.revisions._event(
                            actor,
                            record.authored_at,
                            "document.updated" if predecessor else "document.created",
                            "document-correction-save-" + command.command_id,
                        ),
                        expected_revision=predecessor.revision if predecessor else None,
                    )
                _publication_step("correction-draft-complete")
                self._check(cancelled)
                return record

            return self.revisions._put(raw, CORRECTION_MEDIA_TYPE, source, publish, cancelled)

        return self.revisions._bounded(save)

    def read(self, revision_id, *, cancelled=lambda: False):
        def read():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                source = self._source_for_draft(db, revision_id)

            def current(connection, _actor):
                record = self._record(connection, revision_id)
                self._check(cancelled)
                return record

            return self.revisions._source_fenced(source, current)

        return self.revisions._bounded(read)

    def _verify_accepted(self, connection, accepted, *, depth=0, context=None):
        context = self._context(connection, context)
        if accepted.revision_id in context.accepted_drafts:
            return context.accepted_drafts[accepted.revision_id]
        rows = connection.execute(
            "SELECT d.dependency_revision_id FROM material_dependencies d "
            "JOIN documents a ON a.project_id=d.project_id AND a.revision_id=d.dependency_revision_id "
            "JOIN object_records o ON o.project_id=a.project_id AND o.object_sha256=a.object_sha256 "
            "WHERE d.project_id=? AND d.output_revision_id=? AND o.media_type=? LIMIT 2",
            (self.revisions.project, accepted.decision_revision_id, CORRECTION_MEDIA_TYPE),
        ).fetchall()
        if len(rows) != 1:
            raise DocumentRevisionProblem("document-correction-acceptance-record-missing")
        record = self._record(connection, rows[0][0], depth=depth, context=context)
        base = self.revisions._accepted(
            connection, record.patch.base_revision_id, correction_depth=depth + 1, correction_context=context
        )
        command = CorrectionAcceptance(
            command_id=accepted.command_id,
            draft_revision_id=record.revision_id,
            expected_current_revision_id=accepted.previous_revision_id,
            confirmation_sha256=value_sha256(record),
            decision="accept-correction",
        )
        semantic = hashlib.sha256(
            protected_json(command) + protected_json(record) + accepted.accepted_by.encode()
        ).hexdigest()
        result = self._apply(connection, base, record.patch, depth=depth + 1, context=context)
        factory = iter(m.canonical_id for m in accepted.element_identities)
        structure, mapping = canonicalize_structure(result.ir, identity_factory=lambda: next(factory))
        if (
            accepted.previous_revision_id,
            accepted.result,
            accepted.command_sha256,
            accepted.structure,
            accepted.element_identities,
            accepted.intent_revision_id,
            accepted.intent_sha256,
            accepted.policy_sha256,
        ) != (
            base.revision_id,
            base.result,
            semantic,
            structure,
            mapping,
            record.intent_revision_id,
            record.intent_sha256,
            record.policy_sha256,
        ) or record.state != "draft":
            raise DocumentRevisionProblem("document-correction-acceptance-binding-invalid")
        with self.revisions._aggregates(connection) as aggregates:
            inputs = (
                aggregates.get_revision(base.revision_id),
                aggregates.get_revision(base.result.revision_id),
                aggregates.get_revision(record.revision_id),
                *self._targets(connection, result, fresh=False),
            )
            self._validate_inputs(connection, accepted.decision_revision_id, inputs, {base.revision_id})
            self._validate_inputs(
                connection,
                accepted.revision_id,
                (*inputs, aggregates.get_revision(accepted.decision_revision_id)),
                {base.revision_id},
            )
            previous = aggregates.get_revision(base.revision_id)
            current = aggregates.get_revision(accepted.revision_id)
        impact = connection.execute(
            "SELECT previous_revision_id,replacement_revision_id,reason,dependency_kind,"
            "previous_fingerprint,replacement_fingerprint,actor_id,occurred_at,"
            "propagation_policy_id,propagation_policy_version FROM dependency_impact_runs "
            "WHERE project_id=? AND idempotency_key=?",
            (self.revisions.project, "document-correction-impact-" + accepted.command_id),
        ).fetchone()
        if impact is None or tuple(impact) != (
            base.revision_id,
            accepted.revision_id,
            "HUMAN_DECISION",
            "source-revision",
            _projection_content_sha256(previous),
            _projection_content_sha256(current),
            accepted.accepted_by,
            accepted.accepted_at,
            "dependency.propagation.v1",
            "1.0.0",
        ):
            raise DocumentRevisionProblem("document-correction-impact-invalid")
        lineage = self._lineage(connection, base, depth=depth + 1, context=context).advance(accepted, result)
        context.inheritance[accepted.revision_id] = lineage.inheritance
        context.lineages[accepted.revision_id] = lineage
        context.check(connection, self.revisions.project)
        context.accepted_drafts[accepted.revision_id] = record
        return record

    def metadata(self, revision_id, *, cancelled=lambda: False):
        def read():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                source = self._source_for_revision(db, revision_id)

            def current(connection, _actor):
                context = self._context(connection, None)
                accepted = self.revisions._accepted(connection, revision_id, correction_context=context)
                result = self._inheritance(connection, accepted, context=context)
                self._check(cancelled)
                return result

            return self.revisions._source_fenced(source, current)

        return self.revisions._bounded(read)

    def accepted_draft(self, revision_id):
        def read():
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                source = self._source_for_revision(db, revision_id)

            def current(connection, _actor):
                context = self._context(connection, None)
                accepted = self.revisions._accepted(connection, revision_id, correction_context=context)
                return self._verify_accepted(connection, accepted, context=context)

            return self.revisions._source_fenced(source, current)

        return self.revisions._bounded(read)

    def accept(self, command: CorrectionAcceptance, *, cancelled=lambda: False):
        command = CorrectionAcceptance.model_validate(command)

        def accept():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                source = self._source_for_draft(db, command.draft_revision_id)

            def prepare(connection, actor):
                self._check(cancelled)
                record = self._record(connection, command.draft_revision_id)
                if command.confirmation_sha256 != value_sha256(record) or record.state != "draft":
                    raise DocumentRevisionProblem("document-correction-confirmation-mismatch")
                semantic = hashlib.sha256(
                    protected_json(command) + protected_json(record) + actor.actor_id.encode()
                ).hexdigest()
                replay = connection.execute(
                    "SELECT revision_id,command_sha256,actor_id FROM document_normalized_revisions "
                    "WHERE project_id=? AND command_id=?",
                    (self.revisions.project, command.command_id),
                ).fetchone()
                if replay is not None:
                    if tuple(replay[1:]) != (semantic, actor.actor_id):
                        raise DocumentRevisionProblem("document-correction-command-conflict")
                    return self.revisions._accepted(connection, replay[0])
                base = self.revisions._accepted(connection, record.patch.base_revision_id)
                result = self._apply(connection, base, record.patch, cancelled=cancelled)
                if not record.patch.operations:
                    raise DocumentRevisionProblem("document-correction-empty")
                if (record.intent_revision_id, record.intent_sha256, record.policy_sha256) != (
                    actor.intent_revision_id,
                    actor.intent_sha256,
                    actor.policy_sha256,
                ):
                    raise DocumentRevisionProblem("document-correction-authority-changed")
                targets = self._targets(connection, result, fresh=True)
                with self.revisions._aggregates(connection) as aggregates:
                    current = aggregates.get(base.document_id)
                    if (
                        current.revision_id != base.revision_id
                        or command.expected_current_revision_id != base.revision_id
                    ):
                        raise DocumentRevisionProblem("document-correction-base-changed")
                    draft_current = aggregates.get(record.draft_id)
                    if draft_current.revision_id != record.revision_id:
                        raise DocumentRevisionProblem("document-correction-draft-changed")
                structure, identities = canonicalize_structure(result.ir)
                accepted = AcceptedDocumentRevision(
                    project_id=self.revisions.project,
                    document_id=base.document_id,
                    revision_id=new_uuid_v7(),
                    previous_revision_id=base.revision_id,
                    result=base.result,
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
                    structure_sha256=value_sha256(structure),
                    element_identities=identities,
                    structure=structure,
                )
                return record, base, current, draft_current, targets, actor, accepted

            prepared = self.revisions._source_fenced(source, prepare)
            if isinstance(prepared, AcceptedDocumentRevision):
                return prepared
            record, base, predecessor, draft_predecessor, targets, owner, accepted = prepared

            def publish(connection, stored):
                self._check(cancelled)
                actor = self.revisions.actor()
                self.revisions._authority(connection, actor)
                if actor != owner or self._record(connection, record.revision_id) != record:
                    raise DocumentRevisionProblem("document-correction-authority-changed")
                result = self._apply(connection, base, record.patch, cancelled=cancelled)
                if self._targets(connection, result, fresh=True) != targets:
                    raise DocumentRevisionProblem("document-correction-reference-authority-changed")
                replay = connection.execute(
                    "SELECT revision_id,command_sha256,actor_id FROM document_normalized_revisions "
                    "WHERE project_id=? AND command_id=?",
                    (self.revisions.project, command.command_id),
                ).fetchone()
                if replay:
                    if tuple(replay[1:]) != (accepted.command_sha256, actor.actor_id):
                        raise DocumentRevisionProblem("document-correction-command-conflict")
                    return self.revisions._accepted(connection, replay[0])
                with self.revisions._aggregates(connection) as aggregates:
                    if (
                        aggregates.get(base.document_id) != predecessor
                        or aggregates.get(record.draft_id) != draft_predecessor
                    ):
                        raise DocumentRevisionProblem("document-correction-predecessor-changed")
                    inputs = (
                        predecessor,
                        aggregates.get_revision(base.result.revision_id),
                        draft_predecessor,
                        *targets,
                    )
                    historical = {base.revision_id}
                    decision = aggregates.append(
                        AggregateRevisionDraft(
                            revision_id=accepted.decision_revision_id,
                            aggregate_id=accepted.decision_id,
                            aggregate_kind="decision",
                            created_at=accepted.accepted_at,
                            modified_at=accepted.accepted_at,
                            display_label_observed="Accept document correction",
                            display_label_normalized=None,
                            knowledge_status="observed",
                            rights_status="allowed",
                            dependency_coverage="complete",
                            provenance_inputs=inputs,
                            material_dependencies=self._dependencies(inputs, historical),
                        ),
                        self.revisions._event(
                            actor,
                            accepted.accepted_at,
                            "decision.created",
                            "document-correction-decision-" + command.command_id,
                        ),
                        expected_revision=None,
                    )
                    inputs = (*inputs, decision)
                    successor = aggregates.append(
                        AggregateRevisionDraft(
                            revision_id=accepted.revision_id,
                            aggregate_id=base.document_id,
                            aggregate_kind="document",
                            created_at=predecessor.created_at,
                            modified_at=accepted.accepted_at,
                            display_label_observed=predecessor.display_label_observed,
                            display_label_normalized=predecessor.display_label_normalized,
                            knowledge_status="extracted",
                            rights_status="allowed",
                            object_sha256=stored.object_sha256,
                            dependency_coverage="complete",
                            provenance_inputs=inputs,
                            material_dependencies=self._dependencies(inputs, historical),
                        ),
                        self.revisions._event(
                            actor,
                            accepted.accepted_at,
                            "document.updated",
                            "document-correction-accept-" + command.command_id,
                        ),
                        expected_revision=predecessor.revision,
                    )
                    connection.execute(
                        "INSERT INTO document_normalized_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            accepted.revision_id,
                            self.revisions.project,
                            accepted.document_id,
                            base.revision_id,
                            base.result.result_id,
                            accepted.decision_id,
                            accepted.decision_revision_id,
                            command.command_id,
                            accepted.command_sha256,
                            stored.object_sha256,
                            accepted.content_sha256,
                            accepted.structure_sha256,
                            actor.actor_id,
                            accepted.accepted_at,
                        ),
                    )
                    self.revisions._elements(connection, accepted)
                    change = DependencyChange(
                        change_id=new_uuid_v7(),
                        idempotency_key="document-correction-impact-" + command.command_id,
                        reason="HUMAN_DECISION",
                        dependency_kind="source-revision",
                        previous_revision_id=base.revision_id,
                        replacement_revision_id=accepted.revision_id,
                        configuration_id=None,
                        previous_configuration_version=None,
                        replacement_configuration_version=None,
                        previous_fingerprint=_projection_content_sha256(predecessor),
                        replacement_fingerprint=_projection_content_sha256(successor),
                        propagation_policy_id="dependency.propagation.v1",
                        propagation_policy_version="1.0.0",
                        actor_id=actor.actor_id,
                        trace_id=actor.trace_id,
                        occurred_at=accepted.accepted_at,
                    )
                    impacts = _SqliteDependencyImpactRepository(self.revisions.database, self.revisions.project)
                    preview = impacts._preview_with_connection(
                        connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
                    )
                    impacts._begin_with_connection(
                        connection, change, preview_sha256=preview.preview_sha256, run_id=new_uuid_v7(), batch_size=100
                    )
                    _publication_step("correction-acceptance-complete")
                    self._check(cancelled)
                return accepted

            return self.revisions._put(
                protected_json(accepted), ACCEPTED_REVISION_MEDIA_TYPE, source, publish, cancelled
            )

        return self.revisions._bounded(accept)


class LocalDocumentReprocessingRepository:
    """Protected proposals and one compound per-document acceptance transaction."""

    def __init__(self, revisions, *, target_resolver=None):
        self.revisions = revisions
        self.corrections = revisions.corrections(target_resolver=target_resolver)
        self.impacts = _SqliteDependencyImpactRepository(revisions.database, revisions.project)

    @staticmethod
    def _check(cancelled):
        if cancelled():
            raise DocumentRevisionProblem("document-reprocessing-stopped")

    def _semantic(self, command, actor):
        return self.corrections._semantic(command, actor)

    def source_for_command(self, command):
        with closing(
            open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
        ) as connection:
            if hasattr(command, "batch"):
                return self.corrections._source_for_revision(connection, command.batch.base_revision_ids[0])
            if hasattr(command, "after_batch_id"):
                return None
            selected = (
                command.reconciliation.comparison_revision_id
                if hasattr(command, "reconciliation")
                else command.acceptance.plan_revision_id
                if hasattr(command, "acceptance")
                else command.continuation.batch_revision_id
                if hasattr(command, "continuation")
                else command.cancellation.batch_revision_id
                if hasattr(command, "cancellation")
                else command.batch_revision_id
            )
            return self._source(connection, self._record(connection, selected))

    def _peek(self, connection, revision_id):
        from pydantic import TypeAdapter

        with self.revisions._aggregates(connection) as aggregates:
            revision = aggregates.get_revision(revision_id)
        metadata = connection.execute(
            "SELECT byte_length,media_type FROM object_records WHERE project_id=? AND object_sha256=?",
            (self.revisions.project, revision.object_sha256),
        ).fetchone()
        if (
            revision.aggregate_kind != "document"
            or metadata is None
            or metadata[1] != reprocessing.REPROCESSING_MEDIA_TYPE
            or not 0 < metadata[0] <= reprocessing.MAX_REPROCESSING_BYTES
        ):
            raise DocumentRevisionProblem("document-reprocessing-unavailable")
        raw = self.revisions.objects._read_protected_document_artifact(
            connection, _ProtectedReceipt(revision.object_sha256, metadata[0]), reprocessing.REPROCESSING_MEDIA_TYPE
        )
        record: reprocessing.ReprocessingRecord = TypeAdapter(reprocessing.ReprocessingRecord).validate_json(raw)
        if (record.project_id, record.revision_id) != (self.revisions.project, revision_id):
            raise DocumentRevisionProblem("document-reprocessing-binding-invalid")
        identity = (
            record.batch_id
            if isinstance(record, reprocessing.ReprocessingBatch)
            else record.comparison_id
            if isinstance(record, reprocessing.ReprocessingComparison)
            else record.plan_id
            if isinstance(record, reprocessing.ReprocessingPlan)
            else record.record_id
        )
        when = (
            record.created_at
            if isinstance(record, reprocessing.ReprocessingComparison)
            else record.accepted_at
            if isinstance(record, reprocessing.ReprocessingAccepted)
            else record.authored_at
        )
        author = (
            record.created_by
            if isinstance(record, reprocessing.ReprocessingComparison)
            else record.accepted_by
            if isinstance(record, reprocessing.ReprocessingAccepted)
            else record.authored_by
        )
        if (identity, when) != (revision.aggregate_id, revision.modified_at):
            raise DocumentRevisionProblem("document-reprocessing-binding-invalid")
        events = connection.execute(
            "SELECT actor_type,actor_id,occurred_at FROM provenance_events WHERE project_id=? AND revision_id=?",
            (self.revisions.project, revision_id),
        ).fetchall()
        if [tuple(e) for e in events] != [("human", author, when)]:
            raise DocumentRevisionProblem("document-reprocessing-author-invalid")
        if not isinstance(record, reprocessing.ReprocessingComparison):
            if record.command_sha256 != self.corrections._semantic_values(
                record.command, author, record.intent_revision_id, record.intent_sha256, record.policy_sha256
            ):
                raise DocumentRevisionProblem("document-reprocessing-command-invalid")
        elif (
            record.command_sha256
            != hashlib.sha256(
                protected_json(record.result) + record.batch_revision_id.encode() + record.item_id.encode()
            ).hexdigest()
        ):
            raise DocumentRevisionProblem("document-reprocessing-command-invalid")
        previous_id = (
            record.previous_revision_id
            if isinstance(record, (reprocessing.ReprocessingBatch, reprocessing.ReprocessingPlan))
            else None
        )
        if previous_id:
            with self.revisions._aggregates(connection) as aggregates:
                previous = aggregates.get_revision(previous_id)
            if (previous.aggregate_id, previous.revision + 1) != (revision.aggregate_id, revision.revision):
                raise DocumentRevisionProblem("document-reprocessing-predecessor-invalid")
        elif revision.revision != 0:
            raise DocumentRevisionProblem("document-reprocessing-predecessor-invalid")
        input_ids = (
            tuple(i.base_revision_id for i in record.items)
            if isinstance(record, reprocessing.ReprocessingBatch)
            and isinstance(record.command, reprocessing.ReprocessingCreate)
            else ()
            if isinstance(record, reprocessing.ReprocessingBatch)
            else (record.batch_revision_id, record.base_revision_id, record.result.revision_id)
            if isinstance(record, reprocessing.ReprocessingComparison)
            else (record.comparison_revision_id,)
            if isinstance(record, reprocessing.ReprocessingPlan)
            else (record.base_revision_id, record.comparison_revision_id, record.plan_revision_id)
        )
        if isinstance(record, reprocessing.ReprocessingAccepted):
            comparison = self._peek(connection, record.comparison_revision_id)
            input_ids = (*input_ids, comparison.result.revision_id)
        if previous_id:
            input_ids = (*input_ids, previous_id)
        with self.revisions._aggregates(connection) as aggregates:
            inputs = tuple(aggregates.get_revision(i) for i in dict.fromkeys(input_ids))
        historical = {i.revision_id for i in inputs}
        if isinstance(record, reprocessing.ReprocessingAccepted):
            historical.discard(comparison.result.revision_id)
        self.corrections._validate_inputs(connection, record.revision_id, inputs, historical)
        return record

    def _record(self, connection, revision_id, expected=None):
        record = self._peek(connection, revision_id)
        if expected is not None and not isinstance(record, expected):
            raise DocumentRevisionProblem("document-reprocessing-binding-invalid")
        return record

    def _source(self, connection, record):
        if isinstance(record, reprocessing.ReprocessingBatch):
            return record.items[0].inputs.source
        if isinstance(record, reprocessing.ReprocessingComparison):
            return record.result.binding.source
        comparison_id = record.comparison_revision_id
        return self._record(connection, comparison_id, reprocessing.ReprocessingComparison).result.binding.source

    def _run(self, revision_id, action, cancelled, *, mutation=False):
        def current():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as connection:
                record = self._record(connection, revision_id)
                source = self._source(connection, record)
            completed = False

            def selected(connection, actor):
                nonlocal completed
                result = action(connection, actor, self._record(connection, revision_id))
                completed = True
                return result

            try:
                result = self.revisions._source_fenced(source, selected)
                self._check(cancelled)
                return result
            except Exception:
                if mutation and completed:
                    raise reprocessing.ReprocessingOutcomeUnknown() from None
                raise

        return self.revisions._bounded(current)

    def _key(self, record):
        if isinstance(record, reprocessing.ReprocessingAccepted):
            return "document-reprocessing-accepted-item-" + record.batch_id + "-" + record.item_id
        if isinstance(record, reprocessing.ReprocessingComparison):
            return "document-reprocessing-compare-" + record.batch_revision_id + "-" + record.item_id
        return "document-reprocessing-" + record.document_type + "-" + record.command.command_id

    def _replay(self, connection, key):
        row = connection.execute(
            "SELECT revision_id FROM outbox_events WHERE project_id=? AND idempotency_key=?",
            (self.revisions.project, key),
        ).fetchone()
        return None if row is None else self._record(connection, row[0])

    def _write(self, record, source, inputs, *, previous=None, check=lambda _c, _a: None, cancelled=lambda: False):
        owner = self.revisions.actor()
        raw = protected_json(record)
        if len(raw) > reprocessing.MAX_REPROCESSING_BYTES:
            raise DocumentRevisionProblem("document-reprocessing-limit")

        def publish(connection, stored):
            self._check(cancelled)
            actor = self.revisions.actor()
            self.revisions._authority(connection, actor)
            if actor != owner:
                raise DocumentRevisionProblem("document-reprocessing-authority-changed")
            replay = self._replay(connection, self._key(record))
            if replay is not None:
                if replay.command_sha256 != record.command_sha256:
                    raise DocumentRevisionProblem("document-reprocessing-command-conflict")
                return replay
            check(connection, actor)
            with self.revisions._aggregates(connection) as aggregates:
                predecessor = None if previous is None else aggregates.get_revision(previous)
                identity = (
                    record.batch_id
                    if isinstance(record, reprocessing.ReprocessingBatch)
                    else record.comparison_id
                    if isinstance(record, reprocessing.ReprocessingComparison)
                    else record.plan_id
                )
                if predecessor is not None and aggregates.get(identity) != predecessor:
                    raise DocumentRevisionProblem("document-reprocessing-predecessor-changed")
                retained = tuple(
                    aggregates.get_revision(i) for i in dict.fromkeys((*inputs, *((previous,) if previous else ())))
                )
                aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=record.revision_id,
                        aggregate_id=identity,
                        aggregate_kind="document",
                        created_at=predecessor.created_at if predecessor else actor.occurred_at,
                        modified_at=actor.occurred_at,
                        display_label_observed=record.document_type,
                        display_label_normalized=None,
                        knowledge_status="observed",
                        rights_status="allowed",
                        dependency_coverage="complete",
                        object_sha256=stored.object_sha256,
                        provenance_inputs=retained,
                        material_dependencies=self.corrections._dependencies(
                            retained, set(i.revision_id for i in retained)
                        ),
                    ),
                    self.revisions._event(
                        actor,
                        actor.occurred_at,
                        "document.updated" if predecessor else "document.created",
                        self._key(record),
                    ),
                    expected_revision=predecessor.revision if predecessor else None,
                )
            _publication_step("reprocessing-proposal-complete")
            self._check(cancelled)
            return record

        return self._publish_outcome(raw, source, publish, cancelled)

    @staticmethod
    @contextmanager
    def _after_publication():
        try:
            yield
        except Exception:
            raise reprocessing.ReprocessingOutcomeUnknown() from None

    def _publish_outcome(self, raw, source, publish, cancelled):
        completed = False

        def prepared(connection, stored):
            nonlocal completed
            result = publish(connection, stored)
            completed = True
            return result

        try:
            return self.revisions._put(raw, reprocessing.REPROCESSING_MEDIA_TYPE, source, prepared, cancelled)
        except Exception:
            # Once the publication callback completes, a commit/adapter error
            # can no longer establish that the immutable mutation is absent.
            if completed:
                raise reprocessing.ReprocessingOutcomeUnknown() from None
            raise

    def _latest_batch(self, connection, batch):
        with self.revisions._aggregates(connection) as aggregates:
            head = aggregates.get(batch.batch_id)
        current = self._record(connection, head.revision_id, reprocessing.ReprocessingBatch)
        if current.batch_id != batch.batch_id or tuple((i.item_id, i.base_revision_id) for i in current.items) != tuple(
            (i.item_id, i.base_revision_id) for i in batch.items
        ):
            raise DocumentRevisionProblem("document-reprocessing-batch-binding-invalid")
        return current

    def _current_batch_view(self, batch, cancelled):
        return self._run(batch.revision_id, lambda c, a, b: self._batch_view(c, self._latest_batch(c, b), a), cancelled)

    def _submit_current_items(self, batch, items, cancelled):
        class AdmissionChanged(DocumentRevisionProblem):
            pass

        for item in items:
            self._check(cancelled)

            def admission(connection, actor, item=item):
                self._check(cancelled)
                current = self._latest_batch(connection, batch)
                if current.revision_id != batch.revision_id or current.state != "active":
                    raise AdmissionChanged("document-reprocessing-batch-changed")
                if self._item(current, item.item_id) != item or self._accepted_item(connection, current, item):
                    raise AdmissionChanged("document-reprocessing-item-changed")
                self._fence(connection, item.inputs.source, actor)
                base = self.revisions._accepted(connection, item.base_revision_id)
                with self.revisions._aggregates(connection) as aggregates:
                    if aggregates.get(base.document_id).revision_id != base.revision_id:
                        raise AdmissionChanged("document-reprocessing-base-changed")

            # The authenticated latest head is also the retry response. Never
            # submit an older command's unsubmitted input after a successor.
            view = self._current_batch_view(batch, cancelled)
            if view.batch_revision_id != batch.revision_id or view.state != "active":
                return view
            try:
                self.revisions.submit(item.inputs, admission=admission)
            except AdmissionChanged:
                return self._current_batch_view(batch, cancelled)
        return self._current_batch_view(batch, cancelled)

    def _current_batch(self, connection, batch):
        with self.revisions._aggregates(connection) as aggregates:
            if aggregates.get(batch.batch_id).revision_id != batch.revision_id or batch.state != "active":
                raise DocumentRevisionProblem("document-reprocessing-batch-changed")

    def _fence(self, connection, source, actor):
        self.revisions.objects._open_document_attachment(
            source.attachment_id,
            source.document_revision_id,
            actor=actor,
            expected_source=source,
            publication_connection=connection,
            before_stream=lambda c: self.revisions._authority(c, actor),
        )

    def _item(self, batch, item_id):
        item = next((i for i in batch.items if i.item_id == item_id), None)
        if item is None:
            raise DocumentRevisionProblem("document-reprocessing-item-unavailable")
        return item

    def _job(self, connection, item):
        row = connection.execute(
            "SELECT job_id FROM document_parse_jobs WHERE project_id=? AND command_id=?",
            (self.revisions.project, item.inputs.command_id),
        ).fetchone()
        if row is None:
            return None
        if self.revisions._input(connection, row[0]) != item.inputs:
            raise DocumentRevisionProblem("document-reprocessing-input-invalid")
        return self.revisions.queue._accepted_status_with_connection(connection, row[0])[0]

    def _accepted_item(self, connection, batch, item):
        key = "document-reprocessing-accepted-item-" + batch.batch_id + "-" + item.item_id
        return self._replay(connection, key)

    def _batch_view(self, connection, batch, actor):
        rows = []
        for item in batch.items:
            # Every item has its own original-copy permission; a batch is no grant.
            self._fence(connection, item.inputs.source, actor)
            base = self.revisions._accepted(connection, item.base_revision_id)
            job = self._job(connection, item)
            accepted = self._accepted_item(connection, batch, item)
            with self.revisions._aggregates(connection) as aggregates:
                current = aggregates.get(base.document_id)
            state: reprocessing.ItemState = (
                "accepted"
                if accepted
                else "cancelled"
                if batch.state == "cancelled"
                else "base-conflict"
                if current.revision_id != base.revision_id
                else "not-submitted"
                if job is None
                else "ready"
                if job.state == "succeeded"
                else "failed"
                if job.state == "failed"
                else "cancelled"
                if job.state == "cancelled"
                else "needs-continuation"
                if item.inputs.session_id != getattr(self, "session_id", item.inputs.session_id)
                or job.state == "interrupted"
                else "processing"
            )
            rows.append(
                reprocessing.ReprocessingItemView(
                    item_id=item.item_id,
                    base_revision_id=item.base_revision_id,
                    job_id=None if job is None else job.job_id,
                    state=state,
                    accepted_revision_id=None if accepted is None else accepted.final_revision_id,
                )
            )
        return reprocessing.ReprocessingBatchView(
            project_id=self.revisions.project,
            batch_id=batch.batch_id,
            batch_revision_id=batch.revision_id,
            state=batch.state,
            items=tuple(rows),
        )

    def create(self, command, *, input_factory, cancelled=lambda: False):
        command = reprocessing.ReprocessingCreate.model_validate(command)

        def create():
            self._check(cancelled)
            actor = self.revisions.actor()
            key = "document-reprocessing-document-reprocessing-batch-" + command.command_id
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as connection:
                self.revisions._authority(connection, actor)
                replay = self._replay(connection, key)
                if replay:
                    if replay.command_sha256 != self._semantic(command, actor):
                        raise DocumentRevisionProblem("document-reprocessing-command-conflict")
                    batch = replay
                else:
                    bases = tuple(
                        self.revisions._accepted(connection, identity) for identity in command.base_revision_ids
                    )
                    if len({b.document_id for b in bases}) != len(bases):
                        raise DocumentRevisionProblem("document-reprocessing-duplicate-document")
                    items = []
                    for base in bases:
                        inputs = input_factory(base)
                        if inputs.source != base.result.binding.source:
                            raise DocumentRevisionProblem("document-reprocessing-source-changed")
                        self.revisions._source_fenced(inputs.source, lambda c, a: self.revisions._authority(c, a))
                        with self.revisions._aggregates(connection) as aggregates:
                            if aggregates.get(base.document_id).revision_id != base.revision_id:
                                raise DocumentRevisionProblem("document-reprocessing-base-changed")
                        items.append(
                            reprocessing.ReprocessingItem(
                                item_id=new_uuid_v7(), base_revision_id=base.revision_id, inputs=inputs
                            )
                        )
                    batch = reprocessing.ReprocessingBatch(
                        project_id=self.revisions.project,
                        batch_id=new_uuid_v7(),
                        revision_id=new_uuid_v7(),
                        previous_revision_id=None,
                        command=command,
                        command_id=command.command_id,
                        command_sha256=self._semantic(command, actor),
                        authored_by=actor.actor_id,
                        authored_at=actor.occurred_at,
                        intent_revision_id=actor.intent_revision_id,
                        intent_sha256=actor.intent_sha256,
                        policy_sha256=actor.policy_sha256,
                        state="active",
                        items=tuple(items),
                    )
            if replay is None:

                def check(connection, _actor):
                    with self.revisions._aggregates(connection) as aggregates:
                        for base in bases:
                            self._fence(connection, base.result.binding.source, _actor)
                            if aggregates.get(base.document_id).revision_id != base.revision_id:
                                raise DocumentRevisionProblem("document-reprocessing-base-changed")

                batch = self._write(
                    batch, batch.items[0].inputs.source, command.base_revision_ids, check=check, cancelled=cancelled
                )
            with self._after_publication():
                # Persistence precedes enqueue. Exact retry retains immutable
                # inputs, while every missing job needs current batch admission.
                return self._submit_current_items(batch, batch.items, cancelled)

        return self.revisions._bounded(create)

    def read(self, batch_revision_id, *, cancelled=lambda: False):
        return self._run(batch_revision_id, lambda c, a, b: self._batch_view(c, b, a), cancelled)

    def queue(self, *, after_batch_id=None, cancelled=lambda: False):
        def queue():
            self._check(cancelled)
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as connection:
                self.revisions._authority(connection, self.revisions.actor())
                rows = connection.execute(
                    "SELECT r.aggregate_id,r.revision_id FROM aggregate_revisions r "
                    "WHERE r.project_id=? AND r.display_label_observed=? AND r.aggregate_id>? "
                    "AND NOT EXISTS (SELECT 1 FROM aggregate_revisions later WHERE later.project_id=r.project_id "
                    "AND later.aggregate_id=r.aggregate_id AND later.revision>r.revision) "
                    "ORDER BY r.aggregate_id LIMIT 11",
                    (self.revisions.project, "document-reprocessing-batch", after_batch_id or ""),
                ).fetchall()
            views = tuple(self.read(row[1], cancelled=cancelled) for row in rows[:10])
            return reprocessing.ReprocessingQueue(
                project_id=self.revisions.project,
                items=views,
                next_after_batch_id=rows[9][0] if len(rows) > 10 else None,
            )

        return self.revisions._bounded(queue)

    def _generations(self, connection, accepted):
        result: list[CorrectionDraft] = []
        current = accepted
        context = _CorrectionReadContext(connection, self.revisions.project)
        while True:
            with self.revisions._aggregates(connection) as aggregates:
                decision = aggregates.get_revision(current.decision_revision_id)
            if decision.display_label_observed != "Accept document correction":
                break
            if len(result) >= 32:
                raise DocumentRevisionProblem("document-reprocessing-limit")
            draft = self.corrections._verify_accepted(connection, current, context=context)
            result.append(draft)
            current = self.revisions._accepted(connection, draft.patch.base_revision_id, correction_context=context)
        return tuple(reversed(result))

    def _comparison(self, connection, comparison):
        batch = self._record(connection, comparison.batch_revision_id, reprocessing.ReprocessingBatch)
        item = self._item(batch, comparison.item_id)
        job = self._job(connection, item)
        if (
            job is None
            or job.state != "succeeded"
            or (job.job_id, job.current_attempt_id) != (comparison.job_id, comparison.result.binding.attempt.attempt_id)
        ):
            raise DocumentRevisionProblem("document-reprocessing-result-binding-invalid")
        output = self.revisions.queue._accepted_status_with_connection(connection, job.job_id)[1]
        if output is None or len(output.outputs) != 1 or output.outputs[0].artifact_id != comparison.result.result_id:
            raise DocumentRevisionProblem("document-reprocessing-result-binding-invalid")
        receipt = self.revisions._receipt(connection, comparison.result.result_id)
        parsed = self.revisions._result(connection, receipt)
        source, producer = selected_values(item.inputs.selection)
        if (
            receipt,
            receipt.binding.source,
            receipt.binding.producer,
            receipt.binding.selection_sha256,
            receipt.binding.attempt.job_id,
        ) != (comparison.result, source, producer, selection_sha256(item.inputs.selection), job.job_id):
            raise DocumentRevisionProblem("document-reprocessing-result-binding-invalid")
        base = self.revisions._accepted(connection, comparison.base_revision_id)
        factory = iter(m.canonical_id for m in comparison.candidate.element_identities)
        structure, identities = canonicalize_structure(parsed.ir, identity_factory=lambda: next(factory))
        if (
            comparison.candidate.structure,
            comparison.candidate.element_identities,
            comparison.candidate.result,
            comparison.base_revision_id,
        ) != (structure, identities, receipt, item.base_revision_id):
            raise DocumentRevisionProblem("document-reprocessing-candidate-invalid")
        drafts = self._generations(connection, base)
        if tuple(d.revision_id for d in drafts) != comparison.correction_revision_ids:
            raise DocumentRevisionProblem("document-reprocessing-obligations-invalid")
        return batch, item, base, drafts

    def compare(self, batch_revision_id, item_id, *, offset=0, cancelled=lambda: False):
        def prepare(connection, actor, batch):
            self._current_batch(connection, batch)
            item = self._item(batch, item_id)
            self._fence(connection, item.inputs.source, actor)
            key = "document-reprocessing-compare-" + batch_revision_id + "-" + item_id
            replay = self._replay(connection, key)
            if replay:
                return replay
            job = self._job(connection, item)
            if job is None or job.state != "succeeded":
                raise DocumentRevisionProblem("document-reprocessing-output-unavailable")
            output = self.revisions.queue._accepted_status_with_connection(connection, job.job_id)[1]
            if output is None or len(output.outputs) != 1:
                raise DocumentRevisionProblem("document-reprocessing-output-unavailable")
            receipt = self.revisions._receipt(connection, output.outputs[0].artifact_id)
            parsed = self.revisions._result(connection, receipt)
            if (
                receipt.binding.attempt.job_id,
                receipt.binding.attempt.attempt_id,
                receipt.binding.source,
                receipt.binding.selection_sha256,
            ) != (job.job_id, job.current_attempt_id, item.inputs.source, selection_sha256(item.inputs.selection)):
                raise DocumentRevisionProblem("document-reprocessing-result-binding-invalid")
            base = self.revisions._accepted(connection, item.base_revision_id)
            structure, identities = canonicalize_structure(parsed.ir)
            candidate = CorrectionPreviewBase(
                revision_id=new_uuid_v7(),
                result=receipt,
                structure_sha256=value_sha256(structure),
                element_identities=identities,
                structure=structure,
            )
            return reprocessing.ReprocessingComparison(
                project_id=self.revisions.project,
                comparison_id=new_uuid_v7(),
                revision_id=new_uuid_v7(),
                batch_revision_id=batch_revision_id,
                item_id=item_id,
                base_revision_id=base.revision_id,
                job_id=job.job_id,
                result=receipt,
                candidate=candidate,
                correction_revision_ids=tuple(d.revision_id for d in self._generations(connection, base)),
                created_by=actor.actor_id,
                created_at=actor.occurred_at,
                command_sha256=hashlib.sha256(
                    protected_json(receipt) + batch_revision_id.encode() + item_id.encode()
                ).hexdigest(),
            )

        comparison = self._run(batch_revision_id, prepare, cancelled)

        def check(connection, _actor):
            self._comparison(connection, comparison)
            self._current_batch(connection, self._record(connection, batch_revision_id, reprocessing.ReprocessingBatch))

        comparison = self._write(
            comparison,
            comparison.result.binding.source,
            (batch_revision_id, comparison.base_revision_id, comparison.result.revision_id),
            check=check,
            cancelled=cancelled,
        )
        return self._page(comparison.revision_id, offset=offset, cancelled=cancelled)

    def _latest_plan(self, connection, comparison_id):
        rows = connection.execute(
            "SELECT d.revision_id FROM material_dependencies m JOIN aggregate_revisions d "
            "ON d.project_id=m.project_id AND d.revision_id=m.output_revision_id "
            "WHERE m.project_id=? AND m.dependency_revision_id=? AND d.display_label_observed=? "
            "AND NOT EXISTS (SELECT 1 FROM aggregate_revisions later WHERE later.project_id=d.project_id "
            "AND later.aggregate_id=d.aggregate_id AND later.revision>d.revision) LIMIT 2",
            (self.revisions.project, comparison_id, "document-reprocessing-plan"),
        ).fetchall()
        if len(rows) > 1:
            raise DocumentRevisionProblem("document-reprocessing-plan-conflict")
        return None if not rows else self._record(connection, rows[0][0], reprocessing.ReprocessingPlan)

    def _plan_values(self, connection, comparison, plan, *, cancelled=lambda: False):
        batch, item, base, drafts = self._comparison(connection, comparison)
        candidate = comparison.candidate
        inherited = CorrectionInheritance(
            base_revision_id=candidate.revision_id,
            expected_structure_sha256=candidate.structure_sha256,
            labels=(),
            excluded_node_ids=(),
            reference_matches=(),
        )
        results = []
        if plan is not None:
            if plan.comparison_revision_id != comparison.revision_id or len(plan.steps) > len(drafts):
                raise DocumentRevisionProblem("document-reprocessing-plan-invalid")
            for draft, step in zip(drafts, plan.steps, strict=False):
                self._check(cancelled)
                patch = reprocessing.mapped_patch(draft, candidate, step.mappings)
                if (step.original_draft_revision_id, step.mapped_patch) != (draft.revision_id, patch):
                    raise DocumentRevisionProblem("document-reprocessing-plan-invalid")
                result = apply_correction(candidate, patch, inherited=inherited, cancelled=cancelled)
                factory = iter(m.canonical_id for m in step.next_candidate.element_identities)
                structure, identities = canonicalize_structure(result.ir, identity_factory=factory.__next__)
                if (
                    step.next_candidate.structure,
                    step.next_candidate.element_identities,
                    step.next_candidate.result,
                ) != (structure, identities, comparison.result):
                    raise DocumentRevisionProblem("document-reprocessing-plan-invalid")
                candidate = step.next_candidate
                inherited = reprocessing.preview_inheritance(candidate, result)
                self.corrections._targets(connection, result, fresh=False)
                results.append(result)
        return batch, item, base, drafts, candidate, inherited, tuple(results)

    def _change(self, base_revision, replacement_id, actor, *, key, replacement_fingerprint):
        return DependencyChange(
            change_id=new_uuid_v7(),
            idempotency_key=key,
            reason="HUMAN_DECISION",
            dependency_kind="source-revision",
            previous_revision_id=base_revision.revision_id,
            replacement_revision_id=replacement_id,
            configuration_id=None,
            previous_configuration_version=None,
            replacement_configuration_version=None,
            previous_fingerprint=_projection_content_sha256(base_revision),
            replacement_fingerprint=replacement_fingerprint,
            propagation_policy_id="dependency.propagation.v1",
            propagation_policy_version="1.0.0",
            actor_id=actor.actor_id,
            trace_id=actor.trace_id,
            occurred_at=actor.occurred_at,
        )

    def _prospective(self, connection, base, candidate, actor):
        with self.revisions._aggregates(connection) as aggregates:
            predecessor = aggregates.get_revision(base.revision_id)
        change = self._change(
            predecessor,
            candidate.revision_id,
            actor,
            key="document-reprocessing-preview-" + candidate.revision_id,
            replacement_fingerprint="sha256:" + candidate.structure_sha256,
        )
        return self.impacts._plan_with_connection(
            connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
        )

    @staticmethod
    def _counts(items):
        counts = {
            name: 0 for name in ("unchanged", "moved", "modified", "added", "removed", "ambiguous", "unresolvable")
        }
        for item in items:
            counts[item.state] += 1
        return reprocessing.ReprocessingCounts(**counts)

    def _anchors(self, connection, base, candidate, cancelled):
        from .anchors.contracts import ANCHOR_MEDIA_TYPE

        history = [base.revision_id]
        for draft in reversed(self._generations(connection, base)):
            history.append(draft.patch.base_revision_id)
        placeholders = ",".join("?" for _ in history)
        rows = connection.execute(
            "SELECT DISTINCT r.aggregate_id FROM material_dependencies m JOIN aggregate_revisions r "
            "ON r.project_id=m.project_id AND r.revision_id=m.output_revision_id "
            "JOIN documents d ON d.project_id=r.project_id AND d.revision_id=r.revision_id "
            "JOIN object_records o ON o.project_id=d.project_id AND o.object_sha256=d.object_sha256 "
            "WHERE m.project_id=? AND m.dependency_revision_id IN ("
            + placeholders
            + ") AND o.media_type=? ORDER BY r.aggregate_id LIMIT 10001",
            (self.revisions.project, *history, ANCHOR_MEDIA_TYPE),
        ).fetchall()
        if len(rows) > reprocessing.MAX_REPROCESSING_ITEMS:
            raise DocumentRevisionProblem("document-reprocessing-limit")
        result = []
        anchors = self.revisions.source_anchors()
        for row in rows:
            self._check(cancelled)
            record = anchors._record(connection, row[0])
            old = self.revisions._accepted(connection, record.target.revision_id)
            node = next(n for n in old.structure.nodes if n.node_id == record.target.node_id)
            result.append(
                reprocessing.anchor_candidates(
                    record.anchor_id, record.target, candidate, old_locator=node.locator, cancelled=cancelled
                )
            )
        return tuple(result)

    def _page(self, comparison_revision_id, *, offset=0, cancelled=lambda: False):
        if type(offset) is not int or not 0 <= offset <= 100_000:
            raise DocumentRevisionProblem("document-reprocessing-page-invalid")

        def page(connection, actor, comparison):
            plan = self._latest_plan(connection, comparison.revision_id)
            batch, item, base, drafts, candidate, _inherited, _results = self._plan_values(
                connection, comparison, plan, cancelled=cancelled
            )
            generation = 0 if plan is None else len(plan.steps)
            obligations = []
            if generation < len(drafts):
                draft = drafts[generation]
                old = self.revisions._accepted(connection, draft.patch.base_revision_id)
                nodes = {n.node_id: n for n in old.structure.nodes}
                for index, operation in enumerate(draft.patch.operations):
                    node = nodes[operation.node_id]
                    obligations.append(
                        reprocessing.ReprocessingObligation(
                            obligation_id=reprocessing.operation_id(draft.revision_id, index, operation),
                            original_draft_revision_id=draft.revision_id,
                            original_base_revision_id=draft.patch.base_revision_id,
                            operation_index=index,
                            operation=operation.op,
                            old_node_id=node.node_id,
                            old_node_sha256=value_sha256(node),
                            old_preview=reprocessing.node_text(old.structure, node)[:160],
                            related_old_node_id=operation.before_node_id
                            if operation.op == "reorder"
                            else operation.with_node_id
                            if operation.op == "merge"
                            else None,
                            original_reference_id=operation.reference_id
                            if operation.op == "reference-rematch"
                            else None,
                            original_author=draft.authored_by,
                            original_rationale=draft.rationale[:160],
                        )
                    )
            total = sum(len(d.patch.operations) for d in drafts)
            unresolved = sum(len(d.patch.operations) for d in drafts[generation:])
            differences = reprocessing.compare_structures(base.structure, candidate.structure, cancelled=cancelled)
            anchors = self._anchors(connection, base, candidate, cancelled)
            if len(differences) + len(anchors) + len(candidate.structure.nodes) > reprocessing.MAX_REPROCESSING_ITEMS:
                raise DocumentRevisionProblem("document-reprocessing-limit")
            candidate_nodes = tuple(
                reprocessing.ReprocessingNode(
                    node_id=n.node_id,
                    parent_id=n.parent_id,
                    order=n.order,
                    kind=n.kind,
                    preview=reprocessing.node_text(candidate.structure, n)[:160],
                    node_sha256=value_sha256(n),
                    reference_id=next(
                        (r.reference_id for r in candidate.structure.references if r.node_id == n.node_id), None
                    ),
                )
                for n in candidate.structure.nodes[offset : offset + 20]
            )
            with self.revisions._aggregates(connection) as aggregates:
                current = aggregates.get(base.document_id)
            prospective = self._prospective(connection, base, candidate, actor)
            state: Literal["review", "ready-to-accept", "base-conflict"] = (
                "base-conflict"
                if current.revision_id != base.revision_id
                else "ready-to-accept"
                if plan is not None and unresolved == 0
                else "review"
            )
            old_parsed = self.revisions._result(connection, base.result)
            new_parsed = self.revisions._result(connection, comparison.result)
            length = max(len(differences), len(anchors), len(candidate.structure.nodes))
            result = reprocessing.ReprocessingPage(
                project_id=self.revisions.project,
                batch_id=batch.batch_id,
                batch_revision_id=batch.revision_id,
                item_id=item.item_id,
                base_revision_id=base.revision_id,
                current_revision_id=current.revision_id,
                source=comparison.result.binding.source,
                job_id=comparison.job_id,
                attempt_id=comparison.result.binding.attempt.attempt_id,
                result_id=comparison.result.result_id,
                comparison_revision_id=comparison.revision_id,
                candidate_revision_id=candidate.revision_id,
                plan_revision_id=None if plan is None else plan.revision_id,
                confirmation_sha256=None if plan is None else value_sha256(plan),
                generation=generation,
                generation_count=len(drafts),
                total_obligations=total,
                unresolved_count=unresolved,
                obligations=tuple(obligations),
                candidate_nodes=candidate_nodes,
                differences=differences[offset : offset + 20],
                difference_counts=self._counts(differences),
                anchor_candidates=anchors[offset : offset + 20],
                anchor_counts=self._counts(anchors),
                next_offset=offset + 20 if offset + 20 < length else None,
                old_quality=assess_ir(old_parsed.ir, cancelled=cancelled),
                new_quality=assess_ir(new_parsed.ir, cancelled=cancelled),
                impact=reprocessing.ReprocessingImpact(
                    graph_sha256=prospective.graph_sha256.removeprefix("sha256:"),
                    affected_count=len(prospective.affected_output_revision_ids),
                    informational_count=len(prospective.informational_output_revision_ids),
                    legacy_unreported_count=prospective.legacy_unreported_count,
                ),
                state=state,
            )
            if len(protected_json(result)) > 128 * 1024:
                raise DocumentRevisionProblem("document-reprocessing-limit")
            self._check(cancelled)
            return result

        return self._run(comparison_revision_id, page, cancelled)

    def reconcile(self, command, *, cancelled=lambda: False):
        command = reprocessing.ReprocessingReconcile.model_validate(command)
        if not command.rationale.strip():
            raise DocumentRevisionProblem("document-reprocessing-rationale-empty")

        def prepare(connection, actor, comparison):
            key = "document-reprocessing-document-reprocessing-plan-" + command.command_id
            replay = self._replay(connection, key)
            if replay:
                if replay.command_sha256 != self._semantic(command, actor):
                    raise DocumentRevisionProblem("document-reprocessing-command-conflict")
                return replay
            previous = self._latest_plan(connection, comparison.revision_id)
            if (None if previous is None else previous.revision_id) != command.expected_plan_revision_id:
                raise DocumentRevisionProblem("document-reprocessing-plan-changed")
            batch, _item, base, drafts, candidate, inherited, _results = self._plan_values(
                connection, comparison, previous, cancelled=cancelled
            )
            self._current_batch(connection, batch)
            with self.revisions._aggregates(connection) as aggregates:
                if aggregates.get(base.document_id).revision_id != base.revision_id:
                    raise DocumentRevisionProblem("document-reprocessing-base-changed")
            steps = () if previous is None else previous.steps
            if len(steps) < len(drafts):
                draft = drafts[len(steps)]
                patch = reprocessing.mapped_patch(draft, candidate, command.mappings)
                successor, result = reprocessing.preview_step(
                    candidate, patch, inherited, revision_id=new_uuid_v7(), cancelled=cancelled
                )
                self.corrections._targets(connection, result, fresh=True)
                steps = (
                    *steps,
                    reprocessing.ReconciledGeneration(
                        original_draft_revision_id=draft.revision_id,
                        mapped_patch=patch,
                        mappings=command.mappings,
                        next_candidate=successor,
                    ),
                )
            elif command.mappings or drafts:
                raise DocumentRevisionProblem("document-reprocessing-reconciliation-complete")
            return reprocessing.ReprocessingPlan(
                project_id=self.revisions.project,
                plan_id=new_uuid_v7() if previous is None else previous.plan_id,
                revision_id=new_uuid_v7(),
                previous_revision_id=None if previous is None else previous.revision_id,
                comparison_revision_id=comparison.revision_id,
                command=command,
                command_sha256=self._semantic(command, actor),
                authored_by=actor.actor_id,
                authored_at=actor.occurred_at,
                intent_revision_id=actor.intent_revision_id,
                intent_sha256=actor.intent_sha256,
                policy_sha256=actor.policy_sha256,
                steps=steps,
            )

        plan = self._run(command.comparison_revision_id, prepare, cancelled)

        def check(connection, actor):
            current = self._latest_plan(connection, plan.comparison_revision_id)
            if (None if current is None else current.revision_id) != plan.previous_revision_id:
                raise DocumentRevisionProblem("document-reprocessing-plan-changed")
            comparison = self._record(connection, plan.comparison_revision_id, reprocessing.ReprocessingComparison)
            values = self._plan_values(connection, comparison, plan, cancelled=cancelled)
            self._current_batch(connection, values[0])
            if values[-1]:
                self.corrections._targets(connection, values[-1][-1], fresh=True)

        with closing(
            open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
        ) as connection:
            comparison = self._record(connection, plan.comparison_revision_id, reprocessing.ReprocessingComparison)
        self._write(
            plan,
            comparison.result.binding.source,
            (plan.comparison_revision_id,),
            previous=plan.previous_revision_id,
            check=check,
            cancelled=cancelled,
        )
        with self._after_publication():
            return self._page(plan.comparison_revision_id, cancelled=cancelled)

    def _verify_machine(self, connection, machine):
        rows = connection.execute(
            "SELECT d.dependency_revision_id FROM material_dependencies d JOIN documents r "
            "ON r.project_id=d.project_id AND r.revision_id=d.dependency_revision_id "
            "JOIN object_records o ON o.project_id=r.project_id AND o.object_sha256=r.object_sha256 "
            "WHERE d.project_id=? AND d.output_revision_id=? AND o.media_type=? LIMIT 2",
            (self.revisions.project, machine.decision_revision_id, reprocessing.REPROCESSING_MEDIA_TYPE),
        ).fetchall()
        if len(rows) != 1:
            raise DocumentRevisionProblem("document-reprocessing-acceptance-record-missing")
        record = self._record(connection, rows[0][0], reprocessing.ReprocessingAccepted)
        comparison = self._record(connection, record.comparison_revision_id, reprocessing.ReprocessingComparison)
        plan = self._record(connection, record.plan_revision_id, reprocessing.ReprocessingPlan)
        batch, item, base, drafts, candidate, _inheritance, results = self._plan_values(connection, comparison, plan)
        if len(plan.steps) != len(drafts) or (
            record.batch_id,
            record.batch_revision_id,
            record.item_id,
            record.base_revision_id,
            record.machine_revision_id,
            record.final_revision_id,
            record.command.plan_revision_id,
            record.command.confirmation_sha256,
            record.command.expected_current_revision_id,
            record.accepted_by,
            record.intent_revision_id,
            record.intent_sha256,
            record.policy_sha256,
        ) != (
            batch.batch_id,
            batch.revision_id,
            item.item_id,
            base.revision_id,
            comparison.candidate.revision_id,
            candidate.revision_id,
            plan.revision_id,
            value_sha256(plan),
            base.revision_id,
            machine.accepted_by,
            machine.intent_revision_id,
            machine.intent_sha256,
            machine.policy_sha256,
        ):
            raise DocumentRevisionProblem("document-reprocessing-acceptance-binding-invalid")
        ordinary = DocumentRevisionAcceptance(
            command_id=record.machine_command_id,
            result_id=comparison.result.result_id,
            expected_current_revision_id=base.revision_id,
            confirmation_sha256=hashlib.sha256(comparison.result.model_dump_json(by_alias=True).encode()).hexdigest(),
            decision="accept-structure",
        )
        semantic = hashlib.sha256(
            protected_json(ordinary) + protected_json(comparison.result) + record.accepted_by.encode()
        ).hexdigest()
        if (
            machine.previous_revision_id,
            machine.result,
            machine.structure,
            machine.element_identities,
            machine.command_id,
            machine.command_sha256,
            machine.decision_id,
            machine.decision_revision_id,
        ) != (
            base.revision_id,
            comparison.result,
            comparison.candidate.structure,
            comparison.candidate.element_identities,
            record.machine_command_id,
            semantic,
            record.machine_decision_id,
            record.machine_decision_revision_id,
        ) or semantic != record.machine_command_sha256:
            raise DocumentRevisionProblem("document-reprocessing-machine-binding-invalid")
        if len(record.nested_draft_revision_ids) != len(plan.steps) or len(record.final_command_ids) != len(plan.steps):
            raise DocumentRevisionProblem("document-reprocessing-reconciliation-binding-invalid")
        for step, result, draft_id, command_id in zip(
            plan.steps, results, record.nested_draft_revision_ids, record.final_command_ids, strict=True
        ):
            # Literal nested correction verification recurses through this machine.
            # Here authenticate the protected outer-to-draft/value bindings without
            # recursing back into the final accepted read.
            with self.revisions._aggregates(connection) as aggregates:
                revision = aggregates.get_revision(draft_id)
            metadata = connection.execute(
                "SELECT byte_length,media_type FROM object_records WHERE project_id=? AND object_sha256=?",
                (self.revisions.project, revision.object_sha256),
            ).fetchone()
            if metadata is None or metadata[1] != CORRECTION_MEDIA_TYPE or metadata[0] > MAX_CORRECTION_RECORD_BYTES:
                raise DocumentRevisionProblem("document-reprocessing-reconciliation-binding-invalid")
            draft = CorrectionDraft.model_validate_json(
                self.revisions.objects._read_protected_document_artifact(
                    connection, _ProtectedReceipt(revision.object_sha256, metadata[0]), CORRECTION_MEDIA_TYPE
                )
            )
            if (
                draft.patch,
                draft.source,
                draft.rationale,
                draft.authored_by,
                draft.intent_revision_id,
                draft.intent_sha256,
                draft.policy_sha256,
                draft.preview_sha256,
                draft.previous_draft_revision_id,
                draft.state,
            ) != (
                step.mapped_patch,
                comparison.result.binding.source,
                plan.command.rationale,
                record.accepted_by,
                record.intent_revision_id,
                record.intent_sha256,
                record.policy_sha256,
                result.result_sha256,
                None,
                "draft",
            ):
                raise DocumentRevisionProblem("document-reprocessing-reconciliation-binding-invalid")
            successor = connection.execute(
                "SELECT previous_revision_id,result_id,command_id,actor_id FROM document_normalized_revisions "
                "WHERE project_id=? AND revision_id=?",
                (self.revisions.project, step.next_candidate.revision_id),
            ).fetchone()
            if successor is None or tuple(successor) != (
                step.mapped_patch.base_revision_id,
                comparison.result.result_id,
                command_id,
                record.accepted_by,
            ):
                raise DocumentRevisionProblem("document-reprocessing-reconciliation-binding-invalid")
        with self.revisions._aggregates(connection) as aggregates:
            old = aggregates.get_revision(base.revision_id)
            final = aggregates.get_revision(record.final_revision_id)
        run = connection.execute(
            "SELECT previous_revision_id,replacement_revision_id,previous_fingerprint,replacement_fingerprint,"
            "actor_id,occurred_at,idempotency_key FROM dependency_impact_runs WHERE project_id=? AND run_id=?",
            (self.revisions.project, record.impact_run_id),
        ).fetchone()
        if run is None or tuple(run) != (
            base.revision_id,
            record.final_revision_id,
            _projection_content_sha256(old),
            _projection_content_sha256(final),
            record.accepted_by,
            record.accepted_at,
            "document-reprocessing-impact-" + record.command.command_id,
        ):
            raise DocumentRevisionProblem("document-reprocessing-impact-invalid")

    def _stage(self, value, media, source, cancelled):
        self._check(cancelled)
        return self.revisions._put(protected_json(value), media, source, lambda _connection, stored: stored, cancelled)

    def _insert_accepted(self, connection, accepted, stored):
        connection.execute(
            "INSERT INTO document_normalized_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                accepted.revision_id,
                self.revisions.project,
                accepted.document_id,
                accepted.previous_revision_id,
                accepted.result.result_id,
                accepted.decision_id,
                accepted.decision_revision_id,
                accepted.command_id,
                accepted.command_sha256,
                stored.object_sha256,
                accepted.content_sha256,
                accepted.structure_sha256,
                accepted.accepted_by,
                accepted.accepted_at,
            ),
        )
        self.revisions._elements(connection, accepted)

    def _append_accepted(
        self, connection, aggregates, accepted, stored, current, inputs, historical, actor, *, correction
    ):
        decision = aggregates.append(
            AggregateRevisionDraft(
                revision_id=accepted.decision_revision_id,
                aggregate_id=accepted.decision_id,
                aggregate_kind="decision",
                created_at=accepted.accepted_at,
                modified_at=accepted.accepted_at,
                display_label_observed="Accept document correction" if correction else "Accept document reparse",
                display_label_normalized=None,
                knowledge_status="observed",
                rights_status="allowed",
                dependency_coverage="complete",
                provenance_inputs=inputs,
                material_dependencies=self.corrections._dependencies(inputs, historical),
            ),
            self.revisions._event(
                actor,
                accepted.accepted_at,
                "decision.created",
                ("document-correction-decision-" if correction else "document-reprocessing-decision-")
                + accepted.command_id,
            ),
            expected_revision=None,
        )
        _publication_step("reprocessing-decision-complete")
        all_inputs = (*inputs, decision)
        successor = aggregates.append(
            AggregateRevisionDraft(
                revision_id=accepted.revision_id,
                aggregate_id=accepted.document_id,
                aggregate_kind="document",
                created_at=current.created_at,
                modified_at=accepted.accepted_at,
                display_label_observed=current.display_label_observed,
                display_label_normalized=current.display_label_normalized,
                knowledge_status="extracted",
                rights_status="allowed",
                object_sha256=stored.object_sha256,
                dependency_coverage="complete",
                provenance_inputs=all_inputs,
                material_dependencies=self.corrections._dependencies(all_inputs, historical),
            ),
            self.revisions._event(
                actor,
                accepted.accepted_at,
                "document.updated",
                ("document-correction-accept-" if correction else "document-reprocessing-machine-")
                + accepted.command_id,
            ),
            expected_revision=current.revision,
        )
        self._insert_accepted(connection, accepted, stored)
        _publication_step("reprocessing-accepted-complete")
        return successor

    def _begin_impact(self, connection, previous, successor, actor, key, *, run_id):
        change = self._change(
            previous,
            successor.revision_id,
            actor,
            key=key,
            replacement_fingerprint=_projection_content_sha256(successor),
        )
        preview = self.impacts._preview_with_connection(
            connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
        )
        run = self.impacts._begin_with_connection(
            connection, change, preview_sha256=preview.preview_sha256, run_id=run_id, batch_size=100
        )
        # The new acceptance itself is never on a material path from history.
        if run.state == "running" and run.total_items <= 100:
            run = self.impacts._advance_with_connection(
                connection, run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256
            )
        _publication_step("reprocessing-impact-complete")
        return run

    def _accepted_view(self, connection, record):
        run = self.impacts._run_with_connection(connection, record.impact_run_id)
        return reprocessing.ReprocessingAcceptedView(
            project_id=self.revisions.project,
            batch_id=record.batch_id,
            batch_revision_id=record.batch_revision_id,
            item_id=record.item_id,
            previous_revision_id=record.base_revision_id,
            revision_id=record.final_revision_id,
            machine_revision_id=record.machine_revision_id,
            impact_run_id=run.run_id,
            impact_state=run.state,
            impact_checkpoint_sha256=run.checkpoint_sha256.removeprefix("sha256:"),
            processed_items=run.processed_items,
            total_items=run.total_items,
        )

    def accept(self, command, *, cancelled=lambda: False):
        command = reprocessing.ReprocessingAcceptance.model_validate(command)

        def prepare(connection, actor, plan):
            comparison = self._record(connection, plan.comparison_revision_id, reprocessing.ReprocessingComparison)
            batch, item, base, drafts, candidate, _inherited, results = self._plan_values(
                connection, comparison, plan, cancelled=cancelled
            )
            replay = self._accepted_item(connection, batch, item)
            if replay:
                if replay.command_sha256 != self._semantic(command, actor) or replay.command != command:
                    raise DocumentRevisionProblem("document-reprocessing-command-conflict")
                self.revisions._accepted(connection, replay.final_revision_id)
                return replay
            self._current_batch(connection, batch)
            latest = self._latest_plan(connection, comparison.revision_id)
            if latest is None or latest.revision_id != plan.revision_id or len(plan.steps) != len(drafts):
                raise DocumentRevisionProblem("document-reprocessing-incomplete-reconciliation")
            if command.expected_current_revision_id != base.revision_id or command.confirmation_sha256 != value_sha256(
                plan
            ):
                raise DocumentRevisionProblem("document-reprocessing-confirmation-mismatch")
            if (plan.intent_revision_id, plan.intent_sha256, plan.policy_sha256) != (
                actor.intent_revision_id,
                actor.intent_sha256,
                actor.policy_sha256,
            ):
                raise DocumentRevisionProblem("document-reprocessing-authority-changed")
            with self.revisions._aggregates(connection) as aggregates:
                predecessor = aggregates.get(base.document_id)
                if predecessor.revision_id != base.revision_id:
                    raise DocumentRevisionProblem("document-reprocessing-base-changed")
            preview = self._prospective(connection, base, candidate, actor)
            if preview.graph_sha256 != "sha256:" + command.expected_graph_sha256:
                raise DocumentRevisionProblem("document-reprocessing-graph-changed")
            targets = tuple(self.corrections._targets(connection, result, fresh=True) for result in results)
            common = dict(
                project_id=self.revisions.project,
                document_id=base.document_id,
                result=comparison.result,
                accepted_by=actor.actor_id,
                accepted_at=actor.occurred_at,
                intent_revision_id=actor.intent_revision_id,
                intent_sha256=actor.intent_sha256,
                policy_sha256=actor.policy_sha256,
            )
            ordinary = DocumentRevisionAcceptance(
                command_id=new_uuid_v7(),
                result_id=comparison.result.result_id,
                expected_current_revision_id=base.revision_id,
                confirmation_sha256=hashlib.sha256(
                    comparison.result.model_dump_json(by_alias=True).encode()
                ).hexdigest(),
                decision="accept-structure",
            )
            semantic = hashlib.sha256(
                protected_json(ordinary) + protected_json(comparison.result) + actor.actor_id.encode()
            ).hexdigest()
            machine = AcceptedDocumentRevision(
                **common,
                revision_id=comparison.candidate.revision_id,
                previous_revision_id=base.revision_id,
                decision_id=new_uuid_v7(),
                decision_revision_id=new_uuid_v7(),
                command_id=ordinary.command_id,
                command_sha256=semantic,
                content_sha256=content_sha256(comparison.candidate.structure),
                structure_sha256=comparison.candidate.structure_sha256,
                element_identities=comparison.candidate.element_identities,
                structure=comparison.candidate.structure,
            )
            nested = []
            prior = machine
            for step, result in zip(plan.steps, results, strict=True):
                save = CorrectionSave(
                    command_id=new_uuid_v7(),
                    draft_id=None,
                    expected_draft_revision_id=None,
                    patch=step.mapped_patch,
                    rationale=plan.command.rationale,
                )
                draft = CorrectionDraft(
                    project_id=self.revisions.project,
                    draft_id=new_uuid_v7(),
                    revision_id=new_uuid_v7(),
                    previous_draft_revision_id=None,
                    source=comparison.result.binding.source,
                    patch=step.mapped_patch,
                    rationale=save.rationale,
                    authored_by=actor.actor_id,
                    authored_at=actor.occurred_at,
                    intent_revision_id=actor.intent_revision_id,
                    intent_sha256=actor.intent_sha256,
                    policy_sha256=actor.policy_sha256,
                    command_id=save.command_id,
                    command_sha256=self._semantic(save, actor),
                    preview_sha256=result.result_sha256,
                )
                accept = CorrectionAcceptance(
                    command_id=new_uuid_v7(),
                    draft_revision_id=draft.revision_id,
                    expected_current_revision_id=prior.revision_id,
                    confirmation_sha256=value_sha256(draft),
                    decision="accept-correction",
                )
                corrected = AcceptedDocumentRevision(
                    **common,
                    revision_id=step.next_candidate.revision_id,
                    previous_revision_id=prior.revision_id,
                    decision_id=new_uuid_v7(),
                    decision_revision_id=new_uuid_v7(),
                    command_id=accept.command_id,
                    command_sha256=hashlib.sha256(
                        protected_json(accept) + protected_json(draft) + actor.actor_id.encode()
                    ).hexdigest(),
                    content_sha256=content_sha256(step.next_candidate.structure),
                    structure_sha256=step.next_candidate.structure_sha256,
                    element_identities=step.next_candidate.element_identities,
                    structure=step.next_candidate.structure,
                )
                nested.append((draft, corrected, result))
                prior = corrected
            outer = reprocessing.ReprocessingAccepted(
                project_id=self.revisions.project,
                record_id=new_uuid_v7(),
                revision_id=new_uuid_v7(),
                command=command,
                command_sha256=self._semantic(command, actor),
                batch_id=batch.batch_id,
                batch_revision_id=batch.revision_id,
                item_id=item.item_id,
                comparison_revision_id=comparison.revision_id,
                plan_revision_id=plan.revision_id,
                base_revision_id=base.revision_id,
                machine_revision_id=machine.revision_id,
                final_revision_id=prior.revision_id,
                machine_command_id=machine.command_id,
                machine_decision_id=machine.decision_id,
                machine_decision_revision_id=machine.decision_revision_id,
                machine_command_sha256=machine.command_sha256,
                nested_draft_revision_ids=tuple(d.revision_id for d, c, r in nested),
                final_command_ids=tuple(c.command_id for d, c, r in nested),
                impact_run_id=new_uuid_v7(),
                accepted_by=actor.actor_id,
                accepted_at=actor.occurred_at,
                intent_revision_id=actor.intent_revision_id,
                intent_sha256=actor.intent_sha256,
                policy_sha256=actor.policy_sha256,
            )
            return outer, comparison, plan, batch, item, base, predecessor, machine, tuple(nested), targets, actor

        prepared = self._run(command.plan_revision_id, prepare, cancelled)
        if isinstance(prepared, reprocessing.ReprocessingAccepted):
            return self._run(prepared.revision_id, lambda c, a, r: self._accepted_view(c, r), cancelled)
        outer, comparison, plan, batch, item, base, predecessor, machine, nested, targets, owner = prepared
        source = comparison.result.binding.source
        machine_object = self._stage(machine, ACCEPTED_REVISION_MEDIA_TYPE, source, cancelled)
        nested_objects = tuple(
            (
                self._stage(d, CORRECTION_MEDIA_TYPE, source, cancelled),
                self._stage(c, ACCEPTED_REVISION_MEDIA_TYPE, source, cancelled),
            )
            for d, c, r in nested
        )

        def publish(connection, stored):
            self._check(cancelled)
            actor = self.revisions.actor()
            self.revisions._authority(connection, actor)
            if actor != owner:
                raise DocumentRevisionProblem("document-reprocessing-authority-changed")
            replay = self._accepted_item(connection, batch, item)
            if replay:
                if replay.command != command or replay.command_sha256 != outer.command_sha256:
                    raise DocumentRevisionProblem("document-reprocessing-command-conflict")
                self.revisions._accepted(connection, replay.final_revision_id)
                return self._accepted_view(connection, replay)
            values = self._plan_values(connection, comparison, plan, cancelled=cancelled)
            self._current_batch(connection, batch)
            latest = self._latest_plan(connection, comparison.revision_id)
            if latest is None or latest.revision_id != plan.revision_id:
                raise DocumentRevisionProblem("document-reprocessing-plan-changed")
            if tuple(self.corrections._targets(connection, r, fresh=True) for r in values[-1]) != targets:
                raise DocumentRevisionProblem("document-reprocessing-reference-authority-changed")
            if (
                self._prospective(connection, base, values[4], actor).graph_sha256
                != "sha256:" + command.expected_graph_sha256
            ):
                raise DocumentRevisionProblem("document-reprocessing-graph-changed")
            with self.revisions._aggregates(connection) as aggregates:
                if aggregates.get(base.document_id) != predecessor:
                    raise DocumentRevisionProblem("document-reprocessing-base-changed")
                retained = aggregates.get_revision(comparison.result.revision_id)
                historical_inputs = tuple(
                    aggregates.get_revision(i) for i in (base.revision_id, comparison.revision_id, plan.revision_id)
                )
                outer_inputs = (*historical_inputs, retained)
                outer_revision = aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=outer.revision_id,
                        aggregate_id=outer.record_id,
                        aggregate_kind="document",
                        created_at=outer.accepted_at,
                        modified_at=outer.accepted_at,
                        display_label_observed=outer.document_type,
                        display_label_normalized=None,
                        knowledge_status="observed",
                        rights_status="allowed",
                        object_sha256=stored.object_sha256,
                        dependency_coverage="complete",
                        provenance_inputs=outer_inputs,
                        material_dependencies=self.corrections._dependencies(
                            outer_inputs, {i.revision_id for i in historical_inputs}
                        ),
                    ),
                    self.revisions._event(actor, outer.accepted_at, "document.created", self._key(outer)),
                    expected_revision=None,
                )
                _publication_step("reprocessing-outer-complete")
                current = self._append_accepted(
                    connection,
                    aggregates,
                    machine,
                    machine_object,
                    predecessor,
                    (predecessor, retained, outer_revision),
                    {predecessor.revision_id},
                    actor,
                    correction=False,
                )
                for (draft, corrected, _result), (draft_object, corrected_object), target in zip(
                    nested, nested_objects, targets, strict=True
                ):
                    draft_inputs = (current, retained, *target)
                    draft_revision = aggregates.append(
                        AggregateRevisionDraft(
                            revision_id=draft.revision_id,
                            aggregate_id=draft.draft_id,
                            aggregate_kind="document",
                            created_at=draft.authored_at,
                            modified_at=draft.authored_at,
                            display_label_observed="Document correction draft",
                            display_label_normalized=None,
                            knowledge_status="observed",
                            rights_status="allowed",
                            object_sha256=draft_object.object_sha256,
                            dependency_coverage="complete",
                            provenance_inputs=draft_inputs,
                            material_dependencies=self.corrections._dependencies(draft_inputs, {current.revision_id}),
                        ),
                        self.revisions._event(
                            actor, draft.authored_at, "document.created", "document-correction-save-" + draft.command_id
                        ),
                        expected_revision=None,
                    )
                    _publication_step("reprocessing-draft-complete")
                    previous = current
                    current = self._append_accepted(
                        connection,
                        aggregates,
                        corrected,
                        corrected_object,
                        current,
                        (current, retained, draft_revision, *target),
                        {current.revision_id},
                        actor,
                        correction=True,
                    )
                    self._begin_impact(
                        connection,
                        previous,
                        current,
                        actor,
                        "document-correction-impact-" + corrected.command_id,
                        run_id=new_uuid_v7(),
                    )
                self._begin_impact(
                    connection,
                    predecessor,
                    current,
                    actor,
                    "document-reprocessing-impact-" + command.command_id,
                    run_id=outer.impact_run_id,
                )
            self._check(cancelled)
            # Normal immutable readers verify both outer and literal correction
            # contracts before the sole writer can commit.
            self.revisions._accepted(connection, outer.final_revision_id)
            return self._accepted_view(connection, outer)

        return self.revisions._bounded(lambda: self._publish_outcome(protected_json(outer), source, publish, cancelled))

    def _cancel_jobs(self, batch, cancelled):
        actor = self.revisions.actor()
        for item in batch.items:
            self._check(cancelled)

            def cancel(connection, _actor, item=item):
                job = self._job(connection, item)
                return None if job is None or job.state in {"succeeded", "failed", "cancelled", "interrupted"} else job

            job = self.revisions._source_fenced(item.inputs.source, cancel)
            if job is not None:
                self.revisions.queue.request_cancellation(
                    job.job_id,
                    actor=WorkflowActor(actor.actor_id, "human", "researcher"),
                    now=self.revisions.now(),
                    reason_code="document-reprocessing-cancelled",
                    interruption_kind="user-cancel",
                )

    def cancel(self, command, *, cancelled=lambda: False):
        command = reprocessing.ReprocessingCancel.model_validate(command)

        def prepare(connection, actor, batch):
            key = "document-reprocessing-document-reprocessing-batch-" + command.command_id
            replay = self._replay(connection, key)
            if replay:
                if replay.command_sha256 != self._semantic(command, actor):
                    raise DocumentRevisionProblem("document-reprocessing-command-conflict")
                return replay
            self._current_batch(connection, batch)
            for item in batch.items:
                self._fence(connection, item.inputs.source, actor)
            return reprocessing.ReprocessingBatch(
                project_id=self.revisions.project,
                batch_id=batch.batch_id,
                revision_id=new_uuid_v7(),
                previous_revision_id=batch.revision_id,
                command=command,
                command_id=command.command_id,
                command_sha256=self._semantic(command, actor),
                authored_by=actor.actor_id,
                authored_at=actor.occurred_at,
                intent_revision_id=actor.intent_revision_id,
                intent_sha256=actor.intent_sha256,
                policy_sha256=actor.policy_sha256,
                state="cancelled",
                items=batch.items,
            )

        batch = self._run(command.batch_revision_id, prepare, cancelled)

        def check(connection, actor):
            prior = self._record(connection, batch.previous_revision_id, reprocessing.ReprocessingBatch)
            self._current_batch(connection, prior)
            for item in prior.items:
                self._fence(connection, item.inputs.source, actor)

        batch = self._write(
            batch,
            batch.items[0].inputs.source,
            (),
            previous=batch.previous_revision_id,
            check=check,
            cancelled=cancelled,
        )
        with self._after_publication():
            self._cancel_jobs(batch, cancelled)
            return self._current_batch_view(batch, cancelled)

    def continue_item(self, command, *, input_factory, cancelled=lambda: False):
        command = reprocessing.ReprocessingContinue.model_validate(command)

        def prepare(connection, actor, batch):
            key = "document-reprocessing-document-reprocessing-batch-" + command.command_id
            replay = self._replay(connection, key)
            if replay:
                if replay.command_sha256 != self._semantic(command, actor):
                    raise DocumentRevisionProblem("document-reprocessing-command-conflict")
                return replay
            self._current_batch(connection, batch)
            item = self._item(batch, command.item_id)
            self._fence(connection, item.inputs.source, actor)
            job = self._job(connection, item)
            if (
                (None if job is None else job.job_id) != command.expected_job_id
                or (job is not None and job.state == "succeeded")
                or self._accepted_item(connection, batch, item)
            ):
                raise DocumentRevisionProblem("document-reprocessing-continuation-conflict")
            base = self.revisions._accepted(connection, item.base_revision_id)
            with self.revisions._aggregates(connection) as aggregates:
                if aggregates.get(base.document_id).revision_id != base.revision_id:
                    raise DocumentRevisionProblem("document-reprocessing-base-changed")
            inputs = input_factory(base)
            if (
                inputs.source != item.inputs.source
                or inputs.command_id == item.inputs.command_id
                or inputs.actor_id != actor.actor_id
            ):
                raise DocumentRevisionProblem("document-reprocessing-continuation-invalid")
            items = tuple(
                i.model_copy(update={"inputs": inputs}) if i.item_id == item.item_id else i for i in batch.items
            )
            return reprocessing.ReprocessingBatch(
                project_id=self.revisions.project,
                batch_id=batch.batch_id,
                revision_id=new_uuid_v7(),
                previous_revision_id=batch.revision_id,
                command=command,
                command_id=command.command_id,
                command_sha256=self._semantic(command, actor),
                authored_by=actor.actor_id,
                authored_at=actor.occurred_at,
                intent_revision_id=actor.intent_revision_id,
                intent_sha256=actor.intent_sha256,
                policy_sha256=actor.policy_sha256,
                state="active",
                items=items,
            )

        batch = self._run(command.batch_revision_id, prepare, cancelled)

        def check(connection, actor):
            prior = self._record(connection, batch.previous_revision_id, reprocessing.ReprocessingBatch)
            self._current_batch(connection, prior)
            item = self._item(prior, command.item_id)
            self._fence(connection, item.inputs.source, actor)
            job = self._job(connection, item)
            if (None if job is None else job.job_id) != command.expected_job_id or self._accepted_item(
                connection, prior, item
            ):
                raise DocumentRevisionProblem("document-reprocessing-continuation-conflict")
            with self.revisions._aggregates(connection) as aggregates:
                if aggregates.get(item.inputs.source.document_id).revision_id != item.base_revision_id:
                    raise DocumentRevisionProblem("document-reprocessing-base-changed")

        batch = self._write(
            batch,
            batch.items[0].inputs.source,
            (),
            previous=batch.previous_revision_id,
            check=check,
            cancelled=cancelled,
        )
        with self._after_publication():
            current = self._current_batch_view(batch, cancelled)
            if current.batch_revision_id != batch.revision_id or current.state != "active":
                return current
            item = self._item(batch, command.item_id)
            # The previous immutable job remains inspectable; it cannot be
            # rebound to a different Native session or parser selection.
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as connection:
                prior = self._record(connection, batch.previous_revision_id, reprocessing.ReprocessingBatch)
            self._cancel_jobs(prior.model_copy(update={"items": (self._item(prior, command.item_id),)}), cancelled)
            return self._submit_current_items(batch, (item,), cancelled)

    def read_impact(self, batch_revision_id, item_id, *, cancelled=lambda: False):
        def read(connection, actor, batch):
            item = self._item(batch, item_id)
            self._fence(connection, item.inputs.source, actor)
            record = self._accepted_item(connection, batch, item)
            if record is None:
                raise DocumentRevisionProblem("document-reprocessing-acceptance-unavailable")
            self.revisions._accepted(connection, record.final_revision_id)
            return self._accepted_view(connection, record)

        return self._run(batch_revision_id, read, cancelled)

    def resume_impact(self, batch_revision_id, item_id, expected_checkpoint_sha256, *, cancelled=lambda: False):
        def resume(connection, actor, batch):
            item = self._item(batch, item_id)
            self._fence(connection, item.inputs.source, actor)
            record = self._accepted_item(connection, batch, item)
            if record is None:
                raise DocumentRevisionProblem("document-reprocessing-acceptance-unavailable")
            self.revisions._accepted(connection, record.final_revision_id)
            run = self.impacts._run_with_connection(connection, record.impact_run_id)
            expected = "sha256:" + expected_checkpoint_sha256
            if expected != run.checkpoint_sha256:
                self.impacts._verify_run_snapshot(connection, run.run_id)
                observed = connection.execute(
                    "SELECT 1 FROM dependency_impact_audit_events WHERE project_id=? AND run_id=? "
                    "AND checkpoint_sha256=? AND processed_items<? LIMIT 1",
                    (self.revisions.project, run.run_id, expected, run.processed_items),
                ).fetchone()
                if observed is None:
                    raise DocumentRevisionProblem("document-reprocessing-impact-checkpoint-changed")
                # An authenticated prior checkpoint already advanced. Return
                # the current readback without consuming a second chunk.
                return self._accepted_view(connection, record)
            if run.state == "running":
                self.impacts._advance_with_connection(connection, run.run_id, expected_checkpoint_sha256=expected)
            self._check(cancelled)
            return self._accepted_view(connection, record)

        return self._run(batch_revision_id, resume, cancelled, mutation=True)
