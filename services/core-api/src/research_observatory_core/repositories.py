"""Typed aggregate repositories and explicit local SQLite units of work.

Business modules consume the protocols in this module. Only this adapter owns
SQLAlchemy statements or the restricted canonical database capability.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast, runtime_checkable

from sqlalchemy import Column, Integer, MetaData, String, Table, desc, insert, select
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.sql import ClauseElement

from .storage import MAX_SAFE_INTEGER, CanonicalConnection, open_canonical_database

AggregateKind = Literal["record", "document", "workflow", "evidence", "ontology", "decision"]
KnowledgeStatus = Literal[
    "observed",
    "extracted",
    "inferred",
    "verified",
    "disputed",
    "adjudicated",
    "stale",
    "unknown",
    "not-reported",
    "not-applicable",
    "ambiguous",
    "unavailable",
]
RightsStatus = Literal["allowed", "denied", "unknown", "not-applicable"]
ActorType = Literal["human", "system", "worker", "model"]


class RepositoryProblem(RuntimeError):
    """Bounded repository failure that does not disclose canonical content."""

    code = "RO-CORE-REPOSITORY-FAILED"

    def __init__(self, message: str = "canonical repository operation failed") -> None:
        super().__init__(message)


class RepositoryNotFound(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-NOT-FOUND"


class RepositoryConflict(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-CONFLICT"


class RepositoryTransactionFailed(RepositoryProblem):
    code = "RO-CORE-REPOSITORY-TRANSACTION-FAILED"


@dataclass(frozen=True, slots=True)
class AggregateRevision:
    """Detached domain projection returned across the persistence boundary."""

    revision_id: str
    aggregate_id: str
    aggregate_kind: AggregateKind
    project_id: str
    revision: int
    contract_version: str
    created_at: str
    modified_at: str
    display_label_observed: str
    display_label_normalized: str | None
    knowledge_status: KnowledgeStatus
    rights_status: RightsStatus
    object_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class AggregateRevisionDraft:
    """Caller-owned values for one immutable aggregate revision."""

    revision_id: str
    aggregate_id: str
    aggregate_kind: AggregateKind
    created_at: str
    modified_at: str
    display_label_observed: str
    display_label_normalized: str | None
    knowledge_status: KnowledgeStatus
    rights_status: RightsStatus
    object_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class AtomicRepositoryEvent:
    """Provenance and outbox identities committed with a revision."""

    event_id: str
    outbox_id: str
    event_type: str
    occurred_at: str
    available_at: str
    trace_id: str
    actor_type: ActorType
    actor_id: str | None
    idempotency_key: str


@runtime_checkable
class AggregateRepository(Protocol):
    def get(self, aggregate_id: str) -> AggregateRevision: ...

    def append(
        self,
        draft: AggregateRevisionDraft,
        event: AtomicRepositoryEvent,
        *,
        expected_revision: int | None,
    ) -> AggregateRevision: ...


@runtime_checkable
class UnitOfWork(Protocol):
    @property
    def aggregates(self) -> AggregateRepository: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


@runtime_checkable
class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


_METADATA = MetaData()
_IDENTITIES = Table(
    "aggregate_identities",
    _METADATA,
    Column("aggregate_id", String),
    Column("project_id", String),
    Column("aggregate_kind", String),
    Column("created_at", String),
)
_REVISIONS = Table(
    "aggregate_revisions",
    _METADATA,
    Column("revision_id", String),
    Column("aggregate_id", String),
    Column("aggregate_kind", String),
    Column("project_id", String),
    Column("revision", Integer),
    Column("contract_version", String),
    Column("created_at", String),
    Column("modified_at", String),
    Column("display_label_observed", String),
    Column("display_label_normalized", String),
    Column("knowledge_status", String),
    Column("rights_status", String),
)
_PROVENANCE = Table(
    "provenance_events",
    _METADATA,
    Column("event_id", String),
    Column("project_id", String),
    Column("revision_id", String),
    Column("event_type", String),
    Column("occurred_at", String),
    Column("trace_id", String),
    Column("actor_type", String),
    Column("actor_id", String),
    Column("record_sha256", String),
)
_OUTBOX = Table(
    "outbox_events",
    _METADATA,
    Column("outbox_id", String),
    Column("project_id", String),
    Column("revision_id", String),
    Column("event_type", String),
    Column("occurred_at", String),
    Column("available_at", String),
    Column("state", String),
    Column("attempt_count", Integer),
    Column("published_at", String),
    Column("idempotency_key", String),
    Column("record_sha256", String),
)
_DOCUMENTS = Table(
    "documents",
    _METADATA,
    Column("revision_id", String),
    Column("project_id", String),
    Column("object_sha256", String),
)
_EXTENSIONS = {
    kind: Table(table, _METADATA, Column("revision_id", String))
    for kind, table in (
        ("record", "scholarly_records"),
        ("workflow", "workflows"),
        ("evidence", "evidence"),
        ("ontology", "ontologies"),
        ("decision", "decisions"),
    )
}
_SQLITE_DIALECT = sqlite_dialect(paramstyle="named")


def _execute(connection: CanonicalConnection, statement: ClauseElement):
    compiled = statement.compile(dialect=_SQLITE_DIALECT, compile_kwargs={"render_postcompile": True})
    return connection.execute(str(compiled), compiled.params)


@dataclass(slots=True)
class _UnitOfWorkState:
    connection: CanonicalConnection
    project_id: str
    failed: bool = False
    completed: bool = False


class _UnitOfWorkRegistry:
    """Module-owned transaction authority; returned ports retain only opaque tokens."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, _UnitOfWorkState] = {}

    def register(self, connection: CanonicalConnection, project_id: str) -> str:
        with self._lock:
            while True:
                token = secrets.token_hex(32)
                if token not in self._states:
                    self._states[token] = _UnitOfWorkState(connection, project_id)
                    return token

    def state(self, token: str | None, *, active: bool = True) -> _UnitOfWorkState:
        with self._lock:
            state = self._states.get(token or "")
        if state is None:
            raise RepositoryTransactionFailed("unit of work is closed")
        if active and (state.failed or state.completed):
            raise RepositoryTransactionFailed("unit of work is not active")
        return state

    def fail(self, token: str) -> None:
        with self._lock:
            state = self._states.get(token)
            if state is not None:
                state.failed = True

    def finish(self, token: str, *, commit: bool) -> None:
        state = self.state(token, active=False)
        if state.completed:
            raise RepositoryTransactionFailed("unit of work is already complete")
        if commit and state.failed:
            raise RepositoryTransactionFailed("failed unit of work cannot commit")
        try:
            state.connection.execute("COMMIT" if commit else "ROLLBACK")
            state.completed = True
        except sqlite3.Error as error:
            state.failed = True
            if state.connection.in_transaction:
                with suppress(sqlite3.Error):
                    state.connection.execute("ROLLBACK")
            raise RepositoryTransactionFailed() from error

    def close(self, token: str | None) -> None:
        if token is None:
            return
        with self._lock:
            state = self._states.pop(token, None)
        if state is not None:
            if state.connection.in_transaction:
                with suppress(sqlite3.Error):
                    state.connection.execute("ROLLBACK")
            state.connection.close()


