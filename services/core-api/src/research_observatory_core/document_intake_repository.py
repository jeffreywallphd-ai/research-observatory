"""Atomic product queue composition for inspected local and remote copies."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal

from .acquisition.intake import DocumentIntakeInput, build_document_intake
from .domain_contracts import new_uuid_v7
from .ingestion.preview_workflow import PreviewIntentContext
from .ports.acquisition import AcquisitionProblem
from .ports.corpus import CorpusActor
from .ports.repositories import AggregateRevision
from .ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference, WorkflowQueueConflict
from .repositories import _projection_content_sha256, _SqliteAggregateRepository, _SqliteWorkflowQueueRepository
from .storage import CanonicalConnection


def admit_intake(
    connection: CanonicalConnection,
    aggregates: _SqliteAggregateRepository,
    queue: _SqliteWorkflowQueueRepository,
    *,
    project: str,
    operation_id: str,
    session_id: str,
    kind: Literal["local-import", "remote-download"],
    selection: Mapping[str, object],
    confirmation_sha256: str,
    actor: CorpusActor,
    initial: AggregateRevision | None = None,
) -> WorkflowJobClaim:
    from .document_attachment_repository import _append_attempt_revision, _now, _sha

    if connection.execute("SELECT 1 FROM document_intake_jobs WHERE operation_id=?", (operation_id,)).fetchone():
        raise AcquisitionProblem("acquisition-operation-conflict")
    intent_value = json.loads(
        connection.execute(
            "SELECT text_value FROM settings WHERE project_id=? AND setting_key='research-intent.revision' "
            "ORDER BY revision DESC LIMIT 1",
            (project,),
        ).fetchone()[0]
    )
    intent = PreviewIntentContext(
        project_id=project,
        domain_project_id=intent_value["projectId"],
        intent_id=intent_value["intentId"],
        revision_id=actor.intent_revision_id,
        content_hash="sha256:" + actor.intent_sha256,
        status=intent_value["status"],
    )
    inputs = DocumentIntakeInput(
        kind=kind,
        operation_id=operation_id,
        session_id=session_id,
        actor_id=actor.actor_id,
        intent=intent,
        privacy_sha256=actor.policy_sha256,
        selection_sha256=_sha(selection),
        confirmation_sha256=confirmation_sha256,
    )
    if initial is None:
        source_inputs = tuple(
            aggregates.get_revision(str(selection[key]))
            for key in ("sourceAssertionRevisionId", "workRevisionId", "versionRevisionId")
        )
        initial = _append_attempt_revision(
            aggregates,
            operation_id,
            actor,
            code="intake-admitted",
            inputs=source_inputs,
            fingerprints=(("intake", inputs.configuration_hash.removeprefix("sha256:")),),
            previous=None,
        )
    now = _now()
    submission = build_document_intake(inputs, now=now)
    # All existing definition, snapshot, actor, idempotency and digest guards
    # execute in this same writer. No runnable job is exposed before its exact
    # native-owned operation is claimed and started.
    from .ports.workflow_executor import WorkflowActor

    queue._enqueue_with_connection(connection, submission, actor=WorkflowActor(actor.actor_id, "human", "researcher"))
    connection.execute(
        "INSERT INTO document_intake_jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            operation_id,
            project,
            initial.revision_id,
            submission.job_id,
            kind,
            actor.actor_id,
            session_id,
            json.dumps(selection, sort_keys=True, separators=(",", ":")),
            inputs.configuration_hash.removeprefix("sha256:"),
            now,
        ),
    )
    claim = queue._claim_next_with_connection(
        connection,
        worker_id=new_uuid_v7(),
        concurrency_classes=("document",),
        now=now,
        lease_duration_ms=600_000,
        activity_types=(submission.activity_type,),
        job_id=submission.job_id,
    )
    if claim is None:
        raise WorkflowQueueConflict("document intake admission could not claim its exact job")
    queue._start_with_connection(connection, claim, now=now)
    return claim


def mark_intake_phase(
    connection: CanonicalConnection,
    queue: _SqliteWorkflowQueueRepository,
    claim: WorkflowJobClaim,
    phase: Literal["downloading", "validating"],
) -> None:
    from .document_attachment_repository import _now
    from .ports.object_store import ObjectStagingCancelled
    from .ports.workflow_executor import WorkflowActor

    now = _now()
    row = queue._lease_row(connection, claim, now, states=("running", "cancelling"))
    if row[1] == "cancelling" or row[3] is not None:
        raise ObjectStagingCancelled("document intake cancelled before phase")
    code = "intake-" + phase
    queue._append_history(
        connection,
        project_id=claim.project_id,
        workflow_run_id=claim.workflow_run_id,
        job_id=claim.job_id,
        attempt_id=claim.attempt_id,
        entity_type="job-attempt",
        entity_id=claim.attempt_id,
        from_state=str(row[4]),
        to_state=str(row[4]),
        occurred_at=now,
        actor=WorkflowActor(claim.worker_id, "workload", "local-workflow-worker"),
        reason_code=code,
        extra={"progress": json.loads(str(row[5]))},
    )
    connection.execute(
        "UPDATE workflow_queue_jobs SET diagnostic_code=?,updated_at=? WHERE project_id=? AND job_id=?",
        (code, now, claim.project_id, claim.job_id),
    )


def finish_intake(
    connection: CanonicalConnection,
    aggregates: _SqliteAggregateRepository,
    queue: _SqliteWorkflowQueueRepository,
    claim: WorkflowJobClaim,
    *,
    project: str,
    operation_id: str,
    actor: CorpusActor,
    outcome: Literal["candidate", "failed", "cancelled"],
    code: str,
    candidate_id: str | None = None,
    revision: AggregateRevision | None = None,
) -> None:
    from .document_attachment_repository import _append_attempt_revision, _now, _sha

    row = connection.execute(
        "SELECT job_id,actor_id,revision_id FROM document_intake_jobs WHERE project_id=? AND operation_id=?",
        (project, operation_id),
    ).fetchone()
    if row is None or row[0] != claim.job_id or row[1] != actor.actor_id or claim.project_id != project:
        raise AcquisitionProblem("acquisition-attempt-changed")
    now = _now()
    # This also rejects expired/replaced capabilities before adding an outcome.
    cleanup_failed = outcome == "failed" and code == "acquisition-cleanup-required"
    queue._lease_row(
        connection,
        claim,
        now,
        states=("running", "cancelling") if outcome == "cancelled" or cleanup_failed else ("running",),
    )
    if revision is None:
        initial = aggregates.get_revision(str(row[2]))
        fingerprints = [("intake-outcome", _sha({"outcome": outcome, "code": code, "candidateId": candidate_id}))]
        if candidate_id is not None:
            candidate = connection.execute(
                "SELECT object_sha256,candidate_sha256 FROM document_attachment_candidates "
                "WHERE project_id=? AND candidate_id=?",
                (project, candidate_id),
            ).fetchone()
            if candidate is None:
                raise AcquisitionProblem("acquisition-attempt-changed")
            fingerprints.extend((("copy-bytes", str(candidate[0])), ("candidate", str(candidate[1]))))
        revision = _append_attempt_revision(
            aggregates,
            operation_id,
            actor,
            code=code,
            inputs=(initial,),
            fingerprints=tuple(fingerprints),
            previous=initial.revision,
        )
    connection.execute(
        "INSERT INTO document_intake_results VALUES (?,?,?,?,?,?)",
        (operation_id, project, revision.revision_id, outcome, code, candidate_id),
    )
    if outcome == "candidate":
        output = WorkflowOutputReference(
            revision.aggregate_id, revision.revision_id, _projection_content_sha256(revision), "application/json", None
        )
        queue._stage_artifact_with_connection(connection, claim, artifact=output, role="output", now=now)
        if queue._dependency_registration_gaps_with_connection(connection, claim, now=now, outputs=(output,)):
            raise WorkflowQueueConflict("document intake output dependency registration is incomplete")
        queue._complete_with_connection(connection, claim, now=now, outputs=(output,))
    else:
        queue._finish_attempt_with_connection(
            connection, claim, now=now, error_code=code, cancel=outcome == "cancelled"
        )
