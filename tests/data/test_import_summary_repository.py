"""Accepted summary publication over real draft, queue and provenance adapters."""

from __future__ import annotations

import sqlite3
import time
import tracemalloc
import unittest
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights, review_record
from research_observatory_core.ingestion.import_summaries import SUMMARY_ACTIVITY, summary_receipt_fingerprint
from research_observatory_core.ports.import_previews import PreviewActor, PreviewProblem
from research_observatory_core.ports.repositories import (
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    MaterialDependency,
)
from research_observatory_core.repositories import create_sqlite_unit_of_work_factory, sqlite_workflow_queue_repository
from research_observatory_core.storage import IMPORT_SUMMARY_DDL
from research_observatory_core.workflow_contracts import workflow_record_sha256
from research_observatory_core.workflow_executor import prepare_workflow_job

from tests.data import test_import_preview_drafts as fixture
from tests.data.test_import_source_chunks import PROJECT_ID
from tests.workflows import test_local_workflow_executor as workers

NOW = "2026-08-30T12:03:00.000Z"
RAW = b"title,doi\nSame,10.99999/a\nSame,10.99999/a\nDifferent,https://doi.org/10.99999/A\nOther,\n"


class ImportSummaryRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportPreviewDraftTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repository = self.fixture.repository
        self.project = self.fixture.fixture.project
        self.queue = sqlite_workflow_queue_repository(self.project, PROJECT_ID)

    def start(self, raw=RAW, *, denied_store=False):
        preview, records = self.fixture.accepted(raw)
        self.fixture.change(preview, 0)
        revision = 1
        if denied_store:
            rights = ImportRights(
                store=ImportPermission(value="denied", basis="researcher-confirmed"),
                inspect=ImportPermission(value="permitted", basis="researcher-confirmed"),
            )
            self.fixture.change(
                preview, 1, decisions=(review_record(records[-1], included=False, fields=(), rights=rights),)
            )
            revision = 2
        definition, snapshot, job = workers.runnable_contracts()
        definition["steps"][0]["activityType"] = SUMMARY_ACTIVITY
        snapshot["definition"]["contentHash"] = workflow_record_sha256(definition)
        snapshot["projectId"] = PROJECT_ID
        self.queue.enqueue(
            prepare_workflow_job(
                definition, snapshot, job_id=job, concurrency_class="document", priority=0, available_at=NOW
            ),
            actor=workers.SYSTEM,
        )
        claim = self.queue.claim_next(
            worker_id=workers.WORKER_A, concurrency_classes=("document",), now=NOW, lease_duration_ms=30000
        )
        self.assertIsNotNone(claim)
        self.queue.start(claim, now=NOW)
        actor = PreviewActor(actor_id=claim.worker_id, trace_id="3" * 32, occurred_at=NOW)
        self.repository().begin_summary(preview, revision=revision, claim=claim, actor=actor)
        return preview, records, claim, actor

    def fill(self, preview, claim, actor, revision=1):
        after = 0
        count = self.repository().draft(preview).record_count
        while after < count:
            rows = self.repository().append_summary_page(
                preview, revision=revision, after=after, claim=claim, actor=actor
            )
            self.assertTrue(rows)
            after = rows[-1].ordinal
        return self.repository().summary_result(preview, claim=claim, actor=actor)

    def receipt(self, preview, claim, actor, actual_result, **changes):
        state, draft = self.repository().read(preview), self.repository().draft(preview)
        binding = dict(
            project_id=PROJECT_ID,
            preview_id=preview,
            job_id=claim.job_id,
            summary_attempt_id=claim.attempt_id,
            parse_attempt_id=draft.attempt_id,
            draft_revision=draft.revision,
            source_sha256=state.source_sha256,
            manifest_sha256=state.manifest_sha256,
            result=actual_result,
        )
        binding.update(changes)
        factory = create_sqlite_unit_of_work_factory(self.project / "state/project.sqlite3", PROJECT_ID)
        with factory() as unit:
            receipt = unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=new_uuid_v7(),
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="workflow",
                    created_at=NOW,
                    modified_at=NOW,
                    display_label_observed="Synthetic draft summary",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                    dependency_coverage="complete",
                    material_dependencies=(
                        MaterialDependency(
                            dependency_id=new_uuid_v7(),
                            dependency_kind="parameter-set",
                            relation_type="direct",
                            revision_id=None,
                            configuration_id="import.draft-summary",
                            configuration_version="1.0.0",
                            fingerprint=summary_receipt_fingerprint(**binding),
                            governing_policy_id="dependency.material.v1",
                            governing_policy_version="1.0.0",
                        ),
                    ),
                ),
                AtomicRepositoryEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type="workflow.created",
                    occurred_at=NOW,
                    available_at=NOW,
                    trace_id=actor.trace_id,
                    actor_type="worker",
                    actor_id=claim.worker_id,
                    idempotency_key="summary-fixture-" + new_uuid_v7(),
                ),
                expected_revision=None,
            )
            unit.commit()
        return receipt.revision_id

    def test_counts_groups_members_and_restart_require_exact_queue_acceptance(self):
        preview, _, claim, actor = self.start()
        self.assertIsNone(self.repository().summary(preview, revision=1))
        with self.assertRaisesRegex(PreviewProblem, "summary-incomplete"):
            self.repository().summary_result(preview, claim=claim, actor=actor)
        result = self.fill(preview, claim, actor)
        counts = result.counts
        self.assertEqual(
            (5, 4, 1, 4, 0, 3),
            (
                counts.source_rows,
                counts.record_rows,
                counts.context_rows,
                counts.included_records,
                counts.excluded_records,
                counts.candidate_records,
            ),
        )
        self.assertEqual(
            (4, 3, 1, 1),
            (counts.coverage.title, counts.coverage.doi, counts.raw_duplicate_groups, counts.doi_duplicate_groups),
        )
        receipt = self.receipt(preview, claim, actor, result)
        output = self.repository().finish_summary(
            preview, claim=claim, result=result, receipt_revision_id=receipt, actor=actor
        )
        self.assertIsNone(self.repository().summary(preview, revision=1))
        self.queue.stage_artifact(claim, artifact=output, role="output", now=NOW)
        self.queue.complete(claim, now=NOW, outputs=(output,))
        summary = self.repository().summary(preview, revision=1)
        self.assertEqual(result, summary.result)
        self.assertEqual(receipt, summary.receipt_revision_id)
        group = self.repository().summary_groups(preview, revision=1, reason="doi", after=None, limit=1)[0]
        self.assertEqual(3, group.member_count)
        self.assertEqual(
            (2, 3),
            self.repository().summary_members(
                preview, revision=1, reason="doi", group_key=group.group_key, after=0, limit=2
            ),
        )
        self.assertEqual(
            (4,),
            self.repository().summary_members(
                preview, revision=1, reason="doi", group_key=group.group_key, after=3, limit=2
            ),
        )
        self.assertEqual(
            (), self.repository().summary_groups(preview, revision=1, reason="doi", after=group.group_key, limit=1)
        )
        self.fixture.change(preview, 1)
        for read in (
            lambda: self.repository().summary(preview, revision=1),
            lambda: self.repository().summary_groups(preview, revision=1, reason="doi", after=None, limit=1),
            lambda: self.repository().summary_members(
                preview, revision=1, reason="doi", group_key=group.group_key, after=0, limit=1
            ),
        ):
            with self.assertRaisesRegex(PreviewProblem, "revision-conflict"):
                read()
        self.assertIsNone(self.repository().summary(preview, revision=2))

    def test_wrong_attempt_draft_and_result_receipts_never_publish(self):
        preview, _, claim, actor = self.start()
        result = self.fill(preview, claim, actor)
        for changes in (
            {"summary_attempt_id": new_uuid_v7()},
            {"draft_revision": 2},
            {"parse_attempt_id": new_uuid_v7()},
            {"result": result.model_copy(update={"rows_sha256": "a" * 64})},
        ):
            with self.subTest(changes=list(changes)):
                receipt = self.receipt(preview, claim, actor, result, **changes)
                with self.assertRaisesRegex(PreviewProblem, "receipt-authority-mismatch"):
                    self.repository().finish_summary(
                        preview, claim=claim, result=result, receipt_revision_id=receipt, actor=actor
                    )
                self.assertIsNone(self.repository().summary(preview, revision=1))
        receipt = self.receipt(preview, claim, actor, result)
        with self.assertRaisesRegex(PreviewProblem, "summary-result-mismatch"):
            self.repository().finish_summary(
                preview,
                claim=claim,
                result=result.model_copy(update={"rows_sha256": "b" * 64}),
                receipt_revision_id=receipt,
                actor=actor,
            )

    def test_all_rows_need_store_and_inspect_even_excluded_records_beyond_first_page(self):
        preview, _, claim, actor = self.start(b"title\n" + b"Synthetic\n" * 105, denied_store=True)
        first = self.repository().append_summary_page(preview, revision=2, after=0, claim=claim, actor=actor)
        self.assertEqual(100, len(first))
        with self.assertRaisesRegex(PreviewProblem, "summary-record-denied"):
            self.repository().append_summary_page(preview, revision=2, after=100, claim=claim, actor=actor)
        with self.assertRaisesRegex(PreviewProblem, "summary-incomplete"):
            self.repository().summary_result(preview, claim=claim, actor=actor)
        self.assertIsNone(self.repository().summary(preview, revision=2))
        with self.repository()._transaction(preview) as connection:
            self.assertEqual(100, connection.execute("SELECT COUNT(*) FROM import_summary_rows").fetchone()[0])

    def test_edit_before_completion_leaves_no_summary_or_groups(self):
        preview, _, claim, actor = self.start()
        result = self.fill(preview, claim, actor)
        receipt = self.receipt(preview, claim, actor, result)
        self.fixture.change(preview, 1)
        with self.assertRaisesRegex(PreviewProblem, "revision-conflict"):
            self.repository().finish_summary(
                preview, claim=claim, result=result, receipt_revision_id=receipt, actor=actor
            )
        with self.repository()._transaction(preview) as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM import_summary_groups").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM import_summary_completions").fetchone()[0])

    def test_different_committed_output_does_not_accept_summary_receipt(self):
        preview, _, claim, actor = self.start()
        result = self.fill(preview, claim, actor)
        self.repository().finish_summary(
            preview,
            claim=claim,
            result=result,
            receipt_revision_id=self.receipt(preview, claim, actor, result),
            actor=actor,
        )
        # The shared helper defaults to another synthetic project identity.
        with patch.object(workers, "PROJECT_ID", PROJECT_ID):
            other = workers._canonical_artifact(self.project, 1)
        self.queue.stage_artifact(claim, artifact=other, role="output", now=NOW)
        self.queue.complete(claim, now=NOW, outputs=(other,))
        with self.assertRaisesRegex(PreviewProblem, "summary-output-mismatch"):
            self.repository().summary(preview, revision=1)

    def test_expired_actor_or_cancelled_claim_cannot_write_or_publish(self):
        preview, _, claim, actor = self.start()
        for changed_claim, changed_actor in (
            (replace(claim, lease_token="wrong"), actor),
            (claim, actor.model_copy(update={"actor_id": new_uuid_v7()})),
            (claim, actor.model_copy(update={"occurred_at": "2026-08-30T12:04:00.000Z"})),
        ):
            with self.assertRaises(PreviewProblem):
                self.repository().append_summary_page(
                    preview, revision=1, after=0, claim=changed_claim, actor=changed_actor
                )
        result = self.fill(preview, claim, actor)
        output = self.repository().finish_summary(
            preview,
            claim=claim,
            result=result,
            receipt_revision_id=self.receipt(preview, claim, actor, result),
            actor=actor,
        )
        self.queue.request_cancellation(
            claim.job_id, actor=workers.SYSTEM, now=NOW, reason_code="user-requested", interruption_kind="user-cancel"
        )
        self.queue.cancel(claim, now=NOW, reason_code="user-requested")
        self.assertIsNone(self.repository().summary(preview, revision=1))
        self.assertIsNotNone(output)

    def test_edit_between_page_projection_and_append_rolls_back(self):
        preview, _, claim, actor = self.start()
        repository = self.repository()
        original = repository.draft_page

        def edited(*args, **kwargs):
            result = original(*args, **kwargs)
            self.fixture.change(preview, 1)
            return result

        with (
            patch.object(repository, "draft_page", side_effect=edited),
            self.assertRaisesRegex(PreviewProblem, "revision-conflict"),
        ):
            repository.append_summary_page(preview, revision=1, after=0, claim=claim, actor=actor)
        with repository._transaction(preview) as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM import_summary_rows").fetchone()[0])

    def test_expired_attempt_restarts_from_zero_and_cannot_publish_old_rows(self):
        preview, _, first, actor = self.start()
        old = self.fill(preview, first, actor)
        self.assertEqual(1, self.queue.recover_expired(now="2026-08-30T12:04:00.000Z", actor=workers.SYSTEM))
        second = self.queue.claim_next(
            worker_id=workers.WORKER_B,
            concurrency_classes=("document",),
            now="2026-08-30T12:04:00.000Z",
            lease_duration_ms=30000,
        )
        self.assertIsNotNone(second)
        self.assertNotEqual(first.attempt_id, second.attempt_id)
        self.queue.start(second, now="2026-08-30T12:04:00.000Z")
        fresh_actor = actor.model_copy(update={"actor_id": second.worker_id, "occurred_at": "2026-08-30T12:04:00.000Z"})
        self.repository().begin_summary(preview, revision=1, claim=second, actor=fresh_actor)
        with self.assertRaisesRegex(PreviewProblem, "summary-incomplete"):
            self.repository().summary_result(preview, claim=second, actor=fresh_actor)
        with self.assertRaises(PreviewProblem):
            self.repository().append_summary_page(preview, revision=1, after=0, claim=first, actor=actor)
        result = self.fill(preview, second, fresh_actor)
        self.assertEqual(old, result)
        output = self.repository().finish_summary(
            preview,
            claim=second,
            result=result,
            receipt_revision_id=self.receipt(preview, second, fresh_actor, result),
            actor=fresh_actor,
        )
        self.queue.stage_artifact(second, artifact=output, role="output", now=fresh_actor.occurred_at)
        self.queue.complete(second, now=fresh_actor.occurred_at, outputs=(output,))
        self.assertEqual(second.attempt_id, self.repository().summary(preview, revision=1).summary_attempt_id)

    def test_empty_import_is_complete_zero_not_a_missing_or_failed_summary(self):
        preview, _, claim, actor = self.start(b"")
        self.assertIsNone(self.repository().summary(preview, revision=1))
        result = self.fill(preview, claim, actor)
        self.assertEqual(0, result.counts.source_rows)
        self.assertEqual(0, result.counts.candidate_records)
        output = self.repository().finish_summary(
            preview,
            claim=claim,
            result=result,
            receipt_revision_id=self.receipt(preview, claim, actor, result),
            actor=actor,
        )
        self.queue.stage_artifact(claim, artifact=output, role="output", now=NOW)
        self.queue.complete(claim, now=NOW, outputs=(output,))
        self.assertEqual(result, self.repository().summary(preview, revision=1).result)

    def test_completion_failure_rolls_back_groups_and_retry_preserves_rows(self):
        preview, _, claim, actor = self.start()
        result = self.fill(preview, claim, actor)
        receipt = self.receipt(preview, claim, actor, result)
        repository = self.repository()
        query = repository._query

        def interrupted(connection, sql, *args, **kwargs):
            if "INSERT INTO import_summary_completions" in sql:
                raise PreviewProblem("synthetic-summary-interruption")
            return query(connection, sql, *args, **kwargs)

        with (
            patch.object(repository, "_query", side_effect=interrupted),
            self.assertRaisesRegex(PreviewProblem, "synthetic-summary-interruption"),
        ):
            repository.finish_summary(preview, claim=claim, result=result, receipt_revision_id=receipt, actor=actor)
        with repository._transaction(preview) as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM import_summary_groups").fetchone()[0])
            self.assertEqual(5, connection.execute("SELECT COUNT(*) FROM import_summary_rows").fetchone()[0])
        repository.finish_summary(preview, claim=claim, result=result, receipt_revision_id=receipt, actor=actor)
        # Persisted completion alone still is not accepted output.
        self.assertIsNone(repository.summary(preview, revision=1))

    def test_100k_row_query_scale_has_linear_groups_and_bounded_python_memory(self):
        # Query-scale fixture only; deliberately no canonical import/queue FKs.
        # Actual end-to-end protected 100k qualification remains separate.
        preview, _, claim, _ = self.start()
        draft = self.repository().draft(preview).model_copy(update={"record_count": 100000})
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("PRAGMA temp_store=MEMORY")
            for statement in IMPORT_SUMMARY_DDL:
                if "CREATE TABLE import_summary_rows " in statement or statement.startswith(
                    ("CREATE INDEX import_summary_raw ", "CREATE INDEX import_summary_doi ")
                ):
                    connection.execute(statement)
            connection.executemany(
                "INSERT INTO import_summary_rows VALUES (?, ?, ?, ?, ?, ?, 'record', 'parsed', 1, 0, 31, ?, ?)",
                (
                    (
                        preview,
                        PROJECT_ID,
                        claim.attempt_id,
                        draft.attempt_id,
                        ordinal,
                        f"{ordinal:064x}",
                        f"{(ordinal - 1) // 2:064x}",
                        "a" * 64,
                    )
                    for ordinal in range(1, 100001)
                ),
            )
            tracemalloc.start()
            started = time.monotonic()
            try:
                result = self.repository()._summary_result(connection, preview, claim.attempt_id, draft)
                elapsed = time.monotonic() - started
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
        self.assertEqual(100000, result.counts.source_rows)
        self.assertEqual(100000, result.counts.candidate_records)
        self.assertEqual(50000, result.counts.raw_duplicate_groups)
        self.assertEqual(1, result.counts.doi_duplicate_groups)
        self.assertLess(peak, 8 * 1024 * 1024)
        print(f"Summary query-only 100k rows: {elapsed:.3f}s; peak Python allocation {peak} bytes", flush=True)
