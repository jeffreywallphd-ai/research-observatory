"""Selective recalculation planning over immutable revisions and durable workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace

from .domain_contracts import is_uuid_v7
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
from .ports.workflow_executor import WorkflowActor, WorkflowJobClaim, WorkflowJobRecord, WorkflowJobSubmission
from .recalculation_contracts import (
    RecalculationAuthority,
    RecalculationCandidateCommit,
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
    policy_id: str
    policy_version: str
    policy_sha256: str
    configuration_id: str
    configuration_version: str
    priority: int = 0


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
            "policyId": request.policy_id,
            "policyVersion": request.policy_version,
            "policyHash": request.policy_sha256,
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


class SelectiveRecalculationService:
    """Coordinates project-scoped reads while keeping persistence behind ports."""

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWorkFactory,
        dependencies: MaterialDependencyRepository,
        recalculation: SelectiveRecalculationRepository,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._dependencies = dependencies
        self._recalculation = recalculation

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
            or any(not is_uuid_v7(value) for value in (command.new_revision_id, *command.dependency_ids))
        ):
            raise RepositoryConflict("revision restoration dependency authority is invalid")
        with self._unit_of_work() as unit:
            prior = unit.aggregates.get_revision(command.prior_adjudicated_revision_id)
            current = unit.aggregates.get_revision(command.expected_current_revision_id)
            if (
                prior.knowledge_status != "adjudicated"
                or prior.project_id != current.project_id
                or prior.aggregate_id != current.aggregate_id
                or prior.aggregate_kind != current.aggregate_kind
                or prior.revision >= current.revision
            ):
                raise RepositoryConflict("only a prior adjudicated revision may be restored")
            unit.require_fresh_revision(prior.revision_id)
            dependencies = tuple(
                replace(dependency, dependency_id=dependency_id)
                for dependency, dependency_id in zip(registration.dependencies, command.dependency_ids, strict=True)
            )
            restored = unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=command.new_revision_id,
                    aggregate_id=prior.aggregate_id,
                    aggregate_kind=prior.aggregate_kind,
                    created_at=prior.created_at,
                    modified_at=command.modified_at,
                    display_label_observed=prior.display_label_observed,
                    display_label_normalized=prior.display_label_normalized,
                    knowledge_status=prior.knowledge_status,
                    rights_status=prior.rights_status,
                    dependency_coverage=registration.coverage,
                    object_sha256=prior.object_sha256,
                    provenance_inputs=(current, prior),
                    material_dependencies=dependencies,
                ),
                command.event,
                expected_revision=current.revision,
            )
            unit.commit()
            return restored


__all__ = [
    "RecalculationWorkflow",
    "RecalculationWorkflowIdentity",
    "RecalculationWorkflowRequest",
    "RestoreRevisionCommand",
    "RevisionComparison",
    "ScheduledRecalculation",
    "SelectiveRecalculationService",
]
