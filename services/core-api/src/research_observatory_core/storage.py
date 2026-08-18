"""Versioned local SQLite profile, schema, connection, and integrity boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from research_observatory_core.migrations.versions.v0002_schema_history import (
    SCHEMA_METADATA_V2_DDL,
    SCHEMA_MIGRATIONS_DDL,
    SCHEMA_MIGRATIONS_TRIGGERS,
)

APPLICATION_ID = 0x524F4253  # ASCII "ROBS"
DATABASE_PROFILE = "sqlite-wal-v1"
DATABASE_SCHEMA_VERSION = 2
PREVIOUS_DATABASE_SCHEMA_VERSION = 1
BUSY_TIMEOUT_MILLISECONDS = 5_000
WAL_AUTOCHECKPOINT_PAGES = 1_000
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MINIMUM_SQLITE_VERSION = (3, 37, 0)

EXPECTED_TABLES = (
    "schema_metadata",
    "schema_migrations",
    "projects",
    "object_records",
    "aggregate_identities",
    "aggregate_revisions",
    "scholarly_records",
    "documents",
    "workflows",
    "evidence",
    "ontologies",
    "decisions",
    "provenance_events",
    "settings",
    "outbox_events",
)
IMMUTABLE_ROW_TABLES = (
    "schema_metadata",
    "schema_migrations",
    "projects",
    "aggregate_identities",
    "aggregate_revisions",
    "scholarly_records",
    "documents",
    "workflows",
    "evidence",
    "ontologies",
    "decisions",
    "provenance_events",
    "settings",
)
MUTABLE_STATE_TABLES = ("object_records", "outbox_events")
EXPECTED_TRIGGERS = tuple(
    sorted(f"{table}_no_{operation}" for table in IMMUTABLE_ROW_TABLES for operation in ("delete", "update"))
)
EXPECTED_INDEXES = (
    "aggregate_revisions_project_kind",
    "outbox_events_dispatch",
    "provenance_events_project_time",
)
PREVIOUS_SCHEMA_SHA256 = "61e5693187250e240f9b6cae573e3b89752ae9b135c6c739d14ff3dfbf6dfdc9"
PREVIOUS_PROFILE_SHA256 = "fcd3ee269f5d80ce4b554ffc4578d0d16cd941b4afecea19f8860197a77bd1c0"
EXPECTED_SCHEMA_SHA256 = "afd48fbe857de4172215e9cb61a0f6137e73edec685dcc116bedbb66eb519dda"

_PROFILE_DOCUMENT: dict[str, Any] = {
    "schemaVersion": "1.0",
    "documentType": "research-observatory-sqlite-profile",
    "profileId": DATABASE_PROFILE,
    "databaseSchemaVersion": DATABASE_SCHEMA_VERSION,
    "applicationId": APPLICATION_ID,
    "schemaFingerprintSha256": EXPECTED_SCHEMA_SHA256,
    "minimumSqliteVersion": "3.37.0",
    "identifierStorage": {
        "project": "uuid4-bridge-or-uuid7-lowercase-text",
        "aggregate": "uuid7-lowercase-text",
        "revision": "uuid7-lowercase-text",
        "event": "uuid7-lowercase-text",
        "setting": "uuid7-lowercase-text",
    },
    "timestampStorage": "utc-rfc3339-millisecond-text",
    "canonicalColumnTypes": ["INTEGER", "REAL", "TEXT"],
    "derivedBinaryStorage": "digest-reference-only",
    "immutableRowTables": list(IMMUTABLE_ROW_TABLES),
    "mutableStateTables": list(MUTABLE_STATE_TABLES),
    "connectionProfile": {
        "foreignKeys": True,
        "journalMode": "wal",
        "synchronous": "full",
        "busyTimeoutMilliseconds": BUSY_TIMEOUT_MILLISECONDS,
        "trustedSchema": False,
        "defensive": True,
        "doubleQuotedStringLiterals": False,
        "loadableExtensions": False,
        "recursiveTriggers": True,
        "walAutocheckpointPages": WAL_AUTOCHECKPOINT_PAGES,
        "lockingMode": "normal",
        "schemaChanges": "dedicated-backed-up-migration-connection-only",
    },
    "checkpointPolicy": {
        "automaticMode": "passive",
        "automaticPages": WAL_AUTOCHECKPOINT_PAGES,
        "manualAuthority": "migration-backup-and-maintenance-only",
    },
    "integrityChecks": ["quick_check", "foreign_key_check", "strict_table_inventory"],
    "canonicalTables": list(EXPECTED_TABLES),
}
_PROFILE_SHA256 = hashlib.sha256(
    json.dumps(_PROFILE_DOCUMENT, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
EXPECTED_PROFILE_SHA256 = "29454c72d0b357c2ece14a8991db57bfb87414d7ade85d1a2e8048a648a17cc2"
if _PROFILE_SHA256 != EXPECTED_PROFILE_SHA256:
    raise RuntimeError("compiled SQLite profile differs from its reviewed fingerprint")

_UTC_INPUT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$")


class StorageProblem(RuntimeError):
    """Bounded local storage failure without project content or path disclosure."""


class _GuardedConnection(sqlite3.Connection):
    """Internal SQLite handle retaining file and directory identity guards."""

    _guard_handles: list[int]
    _guard_descriptor: int | None

    def close(self) -> None:
        try:
            super().close()
        finally:
            descriptor = getattr(self, "_guard_descriptor", None)
            if descriptor is not None:
                self._guard_descriptor = None
                os.close(descriptor)
            handles = getattr(self, "_guard_handles", [])
            self._guard_handles = []
            _close_windows_handles(handles)


@dataclass(frozen=True, slots=True)
class _CursorEntry:
    connection_token: str
    cursor: sqlite3.Cursor


class _CapabilityRegistry:
    """Module-owned raw SQLite authority, never returned to ordinary callers."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: dict[str, _GuardedConnection] = {}
        self._cursors: dict[str, _CursorEntry] = {}

    def _token(self) -> str:
        while True:
            token = secrets.token_hex(32)
            if token not in self._connections and token not in self._cursors:
                return token

    def register_connection(self, connection: _GuardedConnection) -> str:
        with self._lock:
            token = self._token()
            self._connections[token] = connection
            return token

    def connection(self, token: str | None) -> _GuardedConnection:
        if token is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        with self._lock:
            connection = self._connections.get(token)
        if connection is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        return connection

    def close_connection(self, token: str | None) -> None:
        if token is None:
            return
        with self._lock:
            connection = self._connections.pop(token, None)
            cursors = [cursor_token for cursor_token, entry in self._cursors.items() if entry.connection_token == token]
            entries = [self._cursors.pop(cursor_token) for cursor_token in cursors]
        for entry in entries:
            with suppress(sqlite3.Error):
                entry.cursor.close()
        if connection is not None:
            connection.close()

    def register_cursor(self, connection_token: str, cursor: sqlite3.Cursor) -> str:
        with self._lock:
            if connection_token not in self._connections:
                cursor.close()
                raise sqlite3.ProgrammingError("canonical connection is closed")
            token = self._token()
            self._cursors[token] = _CursorEntry(connection_token=connection_token, cursor=cursor)
            return token

    def cursor(self, token: str | None) -> sqlite3.Cursor:
        if token is None:
            raise sqlite3.ProgrammingError("canonical cursor is closed")
        with self._lock:
            entry = self._cursors.get(token)
        if entry is None:
            raise sqlite3.ProgrammingError("canonical cursor is closed")
        return entry.cursor

    def close_cursor(self, token: str | None) -> None:
        if token is None:
            return
        with self._lock:
            entry = self._cursors.pop(token, None)
        if entry is not None:
            with suppress(sqlite3.Error):
                entry.cursor.close()


