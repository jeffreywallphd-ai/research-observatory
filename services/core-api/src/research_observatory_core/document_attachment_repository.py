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
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from pydantic import ValidationError

from .corpus_repository import SqliteCorpusRepository
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.acquisition import AcquisitionStage
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
)
from .ports.object_store import ObjectPutCommand, ObjectStagingCancelled, ObjectStore
from .ports.repositories import AggregateRevisionDraft, AtomicRepositoryEvent, MaterialDependency
from .ports.rights import RightsPermissionDraft
from .reconciliation.contracts import SourceAssertion
from .repositories import _projection_content_sha256
from .rights_policy import RightsDecision, RightsRequest, RightsSubject, RightsUse
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
        from .connector_repository import ConnectorRepository

        self._rights = SqliteRightsRepository(
            database,
            project_id,
            connector_record_resolver=ConnectorRepository(database, project_id, objects).source_record,
        )

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
        publication_guard: Callable[[Callable[[], AttachmentCandidate]], AttachmentCandidate] | None = None,
        acquisition: AcquisitionStage | None = None,
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
            if cancellation_requested is not None and cancellation_requested():
                raise ObjectStagingCancelled()
            with self._corpus._transaction(write=True) as (connection, aggregates):
                if cancellation_requested is not None and cancellation_requested():
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
                    from .acquisition_repository import publish_acquisition_source

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

        def result(
            state: AttachmentStatusState,
            candidate_id: str | None = None,
            attachment_id: str | None = None,
            document_revision_id: str | None = None,
            *,
            found_operation: str | None = operation_id,
            found_command: str | None = command_id,
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
            )

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
                if (
                    connection.execute(
                        "SELECT 1 FROM document_attachment_operations WHERE project_id=? AND operation_id=? "
                        "AND candidate_id=? AND session_id=? AND actor_id=?",
                        (self._project, operation_id, candidate_id, session_id, actor.actor_id),
                    ).fetchone()
                    is None
                ):
                    raise AttachmentProblem("attachment-operation-unavailable")
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
            if (
                project_only
                and connection.execute(
                    "SELECT 1 FROM document_attachment_operations WHERE project_id=? AND operation_id=? "
                    "AND candidate_id=? AND session_id=? AND actor_id=?",
                    (self._project, operation_id, candidate_id, session_id, actor.actor_id),
                ).fetchone()
                is None
            ):
                raise AttachmentProblem("attachment-operation-unavailable")
            subject = self._candidate(connection, candidate_id).rights_subject
        connector_record = self._rights._resolve_connector_record(subject)
        try:
            with self._corpus._transaction(write=True) as (connection, aggregates):
                self._authority(connection, actor)
                if project_only:
                    assert operation_id is not None and session_id is not None
                    operation = connection.execute(
                        "SELECT 1 FROM document_attachment_operations WHERE project_id=? AND operation_id=? "
                        "AND candidate_id=? AND session_id=? AND actor_id=?",
                        (self._project, operation_id, candidate_id, session_id, actor.actor_id),
                    ).fetchone()
                    if operation is None:
                        raise AttachmentProblem("attachment-operation-unavailable")
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
                from .acquisition_repository import acquisition_policy_for_commit
                from .ports.acquisition import AcquisitionProblem

                try:
                    acquired = acquisition_policy_for_commit(
                        connection, self._rights, self._project, candidate_id, actor
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
                    for value in (
                        candidate.source_assertion_revision_id,
                        candidate.work_revision_id,
                        candidate.version_revision_id,
                        decision.policy_revision_id,
                        *((acquired[0],) if acquired is not None else ()),
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
                        dependency_kind="human-decision" if index >= 3 else "source-revision",
                        relation_type="direct",
                        revision_id=value.revision_id,
                        configuration_id=None,
                        configuration_version=None,
                        fingerprint=_projection_content_sha256(value),
                        governing_policy_id="dependency.material.v1",
                        governing_policy_version="1.0.0",
                    )
                    for index, value in enumerate(sources)
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
