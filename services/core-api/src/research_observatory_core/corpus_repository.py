"""Protected, append-only CorpusItem publication in one canonical transaction.

The service resolves protected source data before taking the writer. This
adapter rechecks its durable identity and the current Work/Intent/privacy
authority under that writer, then publishes the common aggregate, corpus
projection, provenance, outbox, and retry binding as one unit.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from .connector_service import _fingerprint as _connector_fingerprint
from .corpus.membership import (
    CorpusDecision,
    CorpusItemRevision,
    CorpusProblem,
    DiscoveryPath,
    append_discovery_path,
    apply_decision,
    rebind_work,
)
from .corpus_contracts import encode_corpus_decision, encode_corpus_item_revision, encode_discovery_path
from .corpus_source_projection import SourceProjectionProblem, apply_source_projection
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ingestion.preview_workflow import fingerprint
from .ports.corpus import CorpusActor
from .ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    MaterialDependency,
    RepositoryNotFound,
)
from .privacy import _DEFAULTS, _SETTING_KEYS, _projection
from .reconciliation.contracts import SourceAssertion
from .repositories import _UNIT_OF_WORKS, _projection_content_sha256, _SqliteAggregateRepository
from .rights_policy import RightsAction, RightsDecision, RightsRequest, RightsUse
from .rights_repository import RightsProblem, SqliteRightsRepository
from .storage import (
    _DATABASE_ERRORS,
    CanonicalConnection,
    StorageProblem,
    _normalize_utc_millisecond,
    open_canonical_database,
)
from .workflow_contracts import workflow_record_sha256, workflow_snapshot_errors

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TRACE = re.compile(r"[0-9a-f]{32}\Z")
_CORPUS_RIGHTS_ACTIONS: tuple[RightsAction, ...] = ("store", "inspect", "derive", "index")


def _publication_step(_step: str) -> None:
    """Deterministic failure seam; callers never retry a partially committed write."""


def _connector_output_matches(manifest_json: str, manifest_sha256: str, page: AggregateRevision) -> bool:
    """Accept one exact typed page output, never a UUID mention elsewhere in JSON."""

    try:
        manifest = json.loads(manifest_json)
    except TypeError, ValueError:
        return False
    return (
        manifest
        == {
            "outputs": [
                {
                    "artifactId": page.aggregate_id,
                    "revisionId": page.revision_id,
                    "contentHash": _projection_content_sha256(page),
                    "mediaType": "application/json",
                    "provenanceEntityId": page.aggregate_id,
                }
            ]
        }
        and manifest_sha256 == "sha256:" + hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    )


class _RightsUseDenied(Exception):
    """Carry the evaluated denial across a rolled-back corpus transaction."""

    def __init__(self, decision: RightsDecision, actor: CorpusActor) -> None:
        self.decision = decision
        self.actor = actor


class SqliteCorpusRepository:
    def __init__(self, database: Path, project_id: str) -> None:
        if not database.is_absolute() or not project_id:
            raise CorpusProblem("corpus-storage-invalid")
        self._database = database
        self._project = project_id

    @contextmanager
    def _transaction(self, *, write: bool) -> Iterator[tuple[CanonicalConnection, _SqliteAggregateRepository]]:
        connection: CanonicalConnection | None = None
        token: str | None = None
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project)
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            token = _UNIT_OF_WORKS.register(connection, self._project)
            yield connection, _SqliteAggregateRepository(token)
            connection.execute("COMMIT")
        except _RightsUseDenied as denied:
            # A failed corpus publication rolls back its in-writer use records.
            # Persist the exact evaluated denial after releasing that writer;
            # never re-evaluate against a policy that may have changed meanwhile.
            if connection is not None and connection.in_transaction:
                connection.rollback()
            if token is not None:
                _UNIT_OF_WORKS.unregister(token)
                token = None
            if connection is not None:
                connection.close()
                connection = None
            try:
                SqliteRightsRepository(self._database, self._project).append_denied_attempt(
                    denied.decision, actor=denied.actor
                )
            except RightsProblem:
                raise CorpusProblem("corpus-rights-integrity-invalid") from None
            raise CorpusProblem("corpus-rights-denied") from None
        except (*_DATABASE_ERRORS, StorageProblem, sqlite3.Error, OSError):
            raise CorpusProblem("corpus-storage-invalid") from None
        finally:
            if token is not None:
                _UNIT_OF_WORKS.unregister(token)
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    @staticmethod
    def _command(command_id: str, command_sha256: str, actor: CorpusActor) -> None:
        if (
            not is_uuid_v7(command_id)
            or _HASH.fullmatch(command_sha256) is None
            or not is_uuid_v7(actor.actor_id)
            or actor.actor_type != "human"
            or _TRACE.fullmatch(actor.trace_id) is None
            or not is_uuid_v7(actor.intent_revision_id)
            or _HASH.fullmatch(actor.intent_sha256) is None
            or _HASH.fullmatch(actor.policy_sha256) is None
        ):
            raise CorpusProblem("corpus-command-invalid")
        try:
            _normalize_utc_millisecond(actor.occurred_at)
        except ValueError:
            raise CorpusProblem("corpus-command-invalid") from None

    def _authority(self, connection: CanonicalConnection, actor: CorpusActor) -> None:
        # The service validates the complete Intent chain before this point. A
        # latest-row read inside the writer closes the authority-change race.
        intent = connection.execute(
            "SELECT value_type,text_value FROM settings WHERE project_id=? "
            "AND setting_key='research-intent.revision' ORDER BY revision DESC LIMIT 1",
            (self._project,),
        ).fetchone()
        if intent is None or intent[0] != "text":
            raise CorpusProblem("corpus-intent-unavailable")
        try:
            value = json.loads(str(intent[1]))
        except TypeError, ValueError:
            raise CorpusProblem("corpus-intent-unavailable") from None
        if (
            not isinstance(value, dict)
            or value.get("status") != "accepted"
            or value.get("revisionId") != actor.intent_revision_id
            or value.get("revisionContentHash") != "sha256:" + actor.intent_sha256
        ):
            raise CorpusProblem("corpus-intent-changed")

        policy_revision = connection.execute(
            "SELECT MAX(revision) FROM settings WHERE project_id=? AND setting_key LIKE 'privacy.%'",
            (self._project,),
        ).fetchone()[0]
        if policy_revision is None:
            policy = _projection(self._project, 0, dict(_DEFAULTS))
        else:
            rows = connection.execute(
                "SELECT setting_key,value_type,text_value,integer_value FROM settings "
                "WHERE project_id=? AND revision=? AND setting_key LIKE 'privacy.%' ORDER BY setting_key",
                (self._project, policy_revision),
            ).fetchall()
            if tuple(row[0] for row in rows) != _SETTING_KEYS:
                raise CorpusProblem("corpus-policy-unavailable")
            values: dict[str, str | int] = {}
            for key, value_type, text_value, integer_value in rows:
                if value_type == "text" and isinstance(text_value, str) and integer_value is None:
                    values[str(key)] = text_value
                elif value_type == "integer" and isinstance(integer_value, int) and text_value is None:
                    values[str(key)] = integer_value
                else:
                    raise CorpusProblem("corpus-policy-unavailable")
            try:
                policy = _projection(self._project, int(policy_revision), values)
            except TypeError, ValueError:
                raise CorpusProblem("corpus-policy-unavailable") from None
        observed = fingerprint(policy.model_dump(mode="json", by_alias=True)).removeprefix("sha256:")
        if observed != actor.policy_sha256:
            raise CorpusProblem("corpus-policy-changed")

    def _replay(
        self, connection: CanonicalConnection, command_id: str, command_sha256: str
    ) -> CorpusItemRevision | None:
        row = connection.execute(
            "SELECT semantic_sha256,result_item_id,result_revision_id,result_path_id,result_decision_id,"
            "provenance_event_id,outbox_id FROM corpus_commands WHERE project_id=? AND command_id=?",
            (self._project, command_id),
        ).fetchone()
        if row is None:
            return None
        if row[0] != command_sha256:
            raise CorpusProblem("corpus-command-conflict")
        item = self._load(connection, str(row[1]), revision_id=str(row[2]))
        if (
            item.revision_id != row[2]
            or item.decision_revision_id != row[4]
            or (row[3] is not None and str(row[3]) not in item.discovery_path_ids)
            or row[5] is None
            or row[6] is None
        ):
            raise CorpusProblem("corpus-command-integrity-invalid")
        linked = connection.execute(
            "SELECT p.revision_id,o.revision_id,p.record_sha256,o.record_sha256 "
            "FROM provenance_events p JOIN outbox_events o ON o.project_id=p.project_id "
            "WHERE p.project_id=? AND p.event_id=? AND o.outbox_id=?",
            (self._project, row[5], row[6]),
        ).fetchone()
        if linked is None or linked[0] != item.revision_id or linked[1] != item.revision_id or linked[2] != linked[3]:
            raise CorpusProblem("corpus-command-integrity-invalid")
        return item

    def _load(
        self, connection: CanonicalConnection, item_id: str, *, revision_id: str | None = None
    ) -> CorpusItemRevision:
        if not is_uuid_v7(item_id):
            raise CorpusProblem("corpus-item-invalid")
        rows = connection.execute(
            "SELECT s.project_id,s.item_id,s.revision_id,s.previous_revision_id,s.work_id,s.work_revision_id,"
            "s.membership,s.review,s.duplicate_of_item_id,s.availability,s.discovery_fingerprint,"
            "s.decision_revision_id FROM corpus_item_states s JOIN aggregate_revisions r "
            "ON r.revision_id=s.revision_id AND r.project_id=s.project_id "
            "WHERE s.project_id=? AND s.item_id=? AND (? IS NULL OR s.revision_id=?) "
            "AND r.aggregate_kind='corpus-item' ORDER BY r.revision DESC LIMIT 2",
            (self._project, item_id, revision_id, revision_id),
        ).fetchall()
        if not rows:
            raise CorpusProblem("corpus-item-not-found")
        if revision_id is not None and len(rows) != 1:
            raise CorpusProblem("corpus-item-integrity-invalid")
        row = rows[0]
        paths = tuple(
            str(value[0])
            for value in connection.execute(
                "SELECT path_id FROM corpus_item_discovery_paths WHERE project_id=? AND item_id=? "
                "AND revision_id=? ORDER BY path_id LIMIT 1001",
                (self._project, item_id, row[2]),
            )
        )
        try:
            item = CorpusItemRevision.model_validate(
                dict(
                    project_id=row[0],
                    item_id=row[1],
                    revision_id=row[2],
                    previous_revision_id=row[3],
                    work_id=row[4],
                    work_revision_id=row[5],
                    membership=row[6],
                    review=row[7],
                    duplicate_of_item_id=row[8],
                    availability=row[9],
                    discovery_path_ids=paths,
                    decision_revision_id=row[11],
                )
            )
        except ValidationError:
            raise CorpusProblem("corpus-item-integrity-invalid") from None
        if item.discovery_fingerprint != row[10]:
            raise CorpusProblem("corpus-item-integrity-invalid")
        return item

    def _current(
        self, connection: CanonicalConnection, aggregates: _SqliteAggregateRepository, item_id: str
    ) -> tuple[CorpusItemRevision, AggregateRevision]:
        item = self._load(connection, item_id)
        revision = aggregates.get(item_id)
        if revision.revision_id != item.revision_id or revision.aggregate_kind != "corpus-item":
            raise CorpusProblem("corpus-item-integrity-invalid")
        return item, revision

    def _work(
        self, connection: CanonicalConnection, aggregates: _SqliteAggregateRepository, work_id: str, revision_id: str
    ) -> AggregateRevision:
        try:
            work = aggregates.get(work_id)
        except RepositoryNotFound:
            raise CorpusProblem("corpus-work-unavailable") from None
        row = connection.execute(
            "SELECT disposition FROM reconciliation_work_states WHERE project_id=? AND work_id=? AND revision_id=?",
            (self._project, work_id, revision_id),
        ).fetchone()
        seal = connection.execute(
            "SELECT 1 FROM reconciliation_work_seals WHERE project_id=? AND work_revision_id=?",
            (self._project, revision_id),
        ).fetchone()
        if (
            work.aggregate_kind != "record"
            or work.revision_id != revision_id
            or row is None
            or tuple(row) != ("active",)
            or seal is None
        ):
            raise CorpusProblem("corpus-work-unavailable")
        return work

    def _connector_job(
        self, connection: CanonicalConnection, job_id: str
    ) -> tuple[dict[str, object], str, str, str, str, str, str, str]:
        row = connection.execute(
            "SELECT j.job_id,j.workflow_run_id,j.activity_type,j.state,j.command_fingerprint,"
            "j.idempotency_key,s.snapshot_json,s.record_sha256,d.definition_json,d.record_sha256 "
            "FROM workflow_queue_jobs j JOIN workflow_authority_snapshots s "
            "ON s.snapshot_id=j.snapshot_id AND s.snapshot_revision=j.snapshot_revision "
            "AND s.project_id=j.project_id JOIN workflow_definitions d "
            "ON d.definition_revision_id=s.definition_revision_id AND d.project_id=s.project_id "
            "WHERE j.project_id=? AND j.job_id=?",
            (self._project, job_id),
        ).fetchone()
        if row is None:
            raise CorpusProblem("corpus-connector-source-unavailable")
        try:
            snapshot, definition = json.loads(row[6]), json.loads(row[8])
            jobs = [value for value in snapshot["jobs"] if value["jobId"] == row[0]]
            if (
                workflow_snapshot_errors(definition, snapshot)
                or workflow_record_sha256(snapshot) != row[7]
                or workflow_record_sha256(definition) != row[9]
                or snapshot["projectId"] != self._project
                or snapshot["workflowRunId"] != row[1]
                or len(jobs) != 1
                or jobs[0]["commandFingerprint"] != row[4]
                or jobs[0]["idempotencyKey"] != row[5]
                or row[2] != "scholarly-connector-page"
            ):
                raise CorpusProblem("corpus-connector-source-unavailable")
        except TypeError, ValueError, KeyError, AttributeError:
            raise CorpusProblem("corpus-connector-source-unavailable") from None
        return snapshot, str(row[1]), str(row[2]), str(row[3]), str(row[4]), str(row[5]), str(row[9]), str(row[0])

    def _connector_lineage(self, connection: CanonicalConnection, query_revision_id: str, accepted_job_id: str) -> None:
        original = connection.execute(
            "SELECT job_id FROM workflow_queue_jobs WHERE project_id=? AND idempotency_key=?",
            (self._project, _connector_fingerprint(["scholarly-connector-page", query_revision_id])),
        ).fetchone()
        dependency = connection.execute(
            "SELECT fingerprint FROM material_dependencies WHERE project_id=? AND output_revision_id=? "
            "AND dependency_kind='parameter-set' AND configuration_id='connector.confirmed-input' "
            "AND configuration_version='1.0.0' LIMIT 2",
            (self._project, query_revision_id),
        ).fetchall()
        if original is None or len(dependency) != 1:
            raise CorpusProblem("corpus-connector-source-unavailable")
        original_id = str(original[0])
        root = self._connector_job(connection, original_id)
        configuration = root[0].get("configuration")
        if not isinstance(configuration, dict):
            raise CorpusProblem("corpus-connector-source-unavailable")
        config_id = configuration.get("configurationId")
        if (
            not isinstance(config_id, str)
            or not config_id.startswith("connector-page." + query_revision_id + ".")
            or _TRACE.fullmatch(config_id.rsplit(".", 1)[-1]) is None
            or configuration.get("configurationHash") != dependency[0][0]
            or configuration.get("configurationVersion") != "1.0.0"
            or root[4] != dependency[0][0]
            or root[0].get("continuation") is not None
        ):
            raise CorpusProblem("corpus-connector-source-unavailable")
        current_id, seen = accepted_job_id, set()
        for _ in range(256):
            if current_id in seen:
                break
            seen.add(current_id)
            current = self._connector_job(connection, current_id)
            if current_id == original_id:
                return
            continuation = current[0].get("continuation")
            if not isinstance(continuation, dict):
                break
            parent_id = continuation.get("sourceJobId")
            if not isinstance(parent_id, str) or not is_uuid_v7(parent_id):
                break
            parent = self._connector_job(connection, parent_id)
            if (
                continuation.get("sourceWorkflowRunId") != parent[1]
                or parent[3] not in {"failed", "cancelled"}
                or current[0].get("configuration") != root[0].get("configuration")
                or current[0].get("intent") != root[0].get("intent")
                or current[0].get("policy") != root[0].get("policy")
                or current[0].get("executor") != root[0].get("executor")
                or current[6] != root[6]
                or current[4] != workflow_record_sha256({"command": "retry-as-continuation", "sourceJobId": parent_id})
            ):
                break
            current_id = parent_id
        raise CorpusProblem("corpus-connector-source-unavailable")

    def _source(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        source: SourceAssertion,
        path: DiscoveryPath,
        work_revision_id: str,
        actor: CorpusActor,
    ) -> tuple[tuple[AggregateRevision, ...], str | None]:
        try:
            source = SourceAssertion.model_validate(source)
            path = DiscoveryPath.model_validate(path)
        except ValidationError:
            raise CorpusProblem("corpus-source-mismatch") from None
        address = source.address
        if (
            source.project_id != self._project
            or path.project_id != self._project
            or path.source_revision_id != source.source_revision_id
            or (path.kind, path.context_id, path.context_revision_id, path.ordinal, path.record_key_sha256)
            != (address.kind, address.context_id, address.revision_id, address.ordinal, address.record_key)
        ):
            raise CorpusProblem("corpus-source-mismatch")
        if address.kind == "import-member":
            if source.provider != "local-import" or path.query_revision_id is not None:
                raise CorpusProblem("corpus-source-mismatch")
            match = connection.execute(
                "SELECT m.revision_id,s.revision_id FROM import_manifests m "
                "JOIN import_manifest_members mm ON mm.manifest_revision_id=m.revision_id "
                "AND mm.project_id=m.project_id AND mm.preview_id=m.preview_id "
                "AND mm.parse_attempt_id=m.parse_attempt_id "
                "JOIN import_source_records s ON s.revision_id=mm.source_record_revision_id "
                "AND s.project_id=mm.project_id AND s.source_sha256=m.source_sha256 "
                "AND s.record_key=mm.record_key AND s.preview_id=mm.preview_id "
                "AND s.parse_attempt_id=mm.parse_attempt_id AND s.ordinal=mm.ordinal "
                "WHERE m.project_id=? AND m.revision_id=? AND m.preview_id=? "
                "AND mm.ordinal=? AND mm.record_key=? AND mm.included=1 "
                "AND mm.raw_sha256=? AND s.revision_id=? LIMIT 2",
                (
                    self._project,
                    address.revision_id,
                    address.context_id,
                    address.ordinal,
                    address.record_key,
                    source.source_sha256,
                    source.source_revision_id,
                ),
            ).fetchall()
            if len(match) != 1:
                raise CorpusProblem("corpus-source-unavailable")
            revisions = (str(match[0][0]), str(match[0][1]))
        else:
            # The service has already read the protected page object through
            # ConnectorWorkerService while holding the project fence. Under the
            # writer, bind that immutable page and exact confirmed query to one
            # accepted job output. A substring mention in a manifest is never
            # sufficient authority for a source edge.
            if path.query_revision_id != address.context_id or source.source_revision_id != address.revision_id:
                raise CorpusProblem("corpus-connector-source-unavailable")
            try:
                query = aggregates.get_revision(path.query_revision_id)
                page = aggregates.get_revision(address.revision_id)
            except RepositoryNotFound:
                raise CorpusProblem("corpus-connector-source-unavailable") from None
            if (
                query.project_id != self._project
                or query.aggregate_kind != "document"
                or query.revision_id != address.context_id
                or query.object_sha256 is None
                or page.project_id != self._project
                or page.aggregate_kind != "document"
                or page.object_sha256 is None
            ):
                raise CorpusProblem("corpus-connector-source-unavailable")
            candidates = connection.execute(
                "SELECT c.job_id,c.output_manifest_json,c.output_record_sha256,j.state,j.current_attempt_id,"
                "c.attempt_id,a.state,c.idempotency_key,j.idempotency_key,"
                "c.command_fingerprint,j.command_fingerprint,j.committed_output_sha256 "
                "FROM workflow_committed_outputs c "
                "JOIN workflow_queue_jobs j ON j.job_id=c.job_id AND j.project_id=c.project_id "
                "JOIN workflow_job_attempts a ON a.attempt_id=c.attempt_id AND a.project_id=c.project_id "
                "WHERE c.project_id=? AND j.activity_type='scholarly-connector-page' "
                "AND json_valid(c.output_manifest_json) "
                "AND json_extract(c.output_manifest_json,'$.outputs[0].revisionId')=? LIMIT 257",
                (self._project, address.revision_id),
            ).fetchall()
            if not candidates or len(candidates) > 256:
                raise CorpusProblem("corpus-connector-source-unavailable")
            for (
                job_id,
                manifest_json,
                manifest_hash,
                job_state,
                current_attempt,
                committed_attempt,
                attempt_state,
                committed_key,
                job_key,
                committed_fingerprint,
                job_fingerprint,
                job_output_hash,
            ) in candidates:
                if (
                    not _connector_output_matches(str(manifest_json), str(manifest_hash), page)
                    or job_output_hash != manifest_hash
                    or job_state != "succeeded"
                    or attempt_state != "succeeded"
                    or current_attempt != committed_attempt
                    or committed_key != job_key
                    or committed_fingerprint != job_fingerprint
                ):
                    raise CorpusProblem("corpus-connector-source-unavailable")
                self._connector_lineage(connection, path.query_revision_id, str(job_id))
            revisions = (address.revision_id, path.query_revision_id)
        _, rights_revision_id = self._current_source_rights(
            connection, source, actor, work_revision_id=work_revision_id
        )
        try:
            return tuple(aggregates.get_revision(revision) for revision in dict.fromkeys(revisions)), rights_revision_id
        except RepositoryNotFound:
            raise CorpusProblem("corpus-source-unavailable") from None

    def _current_source_rights(
        self,
        connection: CanonicalConnection,
        source: SourceAssertion,
        actor: CorpusActor,
        *,
        work_revision_id: str | None = None,
    ) -> tuple[str, str | None]:
        """Check the exact metadata copy under the caller's protected action."""

        rights = SqliteRightsRepository(self._database, self._project)
        try:
            subject = rights.source_metadata_subject_with_connection(connection, source)
            if work_revision_id is not None:
                matched = connection.execute(
                    "SELECT 1 FROM reconciliation_work_members WHERE project_id=? "
                    "AND work_revision_id=? AND assertion_revision_id=? LIMIT 2",
                    (self._project, work_revision_id, subject.source_assertion_revision_id),
                ).fetchall()
                if len(matched) != 1:
                    raise CorpusProblem("corpus-source-work-mismatch")
            policy = rights.current_with_connection(connection, subject)
            if policy is None:
                # The protected evaluator applies T01's exact import bridge to
                # both public inspection and corpus use, with the same audit.
                for action in _CORPUS_RIGHTS_ACTIONS:
                    decision = rights.evaluate_with_connection(
                        connection,
                        RightsRequest(
                            actor_id=actor.actor_id,
                            subject=subject,
                            use=RightsUse(
                                action=action,
                                purpose="corpus-membership",
                                destination_kind="local-project",
                            ),
                        ),
                        actor=actor,
                    )
                    if decision.code != "allow" or decision.authority_kind != "legacy-import-bridge":
                        raise _RightsUseDenied(decision, actor)
                return subject.source_assertion_revision_id, None
            for action in _CORPUS_RIGHTS_ACTIONS:
                decision = rights.evaluate_with_connection(
                    connection,
                    RightsRequest(
                        actor_id=actor.actor_id,
                        subject=subject,
                        use=RightsUse(action=action, purpose="corpus-membership", destination_kind="local-project"),
                    ),
                    actor=actor,
                )
                if decision.code != "allow" or decision.policy_revision_id != policy.revision_id:
                    raise _RightsUseDenied(decision, actor)
            return subject.source_assertion_revision_id, policy.revision_id
        except RightsProblem as error:
            if "integrity" in error.code or error.code == "rights-storage-invalid":
                raise CorpusProblem("corpus-rights-integrity-invalid") from None
            raise CorpusProblem("corpus-rights-denied") from None

    def _evidence(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        current: CorpusItemRevision,
        decision: CorpusDecision,
        actor: CorpusActor,
        *,
        added_path: DiscoveryPath | None = None,
    ) -> tuple[AggregateRevision, ...]:
        if (
            decision.project_id != self._project
            or decision.actor_id != actor.actor_id
            or decision.protocol_revision_id != actor.intent_revision_id
            or decision.occurred_at != actor.occurred_at
        ):
            raise CorpusProblem("corpus-decision-authority-invalid")
        linked = {current.work_revision_id}
        paths = connection.execute(
            "SELECT p.source_revision_id,p.context_revision_id FROM corpus_item_discovery_paths a "
            "JOIN corpus_discovery_paths p ON p.path_id=a.path_id AND p.project_id=a.project_id "
            "WHERE a.project_id=? AND a.item_id=? AND a.revision_id=?",
            (self._project, current.item_id, current.revision_id),
        ).fetchall()
        linked.update(value for row in paths for value in row)
        linked.update(
            str(row[0])
            for row in connection.execute(
                "SELECT assertion_revision_id FROM reconciliation_work_members WHERE project_id=? "
                "AND work_revision_id=?",
                (self._project, current.work_revision_id),
            )
        )
        if added_path is not None:
            linked.update((added_path.source_revision_id, added_path.context_revision_id))
        if decision.dimension == "work-reference":
            linked.add(decision.next_value)
        if decision.dimension == "duplicate" and decision.next_value != "none":
            try:
                target = aggregates.get(decision.next_value)
            except RepositoryNotFound:
                raise CorpusProblem("corpus-duplicate-target-unavailable") from None
            if target.project_id != self._project or target.aggregate_kind != "corpus-item":
                raise CorpusProblem("corpus-duplicate-target-unavailable")
            linked.add(target.revision_id)
        revisions: list[AggregateRevision] = []
        for revision_id in decision.evidence_revision_ids:
            if revision_id not in linked:
                raise CorpusProblem("corpus-evidence-unrelated")
            try:
                revision = aggregates.get_revision(revision_id)
            except RepositoryNotFound:
                raise CorpusProblem("corpus-evidence-unavailable") from None
            if revision.project_id != self._project:
                raise CorpusProblem("corpus-evidence-unavailable")
            revisions.append(revision)
        return tuple(revisions)

    def _append(
        self,
        aggregates: _SqliteAggregateRepository,
        item: CorpusItemRevision,
        actor: CorpusActor,
        command_id: str,
        command_sha256: str,
        *,
        current: AggregateRevision | None,
        inputs: tuple[AggregateRevision, ...],
        rights_revision_id: str | None = None,
    ) -> tuple[AggregateRevision, AtomicRepositoryEvent]:
        # The common repository records a complete provenance/ledger/outbox
        # fact and typed dependency registration before returning.
        if encode_corpus_item_revision(item.model_dump(mode="json", by_alias=True)) is None:
            raise CorpusProblem("corpus-contract-invalid")
        sources = tuple(
            {value.revision_id: value for value in inputs if value.revision_id != item.revision_id}.values()
        )
        if len(sources) > 64:
            raise CorpusProblem("corpus-evidence-limit")
        if rights_revision_id is not None and not any(
            value.revision_id == rights_revision_id and value.aggregate_kind == "decision" for value in sources
        ):
            raise CorpusProblem("corpus-rights-integrity-invalid")
        dependencies = tuple(
            MaterialDependency(
                new_uuid_v7(),
                "human-decision" if value.revision_id == rights_revision_id else "source-revision",
                "direct",
                value.revision_id,
                None,
                None,
                _projection_content_sha256(value),
                "dependency.material.v1",
                "1.0.0",
            )
            for value in sources
        ) + tuple(
            MaterialDependency(
                new_uuid_v7(),
                "parameter-set",
                "direct",
                None,
                "corpus." + name,
                "1.0.0",
                "sha256:" + digest,
                "dependency.material.v1",
                "1.0.0",
            )
            for name, digest in (
                ("command", command_sha256),
                ("current-intent", actor.intent_sha256),
                ("current-privacy", actor.policy_sha256),
            )
        )
        event = AtomicRepositoryEvent(
            event_id=new_uuid_v7(),
            outbox_id=new_uuid_v7(),
            event_type="corpus.created" if current is None else "corpus.revised",
            occurred_at=actor.occurred_at,
            available_at=actor.occurred_at,
            trace_id=actor.trace_id,
            actor_type="human",
            actor_id=actor.actor_id,
            idempotency_key="corpus-" + command_id,
        )
        revision = aggregates.append(
            AggregateRevisionDraft(
                revision_id=item.revision_id,
                aggregate_id=item.item_id,
                aggregate_kind="corpus-item",
                created_at=current.created_at if current is not None else actor.occurred_at,
                modified_at=actor.occurred_at,
                display_label_observed="Corpus item",
                display_label_normalized=None,
                knowledge_status="observed" if current is None else "adjudicated",
                rights_status="unknown",
                dependency_coverage="complete",
                provenance_inputs=sources,
                material_dependencies=dependencies,
            ),
            event,
            expected_revision=current.revision if current is not None else None,
        )
        if revision.revision_id != item.revision_id or revision.aggregate_id != item.item_id:
            raise CorpusProblem("corpus-aggregate-integrity-invalid")
        _publication_step("aggregate-created")
        return revision, event

    def _write_path(self, connection: CanonicalConnection, path: DiscoveryPath) -> None:
        if encode_discovery_path(path.model_dump(mode="json", by_alias=True)) is None:
            raise CorpusProblem("corpus-contract-invalid")
        connection.execute(
            "INSERT INTO corpus_discovery_paths (path_id,project_id,item_id,kind,source_revision_id,"
            "direction,occurred_at,predecessor_item_revision_id,"
            "context_id,context_revision_id,ordinal,record_key_sha256,query_revision_id,"
            "citing_work_revision_id,recommendation_revision_id,manual_decision_revision_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                path.path_id,
                path.project_id,
                path.item_id,
                path.kind,
                path.source_revision_id,
                path.direction,
                path.occurred_at,
                path.predecessor_item_revision_id,
                path.context_id,
                path.context_revision_id,
                path.ordinal,
                path.record_key_sha256,
                path.query_revision_id,
                path.citing_work_revision_id,
                path.recommendation_revision_id,
                path.manual_decision_revision_id,
            ),
        )
        _publication_step("path-created")

    def _write_state(self, connection: CanonicalConnection, item: CorpusItemRevision) -> None:
        connection.execute(
            "INSERT INTO corpus_item_states (revision_id,project_id,item_id,previous_revision_id,work_id,"
            "work_revision_id,membership,review,duplicate_of_item_id,availability,"
            "primary_discovery_path_id,discovery_fingerprint,decision_revision_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item.revision_id,
                item.project_id,
                item.item_id,
                item.previous_revision_id,
                item.work_id,
                item.work_revision_id,
                item.membership,
                item.review,
                item.duplicate_of_item_id,
                item.availability,
                item.discovery_path_ids[0],
                item.discovery_fingerprint,
                item.decision_revision_id,
            ),
        )
        for path_id in item.discovery_path_ids:
            connection.execute(
                "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) VALUES (?,?,?,?)",
                (item.revision_id, item.project_id, item.item_id, path_id),
            )
        try:
            apply_source_projection(
                connection,
                self._project,
                item.item_id,
                item.revision_id,
                item.previous_revision_id,
                item.work_revision_id,
            )
        except SourceProjectionProblem:
            raise CorpusProblem("corpus-source-projection-integrity-invalid") from None
        _publication_step("source-projection-updated")
        _publication_step("state-created")

    def _write_decision(self, connection: CanonicalConnection, decision: CorpusDecision) -> None:
        prior = connection.execute(
            "SELECT d.decision_id FROM corpus_decisions d JOIN aggregate_revisions r "
            "ON r.revision_id=d.next_revision_id AND r.project_id=d.project_id "
            "AND r.aggregate_id=d.item_id WHERE d.project_id=? AND d.item_id=? AND d.dimension=? "
            "ORDER BY r.revision DESC LIMIT 1",
            (self._project, decision.item_id, decision.dimension),
        ).fetchone()
        superseded_id = str(prior[0]) if prior is not None else None
        if decision.supersedes_decision_revision_id not in (None, superseded_id):
            raise CorpusProblem("corpus-decision-supersession-invalid")
        decision = CorpusDecision.model_validate(
            decision.model_copy(update={"supersedes_decision_revision_id": superseded_id})
        )
        if encode_corpus_decision(decision.model_dump(mode="json", by_alias=True)) is None:
            raise CorpusProblem("corpus-contract-invalid")
        connection.execute(
            "INSERT INTO corpus_decisions (decision_id,project_id,item_id,previous_revision_id,"
            "next_revision_id,dimension,command,previous_value,next_value,"
            "previous_decision_revision_id,supersedes_decision_revision_id,next_work_id,actor_id,"
            "reason_code,protocol_revision_id,occurred_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision.decision_id,
                decision.project_id,
                decision.item_id,
                decision.previous_revision_id,
                decision.next_revision_id,
                decision.dimension,
                decision.command,
                decision.previous_value,
                decision.next_value,
                decision.previous_decision_revision_id,
                decision.supersedes_decision_revision_id,
                decision.next_work_id,
                decision.actor_id,
                decision.reason_code,
                decision.protocol_revision_id,
                decision.occurred_at,
            ),
        )
        for evidence_id in decision.evidence_revision_ids:
            connection.execute(
                "INSERT INTO corpus_decision_evidence (decision_id,evidence_revision_id) VALUES (?,?)",
                (decision.decision_id, evidence_id),
            )
        _publication_step("decision-created")

    def _write_command(
        self,
        connection: CanonicalConnection,
        command_id: str,
        command_sha256: str,
        item: CorpusItemRevision,
        event: AtomicRepositoryEvent,
        *,
        path_id: str | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO corpus_commands (project_id,command_id,semantic_sha256,result_item_id,"
            "result_revision_id,result_path_id,result_decision_id,provenance_event_id,outbox_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                self._project,
                command_id,
                command_sha256,
                item.item_id,
                item.revision_id,
                path_id,
                item.decision_revision_id,
                event.event_id,
                event.outbox_id,
            ),
        )
        _publication_step("command-created")

    def create(
        self,
        *,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        source: SourceAssertion,
        build: Callable[[], tuple[CorpusItemRevision, DiscoveryPath]],
    ) -> CorpusItemRevision:
        self._command(command_id, command_sha256, actor)
        with self._transaction(write=True) as (connection, aggregates):
            self._authority(connection, actor)
            replay = self._replay(connection, command_id, command_sha256)
            if replay is not None:
                return replay
            item, path = build()
            try:
                item, path = CorpusItemRevision.model_validate(item), DiscoveryPath.model_validate(path)
            except ValidationError:
                raise CorpusProblem("corpus-item-invalid") from None
            if (
                item.project_id != self._project
                or path.item_id != item.item_id
                or item.previous_revision_id is not None
                or item.membership != "candidate"
                or item.review != "pending"
                or item.duplicate_of_item_id is not None
                or item.availability != "unknown"
                or item.decision_revision_id is not None
                or path.predecessor_item_revision_id is not None
                or path.occurred_at != actor.occurred_at
                or item.discovery_path_ids != (path.path_id,)
            ):
                raise CorpusProblem("corpus-item-invalid")
            work = self._work(connection, aggregates, item.work_id, item.work_revision_id)
            sources, rights_revision_id = self._source(
                connection, aggregates, source, path, item.work_revision_id, actor
            )
            rights_input = (aggregates.get_revision(rights_revision_id),) if rights_revision_id is not None else ()
            _, event = self._append(
                aggregates,
                item,
                actor,
                command_id,
                command_sha256,
                current=None,
                inputs=(work, *sources, *rights_input),
                rights_revision_id=rights_revision_id,
            )
            self._write_path(connection, path)
            self._write_state(connection, item)
            self._write_command(connection, command_id, command_sha256, item, event, path_id=path.path_id)
            return item

    def _citation_assertion(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        citing_work_id: str,
        citing_work_revision_id: str,
        source_assertion_revision_id: str,
        actor: CorpusActor,
    ) -> tuple[AggregateRevision, AggregateRevision, str | None]:
        citing_work = self._work(connection, aggregates, citing_work_id, citing_work_revision_id)
        retained_rows = connection.execute(
            "SELECT a.assertion_json,a.source_revision_id,a.address_revision_id "
            "FROM reconciliation_work_members wm JOIN reconciliation_assertions a "
            "ON a.revision_id=wm.assertion_revision_id AND a.project_id=wm.project_id "
            "WHERE wm.project_id=? AND wm.work_revision_id=? AND a.revision_id=? LIMIT 2",
            (self._project, citing_work_revision_id, source_assertion_revision_id),
        ).fetchall()
        if len(retained_rows) != 1:
            raise CorpusProblem("corpus-citation-source-unavailable")
        try:
            retained = SourceAssertion.model_validate_json(retained_rows[0][0])
        except ValidationError:
            raise CorpusProblem("corpus-citation-source-unavailable") from None
        if (
            retained.project_id != self._project
            or retained.source_revision_id != retained_rows[0][1]
            or retained.address.revision_id != retained_rows[0][2]
        ):
            raise CorpusProblem("corpus-citation-source-unavailable")
        exact_assertion_id, rights_revision_id = self._current_source_rights(connection, retained, actor)
        if exact_assertion_id != source_assertion_revision_id:
            raise CorpusProblem("corpus-citation-source-mismatch")
        try:
            assertion = aggregates.get_revision(source_assertion_revision_id)
        except RepositoryNotFound:
            raise CorpusProblem("corpus-citation-source-unavailable") from None
        if assertion.project_id != self._project or assertion.aggregate_kind != "record":
            raise CorpusProblem("corpus-citation-source-unavailable")
        return citing_work, assertion, rights_revision_id

    def create_citation(
        self,
        *,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        work_id: str,
        work_revision_id: str,
        citing_work_id: str,
        citing_work_revision_id: str,
        source_assertion_revision_id: str,
        build: Callable[[], tuple[CorpusItemRevision, DiscoveryPath]],
    ) -> CorpusItemRevision:
        """Create a candidate from human-attested citation lineage, not a verified citation fact."""

        self._command(command_id, command_sha256, actor)
        if any(
            not is_uuid_v7(value)
            for value in (
                work_id,
                work_revision_id,
                citing_work_id,
                citing_work_revision_id,
                source_assertion_revision_id,
            )
        ):
            raise CorpusProblem("corpus-command-invalid")
        with self._transaction(write=True) as (connection, aggregates):
            self._authority(connection, actor)
            replay = self._replay(connection, command_id, command_sha256)
            if replay is not None:
                path = connection.execute(
                    "SELECT p.kind,p.source_revision_id,p.context_id,p.context_revision_id "
                    "FROM corpus_commands c JOIN corpus_discovery_paths p ON p.path_id=c.result_path_id "
                    "AND p.project_id=c.project_id AND p.item_id=c.result_item_id "
                    "WHERE c.project_id=? AND c.command_id=?",
                    (self._project, command_id),
                ).fetchone()
                if (
                    (replay.work_id, replay.work_revision_id, replay.previous_revision_id)
                    != (work_id, work_revision_id, None)
                    or path is None
                    or tuple(path)
                    != ("citation", source_assertion_revision_id, citing_work_id, citing_work_revision_id)
                ):
                    raise CorpusProblem("corpus-command-conflict")
                return replay
            if work_id == citing_work_id:
                raise CorpusProblem("corpus-citation-self-invalid")
            target_work = self._work(connection, aggregates, work_id, work_revision_id)
            citing_work, assertion, rights_revision_id = self._citation_assertion(
                connection, aggregates, citing_work_id, citing_work_revision_id, source_assertion_revision_id, actor
            )
            rights_input = (aggregates.get_revision(rights_revision_id),) if rights_revision_id is not None else ()
            item, path = build()
            try:
                item, path = CorpusItemRevision.model_validate(item), DiscoveryPath.model_validate(path)
            except ValidationError:
                raise CorpusProblem("corpus-item-invalid") from None
            if (
                item.project_id != self._project
                or item.work_id != work_id
                or item.work_revision_id != work_revision_id
                or item.previous_revision_id is not None
                or item.membership != "candidate"
                or item.review != "pending"
                or item.duplicate_of_item_id is not None
                or item.availability != "unknown"
                or item.decision_revision_id is not None
                or item.discovery_path_ids != (path.path_id,)
                or path.project_id != self._project
                or path.item_id != item.item_id
                or path.kind != "citation"
                or path.source_revision_id != source_assertion_revision_id
                or path.context_id != citing_work_id
                or path.context_revision_id != citing_work_revision_id
                or path.citing_work_revision_id != citing_work_revision_id
                or path.predecessor_item_revision_id is not None
                or path.occurred_at != actor.occurred_at
            ):
                raise CorpusProblem("corpus-citation-source-mismatch")
            _, event = self._append(
                aggregates,
                item,
                actor,
                command_id,
                command_sha256,
                current=None,
                inputs=(target_work, citing_work, assertion, *rights_input),
                rights_revision_id=rights_revision_id,
            )
            self._write_path(connection, path)
            self._write_state(connection, item)
            self._write_command(connection, command_id, command_sha256, item, event, path_id=path.path_id)
            return item

    def _change(
        self,
        item_id: str,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        build: Callable[[CorpusItemRevision], CorpusDecision],
        kind: Literal["decide", "rebind"],
    ) -> CorpusItemRevision:
        self._command(command_id, command_sha256, actor)
        if not is_uuid_v7(item_id) or not is_uuid_v7(expected_revision_id):
            raise CorpusProblem("corpus-command-invalid")
        with self._transaction(write=True) as (connection, aggregates):
            self._authority(connection, actor)
            replay = self._replay(connection, command_id, command_sha256)
            if replay is not None:
                if replay.item_id != item_id:
                    raise CorpusProblem("corpus-command-conflict")
                return replay
            current, previous = self._current(connection, aggregates, item_id)
            if current.revision_id != expected_revision_id:
                raise CorpusProblem("corpus-predecessor-stale")
            try:
                decision = CorpusDecision.model_validate(build(current))
            except ValidationError:
                raise CorpusProblem("corpus-decision-invalid") from None
            evidence = self._evidence(connection, aggregates, current, decision, actor)
            item = apply_decision(current, decision) if kind == "decide" else rebind_work(current, decision)
            work = self._work(connection, aggregates, item.work_id, item.work_revision_id)
            _, event = self._append(
                aggregates, item, actor, command_id, command_sha256, current=previous, inputs=(work, *evidence)
            )
            self._write_state(connection, item)
            self._write_decision(connection, decision)
            self._write_command(connection, command_id, command_sha256, item, event)
            return item

    def decide(
        self,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        build: Callable[[CorpusItemRevision], CorpusDecision],
    ) -> CorpusItemRevision:
        return self._change(item_id, expected_revision_id, command_id, command_sha256, actor, build, "decide")

    def rebind(
        self,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        build: Callable[[CorpusItemRevision], CorpusDecision],
    ) -> CorpusItemRevision:
        return self._change(item_id, expected_revision_id, command_id, command_sha256, actor, build, "rebind")

    def add_path(
        self,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        source: SourceAssertion,
        build: Callable[[CorpusItemRevision], tuple[DiscoveryPath, CorpusDecision]],
    ) -> CorpusItemRevision:
        self._command(command_id, command_sha256, actor)
        if not is_uuid_v7(item_id) or not is_uuid_v7(expected_revision_id):
            raise CorpusProblem("corpus-command-invalid")
        with self._transaction(write=True) as (connection, aggregates):
            self._authority(connection, actor)
            replay = self._replay(connection, command_id, command_sha256)
            if replay is not None:
                if replay.item_id != item_id:
                    raise CorpusProblem("corpus-command-conflict")
                return replay
            current, previous = self._current(connection, aggregates, item_id)
            if current.revision_id != expected_revision_id:
                raise CorpusProblem("corpus-predecessor-stale")
            path, decision = build(current)
            try:
                path, decision = DiscoveryPath.model_validate(path), CorpusDecision.model_validate(decision)
            except ValidationError:
                raise CorpusProblem("corpus-discovery-invalid") from None
            evidence = self._evidence(connection, aggregates, current, decision, actor, added_path=path)
            item = append_discovery_path(current, path, decision)
            work = self._work(connection, aggregates, item.work_id, item.work_revision_id)
            sources, rights_revision_id = self._source(
                connection, aggregates, source, path, item.work_revision_id, actor
            )
            rights_input = (aggregates.get_revision(rights_revision_id),) if rights_revision_id is not None else ()
            _, event = self._append(
                aggregates,
                item,
                actor,
                command_id,
                command_sha256,
                current=previous,
                inputs=(work, *sources, *rights_input, *evidence),
                rights_revision_id=rights_revision_id,
            )
            self._write_path(connection, path)
            self._write_state(connection, item)
            self._write_decision(connection, decision)
            self._write_command(connection, command_id, command_sha256, item, event, path_id=path.path_id)
            return item

    def add_citation_path(
        self,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        citing_work_id: str,
        citing_work_revision_id: str,
        source_assertion_revision_id: str,
        build: Callable[[CorpusItemRevision], tuple[DiscoveryPath, CorpusDecision]],
    ) -> CorpusItemRevision:
        """Publish a researcher-attested discovery route, not a verified citation edge."""

        self._command(command_id, command_sha256, actor)
        if any(
            not is_uuid_v7(value)
            for value in (
                item_id,
                expected_revision_id,
                citing_work_id,
                citing_work_revision_id,
                source_assertion_revision_id,
            )
        ):
            raise CorpusProblem("corpus-command-invalid")
        with self._transaction(write=True) as (connection, aggregates):
            self._authority(connection, actor)
            replay = self._replay(connection, command_id, command_sha256)
            if replay is not None:
                if replay.item_id != item_id:
                    raise CorpusProblem("corpus-command-conflict")
                return replay
            current, previous = self._current(connection, aggregates, item_id)
            if current.revision_id != expected_revision_id:
                raise CorpusProblem("corpus-predecessor-stale")
            target_work = self._work(connection, aggregates, current.work_id, current.work_revision_id)
            if citing_work_id == current.work_id:
                raise CorpusProblem("corpus-citation-self-invalid")
            citing_work, assertion, rights_revision_id = self._citation_assertion(
                connection, aggregates, citing_work_id, citing_work_revision_id, source_assertion_revision_id, actor
            )
            rights_input = (aggregates.get_revision(rights_revision_id),) if rights_revision_id is not None else ()
            path, decision = build(current)
            try:
                path, decision = DiscoveryPath.model_validate(path), CorpusDecision.model_validate(decision)
            except ValidationError:
                raise CorpusProblem("corpus-citation-source-mismatch") from None
            if (
                path.project_id != self._project
                or path.item_id != item_id
                or path.kind != "citation"
                or path.source_revision_id != source_assertion_revision_id
                or path.context_id != citing_work_id
                or path.context_revision_id != citing_work_revision_id
                or path.citing_work_revision_id != citing_work_revision_id
                or source_assertion_revision_id not in decision.evidence_revision_ids
            ):
                raise CorpusProblem("corpus-citation-source-mismatch")
            evidence = self._evidence(connection, aggregates, current, decision, actor, added_path=path)
            item = append_discovery_path(current, path, decision)
            _, event = self._append(
                aggregates,
                item,
                actor,
                command_id,
                command_sha256,
                current=previous,
                inputs=(target_work, citing_work, assertion, *rights_input, *evidence),
                rights_revision_id=rights_revision_id,
            )
            self._write_path(connection, path)
            self._write_state(connection, item)
            self._write_decision(connection, decision)
            self._write_command(connection, command_id, command_sha256, item, event, path_id=path.path_id)
            return item

    def inspect(self, item_id: str, *, actor: CorpusActor) -> CorpusItemRevision:
        if not is_uuid_v7(item_id):
            raise CorpusProblem("corpus-item-invalid")
        self._command(new_uuid_v7(), "0" * 64, actor)
        with self._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
            return self._load(connection, item_id)

    def history(
        self, item_id: str, *, actor: CorpusActor
    ) -> tuple[tuple[CorpusItemRevision, tuple[DiscoveryPath, ...], CorpusDecision | None], ...]:
        """Read the exact protected entry and decision chain, oldest first."""

        if not is_uuid_v7(item_id):
            raise CorpusProblem("corpus-item-invalid")
        self._command(new_uuid_v7(), "0" * 64, actor)
        with self._transaction(write=False) as (connection, aggregates):
            self._authority(connection, actor)
            current, _ = self._current(connection, aggregates, item_id)
            revisions = connection.execute(
                "SELECT r.revision_id FROM aggregate_revisions r "
                "JOIN corpus_item_states s ON s.revision_id=r.revision_id "
                "AND s.project_id=r.project_id AND s.item_id=r.aggregate_id "
                "WHERE r.project_id=? AND r.aggregate_id=? AND r.aggregate_kind='corpus-item' "
                "ORDER BY r.revision LIMIT 10001",
                (self._project, item_id),
            ).fetchall()
            if not revisions or len(revisions) > 10000 or revisions[-1][0] != current.revision_id:
                raise CorpusProblem("corpus-history-integrity-invalid")
            result: list[tuple[CorpusItemRevision, tuple[DiscoveryPath, ...], CorpusDecision | None]] = []
            previous: CorpusItemRevision | None = None
            for (revision_id,) in revisions:
                item = self._load(connection, item_id, revision_id=str(revision_id))
                path_rows = connection.execute(
                    "SELECT p.path_id,p.project_id,p.item_id,p.kind,p.source_revision_id,"
                    "p.direction,p.occurred_at,p.predecessor_item_revision_id,"
                    "p.context_id,p.context_revision_id,p.ordinal,p.record_key_sha256,"
                    "p.query_revision_id,p.citing_work_revision_id,p.recommendation_revision_id,"
                    "p.manual_decision_revision_id FROM corpus_item_discovery_paths a "
                    "JOIN corpus_discovery_paths p ON p.path_id=a.path_id AND p.project_id=a.project_id "
                    "AND p.item_id=a.item_id WHERE a.project_id=? AND a.item_id=? AND a.revision_id=? "
                    "ORDER BY p.path_id LIMIT 1001",
                    (self._project, item_id, revision_id),
                ).fetchall()
                try:
                    paths = tuple(
                        DiscoveryPath.model_validate(
                            dict(
                                zip(
                                    (
                                        "path_id",
                                        "project_id",
                                        "item_id",
                                        "kind",
                                        "source_revision_id",
                                        "direction",
                                        "occurred_at",
                                        "predecessor_item_revision_id",
                                        "context_id",
                                        "context_revision_id",
                                        "ordinal",
                                        "record_key_sha256",
                                        "query_revision_id",
                                        "citing_work_revision_id",
                                        "recommendation_revision_id",
                                        "manual_decision_revision_id",
                                    ),
                                    row,
                                    strict=True,
                                )
                            )
                        )
                        for row in path_rows
                    )
                except ValidationError:
                    raise CorpusProblem("corpus-history-integrity-invalid") from None
                if tuple(path.path_id for path in paths) != item.discovery_path_ids:
                    raise CorpusProblem("corpus-history-integrity-invalid")
                decision: CorpusDecision | None = None
                if previous is None:
                    if item.previous_revision_id is not None or item.decision_revision_id is not None:
                        raise CorpusProblem("corpus-history-integrity-invalid")
                    origin = aggregates.get_revision(item.revision_id)
                    if (
                        len(paths) != 1
                        or paths[0].predecessor_item_revision_id is not None
                        or paths[0].occurred_at != origin.created_at
                    ):
                        raise CorpusProblem("corpus-history-integrity-invalid")
                else:
                    if item.previous_revision_id != previous.revision_id or item.decision_revision_id is None:
                        raise CorpusProblem("corpus-history-integrity-invalid")
                    row = connection.execute(
                        "SELECT decision_id,project_id,item_id,previous_revision_id,next_revision_id,"
                        "dimension,command,previous_value,next_value,previous_decision_revision_id,"
                        "supersedes_decision_revision_id,next_work_id,actor_id,reason_code,"
                        "protocol_revision_id,occurred_at FROM corpus_decisions "
                        "WHERE decision_id=? AND project_id=? AND item_id=?",
                        (item.decision_revision_id, self._project, item_id),
                    ).fetchone()
                    if row is None:
                        raise CorpusProblem("corpus-history-integrity-invalid")
                    evidence = tuple(
                        str(e[0])
                        for e in connection.execute(
                            "SELECT evidence_revision_id FROM corpus_decision_evidence "
                            "WHERE decision_id=? ORDER BY evidence_revision_id LIMIT 65",
                            (item.decision_revision_id,),
                        )
                    )
                    try:
                        decision = CorpusDecision.model_validate(
                            dict(
                                zip(
                                    (
                                        "decision_id",
                                        "project_id",
                                        "item_id",
                                        "previous_revision_id",
                                        "next_revision_id",
                                        "dimension",
                                        "command",
                                        "previous_value",
                                        "next_value",
                                        "previous_decision_revision_id",
                                        "supersedes_decision_revision_id",
                                        "next_work_id",
                                        "actor_id",
                                        "reason_code",
                                        "protocol_revision_id",
                                        "occurred_at",
                                    ),
                                    row,
                                    strict=True,
                                )
                            )
                            | {"evidence_revision_ids": evidence}
                        )
                    except ValidationError:
                        raise CorpusProblem("corpus-history-integrity-invalid") from None
                    if decision.next_revision_id != item.revision_id:
                        raise CorpusProblem("corpus-history-integrity-invalid")
                    if decision.dimension == "discovery":
                        additions = set(item.discovery_path_ids) - set(previous.discovery_path_ids)
                        if len(additions) != 1:
                            raise CorpusProblem("corpus-history-integrity-invalid")
                        path = next(path for path in paths if path.path_id in additions)
                        expected = append_discovery_path(previous, path, decision)
                    elif decision.dimension == "work-reference":
                        expected = rebind_work(previous, decision)
                    else:
                        expected = apply_decision(previous, decision)
                    if expected != item:
                        raise CorpusProblem("corpus-history-integrity-invalid")
                result.append((item, paths, decision))
                previous = item
            return tuple(result)