_CAPABILITY_REGISTRY = _CapabilityRegistry()


class CanonicalCursor:
    """Restricted result cursor carrying only an opaque registry token and metadata."""

    __slots__ = ("__description", "__lastrowid", "__rowcount", "__token")

    def __init__(
        self,
        token: str | None,
        *,
        description: tuple[Any, ...] | None,
        lastrowid: int | None,
        rowcount: int,
    ) -> None:
        self.__token = token
        self.__description = description
        self.__lastrowid = lastrowid
        self.__rowcount = rowcount

    def __iter__(self) -> CanonicalCursor:
        return self

    def __next__(self) -> Any:
        try:
            return next(_CAPABILITY_REGISTRY.cursor(self.__token))
        except StopIteration:
            self.close()
            raise

    def fetchone(self) -> Any:
        row = _CAPABILITY_REGISTRY.cursor(self.__token).fetchone()
        if row is None:
            self.close()
        return row

    def fetchmany(self, size: int | None = None) -> list[Any]:
        cursor = _CAPABILITY_REGISTRY.cursor(self.__token)
        rows = cursor.fetchmany() if size is None else cursor.fetchmany(size)
        if not rows:
            self.close()
        return rows

    def fetchall(self) -> list[Any]:
        try:
            return _CAPABILITY_REGISTRY.cursor(self.__token).fetchall()
        finally:
            self.close()

    def close(self) -> None:
        token = self.__token
        self.__token = None
        _CAPABILITY_REGISTRY.close_cursor(token)

    @property
    def description(self) -> tuple[Any, ...] | None:
        return self.__description

    @property
    def lastrowid(self) -> int | None:
        return self.__lastrowid

    @property
    def rowcount(self) -> int:
        return self.__rowcount

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


def _restricted_cursor(connection_token: str, cursor: sqlite3.Cursor) -> CanonicalCursor:
    description = cursor.description
    lastrowid = cursor.lastrowid
    rowcount = cursor.rowcount
    token: str | None = None
    if description is None:
        cursor.close()
    else:
        token = _CAPABILITY_REGISTRY.register_cursor(connection_token, cursor)
    return CanonicalCursor(token, description=description, lastrowid=lastrowid, rowcount=rowcount)


