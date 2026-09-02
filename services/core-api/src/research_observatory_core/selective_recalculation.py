"""Selective recalculation planning over immutable revisions and durable workflows."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

from .domain_contracts import is_uuid_v7
from .models import (
    RecalculationCauseProjection,
    RecalculationComparisonProjection,
    RecalculationComparisonRequest,
    RecalculationPreview,
    RecalculationPreviewRequest,
    RecalculationRestoredRevision,
    RecalculationRestoreRequest,
    RecalculationRestoreReviewProjection,
    RecalculationScheduleProjection,
    RecalculationScheduleRequest,
)
from .models import (
    RecalculationRestoreReviewRequest as ApiRestoreReviewRequest,
)
from .ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyChange,
    MaterialDependencyRepository,
    RepositoryConflict,
    RepositoryProblem,
    UnitOfWorkFactory,
)
from .ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowJobSubmission,
    WorkflowQueueConflict,
    WorkflowQueueProblem,
    WorkflowQueueRepository,
)
from .projects import ProjectLifecycleService
from .recalculation_contracts import (
    RecalculationAuthority,
    RecalculationCandidateCommit,
    RestoreRevisionCommit,
    SelectiveRecalculationRepository,
    recalculation_authority_sha256,
)
from .workflow_contracts import workflow_record_sha256, workflow_snapshot_errors
from .workflow_executor import prepare_workflow_job


@dataclass(frozen=True, slots=True)
class RecalculationWorkflowIdentity:
    workflow_definition_id: str
    definition_revision_id: str
    workflow_run_id: str
    snapshot_id: str
    step_run_id: str
    job_id: str
    history_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecalculationWorkflowRequest:
    target_revision_id: str
    change: DependencyChange
    identity: RecalculationWorkflowIdentity
    actor: WorkflowActor
    created_at: str
    available_at: str
    intent_id: str
    intent_revision_id: str
    intent_sha256: str
    configuration_id: str
    configuration_version: str
    priority: int = 0


@dataclass(frozen=True, slots=True)
class RestoreReviewIdentity:
    workflow_definition_id: str
    definition_revision_id: str
    workflow_run_id: str
    snapshot_id: str
    step_run_id: str
    human_task_id: str
    history_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RestoreReviewRequest:
    prior_adjudicated_revision_id: str
    expected_current_revision_id: str
    identity: RestoreReviewIdentity
    actor: WorkflowActor
    created_at: str
    intent_id: str
    intent_revision_id: str
    intent_sha256: str
    configuration_id: str
    configuration_version: str


@dataclass(frozen=True, slots=True)
class RestoreReview:
    workflow_run_id: str
    human_task_id: str
    snapshot_revision: int
    history_sequence: int
    policy_sha256: str


@dataclass(frozen=True, slots=True)
class RecalculationWorkflow:
    target_revision_id: str
    replacement_revision_ids: tuple[str, ...]
    reused_revision_ids: tuple[str, ...]
    stale_cause_ids: tuple[str, ...]
    plan_sha256: str
    submission: WorkflowJobSubmission


@dataclass(frozen=True, slots=True)
class ScheduledRecalculation:
    workflow: RecalculationWorkflow
    job: WorkflowJobRecord


@dataclass(frozen=True, slots=True)
class RevisionComparison:
    aggregate_id: str
    before_revision_id: str
    after_revision_id: str
    before_revision: int
    after_revision: int
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RestoreRevisionCommand:
    prior_adjudicated_revision_id: str
    expected_current_revision_id: str
    new_revision_id: str
    dependency_ids: tuple[str, ...]
    workflow_run_id: str
    human_task_id: str
    decision_id: str
    modified_at: str
    event: AtomicRepositoryEvent


def _sha256(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _revision_document(revision: AggregateRevision) -> dict[str, object]:
    return {
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


def _history_event(
    event_id: str,
    sequence: int,
    entity_type: str,
    entity_id: str,
    from_state: str | None,
    to_state: str,
    occurred_at: str,
    actor: WorkflowActor,
    reason_code: str,
) -> dict[str, object]:
    return {
        "eventId": event_id,
        "sequence": sequence,
        "entityType": entity_type,
        "entityId": entity_id,
        "fromState": from_state,
        "toState": to_state,
        "occurredAt": occurred_at,
        "actor": {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role},
        "reasonCode": reason_code,
        "progress": None,
        "decisionId": None,
        "checkpointId": None,
        "interruptionKind": None,
    }


def _schema_reference(schema_id: str) -> dict[str, str]:
    return {
        "schemaId": schema_id,
        "schemaVersion": "1.0.0",
        "schemaHash": _sha256({"schemaId": schema_id, "schemaVersion": "1.0.0"}),
    }


def _build_workflow(
    request: RecalculationWorkflowRequest,
    authority: RecalculationAuthority,
) -> RecalculationWorkflow:
    target = authority.target
    replacements = authority.replacements
    reusable = authority.reusable
    causes = authority.causes
    identity = request.identity
    all_ids = (
        identity.workflow_definition_id,
        identity.definition_revision_id,
        identity.workflow_run_id,
        identity.snapshot_id,
        identity.step_run_id,
        identity.job_id,
        request.intent_id,
        request.intent_revision_id,
        *identity.history_event_ids,
    )
    if len(identity.history_event_ids) != 5 or any(not is_uuid_v7(value) for value in all_ids):
        raise RepositoryConflict("recalculation workflow identities are invalid")
    if len(set(all_ids)) != len(all_ids):
        raise RepositoryConflict("recalculation workflow identities are not unique")
    plan_sha256 = recalculation_authority_sha256(authority)
    definition: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-workflow-definition",
        "contractVersion": "1.0.0",
        "workflowDefinitionId": identity.workflow_definition_id,
        "definitionRevisionId": identity.definition_revision_id,
        "definitionVersion": "1.0.0",
        "workflowKey": "selective-recalculation",
        "createdAt": request.created_at,
        "inputSchema": _schema_reference("selective-recalculation-input"),
        "outputSchema": _schema_reference("selective-recalculation-output"),
        "compatibility": {
            "historyContractVersion": "1.0.0",
            "minimumExecutorContractVersion": "1.0.0",
            "maximumExecutorContractVersion": "1.0.0",
        },
        "steps": [
            {
                "stepKey": "recompute-output",
                "kind": "activity",
                "activityType": "selective-recalculation",
                "dependsOn": [],
                "inputSchema": _schema_reference("selective-recalculation-target"),
                "outputSchema": _schema_reference("selective-recalculation-candidate"),
                "retryPolicy": {
                    "maxAttempts": 3,
                    "initialBackoffMs": 1000,
                    "maximumBackoffMs": 10000,
                    "multiplierBasisPoints": 20000,
                    "jitter": "deterministic",
                    "retryableErrorCodes": ["dependency-unavailable"],
                    "nonRetryableErrorCodes": ["rights-denied", "policy-denied", "stale-authority"],
                },
                "idempotency": {"mode": "required", "keyScope": "workflow-step-inputs"},
                "checkpointPolicy": {"mode": "required", "maximumIntervalSeconds": 60},
                "cancellationPolicy": {
                    "mode": "cooperative",
                    "gracePeriodMs": 5000,
                    "partialArtifactDisposition": "retained-incomplete",
                },
                "permissions": {
                    "network": "policy-controlled",
                    "projectFiles": "read-write",
                    "model": "policy-controlled",
                    "capabilityScopes": ["artifacts-read", "objects-write", "policy-read"],
                },
                "progress": {"unit": "outputs", "totalKind": "known", "totalUnits": 1},
                "humanTask": None,
            }
        ],
    }
    revision_inputs = (target, *replacements, *reusable)
    artifacts: list[dict[str, object]] = [
        {
            "artifactId": item.revision_id,
            "revisionId": item.revision_id,
            "contentHash": _sha256(_revision_document(item)),
            "mediaType": (
                "application/vnd.research-observatory.recalculation-target+json"
                if item.revision_id == target.revision_id
                else "application/vnd.research-observatory.replacement-revision+json"
                if item in replacements
                else "application/vnd.research-observatory.reusable-revision+json"
            ),
            "role": "input",
            "disposition": "committed",
            "createdByAttemptId": None,
            "provenanceEntityId": item.aggregate_id,
        }
        for item in revision_inputs
    ]
    artifacts.extend(
        {
            "artifactId": cause.cause_id,
            "revisionId": target.revision_id,
            "contentHash": _sha256(asdict(cause)),
            "mediaType": "application/vnd.research-observatory.stale-cause+json",
            "role": "input",
            "disposition": "committed",
            "createdByAttemptId": None,
            "provenanceEntityId": target.aggregate_id,
        }
        for cause in causes
    )
    input_artifact_ids = [str(item["artifactId"]) for item in artifacts]
    actor_events = (
        ("workflow-run", identity.workflow_run_id, None, "accepted", "command-accepted"),
        ("workflow-step", identity.step_run_id, None, "pending", "step-created"),
        ("workflow-step", identity.step_run_id, "pending", "runnable", "dependencies-satisfied"),
        ("job", identity.job_id, None, "pending", "job-created"),
        ("job", identity.job_id, "pending", "runnable", "job-ready"),
    )
    history = [
        _history_event(
            identity.history_event_ids[index],
            index + 1,
            entity_type,
            entity_id,
            from_state,
            to_state,
            request.created_at,
            request.actor,
            reason,
        )
        for index, (entity_type, entity_id, from_state, to_state, reason) in enumerate(actor_events)
    ]
    snapshot: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-workflow-snapshot",
        "contractVersion": "1.0.0",
        "snapshotId": identity.snapshot_id,
        "snapshotRevision": 1,
        "projectId": target.project_id,
        "workflowRunId": identity.workflow_run_id,
        "definition": {
            "workflowDefinitionId": identity.workflow_definition_id,
            "definitionRevisionId": identity.definition_revision_id,
            "definitionVersion": "1.0.0",
            "contentHash": workflow_record_sha256(definition),
        },
        "intent": {
            "intentId": request.intent_id,
            "revisionId": request.intent_revision_id,
            "contentHash": request.intent_sha256,
        },
        "policy": {
            "policyId": authority.policy_id,
            "policyVersion": authority.policy_version,
            "policyHash": authority.policy_sha256,
        },
        "configuration": {
            "configurationId": request.configuration_id,
            "configurationVersion": request.configuration_version,
            "configurationHash": plan_sha256,
        },
        "executor": {
            "profile": "local",
            "adapterId": "local-durable-workflow",
            "adapterVersion": "1.0.0",
            "contractVersion": "1.0.0",
        },
        "state": "accepted",
        "progress": {"kind": "quantified", "unit": "outputs", "completedUnits": 0, "totalUnits": 1},
        "cancellation": {"requestedAt": None, "reasonCode": None, "interruptionKind": None},
        "createdAt": request.created_at,
        "updatedAt": request.created_at,
        "sequence": 5,
        "stepRuns": [
            {
                "stepRunId": identity.step_run_id,
                "stepKey": "recompute-output",
                "state": "runnable",
                "sequence": 3,
                "progress": {"kind": "quantified", "unit": "outputs", "completedUnits": 0, "totalUnits": 1},
                "jobIds": [identity.job_id],
                "humanTaskIds": [],
                "inputArtifactIds": input_artifact_ids,
                "outputArtifactIds": [],
            }
        ],
        "jobs": [
            {
                "jobId": identity.job_id,
                "stepRunId": identity.step_run_id,
                "state": "runnable",
                "sequence": 5,
                "idempotencyKey": _sha256({"planSha256": plan_sha256, "workflowRunId": identity.workflow_run_id}),
                "commandFingerprint": plan_sha256,
                "attemptIds": [],
                "currentAttemptId": None,
                "inputArtifactIds": input_artifact_ids,
                "outputArtifactIds": [],
                "cancellation": {"requestedAt": None, "reasonCode": None, "interruptionKind": None},
            }
        ],
        "attempts": [],
        "checkpoints": [],
        "artifacts": artifacts,
        "humanTasks": [],
        "history": history,
    }
    errors = workflow_snapshot_errors(definition, snapshot)
    if errors:
        raise RepositoryProblem("generated recalculation workflow authority is invalid")
    submission = prepare_workflow_job(
        definition,
        snapshot,
        job_id=identity.job_id,
        concurrency_class="document",
        priority=request.priority,
        available_at=request.available_at,
    )
    return RecalculationWorkflow(
        target.revision_id,
        tuple(item.revision_id for item in replacements),
        tuple(item.revision_id for item in reusable),
        tuple(cause.cause_id for cause in causes),
        plan_sha256,
        submission,
    )


def _build_restore_review(
    request: RestoreReviewRequest,
    authority: RecalculationAuthority,
    prior: AggregateRevision,
) -> tuple[str, str]:
    identity = request.identity
    all_ids = (
        identity.workflow_definition_id,
        identity.definition_revision_id,
        identity.workflow_run_id,
        identity.snapshot_id,
        identity.step_run_id,
        identity.human_task_id,
        request.intent_id,
        request.intent_revision_id,
        *identity.history_event_ids,
    )
    if (
        len(identity.history_event_ids) != 7
        or any(not is_uuid_v7(value) for value in all_ids)
        or len(set(all_ids)) != len(all_ids)
        or request.actor.actor_type != "human"
        or request.actor.role != "researcher"
    ):
        raise RepositoryConflict("restore-review workflow authority is invalid")
    definition: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-workflow-definition",
        "contractVersion": "1.0.0",
        "workflowDefinitionId": identity.workflow_definition_id,
        "definitionRevisionId": identity.definition_revision_id,
        "definitionVersion": "1.0.0",
        "workflowKey": "selective-recalculation-restore-review",
        "createdAt": request.created_at,
        "inputSchema": _schema_reference("selective-recalculation-restore-review-input"),
        "outputSchema": _schema_reference("selective-recalculation-restore-review-output"),
        "compatibility": {
            "historyContractVersion": "1.0.0",
            "minimumExecutorContractVersion": "1.0.0",
            "maximumExecutorContractVersion": "1.0.0",
        },
        "steps": [
            {
                "stepKey": "authorize-restore",
                "kind": "human-task",
                "activityType": None,
                "dependsOn": [],
                "inputSchema": _schema_reference("selective-recalculation-restore-decision-input"),
                "outputSchema": _schema_reference("selective-recalculation-restore-decision-output"),
                "retryPolicy": {
                    "maxAttempts": 1,
                    "initialBackoffMs": 0,
                    "maximumBackoffMs": 0,
                    "multiplierBasisPoints": 10000,
                    "jitter": "none",
                    "retryableErrorCodes": [],
                    "nonRetryableErrorCodes": [],
                },
                "idempotency": {"mode": "required", "keyScope": "human-task-decision"},
                "checkpointPolicy": {"mode": "forbidden", "maximumIntervalSeconds": None},
                "cancellationPolicy": {
                    "mode": "cooperative",
                    "gracePeriodMs": 0,
                    "partialArtifactDisposition": "discarded",
                },
                "permissions": {
                    "network": "none",
                    "projectFiles": "none",
                    "model": "none",
                    "capabilityScopes": [],
                },
                "progress": {"unit": "decisions", "totalKind": "known", "totalUnits": 1},
                "humanTask": {
                    "requiredRole": "researcher",
                    "decisionSchema": _schema_reference("selective-recalculation-restore-human-decision"),
                    "allowedDispositions": ["approved", "rejected", "deferred"],
                    "consequencesByDisposition": {
                        "approved": "resume-workflow",
                        "rejected": "end-workflow",
                        "deferred": "skip-step",
                    },
                },
            }
        ],
    }
    current = authority.target
    artifacts = [
        {
            "artifactId": revision.revision_id,
            "revisionId": revision.revision_id,
            "contentHash": _sha256(_revision_document(revision)),
            "mediaType": media_type,
            "role": "input",
            "disposition": "committed",
            "createdByAttemptId": None,
            "provenanceEntityId": revision.aggregate_id,
        }
        for revision, media_type in (
            (prior, "application/vnd.research-observatory.restore-prior-revision+json"),
            (current, "application/vnd.research-observatory.restore-current-revision+json"),
        )
    ]
    actor = request.actor
    events = (
        ("workflow-run", identity.workflow_run_id, None, "accepted", "command-accepted"),
        ("workflow-step", identity.step_run_id, None, "pending", "step-created"),
        ("workflow-step", identity.step_run_id, "pending", "runnable", "dependencies-satisfied"),
        ("human-task", identity.human_task_id, None, "requested", "human-review-requested"),
        ("workflow-step", identity.step_run_id, "runnable", "waiting-human", "human-review-pending"),
        ("workflow-run", identity.workflow_run_id, "accepted", "waiting-human", "human-review-pending"),
        ("human-task", identity.human_task_id, "requested", "claimed", "human-task-claimed"),
    )
    history = [
        _history_event(
            identity.history_event_ids[index],
            index + 1,
            entity_type,
            entity_id,
            from_state,
            to_state,
            request.created_at,
            actor,
            reason,
        )
        for index, (entity_type, entity_id, from_state, to_state, reason) in enumerate(events)
    ]
    evidence_ids = [prior.revision_id, current.revision_id]
    snapshot: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-workflow-snapshot",
        "contractVersion": "1.0.0",
        "snapshotId": identity.snapshot_id,
        "snapshotRevision": 1,
        "projectId": current.project_id,
        "workflowRunId": identity.workflow_run_id,
        "definition": {
            "workflowDefinitionId": identity.workflow_definition_id,
            "definitionRevisionId": identity.definition_revision_id,
            "definitionVersion": "1.0.0",
            "contentHash": workflow_record_sha256(definition),
        },
        "intent": {
            "intentId": request.intent_id,
            "revisionId": request.intent_revision_id,
            "contentHash": request.intent_sha256,
        },
        "policy": {
            "policyId": authority.policy_id,
            "policyVersion": authority.policy_version,
            "policyHash": authority.policy_sha256,
        },
        "configuration": {
            "configurationId": request.configuration_id,
            "configurationVersion": request.configuration_version,
            "configurationHash": authority.authority_sha256,
        },
        "executor": {
            "profile": "local",
            "adapterId": "local-durable-workflow",
            "adapterVersion": "1.0.0",
            "contractVersion": "1.0.0",
        },
        "state": "waiting-human",
        "progress": {"kind": "quantified", "unit": "decisions", "completedUnits": 0, "totalUnits": 1},
        "cancellation": {"requestedAt": None, "reasonCode": None, "interruptionKind": None},
        "createdAt": request.created_at,
        "updatedAt": request.created_at,
        "sequence": 7,
        "stepRuns": [
            {
                "stepRunId": identity.step_run_id,
                "stepKey": "authorize-restore",
                "state": "waiting-human",
                "sequence": 5,
                "progress": {"kind": "quantified", "unit": "decisions", "completedUnits": 0, "totalUnits": 1},
                "jobIds": [],
                "humanTaskIds": [identity.human_task_id],
                "inputArtifactIds": evidence_ids,
                "outputArtifactIds": [],
            }
        ],
        "jobs": [],
        "attempts": [],
        "checkpoints": [],
        "artifacts": artifacts,
        "humanTasks": [
            {
                "humanTaskId": identity.human_task_id,
                "workflowRunId": identity.workflow_run_id,
                "definitionRevisionId": identity.definition_revision_id,
                "stepRunId": identity.step_run_id,
                "state": "claimed",
                "sequence": 7,
                "requestedAt": request.created_at,
                "requestedBy": {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role},
                "requiredRole": "researcher",
                "assignedTo": {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role},
                "evidenceArtifactIds": evidence_ids,
                "decision": None,
            }
        ],
        "history": history,
    }
    errors = workflow_snapshot_errors(definition, snapshot)
    if errors:
        raise RepositoryProblem("generated restore-review workflow authority is invalid")
    return (
        json.dumps(definition, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    )


class SelectiveRecalculationService:
    """Coordinates project-scoped reads while keeping persistence behind ports."""

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWorkFactory,
        dependencies: MaterialDependencyRepository,
        recalculation: SelectiveRecalculationRepository,
        workflows: WorkflowQueueRepository | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._dependencies = dependencies
        self._recalculation = recalculation
        self._workflows = workflows

    def schedule(self, request: RecalculationWorkflowRequest) -> ScheduledRecalculation:
        authority = self._recalculation.plan_authority(request.target_revision_id)
        durable_changes = tuple(change for change in authority.changes if change.change_id == request.change.change_id)
        if durable_changes != (request.change,):
            raise RepositoryConflict("recalculation change authority differs")
        if not authority.causes or not any(cause.change_id == request.change.change_id for cause in authority.causes):
            raise RepositoryConflict("recalculation target has no matching open stale cause")
        workflow = _build_workflow(request, authority)
        job = self._recalculation.enqueue_if_current(authority, workflow.submission, actor=request.actor)
        return ScheduledRecalculation(workflow, job)

    def compare(self, before_revision_id: str, after_revision_id: str) -> RevisionComparison:
        with self._unit_of_work() as unit:
            before = unit.aggregates.get_revision(before_revision_id)
            after = unit.aggregates.get_revision(after_revision_id)
        if (
            before.project_id != after.project_id
            or before.aggregate_id != after.aggregate_id
            or before.aggregate_kind != after.aggregate_kind
        ):
            raise RepositoryConflict("revision comparison authority differs")
        changed = {
            name
            for name, before_value, after_value in (
                ("display-label-observed", before.display_label_observed, after.display_label_observed),
                ("display-label-normalized", before.display_label_normalized, after.display_label_normalized),
                ("knowledge-status", before.knowledge_status, after.knowledge_status),
                ("rights-status", before.rights_status, after.rights_status),
                ("object-sha256", before.object_sha256, after.object_sha256),
            )
            if before_value != after_value
        }
        return RevisionComparison(
            before.aggregate_id,
            before.revision_id,
            after.revision_id,
            before.revision,
            after.revision,
            tuple(sorted(changed)),
        )

    def append_candidate(
        self,
        draft: AggregateRevisionDraft,
        event: AtomicRepositoryEvent,
        *,
        claim: WorkflowJobClaim,
        expected_current_revision_id: str,
        plan_sha256: str,
        completed_at: str,
    ) -> AggregateRevision:
        return self._recalculation.commit_candidate(
            RecalculationCandidateCommit(
                claim=claim,
                draft=draft,
                event=event,
                expected_current_revision_id=expected_current_revision_id,
                plan_sha256=plan_sha256,
                completed_at=completed_at,
            )
        )

    def request_restore_review(self, request: RestoreReviewRequest) -> RestoreReview:
        if self._workflows is None:
            raise RepositoryProblem("restore-review workflow repository is unavailable")
        authority = self._recalculation.plan_authority(request.expected_current_revision_id)
        with self._unit_of_work() as unit:
            prior = unit.aggregates.get_revision(request.prior_adjudicated_revision_id)
            current = unit.aggregates.get_revision(request.expected_current_revision_id)
        if (
            current != authority.target
            or prior.knowledge_status != "adjudicated"
            or prior.project_id != current.project_id
            or prior.aggregate_id != current.aggregate_id
            or prior.aggregate_kind != current.aggregate_kind
            or prior.revision >= current.revision
        ):
            raise RepositoryConflict("only a prior adjudicated revision may be reviewed for restoration")
        self._dependencies.registration(prior.revision_id)
        definition_json, snapshot_json = _build_restore_review(request, authority, prior)
        record = self._workflows.register_authority(
            definition_json=definition_json,
            snapshot_json=snapshot_json,
            actor=request.actor,
        )
        return RestoreReview(
            workflow_run_id=record.workflow_run_id,
            human_task_id=request.identity.human_task_id,
            snapshot_revision=record.snapshot_revision,
            history_sequence=record.revision,
            policy_sha256=authority.policy_sha256,
        )

    def restore(self, command: RestoreRevisionCommand) -> AggregateRevision:
        if (
            command.event.actor_type != "human"
            or command.event.actor_id is None
            or command.event.event_type != "aggregate.revision-restored"
            or command.event.occurred_at != command.modified_at
        ):
            raise RepositoryConflict("revision restoration requires explicit human authority")
        registration = self._dependencies.registration(command.prior_adjudicated_revision_id)
        if (
            len(command.dependency_ids) != len(registration.dependencies)
            or len(set(command.dependency_ids)) != len(command.dependency_ids)
            or any(
                not is_uuid_v7(value)
                for value in (
                    command.new_revision_id,
                    *command.dependency_ids,
                    command.workflow_run_id,
                    command.human_task_id,
                    command.decision_id,
                )
            )
        ):
            raise RepositoryConflict("revision restoration dependency authority is invalid")
        return self._recalculation.restore_revision(
            RestoreRevisionCommit(
                prior_adjudicated_revision_id=command.prior_adjudicated_revision_id,
                expected_current_revision_id=command.expected_current_revision_id,
                new_revision_id=command.new_revision_id,
                dependency_ids=command.dependency_ids,
                workflow_run_id=command.workflow_run_id,
                human_task_id=command.human_task_id,
                decision_id=command.decision_id,
                modified_at=command.modified_at,
                event=command.event,
            )
        )


RecalculationRepositoryFactory = Callable[[Path, str], SelectiveRecalculationRepository]
DependencyRepositoryFactory = Callable[[Path, str], MaterialDependencyRepository]
WorkflowRepositoryFactory = Callable[[Path, str], WorkflowQueueRepository]
UnitOfWorkFactoryFactory = Callable[[Path, str], UnitOfWorkFactory]


@dataclass(slots=True)
class RecalculationControlProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    remediation: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


def _derived_uuid_v7(reference_id: str, idempotency_key: str, label: str) -> str:
    reference = UUID(reference_id)
    digest = hashlib.sha256(f"{idempotency_key}\0{label}".encode("ascii")).digest()
    value = bytearray(reference.bytes[:6] + digest[:10])
    value[6] = 0x70 | (value[6] & 0x0F)
    value[8] = 0x80 | (value[8] & 0x3F)
    return str(UUID(bytes=bytes(value)))


def _api_time(value: object) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")  # type: ignore[union-attr]


class RecalculationControlService:
    """Project-authorized Core API facade for preview, schedule, compare, and restore."""

    def __init__(
        self,
        projects: ProjectLifecycleService,
        *,
        recalculation_factory: RecalculationRepositoryFactory | None,
        dependency_factory: DependencyRepositoryFactory | None,
        workflow_factory: WorkflowRepositoryFactory | None,
        unit_of_work_factory: UnitOfWorkFactoryFactory | None,
        local_actor_id: str | None,
    ) -> None:
        self._projects = projects
        self._recalculation_factory = recalculation_factory
        self._dependency_factory = dependency_factory
        self._workflow_factory = workflow_factory
        self._unit_of_work_factory = unit_of_work_factory
        self._local_actor_id = local_actor_id

    @classmethod
    def unavailable(cls, projects: ProjectLifecycleService) -> RecalculationControlService:
        return cls(
            projects,
            recalculation_factory=None,
            dependency_factory=None,
            workflow_factory=None,
            unit_of_work_factory=None,
            local_actor_id=None,
        )

    def _actor(self) -> WorkflowActor:
        if self._local_actor_id is None:
            raise RecalculationControlProblem(
                503,
                "RO-CORE-RECALCULATION-ACTOR-UNAVAILABLE",
                "Local researcher identity is unavailable",
                "A trusted same-user identity is required for recalculation and restore decisions.",
                "Restore the Windows profile identity and retry.",
            )
        return WorkflowActor(self._local_actor_id, "human", "researcher")

    def _service(
        self,
        path: Path,
        project_id: str,
    ) -> tuple[SelectiveRecalculationService, SelectiveRecalculationRepository, MaterialDependencyRepository]:
        if any(
            factory is None
            for factory in (
                self._recalculation_factory,
                self._dependency_factory,
                self._workflow_factory,
                self._unit_of_work_factory,
            )
        ):
            raise RecalculationControlProblem(
                503,
                "RO-CORE-RECALCULATION-UNAVAILABLE",
                "Recalculation controls are unavailable",
                "The durable local recalculation adapters are not composed in this Core runtime.",
                "Restart the packaged desktop runtime and retry.",
                True,
            )
        recalculation = self._recalculation_factory(path, project_id)  # type: ignore[misc]
        dependencies = self._dependency_factory(path, project_id)  # type: ignore[misc]
        workflows = self._workflow_factory(path, project_id)  # type: ignore[misc]
        service = SelectiveRecalculationService(
            unit_of_work=self._unit_of_work_factory(path, project_id),  # type: ignore[misc]
            dependencies=dependencies,
            recalculation=recalculation,
            workflows=workflows,
        )
        return service, recalculation, dependencies

    @staticmethod
    def _problem(error: RepositoryProblem | WorkflowQueueProblem) -> RecalculationControlProblem:
        conflict = isinstance(error, (RepositoryConflict, WorkflowQueueConflict))
        return RecalculationControlProblem(
            412 if conflict else 500,
            "RO-CORE-RECALCULATION-AUTHORITY-CHANGED" if conflict else "RO-CORE-RECALCULATION-FAILED",
            "Recalculation authority changed" if conflict else "Recalculation failed",
            str(error),
            "Reload the current impact preview and workflow state before retrying.",
            conflict,
        )

    def preview(self, command: RecalculationPreviewRequest) -> RecalculationPreview:
        def read(path: Path, project_id: str) -> RecalculationPreview:
            _, repository, _ = self._service(path, project_id)
            try:
                authority = repository.plan_authority(command.target_revision_id)
            except RepositoryProblem as error:
                raise self._problem(error) from error
            return RecalculationPreview(
                project_id=authority.target.project_id,
                target_revision_id=authority.target.revision_id,
                plan_sha256=authority.authority_sha256,
                policy_sha256=authority.policy_sha256,
                change_ids=tuple(item.change_id for item in authority.changes),
                replacement_revision_ids=tuple(item.revision_id for item in authority.replacements),
                reusable_revision_ids=tuple(item.revision_id for item in authority.reusable),
                causes=tuple(
                    RecalculationCauseProjection(
                        cause_id=item.cause_id,
                        change_id=item.change_id,
                        disposition=item.disposition,
                        reason=item.reason,
                        depth=item.depth,
                        confidence=item.confidence,
                        review_required=item.review_required,
                        path_revision_ids=item.path_revision_ids,
                    )
                    for item in authority.causes
                ),
            )

        return self._projects.perform_open_project_action(root=command.root, require_write=False, action=read)

    def schedule(
        self,
        command: RecalculationScheduleRequest,
        *,
        idempotency_key: str,
    ) -> RecalculationScheduleProjection:
        actor = self._actor()

        def mutate(path: Path, project_id: str) -> RecalculationScheduleProjection:
            service, repository, _ = self._service(path, project_id)
            try:
                authority = repository.plan_authority(command.target_revision_id)
                if authority.authority_sha256 != command.expected_plan_sha256:
                    raise RepositoryConflict("recalculation preview is stale or substituted")
                change = next(item for item in authority.changes if item.change_id == command.change_id)
                identity = RecalculationWorkflowIdentity(
                    workflow_definition_id=_derived_uuid_v7(
                        command.target_revision_id, idempotency_key, "definition"
                    ),
                    definition_revision_id=_derived_uuid_v7(
                        command.target_revision_id,
                        idempotency_key,
                        "definition-revision",
                    ),
                    workflow_run_id=_derived_uuid_v7(command.target_revision_id, idempotency_key, "run"),
                    snapshot_id=_derived_uuid_v7(command.target_revision_id, idempotency_key, "snapshot"),
                    step_run_id=_derived_uuid_v7(command.target_revision_id, idempotency_key, "step"),
                    job_id=_derived_uuid_v7(command.target_revision_id, idempotency_key, "job"),
                    history_event_ids=tuple(
                        _derived_uuid_v7(command.target_revision_id, idempotency_key, f"history-{index}")
                        for index in range(5)
                    ),
                )
                scheduled = service.schedule(
                    RecalculationWorkflowRequest(
                        target_revision_id=command.target_revision_id,
                        change=change,
                        identity=identity,
                        actor=actor,
                        created_at=_api_time(command.requested_at),
                        available_at=_api_time(command.requested_at),
                        intent_id=command.intent_id,
                        intent_revision_id=command.intent_revision_id,
                        intent_sha256=command.intent_sha256,
                        configuration_id="selective-recalculation-default",
                        configuration_version="1.0.0",
                    )
                )
            except (StopIteration, RepositoryProblem, WorkflowQueueProblem) as error:
                problem = (
                    error
                    if isinstance(error, (RepositoryProblem, WorkflowQueueProblem))
                    else RepositoryConflict("change is unavailable")
                )
                raise self._problem(problem) from error
            return RecalculationScheduleProjection(
                project_id=project_id,
                target_revision_id=command.target_revision_id,
                plan_sha256=scheduled.workflow.plan_sha256,
                workflow_run_id=scheduled.job.workflow_run_id,
                job_id=scheduled.job.job_id,
                state=scheduled.job.state,
            )

        return self._projects.perform_open_project_action(root=command.root, require_write=True, action=mutate)

    def compare(self, command: RecalculationComparisonRequest) -> RecalculationComparisonProjection:
        def read(path: Path, project_id: str) -> RecalculationComparisonProjection:
            service, _, _ = self._service(path, project_id)
            try:
                comparison = service.compare(command.before_revision_id, command.after_revision_id)
            except RepositoryProblem as error:
                raise self._problem(error) from error
            return RecalculationComparisonProjection(
                aggregate_id=comparison.aggregate_id,
                before_revision_id=comparison.before_revision_id,
                after_revision_id=comparison.after_revision_id,
                before_revision=comparison.before_revision,
                after_revision=comparison.after_revision,
                changed_fields=comparison.changed_fields,
            )

        return self._projects.perform_open_project_action(root=command.root, require_write=False, action=read)

    def request_restore_review(
        self,
        command: ApiRestoreReviewRequest,
        *,
        idempotency_key: str,
    ) -> RecalculationRestoreReviewProjection:
        actor = self._actor()

        def mutate(path: Path, project_id: str) -> RecalculationRestoreReviewProjection:
            service, _, _ = self._service(path, project_id)
            identity = RestoreReviewIdentity(
                workflow_definition_id=_derived_uuid_v7(
                    command.after_revision_id,
                    idempotency_key,
                    "restore-definition",
                ),
                definition_revision_id=_derived_uuid_v7(
                    command.after_revision_id, idempotency_key, "restore-definition-revision"
                ),
                workflow_run_id=_derived_uuid_v7(command.after_revision_id, idempotency_key, "restore-run"),
                snapshot_id=_derived_uuid_v7(command.after_revision_id, idempotency_key, "restore-snapshot"),
                step_run_id=_derived_uuid_v7(command.after_revision_id, idempotency_key, "restore-step"),
                human_task_id=_derived_uuid_v7(command.after_revision_id, idempotency_key, "restore-human-task"),
                history_event_ids=tuple(
                    _derived_uuid_v7(command.after_revision_id, idempotency_key, f"restore-history-{index}")
                    for index in range(7)
                ),
            )
            try:
                review = service.request_restore_review(
                    RestoreReviewRequest(
                        prior_adjudicated_revision_id=command.before_revision_id,
                        expected_current_revision_id=command.after_revision_id,
                        identity=identity,
                        actor=actor,
                        created_at=_api_time(command.requested_at),
                        intent_id=command.intent_id,
                        intent_revision_id=command.intent_revision_id,
                        intent_sha256=command.intent_sha256,
                        configuration_id="selective-recalculation-restore-default",
                        configuration_version="1.0.0",
                    )
                )
            except (RepositoryProblem, WorkflowQueueProblem) as error:
                raise self._problem(error) from error
            return RecalculationRestoreReviewProjection(
                workflow_run_id=review.workflow_run_id,
                human_task_id=review.human_task_id,
                snapshot_revision=review.snapshot_revision,
                history_sequence=review.history_sequence,
                policy_sha256=review.policy_sha256,
            )

        return self._projects.perform_open_project_action(root=command.root, require_write=True, action=mutate)

    def restore(self, command: RecalculationRestoreRequest, *, trace_id: str) -> RecalculationRestoredRevision:
        actor = self._actor()

        def mutate(path: Path, project_id: str) -> RecalculationRestoredRevision:
            service, _, dependencies = self._service(path, project_id)
            timestamp = _api_time(command.modified_at)
            try:
                dependency_count = len(
                    dependencies.registration(command.prior_adjudicated_revision_id).dependencies
                )
                restored = service.restore(
                    RestoreRevisionCommand(
                        prior_adjudicated_revision_id=command.prior_adjudicated_revision_id,
                        expected_current_revision_id=command.expected_current_revision_id,
                        new_revision_id=_derived_uuid_v7(command.decision_id, command.decision_id, "restored-revision"),
                        dependency_ids=tuple(
                            _derived_uuid_v7(command.decision_id, command.decision_id, f"dependency-{index}")
                            for index in range(dependency_count)
                        ),
                        workflow_run_id=command.workflow_run_id,
                        human_task_id=command.human_task_id,
                        decision_id=command.decision_id,
                        modified_at=timestamp,
                        event=AtomicRepositoryEvent(
                            event_id=_derived_uuid_v7(command.decision_id, command.decision_id, "restore-event"),
                            outbox_id=_derived_uuid_v7(command.decision_id, command.decision_id, "restore-outbox"),
                            event_type="aggregate.revision-restored",
                            occurred_at=timestamp,
                            available_at=timestamp,
                            trace_id=trace_id,
                            actor_type="human",
                            actor_id=actor.actor_id,
                            idempotency_key=f"restore-revision:{command.decision_id}",
                        ),
                    )
                )
            except (RepositoryProblem, WorkflowQueueProblem) as error:
                raise self._problem(error) from error
            return RecalculationRestoredRevision(
                project_id=restored.project_id,
                aggregate_id=restored.aggregate_id,
                revision_id=restored.revision_id,
                revision=restored.revision,
                knowledge_status=restored.knowledge_status,
                rights_status=restored.rights_status,
            )

        return self._projects.perform_open_project_action(root=command.root, require_write=True, action=mutate)


__all__ = [
    "RecalculationControlProblem",
    "RecalculationControlService",
    "RecalculationWorkflow",
    "RecalculationWorkflowIdentity",
    "RecalculationWorkflowRequest",
    "RestoreReview",
    "RestoreReviewIdentity",
    "RestoreReviewRequest",
    "RestoreRevisionCommand",
    "RevisionComparison",
    "ScheduledRecalculation",
    "SelectiveRecalculationService",
]
