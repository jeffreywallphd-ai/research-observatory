"""Canonical generation history and fenced, short lived index writer ownership.

Only trusted Core code constructs validation proofs. This adapter never accepts
SQL, source text, a client clock or a persisted bearer token.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, TypeVar

from .corpus_repository import SqliteCorpusRepository
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .lexical_index_store import IndexProjection, projection_manifest
from .lexical_input_repository import lexical_watermark
from .ports.corpus import CorpusActor
from .ports.credential_store import SecretLease
from .ports.derivative_keys import DerivativeKeyProvider, DerivativeKeyScope, DerivativePurpose
from .search.contracts import ANALYZER_ID
from .storage import CanonicalConnection, _normalize_utc_millisecond, open_canonical_database

T = TypeVar("T")


class IndexGuard(Protocol):
    def __call__[Result](self, action: Callable[[], Result]) -> Result: ...


_EVENT_COLUMNS = (
    "event_id",
    "generation_id",
    "project_id",
    "previous_event_id",
    "stage",
    "checkpoint",
    "cursor_item_id",
    "owner_sha256",
    "lease_epoch",
    "authority_sha256",
    "projection_sha256",
    "entry_count",
    "occurred_at",
)
_CONFIG_COLUMNS = (
    "generation_id",
    "project_id",
    "purpose",
    "analyzer_id",
    "derivative_schema_version",
    "canonical_key_version",
    "derivative_key_version",
    "lifecycle_sha256",
    "initial_watermark",
    "authority_sha256",
    "created_at",
)


class IndexCatalogProblem(RuntimeError):
    """Content free missing, stale, denied or inconsistent index authority."""


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def actor_context_sha256(project: str, actor: CorpusActor) -> str:
    # Trace/time identify an attempt, not the lifetime of accepted authority.
    return _sha(
        (project, actor.actor_id, actor.actor_type, actor.intent_revision_id, actor.intent_sha256, actor.policy_sha256)
    )


@dataclass(frozen=True, slots=True)
class IndexValidation:
    watermark: int
    authority_sha256: str
    actor_sha256: str
    expires_at: str | None

    def __post_init__(self) -> None:
        if type(self.watermark) is not int or not 0 <= self.watermark <= 9_007_199_254_740_991:
            raise ValueError("index validation is invalid")
        if not _is_hash(self.authority_sha256) or not _is_hash(self.actor_sha256):
            raise ValueError("index validation is invalid")
        if self.expires_at is not None and _normalize_utc_millisecond(self.expires_at) != self.expires_at:
            raise ValueError("index expiry is not canonical")


@dataclass(frozen=True, slots=True)
class IndexGenerationLease:
    project_id: str
    generation_id: str
    epoch: int
    _secret: SecretLease = field(repr=False, compare=False)

    @property
    def owner_sha256(self) -> str:
        return self._secret.use(lambda material: hashlib.sha256(material).hexdigest())

    def close(self) -> None:
        self._secret.close()


@dataclass(frozen=True, slots=True)
class IndexGeneration:
    scope: DerivativeKeyScope
    derivative_key_version: str
    initial_watermark: int
    configuration_sha256: str
    event_id: str
    stage: str
    checkpoint: int
    cursor_item_id: str | None
    authority_sha256: str
    projection_sha256: str | None
    entry_count: int | None
    selection_id: str | None = None

    @property
    def generation_id(self) -> str:
        return self.scope.generation_id


class SqliteIndexCatalog:
    def __init__(
        self,
        database: Path,
        project_id: str,
        keys: DerivativeKeyProvider,
        *,
        actor: Callable[[], CorpusActor],
        guard: IndexGuard,
        now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    ) -> None:
        self.database, self.project, self.keys = database, project_id, keys
        self.actor, self.guard, self.now = actor, guard, now
        self.corpus = SqliteCorpusRepository(database, project_id)

    def _bounded(self, action: Callable[[], T]) -> T:
        try:
            return self.guard(action)
        except IndexCatalogProblem:
            raise
        except Exception:
            raise IndexCatalogProblem("index authority is unavailable") from None

    @contextmanager
    def _transaction(self, *, write: bool) -> Iterator[tuple[CanonicalConnection, CorpusActor, str]]:
        connection = open_canonical_database(self.database, expected_project_id=self.project)
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            actor, now = self.actor(), self.now()
            if _normalize_utc_millisecond(now) != now:
                raise IndexCatalogProblem("index clock is not canonical")
            self.corpus._command(new_uuid_v7(), "0" * 64, actor)
            self.corpus._authority(connection, actor)
            yield connection, actor, now
            self.corpus._authority(connection, actor)
            connection.execute("COMMIT")
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    def _watermark(self, db: CanonicalConnection) -> int:
        return lexical_watermark(db, self.project)

    def watermark(self) -> int:
        def read() -> int:
            with self._transaction(write=False) as (db, _actor, _now):
                return self._watermark(db)

        return self._bounded(read)

    def _load(self, db: CanonicalConnection, generation_id: str) -> IndexGeneration:
        if not is_uuid_v7(generation_id):
            raise IndexCatalogProblem("index identity is invalid")
        row = db.execute(
            "SELECT "
            + ",".join(_CONFIG_COLUMNS)
            + ",configuration_sha256 FROM search_generations WHERE project_id=? AND generation_id=?",
            (self.project, generation_id),
        ).fetchone()
        if row is None or _sha(dict(zip(_CONFIG_COLUMNS, row[:-1], strict=True))) != row[-1]:
            raise IndexCatalogProblem("index configuration is unavailable")
        config = dict(zip(_CONFIG_COLUMNS, row[:-1], strict=True))
        # Protected immutable rows and insertion-time chain constraints retain
        # history. Commands authenticate its current seal rather than replaying
        # every completed item on every checkpoint (quadratic for large corpora).
        values = db.execute(
            "SELECT "
            + ",".join(_EVENT_COLUMNS)
            + ",record_sha256 FROM search_generation_events WHERE project_id=? AND generation_id=? ORDER BY "
            "event_sequence DESC LIMIT 1",
            (self.project, generation_id),
        ).fetchone()
        if values is None:
            raise IndexCatalogProblem("index history is unavailable")
        event = dict(zip(_EVENT_COLUMNS, values[:-1], strict=True))
        if _sha(event) != values[-1]:
            raise IndexCatalogProblem("index history is unavailable")
        scope = DerivativeKeyScope(
            self.project,
            generation_id,
            DerivativePurpose(config["purpose"]),
            config["canonical_key_version"],
            config["lifecycle_sha256"],
        )
        return IndexGeneration(
            scope,
            config["derivative_key_version"],
            config["initial_watermark"],
            row[-1],
            event["event_id"],
            event["stage"],
            event["checkpoint"],
            event["cursor_item_id"],
            event["authority_sha256"],
            event["projection_sha256"],
            event["entry_count"],
        )

    def _assert_key(self, snapshot: IndexGeneration) -> None:
        with self.keys.lease(snapshot.scope, create=False) as key:
            if key.version != snapshot.derivative_key_version:
                raise IndexCatalogProblem("index key changed")

    def get(self, generation_id: str) -> IndexGeneration:
        def read() -> IndexGeneration:
            with self._transaction(write=False) as (db, _actor, _now):
                return self._load(db, generation_id)

        return self._bounded(read)

    def _selection(self, db: CanonicalConnection) -> dict[str, Any] | None:
        columns = (
            "event_id",
            "project_id",
            "selection_revision",
            "previous_event_id",
            "generation_id",
            "generation_event_id",
            "checkpoint",
            "authority_sha256",
            "occurred_at",
        )
        row = db.execute(
            "SELECT "
            + ",".join(columns)
            + ",record_sha256 FROM search_selections WHERE project_id=? ORDER BY selection_revision DESC LIMIT 1",
            (self.project,),
        ).fetchone()
        if row is None:
            return None
        result = dict(zip(columns, row[:-1], strict=True))
        if _sha(result) != row[-1]:
            raise IndexCatalogProblem("index selection is unavailable")
        return result

    def selected(self) -> IndexGeneration | None:
        def read() -> IndexGeneration | None:
            with self._transaction(write=False) as (db, _actor, _now):
                selection = self._selection(db)
                if selection is None or selection["generation_id"] is None:
                    return None
                snapshot = self._load(db, selection["generation_id"])
                if (
                    snapshot.stage != "Ready"
                    or snapshot.event_id != selection["generation_event_id"]
                    or snapshot.checkpoint != selection["checkpoint"]
                    or snapshot.authority_sha256 != selection["authority_sha256"]
                ):
                    raise IndexCatalogProblem("selected index is unavailable")
                return IndexGeneration(
                    **(asdict(snapshot) | {"scope": snapshot.scope, "selection_id": selection["event_id"]})
                )

        return self._bounded(read)

    @staticmethod
    def _expiry(now: str) -> str:
        return (
            (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(seconds=30))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def _owner(self, db: CanonicalConnection, lease: IndexGenerationLease, now: str) -> None:
        if not isinstance(lease, IndexGenerationLease) or lease.project_id != self.project:
            raise IndexCatalogProblem("index writer is unavailable")
        row = db.execute(
            "SELECT owner_sha256,epoch,renewed_at,expires_at FROM search_generation_leases WHERE project_id=? "
            "AND generation_id=?",
            (self.project, lease.generation_id),
        ).fetchone()
        if (
            row is None
            or not secrets.compare_digest(str(row[0]), lease.owner_sha256)
            or row[1] != lease.epoch
            or not row[2] <= now < row[3]
        ):
            raise IndexCatalogProblem("index writer is stale")

    def _event(
        self,
        db: CanonicalConnection,
        lease: IndexGenerationLease,
        actor: CorpusActor,
        now: str,
        *,
        stage: str,
        checkpoint: int,
        previous: str | None,
        cursor: str | None,
        authority: str,
        projection: IndexProjection | None = None,
    ) -> str:
        self._owner(db, lease, now)
        event = dict(
            zip(
                _EVENT_COLUMNS,
                (
                    new_uuid_v7(),
                    lease.generation_id,
                    self.project,
                    previous,
                    stage,
                    checkpoint,
                    cursor,
                    lease.owner_sha256,
                    lease.epoch,
                    authority,
                    None if projection is None else projection.manifest_sha256,
                    None if projection is None else projection.entry_count,
                    now,
                ),
                strict=True,
            )
        )
        digest = _sha(event)
        db.execute(
            "INSERT INTO search_generation_events("
            + ",".join(_EVENT_COLUMNS)
            + ",record_sha256) VALUES("
            + ",".join("?" for _ in range(len(_EVENT_COLUMNS) + 1))
            + ")",
            (*event.values(), digest),
        )
        kind = {
            "Building": "search.index-checkpoint",
            "Incomplete": "search.index-incomplete",
            "Ready": "search.index-selected",
            "Retired": "search.index-retired",
        }[stage]
        self._audit(db, actor, now, kind, digest)
        return str(event["event_id"])

    def _audit(
        self,
        db: CanonicalConnection,
        actor: CorpusActor,
        now: str,
        kind: str,
        digest: str,
        *,
        idempotency: str | None = None,
    ) -> None:
        identity = new_uuid_v7()
        db.execute(
            "INSERT INTO provenance_events(event_id,project_id,revision_id,event_type,occurred_at,trace_id,actor_"
            "type,actor_id,record_sha256) VALUES(?,?,NULL,?,?,?,?,?,?)",
            (identity, self.project, kind, now, actor.trace_id, actor.actor_type, actor.actor_id, digest),
        )
        db.execute(
            "INSERT INTO outbox_events(outbox_id,project_id,revision_id,event_type,occurred_at,available_at,state"
            ",attempt_count,published_at,idempotency_key,record_sha256) "
            "VALUES(?,?,NULL,?,?,?,'pending',0,NULL,?,?)",
            (
                new_uuid_v7(),
                self.project,
                kind,
                now,
                now,
                "search-control-" + identity if idempotency is None else idempotency,
                digest,
            ),
        )

    def _file_binding(self, generation_id: str, identity: tuple[int, int]) -> str:
        if (
            type(identity) is not tuple
            or len(identity) != 2
            or any(type(value) is not int or value < 0 for value in identity)
        ):
            raise IndexCatalogProblem("index file identity is invalid")
        return _sha(("lexical-file-identity-v1", self.project, generation_id, *(str(value) for value in identity)))

    def bind_file(self, lease: IndexGenerationLease, identity: tuple[int, int]) -> None:
        def write() -> None:
            with self._transaction(write=True) as (db, actor, now):
                self._owner(db, lease, now)
                snapshot = self._load(db, lease.generation_id)
                if snapshot.stage != "Building":
                    raise IndexCatalogProblem("index file binding is closed")
                digest = self._file_binding(lease.generation_id, identity)
                prior = db.execute(
                    "SELECT record_sha256 FROM outbox_events WHERE project_id=? AND idempotency_key=?",
                    (self.project, "search-file-" + lease.generation_id),
                ).fetchone()
                if prior is not None:
                    if prior[0] != digest:
                        raise IndexCatalogProblem("index file identity changed")
                    return
                self._audit(
                    db,
                    actor,
                    now,
                    "search.index-generation-created",
                    digest,
                    idempotency="search-file-" + lease.generation_id,
                )

        self._bounded(write)

    def _bootstrap_identity(self, snapshot: IndexGeneration, role: str, identity: tuple[int, int]) -> str:
        if role not in ("", "-wal", "-shm", "-journal"):
            raise IndexCatalogProblem("bootstrap role is invalid")
        return _sha(
            (
                "lexical-bootstrap-role-v1",
                snapshot.configuration_sha256,
                role,
                self._file_binding(snapshot.generation_id, identity),
            )
        )

    def _bootstrap_records(self, db: CanonicalConnection, snapshot: IndexGeneration) -> dict[str, str]:
        prefix = "search-bootstrap-v1-" + snapshot.generation_id + ":"
        records = dict(
            db.execute(
                "SELECT substr(o.idempotency_key,?),o.record_sha256 FROM outbox_events o WHERE "
                "o.project_id=? AND o.idempotency_key LIKE ? AND o.event_type='search.index-generation-created' "
                "AND o.revision_id IS NULL AND EXISTS(SELECT 1 FROM provenance_events p WHERE "
                "p.project_id=o.project_id AND p.event_type=o.event_type AND p.revision_id IS NULL AND "
                "p.record_sha256=o.record_sha256)",
                (len(prefix) + 1, self.project, prefix + "%"),
            ).fetchall()
        )
        if not records:
            return records
        roles = ("main", "-wal", "-shm", "-journal")
        if set(records) not in (set(roles) | {"seal"}, set(roles) | {"seal", "initialized"}):
            raise IndexCatalogProblem("bootstrap witness is incomplete")
        seal = _sha(
            ("lexical-bootstrap-seal-v1", snapshot.configuration_sha256, tuple((role, records[role]) for role in roles))
        )
        if records["seal"] != seal or ("initialized" in records and records["initialized"] != seal):
            raise IndexCatalogProblem("bootstrap witness is invalid")
        return records

    def bind_bootstrap(self, lease: IndexGenerationLease, identities: dict[str, tuple[int, int]]) -> None:
        def write() -> None:
            with self._transaction(write=True) as (db, actor, now):
                self._owner(db, lease, now)
                snapshot = self._load(db, lease.generation_id)
                if snapshot.stage != "Building" or set(identities) != {"", "-wal", "-shm", "-journal"}:
                    raise IndexCatalogProblem("bootstrap binding is closed")
                records = {
                    (role or "main"): self._bootstrap_identity(snapshot, role, identity)
                    for role, identity in identities.items()
                }
                records["seal"] = _sha(
                    (
                        "lexical-bootstrap-seal-v1",
                        snapshot.configuration_sha256,
                        tuple((role, records[role]) for role in ("main", "-wal", "-shm", "-journal")),
                    )
                )
                prior = self._bootstrap_records(db, snapshot)
                if prior:
                    if prior != records:
                        raise IndexCatalogProblem("bootstrap file identities changed")
                    return
                for role, digest in records.items():
                    self._audit(
                        db,
                        actor,
                        now,
                        "search.index-generation-created",
                        digest,
                        idempotency="search-bootstrap-v1-" + lease.generation_id + ":" + role,
                    )
                self._audit(
                    db,
                    actor,
                    now,
                    "search.index-generation-created",
                    self._file_binding(lease.generation_id, identities[""]),
                    idempotency="search-file-" + lease.generation_id,
                )

        self._bounded(write)

    def initialized(self, generation_id: str) -> bool:
        def read() -> bool:
            with self._transaction(write=False) as (db, _actor, _now):
                return "initialized" in self._bootstrap_records(db, self._load(db, generation_id))

        return self._bounded(read)

    def acknowledge_initialization(self, lease: IndexGenerationLease, identities: dict[str, tuple[int, int]]) -> None:
        def write() -> None:
            with self._transaction(write=True) as (db, actor, now):
                self._owner(db, lease, now)
                snapshot = self._load(db, lease.generation_id)
                records = self._bootstrap_records(db, snapshot)
                if snapshot.stage != "Building" or not records or set(identities) != {"", "-wal", "-shm", "-journal"}:
                    raise IndexCatalogProblem("empty bootstrap acknowledgement is unavailable")
                for role, identity in identities.items():
                    if records[role or "main"] != self._bootstrap_identity(snapshot, role, identity):
                        raise IndexCatalogProblem("bootstrap file identity changed")
                if "initialized" not in records:
                    self._audit(
                        db,
                        actor,
                        now,
                        "search.index-generation-created",
                        records["seal"],
                        idempotency="search-bootstrap-v1-" + lease.generation_id + ":initialized",
                    )

        self._bounded(write)

    def authorize_bootstrap_cleanup(self, generation_id: str, identities: dict[str, tuple[int, int]]) -> None:
        def read() -> None:
            with self._transaction(write=False) as (db, _actor, _now):
                snapshot = self._load(db, generation_id)
                records = self._bootstrap_records(db, snapshot)
                selected = self._selection(db)
                if (
                    snapshot.stage != "Retired"
                    or snapshot.cursor_item_id is not None
                    or snapshot.entry_count is not None
                    or snapshot.projection_sha256 is not None
                    or "initialized" in records
                    or (selected is not None and selected["generation_id"] == generation_id)
                ):
                    raise IndexCatalogProblem("bootstrap cleanup is unavailable")
                for role, identity in identities.items():
                    if not records or records.get(role or "main") != self._bootstrap_identity(snapshot, role, identity):
                        raise IndexCatalogProblem("unknown bootstrap files are preserved")

        self._bounded(read)

    def file_bound(self, generation_id: str, identity: tuple[int, int]) -> bool:
        def read() -> bool:
            with self._transaction(write=False) as (db, _actor, _now):
                self._load(db, generation_id)
                digest = self._file_binding(generation_id, identity)
                return (
                    db.execute(
                        "SELECT 1 FROM outbox_events o WHERE o.project_id=? AND o.idempotency_key=? AND "
                        "o.event_type='search.index-generation-created' AND o.revision_id IS NULL AND "
                        "o.record_sha256=? AND EXISTS(SELECT 1 FROM provenance_events p WHERE "
                        "p.project_id=o.project_id AND p.event_type=o.event_type AND p.revision_id IS NULL AND "
                        "p.record_sha256=o.record_sha256)",
                        (self.project, "search-file-" + generation_id, digest),
                    ).fetchone()
                    is not None
                )

        return self._bounded(read)

    def create(self, scope: DerivativeKeyScope) -> IndexGenerationLease:
        def write() -> IndexGenerationLease:
            if not isinstance(scope, DerivativeKeyScope) or scope.project_id != self.project:
                raise IndexCatalogProblem("index scope is invalid")
            with self.keys.lease(scope, create=True) as key:
                lease = IndexGenerationLease(
                    self.project, scope.generation_id, 1, SecretLease(bytearray(secrets.token_bytes(32)))
                )
                try:
                    with self._transaction(write=True) as (db, actor, now):
                        config = dict(
                            zip(
                                _CONFIG_COLUMNS,
                                (
                                    scope.generation_id,
                                    self.project,
                                    scope.purpose.value,
                                    ANALYZER_ID,
                                    1,
                                    scope.canonical_key_version,
                                    key.version,
                                    scope.lifecycle_sha256,
                                    self._watermark(db),
                                    actor_context_sha256(self.project, actor),
                                    now,
                                ),
                                strict=True,
                            )
                        )
                        key.assert_current(scope)
                        db.execute(
                            "INSERT INTO search_generations("
                            + ",".join(_CONFIG_COLUMNS)
                            + ",configuration_sha256) VALUES("
                            + ",".join("?" for _ in range(len(_CONFIG_COLUMNS) + 1))
                            + ")",
                            (*config.values(), _sha(config)),
                        )
                        db.execute(
                            "INSERT INTO search_generation_leases VALUES(?,?,?,?,?,?,?)",
                            (
                                scope.generation_id,
                                self.project,
                                lease.owner_sha256,
                                lease.epoch,
                                now,
                                now,
                                self._expiry(now),
                            ),
                        )
                        self._event(
                            db,
                            lease,
                            actor,
                            now,
                            stage="Building",
                            checkpoint=0,
                            previous=None,
                            cursor=None,
                            authority=actor_context_sha256(self.project, actor),
                        )
                    return lease
                except BaseException:
                    lease.close()
                    raise

        return self._bounded(write)

    def acquire(self, generation_id: str) -> IndexGenerationLease:
        def write() -> IndexGenerationLease:
            with self._transaction(write=True) as (db, actor, now):
                snapshot = self._load(db, generation_id)
                old = db.execute(
                    "SELECT epoch,renewed_at,expires_at FROM search_generation_leases WHERE generation_id=? AND "
                    "project_id=?",
                    (generation_id, self.project),
                ).fetchone()
                if (
                    old is None
                    or now < old[1]
                    or (now < old[2] and snapshot.stage != "Incomplete")
                    or snapshot.stage == "Retired"
                ):
                    raise IndexCatalogProblem("index writer is unavailable")
                lease = IndexGenerationLease(
                    self.project, generation_id, int(old[0]) + 1, SecretLease(bytearray(secrets.token_bytes(32)))
                )
                try:
                    db.execute(
                        "UPDATE search_generation_leases SET "
                        "owner_sha256=?,epoch=?,issued_at=?,renewed_at=?,expires_at=? WHERE project_id=? AND "
                        "generation_id=?",
                        (lease.owner_sha256, lease.epoch, now, now, self._expiry(now), self.project, generation_id),
                    )
                    if snapshot.stage == "Incomplete":
                        self._event(
                            db,
                            lease,
                            actor,
                            now,
                            stage="Building",
                            checkpoint=snapshot.checkpoint,
                            previous=snapshot.event_id,
                            cursor=snapshot.cursor_item_id,
                            authority=actor_context_sha256(self.project, actor),
                        )
                    self._audit(
                        db,
                        actor,
                        now,
                        "search.index-lease-claimed",
                        _sha((generation_id, lease.owner_sha256, lease.epoch)),
                    )
                except BaseException:
                    lease.close()
                    raise
                return lease

        return self._bounded(write)

    def renew(self, lease: IndexGenerationLease) -> None:
        def write() -> None:
            with self._transaction(write=True) as (db, _actor, now):
                self._owner(db, lease, now)
                snapshot = self._load(db, lease.generation_id)
                self._assert_key(snapshot)
                if snapshot.stage not in ("Building", "Ready"):
                    raise IndexCatalogProblem("index writer is cancelled")
                db.execute(
                    "UPDATE search_generation_leases SET renewed_at=?,expires_at=? WHERE project_id=? AND "
                    "generation_id=?",
                    (now, self._expiry(now), self.project, lease.generation_id),
                )

        self._bounded(write)

    def assert_owner(self, lease: IndexGenerationLease) -> None:
        def read() -> None:
            with self._transaction(write=False) as (db, _actor, now):
                self._owner(db, lease, now)
                snapshot = self._load(db, lease.generation_id)
                self._assert_key(snapshot)
                if snapshot.stage not in ("Building", "Ready"):
                    raise IndexCatalogProblem("index writer is cancelled")

        self._bounded(read)

    def record_progress(self, lease: IndexGenerationLease, *, cursor_item_id: str) -> None:
        def write() -> None:
            with self._transaction(write=True) as (db, actor, now):
                snapshot = self._load(db, lease.generation_id)
                if (
                    snapshot.stage != "Building"
                    or "initialized" not in self._bootstrap_records(db, snapshot)
                    or not is_uuid_v7(cursor_item_id)
                    or (snapshot.cursor_item_id is not None and cursor_item_id <= snapshot.cursor_item_id)
                ):
                    raise IndexCatalogProblem("index progress is invalid")
                self._event(
                    db,
                    lease,
                    actor,
                    now,
                    stage="Building",
                    checkpoint=snapshot.checkpoint,
                    previous=snapshot.event_id,
                    cursor=cursor_item_id,
                    authority=actor_context_sha256(self.project, actor),
                )

        self._bounded(write)

    def cancel(self, lease: IndexGenerationLease) -> None:
        def write() -> None:
            with self._transaction(write=True) as (db, actor, now):
                snapshot = self._load(db, lease.generation_id)
                if snapshot.stage not in ("Building", "Ready"):
                    raise IndexCatalogProblem("index cancellation is invalid")
                self._event(
                    db,
                    lease,
                    actor,
                    now,
                    stage="Incomplete",
                    checkpoint=snapshot.checkpoint,
                    previous=snapshot.event_id,
                    cursor=snapshot.cursor_item_id,
                    authority=actor_context_sha256(self.project, actor),
                )

        self._bounded(write)

    def retire(self, lease: IndexGenerationLease) -> None:
        def write() -> None:
            with self._transaction(write=True) as (db, actor, now):
                snapshot = self._load(db, lease.generation_id)
                selected = self._selection(db)
                if snapshot.stage not in ("Building", "Incomplete", "Ready") or (
                    selected is not None and selected["generation_id"] == lease.generation_id
                ):
                    raise IndexCatalogProblem("selected index cannot be retired")
                self._event(
                    db,
                    lease,
                    actor,
                    now,
                    stage="Retired",
                    checkpoint=snapshot.checkpoint,
                    previous=snapshot.event_id,
                    cursor=snapshot.cursor_item_id,
                    authority=actor_context_sha256(self.project, actor),
                )

        self._bounded(write)

    def publish_ready(
        self,
        lease: IndexGenerationLease,
        projection: IndexProjection,
        validation: IndexValidation,
        *,
        expected_selection_id: str | None,
        revalidate: Callable[[CanonicalConnection], None],
        cancelled: Callable[[], bool] = lambda: False,
    ) -> None:
        def write() -> None:
            if cancelled() is not False:
                raise IndexCatalogProblem("index promotion cancelled")
            if not isinstance(validation, IndexValidation) or not isinstance(projection, IndexProjection):
                raise IndexCatalogProblem("index validation is invalid")
            validation.__post_init__()
            with self._transaction(write=True) as (db, actor, now):
                snapshot = self._load(db, lease.generation_id)
                self._assert_key(snapshot)
                selection = self._selection(db)
                if (
                    snapshot.stage not in ("Building", "Ready")
                    or "initialized" not in self._bootstrap_records(db, snapshot)
                    or validation.watermark != self._watermark(db)
                    or validation.watermark != projection.checkpoint
                    or validation.watermark < snapshot.initial_watermark
                    or validation.actor_sha256 != actor_context_sha256(self.project, actor)
                    or (validation.expires_at is not None and now >= validation.expires_at)
                    or (None if selection is None else selection["event_id"]) != expected_selection_id
                    or not _is_hash(projection.manifest_sha256)
                    or not _is_hash(projection.rows_sha256)
                    or projection_manifest(snapshot.scope, snapshot.derivative_key_version, projection)
                    != projection.manifest_sha256
                    or type(projection.entry_count) is not int
                    or not 0 <= projection.entry_count <= 9_007_199_254_740_991
                ):
                    raise IndexCatalogProblem("index promotion authority changed")
                revalidate(db)
                if cancelled() is not False:
                    raise IndexCatalogProblem("index promotion cancelled")
                fresh = self.now()
                if (
                    _normalize_utc_millisecond(fresh) != fresh
                    or fresh < now
                    or (validation.expires_at is not None and fresh >= validation.expires_at)
                ):
                    raise IndexCatalogProblem("index promotion expired")
                now = fresh
                self._owner(db, lease, now)
                self._assert_key(self._load(db, lease.generation_id))
                event_id = self._event(
                    db,
                    lease,
                    actor,
                    now,
                    stage="Ready",
                    checkpoint=projection.checkpoint,
                    previous=snapshot.event_id,
                    cursor=snapshot.cursor_item_id,
                    authority=validation.authority_sha256,
                    projection=projection,
                )
                pointer = dict(
                    event_id=new_uuid_v7(),
                    project_id=self.project,
                    selection_revision=0 if selection is None else selection["selection_revision"] + 1,
                    previous_event_id=expected_selection_id,
                    generation_id=lease.generation_id,
                    generation_event_id=event_id,
                    checkpoint=projection.checkpoint,
                    authority_sha256=validation.authority_sha256,
                    occurred_at=now,
                )
                db.execute(
                    "INSERT INTO search_selections("
                    + ",".join(pointer)
                    + ",record_sha256) VALUES("
                    + ",".join("?" for _ in range(len(pointer) + 1))
                    + ")",
                    (*pointer.values(), _sha(pointer)),
                )
                fresh = self.now()
                if (
                    _normalize_utc_millisecond(fresh) != fresh
                    or fresh < now
                    or (validation.expires_at is not None and fresh >= validation.expires_at)
                ):
                    raise IndexCatalogProblem("index promotion expired")
                self._owner(db, lease, fresh)
                self._assert_key(self._load(db, lease.generation_id))
                commit_time = self.now()
                if (
                    _normalize_utc_millisecond(commit_time) != commit_time
                    or commit_time < fresh
                    or (validation.expires_at is not None and commit_time >= validation.expires_at)
                ):
                    raise IndexCatalogProblem("index promotion expired")
                self._owner(db, lease, commit_time)
                if cancelled() is not False:
                    raise IndexCatalogProblem("index promotion cancelled")

        self._bounded(write)
