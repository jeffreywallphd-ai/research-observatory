"""Protected FTS5 derivative and same-database revision-bound text mirror."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]

from .lexical_index_io import IndexFileGuard, IndexPathProblem, _bootstrap_step
from .parsing.normalization import MAX_IR_BYTES
from .ports.database_keys import validate_database_key_identity
from .ports.derivative_keys import (
    DerivativeKeyLease,
    DerivativeKeyProblem,
    DerivativeKeyProvider,
    DerivativeKeyScope,
    DerivativePurpose,
)
from .search.compiler import compile_query
from .search.contracts import ANALYZER_ID, QueryDocument
from .storage import (
    StorageProblem,
    _configure_connection,
    _database_uri,
    _key_sqlcipher_connection,
)

_COLUMNS = ("title", "abstract", "full_text", "authors", "venue", "identifiers", "tags", "decisions")
_APPLICATION_ID = 0x524F4958
_MAX_BATCH = 256
_MAX_UNIVERSE = 100_000
_MAX_SEQUENCE = 9_007_199_254_740_991
_ERRORS = (sqlcipher.Error, sqlite3.Error, OSError, StorageProblem, DerivativeKeyProblem, IndexPathProblem)


class LexicalStoreProblem(RuntimeError):
    """Bounded derivative failure; callers preserve canonical source authority."""


class LexicalIndexCancelled(LexicalStoreProblem):
    """The bounded operation stopped; it does not authorize pointer promotion."""


@dataclass(frozen=True, slots=True)
class IndexProjection:
    checkpoint: int
    entry_count: int
    rows_sha256: str
    manifest_sha256: str


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def projection_manifest(scope: DerivativeKeyScope, key_version: str, projection: IndexProjection) -> str:
    return _sha(
        {
            "scope": asdict(scope),
            "keyVersion": key_version,
            "analyzer": ANALYZER_ID,
            "derivativeSchemaVersion": 1,
            "checkpoint": projection.checkpoint,
            "entryCount": projection.entry_count,
            "rowsSha256": projection.rows_sha256,
        }
    )


def _hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True, slots=True)
class IndexRow:
    entry_id: str
    item_id: str
    work_id: str
    work_revision_id: str
    source_revision_id: str
    authority_sha256: str
    document_revision_id: str | None = None
    element_id: str | None = None
    projection_id: str | None = None
    normalized_start: int | None = None
    normalized_end: int | None = None
    year: int | None = None
    title: str = field(default="", repr=False)
    abstract: str = field(default="", repr=False)
    full_text: str = field(default="", repr=False)
    authors: str = field(default="", repr=False)
    venue: str = field(default="", repr=False)
    identifiers: str = field(default="", repr=False)
    tags: str = field(default="", repr=False)
    decisions: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        for value in (self.item_id, self.work_id, self.work_revision_id, self.source_revision_id):
            validate_database_key_identity(value)
        for optional_id in (self.document_revision_id, self.element_id, self.projection_id):
            if optional_id is not None:
                validate_database_key_identity(optional_id)
        if (
            not _hash(self.entry_id)
            or not _hash(self.authority_sha256)
            or (self.year is not None and (type(self.year) is not int or not 1 <= self.year <= 9999))
            or (self.element_id is not None and self.document_revision_id is None)
            or ((self.projection_id is None) != (self.normalized_start is None))
            or ((self.projection_id is None) != (self.normalized_end is None))
            or (
                self.projection_id is not None
                and (
                    self.element_id is None
                    or type(self.normalized_start) is not int
                    or type(self.normalized_end) is not int
                    or not 0 <= self.normalized_start <= self.normalized_end <= _MAX_SEQUENCE
                    or self.normalized_end - self.normalized_start != len(self.full_text)
                )
            )
        ):
            raise ValueError("index row binding is invalid")
        total = 0
        try:
            for column in _COLUMNS:
                value = getattr(self, column)
                if not isinstance(value, str) or "\0" in value:
                    raise ValueError("index row text is invalid")
                total += len(value.encode("utf-8", errors="strict"))
        except UnicodeError:
            raise ValueError("index row text is invalid") from None
        if total > MAX_IR_BYTES:
            raise ValueError("index row text budget exceeded")


def _authorizer(action: int, arg1: str | None, arg2: str | None, _database: str | None, _trigger: str | None) -> int:
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in {"load_extension", "writefile", "readfile"}:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and arg2 is not None:
        return sqlite3.SQLITE_DENY
    if action in (
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_VTABLE,
    ):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class ProtectedLexicalStore:
    """Internal adapter. Only the canonical search service grants row authority.

    It exposes commands and typed snapshots, never raw SQL or key material.
    Derivative commit/checkpoint is atomic locally; canonical acknowledgement is
    a separate idempotent operation owned by the generation coordinator.
    """

    def __init__(
        self,
        root: Path,
        scope: DerivativeKeyScope,
        keys: DerivativeKeyProvider,
        *,
        create: bool = False,
        cancelled: Callable[[], bool] = lambda: False,
        _bootstrap: Callable[[dict[str, tuple[int, int]]], None] | None = None,
        _retirement: tuple[str, Callable[[tuple[int, int]], None]] | None = None,
    ) -> None:
        self._db: Any = None
        self._guard: IndexFileGuard | None = None
        self._key = None
        self._scope = scope
        self._closed = False
        self._journal_bound = False
        self._cancelled = cancelled
        self._was_cancelled = False
        self._retirement = _retirement
        try:
            if (
                not isinstance(scope, DerivativeKeyScope)
                or type(create) is not bool
                or not isinstance(keys, DerivativeKeyProvider)
                or not callable(cancelled)
            ):
                raise LexicalStoreProblem("index request is invalid")
            self._check_cancel()
            scope.__post_init__()
            if scope.purpose is not DerivativePurpose.LEXICAL:
                raise LexicalStoreProblem("index purpose is invalid")
            if _retirement is not None:
                if create:
                    raise LexicalStoreProblem("retired recovery cannot create an index")
                self._guard = IndexFileGuard(root, scope.generation_id, create=False, recovery_probe=True)
                # Canonical ownership of the held main file is checked before
                # leasing historical material or opening SQLCipher/replaying WAL.
                self._retirement_current()
                self._key = keys.lease_for_retirement(
                    scope, expected_version=_retirement[0], authorize=self._retirement_current
                )
                probe = self._guard
                self._guard = IndexFileGuard(root, scope.generation_id, create=False)
                probe.close(clean_sidecars=False)
            else:
                self._key = keys.lease(scope, create=create)
            if not isinstance(self._key, DerivativeKeyLease):
                raise LexicalStoreProblem("index key purpose is invalid")
            if self._guard is None:
                self._guard = IndexFileGuard(root, scope.generation_id, create=create, bootstrap=_bootstrap)
            self._db = sqlcipher.connect(_database_uri(self._guard.path), uri=True, isolation_level=None)
            self._key.use(scope, lambda material: _key_sqlcipher_connection(self._db, material))
            self._db.set_progress_handler(self._progress, 1000)
            # New empty DB only: no filesystem rollback journal, even
            # during the initial transition to the required WAL profile.
            if create and self._db.execute("PRAGMA journal_mode=MEMORY").fetchone() != ("memory",):
                raise LexicalStoreProblem("index bootstrap confinement is unavailable")
            _configure_connection(self._db, initialize=create, protected=True)
            # The shared profile helper installs canonical-only schema denial
            # for reopened project DBs. This private derivative initializer
            # replaces it with its own policy after creating memory tables.
            self._db.set_authorizer(None)
            self._db.execute("PRAGMA temp_store=MEMORY")
            if self._db.execute("PRAGMA temp_store").fetchone()[0] != 2:
                raise LexicalStoreProblem("index temporary confinement is unavailable")
            if create:
                self._initialize()
            self._validate_manifest()
            self._db.execute("CREATE TEMP TABLE allowed_entries(entry_id TEXT PRIMARY KEY) WITHOUT ROWID")
            self._db.execute("CREATE TEMP TABLE allowed_items(item_id TEXT PRIMARY KEY) WITHOUT ROWID")
            self._db.set_authorizer(_authorizer)
            self._current()
            self.integrity_check()
        except BaseException as error:
            self.close()
            if self._was_cancelled:
                raise LexicalIndexCancelled("index operation cancelled") from None
            if not isinstance(error, Exception):
                raise
            raise LexicalStoreProblem("protected index is unavailable") from None

    def _check_cancel(self) -> None:
        try:
            requested = self._cancelled()
        except Exception:
            requested = True
        if requested is not False:
            self._was_cancelled = True
            raise LexicalIndexCancelled("index operation cancelled")

    def _retirement_current(self) -> None:
        try:
            if self._retirement is None or self._guard is None:
                raise LexicalStoreProblem("retired recovery authority is unavailable")
            self._retirement[1](self._guard.file_identity)
        except Exception:
            raise LexicalStoreProblem("retired recovery authority is unavailable") from None

    def _require_search(self) -> None:
        if self._retirement is not None:
            raise LexicalStoreProblem("retired recovery cannot read or change search data")

    def _progress(self) -> int:
        try:
            self._check_cancel()
            return 0
        except LexicalIndexCancelled:
            return 1

    def _rollback(self) -> None:
        # Cancellation must never interrupt the operation that releases its
        # own transaction. Restore bounded cancellation for the next command.
        self._db.set_progress_handler(None, 0)
        try:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
        finally:
            self._db.set_progress_handler(self._progress, 1000)

    def _initialize(self) -> None:
        assert self._key is not None
        assert self._guard is not None
        self._db.execute("BEGIN IMMEDIATE")
        try:
            _bootstrap_step("schema-transaction-open")
            self._db.execute(
                "CREATE TABLE index_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),scope_json TEXT NOT "
                "NULL,key_version TEXT NOT NULL,analyzer TEXT NOT NULL,checkpoint INTEGER NOT NULL "
                "CHECK(checkpoint>=0),last_batch_sha256 TEXT,journal_identity TEXT NOT NULL,sealed INTEGER NOT "
                "NULL CHECK(sealed IN (0,1))) STRICT"
            )
            self._db.execute(
                "CREATE TABLE search_rows(rowid INTEGER PRIMARY KEY,entry_id TEXT UNIQUE NOT NULL,item_id TEXT "
                "NOT NULL,work_id TEXT NOT NULL,work_revision_id TEXT NOT NULL,source_revision_id TEXT NOT "
                "NULL,authority_sha256 TEXT NOT NULL,document_revision_id TEXT,element_id TEXT,projection_id "
                "TEXT,normalized_start INTEGER,normalized_end INTEGER,year INTEGER,title TEXT NOT NULL,abstract "
                "TEXT NOT NULL,full_text TEXT NOT NULL,authors TEXT NOT NULL,venue TEXT NOT NULL,identifiers "
                "TEXT NOT NULL,tags TEXT NOT NULL,decisions TEXT NOT NULL,row_sha256 TEXT NOT NULL) STRICT"
            )
            self._db.execute("CREATE INDEX search_rows_item ON search_rows(item_id)")
            self._db.execute(
                "CREATE VIRTUAL TABLE search_fts USING "
                "fts5(title,abstract,full_text,authors,venue,identifiers,tags,decisions,content='search_rows',con"
                "tent_rowid='rowid',tokenize='unicode61 remove_diacritics 2')"
            )
            self._db.execute(
                "INSERT INTO index_state VALUES(1,?,?,?,0,NULL,?,0)",
                (self._scope_json(), self._key.version, ANALYZER_ID, self._guard.journal_identity),
            )
            self._db.execute(f"PRAGMA application_id={_APPLICATION_ID}")
            self._db.execute("PRAGMA user_version=1")
            _bootstrap_step("schema-before-commit")
            self._db.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def _scope_json(self) -> str:
        return json.dumps(asdict(self._scope), sort_keys=True, separators=(",", ":"))

    def _validate_manifest(self) -> None:
        assert self._key is not None
        assert self._guard is not None
        row = self._db.execute(
            "SELECT scope_json,key_version,analyzer,checkpoint,journal_identity FROM index_state WHERE singleton=1"
        ).fetchone()
        if (
            self._db.execute("PRAGMA application_id").fetchone()[0] != _APPLICATION_ID
            or self._db.execute("PRAGMA user_version").fetchone()[0] != 1
            or row is None
            or row[:3] != (self._scope_json(), self._key.version, ANALYZER_ID)
            or type(row[3]) is not int
            or not 0 <= row[3] <= _MAX_SEQUENCE
        ):
            raise LexicalStoreProblem("index manifest is invalid")
        if row[4] != self._guard.journal_identity:
            if self._journal_bound or not self._guard.journal_created:
                raise LexicalStoreProblem("index recovery journal binding is invalid")
            # Clean shutdown removed the old empty sentinel. Authenticate the
            # protected scope first, then bind the new exclusively created one.
            self._db.execute(
                "UPDATE index_state SET journal_identity=? WHERE singleton=1", (self._guard.journal_identity,)
            )
        self._journal_bound = True

    def _current(self) -> None:
        if self._closed or self._guard is None or self._key is None:
            raise LexicalStoreProblem("index is closed")
        self._check_cancel()
        self._guard.check()
        self._key.assert_current(self._scope)

    @property
    def checkpoint(self) -> int:
        self._require_search()
        try:
            self._current()
            return self._db.execute("SELECT checkpoint FROM index_state WHERE singleton=1").fetchone()[0]
        except _ERRORS:
            raise LexicalStoreProblem("index checkpoint is unavailable") from None

    def connection_profile(self) -> dict[str, int]:
        self._require_search()
        return {
            name: self._db.execute("PRAGMA " + name).fetchone()[0]
            for name in ("temp_store", "trusted_schema", "foreign_keys", "synchronous")
        }

    def _write_rows(self, rows: tuple[IndexRow, ...], removed: tuple[str, ...]) -> None:
        for entry in (*removed, *(row.entry_id for row in rows)):
            prior = self._db.execute(
                "SELECT rowid," + ",".join(_COLUMNS) + " FROM search_rows WHERE entry_id=?", (entry,)
            ).fetchone()
            if prior is not None:
                self._db.execute(
                    "INSERT INTO search_fts(search_fts,rowid,"
                    + ",".join(_COLUMNS)
                    + ") VALUES('delete',"
                    + ",".join("?" for _ in prior)
                    + ")",
                    prior,
                )
                self._db.execute("DELETE FROM search_rows WHERE entry_id=?", (entry,))
        for row in rows:
            values = asdict(row)
            values["row_sha256"] = _sha(values)
            names = tuple(values)
            cursor = self._db.execute(
                "INSERT INTO search_rows(" + ",".join(names) + ") VALUES(" + ",".join("?" for _ in names) + ")",
                tuple(values.values()),
            )
            self._db.execute(
                "INSERT INTO search_fts(rowid,"
                + ",".join(_COLUMNS)
                + ") VALUES("
                + ",".join("?" for _ in range(9))
                + ")",
                (cursor.lastrowid, *(getattr(row, column) for column in _COLUMNS)),
            )

    def _validate_batch(
        self, rows: tuple[IndexRow, ...], removed: tuple[str, ...], *, allow_projection: bool = False
    ) -> None:
        if (
            type(rows) is not tuple
            or type(removed) is not tuple
            or len(rows) + len(removed) > _MAX_BATCH
            or len({row.entry_id for row in rows if isinstance(row, IndexRow)}) != len(rows)
            or any(not _hash(entry) for entry in removed)
        ):
            raise LexicalStoreProblem("index batch is invalid")
        total = 0
        for row in rows:
            row.__post_init__()
            total += sum(len(getattr(row, column).encode("utf-8")) for column in _COLUMNS)
        complete_projection = (
            allow_projection
            and len(rows) == 1
            and not removed
            and rows[0].document_revision_id is not None
            and rows[0].projection_id is not None
            and rows[0].element_id == rows[0].projection_id
            and rows[0].normalized_start == 0
            and rows[0].normalized_end == len(rows[0].full_text)
            and all(not getattr(rows[0], name) for name in _COLUMNS if name != "full_text")
        )
        if total > 4 * 1024 * 1024 and not complete_projection:
            raise LexicalStoreProblem("index batch byte budget exceeded")

    def entry_ids(self, item_id: str, *, limit: int = _MAX_UNIVERSE) -> tuple[str, ...]:
        """Bounded internal binding inventory, without protected text."""
        self._require_search()
        try:
            validate_database_key_identity(item_id)
            if type(limit) is not int or not 1 <= limit <= _MAX_UNIVERSE:
                raise LexicalStoreProblem("index inventory limit is invalid")
            self._current()
            rows = self._db.execute(
                "SELECT entry_id FROM search_rows WHERE item_id=? ORDER BY entry_id LIMIT ?", (item_id, limit)
            ).fetchall()
            self._current()
            return tuple(row[0] for row in rows)
        except (*_ERRORS, ValueError):
            raise LexicalStoreProblem("index inventory is unavailable") from None

    @property
    def sealed(self) -> bool:
        self._require_search()
        self._current()
        row = self._db.execute("SELECT sealed FROM index_state WHERE singleton=1").fetchone()
        if row not in ((0,), (1,)):
            raise LexicalStoreProblem("index seal is invalid")
        return row == (1,)

    @property
    def file_identity(self) -> tuple[int, int]:
        self._current()
        assert self._guard is not None
        return self._guard.file_identity

    @property
    def file_identities(self) -> dict[str, tuple[int, int]]:
        self._current()
        assert self._guard is not None
        return self._guard.file_identities

    def item_matches(self, item_id: str, rows: tuple[IndexRow, ...]) -> bool:
        self._require_search()
        self._current()
        validate_database_key_identity(item_id)
        expected = tuple(sorted((row.entry_id, _sha(asdict(row))) for row in rows))
        actual = tuple(
            self._db.execute(
                "SELECT entry_id,row_sha256 FROM search_rows WHERE item_id=? ORDER BY entry_id", (item_id,)
            )
        )
        self._current()
        return actual == expected

    def stage(self, rows: tuple[IndexRow, ...], removed: tuple[str, ...]) -> None:
        """Idempotent bounded shadow chunks; never advance a source checkpoint."""
        self._require_search()
        self._was_cancelled = False
        try:
            self._validate_batch(rows, removed, allow_projection=True)
            self._current()
            self._db.execute("BEGIN IMMEDIATE")
            if self._db.execute("SELECT checkpoint,sealed FROM index_state WHERE singleton=1").fetchone() != (0, 0):
                raise LexicalStoreProblem("index shadow is already sealed")
            self._write_rows(rows, removed)
            self._current()
            self._db.execute("COMMIT")
            self._current()
        except (*_ERRORS, ValueError, LexicalStoreProblem):
            self._rollback()
            if self._was_cancelled:
                raise LexicalIndexCancelled("index operation cancelled") from None
            raise LexicalStoreProblem("index shadow write failed") from None

    def finish_build(self, checkpoint: int) -> None:
        self._require_search()
        self._was_cancelled = False
        try:
            if type(checkpoint) is not int or not 0 <= checkpoint <= _MAX_SEQUENCE:
                raise LexicalStoreProblem("index checkpoint is invalid")
            self.integrity_check()
            self._db.execute("BEGIN IMMEDIATE")
            state = self._db.execute("SELECT checkpoint,sealed FROM index_state WHERE singleton=1").fetchone()
            if state != (0, 0) and state != (checkpoint, 1):
                raise LexicalStoreProblem("index shadow checkpoint conflicted")
            self._current()
            self._db.execute("UPDATE index_state SET checkpoint=?,sealed=1 WHERE singleton=1", (checkpoint,))
            self._db.execute("COMMIT")
            self._current()
        except (*_ERRORS, ValueError, LexicalStoreProblem):
            self._rollback()
            if self._was_cancelled:
                raise LexicalIndexCancelled("index operation cancelled") from None
            raise LexicalStoreProblem("index shadow completion failed") from None

    def apply(
        self, rows: tuple[IndexRow, ...], removed: tuple[str, ...], *, expected_checkpoint: int, checkpoint: int
    ) -> None:
        self._require_search()
        self._was_cancelled = False
        if (
            type(rows) is not tuple
            or type(removed) is not tuple
            or len(rows) + len(removed) > _MAX_BATCH
            or type(expected_checkpoint) is not int
            or type(checkpoint) is not int
            or not 0 <= expected_checkpoint < checkpoint <= _MAX_SEQUENCE
            or len({r.entry_id for r in rows if isinstance(r, IndexRow)}) != len(rows)
            or any(not _hash(entry) for entry in removed)
        ):
            raise LexicalStoreProblem("index batch is invalid")
        try:
            byte_count = 0
            for row in rows:
                row.__post_init__()
                byte_count += sum(len(getattr(row, column).encode("utf-8")) for column in _COLUMNS)
            if byte_count > 4 * 1024 * 1024:
                raise LexicalStoreProblem("index batch byte budget exceeded")
            self._current()
            digest = _sha((tuple(asdict(row) for row in rows), removed, expected_checkpoint, checkpoint))
            self._db.execute("BEGIN IMMEDIATE")
            old = self._db.execute("SELECT checkpoint,last_batch_sha256 FROM index_state WHERE singleton=1").fetchone()
            if old == (checkpoint, digest):
                self._db.execute("ROLLBACK")
                return
            if old[0] != expected_checkpoint:
                raise LexicalStoreProblem("index checkpoint conflicted")
            self._write_rows(rows, removed)
            self._current()
            self._db.execute(
                "UPDATE index_state SET checkpoint=?,last_batch_sha256=?,sealed=1 WHERE singleton=1 AND checkpoint=?",
                (checkpoint, digest, expected_checkpoint),
            )
            self._db.execute("COMMIT")
            self._current()
        except (*_ERRORS, ValueError, LexicalStoreProblem):
            self._rollback()
            if self._was_cancelled:
                raise LexicalIndexCancelled("index operation cancelled") from None
            raise LexicalStoreProblem("protected index batch failed") from None

    def match(self, query: QueryDocument, entries: tuple[str, ...], items: tuple[str, ...]) -> tuple[str, ...]:
        self._require_search()
        self._was_cancelled = False
        compiled = compile_query(query)
        if (
            type(entries) is not tuple
            or type(items) is not tuple
            or len(entries) > _MAX_UNIVERSE
            or len(items) > _MAX_UNIVERSE
            or any(not _hash(entry) for entry in entries)
        ):
            raise LexicalStoreProblem("index read universe is invalid")
        try:
            for item in items:
                validate_database_key_identity(item)
            self._current()
            if self._db.execute("SELECT sealed FROM index_state WHERE singleton=1").fetchone() != (1,):
                raise LexicalStoreProblem("index shadow is incomplete")
            self._db.execute("BEGIN")
            self._db.execute("DELETE FROM allowed_entries")
            self._db.execute("DELETE FROM allowed_items")
            self._db.executemany("INSERT OR IGNORE INTO allowed_entries VALUES(?)", ((entry,) for entry in entries))
            self._db.executemany("INSERT OR IGNORE INTO allowed_items VALUES(?)", ((item,) for item in items))
            result = tuple(row[0] for row in self._db.execute(compiled.sql, compiled.parameters))
            self._current()
            self._db.execute("COMMIT")
            return result
        except (*_ERRORS, ValueError, LexicalStoreProblem):
            self._rollback()
            if self._was_cancelled:
                raise LexicalIndexCancelled("index operation cancelled") from None
            raise LexicalStoreProblem("protected index read failed") from None

    def integrity_check(self) -> None:
        self._was_cancelled = False
        try:
            self._current()
            self._validate_manifest()
            if (
                self._db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                or self._db.execute("PRAGMA cipher_integrity_check").fetchall()
            ):
                raise LexicalStoreProblem("index integrity failed")
            # rank=1 compares FTS tokens with its same-database text mirror.
            self._db.execute("INSERT INTO search_fts(search_fts,rank) VALUES('integrity-check',1)")
            cursor = self._db.execute("SELECT * FROM search_rows ORDER BY rowid")
            names = tuple(column[0] for column in cursor.description)
            for row in cursor:
                values = dict(zip(names, row, strict=True))
                values.pop("rowid")
                expected = values.pop("row_sha256")
                if expected != _sha(values):
                    raise LexicalStoreProblem("index mirror binding failed")
            self._current()
        except (*_ERRORS, LexicalStoreProblem):
            if self._was_cancelled:
                raise LexicalIndexCancelled("index operation cancelled") from None
            raise LexicalStoreProblem("protected index integrity failed") from None

    def projection(self) -> IndexProjection:
        """Content-free completed mirror digest, distinct from configuration.

        Stable row digests permit comparison across rebuilt generations. The
        overall manifest additionally binds this generation/key/analyzer and
        canonical checkpoint; a new generation cannot relabel an old manifest.
        """
        self._require_search()
        self._was_cancelled = False
        try:
            self._current()
            digest = hashlib.sha256()
            count = 0
            for entry, row_hash in self._db.execute("SELECT entry_id,row_sha256 FROM search_rows ORDER BY entry_id"):
                self._check_cancel()
                if not _hash(entry) or not _hash(row_hash):
                    raise LexicalStoreProblem("index projection binding is invalid")
                digest.update(bytes.fromhex(entry))
                digest.update(bytes.fromhex(row_hash))
                count += 1
            checkpoint = self.checkpoint
            rows_hash = digest.hexdigest()
            assert self._key is not None
            manifest = projection_manifest(
                self._scope, self._key.version, IndexProjection(checkpoint, count, rows_hash, "")
            )
            self._current()
            return IndexProjection(checkpoint, count, rows_hash, manifest)
        except (*_ERRORS, ValueError, LexicalStoreProblem):
            if self._was_cancelled:
                raise LexicalIndexCancelled("index operation cancelled") from None
            raise LexicalStoreProblem("protected index projection is unavailable") from None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        clean = False
        failed = False
        try:
            if self._db is not None:
                try:
                    self._db.set_progress_handler(None, 0)
                    self._db.set_authorizer(None)
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                    if self._retirement is not None:
                        self._retirement_current()
                    checkpoint = self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    clean = checkpoint == (0, 0, 0)
                except (*_ERRORS, LexicalStoreProblem):
                    failed = True
                finally:
                    self._db.close()
        except _ERRORS:
            failed = True
        finally:
            try:
                if self._guard is not None:
                    self._guard.close(clean_sidecars=clean)
            except _ERRORS:
                failed = True
            finally:
                if self._key is not None:
                    self._key.close()
        if failed:
            raise LexicalStoreProblem("protected index close is incomplete") from None

    def __enter__(self) -> ProtectedLexicalStore:
        try:
            self._current()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


def recover_retired_generation(
    root: Path,
    scope: DerivativeKeyScope,
    keys: DerivativeKeyProvider,
    *,
    expected_version: str,
    authorize: Callable[[tuple[int, int]], None],
) -> None:
    """Private Core recovery operation; returns no store, rows or read lease.

    Core must recheck current session/actor, authenticated Retired state,
    nonselection and exact canonical main-file binding in `authorize`.
    Historical material only authenticates and checkpoints owned sidecars;
    ordinary search eligibility still requires the current canonical key.
    """
    try:
        with ProtectedLexicalStore(root, scope, keys, _retirement=(expected_version, authorize)) as store:
            store.integrity_check()
            identity = store.file_identity
        authorize(identity)
    except Exception:
        raise LexicalStoreProblem("retired generation recovery is incomplete") from None


__all__ = ["IndexProjection", "IndexRow", "LexicalIndexCancelled", "LexicalStoreProblem", "ProtectedLexicalStore"]
