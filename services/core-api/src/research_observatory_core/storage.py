"""Versioned local SQLite profile, schema, connection, and integrity boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import threading
from collections.abc import Callable
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]

from research_observatory_core.migrations.versions.v0002_schema_history import (
    SCHEMA_MIGRATIONS_DDL,
    SCHEMA_MIGRATIONS_TRIGGERS,
)
from research_observatory_core.migrations.versions.v0003_object_envelopes import (
    OBJECT_ENVELOPE_COLUMNS,
    OBJECT_ENVELOPE_TRIGGERS,
)
from research_observatory_core.migrations.versions.v0004_object_envelope_upgrades import (
    OBJECT_ENVELOPE_UPGRADES_DDL,
)
from research_observatory_core.migrations.versions.v0005_object_creation_source import (
    OBJECT_CREATION_SOURCE_COLUMN,
    SCHEMA_METADATA_V5_DDL,
)
from research_observatory_core.ports.database_keys import (
    DatabaseKeyConflict,
    DatabaseKeyLease,
    DatabaseKeyProblem,
    DatabaseKeyProvider,
    validate_database_key_identity,
)

APPLICATION_ID = 0x524F4253  # ASCII "ROBS"
DATABASE_PROFILE = "sqlite-wal-v1"
DATABASE_SCHEMA_VERSION = 8
PROVENANCE_LEDGER_DATABASE_SCHEMA_VERSION = 7
ACTOR_IDENTITY_DATABASE_SCHEMA_VERSION = 6
OBJECT_CREATION_SOURCE_DATABASE_SCHEMA_VERSION = 5
OBJECT_ENVELOPE_UPGRADE_DATABASE_SCHEMA_VERSION = 4
OBJECT_ENVELOPE_DATABASE_SCHEMA_VERSION = 3
PREVIOUS_DATABASE_SCHEMA_VERSION = 2
OLDEST_DATABASE_SCHEMA_VERSION = 1
BUSY_TIMEOUT_MILLISECONDS = 5_000
WAL_AUTOCHECKPOINT_PAGES = 1_000
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MINIMUM_SQLITE_VERSION = (3, 37, 0)
SQLCIPHER_PROFILE = "sqlcipher-4.12-community-wal-v1"
DEVELOPMENT_PLAINTEXT_PROFILE = "development-plaintext-fixture"
_SQLCIPHER_HEADER = b"SQLite format 3\x00"
_DATABASE_ERRORS = (sqlite3.Error, sqlcipher.Error)

EXPECTED_TABLES = (
    "schema_metadata",
    "schema_migrations",
    "projects",
    "object_records",
    "object_envelope_upgrades",
    "aggregate_identities",
    "aggregate_revisions",
    "scholarly_records",
    "documents",
    "workflows",
    "workflow_definitions",
    "workflow_authority_snapshots",
    "workflow_queue_jobs",
    "workflow_job_attempts",
    "workflow_attempt_artifacts",
    "workflow_history_events",
    "workflow_checkpoints",
    "workflow_committed_outputs",
    "evidence",
    "ontologies",
    "decisions",
    "provenance_events",
    "provenance_ledger_events",
    "provenance_ledger_entities",
    "provenance_ledger_relations",
    "provenance_ledger_checkpoints",
    "provenance_legacy_bridges",
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
    "workflow_definitions",
    "workflow_authority_snapshots",
    "workflow_history_events",
    "workflow_checkpoints",
    "workflow_committed_outputs",
    "evidence",
    "ontologies",
    "decisions",
    "provenance_events",
    "provenance_ledger_events",
    "provenance_ledger_entities",
    "provenance_ledger_relations",
    "provenance_ledger_checkpoints",
    "provenance_legacy_bridges",
    "settings",
)
MUTABLE_STATE_TABLES = (
    "object_records",
    "object_envelope_upgrades",
    "outbox_events",
    "workflow_queue_jobs",
    "workflow_job_attempts",
    "workflow_attempt_artifacts",
)
EXPECTED_TRIGGERS = tuple(
    sorted(
        [f"{table}_no_{operation}" for table in IMMUTABLE_ROW_TABLES for operation in ("delete", "update")]
        + [
            "object_records_envelope_insert",
            "object_records_envelope_update",
            "provenance_events_bridge_legacy_after_insert",
            "workflow_queue_jobs_identity_immutable",
            "workflow_job_attempts_identity_immutable",
            "workflow_attempt_artifacts_identity_immutable",
            "workflow_attempt_artifacts_disposition_transition",
            "workflow_checkpoint_artifact_authority",
        ]
    )
)
EXPECTED_INDEXES = (
    "aggregate_revisions_project_kind",
    "outbox_events_dispatch",
    "provenance_events_project_time",
    "provenance_ledger_project_time",
    "provenance_ledger_project_type",
    "provenance_ledger_project_subject",
    "provenance_ledger_project_correlation",
    "provenance_ledger_entity_input",
    "provenance_ledger_entity_output",
    "provenance_ledger_relation_entity",
    "provenance_ledger_relation_related_entity",
    "workflow_queue_dispatch",
    "workflow_queue_lease_expiry",
    "workflow_history_run_sequence",
    "workflow_checkpoint_attempt_sequence",
    "workflow_artifact_job_disposition",
)
V1_SCHEMA_SHA256 = "61e5693187250e240f9b6cae573e3b89752ae9b135c6c739d14ff3dfbf6dfdc9"
V1_PROFILE_SHA256 = "fcd3ee269f5d80ce4b554ffc4578d0d16cd941b4afecea19f8860197a77bd1c0"
PREVIOUS_SCHEMA_SHA256 = "afd48fbe857de4172215e9cb61a0f6137e73edec685dcc116bedbb66eb519dda"
PREVIOUS_PROFILE_SHA256 = "29454c72d0b357c2ece14a8991db57bfb87414d7ade85d1a2e8048a648a17cc2"
OBJECT_ENVELOPE_SCHEMA_SHA256 = "246ad968bb1931732c827d0739882c0d59ce91a06c7075867c503c0ef52fd356"
OBJECT_ENVELOPE_PROFILE_SHA256 = "78f1ea999a50641758b0b618af33dc18739d6d6c99644d97823af959583ac2d9"
OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256 = "0b957b48a4280c0dd3c3f9ec518ac44b5fff9354e828572cd2af8aa95e496ff6"
OBJECT_ENVELOPE_UPGRADE_PROFILE_SHA256 = "12cd2d187b6abf8e3cc597288c103277f1079e77b2cd206ad2821730181dbffb"
OBJECT_CREATION_SOURCE_SCHEMA_SHA256 = "4d505b3f925e9df09b137cae61b56125878aa84fd0d6cb353e5d415a0602e2fd"
OBJECT_CREATION_SOURCE_PROFILE_SHA256 = "949f2d60ebe020ad8e8e049ac9d58307213d7aa7008025e5b340e543064ffaa7"
ACTOR_IDENTITY_SCHEMA_SHA256 = "11856aa1b328924596692f08acce368ffbb8798441353fe6a76036329460a7d4"
ACTOR_IDENTITY_PROFILE_SHA256 = "ab8e57caf36e9219a99085648850cd07e2b286feb5e4834ecadf204f76aa771f"
PROVENANCE_LEDGER_SCHEMA_SHA256 = "49329a82e7ade17d57f09a33e650d81e1b3b1d67dc6e4e3b4c8a79d24b6f7475"
EXPECTED_SCHEMA_SHA256 = "1f5d94ac9a17732c72405fdda945df75d1558c444eaf7b6a5dcf286a50443b04"

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
        "actor": "canonical-id-or-uuid7-lowercase-text",
        "setting": "uuid7-lowercase-text",
    },
    "timestampStorage": "utc-rfc3339-millisecond-text",
    "canonicalColumnTypes": ["INTEGER", "REAL", "TEXT"],
    "derivedBinaryStorage": "digest-reference-only",
    "objectCreationSources": [
        "local-import",
        "connector-acquisition",
        "local-derivation",
        "test-fixture",
        "legacy-unreported",
    ],
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
PROVENANCE_LEDGER_PROFILE_SHA256 = "aa59d6f2858f41b7732c91947566fffaf5cd146e1143277deccf2707ceb751e0"
EXPECTED_PROFILE_SHA256 = "c55bb71d5c9553de5d104ae591fee39e06407b479f9f3583b8f1ce42db8ecba7"
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


class _GuardedSqlCipherConnection(sqlcipher.Connection):
    """Internal SQLCipher handle retaining file and directory identity guards."""

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
class _DatabaseProtectionConfiguration:
    profile: str
    provider: DatabaseKeyProvider | None


_DATABASE_PROTECTION_LOCK = threading.RLock()
_DATABASE_PROTECTION = _DatabaseProtectionConfiguration(profile="unconfigured", provider=None)


def configure_protected_database_provider(provider: DatabaseKeyProvider) -> None:
    """Install the process composition's mandatory protected-database key authority."""

    if not isinstance(provider, DatabaseKeyProvider):
        raise ValueError("database key provider is invalid")
    global _DATABASE_PROTECTION
    with _DATABASE_PROTECTION_LOCK:
        if _CAPABILITY_REGISTRY.has_open_connections():
            raise StorageProblem("database protection cannot change while a database is open")
        _DATABASE_PROTECTION = _DatabaseProtectionConfiguration(profile=SQLCIPHER_PROFILE, provider=provider)