class CanonicalConnection:
    """Restricted ordinary database capability carrying only an opaque registry token."""

    __slots__ = ("__token",)

    def __init__(self, token: str) -> None:
        self.__token: str | None = token

    def execute(self, sql: str, parameters: Any = ()) -> CanonicalCursor:
        token = self.__token
        if token is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        connection = _CAPABILITY_REGISTRY.connection(token)
        return _restricted_cursor(token, connection.execute(sql, parameters))

    def executemany(self, sql: str, parameters: Any) -> CanonicalCursor:
        token = self.__token
        if token is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        connection = _CAPABILITY_REGISTRY.connection(token)
        return _restricted_cursor(token, connection.executemany(sql, parameters))

    def commit(self) -> None:
        _CAPABILITY_REGISTRY.connection(self.__token).commit()

    def rollback(self) -> None:
        _CAPABILITY_REGISTRY.connection(self.__token).rollback()

    @property
    def in_transaction(self) -> bool:
        return _CAPABILITY_REGISTRY.connection(self.__token).in_transaction

    def close(self) -> None:
        token = self.__token
        self.__token = None
        _CAPABILITY_REGISTRY.close_connection(token)

    def __enter__(self) -> CanonicalConnection:
        _CAPABILITY_REGISTRY.connection(self.__token)
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


@dataclass(frozen=True, slots=True)
class DatabaseIntegrityReport:
    ok: bool
    profile_id: str | None
    schema_version: int | None
    application_id: int | None
    journal_mode: str | None
    foreign_keys: bool | None
    strict_tables: tuple[str, ...]
    quick_check: tuple[str, ...]
    foreign_key_violations: tuple[tuple[Any, ...], ...]
    errors: tuple[str, ...]


def storage_profile_document() -> dict[str, Any]:
    """Return a detached JSON-compatible copy of the portable profile."""

    return json.loads(json.dumps(_PROFILE_DOCUMENT, ensure_ascii=True))


def _uuid_check(column: str, version: str) -> str:
    return (
        f"length({column}) = 36 AND {column} = lower({column}) "
        f"AND substr({column}, 9, 1) = '-' AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' AND substr({column}, 24, 1) = '-' "
        f"AND length(replace({column}, '-', '')) = 32 "
        f"AND {column} NOT GLOB '*[^0-9a-f-]*' "
        f"AND substr({column}, 15, 1) = '{version}' "
        f"AND substr({column}, 20, 1) IN ('8', '9', 'a', 'b')"
    )


def _project_uuid_check(column: str) -> str:
    common = (
        f"length({column}) = 36 AND {column} = lower({column}) "
        f"AND substr({column}, 9, 1) = '-' AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' AND substr({column}, 24, 1) = '-' "
        f"AND length(replace({column}, '-', '')) = 32 "
        f"AND {column} NOT GLOB '*[^0-9a-f-]*' "
        f"AND substr({column}, 20, 1) IN ('8', '9', 'a', 'b')"
    )
    return (
        f"{common} AND ((project_id_scheme = 'uuid4-bridge' AND substr({column}, 15, 1) = '4') "
        f"OR (project_id_scheme = 'uuid7' AND substr({column}, 15, 1) = '7'))"
    )


def _timestamp_check(column: str) -> str:
    return (
        f"length({column}) = 24 AND {column} GLOB "
        "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
        "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
        "[0-9][0-9][0-9]Z' "
        f"AND CAST(substr({column}, 1, 4) AS INTEGER) BETWEEN 1 AND 9999 "
        f"AND CAST(substr({column}, 12, 2) AS INTEGER) BETWEEN 0 AND 23 "
        f"AND strftime('%Y-%m-%dT%H:%M:%fZ', {column}) IS NOT NULL "
        f"AND strftime('%Y-%m-%dT%H:%M:%fZ', {column}) = {column}"
    )


def _sha256_check(column: str) -> str:
    return f"length({column}) = 64 AND {column} = lower({column}) AND {column} NOT GLOB '*[^0-9a-f]*'"


def _identifier_check(column: str, maximum: int = 120) -> str:
    return (
        f"length({column}) BETWEEN 1 AND {maximum} AND {column} = lower({column}) "
        f"AND substr({column}, 1, 1) GLOB '[a-z]' "
        f"AND {column} NOT GLOB '*[^a-z0-9.-]*' "
        f"AND {column} NOT GLOB '*..*' AND {column} NOT GLOB '*--*' "
        f"AND substr({column}, -1, 1) GLOB '[a-z0-9]'"
    )


def _subtype_table(name: str, kind: str) -> str:
    return f"""
        CREATE TABLE {name} (
            revision_id TEXT PRIMARY KEY,
            aggregate_kind TEXT NOT NULL DEFAULT '{kind}' CHECK (aggregate_kind = '{kind}'),
            FOREIGN KEY (revision_id, aggregate_kind)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """


def _immutable_triggers(table: str, message: str) -> tuple[str, str]:
    return (
        f"""
            CREATE TRIGGER {table}_no_update
            BEFORE UPDATE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{message}');
            END
        """,
        f"""
            CREATE TRIGGER {table}_no_delete
            BEFORE DELETE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{message}');
            END
        """,
    )


_V1_IMMUTABLE_ROW_POLICIES = (
    ("schema_metadata", "schema metadata is immutable outside a reviewed migration"),
    ("projects", "project identity is immutable"),
    ("aggregate_identities", "aggregate identities are immutable"),
    ("aggregate_revisions", "aggregate revisions are immutable"),
    ("scholarly_records", "scholarly record revisions are immutable"),
    ("documents", "document revisions are immutable"),
    ("workflows", "workflow revisions are immutable"),
    ("evidence", "evidence revisions are immutable"),
    ("ontologies", "ontology revisions are immutable"),
    ("decisions", "decision revisions are immutable"),
    ("provenance_events", "provenance events are append-only"),
    ("settings", "settings history is append-only"),
)

