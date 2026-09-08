from __future__ import annotations

import asyncio
import copy
import json
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
    RoutingRun,
    input_references,
)
from research_observatory_core.ports.model_gateway import ModelAdapterFailure, ModelRoutingRepository  # noqa: E402
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
        self.adapters: tuple[FixtureAdapter, ...] = (FixtureAdapter(self.manifest), FixtureAdapter(self.alternate))
        self.repository: ModelRoutingRepository = MemoryRoutingRepository("fixture-project")
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
        assert run is not None
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
        run = self.repository.read(self.request["taskId"])
        assert run is not None
        self.assertTrue(any(event.kind == "attempt-failed" for event in run.events))

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
        now = [100.0]
        # Isolate expiry of an already dispatched call. Real protected admission
        # may take longer than 20 ms; pre-dispatch expiry has a separate test.
        # Only routing time is controlled, never asyncio or the storage clock.
        with patch("research_observatory_core.model_routing.time", SimpleNamespace(monotonic=lambda: now[0])):
            pending = asyncio.create_task(self.run_request())
            try:
                await asyncio.wait_for(self.adapters[0].entered.wait(), 2)
                now[0] = 100.020
                result = await asyncio.wait_for(pending, 2)
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        self.assertEqual("failed", result["status"])
        self.assertIn("model-deadline-exhausted", [item["code"] for item in result["diagnostics"]])
        self.assertEqual(1, self.adapters[0].cancelled)
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])
        self.assertIsNone(result["output"])
        self.assertEqual(before, self.request)
        run = self.repository.read(self.request["taskId"])
        assert run is not None
        self.assertTrue(run.terminal)
        terminal_json = run.events[-1].result_json
        assert terminal_json is not None
        self.assertIsNone(json.loads(terminal_json)["output"])
        self.assertEqual(before, json.loads(run.task_json))

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

        self.enterContext(patch.object(self.adapters[0], "health", new=revoke))
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertEqual([0, 0], [adapter.calls for adapter in self.adapters])

    async def test_deadline_elapsed_during_authorization_cannot_dispatch(self):
        now = [100.0]
        after_health = [False]
        assess = self.authority.assess

        async def health():
            after_health[0] = True
            return True

        def delayed_authority(**kwargs):
            result = assess(**kwargs)
            if after_health[0]:
                now[0] += 0.040
            return result

        self.request["requirements"]["deadlineMs"] = 20
        self.enterContext(patch.object(self.adapters[0], "health", new=health))
        self.enterContext(patch.object(self.authority, "assess", new=delayed_authority))
        # Advance only the gateway clock at the actual synchronous boundary;
        # real asyncio scheduling and protected I/O remain unaffected.
        with patch("research_observatory_core.model_routing.time", SimpleNamespace(monotonic=lambda: now[0])):
            result = await self.run_request()
        self.assertEqual("failed", result["status"])
        self.assertEqual("model-deadline-exhausted", result["diagnostics"][0]["code"])
        self.assertEqual([0, 0], [adapter.calls for adapter in self.adapters])

    async def test_completed_output_is_not_replayed_after_permission_revocation(self):
        await self.run_request()
        previous = self.repository.read(self.request["taskId"])
        assert previous is not None
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

        self.enterContext(patch.object(self.adapters[0], "health", new=revoke))
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

        self.enterContext(patch.object(self.adapters[0], "execute", new=revoke))
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertIsNone(result["output"])
        self.assertEqual(0, self.adapters[1].calls)

    async def assert_result_ownership_change_is_not_published(self, change):
        cap = self.charged_authority()[0] if change == "cost" else None
        token = CancellationToken()
        current = [True]
        ownership_reads = []
        authority = self.authority
        execute = self.adapters[0].execute

        class ActiveResult(dict):
            def items(self):
                # Accepted mapping access runs while the gateway owns the raw
                # result, after adapter execution and its initial guards.
                ownership_reads.append(True)
                if change == "cancel":
                    token.cancel()
                elif change == "permission":
                    authority.reason_codes = ("fixture-rights-revoked",)
                elif change == "catalog":
                    current[0] = False
                elif change == "cost":
                    assert cap is not None
                    cap[0] = 0
                return super().items()

        async def active_result(*args, **kwargs):
            return ActiveResult(await execute(*args, **kwargs))

        self.enterContext(patch.object(self.adapters[0], "execute", new=active_result))
        gateway = self.gateway()
        gateway._catalog_is_current = lambda _catalog: current[0]
        result = await self.run_request(gateway, cancellation=token)
        self.assertTrue(ownership_reads)
        self.assertEqual("cancelled" if change == "cancel" else "denied", result["status"])
        self.assertIsNone(result["output"])
        self.assertEqual(
            "model-cancelled" if change == "cancel" else "model-permission-changed",
            result["diagnostics"][0]["code"],
        )
        terminal = self.repository.read(self.request["taskId"])
        assert terminal is not None
        self.assertTrue(terminal.terminal)
        self.assertEqual(self.original, self.request)
        self.assertEqual(self.original, json.loads(terminal.task_json))
        result_json = terminal.events[-1].result_json
        assert result_json is not None
        persisted = json.loads(result_json)
        self.assertEqual(result["status"], persisted["status"])
        self.assertIsNone(persisted["output"])
        self.assertEqual(result, await self.run_request(gateway))
        self.assertEqual(terminal, self.repository.read(terminal.task_id))
        self.assertEqual([1] + [0] * (len(self.adapters) - 1), [adapter.calls for adapter in self.adapters])

    async def test_cancel_during_result_ownership_does_not_publish_or_replay_output(self):
        await self.assert_result_ownership_change_is_not_published("cancel")

    async def test_permission_revocation_during_result_ownership_does_not_publish_or_replay_output(self):
        await self.assert_result_ownership_change_is_not_published("permission")

    async def test_catalog_revocation_during_result_ownership_does_not_publish_or_replay_output(self):
        await self.assert_result_ownership_change_is_not_published("catalog")

    async def test_cost_cap_shrink_during_result_ownership_does_not_publish_or_replay_output(self):
        await self.assert_result_ownership_change_is_not_published("cost")

    async def assert_publication_authority_work_is_guarded(self, change):
        token = CancellationToken()
        now = [100.0]
        armed = [False]
        late_assessments = []
        assess = self.authority.assess
        execute = self.adapters[0].execute

        class ActiveResult(dict):
            def items(self):
                armed[0] = True
                return super().items()

        async def active_result(*args, **kwargs):
            return ActiveResult(await execute(*args, **kwargs))

        def publication_authority(**kwargs):
            permission = assess(**kwargs)
            if armed[0]:
                late_assessments.append(True)
                if change == "cancel":
                    token.cancel()
                else:
                    now[0] += self.request["requirements"]["deadlineMs"] / 1000 + 0.001
            return permission

        self.enterContext(patch.object(self.adapters[0], "execute", new=active_result))
        self.enterContext(patch.object(self.authority, "assess", new=publication_authority))
        # Replace only the gateway module's time reference. The event loop and
        # protected persistence retain their real clocks and execution paths.
        with patch("research_observatory_core.model_routing.time", SimpleNamespace(monotonic=lambda: now[0])):
            result = await self.run_request(cancellation=token)
        self.assertEqual([True], late_assessments)
        self.assertEqual("cancelled" if change == "cancel" else "failed", result["status"])
        self.assertEqual(
            "model-cancelled" if change == "cancel" else "model-deadline-exhausted",
            result["diagnostics"][0]["code"],
        )
        self.assertIsNone(result["output"])
        terminal = self.repository.read(self.request["taskId"])
        assert terminal is not None
        self.assertTrue(terminal.terminal)
        self.assertEqual(self.original, self.request)
        self.assertEqual(self.original, json.loads(terminal.task_json))
        result_json = terminal.events[-1].result_json
        assert result_json is not None
        persisted = json.loads(result_json)
        self.assertEqual(result["status"], persisted["status"])
        self.assertIsNone(persisted["output"])
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])

    async def test_publication_authority_cancellation_does_not_publish_output(self):
        await self.assert_publication_authority_work_is_guarded("cancel")

    async def test_publication_authority_deadline_exhaustion_does_not_publish_output(self):
        await self.assert_publication_authority_work_is_guarded("deadline")

    async def assert_expiry_during_authority_lookup_is_denied(self, witness, stage):
        now = [1500]
        calls = [0]
        owned = [False]
        if witness == "permission":
            self.inventory.observations = tuple(
                item.model_copy(update={"expires_at_ms": 3000}) for item in self.inventory.observations
            )
        else:
            self.authority.expires_at_ms = 3000
        assess = self.authority.assess
        execute = self.adapters[0].execute

        class ActiveResult(dict):
            def items(self):
                owned[0] = True
                return super().items()

        async def active_result(*args, **kwargs):
            return ActiveResult(await execute(*args, **kwargs))

        def delayed_authority(**kwargs):
            permission = assess(**kwargs)
            calls[0] += 1
            if (stage == "dispatch" and calls[0] == 3) or (stage == "publication" and owned[0]):
                now[0] = 2000
            return permission

        gateway = ModelGateway(
            catalog=self.catalog,
            inventory=self.inventory,
            authority=self.authority,
            adapters=self.adapters,
            repository=self.repository,
            clock_ms=lambda: now[0],
        )
        with (
            patch.object(self.authority, "assess", delayed_authority),
            patch.object(self.adapters[0], "execute", active_result),
        ):
            result = await self.run_request(gateway)
        self.assertEqual("denied", result["status"])
        self.assertEqual("model-permission-changed", result["diagnostics"][0]["code"])
        self.assertIsNone(result["output"])
        terminal = self.repository.read(self.request["taskId"])
        assert terminal is not None and terminal.events[-1].result_json is not None
        self.assertEqual(self.original, self.request)
        self.assertEqual(self.original, json.loads(terminal.task_json))
        self.assertTrue(terminal.terminal)
        result_json = terminal.events[-1].result_json
        assert result_json is not None
        persisted = json.loads(result_json)
        self.assertEqual("denied", persisted["status"])
        self.assertIsNone(persisted["output"])
        self.assertEqual([0 if stage == "dispatch" else 1, 0], [adapter.calls for adapter in self.adapters])
        self.assertEqual(result, await self.run_request(gateway))
        self.assertEqual(terminal, self.repository.read(terminal.task_id))

    async def test_permission_expiry_during_dispatch_lookup_prevents_adapter_call(self):
        await self.assert_expiry_during_authority_lookup_is_denied("permission", "dispatch")

    async def test_host_expiry_during_dispatch_lookup_prevents_adapter_call(self):
        await self.assert_expiry_during_authority_lookup_is_denied("inventory", "dispatch")

    async def test_permission_expiry_during_publication_lookup_prevents_output(self):
        await self.assert_expiry_during_authority_lookup_is_denied("permission", "publication")

    async def test_host_expiry_during_publication_lookup_prevents_output(self):
        await self.assert_expiry_during_authority_lookup_is_denied("inventory", "publication")

    async def assert_replay_consumes_unexpired_candidate(self, witness, completed_at):
        now = [1500]
        armed = [False]
        catalog_checks = [0]
        if witness == "permission":
            self.inventory.observations = tuple(
                item.model_copy(update={"expires_at_ms": 3000}) for item in self.inventory.observations
            )
        else:
            self.authority.expires_at_ms = 3000

        def current_catalog(_catalog):
            if armed[0]:
                catalog_checks[0] += 1
                if catalog_checks[0] == 2:
                    now[0] = completed_at
            return True

        gateway = ModelGateway(
            catalog=self.catalog,
            inventory=self.inventory,
            authority=self.authority,
            adapters=self.adapters,
            repository=self.repository,
            clock_ms=lambda: now[0],
            catalog_is_current=current_catalog,
        )
        result = await self.run_request(gateway)
        self.assertEqual("succeeded", result["status"])
        terminal = self.repository.read(self.request["taskId"])
        assert terminal is not None
        armed[0] = True
        replay = await self.run_request(gateway)
        self.assertEqual(2, catalog_checks[0])
        if completed_at < 2000:
            self.assertEqual(result, replay)
        else:
            self.assertEqual("denied", replay["status"])
            self.assertEqual("model-permission-changed", replay["diagnostics"][0]["code"])
            self.assertIsNone(replay["output"])
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])
        self.assertEqual(terminal, self.repository.read(terminal.task_id))
        self.assertEqual(self.original, self.request)

    async def test_permission_expiry_during_replay_catalog_check_denies_without_rewriting_history(self):
        await self.assert_replay_consumes_unexpired_candidate("permission", 2000)

    async def test_host_expiry_during_replay_catalog_check_denies_without_rewriting_history(self):
        await self.assert_replay_consumes_unexpired_candidate("inventory", 2000)

    async def test_unexpired_replay_after_catalog_check_still_succeeds(self):
        await self.assert_replay_consumes_unexpired_candidate("permission", 1999)

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
        assert run is not None
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

    def charged_authority(self):
        charged = self.manifest.model_copy(update={"cost_microunits_per_thousand_tokens": 1})
        self.catalog = self.catalog.model_copy(update={"manifests": (charged,)})
        self.inventory = FixtureInventory((charged,))
        self.adapters = (FixtureAdapter(charged),)
        limits = self.request["requirements"]
        one_attempt = (limits["maxInputTokens"] + limits["maxOutputTokens"] + 999) // 1000
        cap = [one_attempt]
        assess = self.authority.assess
        self.enterContext(
            patch.object(
                self.authority,
                "assess",
                new=lambda **kwargs: assess(**kwargs).model_copy(update={"maximum_cost_microunits": cap[0]}),
            )
        )
        return cap, one_attempt

    async def test_permission_budget_is_cumulative_across_retry(self):
        _cap, one_attempt = self.charged_authority()
        self.adapters[0].outcomes = [ModelAdapterFailure("rate-limited", retryable=True)]
        result = await self.run_request()
        self.assertEqual(1, self.adapters[0].calls)
        self.assertEqual("model-cost-budget-exhausted", result["diagnostics"][0]["code"])
        run = self.repository.read(self.request["taskId"])
        assert run is not None
        attempts = [e for e in run.events if e.kind == "attempt-started"]
        self.assertEqual([one_attempt], [e.effective_cost_limit_microunits for e in attempts])

    async def test_shrinking_permission_after_health_cannot_dispatch(self):
        cap, _cost = self.charged_authority()

        async def shrink():
            cap[0] = 0
            return True

        self.enterContext(patch.object(self.adapters[0], "health", new=shrink))
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertEqual(0, self.adapters[0].calls)

    async def test_permission_budget_is_cumulative_across_fallback(self):
        self.charged_authority()
        alternate = self.alternate.model_copy(update={"cost_microunits_per_thousand_tokens": 1})
        self.catalog = self.catalog.model_copy(update={"manifests": (*self.catalog.manifests, alternate)})
        self.inventory = FixtureInventory(self.catalog.manifests)
        self.adapters = (*self.adapters, FixtureAdapter(alternate))
        self.adapters[0].outcomes = [ModelAdapterFailure("rate-limited", retryable=True)]
        self.policy = self.policy.model_copy(update={"maximum_retries_per_route": 0})
        result = await self.run_request()
        self.assertEqual([1, 0], [adapter.calls for adapter in self.adapters])
        self.assertEqual("model-cost-budget-exhausted", result["diagnostics"][0]["code"])

    async def test_second_health_cannot_reduce_budget_below_prior_reservations(self):
        cap, cost = self.charged_authority()
        cap[0] = 2 * cost
        self.adapters[0].outcomes = [ModelAdapterFailure("rate-limited", retryable=True)]

        async def shrink():
            if self.adapters[0].calls:
                cap[0] = cost
            return True

        self.enterContext(patch.object(self.adapters[0], "health", new=shrink))
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertEqual(1, self.adapters[0].calls)

    async def test_shrinking_permission_after_retry_output_is_not_promoted_or_replayed(self):
        cap, cost = self.charged_authority()
        cap[0] = 2 * cost
        self.adapters[0].outcomes = [ModelAdapterFailure("rate-limited", retryable=True)]
        execute = self.adapters[0].execute

        async def shrink(*args, **kwargs):
            result = await execute(*args, **kwargs)
            cap[0] = cost  # Still enough per attempt, but not for both reservations.
            return result

        self.enterContext(patch.object(self.adapters[0], "execute", new=shrink))
        result = await self.run_request()
        self.assertEqual(2, self.adapters[0].calls)
        self.assertEqual("denied", result["status"])
        self.assertIsNone(result["output"])
        self.assertEqual(result, await self.run_request())

    async def test_successful_retry_replay_requires_current_total_budget(self):
        cap, cost = self.charged_authority()
        cap[0] = 2 * cost
        self.adapters[0].outcomes = [ModelAdapterFailure("rate-limited", retryable=True)]
        self.assertEqual("succeeded", (await self.run_request())["status"])
        original = self.repository.read(self.request["taskId"])
        assert original is not None
        tampered = original.model_dump(by_alias=True, mode="json")
        # Even mutually consistent route/attempt caps cannot erase prior cost.
        latest_routes = next(e for e in reversed(tampered["events"]) if e["kind"] == "routes")
        latest_routes["resolution"]["eligible"][0]["maximumCostMicrounits"] = cost
        latest_attempt = next(e for e in reversed(tampered["events"]) if e["kind"] == "attempt-started")
        latest_attempt["effectiveCostLimitMicrounits"] = cost
        with self.assertRaisesRegex(ValueError, "cumulative cost"):
            RoutingRun.model_validate(tampered)
        cap[0] = cost
        result = await self.run_request()
        self.assertEqual("denied", result["status"])
        self.assertIsNone(result["output"])
        self.assertEqual(2, self.adapters[0].calls)
        self.assertEqual(original, self.repository.read(self.request["taskId"]))

    async def test_null_permission_cap_does_not_waive_routing_limit(self):
        cap, cost = self.charged_authority()
        cap[0] = None
        self.policy = self.policy.model_copy(update={"maximum_cost_microunits": cost})
        self.adapters[0].outcomes = [ModelAdapterFailure("rate-limited", retryable=True)]
        result = await self.run_request()
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
        assert run is not None
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

        self.enterContext(patch.object(self.adapters[0], "execute", new=stubborn))
        token = CancellationToken()
        pending = asyncio.create_task(self.run_request(cancellation=token))
        await self.adapters[0].entered.wait()
        token.cancel()
        result = await asyncio.wait_for(pending, 0.1)
        self.assertEqual("cancelled", result["status"])
        terminal = self.repository.read(self.request["taskId"])
        assert terminal is not None
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
        gateway = ModelGateway(
            catalog=self.catalog,
            inventory=self.inventory,
            authority=self.authority,
            adapters=self.adapters,
            repository=self.repository,
            clock_ms=lambda: 2600,
        )
        # Cooldown expiry does not renew the permission or host witnesses.
        self.assertEqual("denied", (await self.run_request(gateway))["status"])
        self.assertEqual(1, self.adapters[0].calls)
        self.authority.expires_at_ms = 4000
        self.inventory.observations = tuple(
            item.model_copy(update={"observed_at_ms": 2500, "expires_at_ms": 4000})
            for item in self.inventory.observations
        )
        self.request["taskId"] = new_uuid_v7()
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

        self.enterContext(patch.object(self.adapters[0], "cancel", new=slow_cancel))
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
