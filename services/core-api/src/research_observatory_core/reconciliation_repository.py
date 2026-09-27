"""Atomic scholarly assertions and Work revisions in the canonical database.

The caller holds the current project lifecycle/authority fence. No caller DTO
is a trusted SourceAssertion: every source and candidate is resolved again in
the authority-fenced snapshot before publication, replay or inspection.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.reconciliation import ReconciliationActor, ReconciliationSourceResolver
from .ports.repositories import (
    DEFAULT_DEPENDENCY_IMPACT_LIMITS,
    AggregateKind,
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyChange,
    MaterialDependency,
    RepositoryConflict,
    RepositoryProblem,
)
from .ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference
from .reconciliation.batch import (
    MAX_AUTHORIZED_BYTES,
    MAX_AUTHORIZED_SOURCES,
    MAX_CANDIDATE_BYTES,
    SOURCE_ACTIVITIES,
    BatchInput,
)
from .reconciliation.candidate_sets import CandidateExplanation, CandidateMember, CandidateSetContent, content_digest
from .reconciliation.candidate_views import CandidatePage
from .reconciliation.candidates import DEFAULT_CONFIG, FEATURE_VERSION, PreparedRecord, generate_prepared_candidates
from .reconciliation.contracts import (
    CanonicalFieldSelection,
    CanonicalWorkReference,
    FieldObservation,
    ReconciliationInspection,
    ReconciliationProblem,
    ReconciliationResult,
    SourceAddress,
    SourceAssertion,
)
from .reconciliation.decisions import (
    ReviewCommand,
    ReviewContext,
    ReviewOutcome,
    ReviewPlan,
    ReviewPreview,
    ReviewSource,
    WorkState,
)
from .reconciliation.exact import IdentifierAssertion, MatchAssessment, assess_match, exact_keys, select_field
from .reconciliation.feature_cache import FeatureSnapshot
from .reconciliation.identifiers import NORMALIZER_VERSION
from .reconciliation.workflow import bind_batch_claim
from .repositories import (
    _UNIT_OF_WORKS,
    _projection_content_sha256,
    _SqliteAggregateRepository,
    _SqliteDependencyImpactRepository,
    _SqliteWorkflowQueueRepository,
)
from .storage import (
    _DATABASE_ERRORS,
    CanonicalConnection,
    StorageProblem,
    _normalize_utc_millisecond,
    open_canonical_database,
)

_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_MAX_SOURCE_COUNT = 512
_IMPACT_SNAPSHOT_COLUMNS = (
    "run_id,project_id,change_id,idempotency_key,reason,dependency_kind,previous_revision_id,replacement_revision_id,"
    "configuration_id,previous_configuration_version,replacement_configuration_version,previous_fingerprint,"
    "replacement_fingerprint,propagation_policy_id,propagation_policy_version,actor_id,trace_id,occurred_at,"
    "graph_sha256,preview_sha256,authority_sha256,batch_size,total_items,max_nodes,max_edges,max_depth,"
    "max_path_samples,max_legacy_samples,created_at"
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _payload(source: SourceAssertion) -> str:
    return _digest(source.model_dump(mode="json", by_alias=True))


def _publication_step(_step: str) -> None:
    """Deterministic transaction failure seam; not a production retry mechanism."""


def _keys(assertions: tuple[IdentifierAssertion, ...]) -> frozenset[tuple[str, str]]:
    # Disputed/reassigned keys must remain findable as blockers. This projection
    # never changes the stored verification state or authorizes exact linking.
    return exact_keys(
        tuple(
            item.model_copy(update={"verification_state": "unverified", "reassignment_observed": False})
            for item in assertions
        )
    )


class SqliteReconciliationRepository:
    def __init__(self, database: Path, project_id: str):
        if not database.is_absolute():
            raise ReconciliationProblem("reconciliation-storage-invalid")
        self._database, self._project = database, project_id

    @contextmanager
    def _transaction(self, *, write: bool) -> Iterator[tuple[CanonicalConnection, _SqliteAggregateRepository]]:
        connection, token = None, None
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project)
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            token = _UNIT_OF_WORKS.register(connection, self._project)
            yield connection, _SqliteAggregateRepository(token)
            connection.execute("COMMIT")
        except (*_DATABASE_ERRORS, StorageProblem, RepositoryProblem, ValueError, TypeError, OSError):
            raise ReconciliationProblem("reconciliation-storage-invalid") from None
        finally:
            if token is not None:
                _UNIT_OF_WORKS.unregister(token)
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def _resolve(self, address: SourceAddress, resolve: ReconciliationSourceResolver) -> SourceAssertion:
        source = SourceAssertion.model_validate(resolve(address))
        if source.project_id != self._project or source.address != address:
            raise ReconciliationProblem("reconciliation-source-mismatch")
        if not all(source.rights.permits(action) for action in ("store", "inspect", "derive", "index")):
            raise ReconciliationProblem("reconciliation-rights-denied")
        return source

    def _batch_request(self, connection: CanonicalConnection, request_id: str) -> BatchInput | None:
        if not is_uuid_v7(request_id):
            raise ReconciliationProblem("reconciliation-batch-request-invalid")
        rows = connection.execute(
            "SELECT revision,value_type,text_value FROM settings WHERE project_id=? AND setting_key=? LIMIT 2",
            (self._project, "reconciliation.batch-request." + request_id),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1 or tuple(rows[0][:2]) != (0, "text") or len(rows[0][2].encode()) > 65536:
            raise ReconciliationProblem("reconciliation-batch-request-invalid")
        inputs = BatchInput.model_validate_json(rows[0][2])
        if inputs.project_id != self._project or inputs.request_id != request_id:
            raise ReconciliationProblem("reconciliation-batch-request-invalid")
        return inputs

    def batch_request(self, request_id: str) -> BatchInput | None:
        with self._transaction(write=False) as (connection, _):
            return self._batch_request(connection, request_id)

    def save_batch_request(self, inputs: BatchInput, *, actor: ReconciliationActor) -> BatchInput:
        inputs = BatchInput.model_validate(inputs)
        self._validate_actor(actor)
        if (inputs.project_id, inputs.actor_id, inputs.intent.content_hash, inputs.policy_sha256) != (
            self._project,
            actor.actor_id,
            "sha256:" + actor.intent_sha256,
            "sha256:" + actor.policy_sha256,
        ):
            raise ReconciliationProblem("reconciliation-batch-authority-invalid")
        payload = inputs.model_dump_json(by_alias=True)
        if len(payload.encode()) > 65536:
            raise ReconciliationProblem("reconciliation-batch-request-limit")
        with self._transaction(write=True) as (connection, _):
            previous = self._batch_request(connection, inputs.request_id)
            if previous is not None:
                if previous != inputs:
                    raise ReconciliationProblem("reconciliation-batch-command-conflict")
                return previous
            connection.execute(
                "INSERT INTO settings VALUES (?,?,?,0,'text',?,NULL,NULL,NULL,?,?)",
                (
                    new_uuid_v7(),
                    self._project,
                    "reconciliation.batch-request." + inputs.request_id,
                    payload,
                    actor.occurred_at,
                    actor.occurred_at,
                ),
            )
            return inputs

    @contextmanager
    def _batch_transaction(
        self,
        interrupted: Callable[[], bool] | None,
    ) -> Iterator[tuple[CanonicalConnection, _SqliteAggregateRepository]]:
        with self._transaction(write=True) as (connection, aggregates):
            if interrupted is None:
                yield connection, aggregates
            else:
                # SQL progress polling can abort a long statement. Leave rollback
                # outside the hook so the stop cannot interrupt recovery itself.
                with connection.interrupt_when(interrupted):
                    try:
                        yield connection, aggregates
                    except Exception:
                        if interrupted():
                            raise ReconciliationProblem("reconciliation-batch-interrupted") from None
                        raise

    def _source_snapshot(
        self,
        resolve: ReconciliationSourceResolver,
        *,
        batch: bool = False,
        checkpoint: Callable[[], None] | None = None,
    ) -> tuple[dict[str, SourceAssertion], ReconciliationSourceResolver]:
        prepared: dict[str, SourceAssertion] = {}
        byte_length = 0

        def collect(address: SourceAddress) -> SourceAssertion:
            nonlocal byte_length
            if checkpoint is not None:
                checkpoint()
            key = _digest(address.model_dump(mode="json"))
            if key not in prepared:
                if len(prepared) >= (MAX_AUTHORIZED_SOURCES if batch else _MAX_SOURCE_COUNT):
                    raise ReconciliationProblem("reconciliation-source-limit")
                source = self._resolve(address, resolve)
                byte_length += len(source.model_dump_json(by_alias=True).encode())
                if byte_length > (MAX_AUTHORIZED_BYTES if batch else _MAX_SOURCE_BYTES):
                    raise ReconciliationProblem("reconciliation-source-limit")
                prepared[key] = source
            return prepared[key]

        return prepared, collect

    def _load(self, connection: CanonicalConnection, revision: str) -> ReconciliationInspection:
        row = connection.execute(
            "SELECT address_sha256, payload_sha256, assertion_json, result_json, "
            "source_revision_id, address_revision_id "
            "FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
            (self._project, revision),
        ).fetchone()
        if row is None:
            raise ReconciliationProblem("reconciliation-not-found")
        source = SourceAssertion.model_validate_json(row[2])
        result = ReconciliationResult.model_validate_json(row[3])
        payload_sha = _payload(source)
        if (
            source.project_id != self._project
            or result.project_id != self._project
            or result.source != source.address
            or result.assertion_revision_id != revision
            or _digest(source.address.model_dump(mode="json")) != row[0]
            or payload_sha != row[1]
            or source.source_revision_id != row[4]
            or source.address.revision_id != row[5]
        ):
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        bound = connection.execute(
            "SELECT fingerprint FROM material_dependencies WHERE project_id=? AND output_revision_id=? "
            "AND configuration_id='scholarly.assertion-payload'",
            (self._project, revision),
        ).fetchall()
        if [tuple(row) for row in bound] != [("sha256:" + payload_sha,)]:
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        return ReconciliationInspection(result=result, assertion=source)

    def _authorized_load(
        self, connection: CanonicalConnection, revision: str, resolve: ReconciliationSourceResolver
    ) -> ReconciliationInspection:
        stored = self._load(connection, revision)
        if self._resolve(stored.assertion.address, resolve) != stored.assertion:
            raise ReconciliationProblem("reconciliation-source-changed")
        return stored

    def _cached_features(
        self, connection: CanonicalConnection, revision: str, source: SourceAssertion
    ) -> PreparedRecord | None:
        row = connection.execute(
            "SELECT input_sha256,payload_sha256,feature_json FROM reconciliation_feature_cache "
            "WHERE project_id=? AND assertion_revision_id=? AND feature_version=? "
            "AND normalizer_version=? AND configuration_sha256=?",
            (self._project, revision, FEATURE_VERSION, NORMALIZER_VERSION, DEFAULT_CONFIG.fingerprint),
        ).fetchone()
        if row is None:
            return None
        snapshot = FeatureSnapshot.model_validate_json(row[2])
        if row[0] != snapshot.input_sha256 or row[1] != _digest(snapshot.model_dump(mode="json", by_alias=True)):
            raise ReconciliationProblem("duplicate-feature-cache-mismatch")
        return snapshot.restore(revision, source)

    def prepared_record(self, revision_id: str, *, resolve: ReconciliationSourceResolver) -> PreparedRecord:
        # Authorize even a cache hit. Never resolve protected objects while holding
        # the cache writer, because their access audits have their own transaction.
        with self._transaction(write=False) as (connection, _):
            source = self._authorized_load(connection, revision_id, resolve).assertion
            cached = self._cached_features(connection, revision_id, source)
        if cached is not None:
            return cached
        snapshot = FeatureSnapshot.create(revision_id, source)
        with self._transaction(write=True) as (connection, _):
            if self._load(connection, revision_id).assertion != source:
                raise ReconciliationProblem("reconciliation-source-changed")
            cached = self._cached_features(connection, revision_id, source)
            if cached is not None:
                return cached
            connection.execute(
                "INSERT INTO reconciliation_feature_cache VALUES (?,?,?,?,?,?,?,?)",
                (
                    self._project,
                    revision_id,
                    FEATURE_VERSION,
                    NORMALIZER_VERSION,
                    DEFAULT_CONFIG.fingerprint,
                    snapshot.input_sha256,
                    _digest(snapshot.model_dump(mode="json", by_alias=True)),
                    snapshot.model_dump_json(by_alias=True),
                ),
            )
        return snapshot.restore(revision_id, source)

    def _work_sources(
        self, connection: CanonicalConnection, work_id: str, resolve: ReconciliationSourceResolver
    ) -> tuple[ReconciliationInspection, ...]:
        state = self._state(connection, work_id)
        if state.disposition != "active":
            raise ReconciliationProblem("reconciliation-work-retired")
        return tuple(self._authorized_load(connection, revision, resolve) for revision in state.assertion_revision_ids)

    def _state(self, connection: CanonicalConnection, work_id: str, revision_id: str | None = None) -> WorkState:
        # An explicitly addressed historical revision never follows a current alias.
        row = connection.execute(
            "SELECT r.revision_id,s.previous_revision_id,s.disposition,s.alias_target,s.decision_revision_id,"
            "z.member_count,z.state_sha256 FROM aggregate_revisions r "
            "LEFT JOIN reconciliation_work_states s ON s.revision_id=r.revision_id AND s.project_id=r.project_id "
            "LEFT JOIN reconciliation_work_seals z ON z.work_revision_id=s.revision_id AND z.project_id=s.project_id "
            "WHERE r.project_id=? AND r.aggregate_id=? AND (? IS NULL OR r.revision_id=?) "
            "ORDER BY r.revision DESC LIMIT 1",
            (self._project, work_id, revision_id, revision_id),
        ).fetchone()
        if row is None:
            raise ReconciliationProblem("reconciliation-not-found")
        if row[2] is None or row[5] is None:
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        rows = connection.execute(
            "SELECT assertion_revision_id FROM reconciliation_work_members "
            "WHERE project_id=? AND work_revision_id=? ORDER BY ordinal LIMIT 257",
            (self._project, row[0]),
        ).fetchall()
        state = WorkState(
            work_id=work_id,
            revision_id=row[0],
            previous_revision_id=row[1],
            disposition=row[2],
            alias_target=row[3],
            decision_revision_id=row[4],
            assertion_revision_ids=tuple(item[0] for item in rows),
        )
        if len(rows) != row[5] or state.fingerprint != row[6]:
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        return state

    def _publish_state(self, connection: CanonicalConnection, state: WorkState) -> None:
        state = WorkState.model_validate(state)
        connection.execute(
            "INSERT INTO reconciliation_work_states (revision_id,project_id,work_id,previous_revision_id,"
            "disposition,alias_target,decision_revision_id) VALUES (?,?,?,?,?,?,?)",
            (
                state.revision_id,
                self._project,
                state.work_id,
                state.previous_revision_id,
                state.disposition,
                state.alias_target,
                state.decision_revision_id,
            ),
        )
        for ordinal, assertion in enumerate(state.assertion_revision_ids, 1):
            connection.execute(
                "INSERT INTO reconciliation_work_members VALUES (?,?,?,?)",
                (state.revision_id, self._project, ordinal, assertion),
            )
        connection.execute(
            "INSERT INTO reconciliation_work_seals VALUES (?,?,?,?)",
            (state.revision_id, self._project, len(state.assertion_revision_ids), state.fingerprint),
        )

    def _assignment(self, connection: CanonicalConnection, assertion: str) -> WorkState | None:
        rows = connection.execute(
            "SELECT DISTINCT s.work_id FROM reconciliation_work_members m "
            "JOIN reconciliation_work_states s ON s.revision_id=m.work_revision_id AND s.project_id=m.project_id "
            "WHERE m.project_id=? AND m.assertion_revision_id=? ORDER BY s.work_id LIMIT 513",
            (self._project, assertion),
        ).fetchall()
        if len(rows) > 512:
            raise ReconciliationProblem("reconciliation-work-limit")
        # Validate every formerly assigned identity's current head. An unrelated
        # or unsealed aggregate revision must not silently unassign its sources.
        states = [self._state(connection, row[0]) for row in rows]
        assigned = [state for state in states if assertion in state.assertion_revision_ids]
        if len(assigned) > 1 or (rows and not assigned):
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        return assigned[0] if assigned else None

    def _authorize_assignment(
        self, connection: CanonicalConnection, assertion: str, resolve: ReconciliationSourceResolver
    ) -> WorkState | None:
        state = self._assignment(connection, assertion)
        if state is not None:
            self._work_sources(connection, state.work_id, resolve)
        return state

    def _assessment(
        self, connection: CanonicalConnection, source: SourceAssertion, resolve: ReconciliationSourceResolver
    ) -> MatchAssessment:
        works: set[str] = set()
        unresolved = False
        for scheme, value in _keys(source.identifiers):
            rows = connection.execute(
                "SELECT assertion_revision_id, work_id FROM reconciliation_identifier_links "
                "WHERE project_id=? AND scheme=? AND key_sha256=? LIMIT 257",
                (self._project, scheme, _digest([NORMALIZER_VERSION, scheme, value])),
            ).fetchall()
            if len(rows) > 256:
                raise ReconciliationProblem("reconciliation-match-limit")
            for revision, work in rows:
                candidate = self._authorized_load(connection, revision, resolve)
                if (scheme, value) not in _keys(candidate.assertion.identifiers) or work != candidate.result.work_id:
                    raise ReconciliationProblem("reconciliation-integrity-invalid")
                assignment = self._assignment(connection, revision)
                if assignment is None:
                    unresolved = True
                else:
                    works.add(assignment.work_id)
        if len(works) > 256:
            raise ReconciliationProblem("reconciliation-match-limit")
        existing = {
            work: tuple(
                identifier
                for source in self._work_sources(connection, work, resolve)
                for identifier in source.assertion.identifiers
            )
            for work in sorted(works)
        }
        result = assess_match(source.identifiers, existing)
        if unresolved:
            return MatchAssessment(
                "review-required",
                None,
                result.candidates,
                tuple(sorted(set(result.flags) | {"disputed-identifier"})),
                result.matching_keys,
            )
        return result

    def _append(
        self,
        aggregates: _SqliteAggregateRepository,
        *,
        sources: tuple[AggregateRevision, ...],
        actor: ReconciliationActor,
        digest: str,
        label: str,
        current: AggregateRevision | None = None,
        disputed: bool = False,
        historical_sources: tuple[AggregateRevision, ...] = (),
        kind: AggregateKind = "record",
        adjudicated: bool = False,
        payload_configuration: str = "assertion-payload",
        checkpoint: Callable[[], None] | None = None,
    ) -> AggregateRevision:
        # A propagation run has a fixed graph snapshot. Later outputs must not
        # evade an existing impact by being appended after that snapshot.
        self._require_fresh_inputs(aggregates, tuple(source.revision_id for source in sources), checkpoint=checkpoint)
        # Preserve complete, traversable provenance within the common 64-input
        # envelope. Material and historical-only leaves never share a manifest.
        while len(sources) + len(historical_sources) > 64:

            def pack(items: tuple[AggregateRevision, ...], *, historical: bool) -> tuple[AggregateRevision, ...]:
                return tuple(
                    self._append(
                        aggregates,
                        sources=() if historical else items[offset : offset + 64],
                        historical_sources=items[offset : offset + 64] if historical else (),
                        actor=actor,
                        kind="workflow",
                        label="Scholarly input manifest",
                        digest=_digest(
                            [
                                (item.revision_id, _projection_content_sha256(item))
                                for item in items[offset : offset + 64]
                            ]
                        ),
                        payload_configuration="input-manifest",
                        checkpoint=checkpoint,
                    )
                    for offset in range(0, len(items), 64)
                )

            sources, historical_sources = pack(sources, historical=False), pack(historical_sources, historical=True)
        revision = new_uuid_v7()
        dependencies = tuple(
            MaterialDependency(
                new_uuid_v7(),
                "human-decision" if source.aggregate_kind == "decision" else "source-revision",
                "non-material" if source in historical_sources else "direct",
                source.revision_id,
                None,
                None,
                _projection_content_sha256(source),
                "dependency.material.v1",
                "1.0.0",
            )
            for source in sources + historical_sources
        )
        for name, fingerprint in (
            (payload_configuration, digest),
            ("current-intent", actor.intent_sha256),
            ("current-privacy", actor.policy_sha256),
            ("normalizer", _digest(NORMALIZER_VERSION)),
        ):
            dependencies += (
                MaterialDependency(
                    new_uuid_v7(),
                    "parameter-set",
                    "direct",
                    None,
                    "scholarly." + name,
                    "1.0.0",
                    "sha256:" + fingerprint,
                    "dependency.material.v1",
                    "1.0.0",
                ),
            )
        if checkpoint is not None:
            checkpoint()
        return aggregates.append(
            AggregateRevisionDraft(
                revision_id=revision,
                aggregate_id=current.aggregate_id if current else new_uuid_v7(),
                aggregate_kind=kind,
                created_at=current.created_at if current else actor.occurred_at,
                modified_at=actor.occurred_at,
                display_label_observed=label,
                display_label_normalized=None,
                knowledge_status="adjudicated" if adjudicated else "disputed" if disputed else "inferred",
                rights_status="unknown",
                dependency_coverage="complete",
                provenance_inputs=sources + historical_sources,
                material_dependencies=dependencies,
            ),
            AtomicRepositoryEvent(
                event_id=new_uuid_v7(),
                outbox_id=new_uuid_v7(),
                event_type=kind + ".reconciled",
                occurred_at=actor.occurred_at,
                available_at=actor.occurred_at,
                trace_id=actor.trace_id,
                actor_type=actor.actor_type,
                actor_id=actor.actor_id,
                idempotency_key="reconcile-" + revision,
            ),
            expected_revision=current.revision if current else None,
        )

    def reconcile(
        self,
        source: SourceAddress,
        *,
        command_id: str,
        actor: ReconciliationActor,
        resolve: ReconciliationSourceResolver,
    ) -> ReconciliationResult:
        source = SourceAddress.model_validate(source)
        self._validate_actor(actor)
        if (
            not is_uuid_v7(command_id)
            or not is_uuid_v7(actor.actor_id)
            or re.fullmatch(r"[0-9a-f]{32}", actor.trace_id) is None
        ):
            raise ReconciliationProblem("reconciliation-command-invalid")
        _normalize_utc_millisecond(actor.occurred_at)
        if any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in (actor.intent_sha256, actor.policy_sha256)):
            raise ReconciliationProblem("reconciliation-authority-invalid")
        address_sha = _digest(source.model_dump(mode="json"))
        # Protected object reads write access-audit facts on their own database
        # connection. Resolve them before taking the canonical writer, while the
        # caller still holds the lifecycle/rights fence through both phases.
        # Re-run all index decisions under the writer; a concurrent new source
        # absent from this snapshot is a conflict, never a stale match.
        prepared, collect = self._source_snapshot(resolve)

        with self._transaction(write=False) as (connection, _):
            assertion = collect(source)
            previous = connection.execute(
                "SELECT revision_id FROM reconciliation_assertions WHERE project_id=? AND address_sha256=?",
                (self._project, address_sha),
            ).fetchone()
            if previous is None:
                self._assessment(connection, assertion, collect)
            else:
                self._authorized_load(connection, previous[0], collect)
                self._authorize_assignment(connection, previous[0], collect)

        def resolved(address: SourceAddress) -> SourceAssertion:
            key = _digest(address.model_dump(mode="json"))
            if key not in prepared:
                raise ReconciliationProblem("reconciliation-concurrent-source-change")
            return prepared[key]

        with self._transaction(write=True) as (connection, aggregates):
            return self._reconcile_with_connection(
                connection, aggregates, source, command_id=command_id, actor=actor, resolved=resolved
            )

    def _reconcile_with_connection(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        source: SourceAddress,
        *,
        command_id: str,
        actor: ReconciliationActor,
        resolved: ReconciliationSourceResolver,
    ) -> ReconciliationResult:
        address_sha = _digest(source.model_dump(mode="json"))
        command_sha = _digest([self._project, actor.actor_id, address_sha, NORMALIZER_VERSION])
        assertion = self._resolve(source, resolved)
        command = connection.execute(
            "SELECT actor_id, command_sha256, assertion_revision_id FROM reconciliation_commands "
            "WHERE project_id=? AND command_id=?",
            (self._project, command_id),
        ).fetchone()
        if command is not None:
            if command[:2] != (actor.actor_id, command_sha):
                raise ReconciliationProblem("reconciliation-command-conflict")
            prior = self._authorized_load(connection, command[2], resolved)
            self._authorize_assignment(connection, command[2], resolved)
            return prior.result
        prior = connection.execute(
            "SELECT revision_id FROM reconciliation_assertions WHERE project_id=? AND address_sha256=?",
            (self._project, address_sha),
        ).fetchone()
        exact_runs: tuple[str, ...] = ()
        if prior is not None:
            saved = self._authorized_load(connection, prior[0], resolved)
            self._authorize_assignment(connection, prior[0], resolved)
            result = saved.result
        else:
            assessment = self._assessment(connection, assertion, resolved)
            inputs = tuple(
                aggregates.get_revision(revision)
                for revision in sorted({source.revision_id, assertion.source_revision_id})
            )
            payload_sha = _payload(assertion)
            created = self._append(
                aggregates,
                sources=inputs,
                actor=actor,
                digest=payload_sha,
                label="Scholarly source assertion",
                disputed=bool(assessment.flags),
            )
            _publication_step("assertion-created")
            work = None
            current = aggregates.get(assessment.target) if assessment.target is not None else None
            current_state = self._state(connection, current.aggregate_id) if current else None
            if assessment.disposition != "review-required":
                if current is not None and len(self._work_sources(connection, current.aggregate_id, resolved)) >= 256:
                    raise ReconciliationProblem("reconciliation-work-limit")
                work = self._append(
                    aggregates,
                    sources=(
                        created,
                        *tuple(
                            aggregates.get_revision(revision)
                            for revision in (
                                current_state.assertion_revision_ids
                                + ((current_state.decision_revision_id,) if current_state.decision_revision_id else ())
                                if current_state
                                else ()
                            )
                        ),
                    ),
                    historical_sources=(current,) if current else (),
                    actor=actor,
                    digest=payload_sha,
                    label="Canonical scholarly work",
                    current=current,
                )
            _publication_step("work-created")
            result = ReconciliationResult(
                project_id=self._project,
                assertion_revision_id=created.revision_id,
                source=source,
                work_id=work.aggregate_id if work else None,
                work_revision_id=work.revision_id if work else None,
                disposition=assessment.disposition,
                candidates=assessment.candidates,
                flags=assessment.flags,
                knowledge_status="disputed" if assessment.flags else "inferred",
                matching_reason="human-review-required"
                if assessment.flags
                else "unique-compatible-exact-identifiers"
                if assessment.target
                else "no-exact-match",
            )
            connection.execute(
                "INSERT INTO reconciliation_assertions (revision_id, project_id, source_revision_id, "
                "address_revision_id, address_sha256, payload_sha256, assertion_json, result_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    created.revision_id,
                    self._project,
                    assertion.source_revision_id,
                    source.revision_id,
                    address_sha,
                    payload_sha,
                    assertion.model_dump_json(by_alias=True),
                    result.model_dump_json(by_alias=True),
                ),
            )
            if work is not None:
                self._publish_state(
                    connection,
                    WorkState(
                        work_id=work.aggregate_id,
                        revision_id=work.revision_id,
                        previous_revision_id=current.revision_id if current else None,
                        disposition="active",
                        alias_target=None,
                        assertion_revision_ids=tuple(
                            sorted(
                                (created.revision_id,) + (current_state.assertion_revision_ids if current_state else ())
                            )
                        ),
                        decision_revision_id=current_state.decision_revision_id if current_state else None,
                    ),
                )
            for scheme, value in sorted(_keys(assertion.identifiers)):
                connection.execute(
                    "INSERT INTO reconciliation_identifier_links (assertion_revision_id, project_id, scheme, "
                    "key_sha256, work_id) VALUES (?, ?, ?, ?, ?)",
                    (
                        created.revision_id,
                        self._project,
                        scheme,
                        _digest([NORMALIZER_VERSION, scheme, value]),
                        result.work_id,
                    ),
                )
            _publication_step("links-created")
            if current is not None and work is not None:
                exact_runs = self._publish_impacts(connection, (self._change(current, work, actor, human=False),))
            _publication_step("exact-impacts-created")
        connection.execute(
            "INSERT INTO reconciliation_commands VALUES (?, ?, ?, ?, ?)",
            (command_id, self._project, actor.actor_id, command_sha, result.assertion_revision_id),
        )
        for run_id in exact_runs:
            connection.execute(
                "INSERT INTO reconciliation_exact_impacts VALUES (?,?,?)", (run_id, self._project, command_id)
            )
        _publication_step("command-created")
        return result

    @staticmethod
    def _batch_output(revision: AggregateRevision) -> WorkflowOutputReference:
        return WorkflowOutputReference(
            revision.aggregate_id,
            revision.revision_id,
            _projection_content_sha256(revision),
            "application/vnd.research-observatory.duplicate-candidate-set+json",
            revision.aggregate_id,
        )

    def _candidate_content(self, connection: CanonicalConnection, revision_id: str) -> CandidateSetContent:
        row = connection.execute(
            "SELECT request_id,request_sha256,payload_sha256,candidate_set_json FROM reconciliation_candidate_sets "
            "WHERE project_id=? AND revision_id=?",
            (self._project, revision_id),
        ).fetchone()
        if row is None:
            raise ReconciliationProblem("reconciliation-not-found")
        content = CandidateSetContent.model_validate_json(row[3])
        binding = connection.execute(
            "SELECT fingerprint FROM material_dependencies WHERE project_id=? AND output_revision_id=? "
            "AND configuration_id='scholarly.duplicate-candidate-set'",
            (self._project, revision_id),
        ).fetchall()
        count, first, last = connection.execute(
            "SELECT COUNT(*),MIN(ordinal),MAX(ordinal) FROM reconciliation_candidate_pairs "
            "WHERE project_id=? AND set_revision_id=?",
            (self._project, revision_id),
        ).fetchone()
        if (
            content.project_id != self._project
            or (content.request_id, content.request_sha256, content_digest(content)) != tuple(row[:3])
            or [tuple(item) for item in binding] != [("sha256:" + row[2],)]
            or count != len(content.pair_sha256)
            or (count and (first != 0 or last != count - 1))
        ):
            raise ReconciliationProblem("duplicate-set-integrity-invalid")
        return content

    def candidate_set(self, revision_id: str, *, resolve: ReconciliationSourceResolver) -> CandidateSetContent:
        if not is_uuid_v7(revision_id):
            raise ReconciliationProblem("reconciliation-command-invalid")
        _, collect = self._source_snapshot(resolve, batch=True)
        with self._transaction(write=False) as (connection, _):
            content = self._candidate_content(connection, revision_id)
            for member in content.members:
                source = self._authorized_load(connection, member.assertion_revision_id, collect).assertion
                # The cached fingerprint remains bound to the immutable source;
                # current permissions are required even for historical inspection.
                prepared = FeatureSnapshot.create(member.assertion_revision_id, source).restore(
                    member.assertion_revision_id, source
                )
                if (prepared.revision, prepared.fingerprint) != (member.source_revision_id, member.input_sha256):
                    raise ReconciliationProblem("duplicate-set-source-mismatch")
                self._authorize_assignment(connection, member.assertion_revision_id, collect)
            return content

    def candidate_pairs(
        self,
        revision_id: str,
        *,
        after: int,
        limit: int,
        resolve: ReconciliationSourceResolver,
    ) -> tuple[CandidateExplanation, ...]:
        if type(after) is not int or type(limit) is not int or after < 0 or not 1 <= limit <= 100:
            raise ReconciliationProblem("duplicate-set-page-invalid")
        content = self.candidate_set(revision_id, resolve=resolve)
        if after > len(content.pair_sha256):
            raise ReconciliationProblem("duplicate-set-page-invalid")
        with self._transaction(write=False) as (connection, _):
            rows = connection.execute(
                "SELECT ordinal,payload_sha256,explanation_json FROM reconciliation_candidate_pairs "
                "WHERE project_id=? AND set_revision_id=? AND ordinal>=? ORDER BY ordinal LIMIT ?",
                (self._project, revision_id, after, limit),
            ).fetchall()
            pairs = []
            for ordinal, digest, payload in rows:
                pair = CandidateExplanation.model_validate_json(payload)
                content.validate_pair(ordinal, pair)
                if digest != content_digest(pair):
                    raise ReconciliationProblem("duplicate-set-integrity-invalid")
                pairs.append(pair)
            if len(pairs) != min(limit, len(content.pair_sha256) - after):
                raise ReconciliationProblem("duplicate-set-incomplete")
            return tuple(pairs)

    def inspect_candidates(
        self,
        revision_id: str,
        *,
        after: int,
        limit: int,
        resolve: ReconciliationSourceResolver,
    ) -> CandidatePage:
        _, collect = self._source_snapshot(resolve, batch=True)
        content = self.candidate_set(revision_id, resolve=collect)
        pairs = self.candidate_pairs(revision_id, after=after, limit=limit, resolve=collect)
        inventory = (
            _SqliteWorkflowQueueRepository(self._database, self._project)
            .accepted_snapshot(activity_types=SOURCE_ACTIVITIES)
            .fingerprint.removeprefix("sha256:")
        )
        changed = False
        revisions = {revision_id}
        with self._transaction(write=False) as (connection, _):
            for member in content.members:
                current = self._authorize_assignment(connection, member.assertion_revision_id, collect)
                reference = (
                    CanonicalWorkReference(work_id=current.work_id, revision_id=current.revision_id)
                    if current
                    else None
                )
                changed |= reference != member.canonical_work
                revisions.update((member.assertion_revision_id, member.source_revision_id))
                if member.canonical_work is not None:
                    revisions.add(member.canonical_work.revision_id)
                if current is not None:
                    revisions.add(current.revision_id)
                    if current.decision_revision_id is not None:
                        revisions.add(current.decision_revision_id)
            affected = False
            ordered = sorted(revisions)
            # Include pending direct changes before downstream propagation has
            # advanced, not only already materialized output impact items.
            for offset in range(0, len(ordered), 256):
                chunk = ordered[offset : offset + 256]
                markers = ",".join("?" for _ in chunk)
                if (
                    connection.execute(
                        "SELECT 1 FROM dependency_impact_items WHERE project_id=? AND output_revision_id IN ("
                        + markers
                        + ") "
                        "UNION ALL SELECT 1 FROM dependency_impact_runs "
                        "WHERE project_id=? AND previous_revision_id IN (" + markers + ") "
                        "AND (replacement_fingerprint IS NULL OR replacement_fingerprint<>previous_fingerprint) "
                        "LIMIT 1",
                        (self._project, *chunk, self._project, *chunk),
                    ).fetchone()
                    is not None
                ):
                    affected = True
                    break
        end = after + len(pairs)
        return CandidatePage(
            project_id=self._project,
            set_revision_id=revision_id,
            request_id=content.request_id,
            inventory_sha256=content.inventory_sha256,
            current_inventory_sha256=inventory,
            inventory_state="unchanged" if inventory == content.inventory_sha256 else "changed",
            record_count=len(content.members),
            candidate_count=len(content.pair_sha256),
            compared_pairs=content.compared_pairs,
            membership_state="changed" if changed else "unchanged",
            dependency_state="requires-review" if affected else "unaffected",
            after=after,
            next_after=end if end < len(content.pair_sha256) else None,
            items=pairs,
        )

    def publish_batch(
        self,
        inputs: BatchInput,
        addresses: tuple[SourceAddress, ...],
        *,
        claim: WorkflowJobClaim,
        actor: ReconciliationActor,
        resolve: ReconciliationSourceResolver,
        now: Callable[[], str],
        interrupted: Callable[[], bool] | None = None,
        lease_duration_ms: int = 30000,
    ) -> WorkflowOutputReference:
        """Caller fences current authority; stop hints can only abort this transaction."""
        inputs = BatchInput.model_validate(inputs)
        self._validate_actor(actor)
        if (inputs.project_id, inputs.actor_id, inputs.intent.content_hash, inputs.policy_sha256) != (
            self._project,
            actor.actor_id,
            "sha256:" + actor.intent_sha256,
            "sha256:" + actor.policy_sha256,
        ):
            raise ReconciliationProblem("reconciliation-batch-authority-invalid")
        queue = _SqliteWorkflowQueueRepository(self._database, self._project)
        authority = queue.authority(claim.job_id)
        continuation = json.loads(authority.snapshot_json).get("continuation")
        predecessor = (
            (queue.get(continuation["sourceJobId"]), queue.authority(continuation["sourceJobId"]))
            if continuation
            else None
        )
        bind_batch_claim(authority, claim, inputs, predecessor=predecessor)
        accepted = queue.accepted_output(claim.job_id)
        addresses = tuple(SourceAddress.model_validate(address) for address in addresses)
        keys = tuple(_digest(address.model_dump(mode="json")) for address in addresses)
        if len(addresses) > DEFAULT_CONFIG.max_records or len(keys) != len(set(keys)):
            raise ReconciliationProblem("duplicate-record-limit")

        def checkpoint() -> None:
            if interrupted is not None and interrupted():
                raise ReconciliationProblem("reconciliation-batch-interrupted")

        preparation_heartbeat = datetime.fromisoformat(now())

        def prepare_checkpoint() -> None:
            nonlocal claim, preparation_heartbeat
            checkpoint()
            instant = now()
            current = datetime.fromisoformat(instant)
            if accepted is None and current >= preparation_heartbeat:
                # Queue-only writes here precede the canonical publication writer.
                claim = queue.heartbeat(
                    claim,
                    now=instant,
                    lease_duration_ms=lease_duration_ms,
                    progress={"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None},
                )
                if queue.get(claim.job_id).cancellation_requested_at is not None:
                    raise ReconciliationProblem("reconciliation-batch-interrupted")
                preparation_heartbeat = current + timedelta(milliseconds=min(5000, lease_duration_ms // 3))

        prepared, collect = self._source_snapshot(resolve, batch=True, checkpoint=prepare_checkpoint)
        # Reads of encrypted source objects can publish access audits. Complete
        # every such read before acquiring the canonical writer.
        with self._transaction(write=False) as (connection, _):
            for address in addresses:
                source = collect(address)
                previous = connection.execute(
                    "SELECT revision_id FROM reconciliation_assertions WHERE project_id=? AND address_sha256=?",
                    (self._project, _digest(address.model_dump(mode="json"))),
                ).fetchone()
                if previous is None:
                    self._assessment(connection, source, collect)
                else:
                    self._authorized_load(connection, previous[0], collect)
                    self._authorize_assignment(connection, previous[0], collect)

        def resolved(address: SourceAddress) -> SourceAssertion:
            checkpoint()
            key = _digest(address.model_dump(mode="json"))
            if key not in prepared:
                raise ReconciliationProblem("reconciliation-concurrent-source-change")
            return prepared[key]

        with self._batch_transaction(interrupted) as (connection, aggregates):
            queue._verify_attempt_capability(connection, claim)
            existing = connection.execute(
                "SELECT revision_id,request_sha256 FROM reconciliation_candidate_sets "
                "WHERE project_id=? AND request_id=?",
                (self._project, inputs.request_id),
            ).fetchone()
            if existing is not None:
                content = self._candidate_content(connection, existing[0])
                if existing[1] != inputs.configuration_hash.removeprefix("sha256:"):
                    raise ReconciliationProblem("reconciliation-batch-command-conflict")
                stored_keys = set()
                for member in content.members:
                    stored = self._authorized_load(connection, member.assertion_revision_id, resolved)
                    self._authorize_assignment(connection, member.assertion_revision_id, resolved)
                    stored_keys.add(_digest(stored.assertion.address.model_dump(mode="json")))
                output = self._batch_output(aggregates.get_revision(existing[0]))
                if stored_keys != set(keys) or accepted is None or accepted.outputs != (output,):
                    raise ReconciliationProblem("reconciliation-batch-output-mismatch")
                queue._complete_with_connection(connection, claim, now=now(), outputs=(output,))
                return output
            if accepted is not None:
                raise ReconciliationProblem("reconciliation-batch-output-mismatch")
            next_heartbeat = datetime.fromisoformat(now())

            def maintain(*, force: bool = False) -> None:
                nonlocal claim, next_heartbeat
                checkpoint()
                instant = now()
                current = datetime.fromisoformat(instant)
                if force or current >= next_heartbeat:
                    row = queue._lease_row(connection, claim, instant, states=("running",))
                    if row[3] is not None or row[4] != "running":
                        raise ReconciliationProblem("reconciliation-batch-interrupted")
                    claim = queue._heartbeat_with_connection(
                        connection,
                        claim,
                        now=instant,
                        lease_duration_ms=lease_duration_ms,
                        progress={"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None},
                    )
                    next_heartbeat = current + timedelta(milliseconds=min(5000, lease_duration_ms // 3))

            maintain(force=True)
            worker = replace(actor, actor_id=claim.worker_id, actor_type="worker", occurred_at=now())
            results = []
            features = []
            for address in addresses:
                maintain()
                result = self._reconcile_with_connection(
                    connection,
                    aggregates,
                    address,
                    command_id=new_uuid_v7(),
                    actor=worker,
                    resolved=resolved,
                )
                results.append(result)
                source = self._authorized_load(connection, result.assertion_revision_id, resolved).assertion
                cached = self._cached_features(connection, result.assertion_revision_id, source)
                if cached is None:
                    snapshot = FeatureSnapshot.create(result.assertion_revision_id, source)
                    connection.execute(
                        "INSERT INTO reconciliation_feature_cache VALUES (?,?,?,?,?,?,?,?)",
                        (
                            self._project,
                            result.assertion_revision_id,
                            FEATURE_VERSION,
                            NORMALIZER_VERSION,
                            DEFAULT_CONFIG.fingerprint,
                            snapshot.input_sha256,
                            content_digest(snapshot),
                            snapshot.model_dump_json(by_alias=True),
                        ),
                    )
                    cached = snapshot.restore(result.assertion_revision_id, source)
                features.append(cached)
            _publication_step("batch-exact-complete")
            retrieval = generate_prepared_candidates(tuple(features), checkpoint=maintain)
            pairs = tuple(CandidateExplanation.from_kernel(pair) for pair in retrieval.pairs)
            if sum(len(pair.model_dump_json(by_alias=True).encode()) for pair in pairs) > MAX_CANDIDATE_BYTES:
                raise ReconciliationProblem("duplicate-set-size-limit")
            by_assertion = {item.key: item for item in features}
            members = []
            source_revisions = set()
            for result in sorted(results, key=lambda item: item.assertion_revision_id):
                maintain()
                state = self._authorize_assignment(connection, result.assertion_revision_id, resolved)
                feature = by_assertion[result.assertion_revision_id]
                members.append(
                    CandidateMember(
                        assertion_revision_id=result.assertion_revision_id,
                        source_revision_id=feature.revision,
                        input_sha256=feature.fingerprint,
                        canonical_work=CanonicalWorkReference(work_id=state.work_id, revision_id=state.revision_id)
                        if state
                        else None,
                    )
                )
                source_revisions.add(result.assertion_revision_id)
                if state is not None:
                    source_revisions.add(state.revision_id)
                    if state.decision_revision_id:
                        source_revisions.add(state.decision_revision_id)
            content = CandidateSetContent(
                project_id=self._project,
                request_id=inputs.request_id,
                request_sha256=inputs.configuration_hash.removeprefix("sha256:"),
                inventory_sha256=inputs.inventory.queue_snapshot().fingerprint.removeprefix("sha256:"),
                members=tuple(members),
                compared_pairs=retrieval.compared_pairs,
                pair_sha256=tuple(content_digest(pair) for pair in pairs),
            )
            payload = content.model_dump_json(by_alias=True)
            if len(payload.encode()) > 8 * 1024 * 1024:
                raise ReconciliationProblem("duplicate-set-size-limit")
            revision = self._append(
                aggregates,
                sources=tuple(aggregates.get_revision(item) for item in sorted(source_revisions)),
                actor=replace(worker, occurred_at=now()),
                digest=content_digest(content),
                label="Scholarly duplicate candidates",
                kind="workflow",
                payload_configuration="duplicate-candidate-set",
                checkpoint=maintain,
            )
            connection.execute(
                "INSERT INTO reconciliation_candidate_sets "
                "(revision_id,project_id,request_id,request_sha256,payload_sha256,candidate_set_json) "
                "VALUES (?,?,?,?,?,?)",
                (
                    revision.revision_id,
                    self._project,
                    inputs.request_id,
                    content.request_sha256,
                    content_digest(content),
                    payload,
                ),
            )
            for ordinal, pair in enumerate(pairs):
                maintain()
                content.validate_pair(ordinal, pair)
                connection.execute(
                    "INSERT INTO reconciliation_candidate_pairs VALUES (?,?,?,?,?)",
                    (
                        revision.revision_id,
                        self._project,
                        ordinal,
                        content_digest(pair),
                        pair.model_dump_json(by_alias=True),
                    ),
                )
            _publication_step("batch-candidates-created")
            output = self._batch_output(revision)
            completed_at = now()
            connection.execute(
                "INSERT INTO workflow_attempt_artifacts VALUES "
                "(?, ?, ?, ?, ?, 'output', 'retained-incomplete', ?, ?, ?, ?, ?)",
                (
                    claim.attempt_id,
                    self._project,
                    claim.job_id,
                    output.artifact_id,
                    output.revision_id,
                    output.content_hash,
                    output.media_type,
                    output.provenance_entity_id,
                    completed_at,
                    completed_at,
                ),
            )
            _publication_step("batch-before-completion")
            maintain(force=True)
            queue._complete_with_connection(connection, claim, now=now(), outputs=(output,))
            checkpoint()
            return output

    def inspect(self, revision_id: str, *, resolve: ReconciliationSourceResolver) -> ReconciliationInspection:
        if not is_uuid_v7(revision_id):
            raise ReconciliationProblem("reconciliation-address-invalid")
        _, collect = self._source_snapshot(resolve)
        with self._transaction(write=False) as (connection, aggregates):
            result = self._authorized_load(connection, revision_id, collect)
            state = self._assignment(connection, revision_id)
            current = aggregates.get(state.work_id) if state else None
            sources = self._work_sources(connection, state.work_id, collect) if state else (result,)
            values: dict[str, list[FieldObservation]] = {}
            for source in sources:
                for field in source.assertion.fields:
                    name = {"author": "authors", "container": "venue"}.get(field.name, field.name)
                    values.setdefault(name, []).append(
                        FieldObservation(
                            assertion_revision_id=source.result.assertion_revision_id,
                            value=field.observed,
                            origin=field.origin,
                        )
                    )
            selections = []
            for name, observations in sorted(values.items()):
                selected = select_field(
                    tuple((item.assertion_revision_id, item.value, item.origin) for item in observations)
                )
                selections.append(
                    CanonicalFieldSelection(
                        name=name,
                        selected=selected.selected,
                        status=selected.status,
                        reason=selected.reason,
                        observations=tuple(observations),
                    )
                )
            inspected_revisions = (revision_id,) + ((current.revision_id,) if current else ())
            if state and state.decision_revision_id:
                inspected_revisions += (state.decision_revision_id,)
            impacted = connection.execute(
                "SELECT 1 FROM dependency_impact_items WHERE project_id=? AND output_revision_id IN ("
                + ",".join("?" for _ in inspected_revisions)
                + ") UNION ALL SELECT 1 FROM dependency_impact_runs WHERE project_id=? AND previous_revision_id IN ("
                + ",".join("?" for _ in inspected_revisions)
                + ") AND (replacement_fingerprint IS NULL OR replacement_fingerprint<>previous_fingerprint) LIMIT 1",
                (self._project, *inspected_revisions, self._project, *inspected_revisions),
            ).fetchone()
            result = ReconciliationInspection(
                result=result.result,
                assertion=result.assertion,
                canonical_work=CanonicalWorkReference(work_id=current.aggregate_id, revision_id=current.revision_id)
                if current is not None
                else None,
                canonical_fields=tuple(selections),
                dependency_state="requires-review" if impacted else "unaffected",
            )
            if len(result.model_dump_json(by_alias=True).encode()) > 4 * 1024 * 1024:
                raise ReconciliationProblem("reconciliation-inspection-limit")
            return result

    @staticmethod
    def _require_fresh_inputs(
        aggregates: _SqliteAggregateRepository,
        revisions: tuple[str, ...],
        *,
        checkpoint: Callable[[], None] | None = None,
    ) -> None:
        try:
            for revision in revisions:
                if checkpoint is not None:
                    checkpoint()
                aggregates._require_fresh_revision(revision, include_changed_input=True)
        except RepositoryConflict:
            raise ReconciliationProblem("reconciliation-input-requires-review") from None

    def _inbound_aliases(self, connection: CanonicalConnection, work_ids: tuple[str, ...]) -> tuple[WorkState, ...]:
        pending = list(work_ids)
        found: dict[str, WorkState] = {}
        while pending:
            target = pending.pop()
            rows = connection.execute(
                "SELECT s.work_id FROM reconciliation_work_states s WHERE s.project_id=? AND s.alias_target=? "
                "AND NOT EXISTS (SELECT 1 FROM reconciliation_work_states n WHERE n.project_id=s.project_id "
                "AND n.previous_revision_id=s.revision_id) ORDER BY s.work_id LIMIT 257",
                (self._project, target),
            ).fetchall()
            for row in rows:
                if row[0] in found or row[0] in work_ids:
                    raise ReconciliationProblem("reconciliation-alias-cycle")
                state = self._state(connection, row[0])
                if state.disposition != "alias" or state.alias_target != target:
                    raise ReconciliationProblem("reconciliation-integrity-invalid")
                found[state.work_id] = state
                pending.append(state.work_id)
            if len(found) > 256:
                raise ReconciliationProblem("reconciliation-alias-limit")
        return tuple(found[key] for key in sorted(found))

    def _review_context(
        self,
        connection: CanonicalConnection,
        work_ids: tuple[str, ...],
        unassigned: tuple[str, ...],
        resolve: ReconciliationSourceResolver,
    ) -> ReviewContext:
        if (
            len(work_ids) > 32
            or len(unassigned) > 256
            or len(set(work_ids)) != len(work_ids)
            or len(set(unassigned)) != len(unassigned)
            or any(not is_uuid_v7(item) for item in work_ids + unassigned)
        ):
            raise ReconciliationProblem("reconciliation-review-inputs-invalid")
        works = tuple(self._state(connection, work_id) for work_id in sorted(work_ids))
        if any(work.disposition != "active" for work in works):
            raise ReconciliationProblem("reconciliation-work-retired")
        assignments = {member: work.work_id for work in works for member in work.assertion_revision_ids}
        members = [member for work in works for member in work.assertion_revision_ids] + list(unassigned)
        if not members or len(members) > 512 or len(set(members)) != len(members):
            raise ReconciliationProblem("reconciliation-review-inputs-invalid")
        sources = []
        for revision in sorted(members):
            loaded = self._authorized_load(connection, revision, resolve)
            assigned = self._assignment(connection, revision)
            if (assigned.work_id if assigned else None) != assignments.get(revision):
                raise ReconciliationProblem("reconciliation-review-predecessor-changed")
            sources.append(ReviewSource(assertion_revision_id=revision, assertion=loaded.assertion))
        context = ReviewContext(
            works=works,
            unassigned_assertion_revision_ids=tuple(sorted(unassigned)),
            inbound_aliases=self._inbound_aliases(connection, work_ids),
            sources=tuple(sources),
        )
        if len(context.model_dump_json(by_alias=True).encode()) > 4 * 1024 * 1024:
            raise ReconciliationProblem("reconciliation-inspection-limit")
        return context

    def review_context(
        self, work_ids: tuple[str, ...], *, unassigned: tuple[str, ...] = (), resolve: ReconciliationSourceResolver
    ) -> ReviewContext:
        _, collect = self._source_snapshot(resolve)
        with self._transaction(write=False) as (connection, _):
            return self._review_context(connection, work_ids, unassigned, collect)

    @staticmethod
    def _validate_actor(actor: ReconciliationActor) -> None:
        if (
            actor.actor_type != "human"
            or not is_uuid_v7(actor.actor_id)
            or re.fullmatch(r"[0-9a-f]{32}", actor.trace_id) is None
        ):
            raise ReconciliationProblem("reconciliation-command-invalid")
        _normalize_utc_millisecond(actor.occurred_at)
        if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in (actor.intent_sha256, actor.policy_sha256)):
            raise ReconciliationProblem("reconciliation-authority-invalid")

    @staticmethod
    def _change(
        previous: AggregateRevision,
        replacement: AggregateRevision | None,
        actor: ReconciliationActor,
        *,
        human: bool = True,
    ) -> DependencyChange:
        change_id = new_uuid_v7()
        return DependencyChange(
            change_id=change_id,
            idempotency_key="reconciliation-impact-" + change_id,
            reason="HUMAN_DECISION" if human else "SOURCE_VERSION",
            dependency_kind="human-decision" if previous.aggregate_kind == "decision" else "source-revision",
            previous_revision_id=previous.revision_id,
            replacement_revision_id=replacement.revision_id if replacement else new_uuid_v7(),
            configuration_id=None,
            previous_configuration_version=None,
            replacement_configuration_version=None,
            previous_fingerprint=_projection_content_sha256(previous),
            replacement_fingerprint=_projection_content_sha256(replacement)
            if replacement
            else "sha256:" + _digest(["prospective-reconciliation", previous.revision_id]),
            propagation_policy_id="dependency.propagation.v1",
            propagation_policy_version="1.0.0",
            actor_id=actor.actor_id,
            trace_id=actor.trace_id,
            occurred_at=actor.occurred_at,
        )

    def _review_preview(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        plan: ReviewPlan,
        actor: ReconciliationActor,
        resolve: ReconciliationSourceResolver,
    ) -> ReviewPreview:
        context = self._review_context(
            connection, tuple(work.work_id for work in plan.works), plan.unassigned_assertion_revision_ids, resolve
        )
        if (
            context.works != tuple(sorted(plan.works, key=lambda work: work.work_id))
            or context.fingerprint != plan.evidence_sha256
        ):
            raise ReconciliationProblem("reconciliation-review-predecessor-changed")
        survivors = {part.existing_work_id for part in plan.partitions}
        required = {work.work_id: work.revision_id for work in context.inbound_aliases}
        required.update({work.work_id: work.revision_id for work in plan.works if work.work_id not in survivors})
        if {alias.work_id: alias.revision_id for alias in plan.aliases} != required:
            raise ReconciliationProblem("reconciliation-review-alias-plan-incomplete")
        self._require_fresh_inputs(
            aggregates,
            tuple(source.assertion_revision_id for source in context.sources)
            + tuple(
                state.decision_revision_id
                for state in context.works + context.inbound_aliases
                if state.decision_revision_id
            ),
        )
        impact_repository = _SqliteDependencyImpactRepository(self._database, self._project)
        graph_hashes: set[str] = set()
        affected: set[str] = set()
        unknown: set[str] = set()
        for state in context.works + context.inbound_aliases:
            # These exact current Work heads were checked above. The preview
            # plans a proposed change; publication later verifies actual same-ID
            # replacements through the ordinary strict impact entry point.
            preview = impact_repository._plan_with_connection(
                connection,
                self._change(aggregates.get_revision(state.revision_id), None, actor),
                decisions=(),
                limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS,
            )
            graph_hashes.add(preview.graph_sha256)
            affected.update(preview.affected_output_revision_ids)
            unknown.update(item.output_revision_id for item in preview.impacts if item.disposition == "unknown-impact")
        if len(affected) > 20000:
            raise ReconciliationProblem("reconciliation-review-impact-limit")
        digest = _digest(
            [
                self._project,
                plan.fingerprint,
                context.fingerprint,
                actor.actor_id,
                actor.intent_sha256,
                actor.policy_sha256,
                sorted(graph_hashes),
                sorted(affected),
                sorted(unknown),
            ]
        )
        return ReviewPreview(
            command_id=new_uuid_v7(),
            plan_sha256=plan.fingerprint,
            evidence_sha256=context.fingerprint,
            preview_sha256=digest,
            affected_output_revision_ids=tuple(sorted(affected)),
            unknown_impact_revision_ids=tuple(sorted(unknown)),
        )

    def preview_review(
        self, plan: ReviewPlan, *, actor: ReconciliationActor, resolve: ReconciliationSourceResolver
    ) -> ReviewPreview:
        plan = ReviewPlan.model_validate(plan)
        self._validate_actor(actor)
        _, collect = self._source_snapshot(resolve)
        with self._transaction(write=False) as (connection, aggregates):
            return self._review_preview(connection, aggregates, plan, actor, collect)

    def _review_replay(
        self,
        connection: CanonicalConnection,
        command: ReviewCommand,
        actor: ReconciliationActor,
        resolve: ReconciliationSourceResolver,
    ) -> ReviewOutcome | None:
        row = connection.execute(
            "SELECT actor_id,command_sha256,plan_sha256,plan_json,outcome_json,revision_id "
            "FROM reconciliation_review_decisions WHERE project_id=? AND command_id=?",
            (self._project, command.command_id),
        ).fetchone()
        if row is None:
            return None
        expected = _digest([self._project, actor.actor_id, command.model_dump(mode="json", by_alias=True)])
        if row[0] != actor.actor_id or row[1] != expected:
            raise ReconciliationProblem("reconciliation-command-conflict")
        plan, outcome = ReviewPlan.model_validate_json(row[3]), ReviewOutcome.model_validate_json(row[4])
        if (
            plan != command.plan
            or plan.fingerprint != row[2]
            or outcome.plan_sha256 != row[2]
            or outcome.decision_revision_id != row[5]
            or outcome.command_id != command.command_id
        ):
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        binding = connection.execute(
            "SELECT fingerprint FROM material_dependencies WHERE project_id=? AND output_revision_id=? "
            "AND configuration_id='scholarly.review-plan'",
            (self._project, outcome.decision_revision_id),
        ).fetchall()
        if [tuple(item) for item in binding] != [("sha256:" + plan.fingerprint,)]:
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        for state in outcome.work_states:
            if self._state(connection, state.work_id, state.revision_id) != state:
                raise ReconciliationProblem("reconciliation-integrity-invalid")
        members = (
            tuple(member for work in plan.works for member in work.assertion_revision_ids)
            + plan.unassigned_assertion_revision_ids
        )
        for member in members:
            self._authorized_load(connection, member, resolve)
            self._authorize_assignment(connection, member, resolve)
        return outcome

    def _owned_impact_change(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        impacts: _SqliteDependencyImpactRepository,
        root_id: str,
    ) -> DependencyChange:
        root = impacts._run_with_connection(connection, root_id)
        change = impacts._change_with_connection(connection, root.change_id)
        row = connection.execute(
            "SELECT d.revision_id,d.command_id,d.plan_sha256,d.plan_json,d.outcome_json,d.actor_id "
            "FROM reconciliation_review_decisions d,json_each(d.outcome_json,'$.dependencyRunIds') owned "
            "WHERE d.project_id=? AND owned.value=?",
            (self._project, root_id),
        ).fetchall()
        exact = connection.execute(
            "SELECT c.actor_id,c.assertion_revision_id,a.result_json FROM reconciliation_exact_impacts x "
            "JOIN reconciliation_commands c ON c.command_id=x.command_id AND c.project_id=x.project_id "
            "JOIN reconciliation_assertions a ON a.revision_id=c.assertion_revision_id AND a.project_id=c.project_id "
            "WHERE x.project_id=? AND x.run_id=?",
            (self._project, root_id),
        ).fetchall()
        if len(row) + len(exact) != 1:
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        if row:
            owner = row[0]
            plan, outcome = ReviewPlan.model_validate_json(owner[3]), ReviewOutcome.model_validate_json(owner[4])
            states = [
                state
                for state in outcome.work_states
                if (state.previous_revision_id, state.revision_id)
                == (change.previous_revision_id, change.replacement_revision_id)
            ]
            binding = connection.execute(
                "SELECT fingerprint FROM material_dependencies WHERE project_id=? AND output_revision_id=? "
                "AND configuration_id='scholarly.review-plan'",
                (self._project, owner[0]),
            ).fetchall()
            if (
                outcome.decision_revision_id != owner[0]
                or outcome.command_id != owner[1]
                or plan.fingerprint != owner[2]
                or outcome.plan_sha256 != owner[2]
                or root_id not in outcome.dependency_run_ids
                or change.actor_id != owner[5]
                or change.reason != "HUMAN_DECISION"
                or len(states) != 1
                or states[0].decision_revision_id != owner[0]
                or self._state(connection, states[0].work_id, states[0].revision_id) != states[0]
                or [tuple(item) for item in binding] != [("sha256:" + plan.fingerprint,)]
                or aggregates.get_revision(outcome.decision_revision_id).aggregate_id != outcome.decision_id
            ):
                raise ReconciliationProblem("reconciliation-integrity-invalid")
        else:
            owner = exact[0]
            result = ReconciliationResult.model_validate_json(owner[2])
            if result.work_id is None or result.work_revision_id is None:
                raise ReconciliationProblem("reconciliation-integrity-invalid")
            state = self._state(connection, result.work_id, result.work_revision_id)
            if (
                result.project_id != self._project
                or result.assertion_revision_id != owner[1]
                or change.actor_id != owner[0]
                or change.reason != "SOURCE_VERSION"
                or state.previous_revision_id != change.previous_revision_id
                or state.revision_id != change.replacement_revision_id
                or owner[1] not in state.assertion_revision_ids
            ):
                raise ReconciliationProblem("reconciliation-integrity-invalid")
        if (
            change.previous_revision_id is None
            or change.replacement_revision_id is None
            or change.dependency_kind != "source-revision"
            or change.configuration_id is not None
            or change.previous_configuration_version is not None
            or change.replacement_configuration_version is not None
            or change.propagation_policy_id != "dependency.propagation.v1"
            or change.propagation_policy_version != "1.0.0"
            or change.previous_fingerprint
            != _projection_content_sha256(aggregates.get_revision(change.previous_revision_id))
            or change.replacement_fingerprint
            != _projection_content_sha256(aggregates.get_revision(change.replacement_revision_id))
        ):
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        return change

    def _impact_snapshot_sha256(self, connection: CanonicalConnection, run_id: str) -> str:
        row = connection.execute(
            "SELECT " + _IMPACT_SNAPSHOT_COLUMNS + " FROM dependency_impact_runs WHERE project_id=? AND run_id=?",
            (self._project, run_id),
        ).fetchone()
        if row is None:
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        return _digest(["reconciliation-impact-snapshot/1.0", tuple(row)])

    def _seal_impact(self, connection: CanonicalConnection, run_id: str) -> None:
        connection.execute(
            "INSERT INTO reconciliation_impact_seals VALUES (?,?,?)",
            (run_id, self._project, self._impact_snapshot_sha256(connection, run_id)),
        )

    def advance_review_impacts(self) -> bool:
        # The project lifecycle fence remains held by the worker. Root ownership,
        # chain validation and any replacement intent share one writer snapshot.
        impacts = _SqliteDependencyImpactRepository(self._database, self._project)
        with self._transaction(write=True) as (connection, aggregates):
            row = connection.execute(
                "WITH roots(root_id) AS (SELECT run_id FROM reconciliation_exact_impacts WHERE project_id=? "
                "UNION SELECT owned.value FROM reconciliation_review_decisions d, "
                "json_each(d.outcome_json,'$.dependencyRunIds') owned WHERE d.project_id=?), "
                "leaves AS (SELECT root_id,COALESCE((SELECT c.run_id FROM reconciliation_impact_continuations c "
                "WHERE c.root_run_id=roots.root_id AND c.project_id=? ORDER BY c.sequence DESC LIMIT 1),root_id) leaf "
                "FROM roots) SELECT root_id,leaf FROM leaves WHERE (SELECT event_type "
                "FROM dependency_impact_audit_events a WHERE a.run_id=leaf AND a.project_id=? "
                "ORDER BY sequence DESC LIMIT 1) IN ('started','checkpoint','failed-attempt') ORDER BY root_id LIMIT 1",
                (self._project, self._project, self._project, self._project),
            ).fetchone()
            if row is None:
                return False
            root_id, leaf_id = str(row[0]), str(row[1])
            root_change = self._owned_impact_change(connection, aggregates, impacts, root_id)
            links = connection.execute(
                "SELECT sequence,previous_run_id,run_id,previous_checkpoint_sha256 "
                "FROM reconciliation_impact_continuations "
                "WHERE project_id=? AND root_run_id=? ORDER BY sequence",
                (self._project, root_id),
            ).fetchall()
            previous_id = root_id
            for sequence, link in enumerate(links, 1):
                parent = impacts._run_with_connection(connection, previous_id)
                checkpoint = connection.execute(
                    "SELECT checkpoint_sha256 FROM dependency_impact_audit_events WHERE project_id=? AND run_id=? "
                    "ORDER BY sequence DESC LIMIT 1 OFFSET 1",
                    (self._project, previous_id),
                ).fetchone()
                if (
                    link[0] != sequence
                    or link[1] != previous_id
                    or parent.state != "cancelled"
                    or checkpoint is None
                    or checkpoint[0] != link[3]
                ):
                    raise ReconciliationProblem("reconciliation-integrity-invalid")
                previous_id = str(link[2])
            if previous_id != leaf_id:
                raise ReconciliationProblem("reconciliation-integrity-invalid")
            # Check every saved child, including historical continuations; a
            # substituted middle link cannot be hidden by an authentic leaf.
            for run_id in (root_id, *(str(link[2]) for link in links)):
                seal = connection.execute(
                    "SELECT run_sha256 FROM reconciliation_impact_seals WHERE project_id=? AND run_id=?",
                    (self._project, run_id),
                ).fetchone()
                if seal is None or seal[0] != self._impact_snapshot_sha256(connection, run_id):
                    raise ReconciliationProblem("reconciliation-integrity-invalid")
                impacts._verify_saved_run(connection, run_id)
                run = impacts._run_with_connection(connection, run_id)
                saved = impacts._change_with_connection(connection, run.change_id)
                bounds = connection.execute(
                    "SELECT batch_size,max_nodes,max_edges,max_depth,max_path_samples,max_legacy_samples "
                    "FROM dependency_impact_runs WHERE project_id=? AND run_id=?",
                    (self._project, run_id),
                ).fetchone()
                if (
                    replace(saved, change_id=root_change.change_id, idempotency_key=root_change.idempotency_key)
                    != root_change
                    or tuple(bounds) != (100, 20000, 100000, 128, 64, 100)
                    or impacts._decisions_with_connection(connection, run_id)
                ):
                    raise ReconciliationProblem("reconciliation-integrity-invalid")
            current = impacts._run_with_connection(connection, leaf_id)
            change = impacts._change_with_connection(connection, current.change_id)
            preview = impacts._preview_with_connection(
                connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
            )
            saved_graph = connection.execute(
                "SELECT graph_sha256 FROM dependency_impact_runs WHERE project_id=? AND run_id=?",
                (self._project, leaf_id),
            ).fetchone()[0]
            if preview.graph_sha256 != saved_graph:
                if len(links) >= 128:
                    raise ReconciliationProblem("reconciliation-impact-continuation-limit")
                change_id, child_id = new_uuid_v7(), new_uuid_v7()
                fresh = replace(change, change_id=change_id, idempotency_key="reconciliation-impact-" + change_id)
                fresh_preview = impacts._preview_with_connection(
                    connection, fresh, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
                )
                impacts._begin_with_connection(
                    connection, fresh, preview_sha256=fresh_preview.preview_sha256, run_id=child_id, batch_size=100
                )
                self._seal_impact(connection, child_id)
                _publication_step("impact-continuation-created")
                connection.execute(
                    "INSERT INTO reconciliation_impact_continuations VALUES (?,?,?,?,?,?)",
                    (root_id, self._project, len(links) + 1, leaf_id, child_id, current.checkpoint_sha256),
                )
                _publication_step("impact-continuation-linked")
                impacts._cancel_with_connection(
                    connection,
                    leaf_id,
                    expected_checkpoint_sha256=current.checkpoint_sha256,
                    occurred_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                )
                _publication_step("impact-predecessor-cancelled")
                return True
            # Preserve the engine's authority/preview validation even when the
            # graph is unchanged. Never translate a different conflict into retry.
            impacts._verify_run_snapshot(connection, leaf_id)
        impacts.advance(current.run_id, expected_checkpoint_sha256=current.checkpoint_sha256)
        return True

    def _publish_impacts(
        self, connection: CanonicalConnection, changes: tuple[DependencyChange, ...]
    ) -> tuple[str, ...]:
        impact_repository = _SqliteDependencyImpactRepository(self._database, self._project)
        runs = []
        for change in changes:
            preview = impact_repository._preview_with_connection(
                connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
            )
            run_id = new_uuid_v7()
            impact_repository._begin_with_connection(
                connection, change, preview_sha256=preview.preview_sha256, run_id=run_id, batch_size=100
            )
            self._seal_impact(connection, run_id)
            runs.append(run_id)
        return tuple(runs)

    def review(
        self, command: ReviewCommand, *, actor: ReconciliationActor, resolve: ReconciliationSourceResolver
    ) -> ReviewOutcome:
        command = ReviewCommand.model_validate(command)
        self._validate_actor(actor)
        prepared, collect = self._source_snapshot(resolve)
        with self._transaction(write=False) as (connection, aggregates):
            if self._review_replay(connection, command, actor, collect) is None:
                preview = self._review_preview(connection, aggregates, command.plan, actor, collect)
                if preview.preview_sha256 != command.expected_preview_sha256:
                    raise ReconciliationProblem("reconciliation-review-preview-stale")

        def resolved(address: SourceAddress) -> SourceAssertion:
            key = _digest(address.model_dump(mode="json"))
            if key not in prepared:
                raise ReconciliationProblem("reconciliation-concurrent-source-change")
            return prepared[key]

        with self._transaction(write=True) as (connection, aggregates):
            replay = self._review_replay(connection, command, actor, resolved)
            if replay is not None:
                return replay
            plan = command.plan
            preview = self._review_preview(connection, aggregates, plan, actor, resolved)
            if preview.preview_sha256 != command.expected_preview_sha256:
                raise ReconciliationProblem("reconciliation-review-preview-stale")
            previous = {state.work_id: aggregates.get_revision(state.revision_id) for state in plan.works}
            previous.update({alias.work_id: aggregates.get_revision(alias.revision_id) for alias in plan.aliases})
            states = {work: self._state(connection, work) for work in previous}
            members = set(plan.unassigned_assertion_revision_ids)
            members.update(member for state in plan.works for member in state.assertion_revision_ids)
            prior_decisions = {state.decision_revision_id for state in states.values() if state.decision_revision_id}
            decision = self._append(
                aggregates,
                sources=tuple(aggregates.get_revision(revision) for revision in sorted(members | prior_decisions)),
                historical_sources=tuple(previous[key] for key in sorted(previous)),
                actor=actor,
                digest=plan.fingerprint,
                label="Scholarly identity decision",
                kind="decision",
                adjudicated=True,
                payload_configuration="review-plan",
            )
            _publication_step("review-decision-created")
            outputs, changes, groups = [], [], {}
            for part in plan.partitions:
                current = previous.get(part.existing_work_id) if part.existing_work_id else None
                published = self._append(
                    aggregates,
                    sources=(
                        decision,
                        *tuple(aggregates.get_revision(revision) for revision in part.assertion_revision_ids),
                    ),
                    historical_sources=(current,) if current else (),
                    actor=actor,
                    digest=plan.fingerprint,
                    label="Canonical scholarly work",
                    current=current,
                    adjudicated=True,
                    payload_configuration="review-plan",
                )
                groups[part.group] = published.aggregate_id
                outputs.append(
                    WorkState(
                        work_id=published.aggregate_id,
                        revision_id=published.revision_id,
                        previous_revision_id=current.revision_id if current else None,
                        disposition="active",
                        alias_target=None,
                        assertion_revision_ids=part.assertion_revision_ids,
                        decision_revision_id=decision.revision_id,
                    )
                )
                if current:
                    changes.append(self._change(current, published, actor))
            for alias in plan.aliases:
                current = previous[alias.work_id]
                published = self._append(
                    aggregates,
                    sources=(decision,),
                    historical_sources=(current,),
                    actor=actor,
                    digest=plan.fingerprint,
                    label="Canonical scholarly alias",
                    current=current,
                    adjudicated=True,
                    payload_configuration="review-plan",
                )
                outputs.append(
                    WorkState(
                        work_id=published.aggregate_id,
                        revision_id=published.revision_id,
                        previous_revision_id=current.revision_id,
                        disposition="alias",
                        alias_target=groups[alias.target_group],
                        assertion_revision_ids=(),
                        decision_revision_id=decision.revision_id,
                    )
                )
                changes.append(self._change(current, published, actor))
            _publication_step("review-work-created")
            for state in outputs:
                self._publish_state(connection, state)
            for member in members:
                if self._assignment(connection, member) is None:
                    raise ReconciliationProblem("reconciliation-integrity-invalid")
            _publication_step("review-membership-created")
            runs = self._publish_impacts(connection, tuple(changes))
            _publication_step("review-impacts-created")
            outcome = ReviewOutcome(
                decision_id=decision.aggregate_id,
                decision_revision_id=decision.revision_id,
                command_id=command.command_id,
                plan_sha256=plan.fingerprint,
                work_states=tuple(outputs),
                dependency_run_ids=runs,
            )
            command_sha = _digest([self._project, actor.actor_id, command.model_dump(mode="json", by_alias=True)])
            connection.execute(
                "INSERT INTO reconciliation_review_decisions "
                "(revision_id,project_id,command_id,actor_id,command_sha256,"
                "plan_sha256,intent_sha256,policy_sha256,plan_json,outcome_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    decision.revision_id,
                    self._project,
                    command.command_id,
                    actor.actor_id,
                    command_sha,
                    plan.fingerprint,
                    actor.intent_sha256,
                    actor.policy_sha256,
                    plan.model_dump_json(by_alias=True),
                    outcome.model_dump_json(by_alias=True),
                ),
            )
            _publication_step("review-command-created")
            return outcome
