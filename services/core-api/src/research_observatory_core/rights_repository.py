"""Protected, append-only, record-specific rights policy persistence.

An exact retained reconciliation assertion anchors a source-held metadata copy.
Policy writes, provenance, outbox, exact corpus rechecks, and dependency-impact
intent share one canonical writer transaction. This module never reads source
content or treats a reported license as an entitlement.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from pydantic import ValidationError

from .connectors.contracts import ConnectorRecord, SourceObservation, SourceTerms
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.repositories import (
    DEFAULT_DEPENDENCY_IMPACT_LIMITS,
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyChange,
    DependencyImpactLimitExceeded,
    MaterialDependency,
    RepositoryProblem,
)
from .ports.rights import (
    RightsActor,
    RightsOutputRecheckMarker,
    RightsOutputRecheckState,
    RightsPermissionDraft,
    RightsProblem,
    RightsRecheckScope,
)
from .reconciliation.contracts import SourceAssertion
from .repositories import (
    _UNIT_OF_WORKS,
    _impact_checkpoint_sha256,
    _projection_content_sha256,
    _record_dependency_stale_batch,
    _SqliteAggregateRepository,
    _SqliteDependencyImpactRepository,
)
from .rights_policy import (
    RightsDecision,
    RightsPermission,
    RightsPolicyRevision,
    RightsRequest,
    RightsSourceObservation,
    RightsSubject,
    RightsUse,
    evaluate_rights,
)
from .storage import (
    _DATABASE_ERRORS,
    CanonicalConnection,
    StorageProblem,
    _normalize_utc_millisecond,
    open_canonical_database,
)

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TRACE = re.compile(r"[0-9a-f]{32}\Z")
_MAX_EXACT_RECHECKS = 20_000
_GENERIC_RECHECK_BUDGET_SECONDS = 2.0
_GENERIC_RECHECK_PROGRESS_CALLBACKS = 20_000


class _ReachabilityBudgetExceeded(Exception):
    """Internal stop signal; the published pending scope remains authoritative."""


def _generic_budget_exceeded(deadline: float, callbacks: int) -> bool:
    return monotonic() >= deadline or callbacks >= _GENERIC_RECHECK_PROGRESS_CALLBACKS


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _publication_step(_step: str) -> None:
    """Fault seam: a failure rolls the entire rights publication back."""


class SqliteRightsRepository:
    def __init__(
        self,
        database: Path,
        project_id: str,
        *,
        connector_record_resolver: Callable[[str, int], ConnectorRecord] | None = None,
    ) -> None:
        if not database.is_absolute() or not project_id:
            raise RightsProblem("rights-storage-invalid")
        self._database = database
        self._project = project_id
        self._connector_record_resolver = connector_record_resolver

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
        except (*_DATABASE_ERRORS, StorageProblem, RepositoryProblem, OSError):
            raise RightsProblem("rights-storage-invalid") from None
        finally:
            if token is not None:
                _UNIT_OF_WORKS.unregister(token)
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    @staticmethod
    def _actor(actor: RightsActor, *, command_id: str | None = None, command_sha256: str | None = None) -> None:
        if (
            not is_uuid_v7(actor.actor_id)
            or actor.actor_type != "human"
            or _TRACE.fullmatch(actor.trace_id) is None
            or not is_uuid_v7(actor.intent_revision_id)
            or _HASH.fullmatch(actor.intent_sha256) is None
            or _HASH.fullmatch(actor.policy_sha256) is None
            or (command_id is not None and not is_uuid_v7(command_id))
            or (command_sha256 is not None and _HASH.fullmatch(command_sha256) is None)
        ):
            raise RightsProblem("rights-command-invalid")
        try:
            _normalize_utc_millisecond(actor.occurred_at)
        except ValueError:
            raise RightsProblem("rights-command-invalid") from None

    def _authority(self, connection: CanonicalConnection, actor: RightsActor) -> None:
        # Avoid a second implementation of the existing current Intent/privacy
        # writer check. The local import keeps corpus's rights recheck acyclic.
        from .corpus.membership import CorpusProblem
        from .corpus_repository import SqliteCorpusRepository

        try:
            SqliteCorpusRepository(self._database, self._project)._authority(connection, actor)
        except CorpusProblem:
            raise RightsProblem("rights-authority-changed") from None

    def _retained_source(self, connection: CanonicalConnection, subject: RightsSubject) -> SourceAssertion:
        if subject.project_id != self._project:
            raise RightsProblem("rights-source-mismatch")
        row = connection.execute(
            "SELECT source_revision_id,address_revision_id,address_sha256,payload_sha256,assertion_json "
            "FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
            (self._project, subject.source_assertion_revision_id),
        ).fetchone()
        if row is None:
            raise RightsProblem("rights-subject-unavailable")
        try:
            source = SourceAssertion.model_validate_json(str(row[4]))
        except ValidationError:
            raise RightsProblem("rights-source-integrity-invalid") from None
        address_hash = _digest(subject.address.model_dump(mode="json"))
        if (
            source.project_id != self._project
            or source.address != subject.address
            or source.source_revision_id != row[0]
            or source.address.revision_id != row[1]
            or str(row[2]) != address_hash
            or str(row[3]) != _digest(source.model_dump(mode="json", by_alias=True))
        ):
            raise RightsProblem("rights-source-mismatch")
        return source

    def source_metadata_subject_with_connection(
        self, connection: CanonicalConnection, source: SourceAssertion
    ) -> RightsSubject:
        """Resolve one retained source record, never a connector page as a whole."""

        if not connection.in_transaction:
            raise RightsProblem("rights-transaction-required")
        try:
            source = SourceAssertion.model_validate(source)
        except ValidationError:
            raise RightsProblem("rights-source-mismatch") from None
        if source.project_id != self._project:
            raise RightsProblem("rights-source-mismatch")
        row = connection.execute(
            "SELECT revision_id,assertion_json FROM reconciliation_assertions WHERE project_id=? AND address_sha256=?",
            (self._project, _digest(source.address.model_dump(mode="json"))),
        ).fetchone()
        if row is None:
            raise RightsProblem("rights-subject-unavailable")
        try:
            retained = SourceAssertion.model_validate_json(str(row[1]))
        except ValidationError:
            raise RightsProblem("rights-source-integrity-invalid") from None
        if retained != source:
            raise RightsProblem("rights-source-mismatch")
        return RightsSubject(
            project_id=self._project,
            source_assertion_revision_id=str(row[0]),
            address=source.address,
            copy_id=str(row[0]),
            copy_location="local-source",
            resource_class="metadata",
        )

    def _validate_subject_copy(self, connection: CanonicalConnection, subject: RightsSubject) -> None:
        # A staged attachment candidate is an exact project-held copy witness.
        # It is not a permission: full-text use still needs a current policy.
        if (
            subject.copy_id != subject.source_assertion_revision_id
            or subject.copy_location != "local-source"
            or subject.resource_class != "metadata"
        ):
            if subject.copy_location == "local-project-object" and subject.resource_class == "full-text":
                row = connection.execute(
                    "SELECT 1 FROM document_attachment_candidates c WHERE c.project_id=? "
                    "AND c.candidate_id=? AND c.source_assertion_revision_id=? "
                    "AND NOT EXISTS (SELECT 1 FROM document_attachment_cancellations x "
                    "WHERE x.candidate_id=c.candidate_id) LIMIT 1",
                    (self._project, subject.copy_id, subject.source_assertion_revision_id),
                ).fetchone()
                if row is not None:
                    return
            raise RightsProblem("rights-copy-unavailable")

    def _source_observation(
        self,
        source: SourceAssertion,
        assertion_revision_id: str,
        connector_record: ConnectorRecord | None = None,
    ) -> RightsSourceObservation:
        """Project only exact retained source terms, never a use permission."""

        address = source.address
        if address.kind == "import-member":
            if source.provider != "local-import":
                raise RightsProblem("rights-observation-source-mismatch")
            absent = SourceObservation(state="not-reported", value=None)
            terms = SourceTerms(license=absent, terms=absent, access="unknown")
            retrieved_at = None
        else:
            record = connector_record
            if record is None:
                raise RightsProblem("rights-observation-unavailable")
            if (
                source.source_revision_id != address.revision_id
                or record.provider_id != source.provider
                or hashlib.sha256(record.model_dump_json(by_alias=True).encode()).hexdigest() != source.source_sha256
            ):
                raise RightsProblem("rights-observation-source-mismatch")
            terms, retrieved_at = record.terms, record.retrieved_at
        try:
            return RightsSourceObservation(
                project_id=self._project,
                source_assertion_revision_id=assertion_revision_id,
                address=address,
                source_revision_id=source.source_revision_id,
                source_sha256=source.source_sha256,
                provider=source.provider,
                terms=terms,
                retrieved_at=retrieved_at,
            )
        except ValidationError:
            raise RightsProblem("rights-observation-source-mismatch") from None

    def _resolve_connector_record(self, subject: RightsSubject) -> ConnectorRecord | None:
        if subject.address.kind != "connector-record":
            return None
        resolver = self._connector_record_resolver
        if resolver is None:
            raise RightsProblem("rights-observation-unavailable")
        try:
            return ConnectorRecord.model_validate(resolver(subject.address.revision_id, subject.address.ordinal))
        except Exception:
            raise RightsProblem("rights-observation-unavailable") from None

    def _validate_policy_evidence(
        self, policy: RightsPolicyRevision, actor: RightsActor, source: SourceAssertion
    ) -> None:
        allowed = {
            policy.subject.source_assertion_revision_id,
            source.source_revision_id,
            source.address.revision_id,
        }
        for permission in policy.permissions:
            if permission.basis == "source-observation":
                raise RightsProblem("rights-observation-unverified")
            if permission.basis == "verified-entitlement":
                raise RightsProblem("rights-entitlement-unverified")
            if permission.basis == "researcher-confirmed" and permission.asserted_by_actor_id != actor.actor_id:
                raise RightsProblem("rights-assertor-mismatch")
            if (
                any(revision_id not in allowed for revision_id in permission.evidence_revision_ids)
                # No typed, retained license-observation witness is linked to an
                # exact record here. A generic source or page revision is not one.
                or permission.license_observation_revision_id is not None
                or permission.entitlement_revision_id is not None
            ):
                raise RightsProblem("rights-evidence-unrelated")

    def _load_revision(self, connection: CanonicalConnection, revision_id: str) -> RightsPolicyRevision:
        row = connection.execute(
            "SELECT r.policy_id,r.subject_sha256,r.predecessor_revision_id,r.revision_number,"
            "r.policy_json,r.policy_sha256,s.subject_json,a.revision "
            "FROM rights_policy_revisions r JOIN rights_policy_subjects s "
            "ON s.project_id=r.project_id AND s.subject_sha256=r.subject_sha256 AND s.policy_id=r.policy_id "
            "JOIN aggregate_revisions a ON a.revision_id=r.revision_id AND a.project_id=r.project_id "
            "WHERE r.project_id=? AND r.revision_id=?",
            (self._project, revision_id),
        ).fetchone()
        if row is None:
            raise RightsProblem("rights-policy-integrity-invalid")
        try:
            policy = RightsPolicyRevision.model_validate_json(str(row[4]))
            subject = RightsSubject.model_validate_json(str(row[6]))
        except ValidationError:
            raise RightsProblem("rights-policy-integrity-invalid") from None
        if (
            policy.revision_id != revision_id
            or policy.predecessor_revision_id != row[2]
            or policy.subject != subject
            or _digest(subject.model_dump(mode="json", by_alias=True)) != row[1]
            or _digest(policy.model_dump(mode="json", by_alias=True)) != row[5]
            or int(row[3]) != int(row[7])
        ):
            raise RightsProblem("rights-policy-integrity-invalid")
        return policy

    def current_with_connection(
        self, connection: CanonicalConnection, subject: RightsSubject
    ) -> RightsPolicyRevision | None:
        """Read the exact current snapshot inside the caller's fenced transaction."""

        if not connection.in_transaction:
            raise RightsProblem("rights-transaction-required")
        try:
            subject = RightsSubject.model_validate(subject)
        except ValidationError:
            raise RightsProblem("rights-source-mismatch") from None
        self._retained_source(connection, subject)
        self._validate_subject_copy(connection, subject)
        subject_hash = _digest(subject.model_dump(mode="json", by_alias=True))
        mapping = connection.execute(
            "SELECT policy_id,subject_json FROM rights_policy_subjects WHERE project_id=? AND subject_sha256=?",
            (self._project, subject_hash),
        ).fetchone()
        if mapping is None:
            return None
        try:
            saved_subject = RightsSubject.model_validate_json(str(mapping[1]))
        except ValidationError:
            raise RightsProblem("rights-policy-integrity-invalid") from None
        if saved_subject != subject:
            raise RightsProblem("rights-policy-integrity-invalid")
        head = connection.execute(
            "SELECT revision_id,revision_number FROM rights_policy_revisions "
            "WHERE project_id=? AND subject_sha256=? ORDER BY revision_number DESC LIMIT 1",
            (self._project, subject_hash),
        ).fetchone()
        aggregate_head = connection.execute(
            "SELECT revision_id,revision FROM aggregate_revisions WHERE project_id=? AND aggregate_id=? "
            "ORDER BY revision DESC LIMIT 1",
            (self._project, str(mapping[0])),
        ).fetchone()
        if head is None or aggregate_head is None or tuple(head) != tuple(aggregate_head):
            raise RightsProblem("rights-policy-integrity-invalid")
        policy = self._load_revision(connection, str(head[0]))
        if policy.subject != subject:
            raise RightsProblem("rights-policy-integrity-invalid")
        return policy

    def current(self, subject: RightsSubject, *, actor: RightsActor) -> RightsPolicyRevision | None:
        self._actor(actor)
        with self._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
            return self.current_with_connection(connection, subject)

    def _recheck_scope_with_connection(
        self, connection: CanonicalConnection, policy: RightsPolicyRevision
    ) -> RightsRecheckScope:
        """An older pending scope takes precedence over the current complete row."""

        subject = policy.subject
        subject_hash = _digest(subject.model_dump(mode="json", by_alias=True))
        revision_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM rights_policy_revisions WHERE project_id=? AND subject_sha256=?",
                (self._project, subject_hash),
            ).fetchone()[0]
        )
        scope_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM rights_policy_recheck_scopes WHERE project_id=? AND subject_sha256=?",
                (self._project, subject_hash),
            ).fetchone()[0]
        )
        if revision_count != scope_count:
            raise RightsProblem("rights-impact-integrity-invalid")
        columns = (
            "SELECT s.rights_revision_id,s.source_assertion_revision_id,s.exact_state,s.generic_state,"
            "s.disposition,s.pending_reason,s.reason,s.occurred_at,"
            "exact_receipt.completion_id,generic_receipt.completion_id "
            "FROM rights_policy_recheck_scopes s JOIN rights_policy_revisions r "
            "ON r.project_id=s.project_id AND r.revision_id=s.rights_revision_id "
            "LEFT JOIN rights_policy_recheck_completions exact_receipt "
            "ON exact_receipt.project_id=s.project_id "
            "AND exact_receipt.rights_revision_id=s.rights_revision_id AND exact_receipt.dimension='exact' "
            "LEFT JOIN rights_policy_recheck_completions generic_receipt "
            "ON generic_receipt.project_id=s.project_id "
            "AND generic_receipt.rights_revision_id=s.rights_revision_id AND generic_receipt.dimension='generic' "
            "WHERE s.project_id=? AND s.subject_sha256=? "
        )
        row = connection.execute(
            columns + "AND ((s.exact_state='pending' AND exact_receipt.completion_id IS NULL) "
            "OR (s.generic_state='pending' AND generic_receipt.completion_id IS NULL)) "
            "ORDER BY r.revision_number LIMIT 1",
            (self._project, subject_hash),
        ).fetchone()
        if row is None:
            row = connection.execute(
                columns + "AND s.rights_revision_id=?",
                (self._project, subject_hash, policy.revision_id),
            ).fetchone()
        if row is None or row[1] != subject.source_assertion_revision_id:
            raise RightsProblem("rights-impact-integrity-invalid")
        exact_state = "complete" if row[2] == "complete" or row[8] is not None else "pending"
        generic_state = "complete" if row[3] == "complete" or row[9] is not None else "pending"
        pending_reason = (
            "exact-and-generic-limit"
            if exact_state == "pending" and generic_state == "pending"
            else "exact-limit"
            if exact_state == "pending"
            else "generic-limit"
            if generic_state == "pending"
            else None
        )
        disposition = "complete" if pending_reason is None else "pending"
        if disposition == "complete" and row[0] != policy.revision_id:
            raise RightsProblem("rights-impact-integrity-invalid")
        if (row[4] == "pending") != (row[2] == "pending" or row[3] == "pending"):
            raise RightsProblem("rights-impact-integrity-invalid")
        try:
            return RightsRecheckScope.model_validate(
                {
                    "rights_revision_id": str(row[0]),
                    "subject": subject,
                    "exact_state": exact_state,
                    "generic_state": generic_state,
                    "disposition": disposition,
                    "pending_reason": pending_reason,
                    "reason": str(row[6]),
                    "occurred_at": str(row[7]),
                }
            )
        except ValidationError:
            raise RightsProblem("rights-impact-integrity-invalid") from None

    def recheck_scope(self, subject: RightsSubject, *, actor: RightsActor) -> RightsRecheckScope | None:
        self._actor(actor)
        with self._transaction(write=False) as (connection, _):
            self._authority(connection, actor)
            policy = self.current_with_connection(connection, subject)
            return None if policy is None else self._recheck_scope_with_connection(connection, policy)

    def output_rechecks(self, output_revision_id: str, *, actor: RightsActor) -> RightsOutputRecheckState:
        """Inspect bounded immutable rights markers, including unmaterialized propagation risk."""

        self._actor(actor)
        if not is_uuid_v7(output_revision_id):
            raise RightsProblem("rights-output-invalid")
        markers: tuple[RightsOutputRecheckMarker, ...] = ()
        truncated = False
        try:
            with self._transaction(write=False) as (connection, _):
                self._authority(connection, actor)
                if (
                    connection.execute(
                        "SELECT 1 FROM aggregate_revisions WHERE project_id=? AND revision_id=?",
                        (self._project, output_revision_id),
                    ).fetchone()
                    is None
                ):
                    raise RightsProblem("rights-output-unavailable")
                found: list[RightsOutputRecheckMarker] = []
                for row in connection.execute(
                    "SELECT recheck_id,rights_revision_id,source_assertion_revision_id,path_id,"
                    "reason,disposition,occurred_at "
                    "FROM rights_policy_rechecks WHERE project_id=? AND output_revision_id=? "
                    "ORDER BY occurred_at,recheck_id LIMIT 101",
                    (self._project, output_revision_id),
                ).fetchall():
                    found.append(
                        RightsOutputRecheckMarker(
                            marker_id=str(row[0]),
                            kind="exact",
                            rights_revision_id=str(row[1]),
                            source_assertion_revision_id=str(row[2]),
                            path_id=str(row[3]),
                            reason="RIGHTS_POLICY",
                            disposition="requires-review",
                            occurred_at=str(row[6]),
                        )
                    )
                for row in connection.execute(
                    "SELECT marked.recheck_id,marked.rights_revision_id,scope.source_assertion_revision_id,"
                    "marked.reason,marked.disposition,marked.occurred_at "
                    "FROM rights_policy_generic_rechecks marked JOIN rights_policy_recheck_scopes scope "
                    "ON scope.project_id=marked.project_id AND scope.rights_revision_id=marked.rights_revision_id "
                    "WHERE marked.project_id=? AND marked.output_revision_id=? "
                    "ORDER BY marked.occurred_at,marked.recheck_id LIMIT 101",
                    (self._project, output_revision_id),
                ).fetchall():
                    found.append(
                        RightsOutputRecheckMarker(
                            marker_id=str(row[0]),
                            kind="generic",
                            rights_revision_id=str(row[1]),
                            source_assertion_revision_id=str(row[2]),
                            path_id=None,
                            reason="RIGHTS_POLICY",
                            disposition="requires-review",
                            occurred_at=str(row[5]),
                        )
                    )
                for row in connection.execute(
                    "SELECT path_id,source_assertion_revision_id,reason,disposition,detected_at "
                    "FROM rights_legacy_output_rechecks WHERE project_id=? AND output_revision_id=? "
                    "ORDER BY detected_at,path_id LIMIT 101",
                    (self._project, output_revision_id),
                ).fetchall():
                    marker_id = "legacy:" + _digest(
                        {"projectId": self._project, "outputRevisionId": output_revision_id, "pathId": str(row[0])}
                    )
                    found.append(
                        RightsOutputRecheckMarker(
                            marker_id=marker_id,
                            kind="legacy",
                            rights_revision_id=None,
                            source_assertion_revision_id=None if row[1] is None else str(row[1]),
                            path_id=str(row[0]),
                            reason="RIGHTS_POLICY",
                            disposition="requires-review",
                            occurred_at=str(row[4]),
                        )
                    )
                found.sort(key=lambda marker: (marker.occurred_at, marker.kind, marker.marker_id))
                truncated = len(found) > 100
                markers = tuple(found[:100])
                pending = self._pending_exact_output_with_connection(
                    connection, output_revision_id
                ) or self._pending_generic_output_with_connection(connection, output_revision_id)
                return RightsOutputRecheckState(
                    output_revision_id=output_revision_id,
                    markers=markers,
                    propagation_pending=pending,
                    propagation_unknown=False,
                    truncated=truncated,
                )
        except _ReachabilityBudgetExceeded:
            return RightsOutputRecheckState(
                output_revision_id=output_revision_id,
                markers=markers,
                propagation_pending=True,
                propagation_unknown=True,
                truncated=truncated,
            )

    def _pending_generic_output_with_connection(self, connection: CanonicalConnection, output_revision_id: str) -> bool:
        if (
            connection.execute(
                "SELECT 1 FROM rights_policy_recheck_scopes scope WHERE scope.project_id=? "
                "AND scope.generic_state='pending' AND NOT EXISTS ("
                "SELECT 1 FROM rights_policy_recheck_completions receipt "
                "WHERE receipt.project_id=scope.project_id AND receipt.rights_revision_id=scope.rights_revision_id "
                "AND receipt.dimension='generic') LIMIT 1",
                (self._project,),
            ).fetchone()
            is None
        ):
            return False
        deadline = monotonic() + _GENERIC_RECHECK_BUDGET_SECONDS
        callbacks = 0

        def interrupted() -> bool:
            nonlocal callbacks
            callbacks += 1
            return _generic_budget_exceeded(deadline, callbacks)

        try:
            with connection.interrupt_when(interrupted):
                if _generic_budget_exceeded(deadline, callbacks):
                    raise _ReachabilityBudgetExceeded
                row = connection.execute(
                    "WITH RECURSIVE ancestors(revision_id) AS (SELECT ? UNION "
                    "SELECT dependency.dependency_revision_id FROM material_dependencies dependency "
                    "JOIN ancestors ON ancestors.revision_id=dependency.output_revision_id "
                    "WHERE dependency.project_id=? AND dependency.dependency_revision_id IS NOT NULL "
                    "AND dependency.relation_type IN ('direct','conditional')) "
                    "SELECT 1 FROM ancestors JOIN rights_policy_revisions revision "
                    "ON revision.project_id=? AND revision.predecessor_revision_id=ancestors.revision_id "
                    "JOIN rights_policy_recheck_scopes scope ON scope.project_id=revision.project_id "
                    "AND scope.rights_revision_id=revision.revision_id "
                    "WHERE scope.generic_state='pending' AND NOT EXISTS ("
                    "SELECT 1 FROM rights_policy_recheck_completions receipt "
                    "WHERE receipt.project_id=scope.project_id AND receipt.rights_revision_id=scope.rights_revision_id "
                    "AND receipt.dimension='generic') LIMIT 1",
                    (output_revision_id, self._project, self._project),
                ).fetchone()
                if _generic_budget_exceeded(deadline, callbacks):
                    raise _ReachabilityBudgetExceeded
                return row is not None
        except _DATABASE_ERRORS:
            if _generic_budget_exceeded(deadline, callbacks):
                raise _ReachabilityBudgetExceeded from None
            raise

    def _pending_exact_output_with_connection(self, connection: CanonicalConnection, output_revision_id: str) -> bool:
        rows = connection.execute(
            "SELECT scope.rights_revision_id FROM rights_policy_recheck_scopes scope "
            "JOIN rights_policy_revisions revision ON revision.project_id=scope.project_id "
            "AND revision.revision_id=scope.rights_revision_id "
            "WHERE scope.project_id=? AND scope.exact_state='pending' AND NOT EXISTS ("
            "SELECT 1 FROM rights_policy_recheck_completions receipt "
            "WHERE receipt.project_id=scope.project_id AND receipt.rights_revision_id=scope.rights_revision_id "
            "AND receipt.dimension='exact') ORDER BY revision.revision_number LIMIT 101",
            (self._project,),
        ).fetchall()
        if len(rows) > 100:
            raise _ReachabilityBudgetExceeded
        deadline = monotonic() + _GENERIC_RECHECK_BUDGET_SECONDS
        callbacks = 0

        def interrupted() -> bool:
            nonlocal callbacks
            callbacks += 1
            return _generic_budget_exceeded(deadline, callbacks)

        try:
            with connection.interrupt_when(interrupted):
                for row in rows:
                    if _generic_budget_exceeded(deadline, callbacks):
                        raise _ReachabilityBudgetExceeded
                    policy = self._load_revision(connection, str(row[0]))
                    source = self._retained_source(connection, policy.subject)
                    if self._exact_corpus_links(
                        connection,
                        policy,
                        source,
                        limit=1,
                        missing_only=True,
                        output_revision_id=output_revision_id,
                    ):
                        return True
                return False
        except _DATABASE_ERRORS:
            if _generic_budget_exceeded(deadline, callbacks):
                raise _ReachabilityBudgetExceeded from None
            raise

    def advance_rechecks(
        self, subject: RightsSubject, *, actor: RightsActor, batch_size: int = 1_000
    ) -> RightsRecheckScope | None:
        """Materialize one bounded exact or generic batch; complete only with DB proof."""

        self._actor(actor)
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 1_000:
            raise RightsProblem("rights-recheck-batch-invalid")
        try:
            return self._advance_rechecks_once(subject, actor=actor, batch_size=batch_size)
        except _ReachabilityBudgetExceeded:
            # An interrupted SQLite query may roll back its writer. Reopen a
            # protected read; never claim a batch or completion receipt.
            return self.recheck_scope(subject, actor=actor)

    def _advance_rechecks_once(
        self, subject: RightsSubject, *, actor: RightsActor, batch_size: int
    ) -> RightsRecheckScope | None:
        with self._transaction(write=True) as (connection, _):
            self._authority(connection, actor)
            current = self.current_with_connection(connection, subject)
            if current is None:
                return None
            subject_hash = _digest(current.subject.model_dump(mode="json", by_alias=True))
            row = connection.execute(
                "SELECT scope.rights_revision_id FROM rights_policy_recheck_scopes scope "
                "JOIN rights_policy_revisions revision ON revision.project_id=scope.project_id "
                "AND revision.revision_id=scope.rights_revision_id "
                "WHERE scope.project_id=? AND scope.subject_sha256=? AND scope.exact_state='pending' "
                "AND NOT EXISTS (SELECT 1 FROM rights_policy_recheck_completions receipt "
                "WHERE receipt.project_id=scope.project_id AND receipt.rights_revision_id=scope.rights_revision_id "
                "AND receipt.dimension='exact') "
                "ORDER BY revision.revision_number LIMIT 1",
                (self._project, subject_hash),
            ).fetchone()
            if row is not None:
                scoped = self._load_revision(connection, str(row[0]))
                if scoped.subject != current.subject:
                    raise RightsProblem("rights-impact-integrity-invalid")
                source = self._retained_source(connection, scoped.subject)
                now = _utcnow()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise RightsProblem("rights-clock-unavailable")
                occurred_at = now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                rows = self._exact_corpus_links(connection, scoped, source, limit=batch_size, missing_only=True)
                for output_revision_id, item_id, path_id in rows:
                    self._insert_exact_recheck(connection, scoped, output_revision_id, item_id, path_id, occurred_at)
                _publication_step("exact-recheck-batch-created")
                if not self._exact_corpus_links(connection, scoped, source, limit=1, missing_only=True):
                    connection.execute(
                        "INSERT INTO rights_policy_recheck_completions "
                        "(completion_id,rights_revision_id,project_id,dimension,actor_id,occurred_at) "
                        "VALUES (?,?,?,'exact',?,?)",
                        (new_uuid_v7(), scoped.revision_id, self._project, actor.actor_id, occurred_at),
                    )
                    _publication_step("exact-recheck-completed")
            else:
                generic = connection.execute(
                    "SELECT scope.rights_revision_id FROM rights_policy_recheck_scopes scope "
                    "JOIN rights_policy_revisions revision ON revision.project_id=scope.project_id "
                    "AND revision.revision_id=scope.rights_revision_id "
                    "WHERE scope.project_id=? AND scope.subject_sha256=? AND scope.generic_state='pending' "
                    "AND NOT EXISTS (SELECT 1 FROM rights_policy_recheck_completions receipt "
                    "WHERE receipt.project_id=scope.project_id AND receipt.rights_revision_id=scope.rights_revision_id "
                    "AND receipt.dimension='generic') "
                    "ORDER BY revision.revision_number LIMIT 1",
                    (self._project, subject_hash),
                ).fetchone()
                if generic is not None:
                    scoped = self._load_revision(connection, str(generic[0]))
                    if scoped.subject != current.subject or scoped.predecessor_revision_id is None:
                        raise RightsProblem("rights-impact-integrity-invalid")
                    now = _utcnow()
                    if now.tzinfo is None or now.utcoffset() is None:
                        raise RightsProblem("rights-clock-unavailable")
                    occurred_at = now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                    deadline = monotonic() + _GENERIC_RECHECK_BUDGET_SECONDS
                    callbacks = 0

                    def interrupted() -> bool:
                        nonlocal callbacks
                        callbacks += 1
                        return _generic_budget_exceeded(deadline, callbacks)

                    try:
                        with connection.interrupt_when(interrupted):
                            if _generic_budget_exceeded(deadline, callbacks):
                                raise _ReachabilityBudgetExceeded
                            for output_revision_id, parent_revision_id in self._missing_generic_outputs(
                                connection, scoped, limit=batch_size
                            ):
                                connection.execute(
                                    "INSERT INTO rights_policy_generic_rechecks "
                                    "(recheck_id,rights_revision_id,project_id,previous_revision_id,"
                                    "parent_revision_id,output_revision_id,reason,disposition,occurred_at) "
                                    "VALUES (?,?,?,?,?,?,'RIGHTS_POLICY','requires-review',?)",
                                    (
                                        new_uuid_v7(),
                                        scoped.revision_id,
                                        self._project,
                                        scoped.predecessor_revision_id,
                                        parent_revision_id,
                                        output_revision_id,
                                        occurred_at,
                                    ),
                                )
                            _publication_step("generic-recheck-batch-created")
                            if _generic_budget_exceeded(deadline, callbacks):
                                raise _ReachabilityBudgetExceeded
                            if not self._missing_generic_outputs(connection, scoped, limit=1):
                                connection.execute(
                                    "INSERT INTO rights_policy_recheck_completions "
                                    "(completion_id,rights_revision_id,project_id,dimension,actor_id,occurred_at) "
                                    "VALUES (?,?,?,'generic',?,?)",
                                    (new_uuid_v7(), scoped.revision_id, self._project, actor.actor_id, occurred_at),
                                )
                                _publication_step("generic-recheck-completed")
                    except _DATABASE_ERRORS:
                        if _generic_budget_exceeded(deadline, callbacks):
                            raise _ReachabilityBudgetExceeded from None
                        raise
            return self._recheck_scope_with_connection(connection, current)

    def evaluate_with_connection(
        self, connection: CanonicalConnection, request: RightsRequest, *, actor: RightsActor
    ) -> RightsDecision:
        self._actor(actor)
        try:
            request = RightsRequest.model_validate(request)
        except ValidationError:
            raise RightsProblem("rights-request-invalid") from None
        if request.actor_id != actor.actor_id:
            raise RightsProblem("rights-actor-mismatch")
        self._authority(connection, actor)
        source = self._retained_source(connection, request.subject)
        assertion_hash = _digest(source.model_dump(mode="json", by_alias=True))
        try:
            self._validate_subject_copy(connection, request.subject)
            supported_copy = True
        except RightsProblem as problem:
            if str(problem) != "rights-copy-unavailable":
                raise
            supported_copy = False
        policy = self.current_with_connection(connection, request.subject) if supported_copy else None
        decision = evaluate_rights(policy, request, now=_utcnow())
        if (
            policy is None
            and supported_copy
            and request.subject.address.kind == "import-member"
            and source.provider == "local-import"
            and request.use.action in {"store", "inspect", "derive", "index"}
            and request.use.purpose == "corpus-membership"
            and request.use.destination_kind == "local-project"
            and source.rights.permits(request.use.action)
        ):
            decision = RightsDecision.model_validate(
                decision.model_copy(
                    update={
                        "code": "allow",
                        "reason_code": "rights-legacy-import-confirmed",
                        "authority_kind": "legacy-import-bridge",
                        "governing_assertion_ids": (request.subject.source_assertion_revision_id,),
                        "source_assertion_sha256": assertion_hash,
                    }
                )
            )
        else:
            decision = RightsDecision.model_validate(
                decision.model_copy(update={"source_assertion_sha256": assertion_hash})
            )
        if policy is not None and decision.code == "allow":
            scope = self._recheck_scope_with_connection(connection, policy)
            if scope.disposition == "pending":
                decision = RightsDecision.model_validate(
                    decision.model_copy(update={"code": "unknown", "reason_code": "rights-impact-pending"})
                )
        if decision.code == "allow" and request.use.destination_kind != "local-project":
            # This policy governs source terms. Egress, export, and sharing
            # require their own current authority in the executing boundary.
            decision = RightsDecision.model_validate(
                decision.model_copy(
                    update={"code": "require-confirmation", "reason_code": "rights-further-authority-required"}
                )
            )
        self._insert_use_decision(
            connection,
            decision,
            actor=actor,
            event_kind="legacy-import-bridge" if decision.authority_kind == "legacy-import-bridge" else "evaluate",
        )
        return decision

    def _insert_use_decision(
        self,
        connection: CanonicalConnection,
        decision: RightsDecision,
        *,
        actor: RightsActor,
        event_kind: str,
    ) -> None:
        if (
            decision.actor_id != actor.actor_id
            or decision.subject.project_id != self._project
            or (event_kind == "denied-attempt" and decision.code == "allow")
            or event_kind not in {"evaluate", "denied-attempt", "legacy-import-bridge"}
            or (
                ((decision.authority_kind == "legacy-import-bridge") != (event_kind == "legacy-import-bridge"))
                and event_kind != "denied-attempt"
            )
        ):
            raise RightsProblem("rights-decision-invalid")
        self._write_use_event(
            connection,
            subject=decision.subject,
            use=decision.use,
            policy_revision_id=decision.policy_revision_id,
            authority_kind=decision.authority_kind,
            source_assertion_sha256=decision.source_assertion_sha256,
            code=decision.code,
            reason_code=decision.reason_code,
            event_kind=event_kind,
            occurred_at=decision.evaluated_at,
            actor=actor,
        )

    def _write_use_event(
        self,
        connection: CanonicalConnection,
        *,
        subject: RightsSubject,
        use: RightsUse,
        policy_revision_id: str | None,
        authority_kind: str,
        source_assertion_sha256: str | None,
        code: str,
        reason_code: str,
        event_kind: str,
        occurred_at: str,
        actor: RightsActor,
    ) -> None:
        subject_hash = _digest(subject.model_dump(mode="json", by_alias=True))
        source_row = connection.execute(
            "SELECT payload_sha256 FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
            (self._project, subject.source_assertion_revision_id),
        ).fetchone()
        if source_row is None or source_assertion_sha256 is None or source_row[0] != source_assertion_sha256:
            raise RightsProblem("rights-decision-integrity-invalid")
        policy_sha256 = None
        if policy_revision_id is not None:
            row = connection.execute(
                "SELECT r.policy_sha256,r.subject_sha256,s.source_assertion_revision_id "
                "FROM rights_policy_revisions r JOIN rights_policy_subjects s "
                "ON s.project_id=r.project_id AND s.subject_sha256=r.subject_sha256 "
                "WHERE r.project_id=? AND r.revision_id=?",
                (self._project, policy_revision_id),
            ).fetchone()
            if row is None or row[1] != subject_hash or row[2] != subject.source_assertion_revision_id:
                raise RightsProblem("rights-decision-integrity-invalid")
            policy_sha256 = str(row[0])
        connection.execute(
            "INSERT INTO rights_use_decisions (decision_id,project_id,subject_sha256,"
            "source_assertion_revision_id,policy_revision_id,policy_sha256,actor_id,trace_id,"
            "use_action,use_sha256,decision_code,reason_code,event_kind,authority_kind,"
            "source_assertion_sha256,occurred_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_uuid_v7(),
                self._project,
                subject_hash,
                subject.source_assertion_revision_id,
                policy_revision_id,
                policy_sha256,
                actor.actor_id,
                actor.trace_id,
                use.action,
                _digest(use.model_dump(mode="json", by_alias=True)),
                code,
                reason_code,
                event_kind,
                authority_kind,
                source_assertion_sha256,
                occurred_at,
            ),
        )

    def append_denied_attempt(self, decision: RightsDecision, *, actor: RightsActor) -> None:
        """Record the copied decision after a denied action's writer rolled back."""

        self._actor(actor)
        try:
            decision = RightsDecision.model_validate(decision)
        except ValidationError:
            raise RightsProblem("rights-decision-invalid") from None
        if decision.code == "allow":
            raise RightsProblem("rights-decision-invalid")
        with self._transaction(write=True) as (connection, _):
            self._retained_source(connection, decision.subject)
            self._validate_subject_copy(connection, decision.subject)
            self._insert_use_decision(connection, decision, actor=actor, event_kind="denied-attempt")

    def require_allow_with_connection(
        self, connection: CanonicalConnection, request: RightsRequest, *, actor: RightsActor
    ) -> RightsDecision:
        decision = self.evaluate_with_connection(connection, request, actor=actor)
        if decision.code != "allow":
            raise RightsProblem("rights-use-not-allowed")
        return decision

    def evaluate(self, request: RightsRequest, *, actor: RightsActor) -> RightsDecision:
        with self._transaction(write=True) as (connection, _):
            return self.evaluate_with_connection(connection, request, actor=actor)

    def _replay(
        self,
        connection: CanonicalConnection,
        policy: RightsPolicyRevision,
        command_id: str,
        command_sha256: str,
        actor: RightsActor,
    ) -> RightsPolicyRevision | None:
        row = connection.execute(
            "SELECT revision_id,policy_sha256,command_sha256,actor_id,policy_json "
            "FROM rights_policy_revisions WHERE project_id=? AND command_id=?",
            (self._project, command_id),
        ).fetchone()
        if row is None:
            return None
        expected_hash = _digest(policy.model_dump(mode="json", by_alias=True))
        if (
            row[0] != policy.revision_id
            or row[1] != expected_hash
            or row[2] != command_sha256
            or row[3] != actor.actor_id
            or row[4] != policy.model_dump_json(by_alias=True)
        ):
            raise RightsProblem("rights-command-conflict")
        stored = self._load_revision(connection, policy.revision_id)
        linked = connection.execute(
            "SELECT p.record_sha256,o.record_sha256 FROM provenance_events p "
            "JOIN outbox_events o ON o.project_id=p.project_id AND o.revision_id=p.revision_id "
            "WHERE p.project_id=? AND p.revision_id=? AND o.idempotency_key=? LIMIT 2",
            (self._project, policy.revision_id, "rights-" + command_id),
        ).fetchall()
        if len(linked) != 1 or linked[0][0] != linked[0][1]:
            raise RightsProblem("rights-command-integrity-invalid")
        return stored

    @staticmethod
    def _draft_permissions(policy: RightsPolicyRevision) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                key: value
                for key, value in permission.model_dump(mode="json", by_alias=True).items()
                if key not in {"assertionId", "subject", "assertedByActorId", "recordedAt"}
            }
            for permission in policy.permissions
        )

    def _replay_draft(
        self,
        connection: CanonicalConnection,
        subject: RightsSubject,
        permissions: tuple[RightsPermissionDraft, ...],
        expected_predecessor_revision_id: str | None,
        command_id: str,
        command_sha256: str,
        actor: RightsActor,
    ) -> RightsPolicyRevision | None:
        row = connection.execute(
            "SELECT revision_id,command_sha256,actor_id FROM rights_policy_revisions "
            "WHERE project_id=? AND command_id=?",
            (self._project, command_id),
        ).fetchone()
        if row is None:
            return None
        policy = self._load_revision(connection, str(row[0]))
        drafts = tuple(permission.model_dump(mode="json", by_alias=True) for permission in permissions)
        if (
            row[1] != command_sha256
            or row[2] != actor.actor_id
            or policy.subject != subject
            or policy.predecessor_revision_id != expected_predecessor_revision_id
            or self._draft_permissions(policy) != drafts
        ):
            raise RightsProblem("rights-command-conflict")
        linked = connection.execute(
            "SELECT p.record_sha256,o.record_sha256 FROM provenance_events p "
            "JOIN outbox_events o ON o.project_id=p.project_id AND o.revision_id=p.revision_id "
            "WHERE p.project_id=? AND p.revision_id=? AND o.idempotency_key=? LIMIT 2",
            (self._project, policy.revision_id, "rights-" + command_id),
        ).fetchall()
        if len(linked) != 1 or linked[0][0] != linked[0][1]:
            raise RightsProblem("rights-command-integrity-invalid")
        return policy

    def _append(
        self,
        aggregates: _SqliteAggregateRepository,
        policy: RightsPolicyRevision,
        actor: RightsActor,
        command_id: str,
        command_sha256: str,
        source: AggregateRevision,
        current: AggregateRevision | None,
        *,
        policy_id: str,
    ) -> AggregateRevision:
        inputs = (source,) if current is None else (source, current)
        dependencies = (
            MaterialDependency(
                new_uuid_v7(),
                "source-revision",
                "direct",
                source.revision_id,
                None,
                None,
                _projection_content_sha256(source),
                "rights.policy.v1",
                "1.0.0",
            ),
            *(
                (
                    MaterialDependency(
                        new_uuid_v7(),
                        "human-decision",
                        "non-material",
                        current.revision_id,
                        None,
                        None,
                        _projection_content_sha256(current),
                        "rights.policy.v1",
                        "1.0.0",
                    ),
                )
                if current is not None
                else ()
            ),
            *(
                MaterialDependency(
                    new_uuid_v7(),
                    "parameter-set",
                    "direct",
                    None,
                    "rights." + name,
                    "1.0.0",
                    "sha256:" + digest,
                    "rights.policy.v1",
                    "1.0.0",
                )
                for name, digest in (
                    ("payload", _digest(policy.model_dump(mode="json", by_alias=True))),
                    ("current-intent", actor.intent_sha256),
                    ("current-privacy", actor.policy_sha256),
                    ("command", command_sha256),
                )
            ),
        )
        event = AtomicRepositoryEvent(
            event_id=new_uuid_v7(),
            outbox_id=new_uuid_v7(),
            event_type="rights.policy-created" if current is None else "rights.policy-revised",
            occurred_at=actor.occurred_at,
            available_at=actor.occurred_at,
            trace_id=actor.trace_id,
            actor_type="human",
            actor_id=actor.actor_id,
            idempotency_key="rights-" + command_id,
        )
        revision = aggregates.append(
            AggregateRevisionDraft(
                revision_id=policy.revision_id,
                aggregate_id=policy_id,
                aggregate_kind="decision",
                created_at=current.created_at if current is not None else actor.occurred_at,
                modified_at=actor.occurred_at,
                display_label_observed="Source rights policy",
                display_label_normalized=None,
                knowledge_status="adjudicated",
                rights_status="unknown",
                dependency_coverage="complete",
                provenance_inputs=inputs,
                material_dependencies=dependencies,
            ),
            event,
            expected_revision=current.revision if current is not None else None,
        )
        _publication_step("aggregate-created")
        return revision

    def _mark_exact_corpus_outputs(
        self,
        connection: CanonicalConnection,
        policy: RightsPolicyRevision,
        source: SourceAssertion,
        occurred_at: str,
    ) -> bool:
        rows = self._exact_corpus_links(connection, policy, source, limit=_MAX_EXACT_RECHECKS + 1)
        if len(rows) > _MAX_EXACT_RECHECKS:
            # The rights head must still commit; a durable exact-subject scope
            # will keep subsequent uses closed until propagation is repaired.
            return False
        for output_revision_id, item_id, path_id in rows:
            self._insert_exact_recheck(connection, policy, output_revision_id, item_id, path_id, occurred_at)
        _publication_step("exact-rechecks-created")
        return True

    def _exact_corpus_links(
        self,
        connection: CanonicalConnection,
        policy: RightsPolicyRevision,
        source: SourceAssertion,
        *,
        limit: int,
        missing_only: bool = False,
        output_revision_id: str | None = None,
    ) -> tuple[tuple[str, str, str], ...]:
        address = policy.subject.address
        missing = (
            "AND NOT EXISTS (SELECT 1 FROM rights_policy_rechecks marked "
            "WHERE marked.project_id=linked.project_id AND marked.rights_revision_id=? "
            "AND marked.output_revision_id=linked.revision_id AND marked.path_id=linked.path_id) "
            if missing_only
            else ""
        )
        rows = connection.execute(
            "SELECT linked.revision_id,linked.item_id,linked.path_id "
            "FROM corpus_item_discovery_paths linked JOIN corpus_discovery_paths path "
            "ON path.path_id=linked.path_id AND path.project_id=linked.project_id "
            "AND path.item_id=linked.item_id "
            "WHERE path.project_id=? AND ((path.kind=? AND path.source_revision_id=? "
            "AND path.context_id=? AND path.context_revision_id=? "
            "AND path.ordinal IS ? AND path.record_key_sha256 IS ?) "
            "OR (path.kind='citation' AND path.source_revision_id=?)) "
            + ("AND linked.revision_id=? " if output_revision_id is not None else "")
            + missing
            + "ORDER BY linked.revision_id,linked.path_id LIMIT ?",
            (
                self._project,
                address.kind,
                source.source_revision_id,
                address.context_id,
                address.revision_id,
                address.ordinal,
                address.record_key,
                policy.subject.source_assertion_revision_id,
                *((output_revision_id,) if output_revision_id is not None else ()),
                *((policy.revision_id,) if missing_only else ()),
                limit,
            ),
        ).fetchall()
        return tuple((str(row[0]), str(row[1]), str(row[2])) for row in rows)

    def _insert_exact_recheck(
        self,
        connection: CanonicalConnection,
        policy: RightsPolicyRevision,
        output_revision_id: str,
        item_id: str,
        path_id: str,
        occurred_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO rights_policy_rechecks (recheck_id,project_id,rights_revision_id,"
            "source_assertion_revision_id,item_id,path_id,output_revision_id,reason,disposition,occurred_at) "
            "VALUES (?,?,?,?,?,?,?,'RIGHTS_POLICY','requires-review',?)",
            (
                new_uuid_v7(),
                self._project,
                policy.revision_id,
                policy.subject.source_assertion_revision_id,
                item_id,
                path_id,
                output_revision_id,
                occurred_at,
            ),
        )

    def _missing_generic_outputs(
        self, connection: CanonicalConnection, policy: RightsPolicyRevision, *, limit: int
    ) -> tuple[tuple[str, str], ...]:
        predecessor = policy.predecessor_revision_id
        if predecessor is None:
            raise RightsProblem("rights-impact-integrity-invalid")
        rows = connection.execute(
            "WITH parents(revision_id) AS (SELECT ? UNION "
            "SELECT output_revision_id FROM rights_policy_generic_rechecks "
            "WHERE project_id=? AND rights_revision_id=?) "
            "SELECT dependency.output_revision_id,MIN(dependency.dependency_revision_id) "
            "FROM parents JOIN material_dependencies dependency "
            "ON dependency.project_id=? AND dependency.dependency_revision_id=parents.revision_id "
            "AND dependency.relation_type IN ('direct','conditional') "
            "AND NOT EXISTS (SELECT 1 FROM rights_policy_generic_rechecks marked "
            "WHERE marked.project_id=dependency.project_id AND marked.rights_revision_id=? "
            "AND marked.output_revision_id=dependency.output_revision_id) "
            "GROUP BY dependency.output_revision_id ORDER BY dependency.output_revision_id LIMIT ?",
            (predecessor, self._project, policy.revision_id, self._project, policy.revision_id, limit),
        ).fetchall()
        return tuple((str(row[0]), str(row[1])) for row in rows)

    def _begin_generic_impact(
        self,
        connection: CanonicalConnection,
        previous: AggregateRevision | None,
        replacement: AggregateRevision,
        command_id: str,
        actor: RightsActor,
    ) -> None:
        if previous is None:
            return
        change = DependencyChange(
            change_id=new_uuid_v7(),
            idempotency_key="rights-" + command_id,
            reason="RIGHTS_POLICY",
            dependency_kind="human-decision",
            previous_revision_id=previous.revision_id,
            replacement_revision_id=replacement.revision_id,
            configuration_id=None,
            previous_configuration_version=None,
            replacement_configuration_version=None,
            previous_fingerprint=_projection_content_sha256(previous),
            replacement_fingerprint=_projection_content_sha256(replacement),
            propagation_policy_id="rights.policy.v1",
            propagation_policy_version="1.0.0",
            actor_id=actor.actor_id,
            trace_id=actor.trace_id,
            occurred_at=actor.occurred_at,
        )
        impacts = _SqliteDependencyImpactRepository(self._database, self._project)
        preview = impacts._preview_with_connection(
            connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
        )
        run_id = new_uuid_v7()
        batch_size = 1_000
        run = impacts._begin_with_connection(
            connection,
            change,
            preview_sha256=preview.preview_sha256,
            run_id=run_id,
            batch_size=batch_size,
            decisions=(),
        )
        sequence = 1
        while run.state == "running":
            # The public advance() opens a second writer. Complete its bounded
            # checkpoint protocol here so a rights publish cannot commit an
            # orphaned running impact; the same transaction owns both facts.
            impacts._verify_run_snapshot(connection, run_id)
            rows = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT item_sequence,item_id,output_revision_id,output_kind,"
                    "disposition,depth,relation_type,path_json,path_sha256,"
                    "path_length,path_truncated,cycle_group_id,confidence,review_required "
                    "FROM dependency_impact_items WHERE project_id=? AND run_id=? "
                    "AND item_sequence>? ORDER BY item_sequence LIMIT ?",
                    (self._project, run_id, run.processed_items, batch_size),
                ).fetchall()
            )
            if not rows or len(rows) > batch_size:
                raise RightsProblem("rights-impact-integrity-invalid")
            added_stale, added_unknown = _record_dependency_stale_batch(
                connection,
                run_id=run_id,
                project_id=self._project,
                change_id=change.change_id,
                reason="RIGHTS_POLICY",
                propagation_policy_id=change.propagation_policy_id,
                propagation_policy_version=change.propagation_policy_version,
                detected_at=actor.occurred_at,
                items=rows,
            )
            processed = run.processed_items + len(rows)
            stale = run.stale_count + added_stale
            unknown = run.unknown_count + added_unknown
            event_type = "completed" if processed == run.total_items else "checkpoint"
            sequence += 1
            checkpoint = _impact_checkpoint_sha256(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                processed_items=processed,
                stale_count=stale,
                unknown_count=unknown,
                previous_checkpoint_sha256=run.checkpoint_sha256,
            )
            impacts._insert_audit(
                connection,
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                processed_items=processed,
                stale_count=stale,
                unknown_count=unknown,
                checkpoint_sha256=checkpoint,
                occurred_at=actor.occurred_at,
            )
            run = impacts._run_with_connection(connection, run_id)
            _publication_step("dependency-impact-batch-created")
        if run.state != "completed" or run.processed_items != run.total_items:
            raise RightsProblem("rights-impact-integrity-invalid")
        _publication_step("dependency-impact-created")

    def _publish_with_connection(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        policy: RightsPolicyRevision,
        command_id: str,
        command_sha256: str,
        actor: RightsActor,
        connector_record: ConnectorRecord | None,
    ) -> RightsPolicyRevision:
        subject_json = policy.subject.model_dump_json(by_alias=True)
        subject_hash = _digest(policy.subject.model_dump(mode="json", by_alias=True))
        source = self._retained_source(connection, policy.subject)
        self._validate_subject_copy(connection, policy.subject)
        observation = self._source_observation(source, policy.subject.source_assertion_revision_id, connector_record)
        if policy.source_observation is not None and policy.source_observation != observation:
            raise RightsProblem("rights-observation-mismatch")
        try:
            policy = RightsPolicyRevision.model_validate(policy.model_copy(update={"source_observation": observation}))
        except ValidationError:
            raise RightsProblem("rights-policy-invalid") from None
        policy_json = policy.model_dump_json(by_alias=True)
        policy_hash = _digest(policy.model_dump(mode="json", by_alias=True))
        self._validate_policy_evidence(policy, actor, source)
        replay = self._replay(connection, policy, command_id, command_sha256, actor)
        if replay is not None:
            return replay
        mapping = connection.execute(
            "SELECT policy_id,subject_json FROM rights_policy_subjects WHERE project_id=? AND subject_sha256=?",
            (self._project, subject_hash),
        ).fetchone()
        previous_policy = self.current_with_connection(connection, policy.subject)
        if previous_policy is None:
            if mapping is not None or policy.predecessor_revision_id is not None:
                raise RightsProblem("rights-predecessor-stale")
            policy_id, previous_aggregate = new_uuid_v7(), None
        else:
            if mapping is None or str(mapping[1]) != subject_json:
                raise RightsProblem("rights-policy-integrity-invalid")
            if policy.predecessor_revision_id != previous_policy.revision_id:
                raise RightsProblem("rights-predecessor-stale")
            policy_id = str(mapping[0])
            previous_aggregate = aggregates.get_revision(previous_policy.revision_id)
        source_aggregate = aggregates.get_revision(policy.subject.source_assertion_revision_id)
        revision = self._append(
            aggregates,
            policy,
            actor,
            command_id,
            command_sha256,
            source_aggregate,
            previous_aggregate,
            policy_id=policy_id,
        )
        if previous_policy is None:
            connection.execute(
                "INSERT INTO rights_policy_subjects (project_id,subject_sha256,policy_id,"
                "subject_json,source_assertion_revision_id,copy_id,copy_location,resource_class) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    self._project,
                    subject_hash,
                    policy_id,
                    subject_json,
                    policy.subject.source_assertion_revision_id,
                    policy.subject.copy_id,
                    policy.subject.copy_location,
                    policy.subject.resource_class,
                ),
            )
        connection.execute(
            "INSERT INTO rights_policy_revisions (revision_id,policy_id,project_id,subject_sha256,"
            "predecessor_revision_id,revision_number,policy_json,policy_sha256,command_id,"
            "command_sha256,actor_id,occurred_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                policy.revision_id,
                policy_id,
                self._project,
                subject_hash,
                policy.predecessor_revision_id,
                revision.revision,
                policy_json,
                policy_hash,
                command_id,
                command_sha256,
                actor.actor_id,
                actor.occurred_at,
            ),
        )
        _publication_step("policy-created")
        exact_complete = self._mark_exact_corpus_outputs(connection, policy, source, actor.occurred_at)
        generic_complete = True
        if previous_aggregate is not None:
            connection.execute("SAVEPOINT rights_impact_fallback")
            try:
                self._begin_generic_impact(connection, previous_aggregate, revision, command_id, actor)
            except DependencyImpactLimitExceeded:
                # A planner cap is a pending propagation disposition, not
                # authority to keep the superseded grant as the current head.
                connection.execute("ROLLBACK TO SAVEPOINT rights_impact_fallback")
                generic_complete = False
            finally:
                connection.execute("RELEASE SAVEPOINT rights_impact_fallback")
        pending_reason = (
            "exact-and-generic-limit"
            if not exact_complete and not generic_complete
            else "exact-limit"
            if not exact_complete
            else "generic-limit"
            if not generic_complete
            else None
        )
        connection.execute(
            "INSERT INTO rights_policy_recheck_scopes (rights_revision_id,project_id,subject_sha256,"
            "source_assertion_revision_id,exact_state,generic_state,disposition,pending_reason,reason,occurred_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                policy.revision_id,
                self._project,
                subject_hash,
                policy.subject.source_assertion_revision_id,
                "complete" if exact_complete else "pending",
                "complete" if generic_complete else "pending",
                "complete" if pending_reason is None else "pending",
                pending_reason,
                "RIGHTS_POLICY",
                actor.occurred_at,
            ),
        )
        _publication_step("scope-created")
        return policy

    def publish(
        self,
        policy: RightsPolicyRevision,
        *,
        command_id: str,
        command_sha256: str,
        actor: RightsActor,
    ) -> RightsPolicyRevision:
        """Low-level publication when Core already minted every durable ID."""

        self._actor(actor, command_id=command_id, command_sha256=command_sha256)
        try:
            policy = RightsPolicyRevision.model_validate(policy)
        except ValidationError:
            raise RightsProblem("rights-policy-invalid") from None
        if policy.subject.project_id != self._project:
            raise RightsProblem("rights-source-mismatch")
        connector_record = self._resolve_connector_record(policy.subject)
        with self._transaction(write=True) as (connection, aggregates):
            self._authority(connection, actor)
            return self._publish_with_connection(
                connection, aggregates, policy, command_id, command_sha256, actor, connector_record
            )

    def publish_draft(
        self,
        subject: RightsSubject,
        permissions: tuple[RightsPermissionDraft, ...],
        expected_predecessor_revision_id: str | None,
        *,
        command_id: str,
        command_sha256: str,
        actor: RightsActor,
    ) -> RightsPolicyRevision:
        """Check replay before minting revision, assertion IDs, or recorded time."""

        with self._transaction(write=True) as (connection, aggregates):
            return self.publish_draft_with_connection(
                connection,
                aggregates,
                subject,
                permissions,
                expected_predecessor_revision_id,
                command_id=command_id,
                command_sha256=command_sha256,
                actor=actor,
            )

    def publish_draft_with_connection(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        subject: RightsSubject,
        permissions: tuple[RightsPermissionDraft, ...],
        expected_predecessor_revision_id: str | None,
        *,
        command_id: str,
        command_sha256: str,
        actor: RightsActor,
    ) -> RightsPolicyRevision:
        """Publish within an existing canonical writer, including its rollback."""

        self._actor(actor, command_id=command_id, command_sha256=command_sha256)
        try:
            subject = RightsSubject.model_validate(subject)
            if (
                len(permissions) > 256
                or not isinstance(permissions, tuple)
                or any(not isinstance(item, RightsPermissionDraft) for item in permissions)
                or (expected_predecessor_revision_id is not None and not is_uuid_v7(expected_predecessor_revision_id))
            ):
                raise RightsProblem("rights-policy-invalid")
            permissions = tuple(RightsPermissionDraft.model_validate(item) for item in permissions)
        except ValidationError:
            raise RightsProblem("rights-policy-invalid") from None
        if subject.project_id != self._project:
            raise RightsProblem("rights-source-mismatch")
        connector_record = self._resolve_connector_record(subject)
        self._authority(connection, actor)
        source = self._retained_source(connection, subject)
        self._validate_subject_copy(connection, subject)
        if any(item.basis == "source-observation" for item in permissions):
            raise RightsProblem("rights-observation-unverified")
        if any(item.basis == "verified-entitlement" for item in permissions):
            raise RightsProblem("rights-entitlement-unverified")
        replay = self._replay_draft(
            connection,
            subject,
            permissions,
            expected_predecessor_revision_id,
            command_id,
            command_sha256,
            actor,
        )
        if replay is not None:
            return replay
        now = _utcnow()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RightsProblem("rights-clock-unavailable")
        recorded_at = now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        try:
            minted_permissions = tuple(
                RightsPermission(
                    assertion_id=new_uuid_v7(),
                    subject=subject,
                    use=item.use,
                    value=item.value,
                    basis=item.basis,
                    confidence=item.confidence,
                    asserted_by_actor_id=actor.actor_id if item.basis == "researcher-confirmed" else None,
                    grantee_actor_id=item.grantee_actor_id,
                    evidence_revision_ids=item.evidence_revision_ids,
                    license_observation_revision_id=item.license_observation_revision_id,
                    entitlement_revision_id=item.entitlement_revision_id,
                    recorded_at=recorded_at,
                    expires_at=item.expires_at,
                    confirmation_required=item.confirmation_required,
                )
                for item in permissions
            )
            policy = RightsPolicyRevision(
                revision_id=new_uuid_v7(),
                predecessor_revision_id=expected_predecessor_revision_id,
                subject=subject,
                permissions=minted_permissions,
            )
        except ValidationError:
            raise RightsProblem("rights-policy-invalid") from None
        self._validate_policy_evidence(policy, actor, source)
        return self._publish_with_connection(
            connection, aggregates, policy, command_id, command_sha256, actor, connector_record
        )


__all__ = ["RightsActor", "RightsProblem", "SqliteRightsRepository"]
