"""Protected SQLite adapter for versioned project catalogs, audit and outbox."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
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
from .model_routing_contracts import CircuitState, RoutingEvent, RoutingRun
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


class SqliteModelRoutingRepository:
    """Append-only routing journal on the existing protected settings boundary.

    Request metadata is written once. Each later event is a separate bounded,
    chunked document with a predecessor hash and atomic provenance/outbox fact.
    This is model-attempt evidence, not a second workflow execution queue.
    """

    def __init__(self, database: Path, project_id: str, actor_id: str) -> None:
        if not database.is_absolute() or not project_id or not is_uuid_v7(actor_id):
            raise ValueError("routing repository principal is invalid")
        self._database = database
        self._project_id = project_id
        self._actor_id = actor_id
        self._connection: ContextVar[tuple[CanonicalConnection, tuple[int, object]] | None] = ContextVar(
            "model-routing-connection", default=None
        )
        self._atomic: ContextVar[bool] = ContextVar("model-routing-atomic", default=False)
        self._transaction_runs: ContextVar[dict[str, tuple[RoutingRun, dict, str]] | None] = ContextVar(
            "model-routing-transaction-runs", default=None
        )

    @staticmethod
    def _owner() -> tuple[int, object]:
        try:
            task = asyncio.current_task()
        except RuntimeError:
            task = None
        return threading.get_ident(), task

    @contextmanager
    def session(self):
        if self._connection.get() is not None:
            raise RepositoryConflict("routing connection session cannot be nested")
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project_id)
        except _FAILURES:
            raise RepositoryTransactionFailed("model routing persistence failed") from None
        token = self._connection.set((connection, self._owner()))
        try:
            yield
        finally:
            self._connection.reset(token)
            try:
                connection.close()
            except _FAILURES:
                raise RepositoryTransactionFailed("model routing persistence failed") from None

    @staticmethod
    def _control(connection: CanonicalConnection, statement: str) -> None:
        # Normalize only storage-boundary failures, not exceptions supplied by
        # the caller across a context manager's yield.
        try:
            connection.execute(statement)
        except _FAILURES:
            raise RepositoryTransactionFailed("model routing persistence failed") from None

    @contextmanager
    def atomic(self):
        bound = self._connection.get()
        if bound is None or bound[1] != self._owner() or self._atomic.get():
            raise RepositoryConflict("routing atomic scope requires its owning session")
        connection = bound[0]
        token = self._atomic.set(True)
        runs = self._transaction_runs.set({})
        try:
            self._control(connection, "BEGIN IMMEDIATE")
            yield
            self._control(connection, "COMMIT")
        except BaseException:
            if connection.in_transaction:
                self._control(connection, "ROLLBACK")
            raise
        finally:
            verified = self._transaction_runs.get()
            if verified is not None:
                verified.clear()
            self._transaction_runs.reset(runs)
            self._atomic.reset(token)

    def _transaction(self, operation, *, write: bool = False):
        try:
            bound = self._connection.get()
            if bound is not None and bound[1] != self._owner():
                raise RepositoryConflict("routing connection belongs to another execution context")
            connection = (
                bound[0]
                if bound is not None
                else open_canonical_database(self._database, expected_project_id=self._project_id)
            )
            if self._atomic.get():
                return operation(connection)
            try:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                result = operation(connection)
                connection.execute("COMMIT")
                return result
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                if bound is None:
                    connection.close()
        except RepositoryConflict:
            raise
        except _FAILURES:
            raise RepositoryTransactionFailed("model routing persistence failed") from None

    @staticmethod
    def _task_key(task_id: str) -> str:
        if not is_uuid_v7(task_id):
            raise ValueError("routing task identity is invalid")
        return "routing." + task_id

    def _latest(self, connection: CanonicalConnection, key: str) -> int:
        found = connection.execute(
            "SELECT MAX(revision) FROM settings WHERE project_id=? AND setting_key=?",
            (self._project_id, key + ".head"),
        ).fetchone()[0]
        if found is None:
            residue = connection.execute(
                "SELECT COUNT(*) FROM settings WHERE project_id=? AND setting_key>=? AND setting_key<?",
                (self._project_id, key + ".", key + "/"),
            ).fetchone()[0]
            if residue:
                raise ValueError("routing document header is missing")
            return 0
        return found

    def _read_document(self, connection: CanonicalConnection, key: str, revision: int) -> dict:
        rows = connection.execute(
            "SELECT setting_key, text_value, created_at FROM settings "
            "WHERE project_id=? AND setting_key>=? AND setting_key<? AND revision=? ORDER BY setting_key",
            (self._project_id, key + ".", key + "/", revision),
        ).fetchall()
        if not rows or len(rows) > 129 or rows[0][0] != key + ".head":
            raise ValueError("routing document inventory is invalid")
        header = json.loads(rows[0][1])
        if set(header) != {"parts", "sha256"} or canonical_bytes(header).decode() != rows[0][1]:
            raise ValueError("routing document header is invalid")
        if type(header["parts"]) is not int or not 1 <= header["parts"] <= 128 or len(rows) != header["parts"] + 1:
            raise ValueError("routing document part count is invalid")
        for index, (stored_key, text, stamp) in enumerate(rows[1:]):
            if stored_key != key + f".part.{index:04d}" or stamp != rows[0][2] or not isinstance(text, str):
                raise ValueError("routing document part identity is invalid")
        encoded = "".join(row[1] for row in rows[1:])
        if len(encoded) > 8_000_000:
            raise ValueError("routing document size is invalid")
        value = json.loads(encoded)
        canonical = canonical_bytes(value)
        if (
            not isinstance(value, dict)
            or canonical.decode() != encoded
            or "sha256:" + hashlib.sha256(canonical).hexdigest() != header["sha256"]
        ):
            raise ValueError("routing document bytes are invalid")
        return value

    def _write_document(
        self, connection: CanonicalConnection, key: str, revision: int, value: dict, stamp: str
    ) -> None:
        canonical = canonical_bytes(value)
        encoded = canonical.decode()
        if len(encoded) > 8_000_000:
            raise ValueError("routing document exceeds its bound")
        parts = [encoded[offset : offset + 64_000] for offset in range(0, len(encoded), 64_000)]
        header = canonical_bytes(
            {"parts": len(parts), "sha256": "sha256:" + hashlib.sha256(canonical).hexdigest()}
        ).decode()
        for suffix, content in [(".head", header), *((f".part.{index:04d}", part) for index, part in enumerate(parts))]:
            connection.execute(
                "INSERT INTO settings (setting_id, project_id, setting_key, revision, value_type, "
                "text_value, integer_value, real_value, boolean_value, created_at, modified_at) "
                "VALUES (?, ?, ?, ?, 'text', ?, NULL, NULL, NULL, ?, ?)",
                (new_uuid_v7(), self._project_id, key + suffix, revision, content, stamp, stamp),
            )

    @staticmethod
    def _stamp(milliseconds: int) -> str:
        return (
            datetime.fromtimestamp(milliseconds / 1000, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

    def _envelope(
        self,
        *,
        key: str,
        revision: int,
        payload: dict,
        previous_hash: str | None,
        event_id: str,
        occurred_at_ms: int,
        trace_id: str,
        event_type: str,
    ) -> dict:
        envelope = {
            "projectId": self._project_id,
            "key": key,
            "revision": revision,
            "payload": payload,
            "previousHash": previous_hash,
            "eventId": event_id,
            "outboxId": new_uuid_v7(),
            "actorId": self._actor_id,
            "occurredAt": self._stamp(occurred_at_ms),
            "traceId": trace_id,
            "eventType": event_type,
        }
        return envelope | {"recordHash": canonical_hash(envelope)}

    def _verify_envelope(self, connection: CanonicalConnection, envelope: dict, key: str, revision: int) -> None:
        expected = {
            "projectId",
            "key",
            "revision",
            "payload",
            "previousHash",
            "eventId",
            "outboxId",
            "actorId",
            "occurredAt",
            "traceId",
            "eventType",
            "recordHash",
        }
        if (
            set(envelope) != expected
            or (envelope["projectId"], envelope["key"], envelope["revision"]) != (self._project_id, key, revision)
            or envelope["recordHash"]
            != canonical_hash({name: value for name, value in envelope.items() if name != "recordHash"})
            or not is_uuid_v7(envelope["actorId"])
            or not is_uuid_v7(envelope["eventId"])
            or not is_uuid_v7(envelope["outboxId"])
        ):
            raise ValueError("routing envelope identity is invalid")
        audit = connection.execute(
            "SELECT event_type, occurred_at, trace_id, actor_type, actor_id, record_sha256 FROM provenance_events "
            "WHERE project_id=? AND event_id=?",
            (self._project_id, envelope["eventId"]),
        ).fetchone()
        outbox = connection.execute(
            "SELECT event_type, occurred_at, idempotency_key, record_sha256 FROM outbox_events "
            "WHERE project_id=? AND outbox_id=?",
            (self._project_id, envelope["outboxId"]),
        ).fetchone()
        if (
            audit is None
            or tuple(audit)
            != (
                envelope["eventType"],
                envelope["occurredAt"],
                envelope["traceId"],
                "system",
                envelope["actorId"],
                envelope["recordHash"][7:],
            )
            or outbox is None
            or tuple(outbox)
            != (
                envelope["eventType"],
                envelope["occurredAt"],
                f"{key}.{revision}",
                envelope["recordHash"][7:],
            )
        ):
            raise ValueError("routing audit binding is invalid")

    def _append_audit(self, connection: CanonicalConnection, envelope: dict) -> None:
        connection.execute(
            "INSERT INTO provenance_events (event_id, project_id, revision_id, event_type, occurred_at, "
            "trace_id, actor_type, actor_id, record_sha256) VALUES (?, ?, NULL, ?, ?, ?, 'system', ?, ?)",
            (
                envelope["eventId"],
                self._project_id,
                envelope["eventType"],
                envelope["occurredAt"],
                envelope["traceId"],
                envelope["actorId"],
                envelope["recordHash"][7:],
            ),
        )
        connection.execute(
            "INSERT INTO outbox_events (outbox_id, project_id, revision_id, event_type, occurred_at, available_at, "
            "state, attempt_count, published_at, idempotency_key, record_sha256) "
            "VALUES (?, ?, NULL, ?, ?, ?, 'pending', 0, NULL, ?, ?)",
            (
                envelope["outboxId"],
                self._project_id,
                envelope["eventType"],
                envelope["occurredAt"],
                envelope["occurredAt"],
                f"{envelope['key']}.{envelope['revision']}",
                envelope["recordHash"][7:],
            ),
        )

    def _read_run(self, connection: CanonicalConnection, task_id: str) -> tuple[RoutingRun, dict, str] | None:
        verified = self._transaction_runs.get()
        if verified is not None and task_id in verified:
            return verified[task_id]
        key = self._task_key(task_id)
        request_revision = self._latest(connection, key + ".request")
        latest = self._latest(connection, key + ".events")
        if request_revision == latest == 0:
            return None
        if request_revision != 1 or not 1 <= latest <= 64:
            raise ValueError("routing request/event sequence is invalid")
        metadata = self._read_document(connection, key + ".request", 1)
        trace_id = json.loads(metadata["taskJson"])["traceId"]
        request_hash = canonical_hash(metadata)
        events = []
        previous = None
        admission_actor = ""
        for revision in range(1, latest + 1):
            envelope = self._read_document(connection, key + ".events", revision)
            self._verify_envelope(connection, envelope, key + ".events", revision)
            if revision == 1:
                admission_actor = envelope["actorId"]
            payload = envelope["payload"]
            if (
                set(payload) != {"requestHash", "event"}
                or payload["requestHash"] != request_hash
                or envelope["previousHash"] != previous
            ):
                raise ValueError("routing predecessor or request binding is invalid")
            event = payload["event"]
            if (
                envelope["eventId"] != event["eventId"]
                or envelope["occurredAt"] != self._stamp(event["occurredAtMs"])
                or envelope["eventType"] != "model.routing." + event["kind"]
                or envelope["traceId"] != trace_id
            ):
                raise ValueError("routing event binding is invalid")
            previous = envelope["recordHash"]
            events.append(event)
        run = RoutingRun.model_validate(metadata | {"events": tuple(events)})
        if (
            run.project_id != self._project_id
            or run.task_id != task_id
            or envelope["traceId"] != json.loads(run.task_json)["traceId"]
        ):
            raise ValueError("routing project/task identity is invalid")
        return self._remember_run(run, envelope, admission_actor)

    def _remember_run(self, run: RoutingRun, envelope: dict, actor: str) -> tuple[RoutingRun, dict, str]:
        result = (run, envelope, actor)
        verified = self._transaction_runs.get()
        if verified is not None:
            # Only inside BEGIN IMMEDIATE: no competing writer can change these
            # validated bytes. Commit/rollback drops the entire memo; the next
            # transaction must reconstruct and authenticate persistent history.
            if run.task_id not in verified:
                verified.clear()
            verified[run.task_id] = result
        return result

    def read(self, task_id: str) -> RoutingRun | None:
        result = self._transaction(lambda connection: self._read_run(connection, task_id))
        return None if result is None else result[0]

    def admit(self, run: RoutingRun) -> tuple[RoutingRun, bool]:
        run = RoutingRun.model_validate(run)
        if run.project_id != self._project_id or run.revision != 1 or run.terminal:
            raise RepositoryConflict("routing admission authority is invalid")

        def append(connection: CanonicalConnection):
            key = self._task_key(run.task_id)
            prior = self._read_run(connection, run.task_id)
            if prior is not None:
                existing, _last, admission_actor = prior
                if (
                    existing.task_hash != run.task_hash
                    or existing.policy != run.policy
                    or admission_actor != self._actor_id
                ):
                    raise RepositoryIdempotencyConflict("routing request identity changed")
                return existing, False
            metadata = run.model_dump(by_alias=True, exclude={"events"})
            envelope = self._envelope(
                key=key + ".events",
                revision=1,
                payload={"requestHash": canonical_hash(metadata), "event": run.events[0].model_dump(by_alias=True)},
                previous_hash=None,
                event_id=run.events[0].event_id,
                occurred_at_ms=run.events[0].occurred_at_ms,
                trace_id=json.loads(run.task_json)["traceId"],
                event_type="model.routing.admitted",
            )
            self._write_document(connection, key + ".request", 1, metadata, envelope["occurredAt"])
            self._write_document(connection, key + ".events", 1, envelope, envelope["occurredAt"])
            self._append_audit(connection, envelope)
            self._remember_run(run, envelope, self._actor_id)
            return run, True

        return self._transaction(append, write=True)

    def append(self, task_id: str, *, expected_revision: int, event: RoutingEvent) -> RoutingRun:
        event = RoutingEvent.model_validate(event)
        if type(expected_revision) is not int or not 1 <= expected_revision < 64:
            raise RepositoryConflict("routing expected revision is invalid")

        def append(connection: CanonicalConnection):
            prior = self._read_run(connection, task_id)
            if prior is None or prior[0].revision != expected_revision or prior[0].terminal:
                raise RepositoryConflict("routing revision changed")
            run, predecessor, admission_actor = prior
            if admission_actor != self._actor_id:
                raise RepositoryConflict("routing admission principal differs")
            updated = RoutingRun.model_validate(run.model_dump() | {"events": (*run.events, event)})
            envelope = self._envelope(
                key=self._task_key(task_id) + ".events",
                revision=updated.revision,
                payload={
                    "requestHash": predecessor["payload"]["requestHash"],
                    "event": event.model_dump(by_alias=True),
                },
                previous_hash=predecessor["recordHash"],
                event_id=event.event_id,
                occurred_at_ms=event.occurred_at_ms,
                trace_id=json.loads(run.task_json)["traceId"],
                event_type="model.routing." + event.kind,
            )
            self._write_document(connection, envelope["key"], updated.revision, envelope, envelope["occurredAt"])
            self._append_audit(connection, envelope)
            self._remember_run(updated, envelope, admission_actor)
            return updated

        return self._transaction(append, write=True)

    def _circuit(self, connection: CanonicalConnection, manifest_hash: str) -> tuple[CircuitState, dict | None]:
        empty = CircuitState(manifest_hash=manifest_hash)
        key = "routing-circuit." + manifest_hash[7:]
        revision = self._latest(connection, key)
        if not revision:
            return empty, None
        envelope = self._read_document(connection, key, revision)
        self._verify_envelope(connection, envelope, key, revision)
        result = CircuitState.model_validate(envelope["payload"])
        if (
            result.manifest_hash != manifest_hash
            or result.revision != revision
            or envelope["eventType"] != "model.circuit.changed"
            or envelope["traceId"] != result.trace_id
        ):
            raise ValueError("routing circuit identity is invalid")
        if revision == 1:
            if envelope["previousHash"] is not None:
                raise ValueError("routing circuit predecessor is invalid")
        else:
            previous = self._read_document(connection, key, revision - 1)
            self._verify_envelope(connection, previous, key, revision - 1)
            if envelope["previousHash"] != previous["recordHash"]:
                raise ValueError("routing circuit predecessor differs")
        return result, envelope

    def circuit(self, manifest_hash: str) -> CircuitState:
        return self._transaction(lambda connection: self._circuit(connection, manifest_hash))[0]

    def change_circuit(
        self, state: CircuitState, *, expected_revision: int, expected_attempt_id: str | None = None
    ) -> CircuitState:
        state = CircuitState.model_validate(state)
        if type(expected_revision) is not int or state.revision != expected_revision + 1:
            raise RepositoryConflict("routing circuit expected revision is invalid")
        trace_id = state.trace_id
        if trace_id is None:
            raise RepositoryConflict("routing circuit trace identity is unavailable")

        def append(connection: CanonicalConnection):
            prior, predecessor = self._circuit(connection, state.manifest_hash)
            if prior.revision != expected_revision or prior.active_attempt_id != expected_attempt_id:
                raise RepositoryConflict("routing circuit revision changed")
            if state.active_attempt_id is not None:
                if prior.active_attempt_id is not None or (state.failures, state.open_until_ms) != (
                    prior.failures,
                    prior.open_until_ms,
                ):
                    raise RepositoryConflict("routing circuit reservation is invalid")
            elif (
                prior.active_attempt_id is None
                or predecessor is None
                or state.trace_id != prior.trace_id
                or predecessor["actorId"] != self._actor_id
            ):
                raise RepositoryConflict("routing circuit release authority is invalid")
            envelope = self._envelope(
                key="routing-circuit." + state.manifest_hash[7:],
                revision=state.revision,
                payload=state.model_dump(by_alias=True),
                previous_hash=None if predecessor is None else predecessor["recordHash"],
                event_id=new_uuid_v7(),
                occurred_at_ms=time.time_ns() // 1_000_000,
                trace_id=trace_id,
                event_type="model.circuit.changed",
            )
            self._write_document(connection, envelope["key"], state.revision, envelope, envelope["occurredAt"])
            self._append_audit(connection, envelope)
            return state

        return self._transaction(append, write=True)