@contextmanager
def development_plaintext_database_fixture() -> Any:
    """Explicitly scope legacy schema tests to the sole allowed plaintext profile."""

    global _DATABASE_PROTECTION
    with _DATABASE_PROTECTION_LOCK:
        if _CAPABILITY_REGISTRY.has_open_connections():
            raise StorageProblem("database protection cannot change while a database is open")
        previous = _DATABASE_PROTECTION
        _DATABASE_PROTECTION = _DatabaseProtectionConfiguration(
            profile=DEVELOPMENT_PLAINTEXT_PROFILE,
            provider=None,
        )
    try:
        yield
    finally:
        with _DATABASE_PROTECTION_LOCK:
            if _CAPABILITY_REGISTRY.has_open_connections():
                raise StorageProblem("development plaintext fixture leaked an open database")
            _DATABASE_PROTECTION = previous


def database_protection_profile() -> str:
    with _DATABASE_PROTECTION_LOCK:
        return _DATABASE_PROTECTION.profile


@dataclass(frozen=True, slots=True)
class _CursorEntry:
    connection_token: str
    cursor: Any


class _CapabilityRegistry:
    """Module-owned raw SQLite authority, never returned to ordinary callers."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: dict[str, Any] = {}
        self._cursors: dict[str, _CursorEntry] = {}

    def _token(self) -> str:
        while True:
            token = secrets.token_hex(32)
            if token not in self._connections and token not in self._cursors:
                return token

    def register_connection(self, connection: Any) -> str:
        with self._lock:
            token = self._token()
            self._connections[token] = connection
            return token

    def connection(self, token: str | None) -> Any:
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
            with suppress(*_DATABASE_ERRORS):
                entry.cursor.close()
        if connection is not None:
            connection.close()

    def register_cursor(self, connection_token: str, cursor: Any) -> str:
        with self._lock:
            if connection_token not in self._connections:
                cursor.close()
                raise sqlite3.ProgrammingError("canonical connection is closed")
            token = self._token()
            self._cursors[token] = _CursorEntry(connection_token=connection_token, cursor=cursor)
            return token

    def cursor(self, token: str | None) -> Any:
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
            with suppress(*_DATABASE_ERRORS):
                entry.cursor.close()

    def has_open_connections(self) -> bool:
        with self._lock:
            return bool(self._connections)


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
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    def fetchone(self) -> Any:
        try:
            row = _CAPABILITY_REGISTRY.cursor(self.__token).fetchone()
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error
        if row is None:
            self.close()
        return row

    def fetchmany(self, size: int | None = None) -> list[Any]:
        cursor = _CAPABILITY_REGISTRY.cursor(self.__token)
        try:
            rows = cursor.fetchmany() if size is None else cursor.fetchmany(size)
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error
        if not rows:
            self.close()
        return rows

    def fetchall(self) -> list[Any]:
        try:
            try:
                return _CAPABILITY_REGISTRY.cursor(self.__token).fetchall()
            except sqlcipher.Error as error:
                raise sqlite3.DatabaseError("protected database operation failed") from error
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


def _restricted_cursor(connection_token: str, cursor: Any) -> CanonicalCursor:
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
        try:
            return _restricted_cursor(token, connection.execute(sql, parameters))
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    def executemany(self, sql: str, parameters: Any) -> CanonicalCursor:
        token = self.__token
        if token is None:
            raise sqlite3.ProgrammingError("canonical connection is closed")
        connection = _CAPABILITY_REGISTRY.connection(token)
        try:
            return _restricted_cursor(token, connection.executemany(sql, parameters))
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    def commit(self) -> None:
        try:
            _CAPABILITY_REGISTRY.connection(self.__token).commit()
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

    def rollback(self) -> None:
        try:
            _CAPABILITY_REGISTRY.connection(self.__token).rollback()
        except sqlcipher.Error as error:
            raise sqlite3.DatabaseError("protected database operation failed") from error

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
    protection_profile: str
    cipher_version: str | None
    cipher_integrity: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatabaseRekeyReport:
    operation_id: str
    outcome: str
    previous_key_version: str
    active_key_version: str
    backup_sha256: str


@dataclass(frozen=True, slots=True)
class DatabaseProtectionMigrationReport:
    operation_id: str
    outcome: str
    plaintext_source_sha256: str
    protected_database_sha256: str
    plaintext_cleanup: str


@dataclass(frozen=True, slots=True)
class ProtectedDatabaseBackupReport:
    protection_profile: str
    database_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ProtectedDatabaseRestoreReport:
    operation_id: str
    outcome: str
    restored_database_sha256: str
    displaced_database_sha256: str


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
            schema_version INTEGER NOT NULL CHECK (schema_version = {OLDEST_DATABASE_SCHEMA_VERSION}),
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

_PROVENANCE_EVENTS_V5_DDL = next(
    statement for statement in _V1_DDL_STATEMENTS if "CREATE TABLE provenance_events" in statement
)
PROVENANCE_EVENTS_V6_DDL = _PROVENANCE_EVENTS_V5_DDL.replace(
    f"actor_id TEXT CHECK ({_identifier_check('actor_id', 200)}),",
    f"actor_id TEXT CHECK (({_identifier_check('actor_id', 200)}) OR ({_uuid_check('actor_id', '7')})),",
)
if PROVENANCE_EVENTS_V6_DDL == _PROVENANCE_EVENTS_V5_DDL:
    raise RuntimeError("compiled provenance actor migration differs from its source authority")
SCHEMA_METADATA_V6_DDL = SCHEMA_METADATA_V5_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 5)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 6)",
)
SCHEMA_METADATA_V7_DDL = SCHEMA_METADATA_V6_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 6)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 7)",
)
SCHEMA_METADATA_V8_DDL = SCHEMA_METADATA_V7_DDL.replace(
    "schema_version INTEGER NOT NULL CHECK (schema_version = 7)",
    "schema_version INTEGER NOT NULL CHECK (schema_version = 8)",
)

PROVENANCE_LEDGER_DDL = (
    f"""
        CREATE TABLE provenance_ledger_events (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            segment_key TEXT NOT NULL CHECK ({_identifier_check("segment_key", 120)}),
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            subject TEXT NOT NULL CHECK (length(subject) BETWEEN 50 AND 300),
            event_type TEXT NOT NULL CHECK (length(event_type) BETWEEN 1 AND 160),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            correlation_id TEXT NOT NULL CHECK ({_uuid_check("correlation_id", "7")}),
            causation_id TEXT CHECK (causation_id IS NULL OR ({_uuid_check("causation_id", "7")})),
            activity_id TEXT NOT NULL CHECK ({_uuid_check("activity_id", "7")}),
            activity_type TEXT NOT NULL CHECK ({_identifier_check("activity_type", 128)}),
            activity_status TEXT NOT NULL CHECK (activity_status IN ('succeeded', 'failed', 'cancelled', 'denied')),
            agent_id TEXT NOT NULL CHECK ({_uuid_check("agent_id", "7")}),
            sensitivity TEXT NOT NULL CHECK (
                sensitivity IN (
                    'public-metadata', 'licensed-metadata', 'open-full-text',
                    'licensed-full-text', 'private-research', 'restricted'
                )
            ),
            retention_class TEXT NOT NULL CHECK (
                retention_class IN ('project-lifetime', 'legal-hold', 'policy-bound', 'time-bounded', 'tombstone-only')
            ),
            record_json TEXT NOT NULL CHECK (length(record_json) BETWEEN 2 AND 1048576),
            record_sha256 TEXT NOT NULL CHECK (
                length(record_sha256) = 71 AND substr(record_sha256, 1, 7) = 'sha256:'
                AND substr(record_sha256, 8) = lower(substr(record_sha256, 8))
                AND substr(record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            idempotency_sha256 TEXT NOT NULL CHECK ({_sha256_check("idempotency_sha256")}),
            previous_chain_sha256 TEXT CHECK (
                previous_chain_sha256 IS NULL OR (
                    length(previous_chain_sha256) = 71 AND substr(previous_chain_sha256, 1, 7) = 'sha256:'
                    AND substr(previous_chain_sha256, 8) = lower(substr(previous_chain_sha256, 8))
                    AND substr(previous_chain_sha256, 8) NOT GLOB '*[^0-9a-f]*'
                )
            ),
            chain_sha256 TEXT NOT NULL CHECK (
                length(chain_sha256) = 71 AND substr(chain_sha256, 1, 7) = 'sha256:'
                AND substr(chain_sha256, 8) = lower(substr(chain_sha256, 8))
                AND substr(chain_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, segment_key, sequence),
            UNIQUE (project_id, event_id),
            UNIQUE (project_id, record_sha256)
        ) STRICT
    """,
    f"""
        CREATE TABLE provenance_ledger_entities (
            event_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('input', 'output')),
            entity_id TEXT NOT NULL CHECK ({_uuid_check("entity_id", "7")}),
            revision_id TEXT NOT NULL CHECK ({_uuid_check("revision_id", "7")}),
            entity_kind TEXT NOT NULL CHECK ({_identifier_check("entity_kind", 128)}),
            content_hash TEXT NOT NULL CHECK (
                length(content_hash) = 71 AND substr(content_hash, 1, 7) = 'sha256:'
                AND substr(content_hash, 8) = lower(substr(content_hash, 8))
                AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            sensitivity TEXT NOT NULL CHECK (
                sensitivity IN (
                    'public-metadata', 'licensed-metadata', 'open-full-text',
                    'licensed-full-text', 'private-research', 'restricted'
                )
            ),
            retention_class TEXT NOT NULL CHECK (
                retention_class IN ('project-lifetime', 'legal-hold', 'policy-bound', 'time-bounded', 'tombstone-only')
            ),
            PRIMARY KEY (event_id, direction, revision_id),
            FOREIGN KEY (event_id, project_id) REFERENCES provenance_ledger_events (event_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    f"""
        CREATE TABLE provenance_ledger_relations (
            event_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            relation_id TEXT NOT NULL CHECK ({_uuid_check("relation_id", "7")}),
            relation_type TEXT NOT NULL CHECK (
                relation_type IN (
                    'used', 'wasGeneratedBy', 'wasAssociatedWith', 'wasDerivedFrom',
                    'wasInvalidatedBy', 'wasAttributedTo'
                )
            ),
            entity_id TEXT CHECK (entity_id IS NULL OR ({_uuid_check("entity_id", "7")})),
            entity_revision_id TEXT CHECK (
                entity_revision_id IS NULL OR ({_uuid_check("entity_revision_id", "7")})
            ),
            related_entity_id TEXT CHECK (related_entity_id IS NULL OR ({_uuid_check("related_entity_id", "7")})),
            related_revision_id TEXT CHECK (
                related_revision_id IS NULL OR ({_uuid_check("related_revision_id", "7")})
            ),
            activity_id TEXT CHECK (activity_id IS NULL OR ({_uuid_check("activity_id", "7")})),
            agent_id TEXT CHECK (agent_id IS NULL OR ({_uuid_check("agent_id", "7")})),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            PRIMARY KEY (event_id, relation_id),
            FOREIGN KEY (event_id, project_id) REFERENCES provenance_ledger_events (event_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK ((entity_id IS NULL) = (entity_revision_id IS NULL)),
            CHECK ((related_entity_id IS NULL) = (related_revision_id IS NULL))
        ) STRICT
    """,
    f"""
        CREATE TABLE provenance_ledger_checkpoints (
            checkpoint_id TEXT PRIMARY KEY CHECK ({_uuid_check("checkpoint_id", "7")}),
            event_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            segment_key TEXT NOT NULL CHECK ({_identifier_check("segment_key", 120)}),
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            chain_sha256 TEXT NOT NULL CHECK (
                length(chain_sha256) = 71 AND substr(chain_sha256, 1, 7) = 'sha256:'
                AND substr(chain_sha256, 8) = lower(substr(chain_sha256, 8))
                AND substr(chain_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (event_id, project_id) REFERENCES provenance_ledger_events (event_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, segment_key, sequence)
        ) STRICT
    """,
    f"""
        CREATE TABLE provenance_legacy_bridges (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            revision_id TEXT,
            event_type TEXT NOT NULL CHECK ({_identifier_check("event_type")}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            trace_id TEXT NOT NULL CHECK (
                length(trace_id) = 32 AND trace_id = lower(trace_id) AND trace_id NOT GLOB '*[^0-9a-f]*'
            ),
            actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'system', 'worker', 'model')),
            actor_id TEXT,
            source_record_sha256 TEXT NOT NULL CHECK ({_sha256_check("source_record_sha256")}),
            bridge_state TEXT NOT NULL CHECK (bridge_state = 'legacy-narrow'),
            FOREIGN KEY (event_id) REFERENCES provenance_events (event_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
    *(
        statement
        for table, message in (
            ("provenance_ledger_events", "provenance ledger events are append-only"),
            ("provenance_ledger_entities", "provenance ledger entities are append-only"),
            ("provenance_ledger_relations", "provenance ledger relations are append-only"),
            ("provenance_ledger_checkpoints", "provenance ledger checkpoints are append-only"),
            ("provenance_legacy_bridges", "provenance legacy bridges are append-only"),
        )
        for statement in _immutable_triggers(table, message)
    ),
    "CREATE INDEX provenance_ledger_project_time ON provenance_ledger_events (project_id, occurred_at, event_id)",
    "CREATE INDEX provenance_ledger_project_type ON provenance_ledger_events (project_id, event_type, occurred_at)",
    "CREATE INDEX provenance_ledger_project_subject ON provenance_ledger_events (project_id, subject, occurred_at)",
    "CREATE INDEX provenance_ledger_project_correlation ON provenance_ledger_events "
    "(project_id, correlation_id, occurred_at)",
    "CREATE INDEX provenance_ledger_entity_input ON provenance_ledger_entities "
    "(project_id, revision_id, direction, event_id)",
    "CREATE INDEX provenance_ledger_entity_output ON provenance_ledger_entities "
    "(project_id, entity_id, direction, revision_id)",
    "CREATE INDEX provenance_ledger_relation_entity ON provenance_ledger_relations "
    "(project_id, entity_revision_id, relation_type)",
    "CREATE INDEX provenance_ledger_relation_related_entity ON provenance_ledger_relations "
    "(project_id, related_revision_id, relation_type)",
    """
        CREATE TRIGGER provenance_events_bridge_legacy_after_insert
        AFTER INSERT ON provenance_events
        WHEN NOT EXISTS (
            SELECT 1 FROM provenance_ledger_events
             WHERE project_id=NEW.project_id AND event_id=NEW.event_id
        )
        BEGIN
            INSERT INTO provenance_legacy_bridges (
                event_id, project_id, revision_id, event_type, occurred_at,
                trace_id, actor_type, actor_id, source_record_sha256, bridge_state
            ) VALUES (
                NEW.event_id, NEW.project_id, NEW.revision_id, NEW.event_type,
                NEW.occurred_at, NEW.trace_id, NEW.actor_type, NEW.actor_id,
                NEW.record_sha256, 'legacy-narrow'
            );
        END
    """,
)

WORKFLOW_EXECUTOR_DDL = (
    f"""
        CREATE TABLE workflow_definitions (
            definition_revision_id TEXT PRIMARY KEY CHECK ({_uuid_check("definition_revision_id", "7")}),
            project_id TEXT NOT NULL,
            workflow_definition_id TEXT NOT NULL CHECK ({_uuid_check("workflow_definition_id", "7")}),
            definition_version TEXT NOT NULL CHECK (length(definition_version) BETWEEN 5 AND 64),
            contract_version TEXT NOT NULL CHECK (contract_version = '1.0.0'),
            content_hash TEXT NOT NULL CHECK (
                length(content_hash) = 71 AND substr(content_hash, 1, 7) = 'sha256:'
                AND substr(content_hash, 8) = lower(substr(content_hash, 8))
                AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            definition_json TEXT NOT NULL CHECK (length(definition_json) BETWEEN 2 AND 1048576),
            record_sha256 TEXT NOT NULL CHECK (
                length(record_sha256) = 71 AND substr(record_sha256, 1, 7) = 'sha256:'
                AND substr(record_sha256, 8) = lower(substr(record_sha256, 8))
                AND substr(record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, workflow_definition_id, definition_revision_id),
            UNIQUE (project_id, record_sha256)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_authority_snapshots (
            snapshot_id TEXT NOT NULL CHECK ({_uuid_check("snapshot_id", "7")}),
            snapshot_revision INTEGER NOT NULL CHECK (snapshot_revision BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            project_id TEXT NOT NULL,
            workflow_run_id TEXT NOT NULL CHECK ({_uuid_check("workflow_run_id", "7")}),
            definition_revision_id TEXT NOT NULL CHECK ({_uuid_check("definition_revision_id", "7")}),
            state TEXT NOT NULL CHECK (state IN (
                'accepted', 'running', 'waiting-human', 'paused', 'cancelling',
                'succeeded', 'failed', 'cancelled'
            )),
            history_sequence INTEGER NOT NULL CHECK (history_sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            snapshot_json TEXT NOT NULL CHECK (length(snapshot_json) BETWEEN 2 AND 16777216),
            record_sha256 TEXT NOT NULL CHECK (
                length(record_sha256) = 71 AND substr(record_sha256, 1, 7) = 'sha256:'
                AND substr(record_sha256, 8) = lower(substr(record_sha256, 8))
                AND substr(record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            updated_at TEXT NOT NULL CHECK ({_timestamp_check("updated_at")}),
            PRIMARY KEY (snapshot_id, snapshot_revision),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (definition_revision_id) REFERENCES workflow_definitions (definition_revision_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, workflow_run_id, snapshot_revision),
            UNIQUE (snapshot_id, snapshot_revision, project_id, workflow_run_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_queue_jobs (
            job_id TEXT PRIMARY KEY CHECK ({_uuid_check("job_id", "7")}),
            project_id TEXT NOT NULL,
            workflow_run_id TEXT NOT NULL CHECK ({_uuid_check("workflow_run_id", "7")}),
            snapshot_id TEXT NOT NULL CHECK ({_uuid_check("snapshot_id", "7")}),
            snapshot_revision INTEGER NOT NULL CHECK (snapshot_revision BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            step_run_id TEXT NOT NULL CHECK ({_uuid_check("step_run_id", "7")}),
            activity_type TEXT NOT NULL CHECK ({_identifier_check("activity_type", 96)}),
            concurrency_class TEXT NOT NULL CHECK (
                concurrency_class IN ('interactive', 'document', 'ai', 'maintenance')
            ),
            progress_unit TEXT NOT NULL CHECK ({_identifier_check("progress_unit", 96)}),
            progress_total_kind TEXT NOT NULL CHECK (
                progress_total_kind IN ('known', 'unknown', 'not-applicable')
            ),
            progress_total_units INTEGER CHECK (
                progress_total_units IS NULL OR progress_total_units BETWEEN 0 AND {MAX_SAFE_INTEGER}
            ),
            checkpoint_mode TEXT NOT NULL CHECK (checkpoint_mode IN ('forbidden', 'optional', 'required')),
            partial_artifact_disposition TEXT NOT NULL CHECK (
                partial_artifact_disposition IN ('retained-incomplete', 'quarantined', 'discarded')
            ),
            state TEXT NOT NULL CHECK (state IN (
                'runnable', 'claimed', 'running', 'retry-scheduled', 'cancelling',
                'cancelled', 'failed', 'succeeded'
            )),
            priority INTEGER NOT NULL CHECK (priority BETWEEN -1000 AND 1000),
            available_at TEXT NOT NULL CHECK ({_timestamp_check("available_at")}),
            max_attempts INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 32),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 32),
            initial_backoff_ms INTEGER NOT NULL CHECK (initial_backoff_ms BETWEEN 0 AND 86400000),
            maximum_backoff_ms INTEGER NOT NULL CHECK (maximum_backoff_ms BETWEEN 0 AND 604800000),
            multiplier_basis_points INTEGER NOT NULL CHECK (multiplier_basis_points BETWEEN 10000 AND 100000),
            deterministic_jitter INTEGER NOT NULL CHECK (deterministic_jitter IN (0, 1)),
            retryable_error_codes_json TEXT NOT NULL CHECK (length(retryable_error_codes_json) BETWEEN 2 AND 16384),
            non_retryable_error_codes_json TEXT NOT NULL CHECK (
                length(non_retryable_error_codes_json) BETWEEN 2 AND 16384
            ),
            idempotency_key TEXT NOT NULL CHECK (
                length(idempotency_key) = 71 AND substr(idempotency_key, 1, 7) = 'sha256:'
                AND substr(idempotency_key, 8) = lower(substr(idempotency_key, 8))
                AND substr(idempotency_key, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            command_fingerprint TEXT NOT NULL CHECK (
                length(command_fingerprint) = 71 AND substr(command_fingerprint, 1, 7) = 'sha256:'
                AND substr(command_fingerprint, 8) = lower(substr(command_fingerprint, 8))
                AND substr(command_fingerprint, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            current_attempt_id TEXT CHECK (current_attempt_id IS NULL OR ({_uuid_check("current_attempt_id", "7")})),
            lease_generation INTEGER NOT NULL DEFAULT 0 CHECK (
                lease_generation BETWEEN 0 AND {MAX_SAFE_INTEGER}
            ),
            lease_owner TEXT CHECK (lease_owner IS NULL OR ({_uuid_check("lease_owner", "7")})),
            lease_token_sha256 TEXT CHECK (lease_token_sha256 IS NULL OR ({_sha256_check("lease_token_sha256")})),
            lease_expires_at TEXT CHECK (lease_expires_at IS NULL OR ({_timestamp_check("lease_expires_at")})),
            heartbeat_at TEXT CHECK (heartbeat_at IS NULL OR ({_timestamp_check("heartbeat_at")})),
            cancellation_requested_at TEXT CHECK (
                cancellation_requested_at IS NULL OR ({_timestamp_check("cancellation_requested_at")})
            ),
            cancellation_reason_code TEXT CHECK (
                cancellation_reason_code IS NULL OR ({_identifier_check("cancellation_reason_code", 96)})
            ),
            interruption_kind TEXT CHECK (
                interruption_kind IS NULL OR interruption_kind IN (
                    'ordinary-restart', 'user-cancel', 'security-lock', 'policy', 'dependency'
                )
            ),
            diagnostic_code TEXT CHECK (diagnostic_code IS NULL OR ({_identifier_check("diagnostic_code", 96)})),
            committed_output_sha256 TEXT CHECK (
                committed_output_sha256 IS NULL OR (
                    length(committed_output_sha256) = 71 AND substr(committed_output_sha256, 1, 7) = 'sha256:'
                    AND substr(committed_output_sha256, 8) = lower(substr(committed_output_sha256, 8))
                    AND substr(committed_output_sha256, 8) NOT GLOB '*[^0-9a-f]*'
                )
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            updated_at TEXT NOT NULL CHECK ({_timestamp_check("updated_at")}),
            FOREIGN KEY (snapshot_id, snapshot_revision, project_id, workflow_run_id)
                REFERENCES workflow_authority_snapshots (snapshot_id, snapshot_revision, project_id, workflow_run_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, idempotency_key),
            CHECK (attempt_count <= max_attempts),
            CHECK ((progress_total_kind = 'known') = (progress_total_units IS NOT NULL)),
            CHECK (
                (state IN ('claimed', 'running', 'cancelling') AND current_attempt_id IS NOT NULL
                    AND lease_owner IS NOT NULL AND lease_token_sha256 IS NOT NULL AND lease_expires_at IS NOT NULL)
                OR (state NOT IN ('claimed', 'running', 'cancelling')
                    AND lease_owner IS NULL AND lease_token_sha256 IS NULL AND lease_expires_at IS NULL)
            ),
            CHECK ((state = 'succeeded') = (committed_output_sha256 IS NOT NULL))
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_job_attempts (
            attempt_id TEXT PRIMARY KEY CHECK ({_uuid_check("attempt_id", "7")}),
            project_id TEXT NOT NULL,
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 32),
            state TEXT NOT NULL CHECK (state IN (
                'claimed', 'running', 'succeeded', 'failed', 'cancelled', 'abandoned'
            )),
            worker_id TEXT NOT NULL CHECK ({_uuid_check("worker_id", "7")}),
            lease_generation INTEGER NOT NULL CHECK (lease_generation BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            lease_token_sha256 TEXT NOT NULL CHECK ({_sha256_check("lease_token_sha256")}),
            lease_expires_at TEXT NOT NULL CHECK ({_timestamp_check("lease_expires_at")}),
            heartbeat_at TEXT NOT NULL CHECK ({_timestamp_check("heartbeat_at")}),
            progress_json TEXT,
            started_at TEXT CHECK (started_at IS NULL OR ({_timestamp_check("started_at")})),
            ended_at TEXT CHECK (ended_at IS NULL OR ({_timestamp_check("ended_at")})),
            diagnostic_code TEXT CHECK (diagnostic_code IS NULL OR ({_identifier_check("diagnostic_code", 96)})),
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (job_id, attempt_number),
            UNIQUE (job_id, lease_generation),
            CHECK ((state IN ('succeeded', 'failed', 'cancelled', 'abandoned')) = (ended_at IS NOT NULL))
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_attempt_artifacts (
            attempt_id TEXT NOT NULL CHECK ({_uuid_check("attempt_id", "7")}),
            project_id TEXT NOT NULL,
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            artifact_id TEXT NOT NULL CHECK ({_uuid_check("artifact_id", "7")}),
            revision_id TEXT NOT NULL CHECK ({_uuid_check("revision_id", "7")}),
            role TEXT NOT NULL CHECK (role IN ('output', 'checkpoint', 'diagnostic')),
            disposition TEXT NOT NULL CHECK (
                disposition IN ('committed', 'retained-incomplete', 'quarantined', 'discarded')
            ),
            content_hash TEXT NOT NULL CHECK (
                length(content_hash) = 71 AND substr(content_hash, 1, 7) = 'sha256:'
                AND substr(content_hash, 8) = lower(substr(content_hash, 8))
                AND substr(content_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            media_type TEXT NOT NULL CHECK (length(media_type) BETWEEN 3 AND 100),
            provenance_entity_id TEXT CHECK (
                provenance_entity_id IS NULL OR ({_uuid_check("provenance_entity_id", "7")})
            ),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            updated_at TEXT NOT NULL CHECK ({_timestamp_check("updated_at")}),
            PRIMARY KEY (attempt_id, artifact_id),
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (revision_id, project_id) REFERENCES aggregate_revisions (revision_id, project_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (attempt_id, revision_id),
            CHECK (provenance_entity_id IS NULL OR provenance_entity_id = artifact_id)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_history_events (
            event_id TEXT PRIMARY KEY CHECK ({_uuid_check("event_id", "7")}),
            project_id TEXT NOT NULL,
            workflow_run_id TEXT NOT NULL CHECK ({_uuid_check("workflow_run_id", "7")}),
            job_id TEXT CHECK (job_id IS NULL OR ({_uuid_check("job_id", "7")})),
            attempt_id TEXT CHECK (attempt_id IS NULL OR ({_uuid_check("attempt_id", "7")})),
            sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            entity_type TEXT NOT NULL CHECK (
                entity_type IN ('workflow-run', 'workflow-step', 'job', 'job-attempt', 'human-task')
            ),
            entity_id TEXT NOT NULL CHECK ({_uuid_check("entity_id", "7")}),
            from_state TEXT,
            to_state TEXT NOT NULL CHECK ({_identifier_check("to_state", 96)}),
            occurred_at TEXT NOT NULL CHECK ({_timestamp_check("occurred_at")}),
            actor_json TEXT NOT NULL CHECK (length(actor_json) BETWEEN 2 AND 4096),
            reason_code TEXT NOT NULL CHECK ({_identifier_check("reason_code", 96)}),
            event_json TEXT NOT NULL CHECK (length(event_json) BETWEEN 2 AND 65536),
            record_sha256 TEXT NOT NULL CHECK (
                length(record_sha256) = 71 AND substr(record_sha256, 1, 7) = 'sha256:'
                AND substr(record_sha256, 8) = lower(substr(record_sha256, 8))
                AND substr(record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, workflow_run_id, sequence)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_checkpoints (
            checkpoint_id TEXT PRIMARY KEY CHECK ({_uuid_check("checkpoint_id", "7")}),
            project_id TEXT NOT NULL,
            job_id TEXT NOT NULL CHECK ({_uuid_check("job_id", "7")}),
            attempt_id TEXT NOT NULL CHECK ({_uuid_check("attempt_id", "7")}),
            checkpoint_sequence INTEGER NOT NULL CHECK (
                checkpoint_sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}
            ),
            history_sequence INTEGER NOT NULL CHECK (history_sequence BETWEEN 1 AND {MAX_SAFE_INTEGER}),
            created_at TEXT NOT NULL CHECK ({_timestamp_check("created_at")}),
            state_hash TEXT NOT NULL CHECK (
                length(state_hash) = 71 AND substr(state_hash, 1, 7) = 'sha256:'
                AND substr(state_hash, 8) = lower(substr(state_hash, 8))
                AND substr(state_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            payload_artifact_id TEXT NOT NULL CHECK ({_uuid_check("payload_artifact_id", "7")}),
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id, payload_artifact_id)
                REFERENCES workflow_attempt_artifacts (attempt_id, artifact_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (attempt_id, checkpoint_sequence)
        ) STRICT
    """,
    f"""
        CREATE TABLE workflow_committed_outputs (
            job_id TEXT PRIMARY KEY CHECK ({_uuid_check("job_id", "7")}),
            project_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL CHECK ({_uuid_check("attempt_id", "7")}),
            idempotency_key TEXT NOT NULL,
            command_fingerprint TEXT NOT NULL,
            output_manifest_json TEXT NOT NULL CHECK (length(output_manifest_json) BETWEEN 2 AND 1048576),
            output_record_sha256 TEXT NOT NULL CHECK (
                length(output_record_sha256) = 71 AND substr(output_record_sha256, 1, 7) = 'sha256:'
                AND substr(output_record_sha256, 8) = lower(substr(output_record_sha256, 8))
                AND substr(output_record_sha256, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            committed_at TEXT NOT NULL CHECK ({_timestamp_check("committed_at")}),
            provenance_event_id TEXT NOT NULL CHECK ({_uuid_check("provenance_event_id", "7")}),
            outbox_id TEXT NOT NULL CHECK ({_uuid_check("outbox_id", "7")}),
            FOREIGN KEY (job_id) REFERENCES workflow_queue_jobs (job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES workflow_job_attempts (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (provenance_event_id) REFERENCES provenance_events (event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (outbox_id) REFERENCES outbox_events (outbox_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (project_id, idempotency_key)
        ) STRICT
    """,
    *(
        statement
        for table, message in (
            ("workflow_definitions", "workflow definitions are immutable"),
            ("workflow_authority_snapshots", "workflow authority snapshots are immutable"),
            ("workflow_history_events", "workflow history is append-only"),
            ("workflow_checkpoints", "workflow checkpoints are append-only"),
            ("workflow_committed_outputs", "workflow committed outputs are immutable"),
        )
        for statement in _immutable_triggers(table, message)
    ),
    """
        CREATE TRIGGER workflow_queue_jobs_identity_immutable
        BEFORE UPDATE ON workflow_queue_jobs
        WHEN NEW.job_id <> OLD.job_id OR NEW.project_id <> OLD.project_id
          OR NEW.workflow_run_id <> OLD.workflow_run_id OR NEW.snapshot_id <> OLD.snapshot_id
          OR NEW.snapshot_revision <> OLD.snapshot_revision OR NEW.step_run_id <> OLD.step_run_id
          OR NEW.activity_type <> OLD.activity_type OR NEW.concurrency_class <> OLD.concurrency_class
          OR NEW.progress_unit <> OLD.progress_unit OR NEW.progress_total_kind <> OLD.progress_total_kind
          OR NEW.progress_total_units IS NOT OLD.progress_total_units OR NEW.checkpoint_mode <> OLD.checkpoint_mode
          OR NEW.partial_artifact_disposition <> OLD.partial_artifact_disposition
          OR NEW.idempotency_key <> OLD.idempotency_key OR NEW.command_fingerprint <> OLD.command_fingerprint
          OR NEW.max_attempts <> OLD.max_attempts
        BEGIN
            SELECT RAISE(ABORT, 'workflow queue authority is immutable');
        END
    """,
    """
        CREATE TRIGGER workflow_attempt_artifacts_identity_immutable
        BEFORE UPDATE ON workflow_attempt_artifacts
        WHEN NEW.attempt_id <> OLD.attempt_id OR NEW.project_id <> OLD.project_id
          OR NEW.job_id <> OLD.job_id OR NEW.artifact_id <> OLD.artifact_id
          OR NEW.revision_id <> OLD.revision_id OR NEW.role <> OLD.role
          OR NEW.content_hash <> OLD.content_hash OR NEW.media_type <> OLD.media_type
          OR NEW.provenance_entity_id IS NOT OLD.provenance_entity_id OR NEW.created_at <> OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'workflow artifact authority is immutable');
        END
    """,
    """
        CREATE TRIGGER workflow_attempt_artifacts_disposition_transition
        BEFORE UPDATE OF disposition ON workflow_attempt_artifacts
        WHEN NEW.disposition <> OLD.disposition
         AND NOT (
            OLD.disposition='retained-incomplete'
            AND NEW.disposition IN ('committed', 'quarantined', 'discarded')
         )
        BEGIN
            SELECT RAISE(ABORT, 'workflow artifact disposition transition is invalid');
        END
    """,
    """
        CREATE TRIGGER workflow_checkpoint_artifact_authority
        BEFORE INSERT ON workflow_checkpoints
        WHEN NOT EXISTS (
            SELECT 1 FROM workflow_attempt_artifacts AS artifact
             WHERE artifact.project_id=NEW.project_id AND artifact.job_id=NEW.job_id
               AND artifact.attempt_id=NEW.attempt_id
               AND artifact.artifact_id=NEW.payload_artifact_id
               AND artifact.role='checkpoint' AND artifact.disposition='committed'
               AND artifact.content_hash=NEW.state_hash
        )
        BEGIN
            SELECT RAISE(ABORT, 'workflow checkpoint artifact authority differs');
        END
    """,
    """
        CREATE TRIGGER workflow_job_attempts_identity_immutable
        BEFORE UPDATE ON workflow_job_attempts
        WHEN NEW.attempt_id <> OLD.attempt_id OR NEW.project_id <> OLD.project_id
          OR NEW.job_id <> OLD.job_id OR NEW.attempt_number <> OLD.attempt_number
          OR NEW.worker_id <> OLD.worker_id OR NEW.lease_generation <> OLD.lease_generation
          OR NEW.lease_token_sha256 <> OLD.lease_token_sha256
        BEGIN
            SELECT RAISE(ABORT, 'workflow attempt authority is immutable');
        END
    """,
    "CREATE INDEX workflow_queue_dispatch ON workflow_queue_jobs "
    "(state, concurrency_class, available_at, priority DESC, job_id)",
    "CREATE INDEX workflow_queue_lease_expiry ON workflow_queue_jobs (state, lease_expires_at, job_id)",
    "CREATE INDEX workflow_history_run_sequence ON workflow_history_events (project_id, workflow_run_id, sequence)",
    "CREATE INDEX workflow_checkpoint_attempt_sequence ON workflow_checkpoints (attempt_id, checkpoint_sequence)",
    "CREATE INDEX workflow_artifact_job_disposition ON workflow_attempt_artifacts "
    "(job_id, disposition, role, artifact_id)",
)

_V6_BASE_DDL_STATEMENTS = tuple(
    PROVENANCE_EVENTS_V6_DDL if "CREATE TABLE provenance_events" in statement else statement
    for statement in _V1_DDL_STATEMENTS[1:]
)

_DDL_STATEMENTS = (
    SCHEMA_METADATA_V8_DDL,
    *_V6_BASE_DDL_STATEMENTS,
    SCHEMA_MIGRATIONS_DDL,
    *SCHEMA_MIGRATIONS_TRIGGERS,
    *OBJECT_ENVELOPE_COLUMNS,
    "UPDATE object_records SET ciphertext_byte_length=byte_length",
    *OBJECT_ENVELOPE_TRIGGERS,
    OBJECT_ENVELOPE_UPGRADES_DDL,
    OBJECT_CREATION_SOURCE_COLUMN,
    *PROVENANCE_LEDGER_DDL,
    *WORKFLOW_EXECUTOR_DDL,
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


def _configure_connection(connection: Any, *, initialize: bool, protected: bool = False) -> None:
    sqlite_version = sqlcipher.sqlite_version_info if protected else sqlite3.sqlite_version_info
    if sqlite_version < MINIMUM_SQLITE_VERSION:
        raise StorageProblem("installed SQLite is older than the STRICT storage profile")
    if protected:
        version = connection.execute("PRAGMA cipher_version").fetchone()
        status = connection.execute("PRAGMA cipher_status").fetchone()
        if version is None or not str(version[0]).startswith("4.12.") or status is None or str(status[0]) != "1":
            raise StorageProblem("protected database runtime is unavailable")
        connection.execute("PRAGMA cipher_plaintext_header_size=0")
        cipher_expected = {
            "cipher_page_size": "4096",
            "cipher_use_hmac": "1",
            "cipher_hmac_algorithm": "HMAC_SHA512",
            "cipher_kdf_algorithm": "PBKDF2_HMAC_SHA512",
        }
        for pragma, cipher_value in cipher_expected.items():
            row = connection.execute(f"PRAGMA {pragma}").fetchone()
            if row is None or row[0] != cipher_value:
                raise StorageProblem("protected database compatibility profile was not applied")
    else:
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


def _database_protection_configuration() -> _DatabaseProtectionConfiguration:
    with _DATABASE_PROTECTION_LOCK:
        configuration = _DATABASE_PROTECTION
    if configuration.profile == "unconfigured":
        raise StorageProblem("protected database key authority is not configured")
    return configuration


def _key_sqlcipher_connection(connection: Any, material: memoryview) -> None:
    if len(material) != 32:
        raise StorageProblem("protected database key material is invalid")
    raw_hex = material.hex()
    try:
        connection.execute(f"PRAGMA key = \"x'{raw_hex}'\"")
        connection.execute("PRAGMA cipher_compatibility=4")
        connection.execute("PRAGMA cipher_plaintext_header_size=0")
    finally:
        raw_hex = ""


def _connect_held(
    database: Path,
    *,
    project_id: str | None,
    create_key: bool = False,
    check_same_thread: bool = True,
    key_lease: DatabaseKeyLease | None = None,
) -> Any:
    parent_before = database.parent.stat(follow_symlinks=False)
    before = database.stat(follow_symlinks=False)
    configuration = _database_protection_configuration()
    protected = configuration.profile == SQLCIPHER_PROFILE
    if protected and configuration.provider is None:
        raise StorageProblem("protected database key authority is unavailable")
    if protected and project_id is None:
        raise StorageProblem("protected database project identity is required")
    descriptor: int | None = None
    handles: list[int] = []
    connection: Any = None
    try:
        descriptor = os.open(database, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or opened.st_nlink != 1:
            raise StorageProblem("database identity changed before open")
        header = os.read(descriptor, len(_SQLCIPHER_HEADER))
        os.lseek(descriptor, 0, os.SEEK_SET)
        if protected and not create_key and header == _SQLCIPHER_HEADER:
            raise StorageProblem("production profile rejected a plaintext project database")
        handles = _open_windows_guards(database.parent, database)
        parent_after = database.parent.stat(follow_symlinks=False)
        if (parent_after.st_dev, parent_after.st_ino) != (parent_before.st_dev, parent_before.st_ino) or _redirect(
            database.parent
        ):
            raise StorageProblem("database parent identity changed during open")
        uri = database.as_uri() + "?mode=rw"
        if protected:
            assert configuration.provider is not None
            assert project_id is not None
            key = configuration.provider.active_key(project_id, create=create_key) if key_lease is None else key_lease
            try:
                connection = sqlcipher.connect(
                    uri,
                    uri=True,
                    isolation_level=None,
                    timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
                    factory=_GuardedSqlCipherConnection,
                    check_same_thread=check_same_thread,
                )
                key.use(lambda material: _key_sqlcipher_connection(connection, material))
            finally:
                if key_lease is None:
                    key.close()
            connection.row_factory = sqlcipher.Row
        else:
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
    except (OSError, DatabaseKeyProblem, *_DATABASE_ERRORS) as error:
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
    except _DATABASE_ERRORS:
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
    configuration = _database_protection_configuration()
    if configuration.profile == SQLCIPHER_PROFILE and expected_project_id is None:
        raise StorageProblem("protected database project identity is required")
    if expected_project_id is not None:
        expected_project_id, _ = _project_identity(expected_project_id)
    connection = _connect_held(
        database,
        project_id=expected_project_id,
        check_same_thread=check_same_thread,
    )
    try:
        _configure_connection(
            connection,
            initialize=False,
            protected=configuration.profile == SQLCIPHER_PROFILE,
        )
        errors = _schema_profile_errors(connection, expected_project_id)
        if errors:
            raise StorageProblem("canonical database profile is incompatible")
        return CanonicalConnection(_CAPABILITY_REGISTRY.register_connection(connection))
    except (*_DATABASE_ERRORS, StorageProblem) as error:
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
    protection = database_protection_profile()
    cipher_version: str | None = None
    cipher_integrity: tuple[str, ...] = ()
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
        if protection == SQLCIPHER_PROFILE:
            version = connection.execute("PRAGMA cipher_version").fetchone()
            cipher_version = None if version is None else str(version[0])
            cipher_integrity = tuple(str(row[0]) for row in connection.execute("PRAGMA cipher_integrity_check"))
            if cipher_version is None or not cipher_version.startswith("4.12."):
                errors.append("cipher-version-mismatch")
            if cipher_integrity:
                errors.append("cipher-integrity-check-failed")
        if quick_check != ("ok",):
            errors.append("quick-check-failed")
        if foreign_key_violations:
            errors.append("foreign-key-check-failed")
        if journal_mode != "wal" or foreign_keys is not True:
            errors.append("connection-profile-mismatch")
    except _DATABASE_ERRORS:
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
        protection_profile=protection,
        cipher_version=cipher_version,
        cipher_integrity=cipher_integrity,
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
    connection: Any = None
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
        configuration = _database_protection_configuration()
        connection = _connect_held(database, project_id=project_id, create_key=True)
        _configure_connection(
            connection,
            initialize=True,
            protected=configuration.profile == SQLCIPHER_PROFILE,
        )
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
        os.lseek(descriptor, 0, os.SEEK_SET)
        header = os.read(descriptor, len(_SQLCIPHER_HEADER))
        if configuration.profile == SQLCIPHER_PROFILE and header == _SQLCIPHER_HEADER:
            raise StorageProblem("protected database initialization produced plaintext")
        succeeded = True
        return report
    except (OSError, *_DATABASE_ERRORS) as error:
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    payload = (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _create_exclusive_database_file(path: Path) -> None:
    if not path.is_absolute() or "\x00" in str(path):
        raise StorageProblem("protected database output path is invalid")
    parent = path.parent
    created = False
    valid = False
    descriptor: int | None = None
    try:
        if _redirect(parent) or not parent.is_dir() or parent.resolve(strict=True) != parent:
            raise StorageProblem("protected database output parent is unavailable or redirected")
        if path.exists() or _redirect(path):
            raise StorageProblem("protected database output already exists")
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        created = True
        opened = os.fstat(descriptor)
        visible = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or visible.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino)
        ):
            raise StorageProblem("protected database output identity is invalid")
        valid = True
    except StorageProblem:
        raise
    except OSError as error:
        raise StorageProblem("protected database output could not be created") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created and not valid:
            with suppress(OSError):
                path.unlink(missing_ok=True)


def _remove_database_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists() and sidecar.stat(follow_symlinks=False).st_size:
            raise StorageProblem("protected database retained live sidecar state")
        sidecar.unlink(missing_ok=True)


def _verify_protected_database_file(
    path: Path,
    project_id: str,
    key: DatabaseKeyLease,
    *,
    checkpoint: bool = False,
) -> None:
    connection = _connect_held(path, project_id=project_id, key_lease=key)
    try:
        _configure_connection(connection, initialize=False, protected=True)
        if _schema_profile_errors(connection, project_id):
            raise StorageProblem("protected database backup profile is incompatible")
        if tuple(str(row[0]) for row in connection.execute("PRAGMA cipher_integrity_check")):
            raise StorageProblem("protected database backup failed cipher integrity")
        if tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check")) != ("ok",):
            raise StorageProblem("protected database backup failed logical integrity")
        if tuple(connection.execute("PRAGMA foreign_key_check")):
            raise StorageProblem("protected database backup failed referential integrity")
        if checkpoint:
            connection.set_authorizer(_initialization_authorizer)
            result = tuple(int(value) for value in connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
            if result != (0, 0, 0):
                raise StorageProblem("protected database backup could not checkpoint")
    except (*_DATABASE_ERRORS,) as error:
        raise StorageProblem("protected database backup verification failed") from error
    finally:
        connection.close()
    _remove_database_sidecars(path)


def create_protected_database_backup(
    path: Path,
    destination: Path,
    *,
    project_id: str,
) -> ProtectedDatabaseBackupReport:
    """Create and verify one encrypted, self-contained SQLCipher database backup."""

    project_id, _ = _project_identity(project_id)
    database = _canonical_database_path(Path(path), must_exist=True)
    backup = Path(destination)
    if backup == database:
        raise StorageProblem("protected database backup cannot replace the canonical database")
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("protected database backup requires the production protection profile")
    _create_exclusive_database_file(backup)
    source: Any | None = None
    target: Any | None = None
    succeeded = False
    try:
        with configuration.provider.active_key(project_id, create=False) as key:
            source = _connect_held(database, project_id=project_id, key_lease=key)
            target = _connect_held(backup, project_id=project_id, key_lease=key)
            _configure_connection(source, initialize=False, protected=True)
            _configure_connection(target, initialize=True, protected=True)
            source.set_authorizer(_initialization_authorizer)
            checkpoint = tuple(int(value) for value in source.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone())
            if checkpoint[0] != 0 or checkpoint[1] != checkpoint[2]:
                raise StorageProblem("protected database source could not reach a backup checkpoint")
            source.backup(target, pages=256, sleep=0.01)
            target.set_authorizer(_initialization_authorizer)
            target_checkpoint = tuple(
                int(value) for value in target.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            )
            if target_checkpoint != (0, 0, 0):
                raise StorageProblem("protected database backup could not checkpoint")
            target.close()
            target = None
            source.close()
            source = None
            _verify_protected_database_file(backup, project_id, key)
        with backup.open("rb") as stream:
            if stream.read(len(_SQLCIPHER_HEADER)) == _SQLCIPHER_HEADER:
                raise StorageProblem("protected database backup unexpectedly contains plaintext")
        os.chmod(backup, 0o600)
        succeeded = True
        return ProtectedDatabaseBackupReport(
            protection_profile=SQLCIPHER_PROFILE,
            database_sha256=_file_sha256(backup),
            size_bytes=backup.stat(follow_symlinks=False).st_size,
        )
    except (*_DATABASE_ERRORS, OSError) as error:
        raise StorageProblem("protected database backup failed") from error
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()
        if not succeeded:
            for candidate in (backup, Path(str(backup) + "-wal"), Path(str(backup) + "-shm")):
                with suppress(OSError):
                    candidate.unlink(missing_ok=True)


def restore_protected_database_backup(
    backup_path: Path,
    path: Path,
    *,
    project_id: str,
    operation_id: str,
) -> ProtectedDatabaseRestoreReport:
    """Verify and atomically restore one protected database, rolling back on publication failure."""

    validate_database_key_identity(project_id, operation_id)
    database = _canonical_database_path(Path(path), must_exist=True)
    backup = Path(backup_path)
    try:
        backup_status = backup.stat(follow_symlinks=False)
        if (
            not backup.is_absolute()
            or _redirect(backup)
            or not stat.S_ISREG(backup_status.st_mode)
            or backup_status.st_nlink != 1
            or backup.resolve(strict=True) != backup
        ):
            raise StorageProblem("protected database backup authority is invalid")
    except StorageProblem:
        raise
    except OSError as error:
        raise StorageProblem("protected database backup authority is unavailable") from error
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("protected database restore requires the production protection profile")
    if _CAPABILITY_REGISTRY.has_open_connections():
        raise StorageProblem("protected database restore requires a quiescent Core database boundary")
    staging = database.parent.parent / ".tmp"
    if not staging.is_dir() or _redirect(staging) or staging.resolve(strict=True) != staging:
        raise StorageProblem("protected database restore staging authority is unavailable")
    candidate = staging / f"database-restore-{operation_id}.candidate.sqlite3"
    quarantine = staging / f"database-restore-{operation_id}.displaced.sqlite3"
    failed = staging / f"database-restore-{operation_id}.failed.sqlite3"
    if candidate.exists() or quarantine.exists() or failed.exists():
        raise StorageProblem("protected database restore artifacts already exist")
    with configuration.provider.active_key(project_id, create=False) as key:
        _verify_protected_database_file(backup, project_id, key)
        _verify_protected_database_file(database, project_id, key, checkpoint=True)
        before_sha256 = _file_sha256(database)
        _create_exclusive_database_file(candidate)
        try:
            shutil.copyfile(backup, candidate)
            with candidate.open("r+b") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            _verify_protected_database_file(candidate, project_id, key)
            restored_sha256 = _file_sha256(candidate)
            os.replace(database, quarantine)
            try:
                os.replace(candidate, database)
                verified = _open_with_key_lease(database, project_id, key)
                verified.close()
            except BaseException:
                try:
                    if database.exists():
                        os.replace(database, failed)
                    os.replace(quarantine, database)
                except OSError as rollback_error:
                    raise StorageProblem("protected database restore requires manual recovery") from rollback_error
                with suppress(OSError):
                    failed.unlink(missing_ok=True)
                raise
            try:
                quarantine.unlink()
                outcome = "restored"
            except OSError:
                outcome = "restored-displaced-ciphertext-retained"
            return ProtectedDatabaseRestoreReport(
                operation_id=operation_id,
                outcome=outcome,
                restored_database_sha256=restored_sha256,
                displaced_database_sha256=before_sha256,
            )
        except (*_DATABASE_ERRORS, OSError) as error:
            raise StorageProblem("protected database restore failed") from error
        finally:
            with suppress(OSError):
                candidate.unlink(missing_ok=True)


def _rekey_paths(database: Path, operation_id: str) -> tuple[Path, Path, Path]:
    project = database.parent.parent
    staging = project / ".tmp"
    if not staging.is_dir() or _redirect(staging) or staging.resolve(strict=True) != staging:
        raise StorageProblem("database rekey staging authority is unavailable")
    manifest = staging / f"database-rekey-{operation_id}.json"
    backup = staging / f"database-rekey-{operation_id}.backup.sqlite3"
    quarantine = staging / f"database-rekey-{operation_id}.unrecoverable.sqlite3"
    return manifest, backup, quarantine


def _open_with_key_lease(database: Path, project_id: str, key: DatabaseKeyLease) -> Any:
    connection = _connect_held(database, project_id=project_id, key_lease=key)
    try:
        _configure_connection(connection, initialize=False, protected=True)
        if _schema_profile_errors(connection, project_id):
            raise StorageProblem("protected database profile is incompatible")
        return connection
    except BaseException:
        connection.close()
        raise


def rekey_protected_database(
    path: Path,
    *,
    project_id: str,
    operation_id: str,
    failure_hook: Callable[[str], None] | None = None,
) -> DatabaseRekeyReport:
    """Rekey one protected database with an encrypted rollback copy and resumable key activation."""

    validate_database_key_identity(project_id, operation_id)
    database = _canonical_database_path(Path(path), must_exist=True)
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("database rekey requires the protected production profile")
    manifest, backup, _quarantine = _rekey_paths(database, operation_id)
    if manifest.exists() or backup.exists():
        return recover_protected_database_rekey(database, project_id=project_id, operation_id=operation_id)

    provider = configuration.provider
    with provider.active_key(project_id, create=False) as active:
        previous_version = active.version
    with provider.staged_rekey(project_id, operation_id, create=True) as staged:
        staged_version = staged.version

    connection = _connect_held(database, project_id=project_id)
    backup_sha256 = ""
    try:
        _configure_connection(connection, initialize=False, protected=True)
        connection.set_authorizer(_initialization_authorizer)
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise StorageProblem("protected database could not reach a rekey checkpoint")
        shutil.copyfile(database, backup)
        os.chmod(backup, 0o600)
        with backup.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        backup_sha256 = _file_sha256(backup)
        document = {
            "schemaVersion": "1.0",
            "documentType": "research-observatory-database-rekey-recovery",
            "projectId": project_id,
            "operationId": operation_id,
            "database": "state/project.sqlite3",
            "backup": f".tmp/{backup.name}",
            "backupSha256": backup_sha256,
            "previousKeyVersion": previous_version,
            "stagedKeyVersion": staged_version,
            "state": "prepared",
        }
        _atomic_json(manifest, document)
        if failure_hook is not None:
            failure_hook("after-prepared")
        with provider.staged_rekey(project_id, operation_id, create=False) as staged:
            staged.use(lambda material: _rekey_sqlcipher_connection(connection, material))
        document["state"] = "database-rekeyed"
        _atomic_json(manifest, document)
        if failure_hook is not None:
            failure_hook("after-database-rekeyed")
    except BaseException:
        raise
    finally:
        connection.close()

    with provider.staged_rekey(project_id, operation_id, create=False) as staged:
        candidate = _open_with_key_lease(database, project_id, staged)
        try:
            if tuple(str(row[0]) for row in candidate.execute("PRAGMA cipher_integrity_check")):
                raise StorageProblem("protected database failed integrity after rekey")
        finally:
            candidate.close()
    active_version = provider.activate_rekey(
        project_id,
        operation_id,
        expected_active_version=previous_version,
    )
    document["state"] = "key-activated"
    document["activeKeyVersion"] = active_version
    _atomic_json(manifest, document)
    if failure_hook is not None:
        failure_hook("after-key-activated")
    verified = open_canonical_database(database, expected_project_id=project_id)
    verified.close()
    backup.unlink()
    manifest.unlink()
    return DatabaseRekeyReport(operation_id, "rekeyed", previous_version, active_version, backup_sha256)


def _rekey_sqlcipher_connection(connection: Any, material: memoryview) -> None:
    if len(material) != 32:
        raise StorageProblem("staged database key material is invalid")
    raw_hex = material.hex()
    try:
        connection.execute(f"PRAGMA rekey = \"x'{raw_hex}'\"")
    finally:
        raw_hex = ""


def recover_protected_database_rekey(
    path: Path,
    *,
    project_id: str,
    operation_id: str,
) -> DatabaseRekeyReport:
    """Resolve an interrupted rekey by proving the active key, staged key, or encrypted backup."""

    validate_database_key_identity(project_id, operation_id)
    database = _canonical_database_path(Path(path), must_exist=True)
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("database rekey recovery requires the protected production profile")
    manifest, backup, quarantine = _rekey_paths(database, operation_id)
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StorageProblem("database rekey recovery manifest is unavailable") from error
    if (
        not isinstance(document, dict)
        or document.get("projectId") != project_id
        or document.get("operationId") != operation_id
        or document.get("database") != "state/project.sqlite3"
        or document.get("backup") != f".tmp/{backup.name}"
        or not isinstance(document.get("backupSha256"), str)
        or not isinstance(document.get("previousKeyVersion"), str)
    ):
        raise StorageProblem("database rekey recovery manifest is invalid")
    backup_sha256 = str(document["backupSha256"])
    previous_version = str(document["previousKeyVersion"])
    provider = configuration.provider

    try:
        connection = open_canonical_database(database, expected_project_id=project_id)
    except StorageProblem:
        connection = None
    if connection is not None:
        connection.close()
        with provider.active_key(project_id, create=False) as active:
            active_version = active.version
        backup.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        return DatabaseRekeyReport(
            operation_id, "active-key-confirmed", previous_version, active_version, backup_sha256
        )

    staged_valid = False
    try:
        with provider.staged_rekey(project_id, operation_id, create=False) as staged:
            candidate = _open_with_key_lease(database, project_id, staged)
            candidate.close()
            staged_valid = True
    except DatabaseKeyProblem, StorageProblem:
        staged_valid = False
    if staged_valid:
        try:
            active_version = provider.activate_rekey(
                project_id,
                operation_id,
                expected_active_version=previous_version,
            )
        except DatabaseKeyConflict:
            with provider.active_key(project_id, create=False) as active:
                active_version = active.version
        verified = open_canonical_database(database, expected_project_id=project_id)
        verified.close()
        backup.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        return DatabaseRekeyReport(
            operation_id, "staged-key-activated", previous_version, active_version, backup_sha256
        )

    if not backup.is_file() or _file_sha256(backup) != backup_sha256:
        raise StorageProblem("database rekey recovery backup is invalid")
    if quarantine.exists():
        raise StorageProblem("database rekey recovery quarantine already exists")
    os.replace(database, quarantine)
    shutil.copyfile(backup, database)
    os.chmod(database, 0o600)
    restored = open_canonical_database(database, expected_project_id=project_id)
    restored.close()
    with provider.active_key(project_id, create=False) as active:
        active_version = active.version
    backup.unlink(missing_ok=True)
    manifest.unlink(missing_ok=True)
    return DatabaseRekeyReport(
        operation_id, "encrypted-backup-restored", previous_version, active_version, backup_sha256
    )


_PLAINTEXT_MIGRATION_APPROVAL = "approve-plaintext-to-protected-v1"


def _migration_paths(database: Path, operation_id: str) -> tuple[Path, Path, Path]:
    project = database.parent.parent
    staging = project / ".tmp"
    if not staging.is_dir() or _redirect(staging) or staging.resolve(strict=True) != staging:
        raise StorageProblem("database protection migration staging authority is unavailable")
    manifest = staging / f"database-protection-migration-{operation_id}.json"
    target = staging / f"database-protection-migration-{operation_id}.sqlcipher"
    rollback = staging / f"database-protection-migration-{operation_id}.plaintext-rollback"
    return manifest, target, rollback


def _verify_plaintext_source(database: Path, project_id: str) -> Any:
    with database.open("rb") as stream:
        if stream.read(len(_SQLCIPHER_HEADER)) != _SQLCIPHER_HEADER:
            raise StorageProblem("legacy database is not a plaintext SQLite source")
    source = sqlcipher.connect(
        database.as_uri() + "?mode=ro",
        uri=True,
        isolation_level=None,
        timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
    )
    try:
        source.row_factory = sqlcipher.Row
        source.enable_load_extension(False)
        source.execute("PRAGMA trusted_schema=OFF")
        source.execute("PRAGMA foreign_keys=ON")
        if _schema_profile_errors(source, project_id):
            raise StorageProblem("legacy plaintext database profile is incompatible")
        report = tuple(str(row[0]) for row in source.execute("PRAGMA quick_check"))
        if report != ("ok",) or tuple(source.execute("PRAGMA foreign_key_check")):
            raise StorageProblem("legacy plaintext database failed integrity")
        return source
    except BaseException:
        source.close()
        raise


def _export_plaintext_to_protected(
    source: Any,
    target: Path,
    key: DatabaseKeyLease,
) -> None:
    if target.exists() or _redirect(target):
        raise StorageProblem("protected migration target already exists")

    def export(material: memoryview) -> None:
        if len(material) != 32:
            raise StorageProblem("protected database key material is invalid")
        key_literal = f"x'{material.hex()}'"
        attached = False
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(target), key_literal))
            attached = True
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={APPLICATION_ID}")
            source.execute(f"PRAGMA protected.user_version={DATABASE_SCHEMA_VERSION}")
            source.execute("DETACH DATABASE protected")
            attached = False
        finally:
            key_literal = ""
            if attached:
                with suppress(sqlcipher.Error):
                    source.execute("DETACH DATABASE protected")

    key.use(export)


def _verify_protected_candidate(target: Path, project_id: str, key: DatabaseKeyLease) -> None:
    connection = _connect_held(target, project_id=project_id, key_lease=key)
    try:
        _configure_connection(connection, initialize=True, protected=True)
        errors = _schema_profile_errors(connection, project_id)
        if errors:
            raise StorageProblem(f"protected migration target profile is incompatible: {','.join(errors)}")
        if tuple(str(row[0]) for row in connection.execute("PRAGMA cipher_integrity_check")):
            raise StorageProblem("protected migration target failed cipher integrity")
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise StorageProblem("protected migration target could not checkpoint")
    finally:
        connection.close()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(target) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise StorageProblem("protected migration target retained live sidecar state")
        sidecar.unlink(missing_ok=True)


def _cleanup_plaintext_rollback(path: Path) -> str:
    if not path.exists():
        return "not-present"
    try:
        os.chmod(path, 0o600)
        size = path.stat(follow_symlinks=False).st_size
        with path.open("r+b", buffering=0) as stream:
            block = b"\0" * (1024 * 1024)
            remaining = size
            while remaining:
                chunk = min(remaining, len(block))
                stream.write(block[:chunk])
                remaining -= chunk
            stream.flush()
            os.fsync(stream.fileno())
        path.unlink()
        return "best-effort-overwrite-and-unlink"
    except OSError:
        with suppress(OSError):
            os.chmod(path, 0o400)
        return "cleanup-pending-read-only"


def migrate_plaintext_database_to_protected(
    path: Path,
    *,
    project_id: str,
    operation_id: str,
    approval_token: str,
    failure_hook: Callable[[str], None] | None = None,
) -> DatabaseProtectionMigrationReport:
    """Copy a validated read-only legacy database into SQLCipher and atomically publish it."""

    validate_database_key_identity(project_id, operation_id)
    if approval_token != _PLAINTEXT_MIGRATION_APPROVAL:
        raise StorageProblem("plaintext database migration requires explicit approval")
    database = _canonical_database_path(Path(path), must_exist=True)
    configuration = _database_protection_configuration()
    if configuration.profile != SQLCIPHER_PROFILE or configuration.provider is None:
        raise StorageProblem("plaintext migration requires the protected production profile")
    manifest, target, rollback = _migration_paths(database, operation_id)
    if manifest.exists():
        return recover_plaintext_database_migration(database, project_id=project_id, operation_id=operation_id)
    if target.exists() or rollback.exists():
        raise StorageProblem("unbound database protection migration artifacts exist")

    source = _verify_plaintext_source(database, project_id)
    try:
        source_sha256 = _file_sha256(database)
        with configuration.provider.active_key(project_id, create=True) as key:
            _export_plaintext_to_protected(source, target, key)
            _verify_protected_candidate(target, project_id, key)
        target_sha256 = _file_sha256(target)
        document = {
            "schemaVersion": "1.0",
            "documentType": "research-observatory-database-protection-migration",
            "projectId": project_id,
            "operationId": operation_id,
            "source": "state/project.sqlite3",
            "target": f".tmp/{target.name}",
            "rollback": f".tmp/{rollback.name}",
            "plaintextSourceSha256": source_sha256,
            "protectedTargetSha256": target_sha256,
            "state": "prepared",
        }
        _atomic_json(manifest, document)
        if failure_hook is not None:
            failure_hook("after-prepared")
    finally:
        source.close()

    os.chmod(database, 0o400)
    os.replace(database, rollback)
    document["state"] = "source-staged"
    _atomic_json(manifest, document)
    if failure_hook is not None:
        failure_hook("after-source-staged")
    os.replace(target, database)
    document["state"] = "protected-published"
    _atomic_json(manifest, document)
    if failure_hook is not None:
        failure_hook("after-protected-published")
    verified = open_canonical_database(database, expected_project_id=project_id)
    verified.close()
    cleanup = _cleanup_plaintext_rollback(rollback)
    if cleanup.startswith("cleanup-pending"):
        document["state"] = cleanup
        _atomic_json(manifest, document)
    else:
        manifest.unlink()
    return DatabaseProtectionMigrationReport(operation_id, "protected", source_sha256, target_sha256, cleanup)


def recover_plaintext_database_migration(
    path: Path,
    *,
    project_id: str,
    operation_id: str,
) -> DatabaseProtectionMigrationReport:
    """Resume or safely roll back an interrupted plaintext-to-SQLCipher publication."""

    validate_database_key_identity(project_id, operation_id)
    database = Path(path)
    manifest, target, rollback = _migration_paths(database, operation_id)
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StorageProblem("database protection migration manifest is unavailable") from error
    if (
        not isinstance(document, dict)
        or document.get("projectId") != project_id
        or document.get("operationId") != operation_id
        or document.get("source") != "state/project.sqlite3"
        or document.get("target") != f".tmp/{target.name}"
        or document.get("rollback") != f".tmp/{rollback.name}"
        or not isinstance(document.get("plaintextSourceSha256"), str)
        or not isinstance(document.get("protectedTargetSha256"), str)
    ):
        raise StorageProblem("database protection migration manifest is invalid")
    source_sha256 = str(document["plaintextSourceSha256"])
    target_sha256 = str(document["protectedTargetSha256"])

    try:
        verified = open_canonical_database(database, expected_project_id=project_id)
    except OSError, StorageProblem:
        verified = None
    if verified is not None:
        verified.close()
        cleanup = _cleanup_plaintext_rollback(rollback)
        target.unlink(missing_ok=True)
        if cleanup.startswith("cleanup-pending"):
            document["state"] = cleanup
            _atomic_json(manifest, document)
        else:
            manifest.unlink(missing_ok=True)
        return DatabaseProtectionMigrationReport(
            operation_id, "protected-recovered", source_sha256, target_sha256, cleanup
        )

    configuration = _database_protection_configuration()
    if configuration.provider is None:
        raise StorageProblem("database protection migration key is unavailable")
    target_valid = target.is_file() and _file_sha256(target) == target_sha256
    if target_valid:
        try:
            with configuration.provider.active_key(project_id, create=False) as key:
                _verify_protected_candidate(target, project_id, key)
        except DatabaseKeyProblem, StorageProblem:
            target_valid = False
    if target_valid:
        if database.exists():
            with database.open("rb") as stream:
                header = stream.read(len(_SQLCIPHER_HEADER))
            if header != _SQLCIPHER_HEADER:
                raise StorageProblem("migration recovery found an unknown canonical database")
            if rollback.exists():
                raise StorageProblem("migration recovery found competing plaintext sources")
            os.chmod(database, 0o400)
            os.replace(database, rollback)
        if not rollback.is_file() or _file_sha256(rollback) != source_sha256:
            raise StorageProblem("migration recovery plaintext rollback is invalid")
        os.replace(target, database)
        verified = open_canonical_database(database, expected_project_id=project_id)
        verified.close()
        cleanup = _cleanup_plaintext_rollback(rollback)
        if cleanup.startswith("cleanup-pending"):
            document["state"] = cleanup
            _atomic_json(manifest, document)
        else:
            manifest.unlink(missing_ok=True)
        return DatabaseProtectionMigrationReport(
            operation_id, "protected-recovered", source_sha256, target_sha256, cleanup
        )

    target.unlink(missing_ok=True)
    if rollback.is_file() and _file_sha256(rollback) == source_sha256 and not database.exists():
        os.replace(rollback, database)
        os.chmod(database, 0o600)
    if not database.is_file() or _file_sha256(database) != source_sha256:
        raise StorageProblem("database protection migration cannot restore the plaintext source")
    manifest.unlink(missing_ok=True)
    return DatabaseProtectionMigrationReport(
        operation_id, "plaintext-restored", source_sha256, target_sha256, "retained"
    )
