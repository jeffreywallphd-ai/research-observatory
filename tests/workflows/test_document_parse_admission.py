"""Fixed product activity admission, conservative capacity and parser serialization.

Real disposable queue/history; small injected capacities test policy arithmetic.
These are not native containment or minimum-hardware qualification tests.
"""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.repositories import sqlite_workflow_queue_repository  # noqa: E402
from research_observatory_core.storage import initialize_database  # noqa: E402
from research_observatory_core.workflow_executor import (  # noqa: E402
    ActivityWorkerDemand,
    LocalWorkerSupervisor,
    ProjectWorkerPolicy,
    WorkerCapacity,
    WorkerResources,
)

from tests.workflows import test_local_workflow_executor as fixtures  # noqa: E402


class DocumentParseAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.LocalWorkflowExecutorTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.metadata = WorkerResources(1, 10, 0, 10)
        self.parser = WorkerResources(4, 40, 0, 40)
        self.mapping = {"document-parse": ActivityWorkerDemand("document", self.parser, exclusive=True)}
        self.policy = ProjectWorkerPolicy(
            fixtures.PROJECT_ID,
            WorkerResources(8, 100, 0, 100),
            {"document": self.metadata},
            {"document": 1},
            activity_demands=self.mapping,
        )

    def binding(self, *, capacity=None, **kwargs):
        return self.fixture.admission(
            policy=self.policy,
            capacity=capacity or (lambda: WorkerCapacity(32, 1000, 0, 1000)),
            **kwargs,
        )

    def supervisor(self, binding, handlers, *, activity_types=None, limits=None):
        return LocalWorkerSupervisor(
            self.fixture.repository,
            handlers,
            concurrency_limits=limits or {"document": 1},
            now=lambda: "2026-08-30T12:02:00.000Z",
            recovery_actor=fixtures.SYSTEM,
            admission=binding,
            activity_types=activity_types,
        )

    def test_metadata_filter_keeps_light_reservation_when_parser_cannot_fit(self):
        self.fixture.repository.enqueue(self.fixture.submission(), actor=fixtures.SYSTEM)
        binding = self.binding(capacity=lambda: WorkerCapacity(2, 20, 0, 20))
        handlers = {"source-acquisition": lambda _context, claim: self.fixture.activity_output(claim)}
        result = self.supervisor(binding, handlers).run_available()
        self.assertEqual("succeeded", result[0].state)

    def test_mixed_implicit_filter_reserves_parser_bound_before_any_claim(self):
        self.fixture.repository.enqueue(self.fixture.submission(), actor=fixtures.SYSTEM)
        before = self.fixture.queue_state()
        binding = self.binding(capacity=lambda: WorkerCapacity(4, 50, 0, 50))
        handlers = {"source-acquisition": lambda *_: (), "document-parse": lambda *_: ()}
        with patch.object(self.fixture.repository, "claim_next", wraps=self.fixture.repository.claim_next) as claim:
            self.assertEqual((), self.supervisor(binding, handlers).run_available())
            claim.assert_not_called()
        self.assertEqual(before, self.fixture.queue_state())

    def test_filter_and_policy_are_frozen_and_identical_for_recovery_and_claim(self):
        binding = self.binding()
        self.fixture.repository.enqueue(self.fixture.submission(), actor=fixtures.SYSTEM)
        handlers = {"source-acquisition": lambda _context, claim: self.fixture.activity_output(claim)}
        worker = self.supervisor(binding, handlers)
        handlers["document-parse"] = lambda *_: self.fail("Unselected parser ran")
        self.mapping.clear()
        self.assertIn("document-parse", self.policy.activity_demands)
        with self.assertRaises(TypeError):
            self.policy.activity_demands["document-parse"] = self.mapping  # type: ignore[index, assignment]
        with (
            patch.object(
                self.fixture.repository, "recover_expired", wraps=self.fixture.repository.recover_expired
            ) as recovery,
            patch.object(self.fixture.repository, "claim_next", wraps=self.fixture.repository.claim_next) as claim,
        ):
            self.assertEqual("succeeded", worker.run_available()[0].state)
            self.assertEqual(("source-acquisition",), recovery.call_args.kwargs["activity_types"])
            self.assertTrue(claim.call_args_list)
            self.assertTrue(
                all(call.kwargs["activity_types"] == ("source-acquisition",) for call in claim.call_args_list)
            )

    def test_explicit_metadata_subset_avoids_parser_reservation(self):
        binding = self.binding(capacity=lambda: WorkerCapacity(2, 20, 0, 20))
        self.fixture.repository.enqueue(self.fixture.submission(), actor=fixtures.SYSTEM)
        handlers = {
            "source-acquisition": lambda _context, claim: self.fixture.activity_output(claim),
            "document-parse": lambda *_: self.fail("Excluded parser ran"),
        }
        self.assertEqual(
            "succeeded",
            self.supervisor(binding, handlers, activity_types=("source-acquisition",)).run_available()[0].state,
        )

    def test_four_cpu_slots_deny_five_permit_and_each_other_shortage_denies(self):
        for capacity in (
            WorkerCapacity(4, 50, 0, 50),
            WorkerCapacity(5, 49, 0, 50),
            WorkerCapacity(5, 50, 0, 49),
            WorkerCapacity(None, 50, 0, 50),
            WorkerCapacity(5, None, 0, 50),
        ):
            with self.subTest(capacity=capacity):
                binding = self.binding(capacity=lambda capacity=capacity: capacity)
                self.assertIsNone(
                    binding.controller.reserve(binding, "document", local_limit=1, activity_types=("document-parse",))
                )
        binding = self.binding(capacity=lambda: WorkerCapacity(5, 50, 0, 50))
        token = binding.controller.reserve(binding, "document", local_limit=1, activity_types=("document-parse",))
        self.assertIsNotNone(token)
        binding.controller.release(token)

    def test_parser_permit_is_shared_across_projects_and_release_does_not_block_metadata(self):
        first = self.binding()
        identity = new_uuid_v7()
        root = self.fixture.root.parent / "second-project"
        (root / "state").mkdir(parents=True)
        initialize_database(root / "state/project.sqlite3", project_id=identity, project_created_at=fixtures.CREATED_AT)
        repository = sqlite_workflow_queue_repository(root, identity)
        second = self.fixture.admission(
            repository=repository,
            controller=first.controller,
            policy=replace(self.policy, project_id=identity),
            capacity=first.capacity,
        )
        token = first.controller.reserve(first, "document", local_limit=1, activity_types=("document-parse",))
        self.assertIsNotNone(token)
        try:
            self.assertIsNone(
                second.controller.reserve(second, "document", local_limit=1, activity_types=("document-parse",))
            )
            metadata = second.controller.reserve(
                second, "document", local_limit=1, activity_types=("source-acquisition",)
            )
            self.assertIsNotNone(metadata)
            second.controller.release(metadata)
        finally:
            first.controller.release(token)
        admitted = second.controller.reserve(second, "document", local_limit=1, activity_types=("document-parse",))
        self.assertIsNotNone(admitted)
        second.controller.release(admitted)

    def test_wrong_class_invalid_activity_and_conflicting_policy_fail_before_claim(self):
        binding = self.binding()
        for selection in ((), ("bad activity",), ("source-acquisition", "source-acquisition")):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.supervisor(binding, {"source-acquisition": lambda *_: ()}, activity_types=selection)
        with self.assertRaises(ValueError):
            binding.controller.reserve(binding, "maintenance", local_limit=1, activity_types=("document-parse",))
        with self.assertRaises(ValueError):
            self.fixture.admission(
                controller=binding.controller,
                policy=replace(self.policy, activity_demands={}),
            )
        with self.assertRaises(ValueError):
            replace(self.policy, activity_demands={"bad activity": self.mapping["document-parse"]})
        with self.assertRaises(ValueError):
            ActivityWorkerDemand("document", self.parser, exclusive=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
