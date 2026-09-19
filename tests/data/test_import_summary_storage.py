"""Relational constraints only; worker acceptance remains a separate boundary."""

from __future__ import annotations

import sqlite3
import unittest

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.repositories import sqlite_workflow_queue_repository
from research_observatory_core.storage import open_canonical_database
from research_observatory_core.workflow_executor import prepare_workflow_job

from tests.data import test_import_preview_drafts as draft_fixture
from tests.data.test_import_source_chunks import PROJECT_ID
from tests.workflows import test_local_workflow_executor as worker_fixture

NOW = "2026-08-30T12:03:00.000Z"


class ImportSummaryStorageTests(unittest.TestCase):
    def test_attempt_source_membership_completeness_and_immutability(self):
        fixture = draft_fixture.ImportPreviewDraftTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        preview, records = fixture.accepted(b"title\nSame\nSame\n")
        draft = fixture.change(preview, 0)
        project = fixture.fixture.project
        queue = sqlite_workflow_queue_repository(project, PROJECT_ID)
        definition, snapshot, job = worker_fixture.runnable_contracts()
        snapshot["projectId"] = PROJECT_ID
        queue.enqueue(
            prepare_workflow_job(
                definition, snapshot, job_id=job, concurrency_class="document", priority=0, available_at=NOW
            ),
            actor=worker_fixture.SYSTEM,
        )
        claim = queue.claim_next(
            worker_id=worker_fixture.WORKER_A, concurrency_classes=("document",), now=NOW, lease_duration_ms=30000
        )
        self.assertIsNotNone(claim)
        connection = open_canonical_database(project / "state/project.sqlite3", expected_project_id=PROJECT_ID)
        try:
            attempt = (preview, PROJECT_ID, claim.attempt_id, job, draft.attempt_id, 1, "draft-summary/1", NOW)
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("INSERT INTO import_summary_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)", attempt)
            queue.start(claim, now=NOW)
            for bad in (
                (preview, PROJECT_ID, new_uuid_v7(), job, draft.attempt_id, 1, "draft-summary/1", NOW),
                (preview, PROJECT_ID, claim.attempt_id, job, draft.attempt_id, 2, "draft-summary/1", NOW),
            ):
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute("INSERT INTO import_summary_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)", bad)
            connection.execute("INSERT INTO import_summary_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)", attempt)

            def row(ordinal, key=None):
                record = records[ordinal - 1]
                included = ordinal > 1
                return (
                    preview,
                    PROJECT_ID,
                    claim.attempt_id,
                    draft.attempt_id,
                    ordinal,
                    key or record.record_key,
                    record.kind,
                    record.status,
                    int(included),
                    0,
                    int(included),
                    record.raw_sha256 if included else None,
                    None,
                )

            insert = "INSERT INTO import_summary_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(insert, row(2))
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(insert, row(1, "f" * 64))
            connection.execute(insert, row(1))
            receipt = connection.execute("SELECT receipt_revision_id FROM import_parse_completions").fetchone()[0]
            # A real aggregate FK is necessary, but is not a summary receipt proof.
            # Repository completion must additionally bind its specific dependencies.
            completion = (preview, PROJECT_ID, claim.attempt_id, receipt, 3, "a" * 64, "{}", NOW)
            complete = "INSERT INTO import_summary_completions VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(complete, completion)
            connection.execute(insert, row(2))
            connection.execute(insert, row(3))
            self.assertEqual(records[1].raw_sha256, records[2].raw_sha256)
            group = (preview, PROJECT_ID, claim.attempt_id, "raw", records[1].raw_sha256, 2, 2)
            connection.execute("INSERT INTO import_summary_groups VALUES (?, ?, ?, ?, ?, ?, ?)", group)
            connection.execute(complete, completion)
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(
                    "INSERT INTO import_summary_groups VALUES (?, ?, ?, ?, ?, ?, ?)", (*group[:3], "doi", *group[4:])
                )
            for table in (
                "import_summary_attempts",
                "import_summary_rows",
                "import_summary_groups",
                "import_summary_completions",
            ):
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(f"DELETE FROM {table}")
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(f"UPDATE {table} SET project_id=project_id")
            self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            connection.close()
