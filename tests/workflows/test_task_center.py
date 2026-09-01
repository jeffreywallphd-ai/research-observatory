from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.workflow_executor import WorkflowActor, WorkflowQueueConflict
from research_observatory_core.repositories import sqlite_workflow_queue_repository
from research_observatory_core.storage import development_plaintext_database_fixture, initialize_database
from research_observatory_core.workflow_contracts import canonical_workflow_json, workflow_record_sha256
from research_observatory_core.workflow_executor import prepare_workflow_job

from .test_local_workflow_executor import (
    CREATED_AT,
    FIXTURES,
    PROJECT_ID,
    SYSTEM,
    WORKER_A,
    _canonical_artifact,
    runnable_contracts,
)

RESEARCHER = WorkflowActor(
    actor_id="018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
    actor_type="human",
    role="researcher",
)


def waiting_human_authority() -> tuple[dict[str, Any], dict[str, Any], str]:
    definition = json.loads((FIXTURES / "valid-workflow-definition.v1.json").read_text(encoding="utf-8"))
    snapshot = json.loads((FIXTURES / "valid-local-workflow-snapshot.v1.json").read_text(encoding="utf-8"))
    human_definition = definition["steps"][1]["humanTask"]
    human_definition["allowedDispositions"] = ["approved", "rejected"]
    human_definition["consequencesByDisposition"] = {
        "approved": "resume-workflow",
        "rejected": "end-workflow",
    }
    snapshot["definition"]["contentHash"] = workflow_record_sha256(definition)
    snapshot["state"] = "waiting-human"
    snapshot["progress"] = {"kind": "quantified", "unit": "steps", "completedUnits": 1, "totalUnits": 2}
    snapshot["updatedAt"] = "2026-08-30T12:01:28.000Z"
    snapshot["sequence"] = 28
    snapshot["stepRuns"][1].update(
        state="waiting-human",
        sequence=26,
        progress={
            "kind": "quantified",
            "unit": "decisions",
            "completedUnits": 0,
            "totalUnits": 1,
        },
    )
    snapshot["humanTasks"][0].update(state="claimed", sequence=28, decision=None)
    snapshot["history"] = snapshot["history"][:28]
    return definition, snapshot, str(snapshot["humanTasks"][0]["humanTaskId"])


def waiting_human_with_downstream_activity() -> tuple[dict[str, Any], dict[str, Any], str]:
    definition, snapshot, human_task_id = waiting_human_authority()
    downstream_definition = deepcopy(definition["steps"][0])
    downstream_definition.update(
        stepKey="index-source",
        activityType="source-indexing",
        dependsOn=["review-source"],
    )
    definition["steps"].append(downstream_definition)
    snapshot["definition"]["contentHash"] = workflow_record_sha256(definition)
    snapshot["progress"] = {"kind": "quantified", "unit": "steps", "completedUnits": 1, "totalUnits": 3}
    downstream_step_id = "018f47a2-4d6b-7f78-9f2e-7fb76c86d012"
    downstream_job_id = "018f47a2-4d6b-7f78-9f2e-7fb76c86d028"
    snapshot["stepRuns"].append(
        {
            "stepRunId": downstream_step_id,
            "stepKey": "index-source",
            "state": "pending",
            "sequence": 29,
            "progress": {"kind": "quantified", "unit": "records", "completedUnits": 0, "totalUnits": 100},
            "jobIds": [downstream_job_id],
            "humanTaskIds": [],
            "inputArtifactIds": [],
            "outputArtifactIds": [],
        }
    )
    snapshot["jobs"].append(
        {
            "jobId": downstream_job_id,
            "stepRunId": downstream_step_id,
            "state": "pending",
            "sequence": 30,
            "idempotencyKey": "sha256:" + "8" * 64,
            "commandFingerprint": "sha256:" + "9" * 64,
            "attemptIds": [],
            "currentAttemptId": None,
            "inputArtifactIds": [],
            "outputArtifactIds": [],
            "cancellation": {"requestedAt": None, "reasonCode": None, "interruptionKind": None},
        }
    )
    actor = {"actorId": RESEARCHER.actor_id, "actorType": RESEARCHER.actor_type, "role": RESEARCHER.role}
    snapshot["history"].extend(
        [
            {
                "eventId": "018f47a2-4d6b-7f78-9f2e-7fb76c86e029",
                "sequence": 29,
                "entityType": "workflow-step",
                "entityId": downstream_step_id,
                "fromState": None,
                "toState": "pending",
                "occurredAt": "2026-08-30T12:01:29.000Z",
                "actor": actor,
                "reasonCode": "step-created",
                "progress": None,
                "decisionId": None,
                "checkpointId": None,
                "interruptionKind": None,
            },
            {
                "eventId": "018f47a2-4d6b-7f78-9f2e-7fb76c86e030",
                "sequence": 30,
                "entityType": "job",
                "entityId": downstream_job_id,
                "fromState": None,
                "toState": "pending",
                "occurredAt": "2026-08-30T12:01:30.000Z",
                "actor": actor,
                "reasonCode": "job-created",
                "progress": None,
                "decisionId": None,
                "checkpointId": None,
                "interruptionKind": None,
            },
        ]
    )
    snapshot["sequence"] = 30
    snapshot["updatedAt"] = "2026-08-30T12:01:30.000Z"
    return definition, snapshot, human_task_id


class WorkflowTaskCenterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "project"
        (self.root / "state").mkdir(parents=True)
        self.database = self.root / "state" / "project.sqlite3"
        self.protection = development_plaintext_database_fixture()
        self.protection.__enter__()
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.repository = sqlite_workflow_queue_repository(self.root, PROJECT_ID)

    def tearDown(self) -> None:
        self.protection.__exit__(None, None, None)
        self.temporary.cleanup()

    def enqueue(self):
        definition, snapshot, job_id = runnable_contracts()
        submission = prepare_workflow_job(
            definition,
            snapshot,
            job_id=job_id,
            concurrency_class="document",
            priority=4,
            available_at="2026-08-30T12:02:00.000Z",
        )
        return self.repository.enqueue(submission, actor=SYSTEM)

    def test_projection_distinguishes_compute_wait_and_reports_safe_cancellation_artifacts(self) -> None:
        job = self.enqueue()
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        self.repository.heartbeat(
            claim,
            now="2026-08-30T12:02:00.200Z",
            lease_duration_ms=30_000,
            progress={"kind": "quantified", "unit": "records", "completedUnits": 40, "totalUnits": 100},
        )
        partial = _canonical_artifact(self.root, 90)
        self.repository.stage_artifact(
            claim,
            artifact=partial,
            role="output",
            now="2026-08-30T12:02:00.250Z",
        )

        running = self.repository.task_center(limit=20)
        self.assertEqual(1, len(running))
        self.assertEqual("running", running[0].state)
        self.assertTrue(running[0].active_compute)
        self.assertEqual("document", running[0].jobs[0].resource_pool)
        self.assertEqual(40, running[0].jobs[0].progress.completed_units)
        self.assertFalse(hasattr(running[0].jobs[0], "lease_token"))

        revision = running[0].revision
        with self.assertRaises(WorkflowQueueConflict):
            self.repository.request_cancellation(
                job.job_id,
                actor=RESEARCHER,
                now="2026-08-30T12:02:00.290Z",
                reason_code="user-requested",
                interruption_kind="user-cancel",
                expected_snapshot_revision=running[0].snapshot_revision + 1,
                expected_history_sequence=revision,
            )
        requested = self.repository.request_cancellation(
            job.job_id,
            actor=RESEARCHER,
            now="2026-08-30T12:02:00.300Z",
            reason_code="user-requested",
            interruption_kind="user-cancel",
            expected_snapshot_revision=running[0].snapshot_revision,
            expected_history_sequence=revision,
        )
        self.assertEqual("cancelling", requested.state)
        self.repository.cancel(claim, now="2026-08-30T12:02:00.400Z", reason_code="user-requested")

        cancelled = self.repository.task_center(limit=20)[0]
        self.assertEqual("cancelled", cancelled.state)
        self.assertFalse(cancelled.active_compute)
        self.assertEqual(("retained-incomplete",), cancelled.retained_artifacts)
        self.assertEqual("user-cancel", cancelled.interruption_kind)

    def test_human_decision_creates_immutable_next_snapshot_and_denies_stale_or_wrong_role(self) -> None:
        definition, snapshot, human_task_id = waiting_human_authority()
        self.repository.register_authority(
            definition_json=canonical_workflow_json(definition),
            snapshot_json=canonical_workflow_json(snapshot),
            actor=RESEARCHER,
        )

        waiting = self.repository.task_center(limit=20)[0]
        self.assertEqual("waiting-human", waiting.state)
        self.assertFalse(waiting.active_compute)
        self.assertEqual("1.0.0", waiting.definition_version)
        self.assertEqual(("approved", "rejected"), waiting.human_tasks[0].allowed_dispositions)

        with self.assertRaises(WorkflowQueueConflict):
            self.repository.complete_human_task(
                human_task_id,
                expected_snapshot_revision=1,
                expected_history_sequence=waiting.revision,
                decision_id=new_uuid_v7(timestamp_ms=1_788_091_320_000),
                disposition="approved",
                actor=WorkflowActor(SYSTEM.actor_id, "human", "workflow-coordinator"),
                now="2026-08-30T12:02:00.000Z",
            )

        with self.assertRaises(WorkflowQueueConflict):
            self.repository.complete_human_task(
                human_task_id,
                expected_snapshot_revision=1,
                expected_history_sequence=waiting.revision - 1,
                decision_id=new_uuid_v7(timestamp_ms=1_788_091_320_050),
                disposition="approved",
                actor=RESEARCHER,
                now="2026-08-30T12:02:00.050Z",
            )

        decision_id = new_uuid_v7(timestamp_ms=1_788_091_320_100)
        resumed = self.repository.complete_human_task(
            human_task_id,
            expected_snapshot_revision=1,
            expected_history_sequence=waiting.revision,
            decision_id=decision_id,
            disposition="approved",
            actor=RESEARCHER,
            now="2026-08-30T12:02:00.100Z",
        )
        replay = self.repository.complete_human_task(
            human_task_id,
            expected_snapshot_revision=1,
            expected_history_sequence=waiting.revision,
            decision_id=decision_id,
            disposition="approved",
            actor=RESEARCHER,
            now="2026-08-30T12:02:00.100Z",
        )
        self.assertEqual(2, resumed.snapshot_revision)
        self.assertEqual("succeeded", resumed.state)
        self.assertEqual(resumed, replay)
        definition_reference = cast(dict[str, object], snapshot["definition"])
        self.assertEqual(definition_reference["definitionRevisionId"], resumed.definition_revision_id)

        reopened = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        persisted = reopened.task_center(limit=20)[0]
        self.assertEqual(2, persisted.snapshot_revision)
        self.assertEqual(decision_id, persisted.human_tasks[0].decision_id)

    def test_human_consequences_skip_end_or_resume_the_exact_graph(self) -> None:
        definition, snapshot, human_task_id = waiting_human_with_downstream_activity()
        downstream_job_id = str(snapshot["jobs"][-1]["jobId"])
        self.repository.register_authority(
            definition_json=canonical_workflow_json(definition),
            snapshot_json=canonical_workflow_json(snapshot),
            actor=RESEARCHER,
        )
        waiting = self.repository.task_center(limit=20)[0]
        decision_id = new_uuid_v7(timestamp_ms=1_788_091_321_000)
        resumed = self.repository.complete_human_task(
            human_task_id,
            expected_snapshot_revision=waiting.snapshot_revision,
            expected_history_sequence=waiting.revision,
            decision_id=decision_id,
            disposition="approved",
            actor=RESEARCHER,
            now="2026-08-30T12:02:01.000Z",
        )
        replay = self.repository.complete_human_task(
            human_task_id,
            expected_snapshot_revision=waiting.snapshot_revision,
            expected_history_sequence=waiting.revision,
            decision_id=decision_id,
            disposition="approved",
            actor=RESEARCHER,
            now="2026-08-30T12:02:01.000Z",
        )
        self.assertEqual("queued", resumed.state)
        self.assertEqual("succeeded", next(step.state for step in resumed.steps if step.step_key == "review-source"))
        self.assertEqual("runnable", next(step.state for step in resumed.steps if step.step_key == "index-source"))
        self.assertEqual((downstream_job_id,), tuple(job.job_id for job in resumed.jobs))
        self.assertEqual(resumed, replay)
        reopened = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        restarted = reopened.task_center(limit=20)[0]
        self.assertEqual(resumed.definition_revision_id, restarted.definition_revision_id)
        self.assertEqual("runnable", next(step.state for step in restarted.steps if step.step_key == "index-source"))
        self.assertEqual((downstream_job_id,), tuple(job.job_id for job in restarted.jobs))
        claim = reopened.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:01.100Z",
            lease_duration_ms=30_000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(downstream_job_id, claim.job_id)

        other_root = Path(self.temporary.name).resolve() / "skip-project"
        (other_root / "state").mkdir(parents=True)
        initialize_database(
            other_root / "state" / "project.sqlite3", project_id=PROJECT_ID, project_created_at=CREATED_AT
        )
        skip_repository = sqlite_workflow_queue_repository(other_root, PROJECT_ID)
        skip_definition, skip_snapshot, skip_task_id = waiting_human_authority()
        skip_definition["steps"][1]["humanTask"].update(
            allowedDispositions=["not-applicable"],
            consequencesByDisposition={"not-applicable": "skip-step"},
        )
        skip_snapshot["definition"]["contentHash"] = workflow_record_sha256(skip_definition)
        skip_repository.register_authority(
            definition_json=canonical_workflow_json(skip_definition),
            snapshot_json=canonical_workflow_json(skip_snapshot),
            actor=RESEARCHER,
        )
        skip_waiting = skip_repository.task_center(limit=20)[0]
        skipped = skip_repository.complete_human_task(
            skip_task_id,
            expected_snapshot_revision=skip_waiting.snapshot_revision,
            expected_history_sequence=skip_waiting.revision,
            decision_id=new_uuid_v7(timestamp_ms=1_788_091_321_100),
            disposition="not-applicable",
            actor=RESEARCHER,
            now="2026-08-30T12:02:01.100Z",
        )
        self.assertEqual("succeeded", skipped.state)
        self.assertEqual("skipped", next(step.state for step in skipped.steps if step.step_key == "review-source"))

        end_root = Path(self.temporary.name).resolve() / "end-project"
        (end_root / "state").mkdir(parents=True)
        initialize_database(
            end_root / "state" / "project.sqlite3", project_id=PROJECT_ID, project_created_at=CREATED_AT
        )
        end_repository = sqlite_workflow_queue_repository(end_root, PROJECT_ID)
        end_definition, end_snapshot, end_task_id = waiting_human_authority()
        end_repository.register_authority(
            definition_json=canonical_workflow_json(end_definition),
            snapshot_json=canonical_workflow_json(end_snapshot),
            actor=RESEARCHER,
        )
        end_waiting = end_repository.task_center(limit=20)[0]
        ended = end_repository.complete_human_task(
            end_task_id,
            expected_snapshot_revision=end_waiting.snapshot_revision,
            expected_history_sequence=end_waiting.revision,
            decision_id=new_uuid_v7(timestamp_ms=1_788_091_321_200),
            disposition="rejected",
            actor=RESEARCHER,
            now="2026-08-30T12:02:01.200Z",
        )
        self.assertEqual("failed", ended.state)
        self.assertEqual("failed", next(step.state for step in ended.steps if step.step_key == "review-source"))
        self.assertEqual(
            "failed",
            sqlite_workflow_queue_repository(end_root, PROJECT_ID).task_center(limit=20)[0].state,
        )

    def test_human_resume_rolls_back_authority_when_queue_admission_fails(self) -> None:
        definition, snapshot, human_task_id = waiting_human_with_downstream_activity()
        self.repository.register_authority(
            definition_json=canonical_workflow_json(definition),
            snapshot_json=canonical_workflow_json(snapshot),
            actor=RESEARCHER,
        )
        waiting = self.repository.task_center(limit=20)[0]

        with (
            patch.object(
                type(self.repository),
                "_enqueue_submission",
                side_effect=WorkflowQueueConflict("injected queue admission failure"),
            ),
            self.assertRaises(WorkflowQueueConflict),
        ):
            self.repository.complete_human_task(
                human_task_id,
                expected_snapshot_revision=waiting.snapshot_revision,
                expected_history_sequence=waiting.revision,
                decision_id=new_uuid_v7(timestamp_ms=1_788_091_321_300),
                disposition="approved",
                actor=RESEARCHER,
                now="2026-08-30T12:02:01.300Z",
            )

        reopened = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        unchanged = reopened.task_center(limit=20)[0]
        self.assertEqual(waiting.snapshot_revision, unchanged.snapshot_revision)
        self.assertEqual(waiting.revision, unchanged.revision)
        self.assertEqual("waiting-human", unchanged.state)
        self.assertEqual((), unchanged.jobs)
        self.assertIsNone(unchanged.human_tasks[0].decision_id)

    def test_failed_retry_is_a_new_idempotent_continuation_bound_to_exact_definition(self) -> None:
        job = self.enqueue()
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        self.repository.fail(claim, now="2026-08-30T12:02:00.200Z", error_code="invalid-input")
        failed = self.repository.task_center(limit=20)[0]

        with self.assertRaises(WorkflowQueueConflict):
            self.repository.retry_as_continuation(
                job.job_id,
                expected_snapshot_revision=failed.snapshot_revision + 1,
                expected_history_sequence=failed.revision,
                idempotency_key="0" * 32,
                actor=RESEARCHER,
                now="2026-08-30T12:02:00.250Z",
            )

        continued = self.repository.retry_as_continuation(
            job.job_id,
            expected_snapshot_revision=failed.snapshot_revision,
            expected_history_sequence=failed.revision,
            idempotency_key="1" * 32,
            actor=RESEARCHER,
            now="2026-08-30T12:02:00.300Z",
        )
        replay = self.repository.retry_as_continuation(
            job.job_id,
            expected_snapshot_revision=failed.snapshot_revision,
            expected_history_sequence=failed.revision,
            idempotency_key="1" * 32,
            actor=RESEARCHER,
            now="2026-08-30T12:02:00.400Z",
        )
        self.assertNotEqual(failed.workflow_run_id, continued.workflow_run_id)
        self.assertEqual(failed.definition_revision_id, continued.definition_revision_id)
        self.assertEqual(failed.workflow_run_id, continued.continuation_from_workflow_run_id)
        self.assertEqual(job.job_id, continued.continuation_from_job_id)
        self.assertEqual("queued", continued.state)
        self.assertEqual(continued.workflow_run_id, replay.workflow_run_id)
        self.assertEqual(2, len(self.repository.task_center(limit=20)))
        reopened = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        persisted = next(
            item for item in reopened.task_center(limit=20) if item.workflow_run_id == continued.workflow_run_id
        )
        self.assertEqual(failed.workflow_run_id, persisted.continuation_from_workflow_run_id)
        self.assertEqual(job.job_id, persisted.continuation_from_job_id)

        with self.assertRaises(WorkflowQueueConflict):
            self.repository.retry_as_continuation(
                job.job_id,
                expected_snapshot_revision=failed.snapshot_revision,
                expected_history_sequence=failed.revision - 1,
                idempotency_key="2" * 32,
                actor=RESEARCHER,
                now="2026-08-30T12:02:00.500Z",
            )


if __name__ == "__main__":
    unittest.main()
