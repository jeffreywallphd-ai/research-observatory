"""Accepted-output snapshots enumerate history beyond the Task Center window."""

import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.workflow_executor import (
    WorkflowAcceptedCursor,
    WorkflowActor,
    WorkflowQueueProblem,
)
from research_observatory_core.repositories import sqlite_workflow_queue_repository
from research_observatory_core.workflow_contracts import canonical_workflow_json, workflow_record_sha256
from research_observatory_core.workflow_executor import prepare_workflow_job

from tests.workflows import test_local_workflow_executor as fixture_module


class AcceptedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.LocalWorkflowExecutorTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.queue = self.fixture.repository
        self.output = self.fixture.canonical_output(1)

    def accept(self, index, *, continue_failed=False):
        definition, snapshot, job_id = fixture_module.runnable_contracts(identity_variant=True)
        jobs = snapshot["jobs"]
        assert isinstance(jobs, list) and isinstance(jobs[0], dict)
        jobs[0]["idempotencyKey"] = "sha256:" + hashlib.sha256(str(index).encode()).hexdigest()
        submission = prepare_workflow_job(
            definition,
            snapshot,
            job_id=job_id,
            concurrency_class="document",
            priority=0,
            available_at="2026-08-30T12:02:00.000Z",
        )
        self.queue.enqueue(submission, actor=fixture_module.SYSTEM)
        claim = self.queue.claim_next(
            worker_id=fixture_module.WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        self.queue.start(claim, now="2026-08-30T12:02:00.100Z")
        if continue_failed:
            self.queue.fail(claim, now="2026-08-30T12:02:00.150Z", error_code="invalid-input")
            failed = self.queue.task_center(limit=1)[0]
            self.failed_source = failed
            continued = self.queue.retry_as_continuation(
                job_id,
                expected_snapshot_revision=failed.snapshot_revision,
                expected_history_sequence=failed.revision,
                idempotency_key="1" * 32,
                actor=WorkflowActor(new_uuid_v7(), "human", "researcher"),
                now="2026-08-30T12:02:00.200Z",
            )
            self.assertEqual(job_id, continued.continuation_from_job_id)
            claim = self.queue.claim_next(
                worker_id=fixture_module.WORKER_A,
                concurrency_classes=("document",),
                now="2026-08-30T12:02:00.300Z",
                lease_duration_ms=30000,
            )
            self.assertIsNotNone(claim)
            assert claim is not None
            job_id = claim.job_id
            self.queue.start(claim, now="2026-08-30T12:02:00.400Z")
        self.queue.stage_artifact(claim, artifact=self.output, role="output", now="2026-08-30T12:02:00.500Z")
        self.queue.complete(claim, now="2026-08-30T12:02:00.600Z", outputs=(self.output,))
        return job_id

    def test_accepted_continuation_is_included_and_failed_predecessor_is_not(self):
        continued = self.accept(1, continue_failed=True)
        snapshot = self.queue.accepted_snapshot(activity_types=("source-acquisition",))
        page = self.queue.accepted_page(snapshot, after=None, limit=100)
        self.assertEqual((continued,), tuple(item.job_id for item in page))
        self.assertEqual((), self.queue.accepted_page(snapshot, after=page[0].cursor, limit=100))

    def test_exact_acceptance_and_all_continuation_branches_survive_reopen(self):
        continued = self.accept(1, continue_failed=True)
        source = self.failed_source
        sibling = self.queue.retry_as_continuation(
            source.jobs[0].job_id,
            expected_snapshot_revision=source.snapshot_revision,
            expected_history_sequence=source.revision,
            idempotency_key="2" * 32,
            actor=WorkflowActor(new_uuid_v7(), "human", "researcher"),
            now="2026-08-30T12:02:00.700Z",
        )
        reopened = sqlite_workflow_queue_repository(self.fixture.root, fixture_module.PROJECT_ID)
        latest = reopened.latest_continuation(source.jobs[0].job_id)
        assert latest is not None
        self.assertEqual(sibling.jobs[0].job_id, latest.job_id)
        lineage = reopened.continuation_jobs(source.jobs[0].job_id)
        self.assertEqual({source.jobs[0].job_id, continued, sibling.jobs[0].job_id}, {item.job_id for item in lineage})
        self.assertIsNone(reopened.accepted_output(source.jobs[0].job_id))
        self.assertIsNone(reopened.accepted_output(sibling.jobs[0].job_id))
        accepted = reopened.accepted_output(continued)
        assert accepted is not None
        self.assertEqual((self.output,), accepted.outputs)
        snapshot = reopened.accepted_snapshot(activity_types=("source-acquisition",))
        self.assertEqual(accepted.outputs, reopened.accepted_page(snapshot, after=None)[0].outputs)
        with self.assertRaises(WorkflowQueueProblem):
            reopened.accepted_output(new_uuid_v7())

    def test_continuation_cannot_substitute_executor_authority(self):
        continued = self.accept(1, continue_failed=True)
        with closing(sqlite3.connect(self.fixture.database, autocommit=True)) as raw:
            snapshot_id, revision = raw.execute(
                "SELECT snapshot_id,snapshot_revision FROM workflow_queue_jobs WHERE job_id=?", (continued,)
            ).fetchone()
            original, digest = raw.execute(
                "SELECT snapshot_json,record_sha256 FROM workflow_authority_snapshots "
                "WHERE snapshot_id=? AND snapshot_revision=?",
                (snapshot_id, revision),
            ).fetchone()
            value = json.loads(original)
            value["executor"]["profile"] = "server"
            trigger = raw.execute(
                "SELECT sql FROM sqlite_schema WHERE name='workflow_authority_snapshots_no_update'"
            ).fetchone()[0]
            raw.execute("DROP TRIGGER workflow_authority_snapshots_no_update")
            raw.execute(
                "UPDATE workflow_authority_snapshots SET snapshot_json=?,record_sha256=? "
                "WHERE snapshot_id=? AND snapshot_revision=?",
                (canonical_workflow_json(value), workflow_record_sha256(value), snapshot_id, revision),
            )
            raw.execute(trigger)
            self.assertEqual([], raw.execute("PRAGMA foreign_key_check").fetchall())
            try:
                with self.assertRaises(WorkflowQueueProblem):
                    self.queue.continuation_jobs(self.failed_source.jobs[0].job_id)
            finally:
                raw.execute("DROP TRIGGER workflow_authority_snapshots_no_update")
                raw.execute(
                    "UPDATE workflow_authority_snapshots SET snapshot_json=?,record_sha256=? "
                    "WHERE snapshot_id=? AND snapshot_revision=?",
                    (original, digest, snapshot_id, revision),
                )
                raw.execute(trigger)

    def test_snapshot_is_exhaustive_frozen_and_reopens_without_time_or_uuid_order_assumptions(self):
        empty = self.queue.accepted_snapshot(activity_types=("source-acquisition",))
        expected = {self.accept(index) for index in range(101)}
        snapshot = self.queue.accepted_snapshot(activity_types=("source-acquisition",))
        later = self.accept(101)
        self.assertEqual((), self.queue.accepted_page(empty, after=None, limit=10))
        reopened = sqlite_workflow_queue_repository(self.fixture.root, fixture_module.PROJECT_ID)
        found: list[str] = []
        cursor = None
        while page := reopened.accepted_page(snapshot, after=cursor, limit=17):
            self.assertTrue(all(item.outputs == (self.output,) for item in page))
            found.extend(item.job_id for item in page)
            cursor = page[-1].cursor
        self.assertEqual(101, len(found))
        self.assertEqual(expected, set(found))
        self.assertNotIn(later, found)
        latest = reopened.accepted_snapshot(activity_types=("source-acquisition",))
        first = reopened.accepted_page(latest, after=None, limit=100)
        tail = reopened.accepted_page(latest, after=first[-1].cursor, limit=100)
        self.assertEqual(102, len(first) + len(tail))
        self.assertIn(later, {item.job_id for item in tail})
        with self.assertRaises(WorkflowQueueProblem):
            reopened.accepted_page(latest, after=cursor, limit=100)

    def test_substituted_snapshot_project_checkpoint_or_cursor_denies(self):
        self.accept(1)
        snapshot = self.queue.accepted_snapshot(activity_types=("source-acquisition",))
        anchor = snapshot.boundaries[0]
        for bad in (
            replace(snapshot, project_id=new_uuid_v7()),
            replace(snapshot, boundaries=(replace(anchor, chain_sha256="sha256:" + "0" * 64),)),
            replace(snapshot, boundaries=(replace(anchor, checkpoint_id=new_uuid_v7()),)),
        ):
            with self.subTest(snapshot=bad), self.assertRaises(WorkflowQueueProblem):
                self.queue.accepted_page(bad, after=None, limit=10)
        with self.assertRaises(WorkflowQueueProblem):
            self.queue.accepted_page(
                snapshot,
                after=WorkflowAcceptedCursor(snapshot.fingerprint, anchor.segment_key, anchor.sequence + 1),
                limit=10,
            )

    def test_substituted_completion_or_attempt_cannot_disappear_behind_paging(self):
        first, second = self.accept(1), self.accept(2)
        snapshot = self.queue.accepted_snapshot(activity_types=("source-acquisition",))
        with closing(sqlite3.connect(self.fixture.database, autocommit=True)) as raw:
            trigger = raw.execute(
                "SELECT sql FROM sqlite_schema WHERE name='workflow_committed_outputs_no_update'"
            ).fetchone()[0]
            originals = raw.execute(
                "SELECT provenance_event_id,attempt_id FROM workflow_committed_outputs WHERE job_id=?", (second,)
            ).fetchone()
            for index, column in enumerate(("provenance_event_id", "attempt_id")):
                with self.subTest(column=column):
                    raw.execute("DROP TRIGGER workflow_committed_outputs_no_update")
                    raw.execute(
                        "UPDATE workflow_committed_outputs SET "
                        + column
                        + "=(SELECT "
                        + column
                        + " FROM workflow_committed_outputs WHERE job_id=?) WHERE job_id=?",
                        (first, second),
                    )
                    raw.execute(trigger)
                    self.assertEqual([], raw.execute("PRAGMA foreign_key_check").fetchall())
                    with self.assertRaises(WorkflowQueueProblem):
                        cursor = None
                        while page := self.queue.accepted_page(snapshot, after=cursor, limit=1):
                            cursor = page[-1].cursor
                    raw.execute("DROP TRIGGER workflow_committed_outputs_no_update")
                    raw.execute(
                        "UPDATE workflow_committed_outputs SET " + column + "=? WHERE job_id=?",
                        (originals[index], second),
                    )
                    raw.execute(trigger)