_IMMUTABLE_ROW_POLICIES = (
    *_V1_IMMUTABLE_ROW_POLICIES,
    ("schema_migrations", "schema migration history is append-only"),
)


_V1_DDL_STATEMENTS = (
    f"""
        CREATE TABLE schema_metadata (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            schema_version INTEGER NOT NULL CHECK (schema_version = {PREVIOUS_DATABASE_SCHEMA_VERSION}),
            database_profile TEXT NOT NULL CHECK (database_profile = '{DATABASE_PROFILE}'),
            application_id INTEGER NOT NULL CHECK (application_id = {APPLICATION_ID}),
            profile_sha256 TEXT NOT NULL CHECK ({_sha256_check("profile_sha256")}),
            schema_sha256 TEXT NOT NULL CHECK ({_sha256_check("schema_sha256")}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")})
        ) STRICT
    """,
    f"""
        CREATE TABLE projects (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            project_id TEXT NOT NULL UNIQUE,
            project_id_scheme TEXT NOT NULL CHECK (project_id_scheme IN ('uuid4-bridge', 'uuid7')),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            CHECK ({_project_uuid_check("project_id")}),
            UNIQUE (project_id, project_id_scheme)
        ) STRICT
    """,
    f"""
        CREATE TABLE aggregate_identities (
            aggregate_id TEXT PRIMARY KEY CHECK ({_uuid_check("aggregate_id", "7")}),
            project_id TEXT NOT NULL,
            aggregate_kind TEXT NOT NULL CHECK (aggregate_kind IN (
                'record', 'document', 'workflow', 'evidence', 'ontology', 'decision'
            )),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (aggregate_id, project_id, aggregate_kind)
        ) STRICT
    """,
    f"""
        CREATE TABLE aggregate_revisions (
            revision_id TEXT PRIMARY KEY CHECK ({_uuid_check("revision_id", "7")}),
            aggregate_id TEXT NOT NULL CHECK ({_uuid_check("aggregate_id", "7")}),
            aggregate_kind TEXT NOT NULL CHECK (aggregate_kind IN (
                'record', 'document', 'workflow', 'evidence', 'ontology', 'decision'
            )),
            project_id TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            modified_at TEXT NOT NULL CHECK ({_timestamp_check("modified_at")}),
            display_label_observed TEXT NOT NULL CHECK (length(display_label_observed) BETWEEN 1 AND 4096),
            display_label_normalized TEXT CHECK (length(display_label_normalized) BETWEEN 1 AND 4096),
            knowledge_status TEXT NOT NULL CHECK (knowledge_status IN (
                'observed', 'extracted', 'inferred', 'verified', 'disputed', 'adjudicated',
                'stale', 'unknown', 'not-reported', 'not-applicable', 'ambiguous', 'unavailable'
            )),
            rights_status TEXT NOT NULL CHECK (rights_status IN ('allowed', 'denied', 'unknown', 'not-applicable')),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (aggregate_id, project_id, aggregate_kind)
                REFERENCES aggregate_identities (aggregate_id, project_id, aggregate_kind)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (revision_id <> aggregate_id),
            CHECK (modified_at >= created_at),
            UNIQUE (aggregate_id, revision),
            UNIQUE (revision_id, aggregate_kind),
            UNIQUE (revision_id, project_id),
            UNIQUE (revision_id, aggregate_kind, project_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE object_records (
            object_sha256 TEXT PRIMARY KEY CHECK ({_sha256_check("object_sha256")}),
            project_id TEXT NOT NULL,
            byte_length INTEGER NOT NULL CHECK (byte_length BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            media_type TEXT NOT NULL CHECK (
                length(media_type) BETWEEN 3 AND 200
                AND media_type = lower(media_type)
                AND instr(media_type, '/') BETWEEN 2 AND length(media_type) - 1
                AND media_type NOT GLOB '*[^a-z0-9!#$&^_.+/-]*'
            ),
            rights_status TEXT NOT NULL CHECK (rights_status IN ('allowed', 'denied', 'unknown', 'not-applicable')),
            protection_profile TEXT NOT NULL CHECK ({_identifier_check("protection_profile", 120)}),
            retention_class TEXT NOT NULL CHECK (
                retention_class IN ('project-lifetime', 'derived-rebuildable', 'export-retained')
            ),
            storage_state TEXT NOT NULL CHECK (
                storage_state IN ('pending', 'available', 'quarantined', 'deleted')
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            verified_at TEXT CHECK (verified_at IS NULL OR ({_timestamp_check("verified_at")})),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (verified_at IS NULL OR verified_at >= created_at),
            UNIQUE (object_sha256, project_id)
        ) STRICT
    """,
    _subtype_table("scholarly_records", "record"),
    """
        CREATE TABLE documents (
            revision_id TEXT PRIMARY KEY,
            aggregate_kind TEXT NOT NULL DEFAULT 'document' CHECK (aggregate_kind = 'document'),
            project_id TEXT NOT NULL,
            object_sha256 TEXT,
            FOREIGN KEY (revision_id, aggregate_kind, project_id)
                REFERENCES aggregate_revisions (revision_id, aggregate_kind, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (object_sha256, project_id) REFERENCES object_records (object_sha256, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    _subtype_table("workflows", "workflow"),
    _subtype_table("evidence", "evidence"),
    _subtype_table("ontologies", "ontology"),
    _subtype_table("decisions", "decision"),
    f"""
        CREATE TABLE provenance_events (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT,
            event_type TEXT NOT NULL CHECK ({_identifier_check("event_type")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            trace_id TEXT NOT NULL CHECK (
                length(trace_id) = 32 AND trace_id = lower(trace_id) AND trace_id NOT GLOB '*[^0-9a-f]*'
            ),
            actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'system', 'worker', 'model')),
            actor_id TEXT CHECK ({_identifier_check("actor_id", 200)}),
            record_sha256 TEXT NOT NULL CHECK ({_sha256_check("record_sha256")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE settings (
            setting_id TEXT PRIMARY KEY CHECK ({_uuid_check("setting_id", "7")}),
            project_id TEXT NOT NULL,
            setting_key TEXT NOT NULL CHECK ({_identifier_check("setting_key", 160)}),
            revision INTEGER NOT NULL CHECK (revision BETWEEN 0 AND {MAX_SAFE_INTEGER}),
            value_type TEXT NOT NULL CHECK (value_type IN ('text', 'integer', 'real', 'boolean')),
            text_value TEXT,
            integer_value INTEGER,
            real_value REAL,
            boolean_value INTEGER CHECK (boolean_value IN (0, 1)),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            modified_at TEXT NOT NULL CHECK ({_timestamp_check("modified_at")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (modified_at >= created_at),
            CHECK (integer_value IS NULL OR integer_value BETWEEN -{MAX_SAFE_INTEGER} AND {MAX_SAFE_INTEGER}),
            CHECK (
                real_value IS NULL
                OR real_value BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308
            ),
            CHECK (text_value IS NULL OR length(text_value) <= 65536),
            CHECK (
                (value_type = 'text' AND text_value IS NOT NULL AND integer_value IS NULL
                    AND real_value IS NULL AND boolean_value IS NULL)
                OR (value_type = 'integer' AND text_value IS NULL AND integer_value IS NOT NULL
                    AND real_value IS NULL AND boolean_value IS NULL)
                OR (value_type = 'real' AND text_value IS NULL AND integer_value IS NULL
                    AND real_value IS NOT NULL AND boolean_value IS NULL)
                OR (value_type = 'boolean' AND text_value IS NULL AND integer_value IS NULL
                    AND real_value IS NULL AND boolean_value IS NOT NULL)
            ),
            UNIQUE (project_id, setting_key, revision)
        ) STRICT
    """,
    f"""
        CREATE TABLE outbox_events (
            outbox_id TEXT PRIMARY KEY CHECK ({_uuid_check("outbox_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT,
            event_type TEXT NOT NULL CHECK ({_identifier_check("event_type")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            available_at TEXT NOT NULL CHECK ({_timestamp_check("available_at")}),
            state TEXT NOT NULL CHECK (state IN ('pending', 'publishing', 'published', 'failed')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 1000),
            published_at TEXT CHECK (published_at IS NULL OR ({_timestamp_check("published_at")})),
            idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
            record_sha256 TEXT NOT NULL CHECK ({_sha256_check("record_sha256")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK (available_at >= occurred_at),
            CHECK (
                (state = 'published' AND published_at IS NOT NULL)
                OR (state <> 'published' AND published_at IS NULL)
            ),
            UNIQUE (project_id, idempotency_key)
        ) STRICT
    """,
    *(statement for table, message in _V1_IMMUTABLE_ROW_POLICIES for statement in _immutable_triggers(table, message)),
    "CREATE INDEX aggregate_revisions_project_kind ON aggregate_revisions (project_id, aggregate_kind, revision)",
    "CREATE INDEX provenance_events_project_time ON provenance_events (project_id, occurred_at, event_id)",
    "CREATE INDEX outbox_events_dispatch ON outbox_events (state, available_at, outbox_id)",
)

_DDL_STATEMENTS = (
    SCHEMA_METADATA_V2_DDL,
    *_V1_DDL_STATEMENTS[1:],
    SCHEMA_MIGRATIONS_DDL,
    *SCHEMA_MIGRATIONS_TRIGGERS,
)


def _normalize_utc_millisecond(value: str) -> str:
    if not isinstance(value, str) or not _UTC_INPUT.fullmatch(value):
        raise StorageProblem("storage timestamp must be a canonical UTC instant")
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise StorageProblem("storage timestamp must be a real UTC instant") from error
    offset = instant.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise StorageProblem("storage timestamp must use UTC")
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _project_identity(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or value != value.lower():
        raise StorageProblem("project identity must be canonical")
    try:
        identity = UUID(value)
    except ValueError as error:
        raise StorageProblem("project identity must be canonical") from error
    if str(identity) != value or identity.variant != "specified in RFC 4122" or identity.version not in {4, 7}:
        raise StorageProblem("project identity must be an approved UUID bridge or UUIDv7")
    return value, "uuid4-bridge" if identity.version == 4 else "uuid7"


def _redirect(path: Path) -> bool:
    try:
        return path.is_symlink() or path.is_junction()
    except OSError as error:
        raise StorageProblem("database path identity cannot be inspected") from error


def _canonical_database_path(path: Path, *, must_exist: bool) -> Path:
    database = Path(path)
    raw = str(database)
    windows_value = raw.replace("/", "\\").casefold()
    if (
        not database.is_absolute()
        or database.name != "project.sqlite3"
        or "\x00" in raw
        or windows_value.startswith(("\\\\?\\", "\\\\.\\", "\\??\\", "\\device\\"))
    ):
        raise StorageProblem("database path must be the canonical project database location")
    parent = database.parent
    try:
        if _redirect(parent) or not parent.is_dir() or parent.resolve(strict=True) != parent:
            raise StorageProblem("database parent is unavailable or redirected")
        if must_exist:
            status = database.stat(follow_symlinks=False)
            if _redirect(database) or not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise StorageProblem("database file is redirected, linked, or non-regular")
            if database.resolve(strict=True) != database:
                raise StorageProblem("database file is not canonical")
        elif database.exists() or _redirect(database):
            raise StorageProblem("database initialization will not replace an existing entry")
    except StorageProblem:
        raise
    except OSError as error:
        raise StorageProblem("database path identity cannot be verified") from error
    return database


def _open_windows_guards(parent: Path, database: Path) -> list[int]:
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    file_read_attributes = 0x00000080
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_backup_semantics = 0x02000000
    invalid_handle = wintypes.HANDLE(-1).value
    handles: list[int] = []
    for item, flags in (
        (parent, file_flag_open_reparse_point | file_flag_backup_semantics),
        (database, file_flag_open_reparse_point),
    ):
        handle = create_file(
            str(item),
            file_read_attributes,
            file_share_read | file_share_write,
            None,
            open_existing,
            flags,
            None,
        )
        if handle == invalid_handle:
            _close_windows_handles(handles)
            raise StorageProblem("database path could not be held against replacement")
        handles.append(handle)
    return handles


def _close_windows_handles(handles: list[int]) -> None:
    if os.name != "nt" or not handles:
        return
    import ctypes
    from ctypes import wintypes

    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    for handle in reversed(handles):
        close_handle(handle)


_SCHEMA_MUTATION_ACTIONS = frozenset(
    getattr(sqlite3, name)
    for name in (
        "SQLITE_ALTER_TABLE",
        "SQLITE_CREATE_INDEX",
        "SQLITE_CREATE_TABLE",
        "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE",
        "SQLITE_CREATE_TEMP_TRIGGER",
        "SQLITE_CREATE_TEMP_VIEW",
        "SQLITE_CREATE_TRIGGER",
        "SQLITE_CREATE_VIEW",
        "SQLITE_CREATE_VTABLE",
        "SQLITE_DROP_INDEX",
        "SQLITE_DROP_TABLE",
        "SQLITE_DROP_TEMP_INDEX",
        "SQLITE_DROP_TEMP_TABLE",
        "SQLITE_DROP_TEMP_TRIGGER",
        "SQLITE_DROP_TEMP_VIEW",
        "SQLITE_DROP_TRIGGER",
        "SQLITE_DROP_VIEW",
        "SQLITE_DROP_VTABLE",
        "SQLITE_REINDEX",
    )
)

_PROTECTED_WRITE_PRAGMAS = frozenset(
    {
        "application_id",
        "busy_timeout",
        "defer_foreign_keys",
        "foreign_keys",
        "ignore_check_constraints",
        "journal_mode",
        "legacy_alter_table",
        "locking_mode",
        "query_only",
        "recursive_triggers",
        "schema_version",
        "synchronous",
        "trusted_schema",
        "user_version",
        "wal_autocheckpoint",
        "writable_schema",
    }
)
_PROTECTED_COMMAND_PRAGMAS = frozenset({"incremental_vacuum", "optimize", "wal_checkpoint"})


def _initialization_authorizer(
    action: int,
    _arg1: str | None,
    _arg2: str | None,
    _database: str | None,
    _trigger: str | None,
) -> int:
    if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _canonical_authorizer(
    action: int,
    arg1: str | None,
    arg2: str | None,
    database: str | None,
    trigger: str | None,
) -> int:
    if action in _SCHEMA_MUTATION_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action in {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE} and arg1 == "schema_migrations":
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and arg1 is not None:
        pragma = arg1.casefold()
        if pragma in _PROTECTED_COMMAND_PRAGMAS or (pragma in _PROTECTED_WRITE_PRAGMAS and arg2 is not None):
            return sqlite3.SQLITE_DENY
    return _initialization_authorizer(action, arg1, arg2, database, trigger)


def _configure_connection(connection: sqlite3.Connection, *, initialize: bool) -> None:
    if sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION:
        raise StorageProblem("installed SQLite is older than the STRICT storage profile")
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_FKEY, True)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DDL, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    connection.enable_load_extension(False)
    connection.set_authorizer(_initialization_authorizer)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MILLISECONDS}")
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA recursive_triggers=ON")
    connection.execute("PRAGMA locking_mode=NORMAL")
    journal_statement = "PRAGMA journal_mode=WAL" if initialize else "PRAGMA journal_mode"
    journal_mode = str(connection.execute(journal_statement).fetchone()[0]).lower()
    if journal_mode != "wal":
        raise StorageProblem("canonical database could not enter WAL mode")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(f"PRAGMA wal_autocheckpoint={WAL_AUTOCHECKPOINT_PAGES}")
    expected = {
        "foreign_keys": 1,
        "busy_timeout": BUSY_TIMEOUT_MILLISECONDS,
        "trusted_schema": 0,
        "recursive_triggers": 1,
        "synchronous": 2,
        "wal_autocheckpoint": WAL_AUTOCHECKPOINT_PAGES,
    }
    for pragma, value in expected.items():
        if connection.execute(f"PRAGMA {pragma}").fetchone()[0] != value:
            raise StorageProblem("canonical database connection profile was not applied")
    if not initialize:
        connection.set_authorizer(_canonical_authorizer)


def _connect_held(database: Path, *, check_same_thread: bool = True) -> _GuardedConnection:
    parent_before = database.parent.stat(follow_symlinks=False)
    before = database.stat(follow_symlinks=False)
    descriptor: int | None = None
    handles: list[int] = []
    connection: _GuardedConnection | None = None
    try:
        descriptor = os.open(database, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or opened.st_nlink != 1:
            raise StorageProblem("database identity changed before open")
        handles = _open_windows_guards(database.parent, database)
        parent_after = database.parent.stat(follow_symlinks=False)
        if (parent_after.st_dev, parent_after.st_ino) != (parent_before.st_dev, parent_before.st_ino) or _redirect(
            database.parent
        ):
            raise StorageProblem("database parent identity changed during open")
        uri = database.as_uri() + "?mode=rw"
        connection = sqlite3.connect(
            uri,
            uri=True,
            autocommit=True,
            timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
            factory=_GuardedConnection,
            check_same_thread=check_same_thread,
        )
        connection.row_factory = sqlite3.Row
        after = database.stat(follow_symlinks=False)
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino) or after.st_nlink != 1 or _redirect(database):
            raise StorageProblem("database identity changed during open")
        connection._guard_descriptor = descriptor
        connection._guard_handles = handles
        descriptor = None
        handles = []
        return connection
    except (OSError, sqlite3.Error) as error:
        raise StorageProblem("canonical database could not be opened") from error
    finally:
        if connection is not None and descriptor is not None:
            connection.close()
        if descriptor is not None:
            os.close(descriptor)
        _close_windows_handles(handles)


def _schema_profile_errors(
    connection: sqlite3.Connection | CanonicalConnection, expected_project_id: str | None
) -> list[str]:
    errors: list[str] = []
    if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
        errors.append("application-id-mismatch")
    if connection.execute("PRAGMA user_version").fetchone()[0] != DATABASE_SCHEMA_VERSION:
        errors.append("schema-version-mismatch")
    try:
        metadata = connection.execute(
            """
            SELECT schema_version, database_profile, application_id, profile_sha256, schema_sha256
            FROM schema_metadata WHERE singleton=1
            """
        ).fetchone()
    except sqlite3.Error:
        metadata = None
    if metadata is None or tuple(metadata) != (
        DATABASE_SCHEMA_VERSION,
        DATABASE_PROFILE,
        APPLICATION_ID,
        _PROFILE_SHA256,
        EXPECTED_SCHEMA_SHA256,
    ):
        errors.append("schema-metadata-mismatch")
    if _schema_fingerprint(connection) != EXPECTED_SCHEMA_SHA256:
        errors.append("canonical-schema-fingerprint-mismatch")
    if expected_project_id is not None:
        project_rows = connection.execute("SELECT project_id FROM projects ORDER BY project_id").fetchall()
        if [str(row[0]) for row in project_rows] != [expected_project_id]:
            errors.append("project-identity-mismatch")
    return errors


def _open_canonical_database(
    path: Path,
    *,
    expected_project_id: str | None,
    check_same_thread: bool,
) -> CanonicalConnection:
    database = _canonical_database_path(Path(path), must_exist=True)
    if expected_project_id is not None:
        expected_project_id, _ = _project_identity(expected_project_id)
    connection = _connect_held(database, check_same_thread=check_same_thread)
    try:
        _configure_connection(connection, initialize=False)
        errors = _schema_profile_errors(connection, expected_project_id)
        if errors:
            raise StorageProblem("canonical database profile is incompatible")
        return CanonicalConnection(_CAPABILITY_REGISTRY.register_connection(connection))
    except (sqlite3.Error, StorageProblem) as error:
        connection.close()
        if isinstance(error, StorageProblem):
            raise
        raise StorageProblem("canonical database profile could not be verified") from error


def open_canonical_database(path: Path, *, expected_project_id: str | None = None) -> CanonicalConnection:
    """Open an existing canonical database with every connection control applied."""

    return _open_canonical_database(
        path,
        expected_project_id=expected_project_id,
        check_same_thread=True,
    )


def _open_thread_transferable_canonical_database(
    path: Path,
    *,
    expected_project_id: str,
) -> CanonicalConnection:
    """Open a guarded connection whose authority may be closed by its stream consumer."""

    return _open_canonical_database(
        path,
        expected_project_id=expected_project_id,
        check_same_thread=False,
    )


def validate_canonical_database(path: Path, *, expected_project_id: str | None = None) -> None:
    """Validate and close a canonical database without returning connection authority."""

    connection = open_canonical_database(path, expected_project_id=expected_project_id)
    connection.close()


def _schema_fingerprint(connection: sqlite3.Connection | CanonicalConnection) -> str:
    rows = [
        {"type": str(row[0]), "name": str(row[1]), "table": str(row[2]), "sql": str(row[3])}
        for row in connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        )
    ]
    payload = json.dumps(rows, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def database_integrity_report(
    connection: sqlite3.Connection | CanonicalConnection,
    *,
    expected_project_id: str | None = None,
) -> DatabaseIntegrityReport:
    """Run content-free integrity checks against an already configured connection."""

    errors: list[str] = []
    profile_id: str | None = None
    schema_version: int | None = None
    application_id: int | None = None
    journal_mode: str | None = None
    foreign_keys: bool | None = None
    strict_tables: tuple[str, ...] = ()
    quick_check: tuple[str, ...] = ()
    foreign_key_violations: tuple[tuple[Any, ...], ...] = ()
    try:
        errors.extend(_schema_profile_errors(connection, expected_project_id))
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        metadata = connection.execute("SELECT database_profile FROM schema_metadata WHERE singleton=1").fetchone()
        profile_id = str(metadata[0]) if metadata is not None else None
        strict_tables = tuple(
            sorted(
                str(row[1])
                for row in connection.execute("PRAGMA table_list")
                if row[2] == "table" and int(row[5]) == 1 and not str(row[1]).startswith("sqlite_")
            )
        )
        quick_check = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        foreign_key_violations = tuple(tuple(row) for row in connection.execute("PRAGMA foreign_key_check"))
        if quick_check != ("ok",):
            errors.append("quick-check-failed")
        if foreign_key_violations:
            errors.append("foreign-key-check-failed")
        if journal_mode != "wal" or foreign_keys is not True:
            errors.append("connection-profile-mismatch")
    except sqlite3.Error:
        errors.append("integrity-check-unavailable")
    return DatabaseIntegrityReport(
        ok=not errors,
        profile_id=profile_id,
        schema_version=schema_version,
        application_id=application_id,
        journal_mode=journal_mode,
        foreign_keys=foreign_keys,
        strict_tables=strict_tables,
        quick_check=quick_check,
        foreign_key_violations=foreign_key_violations,
        errors=tuple(dict.fromkeys(errors)),
    )


def initialize_database(
    path: Path,
    *,
    project_id: str,
    project_created_at: str,
) -> DatabaseIntegrityReport:
    """Atomically initialize the current schema without replacing any existing entry."""

    database = _canonical_database_path(Path(path), must_exist=False)
    project_id, project_id_scheme = _project_identity(project_id)
    created_at = _normalize_utc_millisecond(project_created_at)
    descriptor: int | None = None
    connection: _GuardedConnection | None = None
    created = False
    succeeded = False
    try:
        descriptor = os.open(
            database,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        created = True
        status = os.fstat(descriptor)
        path_status = database.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_nlink != 1
            or (status.st_dev, status.st_ino) != (path_status.st_dev, path_status.st_ino)
        ):
            raise StorageProblem("new database identity is not exclusive")
        connection = _connect_held(database)
        _configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version={DATABASE_SCHEMA_VERSION}")
            for statement in _DDL_STATEMENTS:
                connection.execute(statement)
            schema_sha256 = _schema_fingerprint(connection)
            if schema_sha256 != EXPECTED_SCHEMA_SHA256:
                raise StorageProblem("compiled schema does not match its reviewed fingerprint")
            connection.execute(
                """
                INSERT INTO schema_metadata (
                    singleton, schema_version, database_profile, application_id,
                    profile_sha256, schema_sha256, created_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DATABASE_SCHEMA_VERSION,
                    DATABASE_PROFILE,
                    APPLICATION_ID,
                    _PROFILE_SHA256,
                    schema_sha256,
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO projects (
                    singleton, project_id, project_id_scheme, created_at
                ) VALUES (1, ?, ?, ?)
                """,
                (project_id, project_id_scheme, created_at),
            )
            connection.set_authorizer(_canonical_authorizer)
            report = database_integrity_report(connection, expected_project_id=project_id)
            if not report.ok:
                raise StorageProblem("new database did not satisfy its integrity contract")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        after = database.stat(follow_symlinks=False)
        opened = os.fstat(descriptor)
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino) or after.st_nlink != 1:
            raise StorageProblem("new database identity changed during initialization")
        succeeded = True
        return report
    except (OSError, sqlite3.Error) as error:
        raise StorageProblem("canonical database initialization failed") from error
    finally:
        if connection is not None:
            connection.close()
        if descriptor is not None:
            os.close(descriptor)
        if created and not succeeded:
            for candidate in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm")):
                with suppress(OSError):
                    candidate.unlink(missing_ok=True)
