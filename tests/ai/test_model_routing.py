from __future__ import annotations

import asyncio
import copy
import json
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.model_gateway_contracts import decode_model_result  # noqa: E402
from research_observatory_core.model_registry_contracts import (  # noqa: E402
    ModelManifest,
    ModelRegistryCatalog,
    canonical_hash,
)
from research_observatory_core.model_routing import ModelGateway  # noqa: E402
from research_observatory_core.model_routing_contracts import (  # noqa: E402
    CancellationToken,
    RoutingPolicy,
    input_references,
)
from research_observatory_core.ports.model_gateway import ModelAdapterFailure  # noqa: E402
from research_observatory_core.ports.repositories import RepositoryConflict  # noqa: E402

from tests.ai.test_model_registry import FixtureInventory, FixturePolicy, manifest_document, task  # noqa: E402
from tests.model_routing_fixtures import MemoryRoutingRepository  # noqa: E402


class FixtureAdapter:
    """Synthetic adapter; no model, source bytes, network, or credentials."""

    def __init__(self, manifest: ModelManifest, outcomes=()) -> None:
        self.manifest = manifest
        self.outcomes = list(outcomes)
        self.calls = 0
        self.cancelled = 0
        self.entered = asyncio.Event()
        self.wait = False

    def describe(self) -> ModelManifest:
        return self.manifest

    async def health(self) -> bool:
        return True

    async def execute(self, task_spec, input_refs, *, attempt_id, cancel_token):
        self.calls += 1
        self.entered.set()
        if self.wait:
            await asyncio.Event().wait()
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            if callable(outcome):
                return outcome(task_spec)
        result = json.loads(
            (REPO / "packages/contracts/model-gateway/fixtures/valid-generation-result.v1.json").read_text("utf-8")
        )
        for key in ("taskId", "taskKind", "requestHash", "traceId"):
            result[key] = task_spec[key]
        result["route"] = {"selection": "selected"} | self.manifest.identity.model_dump(by_alias=True)
        return result

    async def cancel(self, attempt_id: str) -> None:
        self.cancelled += 1


class ModelRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.request = task()
        self.request["execution"] = {"mode": "dynamic"}
        self.original = copy.deepcopy(self.request)
        self.manifest = ModelManifest.model_validate(manifest_document())
        alternate = manifest_document()
        alternate["manifestId"] = "fixture-scholar-two"
        alternate["identity"]["modelId"] = "scholar-alternate"
        self.alternate = ModelManifest.model_validate(alternate)
        self.catalog = ModelRegistryCatalog(
            project_id="fixture-project", revision=1, manifests=(self.manifest, self.alternate)
        )
        self.authority = FixturePolicy()
        self.inventory = FixtureInventory(self.catalog.manifests)
        self.adapters = (FixtureAdapter(self.manifest), FixtureAdapter(self.alternate))
        self.repository = MemoryRoutingRepository("fixture-project")
        self.policy = RoutingPolicy(project_id="fixture-project", revision=1, maximum_cost_microunits=100)

    def gateway(self, adapters=None):
        return ModelGateway(
            catalog=self.catalog,
            inventory=self.inventory,
            authority=self.authority,
            adapters=self.adapters if adapters is None else adapters,
            repository=self.repository,
            clock_ms=lambda: 1500,
        )

    async def run_request(self, gateway=None, *, cancellation=None):
        return await (self.gateway() if gateway is None else gateway).execute(
            self.request,
            input_references(self.request),
            self.policy,
            CancellationToken() if cancellation is None else cancellation,
        )

    async def test_success_is_valid_owned_and_audited_and_completed_replay_does_not_dispatch(self):
        gateway = self.gateway()
        result = await self.run_request(gateway)
        self.assertEqual("succeeded", result["status"])
        self.assertIsNotNone(decode_model_result(self.request, result))
        self.assertEqual(self.original, self.request)
        self.assertEqual(result, await self.run_request(gateway))
        self.assertEqual(1, self.adapters[0].calls)
        run = self.repository.read(self.request["taskId"])
        self.assertEqual(canonical_hash(self.request), run.task_hash)
        self.assertEqual(["admitted", "routes", "attempt-started", "completed"], [event.kind for event in run.events])

    async def test_transient_failure_has_explicit_degraded_fallback_and_original_request(self):
        self.adapters[0].outcomes = [ModelAdapterFailure("temporarily-unavailable", retryable=True)]
        self.policy = self.policy.model_copy(update={"maximum_retries_per_route": 0})
        result = await self.run_request()
        self.assertEqual("degraded", result["status"])
        self.assertEqual("scholar-alternate", result["route"]["modelId"])
        self.assertEqual(self.original, self.request)
        self.assertIn("model-route-fallback", [item["code"] for item in result["diagnostics"]])
        self.assertTrue(
            any(event.kind == "attempt-failed" for event in self.repository.read(self.request["taskId"]).events)
        )

    async def test_fallback_reauthorizes_and_cannot_cross_changed_egress_or_permission(self):
        def revoke(_task):
            self.authority.reason_codes = ("fixture-rights-revoked",)
            raise ModelAdapterFailure("temporarily-unavailable", retryable=True)

        self.adapters[0].outcomes = [revoke]
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertEqual(1, self.adapters[0].calls)
        self.assertEqual(0, self.adapters[1].calls)
        self.assertIsNone(result["output"])
        self.assertEqual(self.original, self.request)

    async def test_pinned_failure_never_substitutes_and_nonretryable_failure_does_not_fallback(self):
        self.request["execution"] = task()["execution"]
        self.adapters[0].outcomes = [ModelAdapterFailure("provider-denied", retryable=False)]
        result = await self.run_request()
        self.assertEqual("failed", result["status"])
        self.assertEqual(0, self.adapters[1].calls)
        self.assertIsNone(result["output"])

    async def test_cancel_propagates_promptly_and_never_promotes_output(self):
        self.adapters[0].wait = True
        token = CancellationToken()
        pending = asyncio.create_task(self.run_request(cancellation=token))
        await self.adapters[0].entered.wait()
        started = time.perf_counter()
        token.cancel()
        result = await asyncio.wait_for(pending, 0.1)
        self.assertLess(time.perf_counter() - started, 0.1)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(1, self.adapters[0].cancelled)
        self.assertIsNone(result["output"])
        self.assertEqual(self.original, self.request)

    async def test_timeout_has_bounded_attempts_and_retains_original(self):
        self.request["requirements"]["deadlineMs"] = 20
        before = copy.deepcopy(self.request)
        self.adapters[0].wait = True
        result = await self.run_request()
        self.assertEqual("failed", result["status"])
        self.assertIn("model-deadline-exhausted", [item["code"] for item in result["diagnostics"]])
        self.assertEqual(1, self.adapters[0].cancelled)
        self.assertEqual(before, self.request)

    async def test_bad_references_and_same_id_changed_request_do_not_dispatch(self):
        with self.assertRaises(ValueError):
            await self.gateway().execute(self.request, (), self.policy, CancellationToken())
        self.assertEqual(0, self.adapters[0].calls)
        await self.run_request()
        self.request["requirements"]["maxOutputTokens"] = 100
        with self.assertRaises(RepositoryConflict):
            await self.run_request()
        self.assertEqual(1, self.adapters[0].calls)

    async def test_untrusted_success_with_wrong_route_or_output_is_discarded(self):
        self.adapters[0].outcomes = [lambda _task: {"status": "succeeded", "output": "untrusted"}]
        result = await self.run_request()
        self.assertEqual("failed", result["status"])
        self.assertIsNone(result["output"])
        self.assertEqual(0, self.adapters[1].calls)

    async def test_health_revocation_is_checked_before_dispatch(self):
        async def revoke():
            self.authority.reason_codes = ("fixture-rights-revoked",)
            return True

        self.adapters[0].health = revoke
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertEqual([0, 0], [adapter.calls for adapter in self.adapters])

    async def test_completed_output_is_not_replayed_after_permission_revocation(self):
        await self.run_request()
        previous = self.repository.read(self.request["taskId"])
        self.authority.reason_codes = ("fixture-rights-revoked",)
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertIsNone(result["output"])
        self.assertEqual(previous, self.repository.read(previous.task_id))
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])

    async def test_catalog_revocation_during_health_cannot_dispatch(self):
        current = [True]

        async def revoke():
            current[0] = False
            return True

        self.adapters[0].health = revoke
        gateway = self.gateway()
        gateway._catalog_is_current = lambda _catalog: current[0]
        result = await self.run_request(gateway)
        self.assertEqual("denied", result["status"])
        self.assertEqual([0, 0], [adapter.calls for adapter in self.adapters])

    async def test_revocation_after_output_discards_success(self):
        execute = self.adapters[0].execute

        async def revoke(*args, **kwargs):
            result = await execute(*args, **kwargs)
            self.authority.reason_codes = ("fixture-rights-revoked",)
            return result

        self.adapters[0].execute = revoke
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertIsNone(result["output"])
        self.assertEqual(0, self.adapters[1].calls)

    async def test_per_attempt_timeout_can_fallback_within_global_deadline(self):
        self.adapters[0].wait = True
        self.policy = self.policy.model_copy(update={"attempt_timeout_ms": 15, "maximum_retries_per_route": 0})
        result = await self.run_request()
        self.assertEqual("degraded", result["status"])
        self.assertEqual([1, 1], [adapter.calls for adapter in self.adapters])
        self.assertEqual(1, self.adapters[0].cancelled)

    async def test_finite_shared_attempt_budget(self):
        for adapter in self.adapters:
            adapter.outcomes = [ModelAdapterFailure("rate-limited", retryable=True) for _ in range(3)]
        self.policy = self.policy.model_copy(update={"maximum_attempts": 3, "initial_backoff_ms": 0})
        result = await self.run_request()
        self.assertEqual("failed", result["status"])
        self.assertEqual([2, 1], [adapter.calls for adapter in self.adapters])
        run = self.repository.read(self.request["taskId"])
        self.assertEqual(3, sum(event.kind == "attempt-started" for event in run.events))

    async def test_shared_cost_budget_cannot_be_reset_by_retry(self):
        charged = self.manifest.model_copy(update={"cost_microunits_per_thousand_tokens": 1})
        self.catalog = self.catalog.model_copy(update={"manifests": (charged,)})
        self.inventory = FixtureInventory((charged,))
        self.adapters = (FixtureAdapter(charged, [ModelAdapterFailure("rate-limited", retryable=True)]),)
        limits = self.request["requirements"]
        one_attempt = (limits["maxInputTokens"] + limits["maxOutputTokens"] + 999) // 1000
        self.policy = self.policy.model_copy(update={"maximum_cost_microunits": one_attempt})
        result = await self.run_request()
        self.assertEqual("failed", result["status"])
        self.assertEqual(1, self.adapters[0].calls)
        self.assertEqual("model-cost-budget-exhausted", result["diagnostics"][0]["code"])

    async def test_pinned_transient_failure_never_uses_alternate(self):
        self.request["execution"] = task()["execution"]
        self.adapters[0].outcomes = [ModelAdapterFailure("rate-limited", retryable=True)]
        self.policy = self.policy.model_copy(update={"maximum_retries_per_route": 0})
        result = await self.run_request()
        self.assertEqual("failed", result["status"])
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])

    async def test_remote_fallback_and_preference_cannot_override_local_egress_authority(self):
        remote = self.alternate.model_copy(update={"deployment": "remote"})
        self.catalog = self.catalog.model_copy(update={"manifests": (self.manifest, remote)})
        self.inventory = FixtureInventory(self.catalog.manifests)
        self.adapters = (
            FixtureAdapter(self.manifest, [ModelAdapterFailure("temporarily-unavailable", retryable=True)]),
            FixtureAdapter(remote),
        )
        self.policy = self.policy.model_copy(
            update={
                "preferred_manifest_ids": (remote.manifest_id,),
                "maximum_retries_per_route": 0,
                "permitted_deployments": ("local", "remote"),
            }
        )
        result = await self.run_request()
        self.assertEqual("failed", result["status"])
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])
        run = self.repository.read(self.request["taskId"])
        rejected = [item for event in run.events if event.resolution for item in event.resolution.rejected]
        self.assertTrue(
            any(
                item.manifest_id == remote.manifest_id and "deployment-denied" in item.reason_codes for item in rejected
            )
        )

    async def test_late_provider_completion_after_cancel_cannot_replace_terminal_record(self):
        original_execute = self.adapters[0].execute
        interrupted = asyncio.Event()
        release = asyncio.Event()
        finished = asyncio.Event()

        async def stubborn(*args, **kwargs):
            result = await original_execute(*args, **kwargs)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                interrupted.set()
                await release.wait()
            finished.set()
            return result

        self.adapters[0].execute = stubborn
        token = CancellationToken()
        pending = asyncio.create_task(self.run_request(cancellation=token))
        await self.adapters[0].entered.wait()
        token.cancel()
        result = await asyncio.wait_for(pending, 0.1)
        self.assertEqual("cancelled", result["status"])
        terminal = self.repository.read(self.request["taskId"])
        await interrupted.wait()
        # Acknowledging cancellation is not proof the adapter has stopped. Its
        # circuit must remain reserved rather than admitting overlapping work.
        circuit = self.repository.circuit(canonical_hash(self.manifest))
        try:
            self.assertIsNotNone(circuit.active_attempt_id)
        finally:
            release.set()
        await finished.wait()
        self.assertEqual(terminal, self.repository.read(terminal.task_id))
        self.assertIsNone(result["output"])

    async def test_circuit_open_survives_new_gateway_and_resets_after_cooldown(self):
        self.request["execution"] = task()["execution"]
        self.policy = self.policy.model_copy(update={"circuit_failure_threshold": 1})
        self.adapters[0].outcomes = [ModelAdapterFailure("runtime-failed", retryable=False)]
        await self.run_request()
        self.request["taskId"] = new_uuid_v7()
        result = await self.run_request()
        self.assertEqual("model-circuit-open", result["diagnostics"][0]["code"])
        self.assertEqual(1, self.adapters[0].calls)
        self.request["taskId"] = new_uuid_v7()
        gateway = self.gateway()
        gateway._clock_ms = lambda: 2600
        result = await self.run_request(gateway)
        self.assertEqual("succeeded", result["status"])
        self.assertEqual(0, self.repository.circuit(canonical_hash(self.manifest)).failures)

    async def test_cancellation_of_awaiting_caller_cancels_adapter(self):
        self.adapters[0].wait = True
        pending = asyncio.create_task(self.run_request())
        await self.adapters[0].entered.wait()
        pending.cancel()
        result = await asyncio.wait_for(pending, 0.1)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(1, self.adapters[0].cancelled)

    async def test_cancel_does_not_wait_for_unresponsive_cancel_hook(self):
        self.adapters[0].wait = True

        async def slow_cancel(_id):
            await asyncio.Event().wait()

        self.adapters[0].cancel = slow_cancel
        token = CancellationToken()
        pending = asyncio.create_task(self.run_request(cancellation=token))
        await self.adapters[0].entered.wait()
        started = time.perf_counter()
        token.cancel()
        result = await asyncio.wait_for(pending, 0.1)
        self.assertLess(time.perf_counter() - started, 0.1)
        self.assertEqual("cancelled", result["status"])


if __name__ == "__main__":
    unittest.main()
