"""Search preparation/execution uses the actual existing local admitted queue."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_parse_worker import document_worker_policy  # noqa: E402
from research_observatory_core.lexical_search_worker import LexicalSearchActivity  # noqa: E402
from research_observatory_core.ports.workflow_executor import WorkflowActor  # noqa: E402
from research_observatory_core.repositories import sqlite_workflow_admission_binding  # noqa: E402
from research_observatory_core.workflow_executor import (  # noqa: E402
    LocalAdmissionController,
    LocalWorkerSupervisor,
    WorkerResources,
)

from tests.search.fixture_support import SearchRunFixture  # noqa: E402


class LexicalSearchActivityTests(SearchRunFixture):
    def test_unprepared_query_gets_admitted_preparation_atomic_result_and_owned_drain(self):
        self.assertIsNone(self.service.catalog.selected())
        job = self.repo.submit(self.inputs())
        policy = document_worker_policy(self.service.project)
        self.assertTrue(policy.activity_demands["lexical-search"].exclusive)
        controller = LocalAdmissionController(interactive_reserve=WorkerResources(1, 64 * 1024**2, 0, 1024**2))
        admission = sqlite_workflow_admission_binding(self.repo.queue, controller=controller, policy=policy)
        self.repo.documents.bind_admission(admission)
        activity = LexicalSearchActivity(self.repo, session_stopped=lambda: False, heartbeat_seconds=0.25)
        results = LocalWorkerSupervisor(
            self.repo.queue,
            {"lexical-search": activity},
            concurrency_limits={"document": 1},
            now=lambda: self.document_fixture.now,
            recovery_actor=WorkflowActor(self.document_fixture.actor.actor_id, "system", "workflow-coordinator"),
            admission=admission,
            activity_types=("lexical-search",),
        ).run_available()
        self.assertEqual((job.job_id,), tuple(value.job_id for value in results))
        self.assertEqual("succeeded", self.repo.queue.get(job.job_id).state)
        self.assertIsNotNone(self.repo.result(job.job_id))
        self.assertIsNotNone(self.service.catalog.selected())
        import threading

        self.assertFalse(any(value.name == "ro-search-lease" for value in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()
