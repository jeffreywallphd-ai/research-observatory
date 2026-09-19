"""Parse activity proof using encrypted objects and real durable attempt leases."""

from __future__ import annotations

import unittest

from research_observatory_core.ports.import_previews import PreviewProblem
from research_observatory_core.repositories import create_sqlite_unit_of_work_factory
from research_observatory_core.workflow_executor import WorkflowActivityContext, WorkflowCancellationRequested

from tests.data import test_import_preview_repository as fixture


class ImportPreviewActivityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportPreviewRepositoryTests(methodName="runTest")
        lifecycle: unittest.TestCase = self.fixture
        lifecycle.setUp()
        self.addCleanup(lifecycle.tearDown)

    def activity(self, preview, actor, guard):
        from research_observatory_core.ingestion.preview_activity import ImportPreviewActivity

        return ImportPreviewActivity(
            preview_id=preview,
            repository=self.fixture.repository(),
            store=self.fixture.store(),
            unit_of_work=create_sqlite_unit_of_work_factory(
                self.fixture.project / "state/project.sqlite3",
                fixture.fixture.PROJECT_ID,
            ),
            guard=guard,
            trace_id=actor.trace_id,
        )

    def test_real_encrypted_source_parse_receipt_and_exact_attempt_acceptance(self):
        preview, _, _, claim, queue, actor = self.fixture.parse_attempt(
            b"title,doi\nSynthetic,10.99999/EXAMPLE\nMalformed\n"
        )
        calls = 0

        def guard(action):
            nonlocal calls
            calls += 1
            return action()

        context = WorkflowActivityContext(queue, claim, lambda: actor.occurred_at, 30_000)
        outputs = self.activity(preview, actor, guard)(context, claim)
        self.assertEqual(1, len(outputs))
        self.assertGreater(calls, 3)
        with self.assertRaises(PreviewProblem):
            self.fixture.repository().records_page(preview, after=0, limit=10)
        queue.stage_artifact(context.claim, artifact=outputs[0], role="output", now=actor.occurred_at)
        queue.complete(context.claim, outputs=outputs, now=actor.occurred_at)
        records = self.fixture.repository().records_page(preview, after=0, limit=10)
        self.assertEqual(3, len(records))
        self.assertEqual("malformed", records[-1].status)
        self.assertEqual("10.99999/example", records[1].candidates[1].value)

    def test_durable_cancellation_before_parse_never_creates_accepted_preview(self):
        preview, _, _, claim, queue, actor = self.fixture.parse_attempt(b"title\nSynthetic\n")
        queue.request_cancellation(
            claim.job_id,
            actor=fixture.worker_fixture.SYSTEM,
            now=actor.occurred_at,
            reason_code="test-user-cancel",
            interruption_kind="user-cancel",
        )
        context = WorkflowActivityContext(queue, claim, lambda: actor.occurred_at, 30_000)
        with self.assertRaises(WorkflowCancellationRequested):
            self.activity(preview, actor, lambda action: action())(context, claim)
        with self.assertRaises(PreviewProblem):
            self.fixture.repository().records_page(preview, after=0, limit=10)

    def test_revoked_project_guard_stops_before_read_or_receipt(self):
        preview, _, _, claim, queue, actor = self.fixture.parse_attempt(b"title\nSynthetic\n")

        def denied(_action):
            raise PreviewProblem("project-authority-revoked")

        context = WorkflowActivityContext(queue, claim, lambda: actor.occurred_at, 30_000)
        with self.assertRaisesRegex(PreviewProblem, "project-authority-revoked"):
            self.activity(preview, actor, denied)(context, claim)
        with self.assertRaises(PreviewProblem):
            self.fixture.repository().records_page(preview, after=0, limit=10)


if __name__ == "__main__":
    unittest.main()
