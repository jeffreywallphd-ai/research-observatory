"""Live local queue/native session/encryption; declared synthetic parser adapter."""

import json
import sys
import threading
import time
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.corpus_repository import SqliteCorpusRepository  # noqa: E402
from research_observatory_core.corpus_service import CorpusService  # noqa: E402
from research_observatory_core.document_parse_worker import document_worker_policy  # noqa: E402
from research_observatory_core.document_parser_runtime import InstalledParser  # noqa: E402
from research_observatory_core.document_revision_api import DocumentParseCommand  # noqa: E402
from research_observatory_core.document_revision_service import DocumentRevisionService  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.main import DocumentAttachmentRuntime  # noqa: E402
from research_observatory_core.repositories import (  # noqa: E402
    _SqliteWorkflowQueueRepository,
    sqlite_intent_authority_snapshot,
    sqlite_workflow_admission_binding,
)
from research_observatory_core.workflow_executor import (  # noqa: E402
    LocalAdmissionController,
    WorkerCapacity,
    WorkerResources,
)

from tests.documents import test_document_revision_repository as fixtures  # noqa: E402


def now():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DocumentRevisionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f
        owner = self

        class SyntheticRuntime:
            def load(self):
                raise RuntimeError("synthetic-text-only-runtime")

            load_native = load
            load_inspection = load

            def load_text(self):
                return InstalledParser(object(), owner.f.request.binding.producer)

            def run(self, installed, request, source, *, cancelled, page_index=None):
                owner.running.set()
                owner.on_parse()
                deadline = time.monotonic() + owner.delay
                while time.monotonic() < deadline:
                    if cancelled():
                        owner.cancelled.set()
                        raise RuntimeError("synthetic-parser-cancelled")
                    time.sleep(0.01)
                return json.dumps(
                    {
                        "schemaVersion": "1.0",
                        "documentType": "bounded-text-parser-output",
                        "text": source.read().decode(),
                    }
                ).encode()

        self.running, self.cancelled = threading.Event(), threading.Event()
        self.on_parse, self.delay = lambda: None, 0
        self.controller = LocalAdmissionController(interactive_reserve=WorkerResources(1, 256 * 1024**2, 0, 0))

        def admission(path, project):
            binding = sqlite_workflow_admission_binding(
                _SqliteWorkflowQueueRepository(path / "state/project.sqlite3", project),
                controller=self.controller,
                policy=document_worker_policy(project),
            )
            return replace(binding, capacity=lambda: WorkerCapacity(8, 8 * 1024**3, 0, 8 * 1024**3))

        self.service = DocumentRevisionService(
            DocumentAttachmentRuntime(
                self.f.preview.service,
                CorpusService(
                    self.f.preview.service._projects,
                    self.f.preview.service._privacy,
                    imports=self.f.preview.service,
                    connectors=None,
                    repository_factory=lambda path, project: SqliteCorpusRepository(
                        path / "state/project.sqlite3", project
                    ),
                    intent_factory=sqlite_intent_authority_snapshot,
                    actor_id=self.f.actor.actor_id,
                    now=now,
                ),
                lambda _path, _project: self.f.fixture.store,
            ),
            self.f.preview.service,
            admission,
            repository_factory=fixtures.LocalDocumentRevisionRepository,
            runtime=SyntheticRuntime(),
            now=now,
        )
        self.addCleanup(self.service.shutdown)
        self.command = DocumentParseCommand(
            root=self.f.preview.root,
            project_id=self.f.source.project_id,
            session_id=self.f.session,
            command_id=new_uuid_v7(),
            attachment_id=self.f.source.attachment_id,
        )

    def test_native_composition_retains_success_with_live_heartbeat_and_intervening_rights_write(self):
        job = self.service.parse(self.command, trace_id="a" * 32)
        self.delay = 2.4
        self.on_parse = lambda: self.f.permit()
        heartbeats = []
        original = _SqliteWorkflowQueueRepository.heartbeat

        def observed(queue, *args, **kwargs):
            heartbeats.append(time.monotonic())
            return original(queue, *args, **kwargs)

        with patch.object(_SqliteWorkflowQueueRepository, "heartbeat", observed):
            self.service.run_pending()
        self.assertGreaterEqual(len(heartbeats), 3)
        self.assertTrue(self.running.is_set())
        repository, _, _ = self.service._repository(
            self.command.root, self.command.project_id, self.command.session_id, "a" * 32
        )
        state, receipt = repository.status(job.job_id)
        self.assertEqual("succeeded", state.state)
        self.assertIsNotNone(receipt)
        self.assertEqual(0, self.fixture.counts()["document_normalized_revisions"])
        retained, result = repository.result(receipt.result_id)
        self.assertEqual(receipt, retained)
        self.assertEqual("Synthetic plain text full text\n", result.ir.text_projections[0].raw_text)

    def test_current_copy_rights_revoke_during_inference_denies_success(self):
        job = self.service.parse(self.command, trace_id="a" * 32)
        self.on_parse = lambda: self.f.permit(derive="denied")
        self.service.run_pending()
        self.assertEqual("failed", self.fixture.queue.get(job.job_id).state)
        self.assertEqual(0, self.fixture.counts()["document_normalized_revisions"])
        self.assertIsNone(self.fixture.queue.accepted_output(job.job_id))

    def test_native_close_latch_interrupts_without_waiting_for_lifecycle_mutex(self):
        job = self.service.parse(self.command, trace_id="a" * 32)
        self.delay = 8
        worker = threading.Thread(target=self.service.run_pending)
        worker.start()
        try:
            self.assertTrue(self.running.wait(3))
            self.f.preview.service.signal_stop(self.command.root)
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertTrue(self.cancelled.is_set())
            self.assertNotEqual("succeeded", self.fixture.queue.get(job.job_id).state)
            self.assertIsNone(self.fixture.queue.accepted_output(job.job_id))
            self.assertEqual(0, self.fixture.counts()["document_normalized_revisions"])
        finally:
            self.service.signal_stop()
            worker.join(timeout=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