_UNIT_OF_WORKS = _UnitOfWorkRegistry()


@dataclass(frozen=True, slots=True)
class _FactoryConfiguration:
    database: Path
    project_id: str


class _FactoryRegistry:
    """Composition configuration retained outside every returned business port."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._configurations: dict[str, _FactoryConfiguration] = {}

    def register(self, database: Path, project_id: str) -> str:
        with self._lock:
            while True:
                token = secrets.token_hex(32)
                if token not in self._configurations:
                    self._configurations[token] = _FactoryConfiguration(Path(database), project_id)
                    return token

    def configuration(self, token: str) -> _FactoryConfiguration:
        with self._lock:
            configuration = self._configurations.get(token)
        if configuration is None:
            raise RepositoryTransactionFailed("unit-of-work factory is unavailable")
        return configuration


_FACTORIES = _FactoryRegistry()


def _event_digest(project_id: str, revision: AggregateRevision, event: AtomicRepositoryEvent) -> str:
    document = {
        "actorId": event.actor_id,
        "actorType": event.actor_type,
        "aggregateId": revision.aggregate_id,
        "eventId": event.event_id,
        "eventType": event.event_type,
        "occurredAt": event.occurred_at,
        "projectId": project_id,
        "revision": revision.revision,
        "revisionId": revision.revision_id,
        "traceId": event.trace_id,
    }
    payload = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _projection(row: Any) -> AggregateRevision:
    values: tuple[Any, ...] = tuple(row)
    return AggregateRevision(
        revision_id=str(values[0]),
        aggregate_id=str(values[1]),
        aggregate_kind=cast(AggregateKind, values[2]),
        project_id=str(values[3]),
        revision=int(values[4]),
        contract_version=str(values[5]),
        created_at=str(values[6]),
        modified_at=str(values[7]),
        display_label_observed=str(values[8]),
        display_label_normalized=None if values[9] is None else str(values[9]),
        knowledge_status=cast(KnowledgeStatus, values[10]),
        rights_status=cast(RightsStatus, values[11]),
        object_sha256=None if values[12] is None else str(values[12]),
    )


class SqliteAggregateRepository:
    """SQLAlchemy 2 Core adapter for the canonical aggregate repository port."""

    __slots__ = ("__token",)

    def __init__(self, token: str) -> None:
        self.__token = token

    def _state(self) -> _UnitOfWorkState:
        return _UNIT_OF_WORKS.state(self.__token)

    def get(self, aggregate_id: str) -> AggregateRevision:
        state = self._state()
        statement = (
            select(
                _REVISIONS.c.revision_id,
                _REVISIONS.c.aggregate_id,
                _REVISIONS.c.aggregate_kind,
                _REVISIONS.c.project_id,
                _REVISIONS.c.revision,
                _REVISIONS.c.contract_version,
                _REVISIONS.c.created_at,
                _REVISIONS.c.modified_at,
                _REVISIONS.c.display_label_observed,
                _REVISIONS.c.display_label_normalized,
                _REVISIONS.c.knowledge_status,
                _REVISIONS.c.rights_status,
                _DOCUMENTS.c.object_sha256,
            )
            .select_from(
                _REVISIONS.outerjoin(
                    _DOCUMENTS,
                    (_REVISIONS.c.revision_id == _DOCUMENTS.c.revision_id)
                    & (_REVISIONS.c.project_id == _DOCUMENTS.c.project_id),
                )
            )
            .where((_REVISIONS.c.aggregate_id == aggregate_id) & (_REVISIONS.c.project_id == state.project_id))
            .order_by(desc(_REVISIONS.c.revision))
            .limit(1)
        )
        row = _execute(state.connection, statement).fetchone()
        if row is None:
            raise RepositoryNotFound("aggregate was not found")
        return _projection(row)

    def append(
        self,
        draft: AggregateRevisionDraft,
        event: AtomicRepositoryEvent,
        *,
        expected_revision: int | None,
    ) -> AggregateRevision:
        state = self._state()
        if expected_revision is not None and (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or not 0 <= expected_revision < MAX_SAFE_INTEGER
        ):
            self._mark_failed()
            raise RepositoryConflict("expected revision is invalid")
        if draft.aggregate_kind != "document" and draft.object_sha256 is not None:
            self._mark_failed()
            raise RepositoryProblem("object identity is only valid for documents")

        current = self._current(draft.aggregate_id)
        if current is None:
            if expected_revision is not None:
                self._mark_failed()
                raise RepositoryNotFound("aggregate was not found")
            revision_number = 0
        else:
            if expected_revision is None or current.revision != expected_revision:
                self._mark_failed()
                raise RepositoryConflict("aggregate revision changed")
            if (
                current.aggregate_kind != draft.aggregate_kind
                or current.created_at != draft.created_at
                or draft.modified_at < current.modified_at
            ):
                self._mark_failed()
                raise RepositoryConflict("aggregate identity contract changed")
            revision_number = current.revision + 1

        projection = AggregateRevision(
            revision_id=draft.revision_id,
            aggregate_id=draft.aggregate_id,
            aggregate_kind=draft.aggregate_kind,
            project_id=state.project_id,
            revision=revision_number,
            contract_version="1.0.0",
            created_at=draft.created_at,
            modified_at=draft.modified_at,
            display_label_observed=draft.display_label_observed,
            display_label_normalized=draft.display_label_normalized,
            knowledge_status=draft.knowledge_status,
            rights_status=draft.rights_status,
            object_sha256=draft.object_sha256,
        )
        try:
            if current is None:
                _execute(
                    state.connection,
                    insert(_IDENTITIES).values(
                        aggregate_id=projection.aggregate_id,
                        project_id=projection.project_id,
                        aggregate_kind=projection.aggregate_kind,
                        created_at=projection.created_at,
                    ),
                )
            _execute(
                state.connection,
                insert(_REVISIONS).values(
                    revision_id=projection.revision_id,
                    aggregate_id=projection.aggregate_id,
                    aggregate_kind=projection.aggregate_kind,
                    project_id=projection.project_id,
                    revision=projection.revision,
                    contract_version=projection.contract_version,
                    created_at=projection.created_at,
                    modified_at=projection.modified_at,
                    display_label_observed=projection.display_label_observed,
                    display_label_normalized=projection.display_label_normalized,
                    knowledge_status=projection.knowledge_status,
                    rights_status=projection.rights_status,
                ),
            )
            if projection.aggregate_kind == "document":
                _execute(
                    state.connection,
                    insert(_DOCUMENTS).values(
                        revision_id=projection.revision_id,
                        project_id=projection.project_id,
                        object_sha256=projection.object_sha256,
                    ),
                )
            else:
                _execute(
                    state.connection,
                    insert(_EXTENSIONS[projection.aggregate_kind]).values(revision_id=projection.revision_id),
                )
            record_sha256 = _event_digest(state.project_id, projection, event)
            _execute(
                state.connection,
                insert(_PROVENANCE).values(
                    event_id=event.event_id,
                    project_id=state.project_id,
                    revision_id=projection.revision_id,
                    event_type=event.event_type,
                    occurred_at=event.occurred_at,
                    trace_id=event.trace_id,
                    actor_type=event.actor_type,
                    actor_id=event.actor_id,
                    record_sha256=record_sha256,
                ),
            )
            _execute(
                state.connection,
                insert(_OUTBOX).values(
                    outbox_id=event.outbox_id,
                    project_id=state.project_id,
                    revision_id=projection.revision_id,
                    event_type=event.event_type,
                    occurred_at=event.occurred_at,
                    available_at=event.available_at,
                    state="pending",
                    attempt_count=0,
                    published_at=None,
                    idempotency_key=event.idempotency_key,
                    record_sha256=record_sha256,
                ),
            )
        except (KeyError, sqlite3.Error, ValueError) as error:
            self._mark_failed()
            raise RepositoryProblem() from error
        return projection

    def _current(self, aggregate_id: str) -> AggregateRevision | None:
        try:
            return self.get(aggregate_id)
        except RepositoryNotFound:
            return None

    def _mark_failed(self) -> None:
        _UNIT_OF_WORKS.fail(self.__token)


class SqliteUnitOfWork:
    """One explicit SQLite writer transaction with no exposed database handle."""

    __slots__ = ("__factory_token", "__token")

    def __init__(self, factory_token: str) -> None:
        self.__factory_token = factory_token
        self.__token: str | None = None

    @property
    def aggregates(self) -> AggregateRepository:
        if self.__token is None:
            raise RepositoryTransactionFailed("unit of work is not active")
        _UNIT_OF_WORKS.state(self.__token)
        return SqliteAggregateRepository(self.__token)

    def __enter__(self) -> SqliteUnitOfWork:
        if self.__token is not None:
            raise RepositoryTransactionFailed("unit of work cannot be re-entered")
        configuration = _FACTORIES.configuration(self.__factory_token)
        connection = open_canonical_database(
            configuration.database,
            expected_project_id=configuration.project_id,
        )
        try:
            connection.execute("BEGIN IMMEDIATE")
            self.__token = _UNIT_OF_WORKS.register(connection, configuration.project_id)
            return self
        except BaseException:
            connection.close()
            raise

    def commit(self) -> None:
        if self.__token is None:
            raise RepositoryTransactionFailed("unit of work is not active")
        _UNIT_OF_WORKS.finish(self.__token, commit=True)

    def rollback(self) -> None:
        if self.__token is None:
            raise RepositoryTransactionFailed("unit of work is not active")
        _UNIT_OF_WORKS.finish(self.__token, commit=False)

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        token = self.__token
        self.__token = None
        if token is not None:
            state = _UNIT_OF_WORKS.state(token, active=False)
            if not state.completed and state.connection.in_transaction:
                with suppress(RepositoryProblem):
                    _UNIT_OF_WORKS.finish(token, commit=False)
            _UNIT_OF_WORKS.close(token)


class SqliteUnitOfWorkFactory:
    """Composition-root adapter; business services should type against UnitOfWorkFactory."""

    __slots__ = ("__token",)

    def __init__(self, database: Path, project_id: str) -> None:
        self.__token = _FACTORIES.register(database, project_id)

    def __call__(self) -> UnitOfWork:
        return SqliteUnitOfWork(self.__token)


__all__ = [
    "ActorType",
    "AggregateKind",
    "AggregateRepository",
    "AggregateRevision",
    "AggregateRevisionDraft",
    "AtomicRepositoryEvent",
    "KnowledgeStatus",
    "RepositoryConflict",
    "RepositoryNotFound",
    "RepositoryProblem",
    "RepositoryTransactionFailed",
    "RightsStatus",
    "SqliteUnitOfWorkFactory",
    "UnitOfWork",
    "UnitOfWorkFactory",
]
