from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyChange,
    MaterialDependency,
    PrivacyAuditEvent,
    PrivacySetting,
    RepositoryConflict,
    RepositoryProblem,
)
from research_observatory_core.ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowJobSubmission,
    WorkflowOutputReference,
    WorkflowQueueConflict,
    WorkflowQueueProblem,
)
from research_observatory_core.recalculation_contracts import (
    RecalculationAuthority,
    RecalculationCandidateCommit,
    SelectiveRecalculationRepository,
)
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
    sqlite_material_dependency_repository,
    sqlite_privacy_policy_repository,
    sqlite_selective_recalculation_repository,
    sqlite_workflow_queue_repository,
)
from research_observatory_core.selective_recalculation import (
    RecalculationWorkflowIdentity,
    RecalculationWorkflowRequest,
    RestoreReviewIdentity,
    RestoreReviewRequest,
    RestoreRevisionCommand,
    SelectiveRecalculationService,
)
from research_observatory_core.storage import (
    development_plaintext_database_fixture,
    initialize_database,
    open_canonical_database,
)
from research_observatory_core.workflow_contracts import workflow_snapshot_errors

PROJECT_ID = "01890f6e-6a40-7cc5-98b7-123456789abc"
SYSTEM_ID = "01890f6e-6a40-7cc5-98b7-000000000301"
RESEARCHER_ID = "01890f6e-6a40-7cc5-98b7-000000000302"
OCCURRED_AT = "2026-09-01T22:00:00.000Z"


def uid(index: int) -> str:
    return f"01890f6e-6a40-7cc5-98b7-{index:012x}"


def fingerprint(character: str) -> str:
    return "sha256:" + character * 64


def event(
    index: int,
    *,
    actor_type: str = "worker",
    actor_id: str | None = None,
    event_type: str = "evidence.created",
    idempotency_key: str | None = None,
    occurred_at: str | None = None,
) -> AtomicRepositoryEvent:
    timestamp = occurred_at or f"2026-09-01T22:00:{index:02d}.000Z"
    return AtomicRepositoryEvent(
        event_id=uid(10_000 + index),
        outbox_id=uid(20_000 + index),
        event_type=event_type,
        occurred_at=timestamp,
        available_at=timestamp,
        trace_id=f"{index + 1:032x}",
        actor_type=actor_type,  # type: ignore[arg-type]
        actor_id=actor_id or (RESEARCHER_ID if actor_type == "human" else SYSTEM_ID),
        idempotency_key=idempotency_key or f"selective-recalculation-{index}",
    )


def dependency(index: int, revision: AggregateRevision, character: str) -> MaterialDependency:
    return MaterialDependency(
        dependency_id=uid(30_000 + index),
        dependency_kind="source-revision",
        relation_type="direct",
        revision_id=revision.revision_id,
        configuration_id=None,
        configuration_version=None,
        fingerprint=fingerprint(character),
        governing_policy_id="dependency.material.v1",
        governing_policy_version="1.0.0",
    )


def revision_content_hash(revision: AggregateRevision) -> str:
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
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class InjectBeforeEnqueue(SelectiveRecalculationRepository):
    def __init__(self, delegate: SelectiveRecalculationRepository, injection: Callable[[], None]) -> None:
        self._delegate = delegate
        self._injection = injection

    def plan_authority(self, target_revision_id: str) -> RecalculationAuthority:
        return self._delegate.plan_authority(target_revision_id)

    def enqueue_if_current(
        self,
        authority: RecalculationAuthority,
        submission: WorkflowJobSubmission,
        *,
        actor: WorkflowActor,
    ) -> WorkflowJobRecord:
        self._injection()
        return self._delegate.enqueue_if_current(authority, submission, actor=actor)

    def commit_candidate(self, command: RecalculationCandidateCommit) -> AggregateRevision:
        return self._delegate.commit_candidate(command)


