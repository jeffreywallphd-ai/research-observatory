"""Private SQLAlchemy/SQLite adapter for the dependency-neutral repository ports."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy import Column, Integer, MetaData, String, Table, desc, insert, select
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.sql import ClauseElement

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.repositories import (
    AggregateKind,
    AggregateRepository,
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    IntentAuditEvent,
    IntentPolicyAuditEvent,
    IntentPolicyDecisionRecord,
    IntentRevisionRecord,
    IntentRevisionRepository,
    KnowledgeStatus,
    LineageDirection,
    LineageNode,
    LineagePage,
    PrivacyAuditEvent,
    PrivacyPolicyRecord,
    PrivacyPolicyRepository,
    PrivacySetting,
    ProvenanceLedgerRepository,
    RepositoryConflict,
    RepositoryIdempotencyConflict,
    RepositoryNotFound,
    RepositoryProblem,
    RepositoryTransactionFailed,
    RightsStatus,
    UnitOfWork,
    UnitOfWorkFactory,
)
from .provenance import canonical_aggregate_provenance_event, canonical_invalidation_provenance_event
from .provenance_contracts import canonical_provenance_json, decode_provenance_event, provenance_record_sha256
from .storage import MAX_SAFE_INTEGER, CanonicalConnection, StorageProblem, open_canonical_database

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
_LEDGER = Table(
    "provenance_ledger_events",
    _METADATA,
    Column("event_id", String),
    Column("project_id", String),
    Column("segment_key", String),
    Column("sequence", Integer),
    Column("subject", String),
    Column("event_type", String),
    Column("occurred_at", String),
    Column("correlation_id", String),
    Column("causation_id", String),
    Column("activity_id", String),
    Column("activity_type", String),
    Column("activity_status", String),
    Column("agent_id", String),
    Column("sensitivity", String),
    Column("retention_class", String),
    Column("record_json", String),
    Column("record_sha256", String),
    Column("idempotency_sha256", String),
    Column("previous_chain_sha256", String),
    Column("chain_sha256", String),
)
_DOCUMENTS = Table(
    "documents",
    _METADATA,
    Column("revision_id", String),
    Column("project_id", String),
    Column("object_sha256", String),
)
_OBJECTS = Table(
    "object_records",
    _METADATA,
    Column("object_sha256", String),
    Column("project_id", String),
    Column("storage_state", String),
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


class _SqlitePrivacyPolicyRepository(PrivacyPolicyRepository):
    """Canonical SQLite adapter for complete append-only privacy revisions."""

    def __init__(self, database: Path, project_id: str) -> None:
        if not database.is_absolute() or not project_id:
            raise ValueError("privacy repository authority is invalid")
        self._database = database
        self._project_id = project_id

    def _open(self) -> CanonicalConnection:
        return open_canonical_database(self._database, expected_project_id=self._project_id)

    def read(self) -> PrivacyPolicyRecord | None:
        try:
            connection = self._open()
            try:
                maximum = connection.execute(
                    "SELECT MAX(revision) FROM settings WHERE project_id=? AND setting_key LIKE 'privacy.%'",
                    (self._project_id,),
                ).fetchone()[0]
                if maximum is None:
                    return None
                revision = int(maximum)
                rows = connection.execute(
                    """
                    SELECT setting_key, value_type, text_value, integer_value
                      FROM settings
                     WHERE project_id=? AND revision=? AND setting_key LIKE 'privacy.%'
                     ORDER BY setting_key
                    """,
                    (self._project_id, revision),
                ).fetchall()
            finally:
                connection.close()
        except OSError, sqlite3.Error, StorageProblem, TypeError, ValueError, IndexError:
            raise _transaction_failure("privacy policy read failed") from None
        settings: list[PrivacySetting] = []
        for key, value_type, text_value, integer_value in rows:
            if value_type == "text" and isinstance(text_value, str) and integer_value is None:
                value: str | int = text_value
            elif value_type == "integer" and isinstance(integer_value, int) and text_value is None:
                value = integer_value
            else:
                raise _transaction_failure("privacy policy scalar is invalid")
            settings.append(PrivacySetting(key=str(key), value=value))
        return PrivacyPolicyRecord(revision=revision, settings=tuple(settings))

    def append(
        self,
        *,
        expected_revision: int,
        revision: int,
        settings: tuple[PrivacySetting, ...],
        event: PrivacyAuditEvent,
    ) -> None:
        keys = tuple(setting.key for setting in settings)
        if (
            expected_revision < 0
            or revision != expected_revision + 1
            or not settings
            or keys != tuple(sorted(set(keys)))
            or any(not key.startswith("privacy.") for key in keys)
            or any(
                not isinstance(setting.value, str)
                and (not isinstance(setting.value, int) or isinstance(setting.value, bool))
                for setting in settings
            )
        ):
            raise _transaction_failure("privacy policy append is invalid")
        try:
            connection = self._open()
            try:
                connection.execute("BEGIN IMMEDIATE")
                latest = connection.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM settings "
                    "WHERE project_id=? AND setting_key LIKE 'privacy.%'",
                    (self._project_id,),
                ).fetchone()[0]
                if int(latest) != expected_revision:
                    raise RepositoryConflict("privacy revision changed")
                for setting in settings:
                    value = setting.value
                    connection.execute(
                        """
                        INSERT INTO settings (
                            setting_id, project_id, setting_key, revision, value_type,
                            text_value, integer_value, real_value, boolean_value,
                            created_at, modified_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                        """,
                        (
                            new_uuid_v7(),
                            self._project_id,
                            setting.key,
                            revision,
                            "integer" if isinstance(value, int) else "text",
                            None if isinstance(value, int) else value,
                            value if isinstance(value, int) else None,
                            event.occurred_at,
                            event.occurred_at,
                        ),
                    )
                self._append_event(connection, event)
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
        except RepositoryConflict:
            raise
        except OSError, sqlite3.Error, StorageProblem, TypeError, ValueError:
            raise _transaction_failure("privacy policy append failed") from None

    def append_event(self, event: PrivacyAuditEvent) -> None:
        try:
            connection = self._open()
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._append_event(connection, event)
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
        except OSError, sqlite3.Error, StorageProblem, TypeError, ValueError:
            raise _transaction_failure("privacy audit append failed") from None

    def _append_event(self, connection: CanonicalConnection, event: PrivacyAuditEvent) -> None:
        connection.execute(
            """
            INSERT INTO provenance_events (
                event_id, project_id, revision_id, event_type, occurred_at,
                trace_id, actor_type, actor_id, record_sha256
            ) VALUES (?, ?, NULL, ?, ?, ?, 'human', NULL, ?)
            """,
            (
                event.event_id,
                self._project_id,
                event.event_type,
                event.occurred_at,
                event.trace_id,
                event.record_sha256,
            ),
        )


def sqlite_privacy_policy_repository(path: Path, project_id: str) -> PrivacyPolicyRepository:
    """Compose one privacy repository from lifecycle-validated project authority."""

    return _SqlitePrivacyPolicyRepository(path / "state" / "project.sqlite3", project_id)


_INTENT_BRIDGE_KEY = "research-intent.project-id-bridge"
_INTENT_IDEMPOTENCY_KEY = "research-intent.idempotency"
_INTENT_POLICY_DECISION_KEY = "research-intent.policy-decision"
_INTENT_REVISION_KEY = "research-intent.revision"


class _SqliteIntentRevisionRepository(IntentRevisionRepository):
    """SQLite adapter over the existing immutable settings/provenance/outbox schema."""

    def __init__(self, database: Path, project_id: str) -> None:
        if not database.is_absolute() or not project_id:
            raise ValueError("intent repository authority is invalid")
        self._database = database
        self._project_id = project_id

    def _open(self) -> CanonicalConnection:
        return open_canonical_database(self._database, expected_project_id=self._project_id)

    def read(self) -> tuple[IntentRevisionRecord, ...]:
        try:
            connection = self._open()
            try:
                bridge = connection.execute(
                    "SELECT revision, value_type, text_value FROM settings "
                    "WHERE project_id=? AND setting_key=? ORDER BY revision",
                    (self._project_id, _INTENT_BRIDGE_KEY),
                ).fetchall()
                rows = connection.execute(
                    "SELECT revision, value_type, text_value FROM settings "
                    "WHERE project_id=? AND setting_key=? ORDER BY revision DESC LIMIT 100",
                    (self._project_id, _INTENT_REVISION_KEY),
                ).fetchall()
            finally:
                connection.close()
        except OSError, sqlite3.Error, StorageProblem, TypeError, ValueError, IndexError:
            raise _transaction_failure("research intent read failed") from None
        if not rows:
            if bridge:
                raise _transaction_failure("research intent bridge has no revision")
            return ()
        if len(bridge) != 1 or bridge[0][0] != 0 or bridge[0][1] != "text" or not isinstance(bridge[0][2], str):
            raise _transaction_failure("research intent bridge is invalid")
        try:
            bridge_value = json.loads(bridge[0][2])
        except json.JSONDecodeError, TypeError:
            raise _transaction_failure("research intent bridge is invalid") from None
        if (
            not isinstance(bridge_value, dict)
            or set(bridge_value) != {"authority", "domainProjectId", "manifestProjectId", "schemaVersion"}
            or bridge_value["schemaVersion"] != "1.0"
            or bridge_value["authority"] != "ADR-0013"
            or bridge_value["manifestProjectId"] != self._project_id
        ):
            raise _transaction_failure("research intent bridge is invalid")
        records: list[IntentRevisionRecord] = []
        for revision, value_type, content_json in rows:
            if (
                not isinstance(revision, int)
                or revision < 1
                or value_type != "text"
                or not isinstance(content_json, str)
            ):
                raise _transaction_failure("research intent revision is invalid")
            records.append(IntentRevisionRecord(revision=revision, content_json=content_json))
        if [record.revision for record in records] != list(
            range(records[0].revision, max(0, records[0].revision - len(records)), -1)
        ):
            raise _transaction_failure("research intent revision history is discontinuous")
        return tuple(records)

    def replay(
        self,
        *,
        manifest_project_id: str,
        actor_id: str,
        idempotency_key: str,
        command_sha256: str,
        event_type: str = "intent.draft.saved",
    ) -> IntentRevisionRecord | None:
        if manifest_project_id != self._project_id:
            raise RepositoryIdempotencyConflict("research intent project differs")
        try:
            connection = self._open()
            try:
                return self._replay_from_connection(
                    connection,
                    manifest_project_id=manifest_project_id,
                    actor_id=actor_id,
                    idempotency_key=idempotency_key,
                    command_sha256=command_sha256,
                    event_type=event_type,
                )
            finally:
                connection.close()
        except RepositoryIdempotencyConflict:
            raise
        except OSError, sqlite3.Error, StorageProblem, TypeError, ValueError, IndexError:
            raise _transaction_failure("research intent idempotency replay failed") from None

    def _replay_from_connection(
        self,
        connection: CanonicalConnection,
        *,
        manifest_project_id: str,
        actor_id: str,
        idempotency_key: str,
        command_sha256: str,
        event_type: str,
    ) -> IntentRevisionRecord | None:
        if (
            manifest_project_id != self._project_id
            or not is_uuid_v7(actor_id)
            or len(idempotency_key) != 32
            or any(value not in "0123456789abcdef" for value in idempotency_key)
            or len(command_sha256) != 64
            or any(value not in "0123456789abcdef" for value in command_sha256)
            or event_type not in {"intent.draft.saved", "intent.accepted"}
        ):
            raise RepositoryIdempotencyConflict("research intent command authority differs")
        rows = connection.execute(
            "SELECT revision, value_type, text_value FROM settings "
            "WHERE project_id=? AND setting_key=? ORDER BY revision",
            (self._project_id, _INTENT_IDEMPOTENCY_KEY),
        ).fetchall()
        matches: list[tuple[int, dict[str, object]]] = []
        legacy_fields = {
            "actorId",
            "actorType",
            "commandSha256",
            "domainProjectId",
            "eventId",
            "idempotencyKey",
            "manifestProjectId",
            "outboxId",
            "revision",
            "revisionRecordSha256",
            "schemaVersion",
        }
        current_fields = legacy_fields | {"eventType"}
        for revision, value_type, text_value in rows:
            if not isinstance(revision, int) or revision < 1 or value_type != "text" or not isinstance(text_value, str):
                raise _transaction_failure("research intent idempotency record is invalid")
            try:
                binding = json.loads(text_value)
            except json.JSONDecodeError, TypeError:
                raise _transaction_failure("research intent idempotency record is invalid") from None
            if (
                not isinstance(binding, dict)
                or frozenset(binding) not in {frozenset(legacy_fields), frozenset(current_fields)}
                or binding.get("schemaVersion") not in {"1.0", "1.1"}
                or (set(binding) == legacy_fields and binding.get("schemaVersion") != "1.0")
                or (set(binding) == current_fields and binding.get("schemaVersion") != "1.1")
                or binding.get("revision") != revision
                or binding.get("actorType") != "human"
                or binding.get("manifestProjectId") != self._project_id
                or not isinstance(binding.get("domainProjectId"), str)
                or not is_uuid_v7(binding.get("actorId"))
                or not is_uuid_v7(binding.get("eventId"))
                or not is_uuid_v7(binding.get("outboxId"))
                or not isinstance(binding.get("idempotencyKey"), str)
                or not isinstance(binding.get("commandSha256"), str)
                or not isinstance(binding.get("revisionRecordSha256"), str)
            ):
                raise _transaction_failure("research intent idempotency record is invalid")
            if binding["idempotencyKey"] == idempotency_key:
                matches.append((revision, cast(dict[str, object], binding)))
        if not matches:
            orphan = connection.execute(
                "SELECT 1 FROM outbox_events WHERE project_id=? AND idempotency_key=?",
                (self._project_id, idempotency_key),
            ).fetchone()
            if orphan is not None:
                raise _transaction_failure("research intent idempotency binding is incomplete")
            return None
        if len(matches) != 1:
            raise _transaction_failure("research intent idempotency binding is ambiguous")
        revision, binding = matches[0]
        binding_event_type = cast(str, binding.get("eventType", "intent.draft.saved"))
        if (
            binding["actorId"] != actor_id
            or binding["actorType"] != "human"
            or binding["commandSha256"] != command_sha256
            or binding["manifestProjectId"] != manifest_project_id
            or binding_event_type != event_type
        ):
            raise RepositoryIdempotencyConflict("research intent command key is already bound")
        revision_row = connection.execute(
            "SELECT value_type, text_value FROM settings WHERE project_id=? AND setting_key=? AND revision=?",
            (self._project_id, _INTENT_REVISION_KEY, revision),
        ).fetchone()
        if revision_row is None or revision_row[0] != "text" or not isinstance(revision_row[1], str):
            raise _transaction_failure("research intent idempotency result is unavailable")
        content_json = revision_row[1]
        revision_digest = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
        if revision_digest != binding["revisionRecordSha256"]:
            raise _transaction_failure("research intent idempotency result differs")
        try:
            revision_value = json.loads(content_json)
        except json.JSONDecodeError, TypeError:
            raise _transaction_failure("research intent idempotency result is invalid") from None
        if (
            not isinstance(revision_value, dict)
            or revision_value.get("revision") != revision
            or revision_value.get("projectId") != binding["domainProjectId"]
            or revision_value.get("createdBy") != {"actorId": actor_id, "actorType": "human"}
        ):
            raise _transaction_failure("research intent idempotency result authority differs")
        provenance = connection.execute(
            "SELECT event_type, actor_type, actor_id, record_sha256 FROM provenance_events "
            "WHERE project_id=? AND event_id=?",
            (self._project_id, binding["eventId"]),
        ).fetchone()
        if provenance is None or tuple(provenance) != (binding_event_type, "human", actor_id, revision_digest):
            raise _transaction_failure("research intent provenance binding differs")
        outbox = connection.execute(
            "SELECT event_type, idempotency_key, record_sha256 FROM outbox_events WHERE project_id=? AND outbox_id=?",
            (self._project_id, binding["outboxId"]),
        ).fetchone()
        if outbox is None or tuple(outbox) != (binding_event_type, idempotency_key, command_sha256):
            raise _transaction_failure("research intent outbox binding differs")
        return IntentRevisionRecord(revision=revision, content_json=content_json)

    def append(
        self,
        *,
        expected_revision: int,
        domain_project_id: str,
        manifest_project_id: str,
        record: IntentRevisionRecord,
        event: IntentAuditEvent,
    ) -> IntentRevisionRecord:
        if (
            manifest_project_id != self._project_id
            or expected_revision < 0
            or record.revision != expected_revision + 1
            or not record.content_json
            or len(record.content_json.encode("utf-8")) > 65_536
            or event.event_type not in {"intent.draft.saved", "intent.accepted"}
            or event.actor_type != "human"
            or not is_uuid_v7(event.actor_id)
            or len(event.idempotency_key) != 32
            or any(value not in "0123456789abcdef" for value in event.idempotency_key)
            or len(event.command_sha256) != 64
            or any(value not in "0123456789abcdef" for value in event.command_sha256)
            or hashlib.sha256(record.content_json.encode("utf-8")).hexdigest() != event.record_sha256
        ):
            raise _transaction_failure("research intent append is invalid")
        try:
            revision_value = json.loads(record.content_json)
        except json.JSONDecodeError, TypeError:
            raise _transaction_failure("research intent append is invalid") from None
        if (
            not isinstance(revision_value, dict)
            or revision_value.get("revision") != record.revision
            or revision_value.get("projectId") != domain_project_id
            or revision_value.get("createdBy") != {"actorId": event.actor_id, "actorType": "human"}
            or (event.event_type == "intent.draft.saved" and revision_value.get("status") != "draft")
            or (event.event_type == "intent.accepted" and revision_value.get("status") != "accepted")
        ):
            raise _transaction_failure("research intent append authority differs")
        bridge_json = json.dumps(
            {
                "authority": "ADR-0013",
                "domainProjectId": domain_project_id,
                "manifestProjectId": manifest_project_id,
                "schemaVersion": "1.0",
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            connection = self._open()
            try:
                connection.execute("BEGIN IMMEDIATE")
                replay = self._replay_from_connection(
                    connection,
                    manifest_project_id=manifest_project_id,
                    actor_id=event.actor_id,
                    idempotency_key=event.idempotency_key,
                    command_sha256=event.command_sha256,
                    event_type=event.event_type,
                )
                if replay is not None:
                    connection.execute("COMMIT")
                    return replay
                latest = connection.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM settings WHERE project_id=? AND setting_key=?",
                    (self._project_id, _INTENT_REVISION_KEY),
                ).fetchone()[0]
                if int(latest) != expected_revision:
                    raise RepositoryConflict("research intent revision changed")
                bridge = connection.execute(
                    "SELECT text_value FROM settings WHERE project_id=? AND setting_key=? AND revision=0",
                    (self._project_id, _INTENT_BRIDGE_KEY),
                ).fetchone()
                if expected_revision == 0:
                    if bridge is not None:
                        raise RepositoryConflict("research intent bridge already exists")
                    self._insert_text_setting(
                        connection,
                        key=_INTENT_BRIDGE_KEY,
                        revision=0,
                        value=bridge_json,
                        occurred_at=event.occurred_at,
                    )
                elif bridge is None or bridge[0] != bridge_json:
                    raise RepositoryConflict("research intent project bridge changed")
                self._insert_text_setting(
                    connection,
                    key=_INTENT_REVISION_KEY,
                    revision=record.revision,
                    value=record.content_json,
                    occurred_at=event.occurred_at,
                )
                idempotency_json = json.dumps(
                    {
                        "actorId": event.actor_id,
                        "actorType": event.actor_type,
                        "commandSha256": event.command_sha256,
                        "domainProjectId": domain_project_id,
                        "eventId": event.event_id,
                        "eventType": event.event_type,
                        "idempotencyKey": event.idempotency_key,
                        "manifestProjectId": manifest_project_id,
                        "outboxId": event.outbox_id,
                        "revision": record.revision,
                        "revisionRecordSha256": event.record_sha256,
                        "schemaVersion": "1.1",
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                self._insert_text_setting(
                    connection,
                    key=_INTENT_IDEMPOTENCY_KEY,
                    revision=record.revision,
                    value=idempotency_json,
                    occurred_at=event.occurred_at,
                )
                connection.execute(
                    """
                    INSERT INTO provenance_events (
                        event_id, project_id, revision_id, event_type, occurred_at,
                        trace_id, actor_type, actor_id, record_sha256
                    ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        self._project_id,
                        event.event_type,
                        event.occurred_at,
                        event.trace_id,
                        event.actor_type,
                        event.actor_id,
                        event.record_sha256,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO outbox_events (
                        outbox_id, project_id, revision_id, event_type, occurred_at,
                        available_at, state, attempt_count, published_at,
                        idempotency_key, record_sha256
                    ) VALUES (?, ?, NULL, ?, ?, ?, 'pending', 0, NULL, ?, ?)
                    """,
                    (
                        event.outbox_id,
                        self._project_id,
                        event.event_type,
                        event.occurred_at,
                        event.occurred_at,
                        event.idempotency_key,
                        event.command_sha256,
                    ),
                )
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
        except OSError, sqlite3.Error, StorageProblem, TypeError, ValueError:
            raise _transaction_failure("research intent append failed") from None

    def append_policy_decision(
        self,
        *,
        record: IntentPolicyDecisionRecord,
        event: IntentPolicyAuditEvent,
    ) -> None:
        if (
            not is_uuid_v7(record.decision_id)
            or not record.content_json
            or len(record.content_json.encode("utf-8")) > 16_384
            or not is_uuid_v7(event.event_id)
            or event.actor_type != "human"
            or not is_uuid_v7(event.actor_id)
            or hashlib.sha256(record.content_json.encode("utf-8")).hexdigest() != event.record_sha256
        ):
            raise _transaction_failure("research intent policy decision is invalid")
        try:
            value = json.loads(record.content_json)
        except json.JSONDecodeError, TypeError:
            raise _transaction_failure("research intent policy decision is invalid") from None
        if (
            not isinstance(value, dict)
            or value.get("decisionId") != record.decision_id
            or value.get("actorId") != event.actor_id
            or value.get("eventType") != "intent.policy.evaluated"
        ):
            raise _transaction_failure("research intent policy authority differs")
        try:
            connection = self._open()
            try:
                connection.execute("BEGIN IMMEDIATE")
                next_revision = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(revision), 0) + 1 FROM settings WHERE project_id=? AND setting_key=?",
                        (self._project_id, _INTENT_POLICY_DECISION_KEY),
                    ).fetchone()[0]
                )
                self._insert_text_setting(
                    connection,
                    key=_INTENT_POLICY_DECISION_KEY,
                    revision=next_revision,
                    value=record.content_json,
                    occurred_at=event.occurred_at,
                )
                connection.execute(
                    """
                    INSERT INTO provenance_events (
                        event_id, project_id, revision_id, event_type, occurred_at,
                        trace_id, actor_type, actor_id, record_sha256
                    ) VALUES (?, ?, NULL, 'intent.policy.evaluated', ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        self._project_id,
                        event.occurred_at,
                        event.trace_id,
                        event.actor_type,
                        event.actor_id,
                        event.record_sha256,
                    ),
                )
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
        except OSError, sqlite3.Error, StorageProblem, TypeError, ValueError:
            raise _transaction_failure("research intent policy decision append failed") from None

    def _insert_text_setting(
        self,
        connection: CanonicalConnection,
        *,
        key: str,
        revision: int,
        value: str,
        occurred_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO settings (
                setting_id, project_id, setting_key, revision, value_type,
                text_value, integer_value, real_value, boolean_value,
                created_at, modified_at
            ) VALUES (?, ?, ?, ?, 'text', ?, NULL, NULL, NULL, ?, ?)
            """,
            (new_uuid_v7(), self._project_id, key, revision, value, occurred_at, occurred_at),
        )


def sqlite_intent_revision_repository(path: Path, project_id: str) -> IntentRevisionRepository:
    """Compose intent persistence after lifecycle validation binds the project root."""

    return _SqliteIntentRevisionRepository(path / "state" / "project.sqlite3", project_id)


def _transaction_failure(message: str = "canonical repository transaction failed") -> RepositoryTransactionFailed:
    """Create a bounded failure after the concrete adapter exception is out of scope."""

    failure = RepositoryTransactionFailed(message)
    failure.__cause__ = None
    failure.__context__ = None
    failure.__suppress_context__ = True
    return failure


def _repository_failure(message: str = "canonical repository operation failed") -> RepositoryProblem:
    """Create a bounded operation failure without retaining adapter details."""

    failure = RepositoryProblem(message)
    failure.__cause__ = None
    failure.__context__ = None
    failure.__suppress_context__ = True
    return failure


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
        except sqlite3.Error, StorageProblem:
            state.failed = True
            if state.connection.in_transaction:
                with suppress(sqlite3.Error):
                    state.connection.execute("ROLLBACK")
        else:
            return
        raise _transaction_failure()

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


def _command_fingerprint(
    project_id: str,
    revision: AggregateRevision,
    event: AtomicRepositoryEvent,
    expected_revision: int | None,
    provenance_inputs: tuple[AggregateRevision, ...] = (),
) -> str:
    document = {
        "actorId": event.actor_id,
        "actorType": event.actor_type,
        "aggregateId": revision.aggregate_id,
        "aggregateKind": revision.aggregate_kind,
        "availableAt": event.available_at,
        "contractVersion": revision.contract_version,
        "createdAt": revision.created_at,
        "displayLabelNormalized": revision.display_label_normalized,
        "displayLabelObserved": revision.display_label_observed,
        "eventId": event.event_id,
        "eventType": event.event_type,
        "expectedRevision": expected_revision,
        "idempotencyKey": event.idempotency_key,
        "knowledgeStatus": revision.knowledge_status,
        "modifiedAt": revision.modified_at,
        "objectSha256": revision.object_sha256,
        "occurredAt": event.occurred_at,
        "outboxId": event.outbox_id,
        "projectId": project_id,
        "provenanceInputs": [
            {"contentHash": _projection_content_sha256(item), "revisionId": item.revision_id}
            for item in provenance_inputs
        ],
        "revision": revision.revision,
        "revisionId": revision.revision_id,
        "rightsStatus": revision.rights_status,
        "traceId": event.trace_id,
    }
    payload = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


_PROVENANCE_SEGMENT_V1 = "rfc8785.sha256.v1"
_PROVENANCE_SEGMENT_V2 = "rfc8785.sha256.v2"
_PROVENANCE_WRITE_SEGMENT = _PROVENANCE_SEGMENT_V2


def _outbox_authority_sha256(
    *,
    outbox_id: str,
    project_id: str,
    revision_id: str,
    event_type: str,
    occurred_at: str,
    available_at: str,
    idempotency_key: str,
    record_sha256: str,
) -> str:
    document = {
        "availableAt": available_at,
        "eventType": event_type,
        "idempotencyKey": idempotency_key,
        "occurredAt": occurred_at,
        "outboxId": outbox_id,
        "projectId": project_id,
        "recordSha256": record_sha256,
        "revisionId": revision_id,
    }
    payload = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _provenance_chain_sha256(
    *,
    segment_key: str,
    previous_chain_sha256: str | None,
    record_sha256: str,
    idempotency_sha256: str,
    outbox_authority_sha256: str,
    sequence: int,
) -> str:
    fields: tuple[str, ...]
    if segment_key == _PROVENANCE_SEGMENT_V1:
        fields = (previous_chain_sha256 or "genesis", record_sha256, str(sequence))
    elif segment_key == _PROVENANCE_SEGMENT_V2:
        fields = (
            previous_chain_sha256 or "genesis",
            record_sha256,
            idempotency_sha256,
            outbox_authority_sha256,
            str(sequence),
        )
    else:
        raise ValueError("provenance segment is unsupported")
    return f"sha256:{hashlib.sha256(chr(10).join(fields).encode('ascii')).hexdigest()}"


def _record_provenance(
    connection: CanonicalConnection,
    *,
    project_id: str,
    primary_revision_id: str,
    record_json: str,
    event: AtomicRepositoryEvent,
    idempotency_sha256: str,
) -> None:
    decoded = decode_provenance_event(json.loads(record_json))
    if decoded is None or canonical_provenance_json(decoded) != record_json:
        raise ValueError("aggregate provenance record is invalid")
    record_sha256 = provenance_record_sha256(decoded)
    previous_row = connection.execute(
        """
        SELECT sequence, chain_sha256
          FROM provenance_ledger_events
         WHERE project_id=? AND segment_key=?
         ORDER BY sequence DESC
         LIMIT 1
        """,
        (project_id, _PROVENANCE_WRITE_SEGMENT),
    ).fetchone()
    sequence = 1 if previous_row is None else int(previous_row[0]) + 1
    previous_chain = None if previous_row is None else str(previous_row[1])
    digest = record_sha256.removeprefix("sha256:")
    outbox_authority_sha256 = _outbox_authority_sha256(
        outbox_id=event.outbox_id,
        project_id=project_id,
        revision_id=primary_revision_id,
        event_type=str(decoded["type"]),
        occurred_at=event.occurred_at,
        available_at=event.available_at,
        idempotency_key=event.idempotency_key,
        record_sha256=digest,
    )
    chain_sha256 = _provenance_chain_sha256(
        segment_key=_PROVENANCE_WRITE_SEGMENT,
        previous_chain_sha256=previous_chain,
        record_sha256=record_sha256,
        idempotency_sha256=idempotency_sha256,
        outbox_authority_sha256=outbox_authority_sha256,
        sequence=sequence,
    )
    data = cast(dict[str, Any], decoded["data"])
    activity = cast(dict[str, Any], data["activity"])
    connection.execute(
        """
        INSERT INTO provenance_ledger_events (
            event_id, project_id, segment_key, sequence, subject, event_type,
            occurred_at, correlation_id, causation_id, activity_id, activity_type,
            activity_status, agent_id, sensitivity, retention_class, record_json,
            record_sha256, idempotency_sha256, previous_chain_sha256, chain_sha256
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decoded["id"],
            project_id,
            _PROVENANCE_WRITE_SEGMENT,
            sequence,
            decoded["subject"],
            decoded["type"],
            decoded["time"],
            decoded["correlationid"],
            decoded["causationid"],
            activity["activityId"],
            activity["activityType"],
            activity["status"],
            decoded["actorid"],
            decoded["sensitivity"],
            decoded["retentionclass"],
            record_json,
            record_sha256,
            idempotency_sha256,
            previous_chain,
            chain_sha256,
        ),
    )
    for direction in ("input", "output"):
        for entity in cast(tuple[dict[str, Any], ...], data[f"{direction}s"]):
            connection.execute(
                """
                INSERT INTO provenance_ledger_entities (
                    event_id, project_id, direction, entity_id, revision_id,
                    entity_kind, content_hash, sensitivity, retention_class
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decoded["id"],
                    project_id,
                    direction,
                    entity["entityId"],
                    entity["revisionId"],
                    entity["entityKind"],
                    entity["contentHash"],
                    entity["sensitivity"],
                    entity["retentionClass"],
                ),
            )
    for relation in cast(tuple[dict[str, Any], ...], data["relations"]):
        relation_entity = cast(dict[str, Any] | None, relation["entity"])
        related = cast(dict[str, Any] | None, relation["relatedEntity"])
        connection.execute(
            """
            INSERT INTO provenance_ledger_relations (
                event_id, project_id, relation_id, relation_type, entity_id,
                entity_revision_id, related_entity_id, related_revision_id,
                activity_id, agent_id, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decoded["id"],
                project_id,
                relation["relationId"],
                relation["relationType"],
                None if relation_entity is None else relation_entity["entityId"],
                None if relation_entity is None else relation_entity["revisionId"],
                None if related is None else related["entityId"],
                None if related is None else related["revisionId"],
                relation["activityId"],
                relation["agentId"],
                relation["occurredAt"],
            ),
        )
    connection.execute(
        """
        INSERT INTO provenance_ledger_checkpoints (
            checkpoint_id, event_id, project_id, segment_key, sequence, chain_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.outbox_id,
            event.event_id,
            project_id,
            _PROVENANCE_WRITE_SEGMENT,
            sequence,
            chain_sha256,
            event.occurred_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO provenance_events (
            event_id, project_id, revision_id, event_type, occurred_at,
            trace_id, actor_type, actor_id, record_sha256
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            project_id,
            primary_revision_id,
            decoded["type"],
            event.occurred_at,
            event.trace_id,
            event.actor_type,
            event.actor_id,
            digest,
        ),
    )
    connection.execute(
        """
        INSERT INTO outbox_events (
            outbox_id, project_id, revision_id, event_type, occurred_at,
            available_at, state, attempt_count, published_at, idempotency_key,
            record_sha256
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, NULL, ?, ?)
        """,
        (
            event.outbox_id,
            project_id,
            primary_revision_id,
            decoded["type"],
            event.occurred_at,
            event.available_at,
            event.idempotency_key,
            digest,
        ),
    )


def _record_aggregate_provenance(
    connection: CanonicalConnection,
    *,
    project_id: str,
    revision: AggregateRevision,
    previous: AggregateRevision | None,
    additional_inputs: tuple[AggregateRevision, ...],
    event: AtomicRepositoryEvent,
    idempotency_sha256: str,
) -> None:
    _record_provenance(
        connection,
        project_id=project_id,
        primary_revision_id=revision.revision_id,
        record_json=canonical_aggregate_provenance_event(
            revision=revision,
            previous=previous,
            event=event,
            additional_inputs=additional_inputs,
        ),
        event=event,
        idempotency_sha256=idempotency_sha256,
    )


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


def _projection_content_sha256(revision: AggregateRevision) -> str:
    document = {
        "aggregateId": revision.aggregate_id,
        "aggregateKind": revision.aggregate_kind,
        "contractVersion": revision.contract_version,
        "createdAt": revision.created_at,
        "displayLabelNormalized": revision.display_label_normalized,
        "displayLabelObserved": revision.display_label_observed,
        "knowledgeStatus": revision.knowledge_status,
        "modifiedAt": revision.modified_at,
        "objectSha256": revision.object_sha256,
        "projectId": revision.project_id,
        "revision": revision.revision,
        "revisionId": revision.revision_id,
        "rightsStatus": revision.rights_status,
    }
    payload = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class _SqliteAggregateRepository:
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
        try:
            row = _execute(state.connection, statement).fetchone()
        except sqlite3.Error:
            self._mark_failed()
        else:
            if row is None:
                raise RepositoryNotFound("aggregate was not found")
            return _projection(row)
        raise _transaction_failure()

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
        if len(draft.provenance_inputs) > 64 or len({item.revision_id for item in draft.provenance_inputs}) != len(
            draft.provenance_inputs
        ):
            self._mark_failed()
            raise RepositoryProblem("provenance inputs are invalid")
        for source in draft.provenance_inputs:
            stored = self._by_revision_id(source.revision_id)
            if stored != source or source.project_id != state.project_id or source.revision_id == draft.revision_id:
                self._mark_failed()
                raise RepositoryConflict("provenance input authority changed")

        revision_number = 0 if expected_revision is None else expected_revision + 1
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
        fingerprint = _command_fingerprint(
            state.project_id,
            projection,
            event,
            expected_revision,
            draft.provenance_inputs,
        )
        replay = self._replay(event, fingerprint)
        if replay is not None:
            return replay

        current = self._current(draft.aggregate_id)
        if current is None:
            if expected_revision is not None:
                self._mark_failed()
                raise RepositoryNotFound("aggregate was not found")
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
        try:
            if projection.aggregate_kind == "document" and projection.object_sha256 is not None:
                object_row = _execute(
                    state.connection,
                    select(_OBJECTS.c.storage_state).where(
                        (_OBJECTS.c.project_id == projection.project_id)
                        & (_OBJECTS.c.object_sha256 == projection.object_sha256)
                    ),
                ).fetchone()
                if object_row is None or str(object_row[0]) != "available":
                    self._mark_failed()
                    raise RepositoryConflict("document object is unavailable")
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
            _record_aggregate_provenance(
                state.connection,
                project_id=state.project_id,
                revision=projection,
                previous=current,
                additional_inputs=draft.provenance_inputs,
                event=event,
                idempotency_sha256=fingerprint,
            )
        except KeyError, sqlite3.Error, ValueError:
            self._mark_failed()
        else:
            return projection
        raise _repository_failure()

    def invalidate(self, revision_id: str, event: AtomicRepositoryEvent) -> None:
        """Append one output-free, idempotent invalidation fact for an existing revision."""

        state = self._state()
        revision = self._by_revision_id(revision_id)
        if revision is None:
            self._mark_failed()
            raise RepositoryNotFound("aggregate revision was not found")
        fingerprint = _command_fingerprint(state.project_id, revision, event, revision.revision)
        record_json = canonical_invalidation_provenance_event(revision=revision, event=event)
        try:
            existing = state.connection.execute(
                """
                SELECT outbox.outbox_id, outbox.revision_id, outbox.event_type,
                       outbox.occurred_at, outbox.available_at, outbox.idempotency_key,
                       checkpoint.event_id, ledger.record_json, ledger.idempotency_sha256
                  FROM outbox_events AS outbox
                  LEFT JOIN provenance_ledger_checkpoints AS checkpoint
                    ON checkpoint.checkpoint_id=outbox.outbox_id AND checkpoint.project_id=outbox.project_id
                  LEFT JOIN provenance_ledger_events AS ledger
                    ON ledger.event_id=checkpoint.event_id AND ledger.project_id=checkpoint.project_id
                   AND ledger.segment_key=checkpoint.segment_key
                 WHERE outbox.project_id=? AND outbox.idempotency_key=?
                """,
                (state.project_id, event.idempotency_key),
            ).fetchone()
            if existing is not None:
                decoded = decode_provenance_event(json.loads(str(existing[7])))
                data = None if decoded is None else cast(dict[str, Any], decoded["data"])
                activity = None if data is None else cast(dict[str, Any], data["activity"])
                inputs = () if data is None else cast(tuple[dict[str, Any], ...], data["inputs"])
                outputs = () if data is None else cast(tuple[dict[str, Any], ...], data["outputs"])
                if (
                    decoded is None
                    or activity is None
                    or tuple(existing[:7])
                    != (
                        event.outbox_id,
                        revision_id,
                        decoded["type"],
                        event.occurred_at,
                        event.available_at,
                        event.idempotency_key,
                        event.event_id,
                    )
                    or str(existing[8]) != fingerprint
                    or decoded["id"] != event.event_id
                    or decoded["actorid"] != event.actor_id
                    or decoded["time"] != event.occurred_at
                    or str(decoded["traceparent"]).split("-")[1] != event.trace_id
                    or activity["activityType"] != "invalidation"
                    or activity["status"] != "succeeded"
                    or len(inputs) != 1
                    or inputs[0]["revisionId"] != revision_id
                    or outputs
                    or _ledger_integrity_state(state.connection, state.project_id) != "verified"
                ):
                    self._mark_failed()
                    raise RepositoryConflict("invalidation idempotency authority differs")
                return
            _record_provenance(
                state.connection,
                project_id=state.project_id,
                primary_revision_id=revision_id,
                record_json=record_json,
                event=event,
                idempotency_sha256=fingerprint,
            )
        except sqlite3.Error, TypeError, ValueError, json.JSONDecodeError:
            self._mark_failed()
        else:
            return
        raise _repository_failure()

    def _replay(self, event: AtomicRepositoryEvent, fingerprint: str) -> AggregateRevision | None:
        state = self._state()
        try:
            row = state.connection.execute(
                """
                SELECT outbox.outbox_id, outbox.project_id, outbox.revision_id,
                       outbox.event_type, outbox.occurred_at, outbox.available_at,
                       outbox.idempotency_key, outbox.record_sha256,
                       checkpoint.event_id, checkpoint.segment_key,
                       ledger.record_json, ledger.record_sha256, ledger.idempotency_sha256
                  FROM outbox_events AS outbox
                  LEFT JOIN provenance_ledger_checkpoints AS checkpoint
                    ON checkpoint.checkpoint_id=outbox.outbox_id
                   AND checkpoint.project_id=outbox.project_id
                  LEFT JOIN provenance_ledger_events AS ledger
                    ON ledger.event_id=checkpoint.event_id
                   AND ledger.project_id=checkpoint.project_id
                   AND ledger.segment_key=checkpoint.segment_key
                 WHERE outbox.project_id=? AND outbox.idempotency_key=?
                """,
                (state.project_id, event.idempotency_key),
            ).fetchone()
        except sqlite3.Error:
            self._mark_failed()
        else:
            if row is None:
                return None
            if any(row[index] is None for index in (2, 8, 9, 10, 11, 12)):
                self._mark_failed()
                raise RepositoryTransactionFailed("idempotency record has no canonical provenance")
            try:
                decoded = decode_provenance_event(json.loads(str(row[10])))
                if decoded is None:
                    raise ValueError("canonical provenance is invalid")
                record_json = canonical_provenance_json(decoded)
                record_sha256 = provenance_record_sha256(decoded)
                data = cast(dict[str, Any], decoded["data"])
                outputs = cast(tuple[dict[str, Any], ...], data["outputs"])
                agent = cast(dict[str, Any], data["agent"])
                trace_id = str(decoded["traceparent"]).split("-")[1]
            except TypeError, ValueError, json.JSONDecodeError, IndexError:
                self._mark_failed()
                raise RepositoryTransactionFailed("idempotency canonical provenance is invalid") from None
            if len(outputs) != 1:
                self._mark_failed()
                raise RepositoryTransactionFailed("idempotency output authority is ambiguous")
            actor_type = {"human": "human", "system": "system", "software": "worker", "model": "model"}.get(
                str(agent["agentType"])
            )
            digest = record_sha256.removeprefix("sha256:")
            narrow = state.connection.execute(
                """
                SELECT project_id, revision_id, event_type, occurred_at,
                       trace_id, actor_type, actor_id, record_sha256
                  FROM provenance_events
                 WHERE event_id=?
                """,
                (str(decoded["id"]),),
            ).fetchone()
            if (
                actor_type is None
                or str(row[1]) != state.project_id
                or str(row[2]) != str(outputs[0]["revisionId"])
                or str(row[3]) != str(decoded["type"])
                or str(row[4]) != str(decoded["time"])
                or str(row[7]) != digest
                or str(row[8]) != str(decoded["id"])
                or str(row[9]) not in {_PROVENANCE_SEGMENT_V1, _PROVENANCE_SEGMENT_V2}
                or str(row[10]) != record_json
                or str(row[11]) != record_sha256
                or narrow is None
                or tuple(narrow)
                != (
                    state.project_id,
                    outputs[0]["revisionId"],
                    decoded["type"],
                    decoded["time"],
                    trace_id,
                    actor_type,
                    decoded["actorid"],
                    digest,
                )
                or _ledger_integrity_state(state.connection, state.project_id) != "verified"
            ):
                self._mark_failed()
                raise RepositoryTransactionFailed("idempotency transaction binding differs")
            if str(row[12]) != fingerprint:
                self._mark_failed()
                raise RepositoryConflict("idempotency key was used for a different command")
            if (
                str(row[0]) != event.outbox_id
                or str(row[4]) != event.occurred_at
                or str(row[5]) != event.available_at
                or str(row[6]) != event.idempotency_key
                or str(decoded["id"]) != event.event_id
                or str(decoded["actorid"]) != event.actor_id
                or actor_type != event.actor_type
                or trace_id != event.trace_id
            ):
                self._mark_failed()
                raise RepositoryConflict("idempotency command authority differs")
            replay = self._by_revision_id(str(row[2]))
            if replay is None or _projection_content_sha256(replay) != str(outputs[0]["contentHash"]):
                self._mark_failed()
                raise RepositoryTransactionFailed("idempotency record is incomplete")
            return replay
        raise _transaction_failure()

    def _by_revision_id(self, revision_id: str) -> AggregateRevision | None:
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
            .where((_REVISIONS.c.revision_id == revision_id) & (_REVISIONS.c.project_id == state.project_id))
            .limit(1)
        )
        try:
            row = _execute(state.connection, statement).fetchone()
        except sqlite3.Error:
            self._mark_failed()
        else:
            return None if row is None else _projection(row)
        raise _transaction_failure()

    def _current(self, aggregate_id: str) -> AggregateRevision | None:
        try:
            return self.get(aggregate_id)
        except RepositoryNotFound:
            return None

    def _mark_failed(self) -> None:
        _UNIT_OF_WORKS.fail(self.__token)


class _SqliteUnitOfWork:
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
        return _SqliteAggregateRepository(self.__token)

    def __enter__(self) -> _SqliteUnitOfWork:
        if self.__token is not None:
            raise RepositoryTransactionFailed("unit of work cannot be re-entered")
        configuration = _FACTORIES.configuration(self.__factory_token)
        connection: CanonicalConnection | None = None
        try:
            connection = open_canonical_database(
                configuration.database,
                expected_project_id=configuration.project_id,
            )
            connection.execute("BEGIN IMMEDIATE")
            self.__token = _UNIT_OF_WORKS.register(connection, configuration.project_id)
            return self
        except OSError, sqlite3.Error, StorageProblem:
            if connection is not None:
                connection.close()
        except BaseException:
            if connection is not None:
                connection.close()
            raise
        raise _transaction_failure("canonical transaction could not start")

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


class _SqliteUnitOfWorkFactory:
    """Composition-root adapter; business services should type against UnitOfWorkFactory."""

    __slots__ = ("__token",)

    def __init__(self, database: Path, project_id: str) -> None:
        self.__token = _FACTORIES.register(database, project_id)

    def __call__(self) -> UnitOfWork:
        return _SqliteUnitOfWork(self.__token)


def create_sqlite_unit_of_work_factory(database: Path, project_id: str) -> UnitOfWorkFactory:
    """Create the local adapter behind the dependency-neutral factory port."""

    return _SqliteUnitOfWorkFactory(database, project_id)


def _ledger_integrity_state(connection: CanonicalConnection, project_id: str) -> str:
    rows = connection.execute(
        """
        SELECT event_id, project_id, segment_key, sequence, record_json, record_sha256,
               idempotency_sha256, previous_chain_sha256, chain_sha256, subject, event_type,
               occurred_at, correlation_id, causation_id, activity_id,
               activity_type, activity_status, agent_id, sensitivity,
               retention_class
          FROM provenance_ledger_events
         ORDER BY segment_key, sequence
        """,
    ).fetchall()
    entities_by_event: dict[str, set[tuple[Any, ...]]] = {}
    for candidate in connection.execute(
        """
        SELECT event_id, project_id, direction, entity_id, revision_id, entity_kind,
               content_hash, sensitivity, retention_class
          FROM provenance_ledger_entities
        """,
    ):
        if str(candidate[1]) != project_id:
            return "integrity-review"
        entities_by_event.setdefault(str(candidate[0]), set()).add(tuple(candidate[2:]))
    relations_by_event: dict[str, set[tuple[Any, ...]]] = {}
    for candidate in connection.execute(
        """
        SELECT event_id, project_id, relation_id, relation_type, entity_id,
               entity_revision_id, related_entity_id, related_revision_id,
               activity_id, agent_id, occurred_at
          FROM provenance_ledger_relations
        """,
    ):
        if str(candidate[1]) != project_id:
            return "integrity-review"
        relations_by_event.setdefault(str(candidate[0]), set()).add(tuple(candidate[2:]))
    checkpoints: dict[str, tuple[str, str, str, int, str]] = {}
    for candidate in connection.execute(
        """
        SELECT checkpoint_id, event_id, project_id, segment_key, sequence, chain_sha256
          FROM provenance_ledger_checkpoints
        """
    ):
        event_id = str(candidate[1])
        if str(candidate[2]) != project_id or event_id in checkpoints:
            return "integrity-review"
        checkpoints[event_id] = (
            str(candidate[0]),
            str(candidate[2]),
            str(candidate[3]),
            int(candidate[4]),
            str(candidate[5]),
        )
    narrow_audits = {
        str(candidate[0]): tuple(candidate[1:])
        for candidate in connection.execute(
            """
            SELECT event_id, project_id, revision_id, event_type,
                   occurred_at, trace_id, actor_type, actor_id, record_sha256
             FROM provenance_events
             WHERE revision_id IS NOT NULL
               AND event_type LIKE 'org.research-observatory.%.v1'
            """
        )
    }
    outboxes = {
        str(candidate[0]): tuple(candidate[1:])
        for candidate in connection.execute(
            """
            SELECT outbox_id, project_id, revision_id, event_type, occurred_at,
                   available_at, idempotency_key, record_sha256
              FROM outbox_events
             WHERE revision_id IS NOT NULL
            """
        )
    }
    previous_by_segment: dict[str, str] = {}
    sequence_by_segment: dict[str, int] = {}
    for row in rows:
        try:
            decoded = decode_provenance_event(json.loads(str(row[4])))
            if decoded is None:
                return "integrity-review"
            record_json = canonical_provenance_json(decoded)
            record_sha256 = provenance_record_sha256(decoded)
            trace_id = str(decoded["traceparent"]).split("-")[1]
        except TypeError, ValueError, json.JSONDecodeError, IndexError:
            return "integrity-review"
        segment_key = str(row[2])
        if segment_key not in {_PROVENANCE_SEGMENT_V1, _PROVENANCE_SEGMENT_V2}:
            return "integrity-review"
        expected_sequence = sequence_by_segment.get(segment_key, 0) + 1
        previous = previous_by_segment.get(segment_key)
        data = cast(dict[str, Any], decoded["data"])
        activity = cast(dict[str, Any], data["activity"])
        agent = cast(dict[str, Any], data["agent"])
        actor_type = {"human": "human", "system": "system", "software": "worker", "model": "model"}.get(
            str(agent["agentType"])
        )
        if (
            str(row[0]) != decoded["id"]
            or str(row[1]) != project_id
            or str(row[1]) != decoded["projectid"]
            or tuple(row[9:])
            != (
                decoded["subject"],
                decoded["type"],
                decoded["time"],
                decoded["correlationid"],
                decoded["causationid"],
                activity["activityId"],
                activity["activityType"],
                activity["status"],
                decoded["actorid"],
                decoded["sensitivity"],
                decoded["retentionclass"],
            )
        ):
            return "integrity-review"
        inputs = cast(tuple[dict[str, Any], ...], data["inputs"])
        outputs = cast(tuple[dict[str, Any], ...], data["outputs"])
        primary_entity = (
            outputs[0]
            if len(outputs) == 1
            else inputs[0]
            if not outputs and activity["activityType"] == "invalidation" and inputs
            else None
        )
        if primary_entity is None or actor_type is None:
            return "integrity-review"
        narrow_audit = narrow_audits.get(str(row[0]))
        if narrow_audit != (
            project_id,
            primary_entity["revisionId"],
            decoded["type"],
            decoded["time"],
            trace_id,
            actor_type,
            decoded["actorid"],
            record_sha256.removeprefix("sha256:"),
        ):
            return "integrity-review"
        expected_entities = {
            (
                direction,
                entity["entityId"],
                entity["revisionId"],
                entity["entityKind"],
                entity["contentHash"],
                entity["sensitivity"],
                entity["retentionClass"],
            )
            for direction in ("input", "output")
            for entity in cast(tuple[dict[str, Any], ...], data[f"{direction}s"])
        }
        actual_entities = entities_by_event.get(str(row[0]), set())
        if actual_entities != expected_entities:
            return "integrity-review"
        expected_relations: set[tuple[Any, ...]] = set()
        for relation in cast(tuple[dict[str, Any], ...], data["relations"]):
            relation_entity = cast(dict[str, Any] | None, relation["entity"])
            related = cast(dict[str, Any] | None, relation["relatedEntity"])
            expected_relations.add(
                (
                    relation["relationId"],
                    relation["relationType"],
                    None if relation_entity is None else relation_entity["entityId"],
                    None if relation_entity is None else relation_entity["revisionId"],
                    None if related is None else related["entityId"],
                    None if related is None else related["revisionId"],
                    relation["activityId"],
                    relation["agentId"],
                    relation["occurredAt"],
                )
            )
        actual_relations = relations_by_event.get(str(row[0]), set())
        if actual_relations != expected_relations:
            return "integrity-review"
        checkpoint = checkpoints.get(str(row[0]))
        if checkpoint is None:
            return "integrity-review"
        outbox = outboxes.get(checkpoint[0])
        if outbox is None or (str(outbox[0]), str(outbox[1]), str(outbox[2]), str(outbox[3]), str(outbox[6])) != (
            project_id,
            str(primary_entity["revisionId"]),
            str(decoded["type"]),
            str(decoded["time"]),
            record_sha256.removeprefix("sha256:"),
        ):
            return "integrity-review"
        outbox_authority_sha256 = _outbox_authority_sha256(
            outbox_id=checkpoint[0],
            project_id=str(outbox[0]),
            revision_id=str(outbox[1]),
            event_type=str(outbox[2]),
            occurred_at=str(outbox[3]),
            available_at=str(outbox[4]),
            idempotency_key=str(outbox[5]),
            record_sha256=str(outbox[6]),
        )
        idempotency_sha256 = str(row[6])
        try:
            chain_sha256 = _provenance_chain_sha256(
                segment_key=segment_key,
                previous_chain_sha256=previous,
                record_sha256=record_sha256,
                idempotency_sha256=idempotency_sha256,
                outbox_authority_sha256=outbox_authority_sha256,
                sequence=expected_sequence,
            )
        except ValueError:
            return "integrity-review"
        if (
            int(row[3]) != expected_sequence
            or str(row[4]) != record_json
            or str(row[5]) != record_sha256
            or (None if row[7] is None else str(row[7])) != previous
            or str(row[8]) != chain_sha256
        ):
            return "integrity-review"
        if checkpoint != (checkpoint[0], project_id, segment_key, expected_sequence, chain_sha256):
            return "integrity-review"
        previous_by_segment[segment_key] = chain_sha256
        sequence_by_segment[segment_key] = expected_sequence
    event_ids = {str(row[0]) for row in rows}
    checkpoint_ids = {checkpoint[0] for checkpoint in checkpoints.values()}
    return (
        "verified"
        if (
            len(checkpoints) == len(rows)
            and set(checkpoints) == event_ids
            and set(outboxes) == checkpoint_ids
            and set(entities_by_event) == event_ids
            and set(relations_by_event) == event_ids
            and set(narrow_audits) == event_ids
        )
        else "integrity-review"
    )


class _SqliteProvenanceLedgerRepository(ProvenanceLedgerRepository):
    """Read-only bounded lineage adapter over canonical ledger projections."""

    def __init__(
        self,
        database: Path,
        project_id: str,
        *,
        absolute_scan_limit: int = 20_000,
        cursor_limit: int = 10_000,
    ) -> None:
        if (
            not database.is_absolute()
            or not project_id
            or isinstance(absolute_scan_limit, bool)
            or absolute_scan_limit < 1
            or isinstance(cursor_limit, bool)
            or cursor_limit < 1
        ):
            raise ValueError("provenance repository authority is invalid")
        self._database = database
        self._project_id = project_id
        self._absolute_scan_limit = absolute_scan_limit
        self._cursor_limit = cursor_limit

    def lineage(
        self,
        *,
        revision_id: str,
        direction: LineageDirection,
        cursor: int,
        page_size: int,
        max_depth: int,
    ) -> LineagePage:
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project_id)
            try:
                integrity_state = _ledger_integrity_state(connection, self._project_id)
                legacy_event_count = int(
                    connection.execute(
                        "SELECT count(*) FROM provenance_legacy_bridges WHERE project_id=?",
                        (self._project_id,),
                    ).fetchone()[0]
                )
                if legacy_event_count:
                    integrity_state = "integrity-review"
                frontier = [revision_id]
                queued = {revision_id}
                visited: set[str] = set()
                missing: set[str] = set()
                page: list[LineageNode] = []
                fact_count = 0
                rights_restricted = False
                truncation_reason: Literal["cursor-limit", "scan-limit"] | None = None
                depth = 0
                while frontier and len(visited) < self._absolute_scan_limit:
                    remaining_capacity = self._absolute_scan_limit - len(visited)
                    current_frontier = frontier[:remaining_capacity]
                    if len(current_frontier) != len(frontier):
                        truncation_reason = "scan-limit"
                    for current_revision in current_frontier:
                        queued.discard(current_revision)
                    visited.update(current_frontier)
                    next_frontier: list[str] = []
                    for chunk_start in range(0, len(current_frontier), 256):
                        chunk = current_frontier[chunk_start : chunk_start + 256]
                        placeholders = ",".join("?" for _ in chunk)
                        rows = connection.execute(
                            f"""
                            SELECT revision.revision_id, revision.rights_status,
                                   revision.knowledge_status, entity.direction,
                                   entity.entity_id, entity.entity_kind,
                                   event.event_id, event.event_type, event.activity_id,
                                   event.activity_type, event.activity_status, event.agent_id,
                                   event.occurred_at, event.record_json,
                                   relation.relation_id, relation.relation_type,
                                   relation.related_revision_id
                              FROM aggregate_revisions AS revision
                              LEFT JOIN provenance_ledger_entities AS entity
                                ON entity.project_id=revision.project_id
                               AND entity.revision_id=revision.revision_id
                              LEFT JOIN provenance_ledger_events AS event
                                ON event.event_id=entity.event_id
                               AND event.project_id=entity.project_id
                              LEFT JOIN provenance_ledger_relations AS relation
                                ON relation.project_id=entity.project_id
                               AND relation.event_id=entity.event_id
                               AND relation.entity_revision_id=entity.revision_id
                               AND relation.relation_type IN (
                                   'wasInvalidatedBy', 'wasDerivedFrom', 'wasGeneratedBy',
                                   'used', 'wasAttributedTo'
                               )
                             WHERE revision.project_id=?
                               AND revision.revision_id IN ({placeholders})
                             ORDER BY revision.revision_id, event.occurred_at, event.event_id,
                                      entity.direction DESC,
                                      CASE relation.relation_type
                                      WHEN 'wasInvalidatedBy' THEN 0
                                      WHEN 'wasDerivedFrom' THEN 1
                                      WHEN 'wasGeneratedBy' THEN 2
                                      WHEN 'used' THEN 3
                                      ELSE 4 END,
                                      relation.relation_id
                            """,
                            (self._project_id, *chunk),
                        ).fetchall()
                        rows_by_revision: dict[str, list[Any]] = {}
                        for row in rows:
                            rows_by_revision.setdefault(str(row[0]), []).append(row)
                        traversable: list[str] = []
                        decoded_events: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
                        for current_revision in chunk:
                            revision_rows = rows_by_revision.get(current_revision)
                            if not revision_rows:
                                missing.add(current_revision)
                                continue
                            rights_restricted = rights_restricted or str(revision_rows[0][1]) in {
                                "denied",
                                "unknown",
                            }
                            if revision_rows[0][6] is None:
                                missing.add(current_revision)
                                integrity_state = "integrity-review"
                                continue
                            traversable.append(current_revision)
                            for row in revision_rows:
                                if row[14] is None:
                                    integrity_state = "integrity-review"
                                    continue
                                event_id = str(row[6])
                                decoded_parts = decoded_events.get(event_id)
                                if decoded_parts is None:
                                    decoded = decode_provenance_event(json.loads(str(row[13])))
                                    if decoded is None:
                                        raise ValueError("lineage canonical provenance is invalid")
                                    data = cast(dict[str, Any], decoded["data"])
                                    activity = cast(dict[str, Any], data["activity"])
                                    configuration = cast(dict[str, Any], activity["configuration"])
                                    agent = cast(dict[str, Any], data["agent"])
                                    decoded_parts = (configuration, agent)
                                    decoded_events[event_id] = decoded_parts
                                configuration, agent = decoded_parts
                                if fact_count >= cursor and len(page) < page_size:
                                    page.append(
                                        LineageNode(
                                            fact_id=str(row[14]),
                                            relation_type=cast(Any, str(row[15])),
                                            entity_direction=cast(Any, str(row[3])),
                                            revision_id=current_revision,
                                            entity_id=str(row[4]),
                                            entity_kind=str(row[5]),
                                            related_revision_id=None if row[16] is None else str(row[16]),
                                            knowledge_status=cast(KnowledgeStatus, str(row[2])),
                                            rights_status=cast(RightsStatus, str(row[1])),
                                            depth=depth,
                                            event_id=event_id,
                                            event_type=str(row[7]),
                                            activity_id=str(row[8]),
                                            activity_type=str(row[9]),
                                            activity_status=cast(Any, str(row[10])),
                                            configuration_id=str(configuration["configurationId"]),
                                            configuration_version=str(configuration["configurationVersion"]),
                                            configuration_hash=str(configuration["configurationHash"]),
                                            agent_id=str(row[11]),
                                            agent_type=cast(Any, str(agent["agentType"])),
                                            agent_role=str(agent["role"]),
                                            occurred_at=str(row[12]),
                                        )
                                    )
                                fact_count += 1
                        if depth >= max_depth or not traversable:
                            continue
                        traversal_placeholders = ",".join("?" for _ in traversable)
                        if direction == "ancestors":
                            source_column = "entity_revision_id"
                            candidate_column = "related_revision_id"
                        else:
                            source_column = "related_revision_id"
                            candidate_column = "entity_revision_id"
                        traversal_rows = connection.execute(
                            f"""
                            SELECT {source_column}, {candidate_column}
                              FROM provenance_ledger_relations
                             WHERE project_id=? AND relation_type='wasDerivedFrom'
                               AND {source_column} IN ({traversal_placeholders})
                               AND {candidate_column} IS NOT NULL
                             ORDER BY {source_column}, occurred_at, relation_id
                            """,
                            (self._project_id, *traversable),
                        ).fetchall()
                        candidates_by_revision: dict[str, list[str]] = {}
                        for traversal_row in traversal_rows:
                            candidates_by_revision.setdefault(str(traversal_row[0]), []).append(str(traversal_row[1]))
                        for current_revision in traversable:
                            for candidate in candidates_by_revision.get(current_revision, []):
                                if candidate in visited or candidate in queued:
                                    continue
                                if len(visited) + len(next_frontier) >= self._absolute_scan_limit:
                                    truncation_reason = "scan-limit"
                                    continue
                                next_frontier.append(candidate)
                                queued.add(candidate)
                    frontier = next_frontier
                    depth += 1

                if frontier:
                    truncation_reason = "scan-limit"
                if missing:
                    integrity_state = "integrity-review"
                has_more = cursor + len(page) < fact_count
                candidate_cursor = cursor + len(page) if has_more and page else None
                if candidate_cursor is not None and candidate_cursor > self._cursor_limit:
                    truncation_reason = truncation_reason or "cursor-limit"
                    next_cursor = None
                else:
                    next_cursor = candidate_cursor
                if truncation_reason is not None:
                    integrity_state = "integrity-review"
                export_allowed = integrity_state == "verified" and not rights_restricted
                return LineagePage(
                    revision_id=revision_id,
                    direction=direction,
                    items=tuple(page),
                    missing_revision_ids=tuple(sorted(missing)),
                    next_cursor=next_cursor,
                    truncated=truncation_reason is not None,
                    truncation_reason=truncation_reason,
                    integrity_state=cast(Any, integrity_state),
                    legacy_event_count=legacy_event_count,
                    export_allowed=export_allowed,
                    export_denial_reason=(
                        "integrity-review"
                        if integrity_state != "verified"
                        else "rights-restricted"
                        if rights_restricted
                        else None
                    ),
                )
            finally:
                connection.close()
        except OSError, sqlite3.Error, StorageProblem, TypeError, ValueError:
            raise _repository_failure("provenance lineage query failed") from None


def sqlite_provenance_ledger_repository(path: Path, project_id: str) -> ProvenanceLedgerRepository:
    """Compose the canonical provenance repository for one authorized project."""

    return _SqliteProvenanceLedgerRepository(path / "state" / "project.sqlite3", project_id)


__all__ = [
    "create_sqlite_unit_of_work_factory",
    "sqlite_intent_revision_repository",
    "sqlite_privacy_policy_repository",
    "sqlite_provenance_ledger_repository",
]
