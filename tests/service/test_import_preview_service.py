"""Real project, Intent, privacy, encrypted-object and worker composition."""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.import_preview_repository import sqlite_import_preview_repository
from research_observatory_core.import_preview_service import ImportPreviewService, ImportProjectAdapters
from research_observatory_core.object_store import create_local_object_store
from research_observatory_core.ports.import_previews import PreviewCreate, PreviewProblem
from research_observatory_core.privacy import ProjectPrivacyService
from research_observatory_core.projects import ProjectLifecycleProblem, ProjectLifecycleService
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
    sqlite_intent_revision_repository,
    sqlite_privacy_policy_repository,
    sqlite_workflow_admission_binding,
    sqlite_workflow_queue_repository,
)
from research_observatory_core.research_intents import ResearchIntentService
from research_observatory_core.storage import development_plaintext_database_fixture
from research_observatory_core.workflow_executor import (
    LocalAdmissionController,
    ProjectWorkerPolicy,
    WorkerCapacity,
    WorkerResources,
)

from tests.data import test_import_source_chunks as fixture


class ImportPreviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ro-import-runtime-")
        self.addCleanup(self.temp.cleanup)
        protection = development_plaintext_database_fixture()
        protection.__enter__()
        self.addCleanup(protection.__exit__, None, None, None)
        self.projects = ProjectLifecycleService()
        self.addCleanup(self.projects.shutdown)
        self.actor = new_uuid_v7()
        self.intents = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
            stale_state_repository_factory=sqlite_dependency_impact_repository,
            local_actor_id=self.actor,
        )
        created = self.projects.create(
            parent_directory=self.temp.name,
            directory_name="synthetic-project",
            display_name="Synthetic import",
            template_id="theory-synthesis",
            trace_id="1" * 32,
            initialize_authority=lambda path, identity: self.intents.initialize_created_project(
                path,
                identity,
                primary_use_case="theory-synthesis",
                research_objective="Synthetic local bibliography",
                trace_id="1" * 32,
            ),
        )
        self.root, self.project_id = created.root, created.project_id
        self.projects.open(root=self.root, trace_id="1" * 32)
        self.privacy = ProjectPrivacyService(self.projects, sqlite_privacy_policy_repository)
        self.controller = LocalAdmissionController(interactive_reserve=WorkerResources(1, 64 * 1024**2, 0, 1024**2))
        self.epoch = "1" * 32
        self.now = "2026-09-19T19:50:00.000Z"
        self.service = self.runtime()
        self.addCleanup(self.service.shutdown)

    def adapters(self, path, identity):
        queue = sqlite_workflow_queue_repository(path, identity)
        demand = WorkerResources(1, 64 * 1024**2, 0, 1024**2)
        admission = sqlite_workflow_admission_binding(
            queue,
            controller=self.controller,
            policy=ProjectWorkerPolicy(identity, demand, {"document": demand}, {"document": 1}),
        )
        return ImportProjectAdapters(
            sqlite_import_preview_repository(path / "state/project.sqlite3", identity),
            sqlite_intent_revision_repository(path, identity),
            queue,
            create_local_object_store(
                path,
                identity,
                key_provider=fixture.MemoryKeyProvider({"object-key-v1": b"k" * 32}, "object-key-v1"),
                access_policy=self.privacy.object_access_policy(str(path)),
            ),
            create_sqlite_unit_of_work_factory(path / "state/project.sqlite3", identity),
            replace(admission, capacity=lambda: WorkerCapacity(4, 1024**3, 0, 1024**3)),
        )

    def runtime(self, epoch=None):
        return ImportPreviewService(
            self.projects,
            self.privacy,
            self.adapters,
            local_actor_id=self.actor,
            resume_epoch=epoch or self.epoch,
            now=lambda: self.now,
        )

    def intake(self):
        raw = b"title,doi\nSynthetic,10.99999/EXAMPLE\n"
        actor = self.service.actor("2" * 32)
        command = PreviewCreate(
            preview_id=new_uuid_v7(),
            source_name="synthetic.csv",
            format_name="csv",
            rights=fixture.RIGHTS,
            actor=actor,
        )
        self.service.create(self.root, command)
        self.service.append_chunk(self.root, command.preview_id, ordinal=1, data=raw)
        self.service.seal(
            self.root,
            command.preview_id,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            trace_id="2" * 32,
        )
        return command.preview_id

    def test_created_draft_intent_is_real_context_not_an_acceptance_gate(self):
        preview = self.intake()
        job = self.service.schedule(self.root, preview)
        self.assertEqual(job.job_id, self.service.schedule(self.root, preview).job_id)
        queue = sqlite_workflow_queue_repository(Path(self.root), self.project_id)
        snapshot = json.loads(queue.authority(job.job_id).snapshot_json)
        intent = self.intents.workspace(self.root).current
        assert intent is not None
        self.assertEqual("draft", intent.status)
        self.assertEqual(intent.revision_id, snapshot["intent"]["revisionId"])
        self.service.run_pending()
        self.assertEqual("succeeded", queue.get(job.job_id).state)
        self.assertEqual(2, len(self.service.records_page(self.root, preview, after=0, limit=10)))
        current = self.intents.workspace(self.root).current
        assert current is not None
        self.assertEqual("draft", current.status)

    def test_new_recovery_epoch_cancels_old_job_before_claim(self):
        preview = self.intake()
        job = self.service.schedule(self.root, preview)
        self.service.shutdown()
        restarted = self.runtime("2" * 32)
        self.addCleanup(restarted.shutdown)
        restarted.attach(self.root)
        restarted.run_pending()
        state = sqlite_workflow_queue_repository(Path(self.root), self.project_id).get(job.job_id)
        self.assertEqual("cancelled", state.state)
        self.assertEqual("policy", state.interruption_kind)
        self.assertEqual(0, state.attempt_count)
        with self.assertRaises(PreviewProblem):
            restarted.records_page(self.root, preview, after=0, limit=10)

    def test_close_and_reopen_do_not_reuse_old_live_project_binding(self):
        preview = self.intake()
        job = self.service.schedule(self.root, preview)
        self.service.detach(self.root)
        self.projects.close(root=self.root, trace_id="2" * 32)
        with self.assertRaises(ProjectLifecycleProblem):
            self.service.records_page(self.root, preview, after=0, limit=10)
        self.projects.open(root=self.root, trace_id="2" * 32)
        self.service.attach(self.root)
        self.service.run_pending()
        self.assertEqual(
            "succeeded", sqlite_workflow_queue_repository(Path(self.root), self.project_id).get(job.job_id).state
        )

    def test_foreign_intent_adapter_cannot_substitute_a_valid_bridge(self):
        other = self.projects.create(
            parent_directory=self.temp.name,
            directory_name="other-project",
            display_name="Other synthetic project",
            template_id="theory-synthesis",
            trace_id="3" * 32,
            initialize_authority=lambda path, identity: self.intents.initialize_created_project(
                path,
                identity,
                primary_use_case="theory-synthesis",
                research_objective="Other objective",
                trace_id="3" * 32,
            ),
        )
        preview = self.intake()
        wrong = ImportPreviewService(
            self.projects,
            self.privacy,
            lambda path, identity: replace(
                self.adapters(path, identity),
                intents=sqlite_intent_revision_repository(Path(other.root), other.project_id),
            ),
            local_actor_id=self.actor,
            resume_epoch=self.epoch,
            now=lambda: self.now,
        )
        self.addCleanup(wrong.shutdown)
        with self.assertRaisesRegex(PreviewProblem, "preview-intent-project-mismatch"):
            wrong.schedule(self.root, preview)

    def test_background_pump_and_cancel_before_claim(self):
        cancelled = self.intake()
        job = self.service.schedule(self.root, cancelled)
        self.service.cancel(self.root, cancelled, trace_id="4" * 32)
        queue = sqlite_workflow_queue_repository(Path(self.root), self.project_id)
        self.assertEqual("cancelled", queue.get(job.job_id).state)
        self.assertEqual(0, queue.get(job.job_id).attempt_count)
        second = self.intake()
        next_job = self.service.schedule(self.root, second)
        self.service.start()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and queue.get(next_job.job_id).state not in {"succeeded", "failed"}:
            time.sleep(0.01)
        self.assertEqual("succeeded", queue.get(next_job.job_id).state)
        self.service.detach(self.root)
        with self.assertRaises(PreviewProblem):
            self.service.records_page(self.root, cancelled, after=0, limit=10)


if __name__ == "__main__":
    unittest.main()
