"""Protected SQLite adapter for versioned project catalogs, audit and outbox."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .model_registry_contracts import (
    ModelCatalogRecord,
    ModelCatalogSummary,
    ModelManifest,
    ModelRegistryCatalog,
    canonical_bytes,
    canonical_hash,
)
from .ports.repositories import RepositoryConflict, RepositoryIdempotencyConflict, RepositoryTransactionFailed
from .storage import CanonicalConnection, StorageProblem, open_canonical_database

_CATALOG_KEY = "models.catalog"
_MANIFEST_PREFIX = "models.manifest."
_EVENT = "models.catalog.refreshed"
_FAILURES = (OSError, sqlite3.Error, StorageProblem, ValueError, TypeError, KeyError, IndexError)


class SqliteModelCatalogRepository:
    def __init__(self, database: Path, project_id: str) -> None:
        if not database.is_absolute() or not project_id:
            raise ValueError("model catalog repository authority is invalid")
        self._database = database
        self._project_id = project_id

    def _open(self) -> CanonicalConnection:
        return open_canonical_database(self._database, expected_project_id=self._project_id)

    def read(self, *, revision: int | None = None) -> ModelCatalogRecord | None:
        if revision is not None and (type(revision) is not int or revision < 1):
            raise ValueError("catalog revision is invalid")
        try:
            connection = self._open()
            try:
                connection.execute("BEGIN")
                result = self._read(connection, revision)
                connection.execute("COMMIT")
                return result
            finally:
                connection.close()
        except _FAILURES:
            raise RepositoryTransactionFailed("model catalog read failed") from None

    def _read(self, connection: CanonicalConnection, revision: int | None) -> ModelCatalogRecord | None:
        if revision is None:
            revision = connection.execute(
                "SELECT MAX(revision) FROM settings WHERE project_id=? AND setting_key=?",
                (self._project_id, _CATALOG_KEY),
            ).fetchone()[0]
            if revision is None:
                residue = connection.execute(
                    "SELECT COUNT(*) FROM settings WHERE project_id=? AND setting_key LIKE 'models.%'",
                    (self._project_id,),
                ).fetchone()[0]
                if residue:
                    raise ValueError("catalog header is missing")
                return None
        rows = connection.execute(
            "SELECT setting_key, text_value, created_at FROM settings "
            "WHERE project_id=? AND revision=? AND setting_key LIKE 'models.%' ORDER BY setting_key",
            (self._project_id, revision),
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1001 or rows[0][0] != _CATALOG_KEY:
            raise ValueError("catalog row inventory is invalid")
        header_text = rows[0][1]
        header = json.loads(header_text)
        if not isinstance(header, dict) or canonical_bytes(header).decode() != header_text or "manifests" in header:
            raise ValueError("catalog header is not canonical")
        manifests = []
        for key, text, timestamp in rows[1:]:
            manifest = ModelManifest.model_validate_json(text)
            if (
                key != _MANIFEST_PREFIX + manifest.manifest_id
                or canonical_bytes(manifest).decode() != text
                or timestamp != header["occurredAt"]
            ):
                raise ValueError("manifest binding is invalid")
            manifests.append(manifest)
        record = ModelCatalogRecord.model_validate(header | {"manifests": tuple(manifests)})
        if (record.project_id, record.revision, record.occurred_at) != (self._project_id, revision, rows[0][2]):
            raise ValueError("catalog identity is invalid")
        if revision > 1:
            predecessor = connection.execute(
                "SELECT text_value FROM settings WHERE project_id=? AND setting_key=? AND revision=?",
                (self._project_id, _CATALOG_KEY, revision - 1),
            ).fetchone()
            if predecessor is None or json.loads(predecessor[0])["recordHash"] != record.previous_hash:
                raise ValueError("catalog predecessor binding is invalid")
        audit = connection.execute(
            "SELECT event_type, occurred_at, trace_id, actor_type, actor_id, record_sha256 FROM provenance_events "
            "WHERE project_id=? AND event_id=?",
            (self._project_id, record.event_id),
        ).fetchone()
        outbox = connection.execute(
            "SELECT event_type, occurred_at, idempotency_key, record_sha256 FROM outbox_events "
            "WHERE project_id=? AND outbox_id=?",
            (self._project_id, record.outbox_id),
        ).fetchone()
        if audit is None or tuple(audit) != (
            _EVENT,
            record.occurred_at,
            record.trace_id,
            "human",
            record.actor_id,
            record.record_hash[7:],
        ):
            raise ValueError("catalog audit binding is invalid")
        if outbox is None or tuple(outbox) != (
            _EVENT,
            record.occurred_at,
            self._outbox_key(record.request_key_hash),
            record.command_hash[7:],
        ):
            raise ValueError("catalog outbox binding is invalid")
        return record

    def history(self, *, before_revision: int | None = None, limit: int = 20) -> tuple[ModelCatalogSummary, ...]:
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("catalog history limit is invalid")
        if before_revision is not None and (type(before_revision) is not int or before_revision < 1):
            raise ValueError("catalog history cursor is invalid")
        try:
            connection = self._open()
            try:
                connection.execute("BEGIN")
                self._read(connection, None)
                revisions = connection.execute(
                    "SELECT revision FROM settings WHERE project_id=? AND setting_key=? AND revision<? "
                    "ORDER BY revision DESC LIMIT ?",
                    (self._project_id, _CATALOG_KEY, before_revision or 2**31, limit),
                ).fetchall()
                summaries = []
                for (revision,) in revisions:
                    record = self._read(connection, revision)
                    if record is None:
                        raise ValueError("catalog history is incomplete")
                    summaries.append(
                        ModelCatalogSummary(
                            revision=record.revision,
                            catalog_hash=record.catalog_hash,
                            record_hash=record.record_hash,
                            previous_hash=record.previous_hash,
                            occurred_at=record.occurred_at,
                            model_count=len(record.manifests),
                        )
                    )
                connection.execute("COMMIT")
                return tuple(summaries)
            finally:
                connection.close()
        except _FAILURES:
            raise RepositoryTransactionFailed("model catalog history failed") from None

    def append(
        self,
        *,
        expected_revision: int,
        manifests: tuple[ModelManifest, ...],
        actor_id: str,
        idempotency_key: str,
        trace_id: str,
        occurred_at: str,
    ) -> ModelCatalogRecord:
        if (
            type(expected_revision) is not int
            or not 0 <= expected_revision < 2**31 - 1
            or not is_uuid_v7(actor_id)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", idempotency_key)
        ):
            raise ValueError("model catalog command authority is invalid")
        catalog = ModelRegistryCatalog(
            project_id=self._project_id,
            revision=expected_revision + 1,
            manifests=manifests,
        )
        request_key_hash = canonical_hash({"projectId": self._project_id, "actorId": actor_id, "key": idempotency_key})
        command_hash = canonical_hash({"catalog": catalog, "actorId": actor_id, "requestKeyHash": request_key_hash})
        try:
            connection = self._open()
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._read(connection, None)
                replay = connection.execute(
                    "SELECT record_sha256 FROM outbox_events WHERE project_id=? AND idempotency_key=?",
                    (self._project_id, self._outbox_key(request_key_hash)),
                ).fetchone()
                if replay is not None:
                    if replay[0] != command_hash[7:]:
                        raise RepositoryIdempotencyConflict("catalog command identity changed")
                    record = self._read(connection, expected_revision + 1)
                    if (
                        record is None
                        or record.command_hash != command_hash
                        or record.request_key_hash != request_key_hash
                    ):
                        raise ValueError("catalog replay binding is invalid")
                    connection.execute("COMMIT")
                    return record
                if (0 if current is None else current.revision) != expected_revision:
                    raise RepositoryConflict("catalog revision changed")
                # Compare each manifest with its latest historical occurrence,
                # including entries absent from the current catalog.
                prior_rows = connection.execute(
                    "SELECT s.setting_key, s.text_value FROM settings s JOIN "
                    "(SELECT setting_key, MAX(revision) AS latest FROM settings WHERE project_id=? "
                    "AND setting_key LIKE 'models.manifest.%' GROUP BY setting_key) p "
                    "ON s.setting_key=p.setting_key AND s.revision=p.latest WHERE s.project_id=?",
                    (self._project_id, self._project_id),
                ).fetchall()
                prior = {key: ModelManifest.model_validate_json(value) for key, value in prior_rows}
                for manifest in catalog.manifests:
                    previous = prior.get(_MANIFEST_PREFIX + manifest.manifest_id)
                    if previous is not None and (
                        manifest.revision < previous.revision
                        or (manifest.revision == previous.revision and manifest != previous)
                    ):
                        raise RepositoryConflict("manifest revision must advance when metadata changes")
                header = {
                    "projectId": self._project_id,
                    "revision": catalog.revision,
                    "catalogHash": canonical_hash(catalog),
                    "previousHash": None if current is None else current.record_hash,
                    "actorId": actor_id,
                    "eventId": new_uuid_v7(),
                    "outboxId": new_uuid_v7(),
                    "occurredAt": occurred_at,
                    "traceId": trace_id,
                    "commandHash": command_hash,
                    "requestKeyHash": request_key_hash,
                }
                record = ModelCatalogRecord.model_validate(
                    header
                    | {
                        "recordHash": canonical_hash(header),
                        "manifests": catalog.manifests,
                    }
                )
                self._insert(
                    connection,
                    _CATALOG_KEY,
                    record.revision,
                    canonical_bytes(record.model_dump(by_alias=True, exclude={"manifests"})).decode(),
                    occurred_at,
                )
                for manifest in record.manifests:
                    self._insert(
                        connection,
                        _MANIFEST_PREFIX + manifest.manifest_id,
                        record.revision,
                        canonical_bytes(manifest).decode(),
                        occurred_at,
                    )
                self._append_events(connection, record)
                connection.execute("COMMIT")
                return record
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
        except RepositoryConflict:
            raise
        except _FAILURES:
            raise RepositoryTransactionFailed("model catalog append failed") from None

    def _insert(self, connection: CanonicalConnection, key: str, revision: int, text: str, stamp: str) -> None:
        connection.execute(
            "INSERT INTO settings (setting_id, project_id, setting_key, revision, value_type, "
            "text_value, integer_value, real_value, boolean_value, created_at, modified_at) "
            "VALUES (?, ?, ?, ?, 'text', ?, NULL, NULL, NULL, ?, ?)",
            (new_uuid_v7(), self._project_id, key, revision, text, stamp, stamp),
        )

    @staticmethod
    def _outbox_key(request_key_hash: str) -> str:
        return "models.catalog." + request_key_hash[7:]

    def _append_events(self, connection: CanonicalConnection, record: ModelCatalogRecord) -> None:
        connection.execute(
            "INSERT INTO provenance_events (event_id, project_id, revision_id, event_type, occurred_at, "
            "trace_id, actor_type, actor_id, record_sha256) VALUES (?, ?, NULL, ?, ?, ?, 'human', ?, ?)",
            (
                record.event_id,
                self._project_id,
                _EVENT,
                record.occurred_at,
                record.trace_id,
                record.actor_id,
                record.record_hash[7:],
            ),
        )
        connection.execute(
            "INSERT INTO outbox_events (outbox_id, project_id, revision_id, event_type, occurred_at, "
            "available_at, state, attempt_count, published_at, idempotency_key, record_sha256) "
            "VALUES (?, ?, NULL, ?, ?, ?, 'pending', 0, NULL, ?, ?)",
            (
                record.outbox_id,
                self._project_id,
                _EVENT,
                record.occurred_at,
                record.occurred_at,
                self._outbox_key(record.request_key_hash),
                record.command_hash[7:],
            ),
        )


def sqlite_model_catalog_repository(path: Path, project_id: str) -> SqliteModelCatalogRepository:
    return SqliteModelCatalogRepository(path / "state/project.sqlite3", project_id)
