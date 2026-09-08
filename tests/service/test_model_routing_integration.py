from __future__ import annotations

import asyncio
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

# ruff: noqa: E402

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.model_registry_contracts import canonical_hash
from research_observatory_core.model_registry_repository import SqliteModelRoutingRepository
from research_observatory_core.model_routing_contracts import CancellationToken, input_references
from research_observatory_core.ports.repositories import RepositoryConflict
from research_observatory_core.storage import configure_protected_database_provider, initialize_database

from tests.ai import test_model_routing as routing_fixtures
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider
from tests.service.test_model_registry_repository import PROJECT, STAMP


class ProtectedModelRoutingTests(routing_fixtures.ModelRoutingTests):
    """Run the same adapter conformance/routing suite through real SQLCipher."""

    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-routing-integration-fixture-")
        self.root = Path(self.temporary.name).resolve()
        (self.root / "state").mkdir()
        (self.root / ".tmp").mkdir()
        self.database = self.root / "state/project.sqlite3"
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        self.assertTrue(initialize_database(self.database, project_id=PROJECT, project_created_at=STAMP).ok)
        self.actor = new_uuid_v7()
        self.repository: SqliteModelRoutingRepository = SqliteModelRoutingRepository(self.database, PROJECT, self.actor)
        self.catalog = self.catalog.model_copy(update={"project_id": PROJECT})
        self.policy = self.policy.model_copy(update={"project_id": PROJECT})

    def tearDown(self):
        self.temporary.cleanup()

    async def test_interrupted_run_restart_never_redispatches_and_terminal_recovery_fences_late_result(self):
        self.adapters[0].wait = True
        pending = asyncio.create_task(self.run_request())
        await self.adapters[0].entered.wait()
        prior = self.repository.read(self.request["taskId"])
        assert prior is not None
        self.repository = SqliteModelRoutingRepository(self.database, PROJECT, self.actor)
        restarted = self.gateway()
        with self.assertRaisesRegex(ValueError, "recovery is required"):
            await self.run_request(restarted)
        with self.assertRaises(ValueError):
            restarted.recover_interrupted(prior.task_id, expected_revision=prior.revision - 1)
        recovered = restarted.recover_interrupted(prior.task_id, expected_revision=prior.revision)
        self.assertEqual(prior.events, recovered.events[:-1])
        self.assertEqual(prior.task_json, recovered.task_json)
        self.assertEqual("interrupted", recovered.events[-1].kind)
        result_json = recovered.events[-1].result_json
        assert result_json is not None
        self.assertIsNone(json.loads(result_json)["output"])
        self.assertIsNotNone(self.repository.circuit(canonical_hash(self.manifest)).active_attempt_id)
        replay = await self.run_request(restarted)
        self.assertEqual("model-prior-execution-uncertain", replay["diagnostics"][0]["code"])
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])
        pending.cancel()
        with self.assertRaises(RepositoryConflict):
            await pending
        self.assertEqual(recovered, self.repository.read(prior.task_id))

    async def test_other_actor_cannot_terminalize_or_append_an_admitted_run(self):
        token = CancellationToken()
        self.adapters[0].wait = True
        pending = asyncio.create_task(self.run_request(cancellation=token))
        await self.adapters[0].entered.wait()
        prior = self.repository.read(self.request["taskId"])
        assert prior is not None
        repository = self.repository
        self.repository = SqliteModelRoutingRepository(self.database, PROJECT, new_uuid_v7())
        with self.assertRaises(RepositoryConflict):
            self.gateway().recover_interrupted(prior.task_id, expected_revision=prior.revision)
        self.assertEqual(prior, repository.read(prior.task_id))
        token.cancel()
        self.assertEqual("cancelled", (await pending)["status"])

    async def test_persisted_success_replay_after_gateway_restart_has_zero_new_adapter_calls(self):
        result = await self.run_request()
        self.repository = SqliteModelRoutingRepository(self.database, PROJECT, self.actor)
        self.assertEqual(result, await self.run_request(self.gateway()))
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])

    async def test_connection_scope_is_not_inherited_by_other_tasks_or_threads(self):
        with self.repository.session():
            self.assertIsNone(self.repository.read(self.request["taskId"]))

            async def child():
                with self.assertRaises(RepositoryConflict):
                    self.repository.read(self.request["taskId"])

            await asyncio.create_task(child())
            with self.assertRaises(RepositoryConflict):
                await asyncio.to_thread(self.repository.read, self.request["taskId"])
        self.assertIsNone(self.repository.read(self.request["taskId"]))

    async def test_attempt_and_circuit_admission_roll_back_together_before_dispatch(self):
        from unittest.mock import patch

        original = self.repository._append_audit

        def fail_attempt(connection, envelope):
            if envelope["eventType"] == "model.routing.attempt-started":
                raise OSError("synthetic attempt audit failure")
            return original(connection, envelope)

        from research_observatory_core.ports.repositories import RepositoryTransactionFailed

        with (
            patch.object(self.repository, "_append_audit", side_effect=fail_attempt),
            self.assertRaises(RepositoryTransactionFailed),
        ):
            await self.run_request()
        # The entire initial boundary rolls back before any provider work. The
        # same unchanged request can safely be admitted after storage recovers.
        self.assertIsNone(self.repository.read(self.request["taskId"]))
        self.assertEqual(0, self.repository.circuit(canonical_hash(self.manifest)).revision)
        self.assertEqual([0, 0], [adapter.calls for adapter in self.adapters])
        self.assertEqual("succeeded", (await self.run_request())["status"])
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])

    async def test_gateway_overhead_p95_excluding_model_execution(self):
        measurements = []
        gateway = self.gateway()
        loop = asyncio.get_running_loop()
        prior_debug = loop.get_debug()
        # Production asyncio does not collect unittest's task-creation stacks.
        # Functional conformance tests retain IsolatedAsyncioTestCase debug mode.
        loop.set_debug(False)
        try:
            for _ in range(101):
                self.request["taskId"] = new_uuid_v7()
                started = time.perf_counter()
                result = await gateway.execute(
                    self.request, input_references(self.request), self.policy, CancellationToken()
                )
                measurements.append((time.perf_counter() - started) * 1000)
                self.assertEqual("succeeded", result["status"])
        finally:
            loop.set_debug(prior_debug)
        # Zero-delay synthetic model: conservatively include fixture dispatch and
        # result construction, protected journal I/O, validation and Core routing.
        # One cold measurement, then 100 retained warm observations: nearest-rank
        # percentiles without trimming slow samples or retrying for a pass.
        p95 = sorted(measurements[1:])[94]
        print(
            f"protected-gateway-fixture: cold={measurements[0]:.3f}ms; "
            f"warm-p50={sorted(measurements[1:])[49]:.3f}ms; warm-p95={p95:.3f}ms; "
            f"samples={len(measurements) - 1}; protected-I/O included; synthetic zero-delay adapter"
        )
        print(
            json.dumps(
                {
                    "benchmark": "protected-gateway-fixture",
                    "unit": "milliseconds",
                    "cold": measurements[0],
                    "warmSamples": measurements[1:],
                    "percentileMethod": "nearest-rank; all 100 warm samples retained",
                    "python": platform.python_version(),
                    "platform": platform.system(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                    "scope": (
                        "Protected SQLCipher with in-memory fixture keys; zero-delay synthetic adapter; "
                        "excludes production lifecycle factory, packaging and live inference."
                    ),
                },
                sort_keys=True,
            )
        )
        self.assertLess(p95, 25, f"protected gateway fixture p95={p95:.3f}ms; samples={len(measurements) - 1}")
