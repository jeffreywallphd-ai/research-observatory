from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import re
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.repositories import AggregateRevisionDraft, AtomicRepositoryEvent
from research_observatory_core.ports.workflow_executor import (
    WorkflowActor,
    WorkflowLeaseRejected,
    WorkflowOutputReference,
    WorkflowQueueConflict,
    WorkflowQueueProblem,
)
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_workflow_queue_repository,
)
from research_observatory_core.storage import (
    development_plaintext_database_fixture,
    initialize_database,
    open_canonical_database,
)
from research_observatory_core.workflow_contracts import (
    workflow_record_sha256,
    workflow_snapshot_errors,
    workflow_transition_allowed,
)
from research_observatory_core.workflow_executor import (
    LocalWorkerSupervisor,
    WorkflowActivityError,
    prepare_workflow_job,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "packages" / "contracts" / "workflow" / "fixtures"
PROJECT_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d060"
CREATED_AT = "2026-08-30T12:01:00.000Z"
WORKER_A = "018f47a2-4d6b-7f78-9f2e-7fb76c86d040"
WORKER_B = "018f47a2-4d6b-7f78-9f2e-7fb76c86d043"
SYSTEM = WorkflowActor(
    actor_id="018f47a2-4d6b-7f78-9f2e-7fb76c86d042",
    actor_type="system",
    role="workflow-coordinator",
)


def _canonical_artifact(project_root: Path, index: int, *, actor_id: str = WORKER_A) -> WorkflowOutputReference:
    database = project_root / "state" / "project.sqlite3"
    aggregate_id = new_uuid_v7(timestamp_ms=1_788_091_320_500 + index * 10)
    revision_id = new_uuid_v7(timestamp_ms=1_788_091_320_501 + index * 10)
    factory = create_sqlite_unit_of_work_factory(database, PROJECT_ID)
    with factory() as unit:
        revision = unit.aggregates.append(
            AggregateRevisionDraft(
                revision_id=revision_id,
                aggregate_id=aggregate_id,
                aggregate_kind="evidence",
                created_at=CREATED_AT,
                modified_at=f"2026-08-30T12:{10 + index // 60:02d}:{index % 60:02d}.000Z",
                display_label_observed=f"Workflow output {index}",
                display_label_normalized=None,
                knowledge_status="observed",
                rights_status="unknown",
            ),
            AtomicRepositoryEvent(
                event_id=new_uuid_v7(timestamp_ms=1_788_091_320_502 + index * 10),
                outbox_id=new_uuid_v7(timestamp_ms=1_788_091_320_503 + index * 10),
                event_type="evidence.created",
                occurred_at=f"2026-08-30T12:{10 + index // 60:02d}:{index % 60:02d}.000Z",
                available_at=f"2026-08-30T12:{10 + index // 60:02d}:{index % 60:02d}.000Z",
                trace_id=f"{index + 1:032x}",
                actor_type="worker",
                actor_id=actor_id,
                idempotency_key=f"workflow-output-candidate-{index}",
            ),
            expected_revision=None,
        )
        unit.commit()
    connection = open_canonical_database(database, expected_project_id=PROJECT_ID)
    try:
        content_hash = str(
            connection.execute(
                "SELECT content_hash FROM provenance_ledger_entities "
                "WHERE project_id=? AND revision_id=? AND direction='output'",
                (PROJECT_ID, revision.revision_id),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    return WorkflowOutputReference(
        artifact_id=revision.aggregate_id,
        revision_id=revision.revision_id,
        content_hash=content_hash,
        media_type="application/json",
        provenance_entity_id=revision.aggregate_id,
    )


def _claim_checkpoint_and_exit(project_root: str, sender: object) -> None:
    """Act as a worker process that disappears without releasing its durable lease."""

    protection = development_plaintext_database_fixture()
    protection.__enter__()
    repository = sqlite_workflow_queue_repository(Path(project_root), PROJECT_ID)
    claim = repository.claim_next(
        worker_id=WORKER_A,
        concurrency_classes=("document",),
        now="2026-08-30T12:02:00.000Z",
        lease_duration_ms=1_000,
    )
    assert claim is not None
    repository.start(claim, now="2026-08-30T12:02:00.100Z")
    checkpoint_id = new_uuid_v7(timestamp_ms=1_788_091_320_200)
    artifact = _canonical_artifact(Path(project_root), 20)
    repository.stage_artifact(
        claim,
        artifact=artifact,
        role="checkpoint",
        now="2026-08-30T12:02:00.150Z",
    )
    repository.checkpoint(
        claim,
        checkpoint_id=checkpoint_id,
        state_hash=artifact.content_hash,
        payload_artifact_id=artifact.artifact_id,
        now="2026-08-30T12:02:00.200Z",
        progress={"kind": "quantified", "unit": "records", "completedUnits": 25, "totalUnits": 100},
    )
    sender.send((claim, checkpoint_id))  # type: ignore[attr-defined]
    os._exit(0)


def runnable_contracts(*, identity_variant: bool = False) -> tuple[dict[str, object], dict[str, object], str]:
    definition = json.loads((FIXTURES / "valid-workflow-definition.v1.json").read_text(encoding="utf-8"))
    snapshot = json.loads((FIXTURES / "valid-local-workflow-snapshot.v1.json").read_text(encoding="utf-8"))
    definition["steps"][1].update(kind="activity", activityType="human-review", humanTask=None)
    snapshot["definition"]["contentHash"] = workflow_record_sha256(definition)
    snapshot["state"] = "accepted"
    snapshot["progress"] = {"kind": "quantified", "unit": "steps", "completedUnits": 0, "totalUnits": 2}
    snapshot["updatedAt"] = "2026-08-30T12:01:06.000Z"
    snapshot["sequence"] = 6
    snapshot["stepRuns"][0].update(
        state="runnable",
        sequence=4,
        progress={"kind": "quantified", "unit": "records", "completedUnits": 0, "totalUnits": 100},
        outputArtifactIds=[],
    )
    snapshot["stepRuns"][1].update(
        state="pending",
        sequence=3,
        progress={"kind": "quantified", "unit": "decisions", "completedUnits": 0, "totalUnits": 1},
        humanTaskIds=[],
        inputArtifactIds=[],
    )
    snapshot["jobs"] = [snapshot["jobs"][0]]
    job = snapshot["jobs"][0]
    job.update(
        state="runnable",
        sequence=6,
        attemptIds=[],
        currentAttemptId=None,
        outputArtifactIds=[],
        cancellation={"requestedAt": None, "reasonCode": None, "interruptionKind": None},
    )
    snapshot["attempts"] = []
    snapshot["checkpoints"] = []
    snapshot["artifacts"] = []
    snapshot["humanTasks"] = []
    snapshot["history"] = snapshot["history"][:6]
    if identity_variant:
        document = json.dumps({"definition": definition, "snapshot": snapshot})
        protected = {PROJECT_ID, SYSTEM.actor_id}
        identifiers = set(
            re.findall(
                r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                document,
            )
        )
        for value in sorted(identifiers):
            if value not in protected:
                document = document.replace(value, new_uuid_v7())
        remapped = json.loads(document)
        definition = remapped["definition"]
        snapshot = remapped["snapshot"]
        snapshot["definition"]["contentHash"] = workflow_record_sha256(definition)
        job = snapshot["jobs"][0]
        job["idempotencyKey"] = "sha256:" + "c" * 64
    assert workflow_snapshot_errors(definition, snapshot) == ()
    return definition, snapshot, str(job["jobId"])


class LocalWorkflowExecutorTests(unittest.TestCase):
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

    def submission(self, *, priority: int = 0, identity_variant: bool = False):
        definition, snapshot, job_id = runnable_contracts(identity_variant=identity_variant)
        return prepare_workflow_job(
            definition,
            snapshot,
            job_id=job_id,
            concurrency_class="document",
            priority=priority,
            available_at="2026-08-30T12:02:00.000Z",
        )

    def canonical_output(self, index: int) -> WorkflowOutputReference:
        return _canonical_artifact(self.root, index)

    def test_exact_t01_authority_persists_and_reopens_with_runnable_projection(self) -> None:
        submission = self.submission()

        queued = self.repository.enqueue(submission, actor=SYSTEM)
        reopened = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        authority = reopened.authority(queued.job_id)

        self.assertEqual("runnable", reopened.get(queued.job_id).state)
        self.assertEqual(json.loads(submission.definition_json), json.loads(authority.definition_json))
        self.assertEqual(json.loads(submission.snapshot_json), json.loads(authority.snapshot_json))

    def test_two_concurrent_claimers_receive_one_fenced_attempt(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        self.assertIsNone(
            self.repository.claim_next(
                worker_id=new_uuid_v7(timestamp_ms=1_788_091_320_000),
                concurrency_classes=("ai",),
                now="2026-08-30T12:02:00.000Z",
                lease_duration_ms=30_000,
            )
        )
        barrier = threading.Barrier(2)

        def claim(worker_id: str):
            repository = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
            barrier.wait(timeout=2)
            return repository.claim_next(
                worker_id=worker_id,
                concurrency_classes=("document",),
                now="2026-08-30T12:02:00.000Z",
                lease_duration_ms=30_000,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = tuple(pool.map(claim, (WORKER_A, WORKER_B)))

        accepted = [claim for claim in claims if claim is not None]
        self.assertEqual(1, len(accepted))
        self.assertEqual(job.job_id, accepted[0].job_id)
        self.assertEqual(1, accepted[0].attempt_number)
        self.assertEqual(1, accepted[0].lease_generation)

    def test_expired_worker_is_fenced_and_recovery_commits_one_output(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        first = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=1_000,
        )
        assert first is not None
        self.repository.start(first, now="2026-08-30T12:02:00.100Z")

        recovered = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        self.assertEqual(1, recovered.recover_expired(now="2026-08-30T12:02:01.001Z", actor=SYSTEM))
        second = recovered.claim_next(
            worker_id=WORKER_B,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:01.001Z",
            lease_duration_ms=30_000,
        )
        assert second is not None
        recovered.start(second, now="2026-08-30T12:02:01.100Z")
        output = self.canonical_output(1)
        recovered.stage_artifact(
            second,
            artifact=output,
            role="output",
            now="2026-08-30T12:02:01.150Z",
        )
        receipt = recovered.complete(second, now="2026-08-30T12:02:01.200Z", outputs=(output,))
        replay = recovered.complete(second, now="2026-08-30T12:02:01.200Z", outputs=(output,))

        self.assertEqual(receipt.output_record_sha256, replay.output_record_sha256)
        self.assertTrue(replay.replayed)
        self.assertEqual("succeeded", recovered.get(job.job_id).state)
        with self.assertRaises(WorkflowLeaseRejected):
            self.repository.heartbeat(
                first,
                now="2026-08-30T12:02:01.300Z",
                lease_duration_ms=30_000,
                progress={"kind": "quantified", "unit": "records", "completedUnits": 10, "totalUnits": 100},
            )
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM workflow_committed_outputs").fetchone()[0])
            self.assertEqual(
                1,
                connection.execute(
                    "SELECT COUNT(*) FROM provenance_events "
                    "WHERE event_type='org.research-observatory.workflow.job-succeeded.v1'"
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                connection.execute(
                    "SELECT COUNT(*) FROM outbox_events "
                    "WHERE event_type='org.research-observatory.workflow.job-succeeded.v1'"
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                connection.execute(
                    "SELECT COUNT(*) FROM provenance_ledger_events "
                    "WHERE event_type='org.research-observatory.workflow.job-succeeded.v1'"
                ).fetchone()[0],
            )
            self.assertEqual(
                (output.artifact_id, output.revision_id, output.content_hash),
                tuple(
                    connection.execute(
                        "SELECT entity_id, revision_id, content_hash FROM provenance_ledger_entities "
                        "WHERE event_id=(SELECT provenance_event_id FROM workflow_committed_outputs) "
                        "AND direction='output'"
                    ).fetchone()
                ),
            )
            required_event_fields = {
                "eventId",
                "sequence",
                "entityType",
                "entityId",
                "fromState",
                "toState",
                "occurredAt",
                "actor",
                "reasonCode",
                "progress",
                "decisionId",
                "checkpointId",
                "interruptionKind",
            }
            self.assertTrue(
                all(
                    set(json.loads(str(row[0]))) == required_event_fields
                    for row in connection.execute("SELECT event_json FROM workflow_history_events")
                )
            )
        finally:
            connection.close()
        with self.assertRaises(WorkflowLeaseRejected):
            recovered.complete(
                replace(second, lease_token="forged-token"),
                now="2026-08-30T12:02:01.200Z",
                outputs=(output,),
            )

    def test_completion_rejects_unpersisted_output_and_rolls_back_ambiguous_commit(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        nonexistent = WorkflowOutputReference(
            artifact_id=new_uuid_v7(timestamp_ms=1_788_091_320_400),
            revision_id=new_uuid_v7(timestamp_ms=1_788_091_320_401),
            content_hash="sha256:" + "e" * 64,
            media_type="application/json",
            provenance_entity_id=None,
        )
        with self.assertRaises(WorkflowQueueConflict):
            self.repository.complete(claim, now="2026-08-30T12:02:00.200Z", outputs=(nonexistent,))

        output = self.canonical_output(2)
        extra_output = self.canonical_output(3)
        staged = self.repository.stage_artifact(
            claim,
            artifact=output,
            role="output",
            now="2026-08-30T12:02:00.250Z",
        )
        self.assertEqual("retained-incomplete", staged.disposition)
        self.repository.stage_artifact(
            claim,
            artifact=extra_output,
            role="output",
            now="2026-08-30T12:02:00.260Z",
        )
        with (
            patch(
                "research_observatory_core.repositories._record_provenance",
                side_effect=ValueError("injected completion boundary failure"),
            ),
            self.assertRaises(WorkflowQueueProblem),
        ):
            self.repository.complete(claim, now="2026-08-30T12:02:00.300Z", outputs=(output,))

        self.assertEqual("running", self.repository.get(job.job_id).state)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM workflow_committed_outputs").fetchone()[0])
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM provenance_ledger_events "
                    "WHERE event_type='org.research-observatory.workflow.job-succeeded.v1'"
                ).fetchone()[0],
            )
        finally:
            connection.close()

        receipt = self.repository.complete(claim, now="2026-08-30T12:02:00.400Z", outputs=(output,))
        self.assertFalse(receipt.replayed)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(
                "committed",
                connection.execute(
                    "SELECT disposition FROM workflow_attempt_artifacts WHERE attempt_id=? AND artifact_id=?",
                    (claim.attempt_id, output.artifact_id),
                ).fetchone()[0],
            )
            self.assertEqual(
                "retained-incomplete",
                connection.execute(
                    "SELECT disposition FROM workflow_attempt_artifacts WHERE attempt_id=? AND artifact_id=?",
                    (claim.attempt_id, extra_output.artifact_id),
                ).fetchone()[0],
            )
        finally:
            connection.close()

    def test_cancel_wins_before_completion_and_late_output_is_denied(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        self.repository.request_cancellation(
            job.job_id,
            actor=SYSTEM,
            now="2026-08-30T12:02:00.200Z",
            reason_code="user-requested",
            interruption_kind="user-cancel",
        )
        self.repository.cancel(claim, now="2026-08-30T12:02:00.300Z", reason_code="safe-point")
        output = WorkflowOutputReference(
            artifact_id=new_uuid_v7(timestamp_ms=1_788_091_320_400),
            revision_id=new_uuid_v7(timestamp_ms=1_788_091_320_401),
            content_hash="sha256:" + "e" * 64,
            media_type="application/json",
            provenance_entity_id=None,
        )

        with self.assertRaises(WorkflowQueueConflict):
            self.repository.complete(claim, now="2026-08-30T12:02:00.400Z", outputs=(output,))
        self.assertEqual("cancelled", self.repository.get(job.job_id).state)

    def test_security_lock_recovery_cancels_without_ordinary_restart(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=1_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        self.repository.request_cancellation(
            job.job_id,
            actor=SYSTEM,
            now="2026-08-30T12:02:00.200Z",
            reason_code="application-locked",
            interruption_kind="security-lock",
        )

        self.assertEqual(1, self.repository.recover_expired(now="2026-08-30T12:02:01.001Z", actor=SYSTEM))
        recovered = self.repository.get(job.job_id)
        self.assertEqual("cancelled", recovered.state)
        self.assertEqual("security-lock", recovered.interruption_kind)
        self.assertIsNone(
            self.repository.claim_next(
                worker_id=WORKER_B,
                concurrency_classes=("document",),
                now="2026-08-30T12:02:01.001Z",
                lease_duration_ms=30_000,
            )
        )
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            interruptions = tuple(
                json.loads(str(row[0]))["interruptionKind"]
                for row in connection.execute(
                    "SELECT event_json FROM workflow_history_events WHERE sequence > 6 ORDER BY sequence"
                )
            )
            self.assertNotIn("ordinary-restart", interruptions)
            self.assertEqual(
                (None, None, None, None, "security-lock", "security-lock", "security-lock"),
                interruptions,
            )
        finally:
            connection.close()

    def test_queue_writes_do_not_block_existing_interactive_reader_snapshot(self) -> None:
        self.repository.enqueue(self.submission(), actor=SYSTEM)
        reader = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            reader.execute("BEGIN")
            self.assertEqual(1, reader.execute("SELECT COUNT(*) FROM workflow_queue_jobs").fetchone()[0])
            claim = self.repository.claim_next(
                worker_id=WORKER_A,
                concurrency_classes=("document",),
                now="2026-08-30T12:02:00.000Z",
                lease_duration_ms=30_000,
            )
            self.assertIsNotNone(claim)
            self.assertEqual(1, reader.execute("SELECT COUNT(*) FROM workflow_queue_jobs").fetchone()[0])
            reader.execute("ROLLBACK")
            self.assertEqual("claimed", reader.execute("SELECT state FROM workflow_queue_jobs").fetchone()[0])
        finally:
            if reader.in_transaction:
                reader.execute("ROLLBACK")
            reader.close()

    def test_cancellation_poll_is_read_only_during_an_unrelated_writer_transaction(self) -> None:
        self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        writer = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            writer.execute("BEGIN IMMEDIATE")
            self.assertFalse(self.repository.cancellation_requested(claim, now="2026-08-30T12:02:00.200Z"))
        finally:
            if writer.in_transaction:
                writer.execute("ROLLBACK")
            writer.close()

    def test_recovery_is_bounded_and_does_not_block_an_existing_reader_snapshot(self) -> None:
        submissions = (self.submission(), self.submission(identity_variant=True))
        for submission in submissions:
            self.repository.enqueue(submission, actor=SYSTEM)
        for worker_id in (WORKER_A, WORKER_B):
            claim = self.repository.claim_next(
                worker_id=worker_id,
                concurrency_classes=("document",),
                now="2026-08-30T12:02:00.000Z",
                lease_duration_ms=1_000,
            )
            assert claim is not None
            self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        reader = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            reader.execute("BEGIN")
            self.assertEqual(2, reader.execute("SELECT COUNT(*) FROM workflow_queue_jobs").fetchone()[0])
            self.assertEqual(
                1,
                self.repository.recover_expired(
                    now="2026-08-30T12:02:01.001Z",
                    actor=SYSTEM,
                    limit=1,
                ),
            )
            self.assertEqual(2, reader.execute("SELECT COUNT(*) FROM workflow_queue_jobs").fetchone()[0])
        finally:
            if reader.in_transaction:
                reader.execute("ROLLBACK")
            reader.close()
        states = tuple(sorted(self.repository.get(item.job_id).state for item in submissions))
        self.assertEqual(("retry-scheduled", "running"), states)
        self.assertEqual(
            1,
            self.repository.recover_expired(
                now="2026-08-30T12:02:01.001Z",
                actor=SYSTEM,
                limit=1,
            ),
        )

    def test_latest_checkpoint_uses_global_history_order_across_attempts(self) -> None:
        self.repository.enqueue(self.submission(), actor=SYSTEM)
        first = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert first is not None
        with self.assertRaises(WorkflowLeaseRejected):
            self.repository.heartbeat(
                first,
                now="2026-08-30T12:02:00.050Z",
                lease_duration_ms=30_000,
                progress={"kind": "quantified", "unit": "records", "completedUnits": 0, "totalUnits": 100},
            )
        self.repository.start(first, now="2026-08-30T12:02:00.100Z")
        shared_time = "2026-08-30T12:02:00.500Z"
        first_checkpoint = self.canonical_output(30)
        self.repository.stage_artifact(
            first, artifact=first_checkpoint, role="checkpoint", now="2026-08-30T12:02:00.200Z"
        )
        self.repository.checkpoint(
            first,
            checkpoint_id=new_uuid_v7(timestamp_ms=1_788_091_320_500),
            state_hash=first_checkpoint.content_hash,
            payload_artifact_id=first_checkpoint.artifact_id,
            now=shared_time,
            progress={"kind": "quantified", "unit": "records", "completedUnits": 1, "totalUnits": 100},
        )
        first_latest_artifact = self.canonical_output(31)
        self.repository.stage_artifact(
            first, artifact=first_latest_artifact, role="checkpoint", now="2026-08-30T12:02:00.300Z"
        )
        first_latest = self.repository.checkpoint(
            first,
            checkpoint_id=new_uuid_v7(timestamp_ms=1_788_091_320_502),
            state_hash=first_latest_artifact.content_hash,
            payload_artifact_id=first_latest_artifact.artifact_id,
            now=shared_time,
            progress={"kind": "quantified", "unit": "records", "completedUnits": 2, "totalUnits": 100},
        )
        self.repository.fail(first, now="2026-08-30T12:02:00.600Z", error_code="dependency-unavailable")
        second = self.repository.claim_next(
            worker_id=WORKER_B,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:03.000Z",
            lease_duration_ms=30_000,
        )
        assert second is not None
        self.repository.start(second, now="2026-08-30T12:02:03.100Z")
        second_checkpoint = self.canonical_output(32)
        self.repository.stage_artifact(
            second, artifact=second_checkpoint, role="checkpoint", now="2026-08-30T12:02:03.150Z"
        )
        second_latest = self.repository.checkpoint(
            second,
            checkpoint_id=new_uuid_v7(timestamp_ms=1_788_091_320_504),
            state_hash=second_checkpoint.content_hash,
            payload_artifact_id=second_checkpoint.artifact_id,
            now=shared_time,
            progress={"kind": "quantified", "unit": "records", "completedUnits": 2, "totalUnits": 100},
        )
        self.repository.fail(second, now="2026-08-30T12:02:03.200Z", error_code="dependency-unavailable")
        third = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:08.000Z",
            lease_duration_ms=30_000,
        )
        assert third is not None
        self.assertNotEqual(first_latest.checkpoint_id, second_latest.checkpoint_id)
        self.assertEqual(second_latest, third.latest_checkpoint)

    def test_same_idempotency_key_with_changed_command_is_rejected(self) -> None:
        original = self.submission()
        self.repository.enqueue(original, actor=SYSTEM)
        changed = replace(original, command_fingerprint="sha256:" + "1" * 64)

        with self.assertRaises(WorkflowQueueConflict):
            self.repository.enqueue(changed, actor=SYSTEM)

    def test_lease_secret_is_digest_only_and_modified_capabilities_fail_closed(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            stored = str(
                connection.execute(
                    "SELECT lease_token_sha256 FROM workflow_queue_jobs WHERE job_id=?",
                    (job.job_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()
        self.assertNotEqual(claim.lease_token, stored)
        self.assertEqual(hashlib.sha256(claim.lease_token.encode("ascii")).hexdigest(), stored)

        with self.assertRaises(WorkflowLeaseRejected):
            self.repository.start(replace(claim, lease_token="forged-token"), now="2026-08-30T12:02:00.100Z")
        with self.assertRaises(WorkflowLeaseRejected):
            self.repository.start(replace(claim, worker_id=WORKER_B), now="2026-08-30T12:02:00.100Z")
        self.assertEqual("claimed", self.repository.get(job.job_id).state)

    def test_abrupt_worker_exit_recovers_and_resumes_from_latest_checkpoint(self) -> None:
        self.repository.enqueue(self.submission(), actor=SYSTEM)
        process_context = multiprocessing.get_context("spawn")
        receiver, sender = process_context.Pipe(duplex=False)
        worker = process_context.Process(target=_claim_checkpoint_and_exit, args=(str(self.root), sender))
        worker.start()
        claim, checkpoint_id = receiver.recv()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(0, worker.exitcode)

        observed_checkpoints = []

        def resume_handler(_context, resumed_claim):
            observed_checkpoints.append(resumed_claim.latest_checkpoint)
            checkpoint = resumed_claim.latest_checkpoint
            assert checkpoint is not None
            connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
            try:
                resolved = connection.execute(
                    """
                    SELECT artifact.revision_id, artifact.content_hash, artifact.disposition,
                           revision.aggregate_id
                      FROM workflow_attempt_artifacts AS artifact
                      JOIN aggregate_revisions AS revision
                        ON revision.project_id=artifact.project_id
                       AND revision.revision_id=artifact.revision_id
                     WHERE artifact.attempt_id=? AND artifact.artifact_id=?
                    """,
                    (checkpoint.attempt_id, checkpoint.payload_artifact_id),
                ).fetchone()
            finally:
                connection.close()
            assert resolved is not None
            self.assertEqual(
                (
                    checkpoint.payload.revision_id,
                    checkpoint.state_hash,
                    "committed",
                    checkpoint.payload_artifact_id,
                ),
                tuple(map(str, resolved)),
            )
            raise WorkflowActivityError("dependency-unavailable")

        supervisor = LocalWorkerSupervisor(
            sqlite_workflow_queue_repository(self.root, PROJECT_ID),
            {"source-acquisition": resume_handler},
            concurrency_limits={"document": 1},
            now=lambda: "2026-08-30T12:02:01.001Z",
            recovery_actor=SYSTEM,
            worker_id_factory=lambda: WORKER_B,
            lease_duration_ms=30_000,
        )
        results = supervisor.run_available()
        self.assertEqual(1, len(results))
        self.assertEqual("retry-scheduled", results[0].state)
        latest_checkpoint = observed_checkpoints[0]
        self.assertIsNotNone(latest_checkpoint)
        assert latest_checkpoint is not None
        self.assertEqual(checkpoint_id, latest_checkpoint.checkpoint_id)
        with self.assertRaises(WorkflowLeaseRejected):
            self.repository.start(claim, now="2026-08-30T12:02:01.100Z")

    def test_retry_policy_schedules_only_declared_retryable_failures(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")

        scheduled = self.repository.fail(
            claim,
            now="2026-08-30T12:02:00.200Z",
            error_code="dependency-unavailable",
        )

        self.assertEqual("retry-scheduled", scheduled.state)
        self.assertGreater(scheduled.available_at, "2026-08-30T12:02:01.199Z")
        self.assertIsNone(
            self.repository.claim_next(
                worker_id=WORKER_B,
                concurrency_classes=("document",),
                now="2026-08-30T12:02:01.199Z",
                lease_duration_ms=30_000,
            )
        )
        self.assertEqual(job.job_id, scheduled.job_id)

    def test_progress_authority_rejects_regression_and_definition_drift(self) -> None:
        self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        claim = self.repository.heartbeat(
            claim,
            now="2026-08-30T12:02:00.200Z",
            lease_duration_ms=30_000,
            progress={"kind": "quantified", "unit": "records", "completedUnits": 25, "totalUnits": 100},
        )
        for invalid in (
            {"kind": "quantified", "unit": "records", "completedUnits": 24, "totalUnits": 100},
            {"kind": "quantified", "unit": "pages", "completedUnits": 25, "totalUnits": 100},
            {"kind": "quantified", "unit": "records", "completedUnits": 25, "totalUnits": 101},
        ):
            with self.assertRaises(WorkflowQueueConflict):
                self.repository.heartbeat(
                    claim,
                    now="2026-08-30T12:02:00.300Z",
                    lease_duration_ms=30_000,
                    progress=invalid,
                )
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            progress = json.loads(
                str(
                    connection.execute(
                        "SELECT progress_json FROM workflow_job_attempts WHERE attempt_id=?",
                        (claim.attempt_id,),
                    ).fetchone()[0]
                )
            )
        finally:
            connection.close()
        self.assertEqual(25, progress["completedUnits"])

    def test_runtime_history_uses_only_contract_transitions_and_cancellation_is_idempotent(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        first = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert first is not None
        self.repository.start(first, now="2026-08-30T12:02:00.100Z")
        self.repository.fail(first, now="2026-08-30T12:02:00.200Z", error_code="dependency-unavailable")
        second = self.repository.claim_next(
            worker_id=WORKER_B,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:03.000Z",
            lease_duration_ms=30_000,
        )
        assert second is not None
        self.repository.request_cancellation(
            job.job_id,
            actor=SYSTEM,
            now="2026-08-30T12:02:03.100Z",
            reason_code="user-requested",
            interruption_kind="user-cancel",
        )
        self.repository.request_cancellation(
            job.job_id,
            actor=SYSTEM,
            now="2026-08-30T12:02:03.200Z",
            reason_code="user-requested",
            interruption_kind="user-cancel",
        )
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            rows = connection.execute(
                "SELECT entity_type, from_state, to_state FROM workflow_history_events "
                "WHERE sequence > 6 ORDER BY sequence"
            ).fetchall()
        finally:
            connection.close()
        self.assertTrue(all(workflow_transition_allowed(str(row[0]), row[1], str(row[2])) for row in rows))
        self.assertEqual(1, sum(tuple(row) == ("job", "retry-scheduled", "runnable") for row in rows))
        self.assertEqual(1, sum(tuple(row) == ("job", "claimed", "cancelled") for row in rows))

    def test_checkpoint_requires_a_canonical_artifact_staged_by_the_current_attempt(self) -> None:
        self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        with self.assertRaises(WorkflowQueueConflict):
            self.repository.checkpoint(
                claim,
                checkpoint_id=new_uuid_v7(timestamp_ms=1_788_091_320_200),
                state_hash="sha256:" + "d" * 64,
                payload_artifact_id=new_uuid_v7(timestamp_ms=1_788_091_320_201),
                now="2026-08-30T12:02:00.200Z",
                progress={"kind": "quantified", "unit": "records", "completedUnits": 25, "totalUnits": 100},
            )
        artifact = self.canonical_output(40)
        self.repository.stage_artifact(
            claim,
            artifact=artifact,
            role="checkpoint",
            now="2026-08-30T12:02:00.250Z",
        )
        checkpoint = self.repository.checkpoint(
            claim,
            checkpoint_id=new_uuid_v7(timestamp_ms=1_788_091_320_202),
            state_hash=artifact.content_hash,
            payload_artifact_id=artifact.artifact_id,
            now="2026-08-30T12:02:00.300Z",
            progress={"kind": "quantified", "unit": "records", "completedUnits": 25, "totalUnits": 100},
        )
        self.assertEqual(artifact.artifact_id, checkpoint.payload_artifact_id)

    def test_staged_artifact_has_explicit_disposition_after_retry(self) -> None:
        self.repository.enqueue(self.submission(), actor=SYSTEM)
        claim = self.repository.claim_next(
            worker_id=WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.repository.start(claim, now="2026-08-30T12:02:00.100Z")
        artifact = self.canonical_output(41)
        self.repository.stage_artifact(
            claim,
            artifact=artifact,
            role="diagnostic",
            now="2026-08-30T12:02:00.150Z",
        )
        self.repository.fail(claim, now="2026-08-30T12:02:00.200Z", error_code="dependency-unavailable")
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            disposition = connection.execute(
                "SELECT disposition FROM workflow_attempt_artifacts WHERE attempt_id=? AND artifact_id=?",
                (claim.attempt_id, artifact.artifact_id),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual("retained-incomplete", disposition)

    def test_supervisor_converges_cancellation_at_claim_and_completion_races(self) -> None:
        self.repository.enqueue(self.submission(), actor=SYSTEM)

        class CancelAfterClaim:
            def __init__(self, repository):
                self.repository = repository

            def __getattr__(self, name):
                return getattr(self.repository, name)

            def claim_next(self, **kwargs):
                claim = self.repository.claim_next(**kwargs)
                assert claim is not None
                self.repository.request_cancellation(
                    claim.job_id,
                    actor=SYSTEM,
                    now="2026-08-30T12:02:00.000Z",
                    reason_code="claim-race",
                    interruption_kind="user-cancel",
                )
                return claim

        first = LocalWorkerSupervisor(
            CancelAfterClaim(self.repository),
            {"source-acquisition": lambda _context, _claim: ()},
            concurrency_limits={"document": 1},
            now=lambda: "2026-08-30T12:02:00.000Z",
            recovery_actor=SYSTEM,
            worker_id_factory=lambda: WORKER_A,
        ).run_available()
        self.assertEqual("cancelled", first[0].state)

        second_job = self.repository.enqueue(self.submission(identity_variant=True), actor=SYSTEM)
        artifact = self.canonical_output(42)

        class CancelBeforeComplete:
            def __init__(self, repository):
                self.repository = repository

            def __getattr__(self, name):
                return getattr(self.repository, name)

            def complete(self, claim, **kwargs):
                self.repository.request_cancellation(
                    claim.job_id,
                    actor=SYSTEM,
                    now="2026-08-30T12:02:00.000Z",
                    reason_code="completion-race",
                    interruption_kind="user-cancel",
                )
                return self.repository.complete(claim, **kwargs)

        second = LocalWorkerSupervisor(
            CancelBeforeComplete(self.repository),
            {"source-acquisition": lambda _context, _claim: (artifact,)},
            concurrency_limits={"document": 1},
            now=lambda: "2026-08-30T12:02:00.000Z",
            recovery_actor=SYSTEM,
            worker_id_factory=lambda: WORKER_B,
        ).run_available()
        self.assertEqual("cancelled", second[0].state)
        self.assertEqual("cancelled", self.repository.get(second_job.job_id).state)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            disposition = connection.execute(
                "SELECT disposition FROM workflow_attempt_artifacts WHERE job_id=? AND artifact_id=?",
                (second_job.job_id, artifact.artifact_id),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual("retained-incomplete", disposition)

    def test_supervisor_executes_registered_activity_without_holding_database_lock(self) -> None:
        job = self.repository.enqueue(self.submission(), actor=SYSTEM)
        output = self.canonical_output(3)

        supervisor = LocalWorkerSupervisor(
            self.repository,
            {"source-acquisition": lambda _context, _claim: (output,)},
            concurrency_limits={"document": 1},
            now=lambda: "2026-08-30T12:02:00.000Z",
            recovery_actor=SYSTEM,
            worker_id_factory=lambda: WORKER_A,
        )

        results = supervisor.run_available()

        self.assertEqual(1, len(results))
        self.assertEqual("succeeded", results[0].state)
        self.assertEqual("succeeded", self.repository.get(job.job_id).state)


if __name__ == "__main__":
    unittest.main()
