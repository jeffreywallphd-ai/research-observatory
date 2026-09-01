"""Private SQLAlchemy/SQLite adapter for the dependency-neutral repository ports."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
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
from .ports.workflow_executor import (
    ConcurrencyClass,
    WorkflowActor,
    WorkflowArtifactRecord,
    WorkflowArtifactRole,
    WorkflowCheckpointRecord,
    WorkflowCompletionReceipt,
    WorkflowHumanDisposition,
    WorkflowInterruptionKind,
    WorkflowJobAuthority,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowJobSubmission,
    WorkflowLeaseRejected,
    WorkflowOutputReference,
    WorkflowProgressRecord,
    WorkflowQueueConflict,
    WorkflowQueueCorrupt,
    WorkflowQueueNotFound,
    WorkflowQueueProblem,
    WorkflowQueueRepository,
    WorkflowTaskCenterEventRecord,
    WorkflowTaskCenterHumanTaskRecord,
    WorkflowTaskCenterJobRecord,
    WorkflowTaskCenterRunRecord,
    WorkflowTaskCenterStepRecord,
)
from .provenance import (
    canonical_aggregate_provenance_event,
    canonical_invalidation_provenance_event,
    canonical_workflow_completion_provenance_event,
)
from .provenance_contracts import canonical_provenance_json, decode_provenance_event, provenance_record_sha256
from .storage import MAX_SAFE_INTEGER, CanonicalConnection, StorageProblem, open_canonical_database
from .workflow_contracts import workflow_record_sha256, workflow_snapshot_errors

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


def _workflow_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _workflow_sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_workflow_json(value).encode("utf-8")).hexdigest()


def _workflow_time(value: str) -> datetime:
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise WorkflowQueueProblem("workflow timestamp is invalid") from error
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
        raise WorkflowQueueProblem("workflow timestamp is invalid")
    canonical = instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if canonical != value:
        raise WorkflowQueueProblem("workflow timestamp is invalid")
    return instant


def _workflow_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _workflow_uuid(at: str) -> str:
    return new_uuid_v7(timestamp_ms=int(_workflow_time(at).timestamp() * 1_000))


def _workflow_code(value: str) -> bool:
    letters = "abcdefghijklmnopqrstuvwxyz"
    characters = letters + "0123456789.-"
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 96
        and value[0] in letters
        and value[-1] in letters + "0123456789"
        and all(character in characters for character in value)
        and ".." not in value
        and "--" not in value
    )


def _workflow_actor(actor: WorkflowActor) -> None:
    if (
        not is_uuid_v7(actor.actor_id)
        or actor.actor_type not in {"human", "system", "workload"}
        or not _workflow_code(actor.role)
    ):
        raise WorkflowQueueProblem("workflow actor authority is invalid")


def _workflow_progress(progress: Mapping[str, object]) -> str:
    if set(progress) != {"kind", "unit", "completedUnits", "totalUnits"} or not _workflow_code(
        cast(str, progress.get("unit"))
    ):
        raise WorkflowQueueProblem("workflow progress is invalid")
    kind = progress.get("kind")
    completed = progress.get("completedUnits")
    total = progress.get("totalUnits")
    quantified = (
        kind == "quantified"
        and isinstance(completed, int)
        and not isinstance(completed, bool)
        and isinstance(total, int)
        and not isinstance(total, bool)
        and 0 <= completed <= total <= MAX_SAFE_INTEGER
    )
    unquantified = kind in {"unknown", "not-applicable"} and completed is None and total is None
    if not quantified and not unquantified:
        raise WorkflowQueueProblem("workflow progress is invalid")
    return _workflow_json(progress)


def _workflow_progress_record(value: object, *, unit: str = "items") -> WorkflowProgressRecord:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = None
    if isinstance(value, Mapping):
        try:
            _workflow_progress(cast(Mapping[str, object], value))
            return WorkflowProgressRecord(
                kind=cast(Any, value["kind"]),
                unit=str(value["unit"]),
                completed_units=cast(int | None, value["completedUnits"]),
                total_units=cast(int | None, value["totalUnits"]),
            )
        except KeyError, TypeError, WorkflowQueueProblem:
            pass
    return WorkflowProgressRecord("unknown", unit, None, None)


def _workflow_event(
    *,
    sequence: int,
    entity_type: str,
    entity_id: str,
    from_state: str | None,
    to_state: str,
    occurred_at: str,
    actor: WorkflowActor,
    reason_code: str,
    decision_id: str | None = None,
) -> dict[str, object]:
    return {
        "eventId": new_uuid_v7(timestamp_ms=int(_workflow_time(occurred_at).timestamp() * 1_000)),
        "sequence": sequence,
        "entityType": entity_type,
        "entityId": entity_id,
        "fromState": from_state,
        "toState": to_state,
        "occurredAt": occurred_at,
        "actor": {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role},
        "reasonCode": reason_code,
        "progress": None,
        "decisionId": decision_id,
        "checkpointId": None,
        "interruptionKind": None,
    }


class _SqliteWorkflowQueueRepository(WorkflowQueueRepository):
    """Short-transaction SQLite queue with opaque lease tokens and generation fences."""

    def __init__(self, database: Path, project_id: str) -> None:
        if not database.is_absolute() or not project_id:
            raise ValueError("workflow repository authority is invalid")
        self._database = database
        self._project_id = project_id

    def _open(self) -> CanonicalConnection:
        return open_canonical_database(self._database, expected_project_id=self._project_id)

    @contextmanager
    def _transaction(self) -> Iterator[CanonicalConnection]:
        connection: CanonicalConnection | None = None
        try:
            connection = self._open()
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except WorkflowQueueProblem:
            if connection is not None and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except (OSError, sqlite3.Error, StorageProblem, TypeError, ValueError) as error:
            if connection is not None and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise WorkflowQueueProblem("workflow persistence failed") from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _row(row: Any) -> WorkflowJobRecord:
        if row is None:
            raise WorkflowQueueNotFound("workflow job was not found")
        return WorkflowJobRecord(
            job_id=str(row[0]),
            workflow_run_id=str(row[1]),
            state=cast(Any, str(row[2])),
            concurrency_class=cast(Any, str(row[3])),
            priority=int(row[4]),
            available_at=str(row[5]),
            attempt_count=int(row[6]),
            max_attempts=int(row[7]),
            current_attempt_id=None if row[8] is None else str(row[8]),
            lease_generation=int(row[9]),
            cancellation_requested_at=None if row[10] is None else str(row[10]),
            interruption_kind=None if row[11] is None else cast(Any, str(row[11])),
            diagnostic_code=None if row[12] is None else str(row[12]),
            committed_output_sha256=None if row[13] is None else str(row[13]),
            updated_at=str(row[14]),
        )

    @staticmethod
    def _select_job(connection: CanonicalConnection, project_id: str, job_id: str) -> Any:
        return connection.execute(
            """
            SELECT job_id, workflow_run_id, state, concurrency_class, priority, available_at,
                   attempt_count, max_attempts, current_attempt_id, lease_generation,
                   cancellation_requested_at, interruption_kind, diagnostic_code,
                   committed_output_sha256, updated_at
              FROM workflow_queue_jobs WHERE project_id=? AND job_id=?
            """,
            (project_id, job_id),
        ).fetchone()

    @staticmethod
    def _append_history(
        connection: CanonicalConnection,
        *,
        project_id: str,
        workflow_run_id: str,
        job_id: str,
        attempt_id: str | None,
        entity_type: str,
        entity_id: str,
        from_state: str | None,
        to_state: str,
        occurred_at: str,
        actor: WorkflowActor,
        reason_code: str,
        extra: Mapping[str, object] | None = None,
    ) -> int:
        _workflow_actor(actor)
        if not _workflow_code(reason_code):
            raise WorkflowQueueProblem("workflow history reason is invalid")
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM workflow_history_events "
                "WHERE project_id=? AND workflow_run_id=?",
                (project_id, workflow_run_id),
            ).fetchone()[0]
        )
        event_id = _workflow_uuid(occurred_at)
        actor_value = {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role}
        event: dict[str, object] = {
            "eventId": event_id,
            "sequence": sequence,
            "entityType": entity_type,
            "entityId": entity_id,
            "fromState": from_state,
            "toState": to_state,
            "occurredAt": occurred_at,
            "actor": actor_value,
            "reasonCode": reason_code,
            "progress": None,
            "decisionId": None,
            "checkpointId": None,
            "interruptionKind": None,
        }
        if extra:
            event.update(extra)
        event_json = _workflow_json(event)
        connection.execute(
            """
            INSERT INTO workflow_history_events (
                event_id, project_id, workflow_run_id, job_id, attempt_id, sequence,
                entity_type, entity_id, from_state, to_state, occurred_at, actor_json,
                reason_code, event_json, record_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                project_id,
                workflow_run_id,
                job_id,
                attempt_id,
                sequence,
                entity_type,
                entity_id,
                from_state,
                to_state,
                occurred_at,
                _workflow_json(actor_value),
                reason_code,
                event_json,
                _workflow_sha256(event),
            ),
        )
        return sequence

    def _store_authority(
        self,
        connection: CanonicalConnection,
        *,
        definition: Mapping[str, object],
        snapshot: Mapping[str, object],
        definition_json: str,
        snapshot_json: str,
    ) -> None:
        definition_sha256 = workflow_record_sha256(definition)
        snapshot_sha256 = workflow_record_sha256(snapshot)
        definition_revision_id = str(definition["definitionRevisionId"])
        snapshot_id = str(snapshot["snapshotId"])
        snapshot_revision = int(cast(int, snapshot["snapshotRevision"]))
        existing_definition = connection.execute(
            "SELECT project_id, definition_json, record_sha256 FROM workflow_definitions "
            "WHERE definition_revision_id=?",
            (definition_revision_id,),
        ).fetchone()
        expected_definition = (self._project_id, definition_json, definition_sha256)
        if existing_definition is None:
            connection.execute(
                """
                INSERT INTO workflow_definitions (
                    definition_revision_id, project_id, workflow_definition_id,
                    definition_version, contract_version, content_hash, definition_json,
                    record_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition_revision_id,
                    self._project_id,
                    definition["workflowDefinitionId"],
                    definition["definitionVersion"],
                    definition["contractVersion"],
                    cast(Mapping[str, object], snapshot["definition"])["contentHash"],
                    definition_json,
                    definition_sha256,
                    definition["createdAt"],
                ),
            )
        elif tuple(existing_definition) != expected_definition:
            raise WorkflowQueueConflict("workflow definition authority differs")

        existing_snapshot = connection.execute(
            "SELECT project_id, workflow_run_id, definition_revision_id, snapshot_json, record_sha256 "
            "FROM workflow_authority_snapshots WHERE snapshot_id=? AND snapshot_revision=?",
            (snapshot_id, snapshot_revision),
        ).fetchone()
        expected_snapshot = (
            self._project_id,
            str(snapshot["workflowRunId"]),
            definition_revision_id,
            snapshot_json,
            snapshot_sha256,
        )
        if existing_snapshot is None:
            connection.execute(
                """
                INSERT INTO workflow_authority_snapshots (
                    snapshot_id, snapshot_revision, project_id, workflow_run_id,
                    definition_revision_id, state, history_sequence, snapshot_json,
                    record_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    snapshot_revision,
                    self._project_id,
                    snapshot["workflowRunId"],
                    definition_revision_id,
                    snapshot["state"],
                    snapshot["sequence"],
                    snapshot_json,
                    snapshot_sha256,
                    snapshot["createdAt"],
                    snapshot["updatedAt"],
                ),
            )
        elif tuple(existing_snapshot) != expected_snapshot:
            raise WorkflowQueueConflict("workflow snapshot authority differs")

        for event_value in cast(list[dict[str, object]], snapshot["history"]):
            event_json = _workflow_json(event_value)
            event_sha256 = _workflow_sha256(event_value)
            existing_event = connection.execute(
                "SELECT project_id, workflow_run_id, event_json, record_sha256 "
                "FROM workflow_history_events WHERE event_id=?",
                (event_value["eventId"],),
            ).fetchone()
            expected_event = (self._project_id, snapshot["workflowRunId"], event_json, event_sha256)
            if existing_event is not None:
                if tuple(existing_event) != expected_event:
                    raise WorkflowQueueConflict("workflow history authority differs")
                continue
            connection.execute(
                """
                INSERT INTO workflow_history_events (
                    event_id, project_id, workflow_run_id, job_id, attempt_id, sequence,
                    entity_type, entity_id, from_state, to_state, occurred_at, actor_json,
                    reason_code, event_json, record_sha256
                ) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_value["eventId"],
                    self._project_id,
                    snapshot["workflowRunId"],
                    event_value["sequence"],
                    event_value["entityType"],
                    event_value["entityId"],
                    event_value["fromState"],
                    event_value["toState"],
                    event_value["occurredAt"],
                    _workflow_json(event_value["actor"]),
                    event_value["reasonCode"],
                    event_json,
                    event_sha256,
                ),
            )

    def register_authority(
        self,
        *,
        definition_json: str,
        snapshot_json: str,
        actor: WorkflowActor,
    ) -> WorkflowTaskCenterRunRecord:
        _workflow_actor(actor)
        try:
            definition = cast(dict[str, object], json.loads(definition_json))
            snapshot = cast(dict[str, object], json.loads(snapshot_json))
        except (json.JSONDecodeError, TypeError) as error:
            raise WorkflowQueueCorrupt("workflow authority JSON is invalid") from error
        if (
            _workflow_json(definition) != definition_json
            or _workflow_json(snapshot) != snapshot_json
            or snapshot.get("projectId") != self._project_id
            or workflow_snapshot_errors(definition, snapshot)
        ):
            raise WorkflowQueueCorrupt("workflow authority is invalid")
        final_actor = cast(Mapping[str, object], cast(list[object], snapshot["history"])[-1])["actor"]
        expected_actor = {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role}
        if final_actor != expected_actor:
            raise WorkflowQueueConflict("workflow admission actor differs from snapshot authority")
        with self._transaction() as connection:
            self._store_authority(
                connection,
                definition=definition,
                snapshot=snapshot,
                definition_json=definition_json,
                snapshot_json=snapshot_json,
            )
        return self._task_center_run(str(snapshot["workflowRunId"]))

    def _task_center_run(
        self,
        workflow_run_id: str,
        connection: CanonicalConnection | None = None,
    ) -> WorkflowTaskCenterRunRecord:
        owned = connection is None
        active = self._open() if connection is None else connection
        try:
            authority = active.execute(
                """
                SELECT snapshot.snapshot_id, snapshot.snapshot_revision, snapshot.snapshot_json,
                       snapshot.updated_at, definition.definition_json,
                       snapshot.record_sha256, definition.record_sha256
                  FROM workflow_authority_snapshots AS snapshot
                  JOIN workflow_definitions AS definition
                    ON definition.definition_revision_id=snapshot.definition_revision_id
                 WHERE snapshot.project_id=? AND snapshot.workflow_run_id=?
                 ORDER BY snapshot.snapshot_revision DESC LIMIT 1
                """,
                (self._project_id, workflow_run_id),
            ).fetchone()
            if authority is None:
                raise WorkflowQueueNotFound("workflow run was not found")
            snapshot = cast(dict[str, object], json.loads(str(authority[2])))
            definition = cast(dict[str, object], json.loads(str(authority[4])))
            if (
                _workflow_sha256(snapshot) != str(authority[5])
                or _workflow_sha256(definition) != str(authority[6])
                or workflow_snapshot_errors(definition, snapshot)
            ):
                raise WorkflowQueueCorrupt("workflow task-center authority digest differs")
            definition_steps = {
                str(cast(Mapping[str, object], item)["stepKey"]): cast(Mapping[str, object], item)
                for item in cast(list[object], definition["steps"])
            }
            job_rows = active.execute(
                """
                SELECT job.job_id, job.state, job.activity_type, job.concurrency_class,
                       job.priority, job.attempt_count, job.max_attempts, job.current_attempt_id,
                       attempt.worker_id, attempt.progress_json, job.progress_unit,
                       job.progress_total_kind, job.progress_total_units, job.diagnostic_code,
                       job.updated_at, job.interruption_kind, job.step_run_id
                  FROM workflow_queue_jobs AS job
                  LEFT JOIN workflow_job_attempts AS attempt
                    ON attempt.attempt_id=job.current_attempt_id
                 WHERE job.project_id=? AND job.workflow_run_id=?
                 ORDER BY job.created_at, job.job_id
                """,
                (self._project_id, workflow_run_id),
            ).fetchall()
            jobs: list[WorkflowTaskCenterJobRecord] = []
            job_states_by_step: dict[str, str] = {}
            interruption_kind: WorkflowInterruptionKind | None = None
            for row in job_rows:
                if row[9] is None:
                    fallback = (
                        {"kind": "quantified", "unit": str(row[10]), "completedUnits": 0, "totalUnits": int(row[12])}
                        if str(row[11]) == "known"
                        else {"kind": str(row[11]), "unit": str(row[10]), "completedUnits": None, "totalUnits": None}
                    )
                    progress = _workflow_progress_record(fallback, unit=str(row[10]))
                else:
                    progress = _workflow_progress_record(row[9], unit=str(row[10]))
                checkpoint = active.execute(
                    "SELECT checkpoint_id, created_at FROM workflow_checkpoints "
                    "WHERE project_id=? AND job_id=? ORDER BY history_sequence DESC LIMIT 1",
                    (self._project_id, row[0]),
                ).fetchone()
                state = cast(Any, str(row[1]))
                jobs.append(
                    WorkflowTaskCenterJobRecord(
                        job_id=str(row[0]),
                        state=state,
                        activity_type=str(row[2]),
                        resource_pool=cast(Any, str(row[3])),
                        priority=int(row[4]),
                        attempt_count=int(row[5]),
                        max_attempts=int(row[6]),
                        current_attempt_id=None if row[7] is None else str(row[7]),
                        worker_id=None if row[8] is None else str(row[8]),
                        progress=progress,
                        latest_checkpoint_id=None if checkpoint is None else str(checkpoint[0]),
                        latest_checkpoint_at=None if checkpoint is None else str(checkpoint[1]),
                        diagnostic_code=None if row[13] is None else str(row[13]),
                        updated_at=str(row[14]),
                    )
                )
                job_states_by_step[str(row[16])] = state
                if row[15] is not None:
                    interruption_kind = cast(WorkflowInterruptionKind, str(row[15]))

            steps: list[WorkflowTaskCenterStepRecord] = []
            for value in cast(list[object], snapshot["stepRuns"]):
                step = cast(Mapping[str, object], value)
                definition_step = definition_steps[str(step["stepKey"])]
                queue_state = job_states_by_step.get(str(step["stepRunId"]))
                displayed_state = str(step["state"])
                if queue_state in {"claimed", "running", "cancelling", "cancelled", "failed", "succeeded"}:
                    displayed_state = "running" if queue_state == "claimed" else queue_state
                steps.append(
                    WorkflowTaskCenterStepRecord(
                        step_run_id=str(step["stepRunId"]),
                        step_key=str(step["stepKey"]),
                        kind=cast(Any, str(definition_step["kind"])),
                        state=displayed_state,
                        depends_on=tuple(map(str, cast(list[object], definition_step["dependsOn"]))),
                    )
                )

            human_tasks: list[WorkflowTaskCenterHumanTaskRecord] = []
            for value in cast(list[object], snapshot["humanTasks"]):
                task = cast(Mapping[str, object], value)
                step_record = next(item for item in steps if item.step_run_id == task["stepRunId"])
                definition_task = cast(Mapping[str, object], definition_steps[step_record.step_key]["humanTask"])
                allowed_dispositions = cast(list[WorkflowHumanDisposition], definition_task["allowedDispositions"])
                consequences = cast(Mapping[str, object], definition_task["consequencesByDisposition"])
                decision = cast(Mapping[str, object] | None, task["decision"])
                assigned = cast(Mapping[str, object] | None, task["assignedTo"])
                human_tasks.append(
                    WorkflowTaskCenterHumanTaskRecord(
                        human_task_id=str(task["humanTaskId"]),
                        step_run_id=str(task["stepRunId"]),
                        state=cast(Any, str(task["state"])),
                        required_role=str(task["requiredRole"]),
                        assigned_actor_id=None if assigned is None else str(assigned["actorId"]),
                        requested_at=str(task["requestedAt"]),
                        evidence_artifact_ids=tuple(map(str, cast(list[object], task["evidenceArtifactIds"]))),
                        allowed_dispositions=tuple(allowed_dispositions),
                        consequences_by_disposition=tuple(
                            (disposition, str(consequences[disposition])) for disposition in allowed_dispositions
                        ),
                        decision_id=None if decision is None else str(decision["decisionId"]),
                        disposition=None if decision is None else cast(Any, str(decision["disposition"])),
                        decided_at=None if decision is None else str(decision["decidedAt"]),
                    )
                )

            event_rows = active.execute(
                """
                SELECT sequence, entity_type, entity_id, to_state, occurred_at, reason_code
                  FROM workflow_history_events
                 WHERE project_id=? AND workflow_run_id=?
                 ORDER BY sequence DESC LIMIT 25
                """,
                (self._project_id, workflow_run_id),
            ).fetchall()
            events = tuple(
                WorkflowTaskCenterEventRecord(
                    int(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]), str(row[5])
                )
                for row in reversed(event_rows)
            )
            revision = int(
                active.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM workflow_history_events "
                    "WHERE project_id=? AND workflow_run_id=?",
                    (self._project_id, workflow_run_id),
                ).fetchone()[0]
            )
            artifact_rows = active.execute(
                """
                SELECT DISTINCT artifact.disposition
                  FROM workflow_attempt_artifacts AS artifact
                  JOIN workflow_queue_jobs AS job ON job.job_id=artifact.job_id
                 WHERE artifact.project_id=? AND job.workflow_run_id=?
                   AND artifact.disposition<>'committed'
                 ORDER BY artifact.disposition
                """,
                (self._project_id, workflow_run_id),
            ).fetchall()
            retained = cast(Any, tuple(str(row[0]) for row in artifact_rows))
            active_compute = any(job.state in {"claimed", "running", "cancelling"} for job in jobs)
            pending_human = any(task.state in {"requested", "claimed"} for task in human_tasks)
            if active_compute:
                display_state = "cancelling" if any(job.state == "cancelling" for job in jobs) else "running"
            elif pending_human:
                display_state = "waiting-human"
            elif any(job.state in {"runnable", "retry-scheduled"} for job in jobs):
                display_state = "queued"
            elif any(job.state == "failed" for job in jobs):
                display_state = "failed"
            elif jobs and all(job.state == "cancelled" for job in jobs):
                display_state = "cancelled"
            else:
                display_state = str(snapshot["state"])
                if display_state == "accepted":
                    display_state = "queued"
            run_progress = jobs[0].progress if len(jobs) == 1 else _workflow_progress_record(snapshot["progress"])
            updated_at = max([str(authority[3]), *(job.updated_at for job in jobs)])
            return WorkflowTaskCenterRunRecord(
                workflow_run_id=workflow_run_id,
                workflow_key=str(definition["workflowKey"]),
                definition_revision_id=str(definition["definitionRevisionId"]),
                definition_version=str(definition["definitionVersion"]),
                snapshot_id=str(authority[0]),
                snapshot_revision=int(authority[1]),
                state=cast(Any, display_state),
                active_compute=active_compute,
                progress=run_progress,
                revision=revision,
                interruption_kind=interruption_kind,
                updated_at=updated_at,
                steps=tuple(steps),
                jobs=tuple(jobs),
                human_tasks=tuple(human_tasks),
                retained_artifacts=retained,
                events=events,
            )
        except WorkflowQueueProblem:
            raise
        except (
            KeyError,
            StopIteration,
            json.JSONDecodeError,
            sqlite3.Error,
            StorageProblem,
            TypeError,
            ValueError,
        ) as error:
            raise WorkflowQueueCorrupt("workflow task-center projection is invalid") from error
        finally:
            if owned:
                active.close()

    def task_center(self, *, limit: int = 100) -> tuple[WorkflowTaskCenterRunRecord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise WorkflowQueueProblem("workflow task-center limit is invalid")
        connection: CanonicalConnection | None = None
        try:
            connection = self._open()
            rows = connection.execute(
                """
                SELECT workflow_run_id, MAX(updated_at) AS latest
                  FROM workflow_authority_snapshots
                 WHERE project_id=?
                 GROUP BY workflow_run_id
                 ORDER BY latest DESC, workflow_run_id
                 LIMIT ?
                """,
                (self._project_id, limit),
            ).fetchall()
            return tuple(self._task_center_run(str(row[0]), connection) for row in rows)
        except WorkflowQueueProblem:
            raise
        except (OSError, sqlite3.Error, StorageProblem) as error:
            raise WorkflowQueueProblem("workflow task-center read failed") from error
        finally:
            if connection is not None:
                connection.close()

    def enqueue(self, submission: WorkflowJobSubmission, *, actor: WorkflowActor) -> WorkflowJobRecord:
        if submission.project_id != self._project_id:
            raise WorkflowQueueConflict("workflow project authority differs")
        _workflow_actor(actor)
        definition = json.loads(submission.definition_json)
        snapshot = json.loads(submission.snapshot_json)
        if (
            _workflow_json(definition) != submission.definition_json
            or _workflow_json(snapshot) != submission.snapshot_json
            or _workflow_sha256(definition) != submission.definition_record_sha256
            or _workflow_sha256(snapshot) != submission.snapshot_record_sha256
            or snapshot.get("projectId") != self._project_id
            or workflow_snapshot_errors(definition, snapshot)
        ):
            raise WorkflowQueueCorrupt("workflow authority digest differs")
        final_actor = snapshot["history"][-1]["actor"]
        if final_actor != {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role}:
            raise WorkflowQueueConflict("workflow admission actor differs from snapshot authority")
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT job_id, command_fingerprint FROM workflow_queue_jobs WHERE project_id=? AND idempotency_key=?",
                (self._project_id, submission.idempotency_key),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != submission.job_id or str(existing[1]) != submission.command_fingerprint:
                    raise WorkflowQueueConflict("workflow idempotency authority differs")
                return self._row(self._select_job(connection, self._project_id, submission.job_id))

            self._store_authority(
                connection,
                definition=definition,
                snapshot=snapshot,
                definition_json=submission.definition_json,
                snapshot_json=submission.snapshot_json,
            )

            connection.execute(
                """
                INSERT INTO workflow_queue_jobs (
                    job_id, project_id, workflow_run_id, snapshot_id, snapshot_revision,
                    step_run_id, activity_type, concurrency_class, progress_unit,
                    progress_total_kind, progress_total_units, checkpoint_mode,
                    partial_artifact_disposition, state, priority,
                    available_at, max_attempts, initial_backoff_ms, maximum_backoff_ms,
                    multiplier_basis_points, deterministic_jitter, retryable_error_codes_json,
                    non_retryable_error_codes_json, idempotency_key, command_fingerprint,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'runnable', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission.job_id,
                    self._project_id,
                    submission.workflow_run_id,
                    submission.snapshot_id,
                    submission.snapshot_revision,
                    submission.step_run_id,
                    submission.activity_type,
                    submission.concurrency_class,
                    submission.progress_unit,
                    submission.progress_total_kind,
                    submission.progress_total_units,
                    submission.checkpoint_mode,
                    submission.partial_artifact_disposition,
                    submission.priority,
                    submission.available_at,
                    submission.max_attempts,
                    submission.initial_backoff_ms,
                    submission.maximum_backoff_ms,
                    submission.multiplier_basis_points,
                    int(submission.deterministic_jitter),
                    _workflow_json(submission.retryable_error_codes),
                    _workflow_json(submission.non_retryable_error_codes),
                    submission.idempotency_key,
                    submission.command_fingerprint,
                    snapshot["createdAt"],
                    snapshot["updatedAt"],
                ),
            )
            return self._row(self._select_job(connection, self._project_id, submission.job_id))

    def get(self, job_id: str) -> WorkflowJobRecord:
        try:
            connection = self._open()
            try:
                return self._row(self._select_job(connection, self._project_id, job_id))
            finally:
                connection.close()
        except WorkflowQueueProblem:
            raise
        except (OSError, sqlite3.Error, StorageProblem) as error:
            raise WorkflowQueueProblem("workflow read failed") from error

    def authority(self, job_id: str) -> WorkflowJobAuthority:
        try:
            connection = self._open()
            try:
                row = connection.execute(
                    """
                    SELECT definition.definition_json, snapshot.snapshot_json,
                           definition.record_sha256, snapshot.record_sha256
                      FROM workflow_queue_jobs AS job
                      JOIN workflow_authority_snapshots AS snapshot
                        ON snapshot.snapshot_id=job.snapshot_id
                       AND snapshot.snapshot_revision=job.snapshot_revision
                      JOIN workflow_definitions AS definition
                        ON definition.definition_revision_id=snapshot.definition_revision_id
                     WHERE job.project_id=? AND job.job_id=?
                    """,
                    (self._project_id, job_id),
                ).fetchone()
                if row is None:
                    raise WorkflowQueueNotFound("workflow job was not found")
                authority = WorkflowJobAuthority(*map(str, row))
                if (
                    _workflow_sha256(json.loads(authority.definition_json)) != authority.definition_record_sha256
                    or _workflow_sha256(json.loads(authority.snapshot_json)) != authority.snapshot_record_sha256
                ):
                    raise WorkflowQueueCorrupt("workflow authority digest differs")
                return authority
            finally:
                connection.close()
        except WorkflowQueueProblem:
            raise
        except (OSError, sqlite3.Error, StorageProblem, ValueError) as error:
            raise WorkflowQueueProblem("workflow authority read failed") from error

    @staticmethod
    def _latest_checkpoint(connection: CanonicalConnection, job_id: str) -> WorkflowCheckpointRecord | None:
        row = connection.execute(
            """
            SELECT checkpoint.checkpoint_id, checkpoint.attempt_id,
                   checkpoint.checkpoint_sequence, checkpoint.history_sequence,
                   checkpoint.created_at, checkpoint.state_hash, checkpoint.payload_artifact_id,
                   artifact.attempt_id, artifact.job_id, artifact.artifact_id,
                   artifact.revision_id, artifact.role, artifact.disposition,
                   artifact.content_hash, artifact.media_type, artifact.provenance_entity_id
              FROM workflow_checkpoints AS checkpoint
              JOIN workflow_attempt_artifacts AS artifact
                ON artifact.attempt_id=checkpoint.attempt_id
               AND artifact.artifact_id=checkpoint.payload_artifact_id
             WHERE checkpoint.job_id=?
             ORDER BY checkpoint.history_sequence DESC LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        return (
            None
            if row is None
            else WorkflowCheckpointRecord(
                checkpoint_id=str(row[0]),
                attempt_id=str(row[1]),
                checkpoint_sequence=int(row[2]),
                history_sequence=int(row[3]),
                created_at=str(row[4]),
                state_hash=str(row[5]),
                payload_artifact_id=str(row[6]),
                payload=_SqliteWorkflowQueueRepository._artifact_row(row[7:]),
            )
        )

    def claim_next(
        self,
        *,
        worker_id: str,
        concurrency_classes: tuple[ConcurrencyClass, ...],
        now: str,
        lease_duration_ms: int,
    ) -> WorkflowJobClaim | None:
        instant = _workflow_time(now)
        if (
            not is_uuid_v7(worker_id)
            or not concurrency_classes
            or any(item not in {"interactive", "document", "ai", "maintenance"} for item in concurrency_classes)
            or not 1_000 <= lease_duration_ms <= 3_600_000
        ):
            raise WorkflowQueueProblem("workflow claim authority is invalid")
        expires_at = _workflow_timestamp(instant + timedelta(milliseconds=lease_duration_ms))
        placeholders = ",".join("?" for _ in concurrency_classes)
        with self._transaction() as connection:
            candidate = connection.execute(
                f"""
                SELECT job_id, workflow_run_id, step_run_id, activity_type, concurrency_class,
                       attempt_count, lease_generation, idempotency_key, command_fingerprint, state,
                       progress_unit, progress_total_kind, progress_total_units
                 FROM workflow_queue_jobs
                 WHERE project_id=? AND state IN ('runnable', 'retry-scheduled')
                   AND attempt_count<max_attempts AND available_at<=?
                   AND concurrency_class IN ({placeholders})
                 ORDER BY priority DESC, available_at, job_id LIMIT 1
                """,
                (self._project_id, now, *concurrency_classes),
            ).fetchone()
            if candidate is None:
                return None
            job_id = str(candidate[0])
            worker = WorkflowActor(worker_id, "workload", "local-workflow-worker")
            if str(candidate[9]) == "retry-scheduled":
                changed = connection.execute(
                    "UPDATE workflow_queue_jobs SET state='runnable', updated_at=? "
                    "WHERE project_id=? AND job_id=? AND state='retry-scheduled' AND available_at<=?",
                    (now, self._project_id, job_id, now),
                ).rowcount
                if changed != 1:
                    return None
                self._append_history(
                    connection,
                    project_id=self._project_id,
                    workflow_run_id=str(candidate[1]),
                    job_id=job_id,
                    attempt_id=None,
                    entity_type="job",
                    entity_id=job_id,
                    from_state="retry-scheduled",
                    to_state="runnable",
                    occurred_at=now,
                    actor=worker,
                    reason_code="retry-due",
                )
            attempt_number = int(candidate[5]) + 1
            lease_generation = int(candidate[6]) + 1
            attempt_id = _workflow_uuid(now)
            lease_token = secrets.token_urlsafe(32)
            lease_digest = hashlib.sha256(lease_token.encode("ascii")).hexdigest()
            changed = connection.execute(
                """
                UPDATE workflow_queue_jobs
                   SET state='claimed', attempt_count=?, current_attempt_id=?, lease_generation=?,
                       lease_owner=?, lease_token_sha256=?, lease_expires_at=?, heartbeat_at=?,
                       diagnostic_code=NULL, updated_at=?
                 WHERE project_id=? AND job_id=? AND state='runnable'
                   AND attempt_count=? AND lease_generation=?
                """,
                (
                    attempt_number,
                    attempt_id,
                    lease_generation,
                    worker_id,
                    lease_digest,
                    expires_at,
                    now,
                    now,
                    self._project_id,
                    job_id,
                    candidate[5],
                    candidate[6],
                ),
            ).rowcount
            if changed != 1:
                return None
            initial_progress = {
                "kind": "quantified" if str(candidate[11]) == "known" else str(candidate[11]),
                "unit": str(candidate[10]),
                "completedUnits": 0 if str(candidate[11]) == "known" else None,
                "totalUnits": None if candidate[12] is None else int(candidate[12]),
            }
            connection.execute(
                """
                    INSERT INTO workflow_job_attempts (
                        attempt_id, project_id, job_id, attempt_number, state, worker_id,
                        lease_generation, lease_token_sha256, lease_expires_at, heartbeat_at,
                        progress_json
                    ) VALUES (?, ?, ?, ?, 'claimed', ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    self._project_id,
                    job_id,
                    attempt_number,
                    worker_id,
                    lease_generation,
                    lease_digest,
                    expires_at,
                    now,
                    _workflow_json(initial_progress),
                ),
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(candidate[1]),
                job_id=job_id,
                attempt_id=attempt_id,
                entity_type="job",
                entity_id=job_id,
                from_state="runnable",
                to_state="claimed",
                occurred_at=now,
                actor=worker,
                reason_code="worker-claimed",
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(candidate[1]),
                job_id=job_id,
                attempt_id=attempt_id,
                entity_type="job-attempt",
                entity_id=attempt_id,
                from_state=None,
                to_state="claimed",
                occurred_at=now,
                actor=worker,
                reason_code="attempt-created",
                extra={"progress": initial_progress},
            )
            return WorkflowJobClaim(
                project_id=self._project_id,
                workflow_run_id=str(candidate[1]),
                job_id=job_id,
                step_run_id=str(candidate[2]),
                activity_type=str(candidate[3]),
                concurrency_class=cast(Any, str(candidate[4])),
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_generation=lease_generation,
                lease_expires_at=expires_at,
                idempotency_key=str(candidate[7]),
                command_fingerprint=str(candidate[8]),
                latest_checkpoint=self._latest_checkpoint(connection, job_id),
            )

    def _lease_row(
        self,
        connection: CanonicalConnection,
        claim: WorkflowJobClaim,
        now: str,
        *,
        states: tuple[str, ...],
    ) -> Any:
        if claim.project_id != self._project_id:
            raise WorkflowLeaseRejected("workflow lease project differs")
        try:
            digest = hashlib.sha256(claim.lease_token.encode("ascii")).hexdigest()
        except UnicodeEncodeError as error:
            raise WorkflowLeaseRejected("workflow lease capability is invalid") from error
        row = connection.execute(
            """
            SELECT job.workflow_run_id, job.state, job.lease_expires_at, job.cancellation_requested_at,
                   attempt.state, attempt.progress_json, job.progress_unit,
                   job.progress_total_kind, job.progress_total_units, job.checkpoint_mode,
                   job.partial_artifact_disposition
              FROM workflow_queue_jobs AS job
              JOIN workflow_job_attempts AS attempt ON attempt.attempt_id=job.current_attempt_id
             WHERE job.project_id=? AND job.job_id=? AND job.current_attempt_id=?
               AND job.lease_owner=? AND job.lease_generation=? AND job.lease_token_sha256=?
               AND attempt.worker_id=? AND attempt.lease_generation=? AND attempt.lease_token_sha256=?
            """,
            (
                self._project_id,
                claim.job_id,
                claim.attempt_id,
                claim.worker_id,
                claim.lease_generation,
                digest,
                claim.worker_id,
                claim.lease_generation,
                digest,
            ),
        ).fetchone()
        if row is None or str(row[1]) not in states or str(row[2]) <= now:
            raise WorkflowLeaseRejected("workflow lease is stale or expired")
        return row

    @staticmethod
    def _validated_attempt_progress(row: Any, progress: Mapping[str, object]) -> tuple[str, dict[str, object]]:
        progress_json = _workflow_progress(progress)
        parsed = cast(dict[str, object], json.loads(progress_json))
        expected_kind = "quantified" if str(row[7]) == "known" else str(row[7])
        if parsed["unit"] != str(row[6]) or parsed["kind"] != expected_kind or parsed["totalUnits"] != row[8]:
            raise WorkflowQueueConflict("workflow progress authority differs")
        prior = cast(dict[str, object], json.loads(str(row[5])))
        if expected_kind == "quantified" and int(cast(int, parsed["completedUnits"])) < int(
            cast(int, prior["completedUnits"])
        ):
            raise WorkflowQueueConflict("workflow progress cannot regress")
        return progress_json, parsed

    def _verify_attempt_capability(self, connection: CanonicalConnection, claim: WorkflowJobClaim) -> None:
        """Verify an immutable claimant tuple without requiring an active job lease."""

        if claim.project_id != self._project_id:
            raise WorkflowLeaseRejected("workflow lease project differs")
        try:
            digest = hashlib.sha256(claim.lease_token.encode("ascii")).hexdigest()
        except UnicodeEncodeError as error:
            raise WorkflowLeaseRejected("workflow lease capability is invalid") from error
        row = connection.execute(
            """
            SELECT job.workflow_run_id, job.step_run_id, job.activity_type,
                   job.concurrency_class, job.idempotency_key, job.command_fingerprint,
                   attempt.attempt_number
              FROM workflow_job_attempts AS attempt
              JOIN workflow_queue_jobs AS job
                ON job.project_id=attempt.project_id AND job.job_id=attempt.job_id
             WHERE attempt.project_id=? AND attempt.job_id=? AND attempt.attempt_id=?
               AND attempt.worker_id=? AND attempt.lease_generation=?
               AND attempt.lease_token_sha256=?
            """,
            (
                self._project_id,
                claim.job_id,
                claim.attempt_id,
                claim.worker_id,
                claim.lease_generation,
                digest,
            ),
        ).fetchone()
        if row is None or tuple(row) != (
            claim.workflow_run_id,
            claim.step_run_id,
            claim.activity_type,
            claim.concurrency_class,
            claim.idempotency_key,
            claim.command_fingerprint,
            claim.attempt_number,
        ):
            raise WorkflowLeaseRejected("workflow attempt capability differs")

    def start(self, claim: WorkflowJobClaim, *, now: str) -> WorkflowJobRecord:
        _workflow_time(now)
        with self._transaction() as connection:
            row = self._lease_row(connection, claim, now, states=("claimed",))
            connection.execute(
                "UPDATE workflow_queue_jobs SET state='running', updated_at=? WHERE job_id=?",
                (now, claim.job_id),
            )
            connection.execute(
                "UPDATE workflow_job_attempts SET state='running', started_at=? WHERE attempt_id=?",
                (now, claim.attempt_id),
            )
            actor = WorkflowActor(claim.worker_id, "workload", "local-workflow-worker")
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(row[0]),
                job_id=claim.job_id,
                attempt_id=claim.attempt_id,
                entity_type="job",
                entity_id=claim.job_id,
                from_state="claimed",
                to_state="running",
                occurred_at=now,
                actor=actor,
                reason_code="worker-started",
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(row[0]),
                job_id=claim.job_id,
                attempt_id=claim.attempt_id,
                entity_type="job-attempt",
                entity_id=claim.attempt_id,
                from_state="claimed",
                to_state="running",
                occurred_at=now,
                actor=actor,
                reason_code="attempt-started",
                extra={"progress": cast(dict[str, object], json.loads(str(row[5])))},
            )
            return self._row(self._select_job(connection, self._project_id, claim.job_id))

    def heartbeat(
        self,
        claim: WorkflowJobClaim,
        *,
        now: str,
        lease_duration_ms: int,
        progress: Mapping[str, object],
    ) -> WorkflowJobClaim:
        instant = _workflow_time(now)
        if not 1_000 <= lease_duration_ms <= 3_600_000:
            raise WorkflowQueueProblem("workflow heartbeat duration is invalid")
        expires_at = _workflow_timestamp(instant + timedelta(milliseconds=lease_duration_ms))
        with self._transaction() as connection:
            row = self._lease_row(connection, claim, now, states=("running", "cancelling"))
            progress_json, validated_progress = self._validated_attempt_progress(row, progress)
            connection.execute(
                "UPDATE workflow_queue_jobs SET lease_expires_at=?, heartbeat_at=?, updated_at=? WHERE job_id=?",
                (expires_at, now, now, claim.job_id),
            )
            connection.execute(
                "UPDATE workflow_job_attempts SET lease_expires_at=?, heartbeat_at=?, progress_json=? "
                "WHERE attempt_id=?",
                (expires_at, now, progress_json, claim.attempt_id),
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(row[0]),
                job_id=claim.job_id,
                attempt_id=claim.attempt_id,
                entity_type="job-attempt",
                entity_id=claim.attempt_id,
                from_state=str(row[4]),
                to_state=str(row[4]),
                occurred_at=now,
                actor=WorkflowActor(claim.worker_id, "workload", "local-workflow-worker"),
                reason_code="progress-reported",
                extra={"progress": validated_progress},
            )
        return replace(claim, lease_expires_at=expires_at)

    def checkpoint(
        self,
        claim: WorkflowJobClaim,
        *,
        checkpoint_id: str,
        state_hash: str,
        payload_artifact_id: str,
        now: str,
        progress: Mapping[str, object],
    ) -> WorkflowCheckpointRecord:
        _workflow_time(now)
        if not is_uuid_v7(checkpoint_id) or not is_uuid_v7(payload_artifact_id):
            raise WorkflowQueueProblem("workflow checkpoint identity is invalid")
        if (
            len(state_hash) != 71
            or not state_hash.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in state_hash[7:])
        ):
            raise WorkflowQueueProblem("workflow checkpoint digest is invalid")
        with self._transaction() as connection:
            row = self._lease_row(connection, claim, now, states=("running", "cancelling"))
            if str(row[9]) == "forbidden":
                raise WorkflowQueueConflict("workflow checkpoint policy forbids checkpoints")
            progress_json, validated_progress = self._validated_attempt_progress(row, progress)
            artifact = connection.execute(
                """
                SELECT attempt_id, job_id, artifact_id, revision_id, role, disposition,
                       content_hash, media_type, provenance_entity_id
                  FROM workflow_attempt_artifacts
                 WHERE project_id=? AND job_id=? AND attempt_id=? AND artifact_id=?
                """,
                (self._project_id, claim.job_id, claim.attempt_id, payload_artifact_id),
            ).fetchone()
            if artifact is None or tuple(map(str, artifact[4:7])) != (
                "checkpoint",
                "retained-incomplete",
                state_hash,
            ):
                raise WorkflowQueueConflict("workflow checkpoint artifact authority differs")
            payload = replace(self._artifact_row(artifact), disposition="committed")
            connection.execute(
                "UPDATE workflow_attempt_artifacts SET disposition='committed', updated_at=? "
                "WHERE attempt_id=? AND artifact_id=?",
                (now, claim.attempt_id, payload_artifact_id),
            )
            checkpoint_sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(checkpoint_sequence), 0) + 1 FROM workflow_checkpoints WHERE attempt_id=?",
                    (claim.attempt_id,),
                ).fetchone()[0]
            )
            history_sequence = self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(row[0]),
                job_id=claim.job_id,
                attempt_id=claim.attempt_id,
                entity_type="job-attempt",
                entity_id=claim.attempt_id,
                from_state=str(row[4]),
                to_state=str(row[4]),
                occurred_at=now,
                actor=WorkflowActor(claim.worker_id, "workload", "local-workflow-worker"),
                reason_code="checkpoint-recorded",
                extra={"checkpointId": checkpoint_id, "progress": validated_progress},
            )
            connection.execute(
                """
                INSERT INTO workflow_checkpoints (
                    checkpoint_id, project_id, job_id, attempt_id, checkpoint_sequence,
                    history_sequence, created_at, state_hash, payload_artifact_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    self._project_id,
                    claim.job_id,
                    claim.attempt_id,
                    checkpoint_sequence,
                    history_sequence,
                    now,
                    state_hash,
                    payload_artifact_id,
                ),
            )
            connection.execute(
                "UPDATE workflow_job_attempts SET progress_json=? WHERE attempt_id=?",
                (progress_json, claim.attempt_id),
            )
            return WorkflowCheckpointRecord(
                checkpoint_id,
                claim.attempt_id,
                checkpoint_sequence,
                history_sequence,
                now,
                state_hash,
                payload_artifact_id,
                payload,
            )

    def request_cancellation(
        self,
        job_id: str,
        *,
        actor: WorkflowActor,
        now: str,
        reason_code: str,
        interruption_kind: WorkflowInterruptionKind,
        expected_history_sequence: int | None = None,
    ) -> WorkflowJobRecord:
        _workflow_time(now)
        if interruption_kind not in {"user-cancel", "security-lock", "policy", "dependency"}:
            raise WorkflowQueueProblem("workflow interruption kind is invalid")
        if not _workflow_code(reason_code):
            raise WorkflowQueueProblem("workflow cancellation reason is invalid")
        with self._transaction() as connection:
            current = self._row(self._select_job(connection, self._project_id, job_id))
            current_sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM workflow_history_events "
                    "WHERE project_id=? AND workflow_run_id=?",
                    (self._project_id, current.workflow_run_id),
                ).fetchone()[0]
            )
            if expected_history_sequence is not None and expected_history_sequence != current_sequence:
                raise WorkflowQueueConflict("workflow cancellation precondition is stale")
            if current.state in {"succeeded", "failed", "cancelled"}:
                return current
            if current.state == "cancelling":
                return current
            next_state = "cancelling" if current.state == "running" else "cancelled"
            if current.state == "claimed" and current.current_attempt_id is not None:
                attempt_row = connection.execute(
                    "SELECT state, progress_json FROM workflow_job_attempts WHERE attempt_id=?",
                    (current.current_attempt_id,),
                ).fetchone()
                if attempt_row is None or str(attempt_row[0]) != "claimed":
                    raise WorkflowQueueCorrupt("workflow claimed attempt authority differs")
                connection.execute(
                    "UPDATE workflow_job_attempts SET state='cancelled', ended_at=?, diagnostic_code=? "
                    "WHERE attempt_id=?",
                    (now, reason_code, current.current_attempt_id),
                )
                connection.execute(
                    """
                    UPDATE workflow_attempt_artifacts
                       SET disposition=(SELECT partial_artifact_disposition FROM workflow_queue_jobs WHERE job_id=?),
                           updated_at=?
                     WHERE attempt_id=? AND disposition='retained-incomplete'
                    """,
                    (job_id, now, current.current_attempt_id),
                )
                self._append_history(
                    connection,
                    project_id=self._project_id,
                    workflow_run_id=current.workflow_run_id,
                    job_id=job_id,
                    attempt_id=current.current_attempt_id,
                    entity_type="job-attempt",
                    entity_id=current.current_attempt_id,
                    from_state="claimed",
                    to_state="cancelled",
                    occurred_at=now,
                    actor=actor,
                    reason_code=reason_code,
                    extra={
                        "interruptionKind": interruption_kind,
                        "progress": cast(dict[str, object], json.loads(str(attempt_row[1]))),
                    },
                )
            connection.execute(
                """
                UPDATE workflow_queue_jobs
                   SET state=?, cancellation_requested_at=?, cancellation_reason_code=?,
                       interruption_kind=?, lease_owner=CASE WHEN ?='cancelled' THEN NULL ELSE lease_owner END,
                       lease_token_sha256=CASE WHEN ?='cancelled' THEN NULL ELSE lease_token_sha256 END,
                       lease_expires_at=CASE WHEN ?='cancelled' THEN NULL ELSE lease_expires_at END,
                       updated_at=?
                 WHERE project_id=? AND job_id=?
                """,
                (
                    next_state,
                    now,
                    reason_code,
                    interruption_kind,
                    next_state,
                    next_state,
                    next_state,
                    now,
                    self._project_id,
                    job_id,
                ),
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=current.workflow_run_id,
                job_id=job_id,
                attempt_id=current.current_attempt_id,
                entity_type="job",
                entity_id=job_id,
                from_state=current.state,
                to_state=next_state,
                occurred_at=now,
                actor=actor,
                reason_code=reason_code,
                extra={"interruptionKind": interruption_kind},
            )
            return self._row(self._select_job(connection, self._project_id, job_id))

    def retry_as_continuation(
        self,
        job_id: str,
        *,
        expected_history_sequence: int,
        idempotency_key: str,
        actor: WorkflowActor,
        now: str,
    ) -> WorkflowTaskCenterRunRecord:
        _workflow_time(now)
        _workflow_actor(actor)
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 256:
            raise WorkflowQueueProblem("workflow retry idempotency key is invalid")
        retry_key = "sha256:" + hashlib.sha256(f"workflow-retry\0{job_id}\0{idempotency_key}".encode()).hexdigest()
        command_fingerprint = _workflow_sha256({"command": "retry-as-continuation", "sourceJobId": job_id})
        connection: CanonicalConnection | None = None
        try:
            connection = self._open()
            replay = connection.execute(
                "SELECT workflow_run_id, command_fingerprint FROM workflow_queue_jobs "
                "WHERE project_id=? AND idempotency_key=?",
                (self._project_id, retry_key),
            ).fetchone()
            if replay is not None:
                if str(replay[1]) != command_fingerprint:
                    raise WorkflowQueueConflict("workflow retry replay differs")
                return self._task_center_run(str(replay[0]), connection)
            source = connection.execute(
                """
                SELECT job.workflow_run_id, job.state, job.concurrency_class, job.priority,
                       snapshot.snapshot_json, definition.definition_json
                  FROM workflow_queue_jobs AS job
                  JOIN workflow_authority_snapshots AS snapshot
                    ON snapshot.snapshot_id=job.snapshot_id
                   AND snapshot.snapshot_revision=job.snapshot_revision
                  JOIN workflow_definitions AS definition
                    ON definition.definition_revision_id=snapshot.definition_revision_id
                 WHERE job.project_id=? AND job.job_id=?
                """,
                (self._project_id, job_id),
            ).fetchone()
            if source is None:
                raise WorkflowQueueNotFound("workflow job was not found")
            if str(source[1]) not in {"failed", "cancelled"}:
                raise WorkflowQueueConflict("workflow retry requires a terminal unsuccessful job")
            current_sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM workflow_history_events "
                    "WHERE project_id=? AND workflow_run_id=?",
                    (self._project_id, source[0]),
                ).fetchone()[0]
            )
            if current_sequence != expected_history_sequence:
                raise WorkflowQueueConflict("workflow retry precondition is stale")
            definition = cast(dict[str, object], json.loads(str(source[5])))
            snapshot = cast(dict[str, object], json.loads(str(source[4])))
            concurrency_class = cast(ConcurrencyClass, str(source[2]))
            priority = int(source[3])
        finally:
            if connection is not None:
                connection.close()

        continued = deepcopy(snapshot)
        timestamp_ms = int(_workflow_time(now).timestamp() * 1_000)
        continued_run_id = new_uuid_v7(timestamp_ms=timestamp_ms)
        continued_snapshot_id = new_uuid_v7(timestamp_ms=timestamp_ms)
        old_run_id = str(continued["workflowRunId"])
        identity_map: dict[str, str] = {old_run_id: continued_run_id}
        for collection, key in (
            ("stepRuns", "stepRunId"),
            ("jobs", "jobId"),
            ("attempts", "attemptId"),
            ("checkpoints", "checkpointId"),
            ("humanTasks", "humanTaskId"),
        ):
            for value in cast(list[dict[str, object]], continued[collection]):
                identity_map[str(value[key])] = new_uuid_v7(timestamp_ms=timestamp_ms)
        new_job_id = identity_map[job_id]

        def remap(value: object) -> object:
            if isinstance(value, dict):
                return {key: remap(item) for key, item in value.items()}
            if isinstance(value, list):
                return [remap(item) for item in value]
            return identity_map.get(value, value) if isinstance(value, str) else value

        continued = cast(dict[str, object], remap(continued))
        continued["snapshotId"] = continued_snapshot_id
        continued["snapshotRevision"] = 1
        continued["workflowRunId"] = continued_run_id
        continued["createdAt"] = now
        continued["updatedAt"] = now
        jobs = cast(list[dict[str, object]], continued["jobs"])
        if len(jobs) != 1 or str(jobs[0]["jobId"]) != new_job_id:
            raise WorkflowQueueConflict("workflow retry source is not a single-job continuation")
        jobs[0]["idempotencyKey"] = retry_key
        jobs[0]["commandFingerprint"] = command_fingerprint
        history = cast(list[dict[str, object]], continued["history"])
        for event in history:
            event["eventId"] = new_uuid_v7(timestamp_ms=timestamp_ms)
            event["occurredAt"] = now
        history[-1]["actor"] = {
            "actorId": actor.actor_id,
            "actorType": actor.actor_type,
            "role": actor.role,
        }
        from .workflow_executor import prepare_workflow_job

        submission = prepare_workflow_job(
            definition,
            continued,
            job_id=new_job_id,
            concurrency_class=concurrency_class,
            priority=priority,
            available_at=now,
        )
        self.enqueue(submission, actor=actor)
        return self._task_center_run(continued_run_id)

    def complete_human_task(
        self,
        human_task_id: str,
        *,
        expected_snapshot_revision: int,
        expected_history_sequence: int,
        decision_id: str,
        disposition: WorkflowHumanDisposition,
        actor: WorkflowActor,
        now: str,
    ) -> WorkflowTaskCenterRunRecord:
        _workflow_time(now)
        _workflow_actor(actor)
        if not is_uuid_v7(human_task_id) or not is_uuid_v7(decision_id):
            raise WorkflowQueueProblem("workflow human decision identity is invalid")
        if disposition not in {"approved", "rejected", "deferred", "not-applicable"}:
            raise WorkflowQueueProblem("workflow human disposition is invalid")
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT snapshot.snapshot_id, snapshot.snapshot_revision, snapshot.workflow_run_id,
                       snapshot.snapshot_json, definition.definition_json
                  FROM workflow_authority_snapshots AS snapshot
                  JOIN workflow_definitions AS definition
                    ON definition.definition_revision_id=snapshot.definition_revision_id
                 WHERE snapshot.project_id=?
                 ORDER BY snapshot.updated_at DESC, snapshot.snapshot_revision DESC
                """,
                (self._project_id,),
            ).fetchall()
            authority: tuple[Any, dict[str, object], dict[str, object]] | None = None
            for row in rows:
                candidate = cast(dict[str, object], json.loads(str(row[3])))
                if any(
                    cast(Mapping[str, object], item).get("humanTaskId") == human_task_id
                    for item in cast(list[object], candidate["humanTasks"])
                ):
                    authority = (row, candidate, cast(dict[str, object], json.loads(str(row[4]))))
                    break
            if authority is None:
                raise WorkflowQueueNotFound("workflow human task was not found")
            row, snapshot, definition = authority
            current_revision = int(row[1])
            task = next(
                cast(dict[str, object], item)
                for item in cast(list[object], snapshot["humanTasks"])
                if cast(Mapping[str, object], item)["humanTaskId"] == human_task_id
            )
            existing_decision = cast(Mapping[str, object] | None, task["decision"])
            if current_revision == expected_snapshot_revision + 1 and existing_decision is not None:
                expected_actor = {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role}
                if (
                    existing_decision["decisionId"] == decision_id
                    and existing_decision["disposition"] == disposition
                    and existing_decision["decidedBy"] == expected_actor
                ):
                    return self._task_center_run(str(row[2]), connection)
                raise WorkflowQueueConflict("workflow human decision replay differs")
            current_history_sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM workflow_history_events "
                    "WHERE project_id=? AND workflow_run_id=?",
                    (self._project_id, row[2]),
                ).fetchone()[0]
            )
            if (
                current_revision != expected_snapshot_revision
                or current_history_sequence != expected_history_sequence
                or task["state"] not in {"requested", "claimed"}
            ):
                raise WorkflowQueueConflict("workflow human decision precondition is stale")
            assigned = cast(Mapping[str, object] | None, task["assignedTo"])
            if (
                actor.actor_type != "human"
                or actor.role != task["requiredRole"]
                or assigned is None
                or assigned != {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role}
            ):
                raise WorkflowQueueConflict("workflow human decision authority differs")
            step_run = next(
                cast(dict[str, object], item)
                for item in cast(list[object], snapshot["stepRuns"])
                if cast(Mapping[str, object], item)["stepRunId"] == task["stepRunId"]
            )
            definition_step = next(
                cast(Mapping[str, object], item)
                for item in cast(list[object], definition["steps"])
                if cast(Mapping[str, object], item)["stepKey"] == step_run["stepKey"]
            )
            human_definition = cast(Mapping[str, object], definition_step["humanTask"])
            allowed = cast(list[object], human_definition["allowedDispositions"])
            consequences = cast(Mapping[str, object], human_definition["consequencesByDisposition"])
            if disposition not in allowed or not isinstance(consequences.get(disposition), str):
                raise WorkflowQueueConflict("workflow human disposition is not authorized")
            consequence = str(consequences[disposition])
            if consequence not in {"resume-workflow", "end-workflow", "skip-step"}:
                raise WorkflowQueueConflict("workflow human consequence is not executable")

            next_snapshot = deepcopy(snapshot)
            next_task = next(
                cast(dict[str, object], item)
                for item in cast(list[object], next_snapshot["humanTasks"])
                if cast(Mapping[str, object], item)["humanTaskId"] == human_task_id
            )
            next_step = next(
                cast(dict[str, object], item)
                for item in cast(list[object], next_snapshot["stepRuns"])
                if cast(Mapping[str, object], item)["stepRunId"] == next_task["stepRunId"]
            )
            history = cast(list[dict[str, object]], next_snapshot["history"])
            sequence = cast(int, next_snapshot["sequence"])
            next_task["state"] = "completed"
            next_task["sequence"] = sequence + 1
            next_task["decision"] = {
                "decisionId": decision_id,
                "disposition": disposition,
                "decidedBy": {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role},
                "decidedAt": now,
                "evidenceArtifactIds": list(cast(list[object], next_task["evidenceArtifactIds"])),
                "rationaleArtifactId": None,
                "consequenceCode": consequence,
            }
            history.append(
                _workflow_event(
                    sequence=sequence + 1,
                    entity_type="human-task",
                    entity_id=human_task_id,
                    from_state=str(task["state"]),
                    to_state="completed",
                    occurred_at=now,
                    actor=actor,
                    reason_code="human-decision-recorded",
                    decision_id=decision_id,
                )
            )
            terminal_state = "failed" if consequence == "end-workflow" else "succeeded"
            next_step["state"] = terminal_state
            next_step["sequence"] = sequence + 2
            next_step["progress"] = {
                "kind": "quantified",
                "unit": cast(Mapping[str, object], definition_step["progress"])["unit"],
                "completedUnits": 1,
                "totalUnits": 1,
            }
            history.append(
                _workflow_event(
                    sequence=sequence + 2,
                    entity_type="workflow-step",
                    entity_id=str(next_step["stepRunId"]),
                    from_state=str(step_run["state"]),
                    to_state=terminal_state,
                    occurred_at=now,
                    actor=actor,
                    reason_code="human-decision-accepted"
                    if terminal_state == "succeeded"
                    else "human-decision-rejected",
                    decision_id=decision_id,
                )
            )
            if terminal_state == "succeeded":
                history.append(
                    _workflow_event(
                        sequence=sequence + 3,
                        entity_type="workflow-run",
                        entity_id=str(next_snapshot["workflowRunId"]),
                        from_state=str(snapshot["state"]),
                        to_state="running",
                        occurred_at=now,
                        actor=actor,
                        reason_code="human-decision-accepted",
                        decision_id=decision_id,
                    )
                )
                history.append(
                    _workflow_event(
                        sequence=sequence + 4,
                        entity_type="workflow-run",
                        entity_id=str(next_snapshot["workflowRunId"]),
                        from_state="running",
                        to_state="succeeded",
                        occurred_at=now,
                        actor=actor,
                        reason_code="workflow-complete",
                    )
                )
                next_sequence = sequence + 4
            else:
                history.append(
                    _workflow_event(
                        sequence=sequence + 3,
                        entity_type="workflow-run",
                        entity_id=str(next_snapshot["workflowRunId"]),
                        from_state=str(snapshot["state"]),
                        to_state="failed",
                        occurred_at=now,
                        actor=actor,
                        reason_code="human-decision-rejected",
                        decision_id=decision_id,
                    )
                )
                next_sequence = sequence + 3
            next_snapshot["snapshotRevision"] = expected_snapshot_revision + 1
            next_snapshot["state"] = terminal_state
            next_snapshot["sequence"] = next_sequence
            next_snapshot["updatedAt"] = now
            if terminal_state == "succeeded":
                total = cast(Mapping[str, object], next_snapshot["progress"])["totalUnits"]
                next_snapshot["progress"] = {
                    "kind": "quantified",
                    "unit": cast(Mapping[str, object], next_snapshot["progress"])["unit"],
                    "completedUnits": total,
                    "totalUnits": total,
                }
            if workflow_snapshot_errors(definition, next_snapshot):
                raise WorkflowQueueCorrupt("workflow human decision produced invalid authority")
            next_json = _workflow_json(next_snapshot)
            self._store_authority(
                connection,
                definition=definition,
                snapshot=next_snapshot,
                definition_json=_workflow_json(definition),
                snapshot_json=next_json,
            )
            return self._task_center_run(str(row[2]), connection)

    def cancellation_requested(self, claim: WorkflowJobClaim, *, now: str) -> bool:
        _workflow_time(now)
        connection: CanonicalConnection | None = None
        try:
            connection = self._open()
            row = self._lease_row(connection, claim, now, states=("claimed", "running", "cancelling"))
            return row[3] is not None
        except WorkflowQueueProblem:
            raise
        except (OSError, sqlite3.Error, StorageProblem, TypeError, ValueError) as error:
            raise WorkflowQueueProblem("workflow cancellation read failed") from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _output_manifest(outputs: tuple[WorkflowOutputReference, ...]) -> tuple[str, str]:
        if not outputs:
            raise WorkflowQueueProblem("workflow output manifest is empty")
        values: list[dict[str, object]] = []
        for output in outputs:
            if (
                not is_uuid_v7(output.artifact_id)
                or not is_uuid_v7(output.revision_id)
                or (output.provenance_entity_id is not None and not is_uuid_v7(output.provenance_entity_id))
                or len(output.content_hash) != 71
                or not output.content_hash.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in output.content_hash[7:])
                or "/" not in output.media_type
            ):
                raise WorkflowQueueProblem("workflow output reference is invalid")
            values.append(
                {
                    "artifactId": output.artifact_id,
                    "revisionId": output.revision_id,
                    "contentHash": output.content_hash,
                    "mediaType": output.media_type,
                    "provenanceEntityId": output.provenance_entity_id,
                }
            )
        if len({item.artifact_id for item in outputs}) != len(outputs) or len(
            {item.revision_id for item in outputs}
        ) != len(outputs):
            raise WorkflowQueueProblem("workflow output references are not distinct")
        manifest = _workflow_json({"outputs": values})
        return manifest, "sha256:" + hashlib.sha256(manifest.encode("utf-8")).hexdigest()

    def _resolve_outputs(
        self,
        connection: CanonicalConnection,
        outputs: tuple[WorkflowOutputReference, ...],
    ) -> tuple[AggregateRevision, ...]:
        revisions: list[AggregateRevision] = []
        for output in outputs:
            if output.provenance_entity_id not in {None, output.artifact_id}:
                raise WorkflowQueueConflict("workflow output provenance identity differs")
            row = connection.execute(
                """
                SELECT revision.revision_id, revision.aggregate_id, revision.aggregate_kind,
                       revision.project_id, revision.revision, revision.contract_version,
                       revision.created_at, revision.modified_at,
                       revision.display_label_observed, revision.display_label_normalized,
                       revision.knowledge_status, revision.rights_status, document.object_sha256
                  FROM aggregate_revisions AS revision
                  LEFT JOIN documents AS document
                    ON document.project_id=revision.project_id
                   AND document.revision_id=revision.revision_id
                 WHERE revision.project_id=? AND revision.revision_id=?
                   AND revision.aggregate_id=?
                """,
                (self._project_id, output.revision_id, output.artifact_id),
            ).fetchone()
            if row is None:
                raise WorkflowQueueConflict("workflow output revision is not canonical")
            revision = _projection(row)
            content_rows = connection.execute(
                """
                SELECT DISTINCT content_hash
                  FROM provenance_ledger_entities
                 WHERE project_id=? AND entity_id=? AND revision_id=? AND direction='output'
                """,
                (self._project_id, output.artifact_id, output.revision_id),
            ).fetchall()
            if len(content_rows) != 1 or str(content_rows[0][0]) != output.content_hash:
                raise WorkflowQueueConflict("workflow output content authority differs")
            revisions.append(revision)
        return tuple(revisions)

    @staticmethod
    def _artifact_row(row: Any) -> WorkflowArtifactRecord:
        if row is None:
            raise WorkflowQueueNotFound("workflow attempt artifact was not found")
        return WorkflowArtifactRecord(
            attempt_id=str(row[0]),
            job_id=str(row[1]),
            artifact_id=str(row[2]),
            revision_id=str(row[3]),
            role=cast(WorkflowArtifactRole, str(row[4])),
            disposition=cast(Any, str(row[5])),
            content_hash=str(row[6]),
            media_type=str(row[7]),
            provenance_entity_id=None if row[8] is None else str(row[8]),
        )

    def stage_artifact(
        self,
        claim: WorkflowJobClaim,
        *,
        artifact: WorkflowOutputReference,
        role: WorkflowArtifactRole,
        now: str,
    ) -> WorkflowArtifactRecord:
        _workflow_time(now)
        if role not in {"output", "checkpoint", "diagnostic"}:
            raise WorkflowQueueProblem("workflow artifact role is invalid")
        self._output_manifest((artifact,))
        with self._transaction() as connection:
            self._lease_row(connection, claim, now, states=("running", "cancelling"))
            self._resolve_outputs(connection, (artifact,))
            existing = connection.execute(
                """
                SELECT attempt_id, job_id, artifact_id, revision_id, role, disposition,
                       content_hash, media_type, provenance_entity_id
                  FROM workflow_attempt_artifacts
                 WHERE attempt_id=? AND artifact_id=?
                """,
                (claim.attempt_id, artifact.artifact_id),
            ).fetchone()
            expected = (
                claim.attempt_id,
                claim.job_id,
                artifact.artifact_id,
                artifact.revision_id,
                role,
                "retained-incomplete",
                artifact.content_hash,
                artifact.media_type,
                artifact.provenance_entity_id,
            )
            if existing is not None:
                if tuple(existing) != expected:
                    raise WorkflowQueueConflict("workflow attempt artifact replay differs")
                return self._artifact_row(existing)
            connection.execute(
                """
                INSERT INTO workflow_attempt_artifacts (
                    attempt_id, project_id, job_id, artifact_id, revision_id, role,
                    disposition, content_hash, media_type, provenance_entity_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'retained-incomplete', ?, ?, ?, ?, ?)
                """,
                (
                    claim.attempt_id,
                    self._project_id,
                    claim.job_id,
                    artifact.artifact_id,
                    artifact.revision_id,
                    role,
                    artifact.content_hash,
                    artifact.media_type,
                    artifact.provenance_entity_id,
                    now,
                    now,
                ),
            )
            return WorkflowArtifactRecord(
                claim.attempt_id,
                claim.job_id,
                artifact.artifact_id,
                artifact.revision_id,
                role,
                "retained-incomplete",
                artifact.content_hash,
                artifact.media_type,
                artifact.provenance_entity_id,
            )

    def complete(
        self,
        claim: WorkflowJobClaim,
        *,
        now: str,
        outputs: tuple[WorkflowOutputReference, ...],
    ) -> WorkflowCompletionReceipt:
        _workflow_time(now)
        manifest, output_sha256 = self._output_manifest(outputs)
        with self._transaction() as connection:
            existing = connection.execute(
                """
                SELECT attempt_id, output_manifest_json, output_record_sha256, committed_at,
                       idempotency_key, command_fingerprint
                  FROM workflow_committed_outputs WHERE project_id=? AND job_id=?
                """,
                (self._project_id, claim.job_id),
            ).fetchone()
            if existing is not None:
                self._verify_attempt_capability(connection, claim)
                if tuple(existing[:3]) != (claim.attempt_id, manifest, output_sha256) or tuple(existing[4:]) != (
                    claim.idempotency_key,
                    claim.command_fingerprint,
                ):
                    raise WorkflowQueueConflict("workflow completion replay differs")
                return WorkflowCompletionReceipt(claim.job_id, claim.attempt_id, output_sha256, str(existing[3]), True)

            row = self._lease_row(connection, claim, now, states=("running",))
            if row[3] is not None:
                raise WorkflowQueueConflict("workflow cancellation precedes completion")
            if (
                str(row[9]) == "required"
                and connection.execute(
                    "SELECT 1 FROM workflow_checkpoints WHERE project_id=? AND job_id=? LIMIT 1",
                    (self._project_id, claim.job_id),
                ).fetchone()
                is None
            ):
                raise WorkflowQueueConflict("workflow required checkpoint is missing")
            output_revisions = self._resolve_outputs(connection, outputs)
            for output in outputs:
                staged = connection.execute(
                    """
                    SELECT revision_id, role, disposition, content_hash, media_type, provenance_entity_id
                      FROM workflow_attempt_artifacts
                     WHERE project_id=? AND job_id=? AND attempt_id=? AND artifact_id=?
                    """,
                    (self._project_id, claim.job_id, claim.attempt_id, output.artifact_id),
                ).fetchone()
                expected = (
                    output.revision_id,
                    "output",
                    "retained-incomplete",
                    output.content_hash,
                    output.media_type,
                    output.provenance_entity_id,
                )
                if staged is None or tuple(staged) != expected:
                    raise WorkflowQueueConflict("workflow output was not staged by the current attempt")
            provenance_event_id = _workflow_uuid(now)
            outbox_id = _workflow_uuid(now)
            trace_id = hashlib.sha256(claim.job_id.encode("ascii")).hexdigest()[:32]
            provenance_event = AtomicRepositoryEvent(
                event_id=provenance_event_id,
                outbox_id=outbox_id,
                event_type="org.research-observatory.workflow.job-succeeded.v1",
                occurred_at=now,
                available_at=now,
                trace_id=trace_id,
                actor_type="worker",
                actor_id=claim.worker_id,
                idempotency_key=f"workflow-output:{claim.job_id}",
            )
            provenance_fingerprint = hashlib.sha256(
                f"{claim.command_fingerprint}\n{output_sha256}".encode("ascii")
            ).hexdigest()
            _record_provenance(
                connection,
                project_id=self._project_id,
                primary_revision_id=output_revisions[0].revision_id,
                record_json=canonical_workflow_completion_provenance_event(
                    outputs=output_revisions,
                    event=provenance_event,
                ),
                event=provenance_event,
                idempotency_sha256=provenance_fingerprint,
            )
            connection.execute(
                """
                INSERT INTO workflow_committed_outputs (
                    job_id, project_id, attempt_id, idempotency_key, command_fingerprint,
                    output_manifest_json, output_record_sha256, committed_at,
                    provenance_event_id, outbox_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.job_id,
                    self._project_id,
                    claim.attempt_id,
                    claim.idempotency_key,
                    claim.command_fingerprint,
                    manifest,
                    output_sha256,
                    now,
                    provenance_event_id,
                    outbox_id,
                ),
            )
            connection.execute(
                "UPDATE workflow_job_attempts SET state='succeeded', ended_at=? WHERE attempt_id=?",
                (now, claim.attempt_id),
            )
            for output in outputs:
                connection.execute(
                    "UPDATE workflow_attempt_artifacts SET disposition='committed', updated_at=? "
                    "WHERE attempt_id=? AND artifact_id=? AND role='output' "
                    "AND disposition='retained-incomplete'",
                    (now, claim.attempt_id, output.artifact_id),
                )
            connection.execute(
                """
                UPDATE workflow_queue_jobs
                   SET state='succeeded', lease_owner=NULL, lease_token_sha256=NULL,
                       lease_expires_at=NULL, committed_output_sha256=?, updated_at=?
                 WHERE job_id=?
                """,
                (output_sha256, now, claim.job_id),
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(row[0]),
                job_id=claim.job_id,
                attempt_id=claim.attempt_id,
                entity_type="job-attempt",
                entity_id=claim.attempt_id,
                from_state="running",
                to_state="succeeded",
                occurred_at=now,
                actor=WorkflowActor(claim.worker_id, "workload", "local-workflow-worker"),
                reason_code="output-committed",
                extra={"progress": cast(dict[str, object], json.loads(str(row[5])))},
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(row[0]),
                job_id=claim.job_id,
                attempt_id=claim.attempt_id,
                entity_type="job",
                entity_id=claim.job_id,
                from_state="running",
                to_state="succeeded",
                occurred_at=now,
                actor=WorkflowActor(claim.worker_id, "workload", "local-workflow-worker"),
                reason_code="attempt-accepted",
            )
            return WorkflowCompletionReceipt(claim.job_id, claim.attempt_id, output_sha256, now, False)

    def _finish_attempt(self, claim: WorkflowJobClaim, *, now: str, error_code: str, cancel: bool) -> WorkflowJobRecord:
        _workflow_time(now)
        if not _workflow_code(error_code):
            raise WorkflowQueueProblem("workflow diagnostic code is invalid")
        with self._transaction() as connection:
            row = self._lease_row(
                connection,
                claim,
                now,
                states=("claimed", "running", "cancelling") if cancel else ("claimed", "running"),
            )
            job = self._row(self._select_job(connection, self._project_id, claim.job_id))
            if cancel:
                next_state = "cancelled"
                attempt_state = "cancelled"
                available_at = job.available_at
            else:
                policy = connection.execute(
                    "SELECT initial_backoff_ms, maximum_backoff_ms, multiplier_basis_points, "
                    "deterministic_jitter, retryable_error_codes_json, non_retryable_error_codes_json "
                    "FROM workflow_queue_jobs WHERE job_id=?",
                    (claim.job_id,),
                ).fetchone()
                retryable = error_code in json.loads(str(policy[4])) and error_code not in json.loads(str(policy[5]))
                retryable = retryable and job.attempt_count < job.max_attempts
                next_state = "retry-scheduled" if retryable else "failed"
                attempt_state = "failed"
                exponent = max(0, claim.attempt_number - 1)
                delay = min(int(policy[1]), int(int(policy[0]) * (int(policy[2]) / 10_000) ** exponent))
                if retryable and int(policy[3]) and delay:
                    delay += int(hashlib.sha256(claim.job_id.encode("ascii")).hexdigest()[:8], 16) % max(1, delay // 5)
                    delay = min(int(policy[1]), delay)
                available_at = _workflow_timestamp(_workflow_time(now) + timedelta(milliseconds=delay))
            connection.execute(
                "UPDATE workflow_job_attempts SET state=?, ended_at=?, diagnostic_code=? WHERE attempt_id=?",
                (attempt_state, now, error_code, claim.attempt_id),
            )
            if cancel:
                connection.execute(
                    "UPDATE workflow_attempt_artifacts SET disposition=?, updated_at=? "
                    "WHERE attempt_id=? AND disposition='retained-incomplete'",
                    (str(row[10]), now, claim.attempt_id),
                )
            connection.execute(
                """
                UPDATE workflow_queue_jobs
                   SET state=?, available_at=?, lease_owner=NULL, lease_token_sha256=NULL,
                       lease_expires_at=NULL, diagnostic_code=?, updated_at=? WHERE job_id=?
                """,
                (next_state, available_at, error_code, now, claim.job_id),
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(row[0]),
                job_id=claim.job_id,
                attempt_id=claim.attempt_id,
                entity_type="job-attempt",
                entity_id=claim.attempt_id,
                from_state=str(row[4]),
                to_state=attempt_state,
                occurred_at=now,
                actor=WorkflowActor(claim.worker_id, "workload", "local-workflow-worker"),
                reason_code=error_code,
                extra={"progress": cast(dict[str, object], json.loads(str(row[5])))},
            )
            self._append_history(
                connection,
                project_id=self._project_id,
                workflow_run_id=str(row[0]),
                job_id=claim.job_id,
                attempt_id=claim.attempt_id,
                entity_type="job",
                entity_id=claim.job_id,
                from_state=str(row[1]),
                to_state=next_state,
                occurred_at=now,
                actor=WorkflowActor(claim.worker_id, "workload", "local-workflow-worker"),
                reason_code=error_code,
            )
            return self._row(self._select_job(connection, self._project_id, claim.job_id))

    def fail(self, claim: WorkflowJobClaim, *, now: str, error_code: str) -> WorkflowJobRecord:
        return self._finish_attempt(claim, now=now, error_code=error_code, cancel=False)

    def cancel(self, claim: WorkflowJobClaim, *, now: str, reason_code: str) -> WorkflowJobRecord:
        return self._finish_attempt(claim, now=now, error_code=reason_code, cancel=True)

    def recover_expired(self, *, now: str, actor: WorkflowActor, limit: int = 100) -> int:
        _workflow_time(now)
        _workflow_actor(actor)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1_000:
            raise WorkflowQueueProblem("workflow recovery limit is invalid")
        recovered = 0
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT job.job_id, job.workflow_run_id, job.state, job.current_attempt_id,
                       job.attempt_count, job.max_attempts, job.cancellation_requested_at,
                       attempt.state, job.interruption_kind, job.partial_artifact_disposition,
                       attempt.progress_json
                  FROM workflow_queue_jobs AS job
                  JOIN workflow_job_attempts AS attempt ON attempt.attempt_id=job.current_attempt_id
                 WHERE job.project_id=? AND job.state IN ('claimed', 'running', 'cancelling')
                   AND job.lease_expires_at<=? ORDER BY job.job_id LIMIT ?
                """,
                (self._project_id, now, limit),
            ).fetchall()
            for row in rows:
                job_id = str(row[0])
                attempt_id = str(row[3])
                if row[6] is not None or str(row[2]) == "cancelling":
                    next_state = "cancelled"
                    diagnostic = "cancellation-recovered"
                elif int(row[4]) < int(row[5]):
                    next_state = "retry-scheduled"
                    diagnostic = "lease-expired"
                else:
                    next_state = "failed"
                    diagnostic = "attempts-exhausted"
                recovery_interruption = (
                    str(row[8]) if next_state == "cancelled" and row[8] is not None else "ordinary-restart"
                )
                connection.execute(
                    "UPDATE workflow_job_attempts SET state='abandoned', ended_at=?, diagnostic_code=? "
                    "WHERE attempt_id=?",
                    (now, diagnostic, attempt_id),
                )
                if next_state == "cancelled":
                    connection.execute(
                        "UPDATE workflow_attempt_artifacts SET disposition=?, updated_at=? "
                        "WHERE attempt_id=? AND disposition='retained-incomplete'",
                        (str(row[9]), now, attempt_id),
                    )
                connection.execute(
                    """
                    UPDATE workflow_queue_jobs
                       SET state=?, available_at=?, lease_owner=NULL, lease_token_sha256=NULL,
                           lease_expires_at=NULL, diagnostic_code=?, updated_at=? WHERE job_id=?
                    """,
                    (next_state, now, diagnostic, now, job_id),
                )
                self._append_history(
                    connection,
                    project_id=self._project_id,
                    workflow_run_id=str(row[1]),
                    job_id=job_id,
                    attempt_id=attempt_id,
                    entity_type="job-attempt",
                    entity_id=attempt_id,
                    from_state=str(row[7]),
                    to_state="abandoned",
                    occurred_at=now,
                    actor=actor,
                    reason_code=diagnostic,
                    extra={
                        "interruptionKind": recovery_interruption,
                        "progress": cast(dict[str, object], json.loads(str(row[10]))),
                    },
                )
                self._append_history(
                    connection,
                    project_id=self._project_id,
                    workflow_run_id=str(row[1]),
                    job_id=job_id,
                    attempt_id=attempt_id,
                    entity_type="job",
                    entity_id=job_id,
                    from_state=str(row[2]),
                    to_state=next_state,
                    occurred_at=now,
                    actor=actor,
                    reason_code=diagnostic,
                    extra={"interruptionKind": recovery_interruption},
                )
                recovered += 1
        return recovered


def sqlite_workflow_queue_repository(path: Path, project_id: str) -> WorkflowQueueRepository:
    """Compose the canonical local workflow queue for one authorized project."""

    return _SqliteWorkflowQueueRepository(path / "state" / "project.sqlite3", project_id)


def sqlite_provenance_ledger_repository(path: Path, project_id: str) -> ProvenanceLedgerRepository:
    """Compose the canonical provenance repository for one authorized project."""

    return _SqliteProvenanceLedgerRepository(path / "state" / "project.sqlite3", project_id)


__all__ = [
    "create_sqlite_unit_of_work_factory",
    "sqlite_intent_revision_repository",
    "sqlite_privacy_policy_repository",
    "sqlite_provenance_ledger_repository",
    "sqlite_workflow_queue_repository",
]
