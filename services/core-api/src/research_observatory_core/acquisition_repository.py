"""Immutable location-copy witnesses and protected acquisition receipts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from .acquisition.locations import retained_locations
from .connectors.contracts import ConnectorRecord
from .corpus_repository import SqliteCorpusRepository
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.acquisition import AcquisitionLocation, AcquisitionProblem, AcquisitionReceipt, AcquisitionSelection
from .ports.corpus import CorpusActor
from .ports.repositories import AggregateRevision, AggregateRevisionDraft, AtomicRepositoryEvent, MaterialDependency
from .reconciliation.contracts import SourceAssertion
from .repositories import _projection_content_sha256, _SqliteAggregateRepository
from .rights_policy import RightsAction, RightsPolicyRevision, RightsRequest, RightsUse, evaluate_rights
from .rights_repository import SqliteRightsRepository
from .storage import CanonicalConnection

if TYPE_CHECKING:
    from .document_attachment_repository import LocalDocumentAttachmentService


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def load_location(connection: CanonicalConnection, project: str, identity: str) -> AcquisitionLocation:
    row = connection.execute(
        "SELECT source_assertion_revision_id,location_key,location_sha256,location_json "
        "FROM acquisition_locations WHERE project_id=? AND location_id=?",
        (project, identity),
    ).fetchone()
    if row is None:
        raise AcquisitionProblem("acquisition-location-unavailable")
    try:
        location = AcquisitionLocation.model_validate_json(str(row[3]))
    except ValidationError:
        raise AcquisitionProblem("acquisition-location-integrity-invalid") from None
    value = location.model_dump(mode="json", by_alias=True)
    value.pop("locationSha256")
    if (
        location.location_id != identity
        or location.project_id != project
        or tuple(row[:3]) != (location.source_assertion_revision_id, location.location_key, location.location_sha256)
        or _digest(value) != location.location_sha256
    ):
        raise AcquisitionProblem("acquisition-location-integrity-invalid")
    source_row = connection.execute(
        "SELECT assertion_json FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
        (project, location.source_assertion_revision_id),
    ).fetchone()
    if source_row is None:
        raise AcquisitionProblem("acquisition-source-invalid")
    source = SourceAssertion.model_validate_json(str(source_row[0]))
    if (
        source.address != location.address
        or source.source_sha256 != location.source_sha256
        or source.provider != location.provider
        or source.source_revision_id != location.source_revision_id
    ):
        raise AcquisitionProblem("acquisition-source-invalid")
    return location


def permitted_policy(
    connection: CanonicalConnection,
    rights: SqliteRightsRepository,
    location: AcquisitionLocation,
    actor: CorpusActor,
    *,
    record: bool = False,
) -> RightsPolicyRevision:
    rights._authority(connection, actor)
    policy = rights.current_with_connection(connection, location.rights_subject)
    uses: tuple[tuple[RightsAction, str], ...] = (("store", "document-acquisition"), ("inspect", "document-analysis"))
    for action, purpose in uses:
        request = RightsRequest(
            actor_id=actor.actor_id,
            subject=location.rights_subject,
            use=RightsUse(action=action, purpose=purpose, destination_kind="local-project"),
        )
        decision = (
            rights.evaluate_with_connection(connection, request, actor=actor)
            if record
            else evaluate_rights(policy, request, now=datetime.now(UTC))
        )
        if (
            decision.code != "allow"
            or policy is None
            or rights._recheck_scope_with_connection(connection, policy).disposition != "complete"
        ):
            raise AcquisitionProblem("acquisition-rights-denied")
    assert policy is not None
    return policy


def _append_attempt_revision(
    aggregates: _SqliteAggregateRepository,
    operation_id: str,
    actor: CorpusActor,
    *,
    code: str,
    inputs: tuple[AggregateRevision, ...],
    fingerprints: tuple[tuple[str, str], ...],
    previous: int | None,
) -> AggregateRevision:
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    created_at = aggregates.get(operation_id).created_at if previous is not None else now
    dependencies = tuple(
        MaterialDependency(
            new_uuid_v7(),
            "human-decision" if item.aggregate_kind == "decision" else "source-revision",
            "direct",
            item.revision_id,
            None,
            None,
            _projection_content_sha256(item),
            "dependency.material.v1",
            "1.0.0",
        )
        for item in inputs
    )
    dependencies += tuple(
        MaterialDependency(
            new_uuid_v7(),
            "parameter-set",
            "direct",
            None,
            "acquisition." + name,
            "1.0.0",
            "sha256:" + digest,
            "dependency.material.v1",
            "1.0.0",
        )
        for name, digest in fingerprints
    )
    return aggregates.append(
        AggregateRevisionDraft(
            revision_id=new_uuid_v7(),
            aggregate_id=operation_id,
            aggregate_kind="workflow",
            created_at=created_at,
            modified_at=now,
            display_label_observed=code,
            display_label_normalized=None,
            knowledge_status="observed",
            rights_status="allowed",
            dependency_coverage="complete",
            provenance_inputs=tuple(inputs),
            material_dependencies=dependencies,
        ),
        AtomicRepositoryEvent(
            new_uuid_v7(),
            new_uuid_v7(),
            "document." + code,
            now,
            now,
            actor.trace_id,
            "human",
            actor.actor_id,
            "acquisition-" + operation_id + "-" + code,
        ),
        expected_revision=previous,
    )


def finish_attempt_with_connection(
    connection: CanonicalConnection,
    aggregates: _SqliteAggregateRepository,
    *,
    project: str,
    operation_id: str,
    actor: CorpusActor,
    outcome: str,
    code: str,
    candidate_id: str | None = None,
):
    row = connection.execute(
        "SELECT actor_id,revision_id FROM acquisition_attempts WHERE project_id=? AND operation_id=?",
        (project, operation_id),
    ).fetchone()
    if row is None or row[0] != actor.actor_id:
        raise AcquisitionProblem("acquisition-attempt-unavailable")
    if connection.execute(
        "SELECT 1 FROM acquisition_attempt_results WHERE project_id=? AND operation_id=?", (project, operation_id)
    ).fetchone():
        return
    initial = aggregates.get_revision(str(row[1]))
    inputs = (initial,)
    if candidate_id is not None and (
        connection.execute(
            "SELECT 1 FROM document_attachment_operations WHERE project_id=? AND operation_id=? "
            "AND candidate_id=? AND actor_id=?",
            (project, operation_id, candidate_id, actor.actor_id),
        ).fetchone()
        is None
    ):
        raise AcquisitionProblem("acquisition-attempt-changed")
    revision = _append_attempt_revision(
        aggregates,
        operation_id,
        actor,
        code=code,
        inputs=inputs,
        fingerprints=(("outcome", _digest({"outcome": outcome, "code": code, "candidateId": candidate_id})),),
        previous=initial.revision,
    )
    connection.execute(
        "INSERT INTO acquisition_attempt_results VALUES (?,?,?,?,?,?)",
        (operation_id, project, revision.revision_id, outcome, code, candidate_id),
    )


def publish_acquisition_source(
    connection: CanonicalConnection,
    aggregates: _SqliteAggregateRepository,
    rights: SqliteRightsRepository,
    *,
    project: str,
    operation_id: str,
    candidate_id: str,
    object_sha256: str,
    byte_length: int,
    receipt: AcquisitionReceipt,
    actor: CorpusActor,
) -> None:
    location = load_location(connection, project, receipt.location_id)
    policy = permitted_policy(connection, rights, location, actor, record=True)
    if (
        policy.revision_id != receipt.provider_policy_revision_id
        or location.location_sha256 != receipt.location_sha256
        or receipt.actual_sha256 != object_sha256
        or receipt.expanded_bytes != byte_length
        or (receipt.expected_sha256 is not None and receipt.expected_sha256 != object_sha256)
    ):
        raise AcquisitionProblem("acquisition-publication-changed")
    raw = receipt.model_dump(mode="json", by_alias=True)
    connection.execute(
        "INSERT INTO document_acquisition_sources VALUES (?,?,?,?,?,?,?)",
        (
            candidate_id,
            project,
            operation_id,
            location.location_id,
            policy.revision_id,
            _digest(raw),
            json.dumps(raw, sort_keys=True, separators=(",", ":")),
        ),
    )
    finish_attempt_with_connection(
        connection,
        aggregates,
        project=project,
        operation_id=operation_id,
        actor=actor,
        outcome="candidate",
        code="acquisition-candidate",
        candidate_id=candidate_id,
    )


def acquisition_policy_for_commit(
    connection: CanonicalConnection, rights: SqliteRightsRepository, project: str, candidate_id: str, actor: CorpusActor
) -> tuple[str, str] | None:
    row = connection.execute(
        "SELECT location_id,provider_policy_revision_id,receipt_sha256,receipt_json "
        "FROM document_acquisition_sources WHERE project_id=? AND candidate_id=?",
        (project, candidate_id),
    ).fetchone()
    if row is None:
        return None
    try:
        receipt = AcquisitionReceipt.model_validate_json(str(row[3]))
    except ValidationError:
        raise AcquisitionProblem("acquisition-receipt-integrity-invalid") from None
    if (
        receipt.location_id != row[0]
        or receipt.provider_policy_revision_id != row[1]
        or _digest(receipt.model_dump(mode="json", by_alias=True)) != row[2]
    ):
        raise AcquisitionProblem("acquisition-receipt-integrity-invalid")
    location = load_location(connection, project, str(row[0]))
    policy = permitted_policy(connection, rights, location, actor, record=True)
    # A newer permission is a different basis. Reacquisition/confirmation is
    # explicit; do not silently relabel a completed download's decision.
    if policy.revision_id != receipt.provider_policy_revision_id:
        raise AcquisitionProblem("acquisition-policy-changed")
    return policy.revision_id, str(row[2])


class AcquisitionRepository:
    def __init__(self, database: Path, project_id: str, resolve_record: Callable[[str, int], ConnectorRecord]):
        self._database, self._project, self._resolve = database, project_id, resolve_record
        self._corpus = SqliteCorpusRepository(database, project_id)
        self.rights = SqliteRightsRepository(database, project_id, connector_record_resolver=resolve_record)

    def begin_attempt(
        self,
        selection: AcquisitionSelection,
        *,
        operation_id: str,
        session_id: str,
        confirmation_sha256: str,
        expected_policy_revision_id: str,
        actor: CorpusActor,
        attachments: LocalDocumentAttachmentService,
    ) -> None:
        with self._corpus._transaction(write=True) as (connection, aggregates):
            self._corpus._authority(connection, actor)
            if connection.execute(
                "SELECT 1 FROM acquisition_attempts WHERE operation_id=?", (operation_id,)
            ).fetchone():
                raise AcquisitionProblem("acquisition-operation-conflict")
            location = load_location(connection, self._project, selection.location_id)
            policy = permitted_policy(connection, self.rights, location, actor, record=True)
            if (
                location.location_sha256 != selection.location_sha256
                or location.source_assertion_revision_id != selection.source_assertion_revision_id
                or policy.revision_id != expected_policy_revision_id
            ):
                raise AcquisitionProblem("acquisition-preview-stale")
            attachments._current_binding(
                connection,
                source_assertion_revision_id=selection.source_assertion_revision_id,
                work_id=selection.work_id,
                work_revision_id=selection.work_revision_id,
                version_id=selection.version_id,
                version_revision_id=selection.version_revision_id,
            )
            inputs = tuple(
                aggregates.get_revision(identity)
                for identity in (
                    selection.source_assertion_revision_id,
                    selection.work_revision_id,
                    selection.version_revision_id,
                    policy.revision_id,
                )
            )
            raw = selection.model_dump(mode="json", by_alias=True)
            revision = _append_attempt_revision(
                aggregates,
                operation_id,
                actor,
                code="acquisition-admitted",
                inputs=inputs,
                fingerprints=(
                    ("selection", _digest(raw)),
                    ("confirmation", confirmation_sha256),
                    ("intent", actor.intent_sha256),
                    ("privacy", actor.policy_sha256),
                ),
                previous=None,
            )
            connection.execute(
                "INSERT INTO acquisition_attempts VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    operation_id,
                    self._project,
                    revision.revision_id,
                    location.location_id,
                    actor.actor_id,
                    session_id,
                    json.dumps(raw, sort_keys=True, separators=(",", ":")),
                    confirmation_sha256,
                    revision.created_at,
                ),
            )

    def fail_attempt(self, operation_id: str, *, actor: CorpusActor, cancelled: bool, code: str) -> None:
        with self._corpus._transaction(write=True) as (connection, aggregates):
            self._corpus._authority(connection, actor)
            finish_attempt_with_connection(
                connection,
                aggregates,
                project=self._project,
                operation_id=operation_id,
                actor=actor,
                outcome="cancelled" if cancelled else "failed",
                code=code,
            )

    def locations(self, source_assertion_revision_id: str, *, actor: CorpusActor) -> tuple[AcquisitionLocation, ...]:
        if not is_uuid_v7(source_assertion_revision_id):
            raise AcquisitionProblem("acquisition-selection-invalid")
        with self._corpus._transaction(write=False) as (connection, _):
            self.rights._actor(actor)
            self._corpus._authority(connection, actor)
            row = connection.execute(
                "SELECT assertion_json FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
                (self._project, source_assertion_revision_id),
            ).fetchone()
            if row is None:
                raise AcquisitionProblem("acquisition-source-unavailable")
            source = SourceAssertion.model_validate_json(str(row[0]))
        if source.address.kind != "connector-record":
            return ()
        record = self._resolve(source.address.revision_id, source.address.ordinal)
        if (
            record.provider_id != source.provider
            or hashlib.sha256(record.model_dump_json(by_alias=True).encode()).hexdigest() != source.source_sha256
        ):
            raise AcquisitionProblem("acquisition-source-invalid")
        values = retained_locations(record)
        with self._corpus._transaction(write=True) as (connection, _):
            self._corpus._authority(connection, actor)
            if (
                connection.execute(
                    "SELECT assertion_json FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
                    (self._project, source_assertion_revision_id),
                ).fetchone()[0]
                != row[0]
            ):
                raise AcquisitionProblem("acquisition-source-invalid")
            result = []
            for value in values:
                prior = connection.execute(
                    "SELECT location_id FROM acquisition_locations WHERE project_id=? "
                    "AND source_assertion_revision_id=? AND location_key=?",
                    (self._project, source_assertion_revision_id, value.key),
                ).fetchone()
                if prior is not None:
                    result.append(load_location(connection, self._project, str(prior[0])))
                    continue
                location = AcquisitionLocation(
                    location_id=new_uuid_v7(),
                    project_id=self._project,
                    source_assertion_revision_id=source_assertion_revision_id,
                    source_revision_id=source.source_revision_id,
                    address=source.address,
                    source_sha256=source.source_sha256,
                    provider=source.provider,
                    location_key=value.key,
                    url=value.url,
                    license=value.license,
                    version=value.version,
                    location_sha256="0" * 64,
                )
                raw = location.model_dump(mode="json", by_alias=True)
                raw.pop("locationSha256")
                location = location.model_copy(update={"location_sha256": _digest(raw)})
                connection.execute(
                    "INSERT INTO acquisition_locations VALUES (?,?,?,?,?,?,?)",
                    (
                        location.location_id,
                        self._project,
                        source_assertion_revision_id,
                        value.key,
                        location.location_sha256,
                        location.model_dump_json(by_alias=True),
                        actor.occurred_at,
                    ),
                )
                result.append(location)
            return tuple(result)

    def authorize(
        self, selection: AcquisitionSelection, *, actor: CorpusActor, attachments: LocalDocumentAttachmentService
    ) -> tuple[AcquisitionLocation, RightsPolicyRevision]:
        with self._corpus._transaction(write=False) as (connection, _):
            self.rights._actor(actor)
            self._corpus._authority(connection, actor)
            location = load_location(connection, self._project, selection.location_id)
            if (
                location.source_assertion_revision_id != selection.source_assertion_revision_id
                or location.location_sha256 != selection.location_sha256
            ):
                raise AcquisitionProblem("acquisition-selection-invalid")
            intent = json.loads(
                connection.execute(
                    "SELECT text_value FROM settings WHERE project_id=? AND setting_key='research-intent.revision' "
                    "ORDER BY revision DESC LIMIT 1",
                    (self._project,),
                ).fetchone()[0]
            )
            declaration = intent.get("egressPolicy", {})
            settings = dict(
                connection.execute(
                    "SELECT setting_key,text_value FROM settings WHERE project_id=? AND setting_key IN "
                    "('privacy.network-policy','privacy.egress-consent-version') AND revision="
                    "(SELECT MAX(revision) FROM settings WHERE project_id=? AND setting_key LIKE 'privacy.%')",
                    (self._project, self._project),
                )
            )
            if (
                declaration.get("mode") != "approved-content"
                or location.provider not in declaration.get("approvedDestinationIds", ())
                or settings.get("privacy.network-policy") != "approved-providers"
                or settings.get("privacy.egress-consent-version") != "egress-preview-v1"
            ):
                raise AcquisitionProblem("acquisition-egress-denied")
            # Reuse exact active Work/Version/source membership rather than a
            # second association implementation or metadata-only identifier.
            attachments._current_binding(
                connection,
                source_assertion_revision_id=selection.source_assertion_revision_id,
                work_id=selection.work_id,
                work_revision_id=selection.work_revision_id,
                version_id=selection.version_id,
                version_revision_id=selection.version_revision_id,
            )
            return location, permitted_policy(connection, self.rights, location, actor)

    def source_for_revision(
        self, revision_id: str, *, actor: CorpusActor
    ) -> tuple[AcquisitionLocation, AcquisitionReceipt] | None:
        with self._corpus._transaction(write=False) as (connection, _):
            self._corpus._authority(connection, actor)
            row = connection.execute(
                "SELECT s.location_id,s.receipt_sha256,s.receipt_json FROM document_attachment_assertions a "
                "JOIN document_acquisition_sources s ON s.project_id=a.project_id AND s.candidate_id=a.candidate_id "
                "WHERE a.project_id=? AND a.document_revision_id=?",
                (self._project, revision_id),
            ).fetchone()
            if row is None:
                return None
            receipt = AcquisitionReceipt.model_validate_json(str(row[2]))
            if _digest(receipt.model_dump(mode="json", by_alias=True)) != row[1]:
                raise AcquisitionProblem("acquisition-receipt-integrity-invalid")
            return load_location(connection, self._project, str(row[0])), receipt
