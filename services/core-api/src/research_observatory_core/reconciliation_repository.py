"""Atomic scholarly assertions and Work revisions in the canonical database.

The caller holds the current project lifecycle/authority fence. No caller DTO
is a trusted SourceAssertion: every source and candidate is resolved again in
the authority-fenced snapshot before publication, replay or inspection.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.reconciliation import ReconciliationActor, ReconciliationSourceResolver
from .ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    MaterialDependency,
    RepositoryProblem,
)
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
from .reconciliation.exact import IdentifierAssertion, MatchAssessment, assess_match, exact_keys, select_field
from .reconciliation.identifiers import NORMALIZER_VERSION
from .repositories import _UNIT_OF_WORKS, _projection_content_sha256, _SqliteAggregateRepository
from .storage import (
    _DATABASE_ERRORS,
    CanonicalConnection,
    StorageProblem,
    _normalize_utc_millisecond,
    open_canonical_database,
)

_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_MAX_SOURCE_COUNT = 512


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

    def _source_snapshot(
        self, resolve: ReconciliationSourceResolver
    ) -> tuple[dict[str, SourceAssertion], ReconciliationSourceResolver]:
        prepared: dict[str, SourceAssertion] = {}
        byte_length = 0

        def collect(address: SourceAddress) -> SourceAssertion:
            nonlocal byte_length
            key = _digest(address.model_dump(mode="json"))
            if key not in prepared:
                if len(prepared) >= _MAX_SOURCE_COUNT:
                    raise ReconciliationProblem("reconciliation-source-limit")
                source = self._resolve(address, resolve)
                byte_length += len(source.model_dump_json(by_alias=True).encode())
                if byte_length > _MAX_SOURCE_BYTES:
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

    def _work_sources(
        self, connection: CanonicalConnection, work_id: str, resolve: ReconciliationSourceResolver
    ) -> tuple[ReconciliationInspection, ...]:
        rows = connection.execute(
            "SELECT assertion_revision_id FROM reconciliation_work_revisions "
            "WHERE project_id=? AND work_id=? ORDER BY revision_id LIMIT 257",
            (self._project, work_id),
        ).fetchall()
        if not 1 <= len(rows) <= 256:
            raise ReconciliationProblem("reconciliation-work-limit")
        sources = tuple(self._authorized_load(connection, row[0], resolve) for row in rows)
        if any(source.result.work_id != work_id for source in sources):
            raise ReconciliationProblem("reconciliation-integrity-invalid")
        return sources

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
                if work is None:
                    unresolved = True
                else:
                    works.add(work)
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
    ) -> AggregateRevision:
        revision = new_uuid_v7()
        dependencies = tuple(
            MaterialDependency(
                new_uuid_v7(),
                "source-revision",
                "direct",
                source.revision_id,
                None,
                None,
                _projection_content_sha256(source),
                "dependency.material.v1",
                "1.0.0",
            )
            for source in sources
        )
        for name, fingerprint in (
            ("assertion-payload", digest),
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
        return aggregates.append(
            AggregateRevisionDraft(
                revision_id=revision,
                aggregate_id=current.aggregate_id if current else new_uuid_v7(),
                aggregate_kind="record",
                created_at=current.created_at if current else actor.occurred_at,
                modified_at=actor.occurred_at,
                display_label_observed=label,
                display_label_normalized=None,
                knowledge_status="disputed" if disputed else "inferred",
                rights_status="unknown",
                dependency_coverage="complete",
                provenance_inputs=sources,
                material_dependencies=dependencies,
            ),
            AtomicRepositoryEvent(
                event_id=new_uuid_v7(),
                outbox_id=new_uuid_v7(),
                event_type="record.reconciled",
                occurred_at=actor.occurred_at,
                available_at=actor.occurred_at,
                trace_id=actor.trace_id,
                actor_type="human",
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
        command_sha = _digest([self._project, actor.actor_id, address_sha, NORMALIZER_VERSION])
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
                saved = self._authorized_load(connection, previous[0], collect)
                if saved.result.work_id is not None:
                    self._work_sources(connection, saved.result.work_id, collect)

        def resolved(address: SourceAddress) -> SourceAssertion:
            key = _digest(address.model_dump(mode="json"))
            if key not in prepared:
                raise ReconciliationProblem("reconciliation-concurrent-source-change")
            return prepared[key]

        with self._transaction(write=True) as (connection, aggregates):
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
                if prior.result.work_id is not None:
                    self._work_sources(connection, prior.result.work_id, resolved)
                return prior.result
            prior = connection.execute(
                "SELECT revision_id FROM reconciliation_assertions WHERE project_id=? AND address_sha256=?",
                (self._project, address_sha),
            ).fetchone()
            if prior is not None:
                saved = self._authorized_load(connection, prior[0], resolved)
                if saved.result.work_id is not None:
                    self._work_sources(connection, saved.result.work_id, resolved)
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
                if assessment.disposition != "review-required":
                    if (
                        current is not None
                        and len(self._work_sources(connection, current.aggregate_id, resolved)) >= 256
                    ):
                        raise ReconciliationProblem("reconciliation-work-limit")
                    work = self._append(
                        aggregates,
                        sources=(created,) + ((current,) if current else ()),
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
                    connection.execute(
                        "INSERT INTO reconciliation_work_revisions (revision_id, project_id, work_id, "
                        "assertion_revision_id, previous_revision_id) VALUES (?, ?, ?, ?, ?)",
                        (
                            work.revision_id,
                            self._project,
                            work.aggregate_id,
                            created.revision_id,
                            current.revision_id if current else None,
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
            connection.execute(
                "INSERT INTO reconciliation_commands VALUES (?, ?, ?, ?, ?)",
                (command_id, self._project, actor.actor_id, command_sha, result.assertion_revision_id),
            )
            _publication_step("command-created")
            return result

    def inspect(self, revision_id: str, *, resolve: ReconciliationSourceResolver) -> ReconciliationInspection:
        if not is_uuid_v7(revision_id):
            raise ReconciliationProblem("reconciliation-address-invalid")
        _, collect = self._source_snapshot(resolve)
        with self._transaction(write=False) as (connection, aggregates):
            result = self._authorized_load(connection, revision_id, collect)
            current = aggregates.get(result.result.work_id) if result.result.work_id else None
            if result.result.work_id and current is None:
                raise ReconciliationProblem("reconciliation-integrity-invalid")
            sources = (
                self._work_sources(connection, result.result.work_id, collect) if result.result.work_id else (result,)
            )
            if current is not None and current.revision_id not in {
                source.result.work_revision_id for source in sources
            }:
                raise ReconciliationProblem("reconciliation-integrity-invalid")
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
            result = ReconciliationInspection(
                result=result.result,
                assertion=result.assertion,
                canonical_work=CanonicalWorkReference(work_id=current.aggregate_id, revision_id=current.revision_id)
                if current is not None
                else None,
                canonical_fields=tuple(selections),
            )
            if len(result.model_dump_json(by_alias=True).encode()) > 4 * 1024 * 1024:
                raise ReconciliationProblem("reconciliation-inspection-limit")
            return result
