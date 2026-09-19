"""Short-transaction SQLAlchemy adapter over the protected canonical project DB.

Intake seals bind declared source identity and immutable chunk membership. Only
verified parser EOF under the exact durable attempt can certify complete parsing.
Cancelling a preview preserves its audit and object references, never shared bytes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import dialect

from .domain_contracts import is_uuid_v7
from .ingestion.import_drafts import ImportRights
from .ingestion.preview_records import StoredImportRecord
from .ingestion.reference_imports import PARSER_VERSION, ImportRecord, ImportSession, ImportSource
from .ingestion.source_chunks import CHUNK_BYTES, MAX_CHUNKS, MAX_SOURCE_BYTES, SourceChunk
from .ports.import_previews import ImportPreviewRepository, PreviewActor, PreviewCreate, PreviewProblem, PreviewState
from .ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference, WorkflowQueueProblem
from .repositories import _SqliteWorkflowQueueRepository
from .storage import CanonicalConnection, StorageProblem, _normalize_utc_millisecond, open_canonical_database

_DIALECT = dialect(paramstyle="named")
_TERMINAL = {"cancelled", "failed", "security-interrupted"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def _execute(connection: CanonicalConnection, sql: str, **parameters: Any):
    statement = text(sql).bindparams(**parameters).compile(dialect=_DIALECT)
    return connection.execute(str(statement), statement.params)


def _actor(actor: PreviewActor) -> PreviewActor:
    actor = PreviewActor.model_validate(actor)
    _normalize_utc_millisecond(actor.occurred_at)
    return actor


class _SqliteImportPreviewRepository:
    def __init__(self, database: Path, project_id: str):
        if not database.is_absolute():
            raise ValueError("preview-repository-path-invalid")
        self._database = database
        self._project = project_id
        self._queue = _SqliteWorkflowQueueRepository(database, project_id)

    @contextmanager
    def _transaction(self, preview_id: str | None, *, write: bool = False) -> Iterator[CanonicalConnection]:
        if preview_id is not None and not is_uuid_v7(preview_id):
            raise PreviewProblem("preview-identity-invalid")
        connection: CanonicalConnection | None = None
        failed = False
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project)
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except PreviewProblem:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        except (
            OSError,
            sqlite3.Error,
            StorageProblem,
            TypeError,
            ValueError,
            KeyError,
            IndexError,
            WorkflowQueueProblem,
        ):
            failed = True
            if connection is not None and connection.in_transaction:
                connection.rollback()
        finally:
            if connection is not None:
                connection.close()
        if failed:
            raise PreviewProblem("preview-persistence-failed")

    def _query(self, connection: CanonicalConnection, sql: str, preview_id: str, **parameters: Any):
        return _execute(connection, sql, project=self._project, preview=preview_id, **parameters)

    def _event(self, connection: CanonicalConnection, preview_id: str, event: str, actor: PreviewActor) -> None:
        actor = _actor(actor)
        self._query(
            connection,
            """
            INSERT INTO import_preview_events
            SELECT :preview, :project, COALESCE(MAX(sequence), 0) + 1, :event, :actor, :trace, :occurred
              FROM import_preview_events WHERE preview_id=:preview AND project_id=:project
        """,
            preview_id,
            event=event,
            actor=actor.actor_id,
            trace=actor.trace_id,
            occurred=actor.occurred_at,
        )

    def _read(self, connection: CanonicalConnection, preview_id: str) -> PreviewState:
        row = self._query(
            connection,
            """
            SELECT p.source_name, p.format_name, p.encoding, p.initial_rights_json,
                   (SELECT event_type FROM import_preview_events e
                     WHERE e.preview_id=p.preview_id AND e.project_id=p.project_id ORDER BY sequence DESC LIMIT 1),
                   s.source_sha256, s.manifest_sha256,
                   COALESCE(s.byte_length, (SELECT COALESCE(SUM(byte_length), 0) FROM import_source_chunks c
                     WHERE c.preview_id=p.preview_id AND c.project_id=p.project_id)),
                   COALESCE(s.chunk_count, (SELECT COUNT(*) FROM import_source_chunks c
                     WHERE c.preview_id=p.preview_id AND c.project_id=p.project_id)),
                   (SELECT rights_json FROM import_draft_revisions d
                     WHERE d.preview_id=p.preview_id AND d.project_id=p.project_id ORDER BY revision DESC LIMIT 1)
              FROM import_previews p LEFT JOIN import_source_seals s
                ON s.preview_id=p.preview_id AND s.project_id=p.project_id
             WHERE p.preview_id=:preview AND p.project_id=:project
        """,
            preview_id,
        ).fetchone()
        if row is None:
            raise PreviewProblem("preview-not-found")
        return PreviewState(
            project_id=self._project,
            preview_id=preview_id,
            source_name=row[0],
            format_name=row[1],
            encoding=row[2],
            rights=ImportRights.model_validate_json(row[9] or row[3]),
            state=row[4],
            source_sha256=row[5],
            manifest_sha256=row[6],
            byte_length=row[7],
            chunk_count=row[8],
        )

    @staticmethod
    def _active(state: PreviewState) -> None:
        if state.state in _TERMINAL:
            raise PreviewProblem("preview-closed")
        if not state.rights.permits("store") or not state.rights.permits("inspect"):
            raise PreviewProblem("preview-rights-denied")

    def read(self, preview_id: str) -> PreviewState:
        with self._transaction(preview_id) as connection:
            return self._read(connection, preview_id)

    def previews_page(self, *, after: str | None, limit: int) -> tuple[PreviewState, ...]:
        if type(limit) is not int or not 1 <= limit <= 25:
            raise PreviewProblem("preview-page-limit")
        with self._transaction(after) as connection:
            ids = _execute(
                connection,
                """
                SELECT preview_id FROM import_previews
                 WHERE project_id=:project AND (:after IS NULL OR preview_id>:after)
                 ORDER BY preview_id LIMIT :limit
            """,
                project=self._project,
                after=after,
                limit=limit,
            ).fetchall()
            return tuple(self._read(connection, row[0]) for row in ids)

    def create(self, command: PreviewCreate) -> PreviewState:
        command = PreviewCreate.model_validate(command)
        actor = _actor(command.actor)
        if not command.rights.permits("store") or not command.rights.permits("inspect"):
            raise PreviewProblem("preview-rights-denied")
        with self._transaction(command.preview_id, write=True) as connection:
            self._query(
                connection,
                """
                INSERT INTO import_previews VALUES
                (:preview, :project, :name, :format, :encoding, :rights, :actor, :trace, :created)
            """,
                command.preview_id,
                name=command.source_name,
                format=command.format_name,
                encoding=command.encoding,
                rights=command.rights.model_dump_json(by_alias=True),
                actor=actor.actor_id,
                trace=actor.trace_id,
                created=actor.occurred_at,
            )
            self._event(connection, command.preview_id, "created", actor)
            return self._read(connection, command.preview_id)

    def append_chunk(self, preview_id: str, *, ordinal: int, chunk: SourceChunk) -> None:
        if type(ordinal) is not int or not 1 <= ordinal <= MAX_CHUNKS:
            raise PreviewProblem("preview-chunk-order")
        chunk = SourceChunk(chunk.object_sha256, chunk.byte_length)
        with self._transaction(preview_id, write=True) as connection:
            state = self._read(connection, preview_id)
            self._active(state)
            if state.state != "created":
                raise PreviewProblem("preview-intake-sealed")
            prior = self._query(
                connection,
                """
                SELECT object_sha256, byte_length FROM import_source_chunks
                 WHERE preview_id=:preview AND project_id=:project AND ordinal=:ordinal
            """,
                preview_id,
                ordinal=ordinal,
            ).fetchone()
            if prior is not None:
                if tuple(prior) == (chunk.object_sha256, chunk.byte_length):
                    return
                raise PreviewProblem("preview-chunk-conflict")
            if ordinal != state.chunk_count + 1 or state.byte_length != state.chunk_count * CHUNK_BYTES:
                raise PreviewProblem("preview-chunk-order")
            metadata = _execute(
                connection,
                """
                SELECT byte_length, storage_state, protection_profile, retention_class FROM object_records
                 WHERE project_id=:project AND object_sha256=:digest
            """,
                project=self._project,
                digest=chunk.object_sha256,
            ).fetchone()
            if metadata is None or tuple(metadata) != (
                chunk.byte_length,
                "available",
                "project-encrypted-v1",
                "project-lifetime",
            ):
                raise PreviewProblem("preview-chunk-unavailable")
            self._query(
                connection,
                "INSERT INTO import_source_chunks VALUES (:preview, :project, :ordinal, :digest, :size)",
                preview_id,
                ordinal=ordinal,
                digest=chunk.object_sha256,
                size=chunk.byte_length,
            )

    def _chunks(self, connection: CanonicalConnection, preview_id: str) -> tuple[SourceChunk, ...]:
        rows = self._query(
            connection,
            """
            SELECT ordinal, object_sha256, byte_length FROM import_source_chunks
             WHERE preview_id=:preview AND project_id=:project ORDER BY ordinal
        """,
            preview_id,
        ).fetchall()
        if len(rows) > MAX_CHUNKS or any(row[0] != index + 1 for index, row in enumerate(rows)):
            raise PreviewProblem("preview-chunk-order")
        chunks = tuple(SourceChunk(row[1], row[2]) for row in rows)
        if any(chunk.byte_length != CHUNK_BYTES for chunk in chunks[:-1]):
            raise PreviewProblem("preview-chunk-order")
        return chunks

    def source_chunks(self, preview_id: str) -> tuple[SourceChunk, ...]:
        with self._transaction(preview_id) as connection:
            state = self._read(connection, preview_id)
            self._active(state)
            if state.source_sha256 is None:
                raise PreviewProblem("preview-intake-incomplete")
            chunks = self._chunks(connection, preview_id)
            if (
                self._manifest(preview_id, state.source_sha256, chunks) != state.manifest_sha256
                or sum(chunk.byte_length for chunk in chunks) != state.byte_length
                or len(chunks) != state.chunk_count
            ):
                raise PreviewProblem("preview-source-manifest-mismatch")
            return chunks

    def _manifest(self, preview_id: str, source_sha256: str, chunks: tuple[SourceChunk, ...]) -> str:
        return hashlib.sha256(
            _json(
                [
                    "import-source-chunks/1",
                    self._project,
                    preview_id,
                    source_sha256,
                    [[chunk.object_sha256, chunk.byte_length] for chunk in chunks],
                ]
            ).encode("ascii")
        ).hexdigest()

    def seal(
        self, preview_id: str, *, source_sha256: str, byte_length: int, chunk_count: int, actor: PreviewActor
    ) -> PreviewState:
        actor = _actor(actor)
        ImportSource("source", source_sha256)
        if (
            type(byte_length) is not int
            or not 0 <= byte_length <= MAX_SOURCE_BYTES
            or type(chunk_count) is not int
            or not 0 <= chunk_count <= MAX_CHUNKS
        ):
            raise PreviewProblem("preview-source-size")
        with self._transaction(preview_id, write=True) as connection:
            state = self._read(connection, preview_id)
            self._active(state)
            chunks = self._chunks(connection, preview_id)
            if sum(chunk.byte_length for chunk in chunks) != byte_length or len(chunks) != chunk_count:
                raise PreviewProblem("preview-source-size")
            manifest = self._manifest(preview_id, source_sha256, chunks)
            if state.source_sha256 is not None:
                if state.manifest_sha256 != manifest:
                    raise PreviewProblem("preview-source-conflict")
                return state
            if state.state != "created":
                raise PreviewProblem("preview-intake-closed")
            self._query(
                connection,
                """
                INSERT INTO import_source_seals VALUES
                (:preview, :project, :source, :manifest, :size, :count, :sealed)
            """,
                preview_id,
                source=source_sha256,
                manifest=manifest,
                size=byte_length,
                count=chunk_count,
                sealed=actor.occurred_at,
            )
            self._event(connection, preview_id, "source-sealed", actor)
            return self._read(connection, preview_id)

    def cancel(self, preview_id: str, *, actor: PreviewActor, security_interruption: bool = False) -> None:
        actor = _actor(actor)
        if type(security_interruption) is not bool:
            raise PreviewProblem("preview-cancel-kind-invalid")
        with self._transaction(preview_id, write=True) as connection:
            state = self._read(connection, preview_id)
            if state.state in _TERMINAL:
                return
            self._event(connection, preview_id, "security-interrupted" if security_interruption else "cancelled", actor)

    def _running(self, connection: CanonicalConnection, claim: WorkflowJobClaim, actor: PreviewActor) -> None:
        actor = _actor(actor)
        if actor.actor_id != claim.worker_id:
            raise PreviewProblem("preview-worker-actor-mismatch")
        self._queue._verify_attempt_capability(connection, claim)
        row = self._queue._lease_row(connection, claim, actor.occurred_at, states=("running",))
        if row[3] is not None or row[4] != "running":
            raise PreviewProblem("preview-worker-cancelled")

    def _attempt(self, connection: CanonicalConnection, preview_id: str, claim: WorkflowJobClaim) -> None:
        if (
            self._query(
                connection,
                """
            SELECT 1 FROM import_parse_attempts WHERE preview_id=:preview AND project_id=:project
              AND attempt_id=:attempt AND job_id=:job AND parser_version=:parser
        """,
                preview_id,
                attempt=claim.attempt_id,
                job=claim.job_id,
                parser=PARSER_VERSION,
            ).fetchone()
            is None
        ):
            raise PreviewProblem("preview-attempt-mismatch")

    def begin_parse(self, preview_id: str, *, claim: WorkflowJobClaim, actor: PreviewActor) -> None:
        with self._transaction(preview_id, write=True) as connection:
            self._running(connection, claim, actor)
            state = self._read(connection, preview_id)
            self._active(state)
            if state.source_sha256 is None or state.state not in {"source-sealed", "parse-started", "parse-completed"}:
                raise PreviewProblem("preview-source-not-runnable")
            if (
                self._manifest(preview_id, state.source_sha256, self._chunks(connection, preview_id))
                != state.manifest_sha256
            ):
                raise PreviewProblem("preview-source-manifest-mismatch")
            prior = self._query(
                connection,
                """
                SELECT attempt_id, job_id FROM import_parse_attempts
                 WHERE preview_id=:preview AND project_id=:project ORDER BY rowid DESC LIMIT 1
            """,
                preview_id,
            ).fetchone()
            if prior is not None:
                if prior[1] != claim.job_id:
                    raise PreviewProblem("preview-job-substitution")
                if prior[0] == claim.attempt_id:
                    return
            self._query(
                connection,
                """
                INSERT INTO import_parse_attempts VALUES (:preview, :project, :attempt, :job, :parser, :started)
            """,
                preview_id,
                attempt=claim.attempt_id,
                job=claim.job_id,
                parser=PARSER_VERSION,
                started=actor.occurred_at,
            )
            self._event(connection, preview_id, "parse-started", actor)

    def append_records(
        self, preview_id: str, *, claim: WorkflowJobClaim, records: tuple[ImportRecord, ...], actor: PreviewActor
    ) -> None:
        if not isinstance(records, tuple) or not 1 <= len(records) <= 100:
            raise PreviewProblem("preview-record-batch-limit")
        with self._transaction(preview_id, write=True) as connection:
            self._running(connection, claim, actor)
            state = self._read(connection, preview_id)
            self._active(state)
            self._attempt(connection, preview_id, claim)
            if state.state != "parse-started" or state.source_sha256 is None:
                raise PreviewProblem("preview-parse-closed")
            total_bytes = 0
            for record in records:
                if (
                    record.source != ImportSource(state.source_name, state.source_sha256, state.encoding)
                    or record.format_name != state.format_name
                    or record.byte_end > state.byte_length
                ):
                    raise PreviewProblem("preview-record-source-mismatch")
                payload = StoredImportRecord.from_record(record).model_dump_json(by_alias=True)
                total_bytes += len(payload.encode("utf-8"))
                if total_bytes > 8 * 1024 * 1024:
                    raise PreviewProblem("preview-record-batch-limit")
                self._query(
                    connection,
                    """
                    INSERT INTO import_parse_records VALUES (:preview, :project, :attempt, :ordinal, :key, :record)
                """,
                    preview_id,
                    attempt=claim.attempt_id,
                    ordinal=record.ordinal,
                    key=record.record_key,
                    record=payload,
                )

    def finish_parse(
        self,
        preview_id: str,
        *,
        claim: WorkflowJobClaim,
        session: ImportSession,
        receipt_revision_id: str,
        actor: PreviewActor,
    ) -> WorkflowOutputReference:
        if not session.complete or not is_uuid_v7(receipt_revision_id):
            raise PreviewProblem("preview-parse-incomplete")
        with self._transaction(preview_id, write=True) as connection:
            self._running(connection, claim, actor)
            state = self._read(connection, preview_id)
            self._active(state)
            self._attempt(connection, preview_id, claim)
            if (
                state.state != "parse-started"
                or state.source_sha256 is None
                or session.source != ImportSource(state.source_name, state.source_sha256, state.encoding)
                or session.format_name != state.format_name
            ):
                raise PreviewProblem("preview-parse-source-mismatch")
            receipt = _execute(
                connection,
                """
                SELECT r.aggregate_id, e.content_hash FROM aggregate_revisions r
                  JOIN provenance_ledger_entities e ON e.project_id=r.project_id AND e.revision_id=r.revision_id
                  JOIN material_dependency_outputs m ON m.project_id=r.project_id AND m.output_revision_id=r.revision_id
                 WHERE r.project_id=:project AND r.revision_id=:revision AND r.aggregate_kind='workflow'
                   AND r.knowledge_status='observed' AND e.direction='output' AND m.coverage='complete'
                   AND EXISTS (SELECT 1 FROM material_dependencies d WHERE d.project_id=r.project_id
                     AND d.output_revision_id=r.revision_id AND d.dependency_kind='parameter-set'
                     AND d.configuration_id='import.source-manifest' AND d.configuration_version='1.0.0'
                     AND d.fingerprint=:manifest)
            """,
                project=self._project,
                revision=receipt_revision_id,
                manifest="sha256:" + str(state.manifest_sha256),
            ).fetchone()
            if receipt is None:
                raise PreviewProblem("preview-receipt-authority-mismatch")
            count = self._query(
                connection,
                """
                SELECT COUNT(*) FROM import_parse_records WHERE preview_id=:preview AND project_id=:project
                  AND attempt_id=:attempt
            """,
                preview_id,
                attempt=claim.attempt_id,
            ).fetchone()[0]
            if count != session.record_count:
                raise PreviewProblem("preview-record-count-mismatch")
            self._query(
                connection,
                """
                INSERT INTO import_parse_completions VALUES
                (:preview, :project, :attempt, :receipt, :count, :source, :completed)
            """,
                preview_id,
                attempt=claim.attempt_id,
                receipt=receipt_revision_id,
                count=count,
                source=state.source_sha256,
                completed=actor.occurred_at,
            )
            self._event(connection, preview_id, "parse-completed", actor)
            return WorkflowOutputReference(
                artifact_id=receipt[0],
                revision_id=receipt_revision_id,
                content_hash=receipt[1],
                media_type="application/json",
                provenance_entity_id=receipt[0],
            )

    def _accepted_attempt(self, connection: CanonicalConnection, preview_id: str) -> str:
        row = self._query(
            connection,
            """
            SELECT p.attempt_id, c.receipt_revision_id, o.output_manifest_json
              FROM import_parse_attempts p
              JOIN import_parse_completions c ON c.preview_id=p.preview_id AND c.project_id=p.project_id
                AND c.attempt_id=p.attempt_id
              JOIN workflow_queue_jobs j ON j.job_id=p.job_id AND j.project_id=p.project_id
                AND j.current_attempt_id=p.attempt_id
              JOIN workflow_job_attempts a ON a.attempt_id=p.attempt_id
                AND a.project_id=p.project_id AND a.job_id=p.job_id
              JOIN workflow_committed_outputs o ON o.job_id=p.job_id
                AND o.project_id=p.project_id AND o.attempt_id=p.attempt_id
             WHERE p.preview_id=:preview AND p.project_id=:project AND j.state='succeeded' AND a.state='succeeded'
               AND j.cancellation_requested_at IS NULL
        """,
            preview_id,
        ).fetchone()
        if row is None or not any(item.get("revisionId") == row[1] for item in json.loads(row[2])["outputs"]):
            raise PreviewProblem("preview-not-accepted")
        return str(row[0])

    def _record_access(self, connection: CanonicalConnection, preview_id: str, ordinal: int) -> None:
        """Draft adapter extends current rights checks inside the same read snapshot."""

    def records_page(self, preview_id: str, *, after: int, limit: int) -> tuple[ImportRecord, ...]:
        if type(after) is not int or not 0 <= after <= 200000 or type(limit) is not int or not 1 <= limit <= 100:
            raise PreviewProblem("preview-page-limit")
        with self._transaction(preview_id) as connection:
            state = self._read(connection, preview_id)
            self._active(state)
            attempt = self._accepted_attempt(connection, preview_id)
            if state.source_sha256 is None:
                raise PreviewProblem("preview-source-missing")
            cursor = self._query(
                connection,
                """
                SELECT record_key, record_json FROM import_parse_records
                 WHERE preview_id=:preview AND project_id=:project AND attempt_id=:attempt AND ordinal>:after
                 ORDER BY ordinal LIMIT :limit
            """,
                preview_id,
                attempt=attempt,
                after=after,
                limit=limit,
            )
            rows: list[Any] = []
            byte_count = 0
            try:
                while row := cursor.fetchone():
                    size = len(row[1].encode("utf-8"))
                    if byte_count + size > 8 * 1024 * 1024:
                        if not rows:
                            raise PreviewProblem("preview-record-size")
                        break
                    rows.append(row)
                    byte_count += size
            finally:
                cursor.close()
            records = tuple(
                StoredImportRecord.model_validate_json(row[1]).restore(
                    ImportSource(state.source_name, state.source_sha256, state.encoding), state.format_name
                )
                for row in rows
            )
            if any(record.record_key != row[0] for record, row in zip(records, rows, strict=True)):
                raise PreviewProblem("preview-record-identity-mismatch")
            for record in records:
                self._record_access(connection, preview_id, record.ordinal)
            return records


def sqlite_import_preview_repository(path: Path, project_id: str) -> ImportPreviewRepository:
    # Compose draft operations over the same intake adapter, without a second DB.
    from .import_draft_repository import SqliteImportDraftRepository

    return SqliteImportDraftRepository(path, project_id)
