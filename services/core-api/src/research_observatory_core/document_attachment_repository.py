"""Inspected local-copy candidate and exact WorkVersion attachment.

The encrypted object stage and LPAC inspection run without a canonical writer.
Only a current researcher rights policy can turn the resulting inert candidate
into a document aggregate. Every source, Work, Version, policy, provenance and
outbox fact is rechecked and published in one canonical transaction.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import re
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, BinaryIO, Literal

from pydantic import Field, ValidationError

from .acquisition.intake import DocumentIntakeInput, build_document_intake
from .acquisition.locations import retained_locations
from .connectors.contracts import ConnectorRecord
from .corpus_repository import SqliteCorpusRepository
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from .ingestion.preview_workflow import PreviewIntentContext
from .ports.acquisition import (
    AccessNeedChannel,
    AccessNeedKind,
    AccessNeedSelection,
    AcquisitionLocation,
    AcquisitionProblem,
    AcquisitionReceipt,
    AcquisitionSelection,
    AcquisitionStage,
    DocumentAccessNeed,
)
from .ports.corpus import CorpusActor
from .ports.document_attachments import (
    MAX_DOCUMENT_BYTES,
    AttachmentCandidate,
    AttachmentProblem,
    AttachmentStatusState,
    DocumentAttachment,
    DocumentAttachmentStatus,
    DocumentInspection,
    DocumentInspectionProblem,
    DocumentPublicationGuard,
)
from .ports.object_store import ObjectPutCommand, ObjectStagingCancelled, ObjectStagingCleanupRequired, ObjectStore
from .ports.repositories import AggregateRevision, AggregateRevisionDraft, AtomicRepositoryEvent, MaterialDependency
from .ports.rights import RightsPermissionDraft
from .ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference, WorkflowQueueConflict
from .reconciliation.contracts import SourceAssertion
from .repositories import _projection_content_sha256, _SqliteAggregateRepository, _SqliteWorkflowQueueRepository
from .rights_policy import (
    RightsAction,
    RightsDecision,
    RightsPolicyRevision,
    RightsRequest,
    RightsSubject,
    RightsUse,
    evaluate_rights,
)
from .rights_repository import RightsProblem, SqliteRightsRepository, _digest
from .storage import CanonicalConnection

_FORMATS = frozenset({"pdf", "jats", "tei", "xml", "html", "docx", "plain-text"})
_SESSION = re.compile(r"[0-9a-f]{32}\Z")


class _Denied(Exception):
    def __init__(self, decision: RightsDecision) -> None:
        self.decision = decision


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _inspect_signed_worker(
    source: BinaryIO, *, filename: str, declared_media_type: str | None, cancel: Callable[[], bool] | None
) -> DocumentInspection:
    # This import is intentionally at the platform adapter edge. The service
    # contract itself carries no Windows path, worker handle or process token.
    from workers.document.inspection import DocumentInspectionError
    from workers.windows.document_launcher import inspect_document

    try:
        return inspect_document(source, filename=filename, declared_media_type=declared_media_type, cancel=cancel)
    except DocumentInspectionError as error:
        raise DocumentInspectionProblem(error.code) from None


class LocalDocumentAttachmentService:
    def __init__(
        self,
        database: Path,
        project_id: str,
        objects: ObjectStore,
        *,
        inspector: Callable[..., DocumentInspection] = _inspect_signed_worker,
    ) -> None:
        if not database.is_absolute() or not project_id or not callable(inspector):
            raise AttachmentProblem("attachment-configuration-invalid")
        self._database = database
        self._project = project_id
        self._objects = objects
        self._inspector = inspector
        self._corpus = SqliteCorpusRepository(database, project_id)
        self._queue = _SqliteWorkflowQueueRepository(database, project_id)
        from .connector_repository import ConnectorRepository

        self._rights = SqliteRightsRepository(
            database,
            project_id,
            connector_record_resolver=ConnectorRepository(database, project_id, objects).source_record,
        )

    def ensure_intake_ready(self) -> None:
        self._objects.ensure_intake_ready()

    def _authority(self, connection: CanonicalConnection, actor: CorpusActor) -> None:
        try:
            SqliteRightsRepository._actor(actor)
            self._corpus._authority(connection, actor)
        except RightsProblem, RuntimeError:
            raise AttachmentProblem("attachment-authority-changed") from None

    def _current_binding(
        self,
        connection: CanonicalConnection,
        *,
        source_assertion_revision_id: str,
        work_id: str,
        work_revision_id: str,
        version_id: str,
        version_revision_id: str,
    ) -> SourceAssertion:
        values = (source_assertion_revision_id, work_id, work_revision_id, version_id, version_revision_id)
        if any(not is_uuid_v7(value) for value in values):
            raise AttachmentProblem("attachment-selection-invalid")
        row = connection.execute(
            "SELECT a.assertion_json FROM reconciliation_assertions a "
            "JOIN reconciliation_work_members wm ON wm.project_id=a.project_id "
            "AND wm.assertion_revision_id=a.revision_id "
            "JOIN reconciliation_work_states w ON w.project_id=wm.project_id "
            "AND w.revision_id=wm.work_revision_id "
            "JOIN reconciliation_version_sources vs ON vs.project_id=a.project_id "
            "AND vs.assertion_revision_id=a.revision_id "
            "JOIN reconciliation_versions v ON v.project_id=vs.project_id "
            "AND v.revision_id=vs.version_revision_id "
            "WHERE a.project_id=? AND a.revision_id=? AND w.work_id=? AND w.revision_id=? "
            "AND w.disposition='active' AND v.version_id=? AND v.revision_id=? "
            "AND w.revision_id=(SELECT ar.revision_id FROM aggregate_revisions ar "
            "WHERE ar.project_id=w.project_id AND ar.aggregate_id=w.work_id ORDER BY ar.revision DESC LIMIT 1) "
            "AND v.revision_id=(SELECT ar.revision_id FROM aggregate_revisions ar "
            "WHERE ar.project_id=v.project_id AND ar.aggregate_id=v.version_id ORDER BY ar.revision DESC LIMIT 1) "
            "AND NOT EXISTS (SELECT 1 FROM reconciliation_version_sources other_source "
            "WHERE other_source.project_id=v.project_id AND other_source.version_revision_id=v.revision_id "
            "AND NOT EXISTS (SELECT 1 FROM reconciliation_work_members owned "
            "WHERE owned.project_id=w.project_id AND owned.work_revision_id=w.revision_id "
            "AND owned.assertion_revision_id=other_source.assertion_revision_id))",
            (self._project, source_assertion_revision_id, work_id, work_revision_id, version_id, version_revision_id),
        ).fetchone()
        if row is None:
            raise AttachmentProblem("attachment-association-stale")
        try:
            source = SourceAssertion.model_validate_json(str(row[0]))
        except ValidationError:
            raise AttachmentProblem("attachment-source-integrity-invalid") from None
        if source.project_id != self._project:
            raise AttachmentProblem("attachment-source-integrity-invalid")
        return source

    def _subject(self, source: SourceAssertion, candidate_id: str, source_revision_id: str) -> RightsSubject:
        return RightsSubject(
            project_id=self._project,
            source_assertion_revision_id=source_revision_id,
            address=source.address,
            copy_id=candidate_id,
            copy_location="local-project-object",
            resource_class="full-text",
        )

    def _candidate(self, connection: CanonicalConnection, candidate_id: str) -> AttachmentCandidate:
        row = connection.execute(
            "SELECT source_assertion_revision_id,work_id,work_revision_id,version_id,version_revision_id,"
            "object_sha256,byte_length,format_name,media_type,source_name,confirmation_required,candidate_sha256 "
            "FROM document_attachment_candidates WHERE project_id=? AND candidate_id=?",
            (self._project, candidate_id),
        ).fetchone()
        if row is None:
            raise AttachmentProblem("attachment-candidate-unavailable")
        source_row = connection.execute(
            "SELECT assertion_json FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
            (self._project, row[0]),
        ).fetchone()
        if source_row is None:
            raise AttachmentProblem("attachment-source-integrity-invalid")
        try:
            source = SourceAssertion.model_validate_json(str(source_row[0]))
        except ValidationError:
            raise AttachmentProblem("attachment-source-integrity-invalid") from None
        return AttachmentCandidate(
            candidate_id=candidate_id,
            project_id=self._project,
            source_assertion_revision_id=str(row[0]),
            work_id=str(row[1]),
            work_revision_id=str(row[2]),
            version_id=str(row[3]),
            version_revision_id=str(row[4]),
            object_sha256=str(row[5]),
            byte_length=int(row[6]),
            format=str(row[7]),
            media_type=str(row[8]),
            source_name=str(row[9]),
            confirmation_required=bool(row[10]),
            candidate_sha256=str(row[11]),
            rights_subject=self._subject(source, candidate_id, str(row[0])),
        )

    def stage(
        self,
        source: BinaryIO,
        *,
        source_name: str,
        declared_media_type: str | None,
        source_assertion_revision_id: str,
        work_id: str,
        work_revision_id: str,
        version_id: str,
        version_revision_id: str,
        actor: CorpusActor,
        operation_id: str | None = None,
        session_id: str | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
        publication_guard: DocumentPublicationGuard | None = None,
        acquisition: AcquisitionStage | None = None,
    ) -> AttachmentCandidate:
        if (operation_id is None) != (session_id is None) or (
            operation_id is not None and (not is_uuid_v7(operation_id) or _SESSION.fullmatch(session_id or "") is None)
        ):
            raise AttachmentProblem("attachment-operation-invalid")
        name = ntpath.basename(source_name)
        if not name or len(name) > 255 or "\x00" in name or name in {".", ".."}:
            raise AttachmentProblem("attachment-source-name-invalid")
        if declared_media_type is not None and (
            not isinstance(declared_media_type, str) or len(declared_media_type) > 200
        ):
            raise AttachmentProblem("attachment-media-type-invalid")
        selection = dict(
            zip(
                ("sourceAssertionRevisionId", "workId", "workRevisionId", "versionId", "versionRevisionId"),
                (source_assertion_revision_id, work_id, work_revision_id, version_id, version_revision_id),
                strict=True,
            )
        )
        claim = acquisition.intake_claim if acquisition is not None else None
        if acquisition is None and operation_id is not None:
            self.ensure_intake_ready()

            def admit() -> WorkflowJobClaim:

                with self._corpus._transaction(write=True) as (connection, aggregates):
                    self._authority(connection, actor)
                    self._current_binding(
                        connection,
                        source_assertion_revision_id=source_assertion_revision_id,
                        work_id=work_id,
                        work_revision_id=work_revision_id,
                        version_id=version_id,
                        version_revision_id=version_revision_id,
                    )
                    assert operation_id is not None and session_id is not None
                    return admit_intake(
                        connection,
                        aggregates,
                        self._queue,
                        project=self._project,
                        operation_id=operation_id,
                        session_id=session_id,
                        kind="local-import",
                        selection=selection,
                        confirmation_sha256=_sha({"operationId": operation_id, "selection": selection}),
                        actor=actor,
                    )

            claim = publication_guard(admit) if publication_guard is not None else admit()
        user_cancelled = cancellation_requested

        def cancelled() -> bool:
            return bool(user_cancelled and user_cancelled()) or bool(
                claim is not None and self._queue.cancellation_requested(claim, now=_now())
            )

        try:
            return self._stage_inspected(
                source,
                source_name=source_name,
                declared_media_type=declared_media_type,
                source_assertion_revision_id=source_assertion_revision_id,
                work_id=work_id,
                work_revision_id=work_revision_id,
                version_id=version_id,
                version_revision_id=version_revision_id,
                actor=actor,
                operation_id=operation_id,
                session_id=session_id,
                cancellation_requested=cancelled,
                publication_guard=publication_guard,
                acquisition=acquisition,
                intake_claim=claim,
                publication_cancelled=user_cancelled,
            )
        except BaseException as error:
            if acquisition is None and claim is not None:
                was_cancelled = isinstance(error, ObjectStagingCancelled) or (
                    isinstance(error, DocumentInspectionProblem) and error.code == "cancelled"
                )
                code = (
                    "acquisition-cleanup-required"
                    if isinstance(error, ObjectStagingCleanupRequired)
                    else ("intake-cancelled" if was_cancelled else "intake-failed")
                )

                def fail() -> None:

                    with self._corpus._transaction(write=True) as (connection, aggregates):
                        self._authority(connection, actor)
                        assert operation_id is not None
                        finish_intake(
                            connection,
                            aggregates,
                            self._queue,
                            claim,
                            project=self._project,
                            operation_id=operation_id,
                            actor=actor,
                            outcome="cancelled" if was_cancelled else "failed",
                            code=code,
                        )

                # A revoked native session may not publish protected state.
                # Its expired queue lease remains honest restart evidence.
                with suppress(Exception):
                    publication_guard(fail) if publication_guard is not None else fail()
            raise

    def _stage_inspected(
        self,
        source: BinaryIO,
        *,
        source_name: str,
        declared_media_type: str | None,
        source_assertion_revision_id: str,
        work_id: str,
        work_revision_id: str,
        version_id: str,
        version_revision_id: str,
        actor: CorpusActor,
        operation_id: str | None = None,
        session_id: str | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
        publication_guard: DocumentPublicationGuard | None = None,
        acquisition: AcquisitionStage | None = None,
        intake_claim: WorkflowJobClaim | None = None,
        publication_cancelled: Callable[[], bool] | None = None,
    ) -> AttachmentCandidate:
        name = ntpath.basename(source_name)
        if not name or len(name) > 255 or "\x00" in name or name in {".", ".."}:
            raise AttachmentProblem("attachment-source-name-invalid")
        if declared_media_type is not None and (
            not isinstance(declared_media_type, str) or len(declared_media_type) > 200
        ):
            raise AttachmentProblem("attachment-media-type-invalid")
        if (operation_id is None) != (session_id is None) or (
            operation_id is not None and (not is_uuid_v7(operation_id) or _SESSION.fullmatch(session_id or "") is None)
        ):
            raise AttachmentProblem("attachment-operation-invalid")
        with self._corpus._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
            if (
                operation_id is not None
                and connection.execute(
                    "SELECT 1 FROM document_attachment_operations WHERE operation_id=?", (operation_id,)
                ).fetchone()
            ):
                raise AttachmentProblem("attachment-operation-conflict")
            self._current_binding(
                connection,
                source_assertion_revision_id=source_assertion_revision_id,
                work_id=work_id,
                work_revision_id=work_revision_id,
                version_id=version_id,
                version_revision_id=version_revision_id,
            )

        observed: list[DocumentInspection] = []

        def inspect(verified_source: BinaryIO, staged_sha256: str, staged_size: int) -> str:
            if intake_claim is not None:

                def validating() -> None:

                    with self._corpus._transaction(write=True) as (connection, _):
                        self._authority(connection, actor)
                        mark_intake_phase(connection, self._queue, intake_claim, "validating")

                publication_guard(validating) if publication_guard is not None else validating()
            verdict = self._inspector(
                verified_source, filename=name, declared_media_type=declared_media_type, cancel=cancellation_requested
            )
            canonical_format = "plain-text" if verdict.format == "txt" else verdict.format
            if (
                canonical_format not in _FORMATS
                or verdict.size_bytes != staged_size
                or verdict.sha256 != staged_sha256
                or not isinstance(verdict.media_type, str)
            ):
                raise AttachmentProblem("attachment-inspection-identity-mismatch")
            observed.append(verdict)
            return verdict.media_type

        stored = self._objects.put_inspected(
            source,
            ObjectPutCommand(
                media_type="application/octet-stream",
                rights_status="unknown",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="connector-acquisition" if acquisition is not None else "local-import",
                created_at=_now(),
                expected_sha256=acquisition.expected_sha256 if acquisition is not None else None,
            ),
            inspect,
            max_plaintext_bytes=MAX_DOCUMENT_BYTES,
            cancellation_requested=cancellation_requested,
        )
        if len(observed) != 1 or stored.storage_state != "available":
            raise AttachmentProblem("attachment-inspection-missing")
        format_name = "plain-text" if observed[0].format == "txt" else observed[0].format
        candidate_id = new_uuid_v7()
        # Local bytes carry no trustworthy Version identity, even when the
        # selected retained source is a member. Require the exact candidate
        # fingerprint to be confirmed by the researcher before publication.
        fingerprint = _sha(
            {
                "projectId": self._project,
                "candidateId": candidate_id,
                "sourceAssertionRevisionId": source_assertion_revision_id,
                "workId": work_id,
                "workRevisionId": work_revision_id,
                "versionId": version_id,
                "versionRevisionId": version_revision_id,
                "objectSha256": stored.object_sha256,
                "byteLength": stored.byte_length,
                "format": format_name,
                "mediaType": stored.media_type,
            }
        )

        def publish() -> AttachmentCandidate:
            if publication_cancelled is not None and publication_cancelled():
                raise ObjectStagingCancelled()
            with self._corpus._transaction(write=True) as (connection, aggregates):
                if publication_cancelled is not None and publication_cancelled():
                    raise ObjectStagingCancelled()
                self._authority(connection, actor)
                self._current_binding(
                    connection,
                    source_assertion_revision_id=source_assertion_revision_id,
                    work_id=work_id,
                    work_revision_id=work_revision_id,
                    version_id=version_id,
                    version_revision_id=version_revision_id,
                )
                object_row = connection.execute(
                    "SELECT byte_length,media_type,storage_state,protection_profile FROM object_records "
                    "WHERE project_id=? AND object_sha256=?",
                    (self._project, stored.object_sha256),
                ).fetchone()
                if object_row is None or tuple(object_row) != (
                    stored.byte_length,
                    stored.media_type,
                    "available",
                    "project-encrypted-v1",
                ):
                    raise AttachmentProblem("attachment-object-unavailable")
                connection.execute(
                    "INSERT INTO document_attachment_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        candidate_id,
                        self._project,
                        source_assertion_revision_id,
                        work_id,
                        work_revision_id,
                        version_id,
                        version_revision_id,
                        stored.object_sha256,
                        stored.byte_length,
                        format_name,
                        stored.media_type,
                        name,
                        1,
                        fingerprint,
                        actor.actor_id,
                        actor.trace_id,
                        _now(),
                    ),
                )
                if operation_id is not None and session_id is not None:
                    try:
                        connection.execute(
                            "INSERT INTO document_attachment_operations VALUES (?,?,?,?,?,?)",
                            (operation_id, self._project, candidate_id, session_id, actor.actor_id, _now()),
                        )
                    except sqlite3.IntegrityError:
                        raise AttachmentProblem("attachment-operation-conflict") from None
                if acquisition is not None:
                    if operation_id is None:
                        raise AttachmentProblem("attachment-operation-invalid")
                    publish_acquisition_source(
                        connection,
                        aggregates,
                        self._rights,
                        project=self._project,
                        operation_id=operation_id,
                        candidate_id=candidate_id,
                        object_sha256=stored.object_sha256,
                        byte_length=stored.byte_length,
                        receipt=acquisition.receipt(),
                        actor=actor,
                        queue=self._queue,
                        intake_claim=acquisition.intake_claim,
                    )
                elif intake_claim is not None:
                    assert operation_id is not None
                    finish_intake(
                        connection,
                        aggregates,
                        self._queue,
                        intake_claim,
                        project=self._project,
                        operation_id=operation_id,
                        actor=actor,
                        outcome="candidate",
                        code="intake-candidate",
                        candidate_id=candidate_id,
                    )
                return self._candidate(connection, candidate_id)

        return publication_guard(publish) if publication_guard is not None else publish()

    def load_candidate(self, candidate_id: str, *, actor: CorpusActor) -> AttachmentCandidate:
        with self._corpus._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
            if connection.execute(
                "SELECT 1 FROM document_attachment_cancellations WHERE project_id=? AND candidate_id=?",
                (self._project, candidate_id),
            ).fetchone():
                raise AttachmentProblem("attachment-candidate-cancelled")
            return self._candidate(connection, candidate_id)

    def retained_candidates(
        self, selection: AccessNeedSelection, *, actor: CorpusActor
    ) -> tuple[dict[str, object], ...]:
        with self._corpus._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
            self._current_binding(
                connection,
                source_assertion_revision_id=selection.source_assertion_revision_id,
                work_id=selection.work_id,
                work_revision_id=selection.work_revision_id,
                version_id=selection.version_id,
                version_revision_id=selection.version_revision_id,
            )
            rows = connection.execute(
                "SELECT c.candidate_id,c.source_name,o.operation_id,s.location_id "
                "FROM document_attachment_candidates c "
                "JOIN document_attachment_operations o ON o.project_id=c.project_id AND o.candidate_id=c.candidate_id "
                "LEFT JOIN document_acquisition_sources s "
                "ON s.project_id=c.project_id AND s.candidate_id=c.candidate_id "
                "WHERE c.project_id=? AND c.actor_id=? AND c.source_assertion_revision_id=? "
                "AND c.work_id=? AND c.work_revision_id=? AND c.version_id=? AND c.version_revision_id=? "
                "AND NOT EXISTS (SELECT 1 FROM document_attachment_cancellations x "
                "WHERE x.candidate_id=c.candidate_id) "
                "AND NOT EXISTS (SELECT 1 FROM document_attachment_assertions a "
                "WHERE a.candidate_id=c.candidate_id) "
                "ORDER BY c.candidate_id LIMIT 50",
                (self._project, actor.actor_id, *selection.association),
            ).fetchall()
            return tuple(
                {
                    "candidateId": str(row[0]),
                    "sourceName": str(row[1]),
                    "originalOperationId": str(row[2]),
                    "copyId": str(row[3]) if row[3] is not None else None,
                }
                for row in rows
            )

    def recover_candidate(
        self,
        candidate_id: str,
        *,
        original_operation_id: str,
        recovery_operation_id: str,
        session_id: str,
        confirmation_sha256: str,
        exact_selection: tuple[str, str, str, str, str],
        actor: CorpusActor,
        remote_selection: AcquisitionSelection | None = None,
    ) -> AttachmentCandidate:

        if (
            any(not is_uuid_v7(x) for x in (candidate_id, original_operation_id, recovery_operation_id))
            or recovery_operation_id == original_operation_id
            or _SESSION.fullmatch(session_id) is None
        ):
            raise AttachmentProblem("attachment-operation-invalid")

        def reviewed(connection: CanonicalConnection):
            self._authority(connection, actor)
            candidate = self._candidate(connection, candidate_id)
            if exact_selection != (
                candidate.source_assertion_revision_id,
                candidate.work_id,
                candidate.work_revision_id,
                candidate.version_id,
                candidate.version_revision_id,
            ):
                raise AttachmentProblem("attachment-association-stale")
            if confirmation_sha256 != candidate.candidate_sha256:
                raise AttachmentProblem("attachment-confirmation-required")
            self._current_binding(
                connection,
                source_assertion_revision_id=candidate.source_assertion_revision_id,
                work_id=candidate.work_id,
                work_revision_id=candidate.work_revision_id,
                version_id=candidate.version_id,
                version_revision_id=candidate.version_revision_id,
            )
            if connection.execute(
                "SELECT 1 FROM document_attachment_cancellations WHERE project_id=? AND candidate_id=?",
                (self._project, candidate_id),
            ).fetchone():
                raise AttachmentProblem("attachment-candidate-cancelled")
            if connection.execute(
                "SELECT 1 FROM document_attachment_assertions WHERE project_id=? AND candidate_id=?",
                (self._project, candidate_id),
            ).fetchone():
                raise AttachmentProblem("attachment-already-committed")
            basis = current_recovery_basis(
                connection,
                project=self._project,
                candidate=candidate,
                original_operation_id=original_operation_id,
                session_id=session_id,
                actor=actor,
                rights=self._rights,
                remote_selection=remote_selection,
            )
            return candidate, basis

        with self._corpus._transaction(write=False) as (connection, _):
            candidate, basis = reviewed(connection)
        # Recovery reviews the retained inspection and encrypted-store state.
        # Candidate metadata is not an ordinary document-read grant; its copy
        # remains pending until the separate explicit attachment decision.
        stored = self._objects.metadata(candidate.object_sha256)
        if (
            stored.storage_state != "available"
            or stored.protection_profile != "project-encrypted-v1"
            or stored.byte_length != candidate.byte_length
            or stored.media_type != candidate.media_type
        ):
            raise AttachmentProblem("attachment-object-unavailable")
        with self._corpus._transaction(write=True) as (connection, aggregates):
            current, current_basis = reviewed(connection)
            if current != candidate or current_basis != basis:
                raise AttachmentProblem("attachment-recovery-stale")
            raw = basis.model_dump(mode="json", by_alias=True)
            digest = _sha(raw)
            replay = connection.execute(
                "SELECT basis_sha256 FROM document_attachment_recoveries WHERE operation_id=?", (recovery_operation_id,)
            ).fetchone()
            if replay is not None:
                if replay[0] != digest:
                    raise AttachmentProblem("attachment-operation-conflict")
                return candidate
            if connection.execute(
                "SELECT 1 FROM document_attachment_operations WHERE operation_id=?", (recovery_operation_id,)
            ).fetchone():
                raise AttachmentProblem("attachment-operation-conflict")
            identities = tuple(
                dict.fromkeys(
                    (
                        candidate.source_assertion_revision_id,
                        candidate.work_revision_id,
                        candidate.version_revision_id,
                        *(
                            x
                            for x in (
                                basis.current_provider_policy_revision_id,
                                basis.original_provider_policy_revision_id,
                                basis.candidate_policy_revision_id,
                            )
                            if x is not None
                        ),
                    )
                )
            )
            inputs = tuple(aggregates.get_revision(x) for x in identities)
            revision = _append_attempt_revision(
                aggregates,
                recovery_operation_id,
                actor,
                code="intake-candidate-recovered",
                inputs=inputs,
                fingerprints=(("recovery-basis", digest), ("copy-bytes", candidate.object_sha256)),
                previous=None,
            )
            connection.execute(
                "INSERT INTO document_attachment_recoveries VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    recovery_operation_id,
                    self._project,
                    original_operation_id,
                    candidate_id,
                    revision.revision_id,
                    actor.actor_id,
                    session_id,
                    digest,
                    json.dumps(raw, sort_keys=True, separators=(",", ":")),
                    _now(),
                ),
            )
        return candidate

    def _operation_recovery(
        self,
        connection: CanonicalConnection,
        candidate_id: str,
        operation_id: str,
        session_id: str,
        actor: CorpusActor,
        *,
        recheck: bool = True,
    ):

        return operation_recovery(
            connection,
            project=self._project,
            candidate=self._candidate(connection, candidate_id),
            operation_id=operation_id,
            session_id=session_id,
            actor=actor,
            rights=self._rights,
            recheck=recheck,
        )

    def status(
        self,
        *,
        source_assertion_revision_id: str,
        work_id: str,
        work_revision_id: str,
        version_id: str,
        version_revision_id: str,
        operation_id: str | None,
        command_id: str | None,
        session_id: str,
        actor: CorpusActor,
    ) -> DocumentAttachmentStatus:
        selection = (source_assertion_revision_id, work_id, work_revision_id, version_id, version_revision_id)
        if (
            any(not is_uuid_v7(value) for value in selection)
            or (operation_id is not None and not is_uuid_v7(operation_id))
            or (command_id is not None and (operation_id is None or not is_uuid_v7(command_id)))
            or _SESSION.fullmatch(session_id) is None
        ):
            raise AttachmentProblem("attachment-status-invalid")

        # Recover only expired leases of these one-attempt activities. Existing
        # queue recovery records abandonment; it neither reclaims nor dispatches.
        from .ports.workflow_executor import WorkflowActor

        with self._corpus._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
        self._queue.recover_expired(
            now=_now(),
            actor=WorkflowActor(actor.actor_id, "human", "researcher"),
            activity_types=("document-intake-local", "document-intake-remote"),
        )

        def result(
            state: AttachmentStatusState,
            candidate_id: str | None = None,
            attachment_id: str | None = None,
            document_revision_id: str | None = None,
            *,
            found_operation: str | None = operation_id,
            found_command: str | None = command_id,
            intake_code: str | None = None,
        ) -> DocumentAttachmentStatus:
            return DocumentAttachmentStatus(
                state,
                self._project,
                *selection,
                found_operation,
                found_command,
                candidate_id,
                attachment_id,
                document_revision_id,
                intake_code,
            )

        def intake_status(connection: CanonicalConnection) -> DocumentAttachmentStatus | None:
            row = connection.execute(
                "SELECT i.operation_id,i.session_id,j.state,j.diagnostic_code,r.code "
                "FROM document_intake_jobs i JOIN workflow_queue_jobs j "
                "ON j.project_id=i.project_id AND j.job_id=i.job_id "
                "LEFT JOIN document_intake_results r ON r.project_id=i.project_id AND r.operation_id=i.operation_id "
                "WHERE i.project_id=? AND i.actor_id=? "
                "AND json_extract(i.selection_json,'$.sourceAssertionRevisionId')=? "
                "AND json_extract(i.selection_json,'$.workId')=? "
                "AND json_extract(i.selection_json,'$.workRevisionId')=? "
                "AND json_extract(i.selection_json,'$.versionId')=? "
                "AND json_extract(i.selection_json,'$.versionRevisionId')=? "
                "AND (? IS NULL OR i.operation_id=?) "
                "AND j.state IN ('claimed','running','cancelling','failed','cancelled') "
                "ORDER BY i.created_at DESC,i.operation_id DESC LIMIT 1",
                (self._project, actor.actor_id, *selection, operation_id, operation_id),
            ).fetchone()
            if row is None or command_id is not None:
                return None
            code = str(row[4] or row[3] or "acquisition-failed")
            state: AttachmentStatusState = "intake-failed"
            if row[2] in {"claimed", "running", "cancelling"}:
                state = "intake-running"
                if row[1] != session_id:
                    code = "intake-interrupted"
                elif code not in {"intake-downloading", "intake-validating"}:
                    code = "intake-downloading" if row[2] != "cancelling" else "intake-cancelling"
            elif row[2] == "cancelled":
                state = "intake-cancelled"
            elif code == "acquisition-cleanup-required":
                try:
                    self.ensure_intake_ready()
                except ObjectStagingCleanupRequired:
                    pass
                else:
                    code = "intake-cleanup-cleared"
            return result(state, found_operation=str(row[0]), found_command=None, intake_code=code)

        with self._corpus._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
            if operation_id is not None:
                row = connection.execute(
                    "SELECT o.candidate_id,o.session_id,o.actor_id,c.source_assertion_revision_id,c.work_id,"
                    "c.work_revision_id,c.version_id,c.version_revision_id "
                    "FROM document_attachment_operations o JOIN document_attachment_candidates c "
                    "ON c.project_id=o.project_id AND c.candidate_id=o.candidate_id "
                    "WHERE o.project_id=? AND o.operation_id=?",
                    (self._project, operation_id),
                ).fetchone()
                recovered = False
                if row is None:
                    row = connection.execute(
                        "SELECT o.candidate_id,o.session_id,o.actor_id,c.source_assertion_revision_id,c.work_id,"
                        "c.work_revision_id,c.version_id,c.version_revision_id "
                        "FROM document_attachment_recoveries o JOIN document_attachment_candidates c "
                        "ON c.project_id=o.project_id AND c.candidate_id=o.candidate_id "
                        "WHERE o.project_id=? AND o.operation_id=?",
                        (self._project, operation_id),
                    ).fetchone()
                    recovered = row is not None
                if row is None:
                    intake = intake_status(connection)
                    if intake is not None:
                        return intake
                if row is None or str(row[2]) != actor.actor_id or tuple(row[3:8]) != selection:
                    return result("unavailable", found_command=None)
                candidate_id = str(row[0])
                attachment = connection.execute(
                    "SELECT attachment_id,document_revision_id,command_id FROM document_attachment_assertions "
                    "WHERE project_id=? AND candidate_id=?",
                    (self._project, candidate_id),
                ).fetchone()
                if attachment is not None:
                    if command_id is not None and str(attachment[2]) != command_id:
                        return result("unavailable", found_command=None)
                    return result(
                        "committed",
                        candidate_id,
                        str(attachment[0]),
                        str(attachment[1]),
                        found_command=str(attachment[2]),
                    )
                if connection.execute(
                    "SELECT 1 FROM document_attachment_cancellations WHERE project_id=? AND candidate_id=?",
                    (self._project, candidate_id),
                ).fetchone():
                    return result("cancelled", candidate_id)
                if str(row[1]) != session_id:
                    return result("stale-session", candidate_id, found_command=None)
                if recovered:
                    try:
                        self._operation_recovery(connection, candidate_id, operation_id, session_id, actor)
                    except AttachmentProblem, AcquisitionProblem:
                        return result("unresolved", candidate_id, found_command=None)
                return result("unresolved" if command_id is not None else "candidate", candidate_id)

            attachment = connection.execute(
                "SELECT a.attachment_id,a.document_revision_id,a.candidate_id,a.command_id,o.operation_id "
                "FROM document_attachment_assertions a LEFT JOIN document_attachment_operations o "
                "ON o.project_id=a.project_id AND o.candidate_id=a.candidate_id "
                "WHERE a.project_id=? AND a.source_assertion_revision_id=? AND a.work_id=? "
                "AND a.work_revision_id=? AND a.version_id=? AND a.version_revision_id=? "
                "ORDER BY a.committed_at DESC,a.attachment_id DESC LIMIT 1",
                (self._project, *selection),
            ).fetchone()
            if attachment is None:
                intake = intake_status(connection)
                if intake is not None:
                    return intake
                return result("metadata-only", found_operation=None, found_command=None)
            found_operation = str(attachment[4]) if attachment[4] is not None else None
            return result(
                "committed" if found_operation is not None else "legacy",
                str(attachment[2]),
                str(attachment[0]),
                str(attachment[1]),
                found_operation=found_operation,
                found_command=str(attachment[3]),
            )

    def cancel(
        self,
        candidate_id: str,
        *,
        actor: CorpusActor,
        operation_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        with self._corpus._transaction(write=True) as (connection, _):
            self._authority(connection, actor)
            if operation_id is not None or session_id is not None:
                if (
                    operation_id is None
                    or session_id is None
                    or not is_uuid_v7(operation_id)
                    or _SESSION.fullmatch(session_id) is None
                ):
                    raise AttachmentProblem("attachment-operation-invalid")
                self._operation_recovery(connection, candidate_id, operation_id, session_id, actor, recheck=False)
            self._candidate(connection, candidate_id)
            if connection.execute(
                "SELECT 1 FROM document_attachment_assertions WHERE project_id=? AND candidate_id=?",
                (self._project, candidate_id),
            ).fetchone():
                raise AttachmentProblem("attachment-already-committed")
            connection.execute(
                "INSERT OR IGNORE INTO document_attachment_cancellations VALUES (?,?,?,?,?)",
                (candidate_id, self._project, actor.actor_id, actor.trace_id, _now()),
            )

    def commit(
        self,
        candidate_id: str,
        *,
        confirmation_sha256: str,
        command_id: str,
        actor: CorpusActor,
        operation_id: str | None = None,
        session_id: str | None = None,
        match_confirmed: bool | None = None,
        permitted_use: str | None = None,
        exact_selection: tuple[str, str, str, str, str] | None = None,
    ) -> DocumentAttachment:
        if not is_uuid_v7(candidate_id) or not is_uuid_v7(command_id):
            raise AttachmentProblem("attachment-command-invalid")
        project_only = operation_id is not None
        if project_only:
            if (
                not is_uuid_v7(operation_id)
                or _SESSION.fullmatch(session_id or "") is None
                or match_confirmed is not True
                or permitted_use != "project-only"
                or exact_selection is None
                or len(exact_selection) != 5
                or any(not is_uuid_v7(value) for value in exact_selection)
            ):
                raise AttachmentProblem("attachment-command-invalid")
            command_sha256 = _sha(
                {
                    "candidateId": candidate_id,
                    "confirmationSha256": confirmation_sha256,
                    "operationId": operation_id,
                    "sessionId": session_id,
                    "selection": exact_selection,
                    "matchConfirmed": True,
                    "permittedUse": "project-only",
                }
            )
        else:
            if any(value is not None for value in (session_id, match_confirmed, permitted_use, exact_selection)):
                raise AttachmentProblem("attachment-command-invalid")
            command_sha256 = _sha({"candidateId": candidate_id, "confirmationSha256": confirmation_sha256})
        # Preserve operation-denial precedence before resolving protected source
        # bytes outside the writer. The writer rechecks the same exact binding.
        with self._corpus._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
            if project_only:
                assert operation_id is not None and session_id is not None
                self._operation_recovery(connection, candidate_id, operation_id, session_id, actor)
            subject = self._candidate(connection, candidate_id).rights_subject
        connector_record = self._rights._resolve_connector_record(subject)
        try:
            with self._corpus._transaction(write=True) as (connection, aggregates):
                self._authority(connection, actor)
                if project_only:
                    assert operation_id is not None and session_id is not None
                    recovery = self._operation_recovery(connection, candidate_id, operation_id, session_id, actor)
                else:
                    recovery = None
                replay = connection.execute(
                    "SELECT attachment_id,command_sha256,actor_id FROM document_attachment_assertions "
                    "WHERE project_id=? AND command_id=?",
                    (self._project, command_id),
                ).fetchone()
                if replay is not None:
                    if replay[1] != command_sha256 or replay[2] != actor.actor_id:
                        raise AttachmentProblem("attachment-command-conflict")
                    return self._attachment(connection, str(replay[0]))
                candidate = self._candidate(connection, candidate_id)
                if project_only and exact_selection != (
                    candidate.source_assertion_revision_id,
                    candidate.work_id,
                    candidate.work_revision_id,
                    candidate.version_id,
                    candidate.version_revision_id,
                ):
                    raise AttachmentProblem("attachment-association-stale")
                if connection.execute(
                    "SELECT 1 FROM document_attachment_cancellations WHERE project_id=? AND candidate_id=?",
                    (self._project, candidate_id),
                ).fetchone():
                    raise AttachmentProblem("attachment-candidate-cancelled")
                if confirmation_sha256 != candidate.candidate_sha256:
                    raise AttachmentProblem("attachment-confirmation-required")
                self._current_binding(
                    connection,
                    source_assertion_revision_id=candidate.source_assertion_revision_id,
                    work_id=candidate.work_id,
                    work_revision_id=candidate.work_revision_id,
                    version_id=candidate.version_id,
                    version_revision_id=candidate.version_revision_id,
                )
                object_row = connection.execute(
                    "SELECT byte_length,media_type,storage_state FROM object_records "
                    "WHERE project_id=? AND object_sha256=?",
                    (self._project, candidate.object_sha256),
                ).fetchone()
                if object_row is None or tuple(object_row) != (
                    candidate.byte_length,
                    candidate.media_type,
                    "available",
                ):
                    raise AttachmentProblem("attachment-object-unavailable")
                try:
                    acquired = acquisition_policy_for_commit(
                        connection,
                        self._rights,
                        self._project,
                        candidate_id,
                        actor,
                        reviewed_policy_revision_id=recovery[1].current_provider_policy_revision_id
                        if recovery
                        else None,
                    )
                except AcquisitionProblem as error:
                    raise AttachmentProblem(error.code) from None
                if project_only and self._rights.current_with_connection(connection, candidate.rights_subject) is None:
                    permissions = tuple(
                        RightsPermissionDraft(
                            use=use,
                            value="permitted",
                            basis="researcher-confirmed",
                            confidence="confirmed",
                            grantee_actor_id=actor.actor_id,
                            evidence_revision_ids=(candidate.source_assertion_revision_id,),
                            license_observation_revision_id=None,
                            entitlement_revision_id=None,
                        )
                        for use in (
                            RightsUse(action="store", purpose="document-attachment", destination_kind="local-project"),
                            RightsUse(action="inspect", purpose="document-analysis", destination_kind="local-project"),
                        )
                    )
                    self._rights.publish_draft_with_connection(
                        connection,
                        aggregates,
                        candidate.rights_subject,
                        permissions,
                        None,
                        command_id=command_id,
                        command_sha256=command_sha256,
                        actor=actor,
                        connector_record=connector_record,
                    )
                decision = self._rights.evaluate_with_connection(
                    connection,
                    RightsRequest(
                        actor_id=actor.actor_id,
                        subject=candidate.rights_subject,
                        use=RightsUse(action="store", purpose="document-attachment", destination_kind="local-project"),
                    ),
                    actor=actor,
                )
                if decision.code != "allow" or decision.policy_revision_id is None:
                    raise _Denied(decision)
                if project_only:
                    inspect_decision = self._rights.evaluate_with_connection(
                        connection,
                        RightsRequest(
                            actor_id=actor.actor_id,
                            subject=candidate.rights_subject,
                            use=RightsUse(
                                action="inspect", purpose="document-analysis", destination_kind="local-project"
                            ),
                        ),
                        actor=actor,
                    )
                    if inspect_decision.code != "allow":
                        raise _Denied(inspect_decision)
                sources = tuple(
                    aggregates.get_revision(value)
                    for value in dict.fromkeys(
                        (
                            candidate.source_assertion_revision_id,
                            candidate.work_revision_id,
                            candidate.version_revision_id,
                            decision.policy_revision_id,
                            *((acquired[0],) if acquired is not None else ()),
                            *((recovery[0],) if recovery else ()),
                            *(
                                (recovery[1].original_provider_policy_revision_id,)
                                if recovery and recovery[1].original_provider_policy_revision_id
                                else ()
                            ),
                        )
                    )
                )
                document_id, revision_id, attachment_id = new_uuid_v7(), new_uuid_v7(), new_uuid_v7()
                event = AtomicRepositoryEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type="document.attached",
                    occurred_at=actor.occurred_at,
                    available_at=actor.occurred_at,
                    trace_id=actor.trace_id,
                    actor_type="human",
                    actor_id=actor.actor_id,
                    idempotency_key="document-attachment-" + command_id,
                )
                dependencies = tuple(
                    MaterialDependency(
                        dependency_id=new_uuid_v7(),
                        dependency_kind="human-decision" if value.aggregate_kind == "decision" else "source-revision",
                        relation_type="direct",
                        revision_id=value.revision_id,
                        configuration_id=None,
                        configuration_version=None,
                        fingerprint=_projection_content_sha256(value),
                        governing_policy_id="dependency.material.v1",
                        governing_policy_version="1.0.0",
                    )
                    for value in sources
                )
                if acquired is not None:
                    dependencies += (
                        MaterialDependency(
                            new_uuid_v7(),
                            "parameter-set",
                            "direct",
                            None,
                            "document.acquisition-source",
                            "1.0.0",
                            "sha256:" + acquired[1],
                            "dependency.material.v1",
                            "1.0.0",
                        ),
                    )
                revision = aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=revision_id,
                        aggregate_id=document_id,
                        aggregate_kind="document",
                        created_at=actor.occurred_at,
                        modified_at=actor.occurred_at,
                        display_label_observed=candidate.source_name,
                        display_label_normalized=None,
                        knowledge_status="observed",
                        rights_status="allowed",
                        object_sha256=candidate.object_sha256,
                        dependency_coverage="complete",
                        provenance_inputs=sources,
                        material_dependencies=dependencies,
                    ),
                    event,
                    expected_revision=None,
                )
                if revision.revision_id != revision_id:
                    raise AttachmentProblem("attachment-aggregate-conflict")
                connection.execute(
                    "INSERT INTO document_attachment_assertions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        attachment_id,
                        self._project,
                        candidate_id,
                        candidate.source_assertion_revision_id,
                        document_id,
                        revision_id,
                        candidate.work_id,
                        candidate.work_revision_id,
                        candidate.version_id,
                        candidate.version_revision_id,
                        candidate.object_sha256,
                        _digest(candidate.rights_subject.model_dump(mode="json", by_alias=True)),
                        decision.policy_revision_id,
                        confirmation_sha256,
                        command_id,
                        command_sha256,
                        event.event_id,
                        event.outbox_id,
                        actor.actor_id,
                        actor.occurred_at,
                    ),
                )
                return self._attachment(connection, attachment_id)
        except _Denied as denied:
            try:
                self._rights.append_denied_attempt(denied.decision, actor=actor)
            except RightsProblem:
                raise AttachmentProblem("attachment-rights-integrity-invalid") from None
            raise AttachmentProblem("attachment-rights-denied") from None
        except sqlite3.Error, RightsProblem:
            raise AttachmentProblem("attachment-commit-failed") from None

    def _attachment(self, connection: CanonicalConnection, attachment_id: str) -> DocumentAttachment:
        row = connection.execute(
            "SELECT document_id,document_revision_id,candidate_id,work_id,work_revision_id,version_id,"
            "version_revision_id,source_assertion_revision_id,object_sha256,rights_policy_revision_id,"
            "provenance_event_id,outbox_id FROM document_attachment_assertions "
            "WHERE project_id=? AND attachment_id=?",
            (self._project, attachment_id),
        ).fetchone()
        if row is None:
            raise AttachmentProblem("attachment-integrity-invalid")
        return DocumentAttachment(attachment_id, *tuple(row))


def load_location(connection: CanonicalConnection, project: str, identity: str) -> AcquisitionLocation:
    row = connection.execute(
        "SELECT source_assertion_revision_id,location_key,location_sha256,location_json "
        "FROM acquisition_locations WHERE project_id=? AND location_id=?",
        (project, identity),
    ).fetchone()
    if row is None:
        raise AcquisitionProblem("acquisition-location-unavailable")
    try:
        location = AcquisitionLocation.model_validate_json(str(row[3]))
    except ValidationError:
        raise AcquisitionProblem("acquisition-location-integrity-invalid") from None
    value = location.model_dump(mode="json", by_alias=True)
    value.pop("locationSha256")
    if (
        location.location_id != identity
        or location.project_id != project
        or tuple(row[:3]) != (location.source_assertion_revision_id, location.location_key, location.location_sha256)
        or _sha(value) != location.location_sha256
    ):
        raise AcquisitionProblem("acquisition-location-integrity-invalid")
    source_row = connection.execute(
        "SELECT assertion_json FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
        (project, location.source_assertion_revision_id),
    ).fetchone()
    if source_row is None:
        raise AcquisitionProblem("acquisition-source-invalid")
    source = SourceAssertion.model_validate_json(str(source_row[0]))
    if (
        source.address != location.address
        or source.source_sha256 != location.source_sha256
        or source.provider != location.provider
        or source.source_revision_id != location.source_revision_id
    ):
        raise AcquisitionProblem("acquisition-source-invalid")
    return location


def permitted_policy(
    connection: CanonicalConnection,
    rights: SqliteRightsRepository,
    location: AcquisitionLocation,
    actor: CorpusActor,
    *,
    record: bool = False,
) -> RightsPolicyRevision:
    rights._authority(connection, actor)
    policy = rights.current_with_connection(connection, location.rights_subject)
    uses: tuple[tuple[RightsAction, str], ...] = (("store", "document-acquisition"), ("inspect", "document-analysis"))
    for action, purpose in uses:
        request = RightsRequest(
            actor_id=actor.actor_id,
            subject=location.rights_subject,
            use=RightsUse(action=action, purpose=purpose, destination_kind="local-project"),
        )
        decision = (
            rights.evaluate_with_connection(connection, request, actor=actor)
            if record
            else evaluate_rights(policy, request, now=datetime.now(UTC))
        )
        if (
            decision.code != "allow"
            or policy is None
            or rights._recheck_scope_with_connection(connection, policy).disposition != "complete"
        ):
            raise AcquisitionProblem("acquisition-rights-denied")
    assert policy is not None
    return policy


def _append_attempt_revision(
    aggregates: _SqliteAggregateRepository,
    operation_id: str,
    actor: CorpusActor,
    *,
    code: str,
    inputs: tuple[AggregateRevision, ...],
    fingerprints: tuple[tuple[str, str], ...],
    previous: int | None,
) -> AggregateRevision:
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    created_at = aggregates.get(operation_id).created_at if previous is not None else now
    dependencies = tuple(
        MaterialDependency(
            new_uuid_v7(),
            "human-decision" if item.aggregate_kind == "decision" else "source-revision",
            "direct",
            item.revision_id,
            None,
            None,
            _projection_content_sha256(item),
            "dependency.material.v1",
            "1.0.0",
        )
        for item in inputs
    )
    dependencies += tuple(
        MaterialDependency(
            new_uuid_v7(),
            "parameter-set",
            "direct",
            None,
            "acquisition." + name,
            "1.0.0",
            "sha256:" + digest,
            "dependency.material.v1",
            "1.0.0",
        )
        for name, digest in fingerprints
    )
    return aggregates.append(
        AggregateRevisionDraft(
            revision_id=new_uuid_v7(),
            aggregate_id=operation_id,
            aggregate_kind="workflow",
            created_at=created_at,
            modified_at=now,
            display_label_observed=code,
            display_label_normalized=None,
            knowledge_status="observed",
            rights_status="allowed",
            dependency_coverage="complete",
            provenance_inputs=tuple(inputs),
            material_dependencies=dependencies,
        ),
        AtomicRepositoryEvent(
            new_uuid_v7(),
            new_uuid_v7(),
            "document." + code,
            now,
            now,
            actor.trace_id,
            "human",
            actor.actor_id,
            "acquisition-" + operation_id + "-" + code,
        ),
        expected_revision=previous,
    )


def finish_attempt_with_connection(
    connection: CanonicalConnection,
    aggregates: _SqliteAggregateRepository,
    *,
    project: str,
    operation_id: str,
    actor: CorpusActor,
    outcome: str,
    code: str,
    candidate_id: str | None = None,
):
    row = connection.execute(
        "SELECT actor_id,revision_id FROM acquisition_attempts WHERE project_id=? AND operation_id=?",
        (project, operation_id),
    ).fetchone()
    if row is None or row[0] != actor.actor_id:
        raise AcquisitionProblem("acquisition-attempt-unavailable")
    existing = connection.execute(
        "SELECT revision_id FROM acquisition_attempt_results WHERE project_id=? AND operation_id=?",
        (project, operation_id),
    ).fetchone()
    if existing:
        return aggregates.get_revision(str(existing[0]))
    initial = aggregates.get_revision(str(row[1]))
    inputs = (initial,)
    if candidate_id is not None and (
        connection.execute(
            "SELECT 1 FROM document_attachment_operations WHERE project_id=? AND operation_id=? "
            "AND candidate_id=? AND actor_id=?",
            (project, operation_id, candidate_id, actor.actor_id),
        ).fetchone()
        is None
    ):
        raise AcquisitionProblem("acquisition-attempt-changed")
    fingerprints = [("outcome", _sha({"outcome": outcome, "code": code, "candidateId": candidate_id}))]
    if candidate_id is not None:
        candidate = connection.execute(
            "SELECT c.object_sha256,c.candidate_sha256,s.receipt_sha256 FROM document_attachment_candidates c "
            "JOIN document_acquisition_sources s ON s.project_id=c.project_id AND s.candidate_id=c.candidate_id "
            "WHERE c.project_id=? AND c.candidate_id=?",
            (project, candidate_id),
        ).fetchone()
        if candidate is None:
            raise AcquisitionProblem("acquisition-attempt-changed")
        fingerprints.extend(zip(("copy-bytes", "candidate", "receipt"), map(str, candidate), strict=True))
    revision = _append_attempt_revision(
        aggregates,
        operation_id,
        actor,
        code=code,
        inputs=inputs,
        fingerprints=tuple(fingerprints),
        previous=initial.revision,
    )
    connection.execute(
        "INSERT INTO acquisition_attempt_results VALUES (?,?,?,?,?,?)",
        (operation_id, project, revision.revision_id, outcome, code, candidate_id),
    )
    return revision


def publish_acquisition_source(
    connection: CanonicalConnection,
    aggregates: _SqliteAggregateRepository,
    rights: SqliteRightsRepository,
    *,
    project: str,
    operation_id: str,
    candidate_id: str,
    object_sha256: str,
    byte_length: int,
    receipt: AcquisitionReceipt,
    actor: CorpusActor,
    queue: _SqliteWorkflowQueueRepository,
    intake_claim: WorkflowJobClaim | None,
) -> None:
    location = load_location(connection, project, receipt.location_id)
    policy = permitted_policy(connection, rights, location, actor, record=True)
    if (
        policy.revision_id != receipt.provider_policy_revision_id
        or location.location_sha256 != receipt.location_sha256
        or receipt.actual_sha256 != object_sha256
        or receipt.expanded_bytes != byte_length
        or (receipt.expected_sha256 is not None and receipt.expected_sha256 != object_sha256)
    ):
        raise AcquisitionProblem("acquisition-publication-changed")
    raw = receipt.model_dump(mode="json", by_alias=True)
    connection.execute(
        "INSERT INTO document_acquisition_sources VALUES (?,?,?,?,?,?,?)",
        (
            candidate_id,
            project,
            operation_id,
            location.location_id,
            policy.revision_id,
            _sha(raw),
            json.dumps(raw, sort_keys=True, separators=(",", ":")),
        ),
    )
    revision = finish_attempt_with_connection(
        connection,
        aggregates,
        project=project,
        operation_id=operation_id,
        actor=actor,
        outcome="candidate",
        code="acquisition-candidate",
        candidate_id=candidate_id,
    )
    if intake_claim is None:
        raise AcquisitionProblem("acquisition-attempt-changed")

    finish_intake(
        connection,
        aggregates,
        queue,
        intake_claim,
        project=project,
        operation_id=operation_id,
        actor=actor,
        outcome="candidate",
        code="acquisition-candidate",
        candidate_id=candidate_id,
        revision=revision,
    )


def acquisition_policy_for_commit(
    connection: CanonicalConnection,
    rights: SqliteRightsRepository,
    project: str,
    candidate_id: str,
    actor: CorpusActor,
    *,
    reviewed_policy_revision_id: str | None = None,
) -> tuple[str, str] | None:
    row = connection.execute(
        "SELECT location_id,provider_policy_revision_id,receipt_sha256,receipt_json "
        "FROM document_acquisition_sources WHERE project_id=? AND candidate_id=?",
        (project, candidate_id),
    ).fetchone()
    if row is None:
        return None
    try:
        receipt = AcquisitionReceipt.model_validate_json(str(row[3]))
    except ValidationError:
        raise AcquisitionProblem("acquisition-receipt-integrity-invalid") from None
    if (
        receipt.location_id != row[0]
        or receipt.provider_policy_revision_id != row[1]
        or _sha(receipt.model_dump(mode="json", by_alias=True)) != row[2]
    ):
        raise AcquisitionProblem("acquisition-receipt-integrity-invalid")
    location = load_location(connection, project, str(row[0]))
    policy = permitted_policy(connection, rights, location, actor, record=True)
    # A newer permission is a different basis. Reacquisition/confirmation is
    # explicit; do not silently relabel a completed download's decision.
    if policy.revision_id != (reviewed_policy_revision_id or receipt.provider_policy_revision_id):
        raise AcquisitionProblem("acquisition-policy-changed")
    return policy.revision_id, str(row[2])


class AcquisitionRepository:
    def __init__(
        self,
        database: Path,
        project_id: str,
        resolve_record: Callable[[str, int], ConnectorRecord],
        attachments: LocalDocumentAttachmentService,
    ):
        self._database, self._project, self._resolve = database, project_id, resolve_record
        self._attachments = attachments
        self._corpus = SqliteCorpusRepository(database, project_id)
        self.rights = SqliteRightsRepository(database, project_id, connector_record_resolver=resolve_record)
        self._queue = _SqliteWorkflowQueueRepository(database, project_id)
        self._claims: dict[str, WorkflowJobClaim] = {}

    def begin_attempt(
        self,
        selection: AcquisitionSelection,
        *,
        operation_id: str,
        session_id: str,
        confirmation_sha256: str,
        expected_policy_revision_id: str,
        actor: CorpusActor,
    ) -> WorkflowJobClaim:
        with self._corpus._transaction(write=True) as (connection, aggregates):
            self._corpus._authority(connection, actor)
            if connection.execute(
                "SELECT 1 FROM acquisition_attempts WHERE operation_id=?", (operation_id,)
            ).fetchone():
                raise AcquisitionProblem("acquisition-operation-conflict")
            location = load_location(connection, self._project, selection.location_id)
            policy = permitted_policy(connection, self.rights, location, actor, record=True)
            if (
                location.location_sha256 != selection.location_sha256
                or location.source_assertion_revision_id != selection.source_assertion_revision_id
                or policy.revision_id != expected_policy_revision_id
            ):
                raise AcquisitionProblem("acquisition-preview-stale")
            self._attachments._current_binding(
                connection,
                source_assertion_revision_id=selection.source_assertion_revision_id,
                work_id=selection.work_id,
                work_revision_id=selection.work_revision_id,
                version_id=selection.version_id,
                version_revision_id=selection.version_revision_id,
            )
            inputs = tuple(
                aggregates.get_revision(identity)
                for identity in (
                    selection.source_assertion_revision_id,
                    selection.work_revision_id,
                    selection.version_revision_id,
                    policy.revision_id,
                )
            )
            raw = selection.model_dump(mode="json", by_alias=True)
            revision = _append_attempt_revision(
                aggregates,
                operation_id,
                actor,
                code="acquisition-admitted",
                inputs=inputs,
                fingerprints=(
                    ("selection", _sha(raw)),
                    ("confirmation", confirmation_sha256),
                    ("intent", actor.intent_sha256),
                    ("privacy", actor.policy_sha256),
                ),
                previous=None,
            )
            connection.execute(
                "INSERT INTO acquisition_attempts VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    operation_id,
                    self._project,
                    revision.revision_id,
                    location.location_id,
                    actor.actor_id,
                    session_id,
                    json.dumps(raw, sort_keys=True, separators=(",", ":")),
                    confirmation_sha256,
                    revision.created_at,
                ),
            )

            claim = admit_intake(
                connection,
                aggregates,
                self._queue,
                project=self._project,
                operation_id=operation_id,
                session_id=session_id,
                kind="remote-download",
                selection=raw,
                confirmation_sha256=confirmation_sha256,
                actor=actor,
                initial=revision,
            )
        self._claims[operation_id] = claim
        return claim

    def intake_cancelled(self, claim: WorkflowJobClaim) -> bool:
        return self._queue.cancellation_requested(claim, now=_now())

    def intake_downloading(self, claim: WorkflowJobClaim, *, actor: CorpusActor) -> None:

        with self._corpus._transaction(write=True) as (connection, _):
            self._attachments._authority(connection, actor)
            mark_intake_phase(connection, self._queue, claim, "downloading")

    def release_intake(self, operation_id: str) -> None:
        self._claims.pop(operation_id, None)

    def recover_candidate(
        self,
        candidate_id: str,
        *,
        original_operation_id: str,
        recovery_operation_id: str,
        session_id: str,
        selection: AcquisitionSelection,
        confirmation_sha256: str,
        actor: CorpusActor,
    ) -> AttachmentCandidate:
        return self._attachments.recover_candidate(
            candidate_id,
            original_operation_id=original_operation_id,
            recovery_operation_id=recovery_operation_id,
            session_id=session_id,
            exact_selection=selection.association,
            confirmation_sha256=confirmation_sha256,
            actor=actor,
            remote_selection=selection,
        )

    def _access_selection(
        self, connection: CanonicalConnection, selection: AccessNeedSelection | AcquisitionSelection, actor: CorpusActor
    ) -> AccessNeedSelection:
        value = AccessNeedSelection(**{name: getattr(selection, name) for name in AccessNeedSelection.model_fields})
        self._corpus._authority(connection, actor)
        self._attachments._current_binding(
            connection,
            source_assertion_revision_id=value.source_assertion_revision_id,
            work_id=value.work_id,
            work_revision_id=value.work_revision_id,
            version_id=value.version_id,
            version_revision_id=value.version_revision_id,
        )
        if (value.location_id is None) != (value.location_sha256 is None):
            raise AcquisitionProblem("acquisition-selection-invalid")
        if value.location_id is not None:
            location = load_location(connection, self._project, value.location_id)
            if (
                location.location_sha256 != value.location_sha256
                or location.source_assertion_revision_id != value.source_assertion_revision_id
            ):
                raise AcquisitionProblem("acquisition-selection-invalid")
        return value

    def record_access_need(
        self,
        selection: AccessNeedSelection | AcquisitionSelection,
        *,
        command_id: str,
        kind: AccessNeedKind,
        channel: AccessNeedChannel,
        actor: CorpusActor,
    ) -> DocumentAccessNeed:
        if kind not in {"unknown", "unavailable", "rights-denied", "entitlement-required"} or channel not in {
            "manual",
            "institutional",
        }:
            raise AcquisitionProblem("acquisition-command-invalid")
        with self._corpus._transaction(write=True) as (connection, aggregates):
            value = self._access_selection(connection, selection, actor)
            raw = value.model_dump(mode="json", by_alias=True)
            command_sha = _sha(
                {
                    "selection": raw,
                    "kind": kind,
                    "channel": channel,
                    "actorId": actor.actor_id,
                    "intent": actor.intent_sha256,
                    "privacy": actor.policy_sha256,
                }
            )
            self._corpus._command(command_id, command_sha, actor)
            replay = connection.execute(
                "SELECT revision_id,kind,channel,created_at,command_sha256 FROM document_access_needs "
                "WHERE project_id=? AND annotation_id=?",
                (self._project, command_id),
            ).fetchone()
            if replay is not None:
                if replay[4] != command_sha:
                    raise AcquisitionProblem("acquisition-operation-conflict")
                return DocumentAccessNeed(command_id, str(replay[0]), replay[1], replay[2], str(replay[3]), value)
            inputs = tuple(
                aggregates.get_revision(x)
                for x in (value.source_assertion_revision_id, value.work_revision_id, value.version_revision_id)
            )
            revision = _append_attempt_revision(
                aggregates,
                command_id,
                actor,
                code="access-need-recorded",
                inputs=inputs,
                fingerprints=(("local-access-annotation", command_sha),),
                previous=None,
            )
            now = _now()
            connection.execute(
                "INSERT INTO document_access_needs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    command_id,
                    self._project,
                    revision.revision_id,
                    value.location_id,
                    json.dumps(raw, sort_keys=True, separators=(",", ":")),
                    kind,
                    channel,
                    actor.actor_id,
                    command_sha,
                    now,
                ),
            )
            return DocumentAccessNeed(command_id, revision.revision_id, kind, channel, now, value)

    def access_needs(
        self,
        selection: AccessNeedSelection | AcquisitionSelection,
        *,
        actor: CorpusActor,
        after: str | None = None,
        limit: int = 100,
    ) -> tuple[DocumentAccessNeed, ...]:
        if (after is not None and not is_uuid_v7(after)) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise AcquisitionProblem("acquisition-command-invalid")
        with self._corpus._transaction(write=False) as (connection, _):
            value = self._access_selection(connection, selection, actor)
            raw = json.dumps(value.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":"))
            rows = connection.execute(
                "SELECT annotation_id,revision_id,kind,channel,created_at FROM document_access_needs "
                "WHERE project_id=? AND selection_json=? AND (? IS NULL OR annotation_id>?) "
                "ORDER BY annotation_id LIMIT ?",
                (self._project, raw, after, after, limit),
            ).fetchall()
            return tuple(DocumentAccessNeed(str(r[0]), str(r[1]), r[2], r[3], str(r[4]), value) for r in rows)

    def fail_attempt(self, operation_id: str, *, actor: CorpusActor, cancelled: bool, code: str) -> None:
        with self._corpus._transaction(write=True) as (connection, aggregates):
            self._corpus._authority(connection, actor)
            revision = finish_attempt_with_connection(
                connection,
                aggregates,
                project=self._project,
                operation_id=operation_id,
                actor=actor,
                outcome="cancelled" if cancelled else "failed",
                code=code,
            )
            claim = self._claims.get(operation_id)
            if claim is not None:
                finish_intake(
                    connection,
                    aggregates,
                    self._queue,
                    claim,
                    project=self._project,
                    operation_id=operation_id,
                    actor=actor,
                    outcome="cancelled" if cancelled else "failed",
                    code=code,
                    revision=revision,
                )
        self._claims.pop(operation_id, None)

    def locations(self, source_assertion_revision_id: str, *, actor: CorpusActor) -> tuple[AcquisitionLocation, ...]:
        if not is_uuid_v7(source_assertion_revision_id):
            raise AcquisitionProblem("acquisition-selection-invalid")
        with self._corpus._transaction(write=False) as (connection, _):
            self.rights._actor(actor)
            self._corpus._authority(connection, actor)
            row = connection.execute(
                "SELECT assertion_json FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
                (self._project, source_assertion_revision_id),
            ).fetchone()
            if row is None:
                raise AcquisitionProblem("acquisition-source-unavailable")
            source = SourceAssertion.model_validate_json(str(row[0]))
        if source.address.kind != "connector-record":
            return ()
        record = self._resolve(source.address.revision_id, source.address.ordinal)
        if (
            record.provider_id != source.provider
            or hashlib.sha256(record.model_dump_json(by_alias=True).encode()).hexdigest() != source.source_sha256
        ):
            raise AcquisitionProblem("acquisition-source-invalid")
        values = retained_locations(record)
        with self._corpus._transaction(write=True) as (connection, _):
            self._corpus._authority(connection, actor)
            if (
                connection.execute(
                    "SELECT assertion_json FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
                    (self._project, source_assertion_revision_id),
                ).fetchone()[0]
                != row[0]
            ):
                raise AcquisitionProblem("acquisition-source-invalid")
            result = []
            for value in values:
                prior = connection.execute(
                    "SELECT location_id FROM acquisition_locations WHERE project_id=? "
                    "AND source_assertion_revision_id=? AND location_key=?",
                    (self._project, source_assertion_revision_id, value.key),
                ).fetchone()
                if prior is not None:
                    result.append(load_location(connection, self._project, str(prior[0])))
                    continue
                location = AcquisitionLocation(
                    location_id=new_uuid_v7(),
                    project_id=self._project,
                    source_assertion_revision_id=source_assertion_revision_id,
                    source_revision_id=source.source_revision_id,
                    address=source.address,
                    source_sha256=source.source_sha256,
                    provider=source.provider,
                    location_key=value.key,
                    url=value.url,
                    license=value.license,
                    version=value.version,
                    location_sha256="0" * 64,
                )
                raw = location.model_dump(mode="json", by_alias=True)
                raw.pop("locationSha256")
                location = location.model_copy(update={"location_sha256": _sha(raw)})
                connection.execute(
                    "INSERT INTO acquisition_locations VALUES (?,?,?,?,?,?,?)",
                    (
                        location.location_id,
                        self._project,
                        source_assertion_revision_id,
                        value.key,
                        location.location_sha256,
                        location.model_dump_json(by_alias=True),
                        actor.occurred_at,
                    ),
                )
                result.append(location)
            return tuple(result)

    def authorize(
        self, selection: AcquisitionSelection, *, actor: CorpusActor
    ) -> tuple[AcquisitionLocation, RightsPolicyRevision]:
        with self._corpus._transaction(write=False) as (connection, _):
            self.rights._actor(actor)
            self._corpus._authority(connection, actor)
            location = load_location(connection, self._project, selection.location_id)
            if (
                location.source_assertion_revision_id != selection.source_assertion_revision_id
                or location.location_sha256 != selection.location_sha256
            ):
                raise AcquisitionProblem("acquisition-selection-invalid")
            intent = json.loads(
                connection.execute(
                    "SELECT text_value FROM settings WHERE project_id=? AND setting_key='research-intent.revision' "
                    "ORDER BY revision DESC LIMIT 1",
                    (self._project,),
                ).fetchone()[0]
            )
            declaration = intent.get("egressPolicy", {})
            settings = dict(
                connection.execute(
                    "SELECT setting_key,text_value FROM settings WHERE project_id=? AND setting_key IN "
                    "('privacy.network-policy','privacy.egress-consent-version') AND revision="
                    "(SELECT MAX(revision) FROM settings WHERE project_id=? AND setting_key LIKE 'privacy.%')",
                    (self._project, self._project),
                )
            )
            if (
                declaration.get("mode") != "approved-content"
                or location.provider not in declaration.get("approvedDestinationIds", ())
                or settings.get("privacy.network-policy") != "approved-providers"
                or settings.get("privacy.egress-consent-version") != "egress-preview-v1"
            ):
                raise AcquisitionProblem("acquisition-egress-denied")
            # Reuse exact active Work/Version/source membership rather than a
            # second association implementation or metadata-only identifier.
            self._attachments._current_binding(
                connection,
                source_assertion_revision_id=selection.source_assertion_revision_id,
                work_id=selection.work_id,
                work_revision_id=selection.work_revision_id,
                version_id=selection.version_id,
                version_revision_id=selection.version_revision_id,
            )
            return location, permitted_policy(connection, self.rights, location, actor)

    def source_for_revision(
        self, revision_id: str, *, actor: CorpusActor
    ) -> tuple[AcquisitionLocation, AcquisitionReceipt] | None:
        with self._corpus._transaction(write=False) as (connection, _):
            self._corpus._authority(connection, actor)
            row = connection.execute(
                "SELECT s.location_id,s.receipt_sha256,s.receipt_json FROM document_attachment_assertions a "
                "JOIN document_acquisition_sources s ON s.project_id=a.project_id AND s.candidate_id=a.candidate_id "
                "WHERE a.project_id=? AND a.document_revision_id=?",
                (self._project, revision_id),
            ).fetchone()
            if row is None:
                return None
            receipt = AcquisitionReceipt.model_validate_json(str(row[2]))
            if _sha(receipt.model_dump(mode="json", by_alias=True)) != row[1]:
                raise AcquisitionProblem("acquisition-receipt-integrity-invalid")
            return load_location(connection, self._project, str(row[0])), receipt


def admit_intake(
    connection: CanonicalConnection,
    aggregates: _SqliteAggregateRepository,
    queue: _SqliteWorkflowQueueRepository,
    *,
    project: str,
    operation_id: str,
    session_id: str,
    kind: Literal["local-import", "remote-download"],
    selection: Mapping[str, object],
    confirmation_sha256: str,
    actor: CorpusActor,
    initial: AggregateRevision | None = None,
) -> WorkflowJobClaim:

    if connection.execute("SELECT 1 FROM document_intake_jobs WHERE operation_id=?", (operation_id,)).fetchone():
        raise AcquisitionProblem("acquisition-operation-conflict")
    intent_value = json.loads(
        connection.execute(
            "SELECT text_value FROM settings WHERE project_id=? AND setting_key='research-intent.revision' "
            "ORDER BY revision DESC LIMIT 1",
            (project,),
        ).fetchone()[0]
    )
    intent = PreviewIntentContext(
        project_id=project,
        domain_project_id=intent_value["projectId"],
        intent_id=intent_value["intentId"],
        revision_id=actor.intent_revision_id,
        content_hash="sha256:" + actor.intent_sha256,
        status=intent_value["status"],
    )
    inputs = DocumentIntakeInput(
        kind=kind,
        operation_id=operation_id,
        session_id=session_id,
        actor_id=actor.actor_id,
        intent=intent,
        privacy_sha256=actor.policy_sha256,
        selection_sha256=_sha(selection),
        confirmation_sha256=confirmation_sha256,
    )
    if initial is None:
        source_inputs = tuple(
            aggregates.get_revision(str(selection[key]))
            for key in ("sourceAssertionRevisionId", "workRevisionId", "versionRevisionId")
        )
        initial = _append_attempt_revision(
            aggregates,
            operation_id,
            actor,
            code="intake-admitted",
            inputs=source_inputs,
            fingerprints=(("intake", inputs.configuration_hash.removeprefix("sha256:")),),
            previous=None,
        )
    now = _now()
    submission = build_document_intake(inputs, now=now)
    # All existing definition, snapshot, actor, idempotency and digest guards
    # execute in this same writer. No runnable job is exposed before its exact
    # native-owned operation is claimed and started.
    from .ports.workflow_executor import WorkflowActor

    queue._enqueue_with_connection(connection, submission, actor=WorkflowActor(actor.actor_id, "human", "researcher"))
    connection.execute(
        "INSERT INTO document_intake_jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            operation_id,
            project,
            initial.revision_id,
            submission.job_id,
            kind,
            actor.actor_id,
            session_id,
            json.dumps(selection, sort_keys=True, separators=(",", ":")),
            inputs.configuration_hash.removeprefix("sha256:"),
            now,
        ),
    )
    claim = queue._claim_next_with_connection(
        connection,
        worker_id=new_uuid_v7(),
        concurrency_classes=("document",),
        now=now,
        lease_duration_ms=600_000,
        activity_types=(submission.activity_type,),
        job_id=submission.job_id,
    )
    if claim is None:
        raise WorkflowQueueConflict("document intake admission could not claim its exact job")
    queue._start_with_connection(connection, claim, now=now)
    return claim


def mark_intake_phase(
    connection: CanonicalConnection,
    queue: _SqliteWorkflowQueueRepository,
    claim: WorkflowJobClaim,
    phase: Literal["downloading", "validating"],
) -> None:
    from .ports.object_store import ObjectStagingCancelled
    from .ports.workflow_executor import WorkflowActor

    now = _now()
    row = queue._lease_row(connection, claim, now, states=("running", "cancelling"))
    if row[1] == "cancelling" or row[3] is not None:
        raise ObjectStagingCancelled("document intake cancelled before phase")
    code = "intake-" + phase
    queue._append_history(
        connection,
        project_id=claim.project_id,
        workflow_run_id=claim.workflow_run_id,
        job_id=claim.job_id,
        attempt_id=claim.attempt_id,
        entity_type="job-attempt",
        entity_id=claim.attempt_id,
        from_state=str(row[4]),
        to_state=str(row[4]),
        occurred_at=now,
        actor=WorkflowActor(claim.worker_id, "workload", "local-workflow-worker"),
        reason_code=code,
        extra={"progress": json.loads(str(row[5]))},
    )
    connection.execute(
        "UPDATE workflow_queue_jobs SET diagnostic_code=?,updated_at=? WHERE project_id=? AND job_id=?",
        (code, now, claim.project_id, claim.job_id),
    )


def finish_intake(
    connection: CanonicalConnection,
    aggregates: _SqliteAggregateRepository,
    queue: _SqliteWorkflowQueueRepository,
    claim: WorkflowJobClaim,
    *,
    project: str,
    operation_id: str,
    actor: CorpusActor,
    outcome: Literal["candidate", "failed", "cancelled"],
    code: str,
    candidate_id: str | None = None,
    revision: AggregateRevision | None = None,
) -> None:

    row = connection.execute(
        "SELECT job_id,actor_id,revision_id FROM document_intake_jobs WHERE project_id=? AND operation_id=?",
        (project, operation_id),
    ).fetchone()
    if row is None or row[0] != claim.job_id or row[1] != actor.actor_id or claim.project_id != project:
        raise AcquisitionProblem("acquisition-attempt-changed")
    now = _now()
    # This also rejects expired/replaced capabilities before adding an outcome.
    cleanup_failed = outcome == "failed" and code == "acquisition-cleanup-required"
    queue._lease_row(
        connection,
        claim,
        now,
        states=("running", "cancelling") if outcome == "cancelled" or cleanup_failed else ("running",),
    )
    if revision is None:
        initial = aggregates.get_revision(str(row[2]))
        fingerprints = [("intake-outcome", _sha({"outcome": outcome, "code": code, "candidateId": candidate_id}))]
        if candidate_id is not None:
            candidate = connection.execute(
                "SELECT object_sha256,candidate_sha256 FROM document_attachment_candidates "
                "WHERE project_id=? AND candidate_id=?",
                (project, candidate_id),
            ).fetchone()
            if candidate is None:
                raise AcquisitionProblem("acquisition-attempt-changed")
            fingerprints.extend((("copy-bytes", str(candidate[0])), ("candidate", str(candidate[1]))))
        revision = _append_attempt_revision(
            aggregates,
            operation_id,
            actor,
            code=code,
            inputs=(initial,),
            fingerprints=tuple(fingerprints),
            previous=initial.revision,
        )
    connection.execute(
        "INSERT INTO document_intake_results VALUES (?,?,?,?,?,?)",
        (operation_id, project, revision.revision_id, outcome, code, candidate_id),
    )
    if outcome == "candidate":
        output = WorkflowOutputReference(
            revision.aggregate_id, revision.revision_id, _projection_content_sha256(revision), "application/json", None
        )
        queue._stage_artifact_with_connection(connection, claim, artifact=output, role="output", now=now)
        if queue._dependency_registration_gaps_with_connection(connection, claim, now=now, outputs=(output,)):
            raise WorkflowQueueConflict("document intake output dependency registration is incomplete")
        queue._complete_with_connection(connection, claim, now=now, outputs=(output,))
    else:
        queue._finish_attempt_with_connection(
            connection, claim, now=now, error_code=code, cancel=outcome == "cancelled"
        )


class DocumentRecoveryBasis(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    candidate_id: Identity
    candidate_sha256: Digest
    object_sha256: Digest
    original_operation_id: Identity
    actor_id: Identity
    session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    selection: tuple[Identity, Identity, Identity, Identity, Identity]
    intent_revision_id: Identity
    intent_sha256: Digest
    privacy_sha256: Digest
    candidate_policy_revision_id: Identity | None
    location_id: Identity | None
    location_sha256: Digest | None
    original_provider_policy_revision_id: Identity | None
    current_provider_policy_revision_id: Identity | None
    receipt_sha256: Digest | None


def current_recovery_basis(
    connection: CanonicalConnection,
    *,
    project: str,
    candidate: AttachmentCandidate,
    original_operation_id: str,
    session_id: str,
    actor: CorpusActor,
    rights: SqliteRightsRepository,
    remote_selection: AcquisitionSelection | None = None,
) -> DocumentRecoveryBasis:

    original = connection.execute(
        "SELECT actor_id FROM document_attachment_operations WHERE project_id=? AND operation_id=? AND candidate_id=?",
        (project, original_operation_id, candidate.candidate_id),
    ).fetchone()
    owner = connection.execute(
        "SELECT actor_id FROM document_attachment_candidates WHERE project_id=? AND candidate_id=?",
        (project, candidate.candidate_id),
    ).fetchone()
    if original is None or owner is None or original[0] != actor.actor_id or owner[0] != actor.actor_id:
        raise AttachmentProblem("attachment-operation-unavailable")
    current_policy = rights.current_with_connection(connection, candidate.rights_subject)
    acquired = connection.execute(
        "SELECT location_id,provider_policy_revision_id,receipt_sha256,receipt_json "
        "FROM document_acquisition_sources WHERE project_id=? AND candidate_id=?",
        (project, candidate.candidate_id),
    ).fetchone()
    location = None
    provider_policy = None
    if acquired is not None:
        receipt = AcquisitionReceipt.model_validate_json(str(acquired[3]))
        location = load_location(connection, project, str(acquired[0]))
        if (
            receipt.location_id != location.location_id
            or receipt.location_sha256 != location.location_sha256
            or receipt.provider_policy_revision_id != acquired[1]
            or _sha(receipt.model_dump(mode="json", by_alias=True)) != acquired[2]
            or receipt.actual_sha256 != candidate.object_sha256
            or receipt.expanded_bytes != candidate.byte_length
        ):
            raise AcquisitionProblem("acquisition-receipt-integrity-invalid")
        if remote_selection is not None:
            origin = connection.execute(
                "SELECT selection_json FROM acquisition_attempts WHERE project_id=? AND operation_id=?",
                (project, original_operation_id),
            ).fetchone()
            if origin is None or AcquisitionSelection.model_validate_json(str(origin[0])) != remote_selection:
                raise AcquisitionProblem("acquisition-selection-invalid")
        provider_policy = permitted_policy(connection, rights, location, actor)
    elif remote_selection is not None:
        raise AcquisitionProblem("acquisition-selection-invalid")
    return DocumentRecoveryBasis(
        project_id=project,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        object_sha256=candidate.object_sha256,
        original_operation_id=original_operation_id,
        actor_id=actor.actor_id,
        session_id=session_id,
        selection=(
            candidate.source_assertion_revision_id,
            candidate.work_id,
            candidate.work_revision_id,
            candidate.version_id,
            candidate.version_revision_id,
        ),
        intent_revision_id=actor.intent_revision_id,
        intent_sha256=actor.intent_sha256,
        privacy_sha256=actor.policy_sha256,
        candidate_policy_revision_id=current_policy.revision_id if current_policy else None,
        location_id=location.location_id if location else None,
        location_sha256=location.location_sha256 if location else None,
        original_provider_policy_revision_id=str(acquired[1]) if acquired else None,
        current_provider_policy_revision_id=provider_policy.revision_id if provider_policy else None,
        receipt_sha256=str(acquired[2]) if acquired else None,
    )


def operation_recovery(
    connection: CanonicalConnection,
    *,
    project: str,
    candidate: AttachmentCandidate,
    operation_id: str,
    session_id: str,
    actor: CorpusActor,
    rights: SqliteRightsRepository,
    recheck: bool = True,
) -> tuple[str, DocumentRecoveryBasis] | None:

    original = connection.execute(
        "SELECT 1 FROM document_attachment_operations WHERE project_id=? "
        "AND operation_id=? AND candidate_id=? AND actor_id=? AND session_id=?",
        (project, operation_id, candidate.candidate_id, actor.actor_id, session_id),
    ).fetchone()
    if original:
        return None
    row = connection.execute(
        "SELECT revision_id,basis_sha256,basis_json FROM document_attachment_recoveries "
        "WHERE project_id=? AND operation_id=? AND candidate_id=? AND actor_id=? AND session_id=?",
        (project, operation_id, candidate.candidate_id, actor.actor_id, session_id),
    ).fetchone()
    if row is None:
        raise AttachmentProblem("attachment-operation-unavailable")
    try:
        basis = DocumentRecoveryBasis.model_validate_json(str(row[2]))
    except ValueError:
        raise AttachmentProblem("attachment-recovery-integrity-invalid") from None
    if (
        _sha(basis.model_dump(mode="json", by_alias=True)) != row[1]
        or basis.session_id != session_id
        or basis.actor_id != actor.actor_id
    ):
        raise AttachmentProblem("attachment-recovery-integrity-invalid")
    if recheck and basis != current_recovery_basis(
        connection,
        project=project,
        candidate=candidate,
        original_operation_id=basis.original_operation_id,
        session_id=session_id,
        actor=actor,
        rights=rights,
    ):
        raise AttachmentProblem("attachment-recovery-stale")
    return str(row[0]), basis