class SelectiveRecalculationE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "project"
        (self.root / "state").mkdir(parents=True)
        self.database = self.root / "state" / "project.sqlite3"
        self.protection = development_plaintext_database_fixture()
        self.protection.__enter__()
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=OCCURRED_AT)
        self.factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        self._build_fixture()
        self.impacts = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        preview = self.impacts.preview(self.change)
        run = self.impacts.begin(
            self.change,
            preview_sha256=preview.preview_sha256,
            run_id=uid(80_002),
            batch_size=8,
        )
        self.impacts.advance(run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256)
        self.recalculation = sqlite_selective_recalculation_repository(self.root, PROJECT_ID)
        self.workflows = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        self.service = SelectiveRecalculationService(
            unit_of_work=self.factory,
            dependencies=sqlite_material_dependency_repository(self.root, PROJECT_ID),
            recalculation=self.recalculation,
            workflows=self.workflows,
        )

    def tearDown(self) -> None:
        self.protection.__exit__(None, None, None)
        self.temporary.cleanup()

    def _append(self, draft: AggregateRevisionDraft, index: int, expected: int | None = None) -> AggregateRevision:
        with self.factory() as unit:
            revision = unit.aggregates.append(draft, event(index), expected_revision=expected)
            unit.commit()
            return revision

    def _append_privacy_policy(self) -> None:
        settings = tuple(
            PrivacySetting(key, value)
            for key, value in sorted(
                {
                    "privacy.cache-retention-days": 30,
                    "privacy.document-retention": "project-lifetime",
                    "privacy.egress-consent-version": "none",
                    "privacy.log-retention-days": 14,
                    "privacy.network-policy": "offline",
                    "privacy.remote-model-approval": "preview-every-task",
                    "privacy.telemetry-mode": "off",
                }.items()
            )
        )
        sqlite_privacy_policy_repository(self.root, PROJECT_ID).append(
            expected_revision=0,
            revision=1,
            settings=settings,
            event=PrivacyAuditEvent(
                event_id=uid(89_001),
                event_type="privacy.policy.changed",
                occurred_at="2026-09-01T22:00:30.000Z",
                trace_id="7" * 32,
                record_sha256="f" * 64,
            ),
        )

    def _build_fixture(self) -> None:
        self.source_v1 = self._append(
            AggregateRevisionDraft(
                revision_id=uid(1),
                aggregate_id=uid(101),
                aggregate_kind="evidence",
                created_at=OCCURRED_AT,
                modified_at=OCCURRED_AT,
                display_label_observed="source v1",
                display_label_normalized=None,
                knowledge_status="observed",
                rights_status="allowed",
                dependency_coverage="not-applicable",
            ),
            1,
        )
        self.source_v2 = self._append(
            replace(
                AggregateRevisionDraft(
                    revision_id=uid(2),
                    aggregate_id=self.source_v1.aggregate_id,
                    aggregate_kind="evidence",
                    created_at=OCCURRED_AT,
                    modified_at="2026-09-01T22:00:02.000Z",
                    display_label_observed="source v2",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="allowed",
                    dependency_coverage="not-applicable",
                ),
                provenance_inputs=(self.source_v1,),
            ),
            2,
            0,
        )
        self.verified = self._append(
            AggregateRevisionDraft(
                revision_id=uid(3),
                aggregate_id=uid(103),
                aggregate_kind="evidence",
                created_at=OCCURRED_AT,
                modified_at="2026-09-01T22:00:03.000Z",
                display_label_observed="verified unchanged input",
                display_label_normalized=None,
                knowledge_status="verified",
                rights_status="allowed",
                dependency_coverage="not-applicable",
            ),
            3,
        )
        self.adjudicated = self._append(
            AggregateRevisionDraft(
                revision_id=uid(4),
                aggregate_id=uid(104),
                aggregate_kind="evidence",
                created_at=OCCURRED_AT,
                modified_at="2026-09-01T22:00:04.000Z",
                display_label_observed="adjudicated synthesis",
                display_label_normalized="adjudicated synthesis",
                knowledge_status="adjudicated",
                rights_status="allowed",
                dependency_coverage="complete",
                provenance_inputs=(self.source_v1, self.verified),
                material_dependencies=(
                    dependency(4, self.source_v1, "a"),
                    dependency(5, self.verified, "c"),
                ),
            ),
            4,
        )
        self.change = DependencyChange(
            change_id=uid(80_001),
            idempotency_key="source-v1-superseded",
            reason="SOURCE_VERSION",
            dependency_kind="source-revision",
            previous_revision_id=self.source_v1.revision_id,
            replacement_revision_id=self.source_v2.revision_id,
            configuration_id=None,
            previous_configuration_version=None,
            replacement_configuration_version=None,
            previous_fingerprint=fingerprint("a"),
            replacement_fingerprint=fingerprint("b"),
            propagation_policy_id="dependency.propagation.v1",
            propagation_policy_version="1.0.0",
            actor_id=SYSTEM_ID,
            trace_id="9" * 32,
            occurred_at=OCCURRED_AT,
        )

    def request(self, *, target_revision_id: str | None = None) -> RecalculationWorkflowRequest:
        return RecalculationWorkflowRequest(
            target_revision_id=target_revision_id or self.adjudicated.revision_id,
            change=self.change,
            identity=RecalculationWorkflowIdentity(
                workflow_definition_id=uid(90_001),
                definition_revision_id=uid(90_002),
                workflow_run_id=uid(90_003),
                snapshot_id=uid(90_004),
                step_run_id=uid(90_005),
                job_id=uid(90_006),
                history_event_ids=tuple(uid(91_000 + index) for index in range(5)),
            ),
            actor=WorkflowActor(SYSTEM_ID, "system", "workflow-coordinator"),
            created_at="2026-09-01T22:01:00.000Z",
            available_at="2026-09-01T22:01:00.000Z",
            intent_id=uid(90_007),
            intent_revision_id=uid(90_008),
            intent_sha256=fingerprint("d"),
            configuration_id="selective-recalculation-default",
            configuration_version="1.0.0",
            priority=10,
        )

    def candidate_draft(self) -> AggregateRevisionDraft:
        return AggregateRevisionDraft(
            revision_id=uid(5),
            aggregate_id=self.adjudicated.aggregate_id,
            aggregate_kind="evidence",
            created_at=self.adjudicated.created_at,
            modified_at="2026-09-01T22:02:00.000Z",
            display_label_observed="recomputed synthesis candidate",
            display_label_normalized="recomputed synthesis candidate",
            knowledge_status="verified",
            rights_status="allowed",
            dependency_coverage="complete",
            provenance_inputs=(self.adjudicated, self.source_v2, self.verified),
            material_dependencies=(
                dependency(6, self.source_v2, "b"),
                dependency(7, self.verified, "c"),
            ),
        )

    def _authority_counts(self) -> tuple[int, ...]:
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            return tuple(
                int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
                for table in (
                    "aggregate_revisions",
                    "provenance_events",
                    "outbox_events",
                    "workflow_attempt_artifacts",
                    "workflow_committed_outputs",
                    "workflow_history_events",
                )
            )
        finally:
            connection.close()

    def _restorable_pair(self, index: int) -> tuple[AggregateRevision, AggregateRevision]:
        prior = self._append(
            AggregateRevisionDraft(
                revision_id=uid(index),
                aggregate_id=uid(200 + index),
                aggregate_kind="evidence",
                created_at=OCCURRED_AT,
                modified_at=f"2026-09-01T22:00:{index:02d}.000Z",
                display_label_observed=f"adjudicated value {index}",
                display_label_normalized=f"adjudicated value {index}",
                knowledge_status="adjudicated",
                rights_status="allowed",
                dependency_coverage="complete",
                provenance_inputs=(self.source_v1,),
                material_dependencies=(dependency(index, self.source_v1, "a"),),
            ),
            index,
        )
        current = self._append(
            AggregateRevisionDraft(
                revision_id=uid(index + 1),
                aggregate_id=prior.aggregate_id,
                aggregate_kind="evidence",
                created_at=prior.created_at,
                modified_at=f"2026-09-01T22:00:{index + 1:02d}.000Z",
                display_label_observed=f"candidate value {index}",
                display_label_normalized=f"candidate value {index}",
                knowledge_status="verified",
                rights_status="allowed",
                dependency_coverage="complete",
                provenance_inputs=(prior, self.source_v1),
                material_dependencies=(dependency(index + 1, self.source_v1, "a"),),
            ),
            index + 1,
            0,
        )
        return prior, current

    def _restore_command(
        self,
        prior: AggregateRevision,
        current: AggregateRevision,
        index: int,
        *,
        disposition: str = "approved",
    ) -> RestoreRevisionCommand:
        identity_base = 130_000 + index * 20
        identity = RestoreReviewIdentity(
            workflow_definition_id=uid(identity_base),
            definition_revision_id=uid(identity_base + 1),
            workflow_run_id=uid(identity_base + 2),
            snapshot_id=uid(identity_base + 3),
            step_run_id=uid(identity_base + 4),
            human_task_id=uid(identity_base + 5),
            history_event_ids=tuple(uid(identity_base + 6 + offset) for offset in range(7)),
        )
        actor = WorkflowActor(RESEARCHER_ID, "human", "researcher")
        review = self.service.request_restore_review(
            RestoreReviewRequest(
                prior_adjudicated_revision_id=prior.revision_id,
                expected_current_revision_id=current.revision_id,
                identity=identity,
                actor=actor,
                created_at=f"2026-09-01T23:{index:02d}:00.000Z",
                intent_id=uid(identity_base + 13),
                intent_revision_id=uid(identity_base + 14),
                intent_sha256=fingerprint("d"),
                configuration_id="selective-recalculation-restore-default",
                configuration_version="1.0.0",
            )
        )
        decision_id = uid(identity_base + 15)
        self.workflows.complete_human_task(
            review.human_task_id,
            expected_snapshot_revision=review.snapshot_revision,
            expected_history_sequence=review.history_sequence,
            decision_id=decision_id,
            disposition=disposition,  # type: ignore[arg-type]
            actor=actor,
            now=f"2026-09-01T23:{index:02d}:01.000Z",
        )
        occurred_at = f"2026-09-01T23:{index:02d}:02.000Z"
        return RestoreRevisionCommand(
            prior_adjudicated_revision_id=prior.revision_id,
            expected_current_revision_id=current.revision_id,
            new_revision_id=uid(index + 2),
            dependency_ids=(uid(31_000 + index),),
            workflow_run_id=review.workflow_run_id,
            human_task_id=review.human_task_id,
            decision_id=decision_id,
            modified_at=occurred_at,
            event=event(
                index + 2,
                actor_type="human",
                event_type="aggregate.revision-restored",
                idempotency_key=f"restore-revision:{decision_id}",
                occurred_at=occurred_at,
            ),
        )

    def test_restore_requires_exact_completed_human_decision_and_current_policy(self) -> None:
        prior, current = self._restorable_pair(54)
        command = self._restore_command(prior, current, 54)

        with self.assertRaises(WorkflowQueueConflict):
            self.service.restore(replace(command, event=replace(command.event, actor_id=SYSTEM_ID)))
        substituted_decision_id = uid(150_001)
        with self.assertRaises(WorkflowQueueConflict):
            self.service.restore(
                replace(
                    command,
                    decision_id=substituted_decision_id,
                    event=replace(command.event, idempotency_key=f"restore-revision:{substituted_decision_id}"),
                )
            )

        self._append_privacy_policy()
        with self.assertRaises(WorkflowQueueConflict):
            self.service.restore(command)
        with self.factory() as unit:
            self.assertEqual(
                (prior.revision_id, current.revision_id),
                tuple(item.revision_id for item in unit.aggregates.history(prior.aggregate_id)),
            )

        rejected_prior, rejected_current = self._restorable_pair(57)
        rejected = self._restore_command(rejected_prior, rejected_current, 57, disposition="rejected")
        with self.assertRaises(WorkflowQueueConflict):
            self.service.restore(rejected)

    def _impact_change(self, index: int) -> DependencyChange:
        return replace(
            self.change,
            change_id=uid(81_000 + index),
            idempotency_key=f"source-v1-superseded-restore-{index}",
            trace_id=f"{index:x}"[-1] * 32,
            occurred_at=f"2026-09-01T22:10:{index:02d}.000Z",
        )

    def commit_candidate(self, draft: AggregateRevisionDraft) -> tuple[AggregateRevision, WorkflowJobClaim]:
        scheduled = self.service.schedule(self.request())
        claim = self.workflows.claim_next(
            worker_id=uid(92_001),
            concurrency_classes=("document",),
            now="2026-09-01T22:01:01.000Z",
            lease_duration_ms=60_000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        self.workflows.start(claim, now="2026-09-01T22:01:02.000Z")
        checkpoint_artifact = WorkflowOutputReference(
            artifact_id=self.verified.aggregate_id,
            revision_id=self.verified.revision_id,
            content_hash=revision_content_hash(self.verified),
            media_type="application/vnd.research-observatory.recalculation-checkpoint+json",
            provenance_entity_id=self.verified.aggregate_id,
        )
        self.workflows.stage_artifact(
            claim,
            artifact=checkpoint_artifact,
            role="checkpoint",
            now="2026-09-01T22:01:03.000Z",
        )
        self.workflows.checkpoint(
            claim,
            checkpoint_id=uid(92_002),
            state_hash=checkpoint_artifact.content_hash,
            payload_artifact_id=checkpoint_artifact.artifact_id,
            now="2026-09-01T22:01:04.000Z",
            progress={"kind": "quantified", "unit": "outputs", "completedUnits": 0, "totalUnits": 1},
        )
        completed_at = "2026-09-01T22:01:05.000Z"
        candidate_event = event(
            5,
            actor_id=claim.worker_id,
            event_type="aggregate.recalculation-candidate-created",
            idempotency_key=f"recalculation-candidate:{claim.job_id}",
            occurred_at=completed_at,
        )
        candidate = self.service.append_candidate(
            draft,
            candidate_event,
            claim=claim,
            expected_current_revision_id=self.adjudicated.revision_id,
            plan_sha256=scheduled.workflow.plan_sha256,
            completed_at=completed_at,
        )
        reopened_service = SelectiveRecalculationService(
            unit_of_work=create_sqlite_unit_of_work_factory(self.database, PROJECT_ID),
            dependencies=sqlite_material_dependency_repository(self.root, PROJECT_ID),
            recalculation=sqlite_selective_recalculation_repository(self.root, PROJECT_ID),
        )
        replay = reopened_service.append_candidate(
            draft,
            candidate_event,
            claim=claim,
            expected_current_revision_id=self.adjudicated.revision_id,
            plan_sha256=scheduled.workflow.plan_sha256,
            completed_at=completed_at,
        )
        self.assertEqual(candidate, replay)
        return candidate, claim

    def test_selective_job_reuses_only_unchanged_verified_inputs_and_survives_restart(self) -> None:
        scheduled = self.service.schedule(self.request())
        replay = self.service.schedule(self.request())

        self.assertEqual(self.adjudicated.revision_id, scheduled.workflow.target_revision_id)
        self.assertEqual((self.source_v2.revision_id,), scheduled.workflow.replacement_revision_ids)
        self.assertEqual((self.verified.revision_id,), scheduled.workflow.reused_revision_ids)
        self.assertEqual(scheduled.workflow.plan_sha256, scheduled.workflow.submission.command_fingerprint)
        definition = json.loads(scheduled.workflow.submission.definition_json)
        snapshot = json.loads(scheduled.workflow.submission.snapshot_json)
        self.assertEqual((), workflow_snapshot_errors(definition, snapshot))
        media_by_revision = {item["revisionId"]: item["mediaType"] for item in snapshot["artifacts"]}
        self.assertEqual(
            "application/vnd.research-observatory.replacement-revision+json",
            media_by_revision[self.source_v2.revision_id],
        )
        self.assertNotIn(self.source_v1.revision_id, media_by_revision)
        self.assertEqual(1, len(scheduled.workflow.stale_cause_ids))
        self.assertEqual("runnable", scheduled.job.state)
        self.assertEqual(scheduled.job, replay.job)
        self.assertEqual(scheduled.workflow.submission, replay.workflow.submission)

        reopened = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        authority = reopened.authority(scheduled.job.job_id)
        self.assertEqual(scheduled.workflow.submission.definition_json, authority.definition_json)
        self.assertEqual(scheduled.workflow.submission.snapshot_json, authority.snapshot_json)
        projection = reopened.task_center(limit=10)[0]
        self.assertEqual("selective-recalculation", projection.workflow_key)
        self.assertEqual("queued", projection.state)

    def test_enqueue_fails_without_queue_write_when_authority_changes_after_planning(self) -> None:
        verified_v2 = self._append(
            AggregateRevisionDraft(
                revision_id=uid(8),
                aggregate_id=self.verified.aggregate_id,
                aggregate_kind="evidence",
                created_at=self.verified.created_at,
                modified_at="2026-09-01T22:00:08.000Z",
                display_label_observed="verified replacement input",
                display_label_normalized=None,
                knowledge_status="verified",
                rights_status="allowed",
                dependency_coverage="not-applicable",
                provenance_inputs=(self.verified,),
            ),
            8,
            0,
        )
        second_change = DependencyChange(
            change_id=uid(80_010),
            idempotency_key="verified-v1-superseded",
            reason="SOURCE_VERSION",
            dependency_kind="source-revision",
            previous_revision_id=self.verified.revision_id,
            replacement_revision_id=verified_v2.revision_id,
            configuration_id=None,
            previous_configuration_version=None,
            replacement_configuration_version=None,
            previous_fingerprint=fingerprint("c"),
            replacement_fingerprint=fingerprint("f"),
            propagation_policy_id="dependency.propagation.v1",
            propagation_policy_version="1.0.0",
            actor_id=SYSTEM_ID,
            trace_id="8" * 32,
            occurred_at="2026-09-01T22:00:08.000Z",
        )

        def inject_propagation() -> None:
            preview = self.impacts.preview(second_change)
            run = self.impacts.begin(
                second_change,
                preview_sha256=preview.preview_sha256,
                run_id=uid(80_011),
                batch_size=8,
            )
            self.impacts.advance(run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256)

        racing_service = SelectiveRecalculationService(
            unit_of_work=self.factory,
            dependencies=sqlite_material_dependency_repository(self.root, PROJECT_ID),
            recalculation=InjectBeforeEnqueue(self.recalculation, inject_propagation),
        )
        with self.assertRaises(WorkflowQueueConflict):
            racing_service.schedule(self.request())
        self.assertEqual((), self.workflows.task_center(limit=10))

    def test_enqueue_fails_without_queue_write_when_privacy_policy_changes_after_planning(self) -> None:
        racing_service = SelectiveRecalculationService(
            unit_of_work=self.factory,
            dependencies=sqlite_material_dependency_repository(self.root, PROJECT_ID),
            recalculation=InjectBeforeEnqueue(self.recalculation, self._append_privacy_policy),
        )

        with self.assertRaises(WorkflowQueueConflict):
            racing_service.schedule(self.request())

        self.assertEqual((), self.workflows.task_center(limit=10))

    def test_candidate_requires_an_active_exact_workflow_and_specific_event(self) -> None:
        draft = self.candidate_draft()
        missing_claim = WorkflowJobClaim(
            project_id=PROJECT_ID,
            workflow_run_id=uid(93_001),
            job_id=uid(93_002),
            step_run_id=uid(93_003),
            activity_type="selective-recalculation",
            concurrency_class="document",
            attempt_id=uid(93_004),
            attempt_number=1,
            worker_id=uid(93_005),
            lease_token="missing-workflow-lease",
            lease_generation=1,
            lease_expires_at="2026-09-01T22:02:00.000Z",
            idempotency_key="missing-workflow",
            command_fingerprint=fingerprint("a"),
            latest_checkpoint=None,
        )
        missing_event = event(
            9,
            actor_id=missing_claim.worker_id,
            event_type="aggregate.recalculation-candidate-created",
            idempotency_key=f"recalculation-candidate:{missing_claim.job_id}",
            occurred_at="2026-09-01T22:01:05.000Z",
        )
        with self.assertRaises(WorkflowQueueProblem):
            self.service.append_candidate(
                draft,
                missing_event,
                claim=missing_claim,
                expected_current_revision_id=self.adjudicated.revision_id,
                plan_sha256=missing_claim.command_fingerprint,
                completed_at=missing_event.occurred_at,
            )

        scheduled = self.service.schedule(self.request())
        claim = self.workflows.claim_next(
            worker_id=uid(93_006),
            concurrency_classes=("document",),
            now="2026-09-01T22:01:01.000Z",
            lease_duration_ms=60_000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        completed_at = "2026-09-01T22:01:05.000Z"
        candidate_event = event(
            10,
            actor_id=claim.worker_id,
            event_type="aggregate.recalculation-candidate-created",
            idempotency_key=f"recalculation-candidate:{claim.job_id}",
            occurred_at=completed_at,
        )
        with self.assertRaises(WorkflowQueueProblem):
            self.service.append_candidate(
                draft,
                candidate_event,
                claim=claim,
                expected_current_revision_id=self.adjudicated.revision_id,
                plan_sha256=scheduled.workflow.plan_sha256,
                completed_at=completed_at,
            )
        with self.assertRaises(RepositoryConflict):
            self.service.append_candidate(
                draft,
                event(11, actor_id=claim.worker_id, occurred_at=completed_at),
                claim=claim,
                expected_current_revision_id=self.adjudicated.revision_id,
                plan_sha256=scheduled.workflow.plan_sha256,
                completed_at=completed_at,
            )
        with self.factory() as unit:
            self.assertEqual((self.adjudicated,), unit.aggregates.history(self.adjudicated.aggregate_id))

    def test_candidate_rejects_each_substituted_claim_field_without_any_write(self) -> None:
        scheduled = self.service.schedule(self.request())
        claim = self.workflows.claim_next(
            worker_id=uid(93_100),
            concurrency_classes=("document",),
            now="2026-09-01T22:01:01.000Z",
            lease_duration_ms=60_000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        self.workflows.start(claim, now="2026-09-01T22:01:02.000Z")
        checkpoint_artifact = WorkflowOutputReference(
            artifact_id=self.verified.aggregate_id,
            revision_id=self.verified.revision_id,
            content_hash=revision_content_hash(self.verified),
            media_type="application/vnd.research-observatory.recalculation-checkpoint+json",
            provenance_entity_id=self.verified.aggregate_id,
        )
        self.workflows.stage_artifact(
            claim,
            artifact=checkpoint_artifact,
            role="checkpoint",
            now="2026-09-01T22:01:03.000Z",
        )
        self.workflows.checkpoint(
            claim,
            checkpoint_id=uid(93_101),
            state_hash=checkpoint_artifact.content_hash,
            payload_artifact_id=checkpoint_artifact.artifact_id,
            now="2026-09-01T22:01:04.000Z",
            progress={"kind": "quantified", "unit": "outputs", "completedUnits": 0, "totalUnits": 1},
        )
        baseline = self._authority_counts()
        substitutions = (
            ("project", replace(claim, project_id=uid(93_102))),
            ("workflow-run", replace(claim, workflow_run_id=uid(93_103))),
            ("job", replace(claim, job_id=uid(93_104))),
            ("step-run", replace(claim, step_run_id=uid(93_105))),
            ("activity", replace(claim, activity_type="substituted-activity")),
            ("concurrency", replace(claim, concurrency_class="ai")),
            ("attempt", replace(claim, attempt_id=uid(93_106))),
            ("attempt-number", replace(claim, attempt_number=claim.attempt_number + 1)),
            ("worker", replace(claim, worker_id=uid(93_107))),
            ("lease-token", replace(claim, lease_token="substituted-lease-token")),
            ("lease-generation", replace(claim, lease_generation=claim.lease_generation + 1)),
            ("idempotency", replace(claim, idempotency_key="substituted-idempotency")),
            ("command", replace(claim, command_fingerprint=fingerprint("f"))),
        )
        completed_at = "2026-09-01T22:01:05.000Z"
        for name, substituted in substitutions:
            candidate_event = event(
                14,
                actor_id=substituted.worker_id,
                event_type="aggregate.recalculation-candidate-created",
                idempotency_key=f"recalculation-candidate:{substituted.job_id}",
                occurred_at=completed_at,
            )
            with self.subTest(field=name), self.assertRaises(WorkflowQueueProblem):
                self.service.append_candidate(
                    self.candidate_draft(),
                    candidate_event,
                    claim=substituted,
                    expected_current_revision_id=self.adjudicated.revision_id,
                    plan_sha256=scheduled.workflow.plan_sha256,
                    completed_at=completed_at,
                )
            self.assertEqual(baseline, self._authority_counts())

        candidate_event = event(
            14,
            actor_id=claim.worker_id,
            event_type="aggregate.recalculation-candidate-created",
            idempotency_key=f"recalculation-candidate:{claim.job_id}",
            occurred_at=completed_at,
        )
        candidate = self.service.append_candidate(
            self.candidate_draft(),
            candidate_event,
            claim=claim,
            expected_current_revision_id=self.adjudicated.revision_id,
            plan_sha256=scheduled.workflow.plan_sha256,
            completed_at=completed_at,
        )
        committed = self._authority_counts()
        reopened = SelectiveRecalculationService(
            unit_of_work=create_sqlite_unit_of_work_factory(self.database, PROJECT_ID),
            dependencies=sqlite_material_dependency_repository(self.root, PROJECT_ID),
            recalculation=sqlite_selective_recalculation_repository(self.root, PROJECT_ID),
        )
        self.assertEqual(
            candidate,
            reopened.append_candidate(
                self.candidate_draft(),
                candidate_event,
                claim=claim,
                expected_current_revision_id=self.adjudicated.revision_id,
                plan_sha256=scheduled.workflow.plan_sha256,
                completed_at=completed_at,
            ),
        )
        self.assertEqual(committed, self._authority_counts())

    def test_cancelled_workflow_and_substituted_dependency_cannot_commit_candidate(self) -> None:
        scheduled = self.service.schedule(self.request())
        claim = self.workflows.claim_next(
            worker_id=uid(94_001),
            concurrency_classes=("document",),
            now="2026-09-01T22:01:01.000Z",
            lease_duration_ms=60_000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        self.workflows.start(claim, now="2026-09-01T22:01:02.000Z")
        completed_at = "2026-09-01T22:01:05.000Z"
        candidate_event = event(
            12,
            actor_id=claim.worker_id,
            event_type="aggregate.recalculation-candidate-created",
            idempotency_key=f"recalculation-candidate:{claim.job_id}",
            occurred_at=completed_at,
        )
        substituted = replace(
            self.candidate_draft(),
            material_dependencies=(
                dependency(6, self.source_v1, "a"),
                dependency(7, self.verified, "c"),
            ),
        )
        with self.assertRaises(RepositoryConflict):
            self.service.append_candidate(
                substituted,
                candidate_event,
                claim=claim,
                expected_current_revision_id=self.adjudicated.revision_id,
                plan_sha256=scheduled.workflow.plan_sha256,
                completed_at=completed_at,
            )
        with self.assertRaises(RepositoryConflict):
            self.service.append_candidate(
                replace(self.candidate_draft(), rights_status="denied"),
                candidate_event,
                claim=claim,
                expected_current_revision_id=self.adjudicated.revision_id,
                plan_sha256=scheduled.workflow.plan_sha256,
                completed_at=completed_at,
            )
        self.workflows.cancel(claim, now="2026-09-01T22:01:03.000Z", reason_code="user-cancelled")
        with self.assertRaises(WorkflowQueueProblem):
            self.service.append_candidate(
                self.candidate_draft(),
                candidate_event,
                claim=claim,
                expected_current_revision_id=self.adjudicated.revision_id,
                plan_sha256=scheduled.workflow.plan_sha256,
                completed_at=completed_at,
            )
        with self.factory() as unit:
            self.assertEqual((self.adjudicated,), unit.aggregates.history(self.adjudicated.aggregate_id))

    def test_recovered_but_unfinished_workflow_cannot_commit_candidate(self) -> None:
        scheduled = self.service.schedule(self.request())
        claim = self.workflows.claim_next(
            worker_id=uid(95_001),
            concurrency_classes=("document",),
            now="2026-09-01T22:01:01.000Z",
            lease_duration_ms=1_000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        self.workflows.start(claim, now="2026-09-01T22:01:01.500Z")
        self.assertEqual(
            1,
            self.workflows.recover_expired(
                now="2026-09-01T22:01:03.000Z",
                actor=WorkflowActor(SYSTEM_ID, "system", "workflow-recovery"),
            ),
        )
        completed_at = "2026-09-01T22:01:04.000Z"
        candidate_event = event(
            13,
            actor_id=claim.worker_id,
            event_type="aggregate.recalculation-candidate-created",
            idempotency_key=f"recalculation-candidate:{claim.job_id}",
            occurred_at=completed_at,
        )
        with self.assertRaises(WorkflowQueueProblem):
            self.service.append_candidate(
                self.candidate_draft(),
                candidate_event,
                claim=claim,
                expected_current_revision_id=self.adjudicated.revision_id,
                plan_sha256=scheduled.workflow.plan_sha256,
                completed_at=completed_at,
            )
        with self.factory() as unit:
            self.assertEqual((self.adjudicated,), unit.aggregates.history(self.adjudicated.aggregate_id))

    def test_candidate_commit_is_atomic_with_completed_plan_and_retains_history(self) -> None:
        candidate_draft = self.candidate_draft()
        candidate, claim = self.commit_candidate(candidate_draft)
        comparison = self.service.compare(self.adjudicated.revision_id, candidate.revision_id)
        self.assertEqual(
            ("display-label-normalized", "display-label-observed", "knowledge-status"),
            comparison.changed_fields,
        )
        self.assertEqual(1, candidate.revision)
        self.assertEqual("succeeded", self.workflows.get(claim.job_id).state)
        reopened_factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        with reopened_factory() as unit:
            self.assertEqual(
                (self.adjudicated.revision_id, candidate.revision_id),
                tuple(item.revision_id for item in unit.aggregates.history(self.adjudicated.aggregate_id)),
            )
            self.assertEqual(self.adjudicated, unit.aggregates.get_revision(self.adjudicated.revision_id))
        candidate_dependencies = sqlite_material_dependency_repository(self.root, PROJECT_ID).registration(
            candidate.revision_id
        )
        self.assertEqual(
            (self.source_v2.revision_id, self.verified.revision_id),
            tuple(item.revision_id for item in candidate_dependencies.dependencies),
        )
        with self.assertRaises(RepositoryConflict):
            self.service.restore(
                RestoreRevisionCommand(
                    prior_adjudicated_revision_id=self.adjudicated.revision_id,
                    expected_current_revision_id=candidate.revision_id,
                    new_revision_id=uid(6),
                    dependency_ids=(uid(30_008), uid(30_009)),
                    workflow_run_id=uid(140_001),
                    human_task_id=uid(140_002),
                    decision_id=uid(140_003),
                    modified_at="2026-09-01T22:03:00.000Z",
                    event=event(
                        6,
                        actor_type="human",
                        event_type="aggregate.revision-restored",
                        occurred_at="2026-09-01T22:03:00.000Z",
                    ),
                )
            )
        with self.factory() as unit:
            self.assertEqual(
                (self.adjudicated.revision_id, candidate.revision_id),
                tuple(item.revision_id for item in unit.aggregates.history(self.adjudicated.aggregate_id)),
            )

    def test_fresh_adjudicated_restore_appends_without_rewinding_history(self) -> None:
        prior = self._append(
            AggregateRevisionDraft(
                revision_id=uid(40),
                aggregate_id=uid(140),
                aggregate_kind="evidence",
                created_at=OCCURRED_AT,
                modified_at="2026-09-01T22:10:00.000Z",
                display_label_observed="stable adjudicated value",
                display_label_normalized="stable adjudicated value",
                knowledge_status="adjudicated",
                rights_status="allowed",
                dependency_coverage="complete",
                provenance_inputs=(self.verified,),
                material_dependencies=(dependency(40, self.verified, "c"),),
            ),
            40,
        )
        current = self._append(
            AggregateRevisionDraft(
                revision_id=uid(41),
                aggregate_id=prior.aggregate_id,
                aggregate_kind="evidence",
                created_at=prior.created_at,
                modified_at="2026-09-01T22:11:00.000Z",
                display_label_observed="new candidate value",
                display_label_normalized="new candidate value",
                knowledge_status="verified",
                rights_status="allowed",
                dependency_coverage="complete",
                provenance_inputs=(prior, self.verified),
                material_dependencies=(dependency(41, self.verified, "c"),),
            ),
            41,
            0,
        )
        command = self._restore_command(prior, current, 40)
        restored = self.service.restore(command)
        reopened = SelectiveRecalculationService(
            unit_of_work=create_sqlite_unit_of_work_factory(self.database, PROJECT_ID),
            dependencies=sqlite_material_dependency_repository(self.root, PROJECT_ID),
            recalculation=sqlite_selective_recalculation_repository(self.root, PROJECT_ID),
        )
        self.assertEqual(restored, reopened.restore(command))
        self.assertEqual(2, restored.revision)
        self.assertEqual("adjudicated", restored.knowledge_status)
        self.assertEqual((), self.service.compare(prior.revision_id, restored.revision_id).changed_fields)
        with self.factory() as unit:
            self.assertEqual(
                (prior.revision_id, current.revision_id, restored.revision_id),
                tuple(item.revision_id for item in unit.aggregates.history(prior.aggregate_id)),
            )

    def test_restore_rejects_started_cancelled_and_multiple_durable_changes_after_restart(self) -> None:
        prior, current = self._restorable_pair(43)
        command = self._restore_command(prior, current, 43)
        first_change = self._impact_change(1)
        preview = self.impacts.preview(first_change)
        started = self.impacts.begin(
            first_change,
            preview_sha256=preview.preview_sha256,
            run_id=uid(82_001),
            batch_size=1_000,
        )
        self.assertEqual((), self.impacts.stale_states(output_revision_id=prior.revision_id))

        reopened = SelectiveRecalculationService(
            unit_of_work=create_sqlite_unit_of_work_factory(self.database, PROJECT_ID),
            dependencies=sqlite_material_dependency_repository(self.root, PROJECT_ID),
            recalculation=sqlite_selective_recalculation_repository(self.root, PROJECT_ID),
        )
        with self.assertRaises(RepositoryConflict):
            reopened.restore(command)
        self.assertEqual("running", self.impacts.run(started.run_id).state)

        cancelled = self.impacts.cancel(
            started.run_id,
            expected_checkpoint_sha256=started.checkpoint_sha256,
            occurred_at="2026-09-01T22:11:00.000Z",
        )
        self.assertEqual("cancelled", cancelled.state)
        with self.assertRaises(RepositoryConflict):
            reopened.restore(command)

        second_change = self._impact_change(2)
        second_preview = self.impacts.preview(second_change)
        second = self.impacts.begin(
            second_change,
            preview_sha256=second_preview.preview_sha256,
            run_id=uid(82_002),
            batch_size=1_000,
        )
        with self.assertRaises(RepositoryConflict):
            reopened.restore(command)
        self.assertEqual("cancelled", self.impacts.run(started.run_id).state)
        self.assertEqual("running", self.impacts.run(second.run_id).state)
        with self.factory() as unit:
            self.assertEqual(
                (prior.revision_id, current.revision_id),
                tuple(item.revision_id for item in unit.aggregates.history(prior.aggregate_id)),
            )

    def test_restore_rejects_unmaterialized_output_after_partial_checkpoint(self) -> None:
        pairs = (self._restorable_pair(46), self._restorable_pair(49))
        change = self._impact_change(3)
        preview = self.impacts.preview(change)
        started = self.impacts.begin(
            change,
            preview_sha256=preview.preview_sha256,
            run_id=uid(82_003),
            batch_size=1,
        )
        checkpointed = self.impacts.advance(
            started.run_id,
            expected_checkpoint_sha256=started.checkpoint_sha256,
        )
        self.assertEqual("running", checkpointed.state)
        index, prior, current = next(
            (index, *pair)
            for index, pair in zip((46, 49), pairs, strict=True)
            if not self.impacts.stale_states(output_revision_id=pair[0].revision_id)
        )
        with self.assertRaises(RepositoryConflict):
            self.service.restore(self._restore_command(prior, current, index))
        self.assertEqual(checkpointed, self.impacts.run(started.run_id))

    def test_restore_rejects_failed_attempt_recovery_and_completed_impact(self) -> None:
        prior, current = self._restorable_pair(52)
        command = self._restore_command(prior, current, 52)
        change = self._impact_change(4)
        preview = self.impacts.preview(change)
        started = self.impacts.begin(
            change,
            preview_sha256=preview.preview_sha256,
            run_id=uid(82_004),
            batch_size=1_000,
        )
        with (
            patch(
                "research_observatory_core.repositories._record_dependency_stale_batch",
                side_effect=RuntimeError("injected batch failure"),
            ),
            self.assertRaises(RepositoryProblem),
        ):
            self.impacts.advance(started.run_id, expected_checkpoint_sha256=started.checkpoint_sha256)
        failed = self.impacts.run(started.run_id)
        self.assertEqual("failed-attempt", self.impacts.audit(run_id=started.run_id)[-1].event_type)
        self.assertEqual((), self.impacts.stale_states(output_revision_id=prior.revision_id))
        with self.assertRaises(RepositoryConflict):
            self.service.restore(command)

        reopened_impacts = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        completed = reopened_impacts.advance(
            started.run_id,
            expected_checkpoint_sha256=failed.checkpoint_sha256,
        )
        self.assertEqual("completed", completed.state)
        with self.assertRaises(RepositoryConflict):
            self.service.restore(command)
        self.assertTrue(reopened_impacts.stale_states(output_revision_id=prior.revision_id))

    def test_substitution_and_non_adjudicated_restore_fail_without_canonical_change(self) -> None:
        with self.assertRaises(RepositoryConflict):
            self.service.schedule(self.request(target_revision_id=self.source_v1.revision_id))
        with self.assertRaises(RepositoryConflict):
            self.service.compare(self.source_v1.revision_id, self.adjudicated.revision_id)
        with self.assertRaises(RepositoryConflict):
            self.service.restore(
                RestoreRevisionCommand(
                    prior_adjudicated_revision_id=self.verified.revision_id,
                    expected_current_revision_id=self.verified.revision_id,
                    new_revision_id=uid(7),
                    dependency_ids=(),
                    workflow_run_id=uid(140_011),
                    human_task_id=uid(140_012),
                    decision_id=uid(140_013),
                    modified_at="2026-09-01T22:04:00.000Z",
                    event=event(
                        7,
                        actor_type="human",
                        event_type="aggregate.revision-restored",
                        occurred_at="2026-09-01T22:04:00.000Z",
                    ),
                )
            )
        with self.factory() as unit:
            self.assertEqual((self.adjudicated,), unit.aggregates.history(self.adjudicated.aggregate_id))


if __name__ == "__main__":
    unittest.main()
