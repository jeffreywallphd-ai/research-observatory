"""Append-only current-session review of an already inspected candidate."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from .ports.acquisition import AcquisitionProblem, AcquisitionReceipt, AcquisitionSelection
from .ports.corpus import CorpusActor
from .ports.document_attachments import AttachmentCandidate, AttachmentProblem
from .rights_repository import SqliteRightsRepository
from .storage import CanonicalConnection


class DocumentRecoveryBasis(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    candidate_id: Identity
    candidate_sha256: Digest
    object_sha256: Digest
    original_operation_id: Identity
    actor_id: Identity
    session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    selection: tuple[Identity, Identity, Identity, Identity, Identity]
    intent_revision_id: Identity
    intent_sha256: Digest
    privacy_sha256: Digest
    candidate_policy_revision_id: Identity | None
    location_id: Identity | None
    location_sha256: Digest | None
    original_provider_policy_revision_id: Identity | None
    current_provider_policy_revision_id: Identity | None
    receipt_sha256: Digest | None


def current_recovery_basis(
    connection: CanonicalConnection,
    *,
    project: str,
    candidate: AttachmentCandidate,
    original_operation_id: str,
    session_id: str,
    actor: CorpusActor,
    rights: SqliteRightsRepository,
    remote_selection: AcquisitionSelection | None = None,
) -> DocumentRecoveryBasis:
    from .document_attachment_repository import _sha, load_location, permitted_policy

    original = connection.execute(
        "SELECT actor_id FROM document_attachment_operations WHERE project_id=? AND operation_id=? AND candidate_id=?",
        (project, original_operation_id, candidate.candidate_id),
    ).fetchone()
    owner = connection.execute(
        "SELECT actor_id FROM document_attachment_candidates WHERE project_id=? AND candidate_id=?",
        (project, candidate.candidate_id),
    ).fetchone()
    if original is None or owner is None or original[0] != actor.actor_id or owner[0] != actor.actor_id:
        raise AttachmentProblem("attachment-operation-unavailable")
    current_policy = rights.current_with_connection(connection, candidate.rights_subject)
    acquired = connection.execute(
        "SELECT location_id,provider_policy_revision_id,receipt_sha256,receipt_json "
        "FROM document_acquisition_sources WHERE project_id=? AND candidate_id=?",
        (project, candidate.candidate_id),
    ).fetchone()
    location = None
    provider_policy = None
    if acquired is not None:
        receipt = AcquisitionReceipt.model_validate_json(str(acquired[3]))
        location = load_location(connection, project, str(acquired[0]))
        if (
            receipt.location_id != location.location_id
            or receipt.location_sha256 != location.location_sha256
            or receipt.provider_policy_revision_id != acquired[1]
            or _sha(receipt.model_dump(mode="json", by_alias=True)) != acquired[2]
            or receipt.actual_sha256 != candidate.object_sha256
            or receipt.expanded_bytes != candidate.byte_length
        ):
            raise AcquisitionProblem("acquisition-receipt-integrity-invalid")
        if remote_selection is not None:
            origin = connection.execute(
                "SELECT selection_json FROM acquisition_attempts WHERE project_id=? AND operation_id=?",
                (project, original_operation_id),
            ).fetchone()
            if origin is None or AcquisitionSelection.model_validate_json(str(origin[0])) != remote_selection:
                raise AcquisitionProblem("acquisition-selection-invalid")
        provider_policy = permitted_policy(connection, rights, location, actor)
    elif remote_selection is not None:
        raise AcquisitionProblem("acquisition-selection-invalid")
    return DocumentRecoveryBasis(
        project_id=project,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        object_sha256=candidate.object_sha256,
        original_operation_id=original_operation_id,
        actor_id=actor.actor_id,
        session_id=session_id,
        selection=(
            candidate.source_assertion_revision_id,
            candidate.work_id,
            candidate.work_revision_id,
            candidate.version_id,
            candidate.version_revision_id,
        ),
        intent_revision_id=actor.intent_revision_id,
        intent_sha256=actor.intent_sha256,
        privacy_sha256=actor.policy_sha256,
        candidate_policy_revision_id=current_policy.revision_id if current_policy else None,
        location_id=location.location_id if location else None,
        location_sha256=location.location_sha256 if location else None,
        original_provider_policy_revision_id=str(acquired[1]) if acquired else None,
        current_provider_policy_revision_id=provider_policy.revision_id if provider_policy else None,
        receipt_sha256=str(acquired[2]) if acquired else None,
    )


def operation_recovery(
    connection: CanonicalConnection,
    *,
    project: str,
    candidate: AttachmentCandidate,
    operation_id: str,
    session_id: str,
    actor: CorpusActor,
    rights: SqliteRightsRepository,
    recheck: bool = True,
) -> tuple[str, DocumentRecoveryBasis] | None:
    from .document_attachment_repository import _sha

    original = connection.execute(
        "SELECT 1 FROM document_attachment_operations WHERE project_id=? "
        "AND operation_id=? AND candidate_id=? AND actor_id=? AND session_id=?",
        (project, operation_id, candidate.candidate_id, actor.actor_id, session_id),
    ).fetchone()
    if original:
        return None
    row = connection.execute(
        "SELECT revision_id,basis_sha256,basis_json FROM document_attachment_recoveries "
        "WHERE project_id=? AND operation_id=? AND candidate_id=? AND actor_id=? AND session_id=?",
        (project, operation_id, candidate.candidate_id, actor.actor_id, session_id),
    ).fetchone()
    if row is None:
        raise AttachmentProblem("attachment-operation-unavailable")
    try:
        basis = DocumentRecoveryBasis.model_validate_json(str(row[2]))
    except ValueError:
        raise AttachmentProblem("attachment-recovery-integrity-invalid") from None
    if (
        _sha(basis.model_dump(mode="json", by_alias=True)) != row[1]
        or basis.session_id != session_id
        or basis.actor_id != actor.actor_id
    ):
        raise AttachmentProblem("attachment-recovery-integrity-invalid")
    if recheck and basis != current_recovery_basis(
        connection,
        project=project,
        candidate=candidate,
        original_operation_id=basis.original_operation_id,
        session_id=session_id,
        actor=actor,
        rights=rights,
    ):
        raise AttachmentProblem("attachment-recovery-stale")
    return str(row[0]), basis
