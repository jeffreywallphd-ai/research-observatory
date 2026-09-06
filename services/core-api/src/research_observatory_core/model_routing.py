"""Bounded, policy-reauthorized model routing over provider-neutral ports."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any, cast

from .domain_contracts import new_uuid_v7
from .model_gateway_contracts import ModelResultSnapshot, ModelTaskSnapshot, decode_model_result, decode_model_task
from .model_registry import ModelRegistry
from .model_registry_contracts import (
    ModelEligibilityCandidate,
    ModelManifest,
    ModelRegistryCatalog,
    canonical_bytes,
    canonical_hash,
)
from .model_routing_contracts import (
    CancellationToken,
    CircuitState,
    RoutingEvent,
    RoutingPolicy,
    RoutingRun,
    input_references,
    routing_contract_scope,
)
from .ports.model_gateway import ModelAdapter, ModelAdapterFailure, ModelRoutingRepository
from .ports.model_registry import ModelEligibilityPolicy, ModelInventory


class _Interrupted(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


class _ExistingRun(Exception):
    def __init__(self, run: RoutingRun) -> None:
        self.run = run


@dataclass
class _CircuitReservation:
    repository: ModelRoutingRepository
    circuit: CircuitState
    leased: CircuitState
    policy: RoutingPolicy
    clock_ms: Callable[[], int]
    trace_id: str
    failed: bool = False
    released: bool = False
    execution_stopped: bool = True

    def release(self) -> None:
        if self.released or not self.execution_stopped:
            return
        failures = min(10, self.circuit.failures + 1) if self.failed else 0
        self.repository.change_circuit(
            CircuitState(
                manifest_hash=self.leased.manifest_hash,
                trace_id=self.trace_id,
                revision=self.leased.revision + 1,
                failures=failures,
                open_until_ms=self.clock_ms() + self.policy.circuit_cooldown_ms
                if failures >= self.policy.circuit_failure_threshold
                else 0,
            ),
            expected_revision=self.leased.revision,
            expected_attempt_id=self.leased.active_attempt_id,
        )
        self.released = True


def _failure(
    task: ModelTaskSnapshot, code: str, *, elapsed_ms: int, cancelled: bool = False, denied: bool = False
) -> ModelResultSnapshot:
    requirements = cast(Mapping[str, Any], task["requirements"])
    value: dict[str, Any] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-model-result",
        "contractVersion": "1.0.0",
        **{key: task[key] for key in ("taskId", "taskKind", "requestHash", "traceId")},
        "status": "cancelled" if cancelled else "denied" if denied else "failed",
        "route": {
            "selection": "none",
            "reasonCode": code,
            **dict.fromkeys(
                (
                    "providerId",
                    "providerVersion",
                    "modelId",
                    "modelVersion",
                    "runtimeId",
                    "runtimeVersion",
                    "configurationHash",
                    "evaluationId",
                    "evaluationVersion",
                )
            ),
        },
        "policyDecision": {
            "decisionId": new_uuid_v7(),
            "policyVersion": "1.0.0",
            "outcome": "denied",
            "reasonCodes": [code],
        },
        "latency": {"queueMs": 0, "executionMs": 0, "totalMs": min(elapsed_ms, 86_400_000)},
        "usage": {"reporting": "not-reported", "inputTokens": None, "outputTokens": None, "totalTokens": None},
        "validation": {"outcome": "not-run", "validatorVersion": "1.0.0", "outputHash": None, "errorCodes": []},
        "confidence": {"kind": "not-reported"},
        "citationStatus": "not-applicable"
        if requirements["citationRequirement"] == "not-applicable"
        else "not-supplied",
        "citations": [],
        "output": None,
        "diagnostics": [{"code": code, "retryable": False, "partialOutputDisposition": "discarded"}],
    }
    result = decode_model_result(task, value)
    if result is None:
        raise ValueError("gateway failure contract is invalid")
    return result


def _consume_completion(pending: asyncio.Task[object]) -> None:
    if not pending.cancelled():
        pending.exception()


class ModelGateway:
    def __init__(
        self,
        *,
        catalog: ModelRegistryCatalog,
        inventory: ModelInventory,
        authority: ModelEligibilityPolicy,
        adapters: tuple[ModelAdapter, ...],
        repository: ModelRoutingRepository,
        catalog_is_current: Callable[[ModelRegistryCatalog], bool] | None = None,
        clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    ) -> None:
        self._catalog = ModelRegistryCatalog.model_validate(catalog)
        self._registry = ModelRegistry(inventory, authority, clock_ms=clock_ms)
        if not isinstance(adapters, tuple) or len(adapters) > 1000:
            raise ValueError("adapter inventory is invalid")
        self._adapters: dict[str, ModelAdapter] = {}
        for adapter in adapters:
            digest = canonical_hash(ModelManifest.model_validate(adapter.describe()))
            if digest in self._adapters:
                raise ValueError("adapter identity is ambiguous")
            self._adapters[digest] = adapter
        self._repository = repository
        self._catalog_is_current = catalog_is_current
        self._clock_ms = clock_ms
        self._session_id = new_uuid_v7()

    def recover_interrupted(self, task_id: str, *, expected_revision: int) -> RoutingRun:
        """Core-owner recovery: fence late writes, never repeat an ambiguous call.

        This is journal disposition, not job scheduling or proof a provider did
        not execute. A reserved circuit stays reserved until the original call
        ends or a future supervised-runtime recovery proves it stopped.
        """
        run = self._repository.read(task_id)
        if run is None or run.revision != expected_revision or run.terminal:
            raise ValueError("routing recovery predecessor differs")
        task = decode_model_task(json.loads(run.task_json))
        if task is None:
            raise ValueError("routing recovery request is invalid")
        result = _failure(task, "model-prior-execution-uncertain", elapsed_ms=run.events[-1].elapsed_ms)
        return self._repository.append(
            task_id,
            expected_revision=expected_revision,
            event=RoutingEvent(
                event_id=new_uuid_v7(),
                kind="interrupted",
                occurred_at_ms=max(self._clock_ms(), run.events[-1].occurred_at_ms),
                attempt_number=max(event.attempt_number for event in run.events),
                elapsed_ms=run.events[-1].elapsed_ms,
                reason_codes=("model-prior-execution-uncertain",),
                result_json=canonical_bytes(result).decode(),
            ),
        )

    def _same_authority(self, candidate: ModelEligibilityCandidate, task: ModelTaskSnapshot) -> bool:
        selected_catalog = ModelRegistryCatalog(
            project_id=self._catalog.project_id,
            revision=self._catalog.revision,
            manifests=tuple(
                item for item in self._catalog.manifests if canonical_hash(item) == candidate.manifest_hash
            ),
        )
        return self._current_catalog() and any(
            (item.manifest_hash, item.policy_revision, item.rights_revision)
            == (candidate.manifest_hash, candidate.policy_revision, candidate.rights_revision)
            for item in self._registry.resolve(selected_catalog, task).eligible
        )

    def _current_catalog(self) -> bool:
        # An unbound fixture uses its immutable snapshot. Core composition must
        # supply the guarded persisted-catalog check for a live project.
        return self._catalog_is_current is None or self._catalog_is_current(self._catalog)

    async def execute(
        self,
        task_spec: object,
        input_refs: object,
        policy: RoutingPolicy,
        cancel_token: CancellationToken,
    ) -> ModelResultSnapshot:
        started = time.monotonic()
        with routing_contract_scope(), self._repository.session():
            try:
                return await self._execute(task_spec, input_refs, policy, cancel_token, started=started)
            except _ExistingRun as existing:
                return self._replay(existing.run)

    def _replay(self, run: RoutingRun) -> ModelResultSnapshot:
        if not run.terminal:
            # A fresh process cannot know whether the previous provider call ran.
            raise ValueError("model run is already admitted; recovery is required")
        task = decode_model_task(json.loads(run.task_json))
        result = decode_model_result(task, json.loads(cast(str, run.events[-1].result_json)))
        if task is None or result is None:
            raise ValueError("persisted model result is invalid")
        if result["status"] in {"succeeded", "degraded"}:
            active = next(event for event in reversed(run.events) if event.kind == "attempt-started")
            current = self._registry.resolve(self._catalog, task)
            candidate = next(
                (
                    item
                    for item in current.eligible
                    if (item.manifest_hash, item.policy_revision, item.rights_revision)
                    == (active.manifest_hash, active.policy_revision, active.rights_revision)
                ),
                None,
            )
            if not self._current_catalog() or candidate is None:
                return _failure(task, "model-permission-changed", elapsed_ms=0, denied=True)
        return result

    async def _execute(
        self,
        task_spec: object,
        input_refs: object,
        policy: RoutingPolicy,
        cancel_token: CancellationToken,
        *,
        started: float,
    ) -> ModelResultSnapshot:
        task = decode_model_task(task_spec)
        policy = RoutingPolicy.model_validate(policy)
        if (
            task is None
            or policy.project_id != self._catalog.project_id
            or not isinstance(cancel_token, CancellationToken)
        ):
            raise ValueError("gateway request authority is invalid")
        references = input_references(task)
        if canonical_bytes(input_refs) != canonical_bytes(references):
            raise ValueError("gateway input references differ from the task")
        start = started
        requirements = cast(Mapping[str, Any], task["requirements"])
        deadline = start + requirements["deadlineMs"] / 1000
        request = RoutingRun(
            project_id=policy.project_id,
            task_id=cast(str, task["taskId"]),
            task_hash=canonical_hash(task),
            task_json=canonical_bytes(task).decode(),
            policy=policy,
            session_id=self._session_id,
            events=(RoutingEvent(event_id=new_uuid_v7(), kind="admitted", occurred_at_ms=self._clock_ms()),),
        )
        first_resolution = self._registry.resolve(self._catalog, task)
        run = request
        needs_admission = True
        attempts = 0
        spent = 0
        used: dict[str, int] = {}
        first_hash: str | None = None
        release: Callable[[], None] | None = None

        def elapsed() -> int:
            return max(0, int((time.monotonic() - start) * 1000))

        def emit(kind: Any, **fields: Any) -> None:
            nonlocal run
            event = RoutingEvent(
                event_id=new_uuid_v7(),
                kind=kind,
                occurred_at_ms=self._clock_ms(),
                attempt_number=attempts,
                elapsed_ms=elapsed(),
                **fields,
            )
            run = self._repository.append(run.task_id, expected_revision=run.revision, event=event)

        def ensure_admitted() -> None:
            nonlocal run, needs_admission
            if not needs_admission:
                return
            run, admitted = self._repository.admit(request)
            if not admitted:
                raise _ExistingRun(run)
            needs_admission = False
            # Admission, alternatives and first attempt (or immediate denial)
            # share one durable pre-dispatch transaction, never an adapter await.
            event = RoutingEvent(
                event_id=new_uuid_v7(),
                kind="routes",
                occurred_at_ms=self._clock_ms(),
                resolution=first_resolution,
            )
            run = self._repository.append(run.task_id, expected_revision=run.revision, event=event)

        def finish(result: ModelResultSnapshot) -> ModelResultSnapshot:
            with self._repository.atomic():
                ensure_admitted()
                emit("completed", result_json=canonical_bytes(result).decode())
                if release is not None:
                    release()
            return result

        def fail(code: str, *, denied: bool = False) -> ModelResultSnapshot:
            return finish(
                _failure(task, code, elapsed_ms=elapsed(), cancelled=code == "model-cancelled", denied=denied)
            )

        while attempts < policy.maximum_attempts:
            if cancel_token.is_cancelled():
                return fail("model-cancelled")
            if time.monotonic() >= deadline:
                return fail("model-deadline-exhausted")
            if not self._current_catalog():
                return fail("model-catalog-changed", denied=True)
            resolution = first_resolution if attempts == 0 else self._registry.resolve(self._catalog, task)
            if attempts:
                emit("routes", resolution=resolution)
            if not resolution.eligible:
                return fail("model-permission-or-capability-denied", denied=True)
            preference = {key: index for index, key in enumerate(policy.preferred_manifest_ids)}
            manifests = {canonical_hash(item): item for item in self._catalog.manifests}
            candidates = sorted(resolution.eligible, key=lambda item: preference.get(item.manifest_id, len(preference)))
            selected = None
            skipped_reason = "model-attempt-budget-exhausted"
            for candidate in candidates:
                manifest = manifests[candidate.manifest_hash]
                if manifest.deployment not in policy.permitted_deployments:
                    skipped_reason = "model-egress-denied"
                    continue
                if used.get(candidate.manifest_hash, 0) > policy.maximum_retries_per_route:
                    continue
                adapter = self._adapters.get(candidate.manifest_hash)
                if (
                    adapter is None
                    or canonical_hash(ModelManifest.model_validate(adapter.describe())) != candidate.manifest_hash
                ):
                    skipped_reason = "model-adapter-unavailable"
                    continue
                cost = manifest.cost_microunits_per_thousand_tokens
                if cost is None:
                    skipped_reason = "model-cost-unknown"
                    continue
                reserved = (cost * (requirements["maxInputTokens"] + requirements["maxOutputTokens"]) + 999) // 1000
                if spent + reserved > policy.maximum_cost_microunits:
                    skipped_reason = "model-cost-budget-exhausted"
                    continue
                circuit = self._repository.circuit(candidate.manifest_hash)
                if circuit.active_attempt_id is not None or circuit.open_until_ms > self._clock_ms():
                    skipped_reason = "model-circuit-open"
                    continue
                selected = candidate, manifest, adapter, reserved, circuit
                break
            if selected is None:
                return fail(skipped_reason, denied=skipped_reason == "model-egress-denied")
            candidate, manifest, adapter, reserved, circuit = selected
            attempt_id = new_uuid_v7()
            attempts += 1
            used[candidate.manifest_hash] = used.get(candidate.manifest_hash, 0) + 1
            spent += reserved
            if first_hash is None:
                first_hash = candidate.manifest_hash
            with self._repository.atomic():
                ensure_admitted()
                leased = self._repository.change_circuit(
                    CircuitState.model_validate(
                        circuit.model_dump()
                        | {
                            "revision": circuit.revision + 1,
                            "active_attempt_id": attempt_id,
                            "trace_id": task["traceId"],
                        }
                    ),
                    expected_revision=circuit.revision,
                )
                emit(
                    "attempt-started",
                    attempt_id=attempt_id,
                    manifest_hash=candidate.manifest_hash,
                    manifest=manifest,
                    policy_revision=candidate.policy_revision,
                    rights_revision=candidate.rights_revision,
                    reserved_cost_microunits=reserved,
                )
            reservation = _CircuitReservation(
                self._repository, circuit, leased, policy, self._clock_ms, cast(str, task["traceId"])
            )
            release = reservation.release
            try:
                raw = await self._invoke(
                    adapter,
                    task,
                    references,
                    attempt_id,
                    cancel_token,
                    min(deadline, time.monotonic() + policy.attempt_timeout_ms / 1000),
                    partial(self._same_authority, candidate, task),
                    candidate.manifest_hash,
                    reservation,
                )
                if cancel_token.is_cancelled():
                    raise _Interrupted("model-cancelled")
                if time.monotonic() >= deadline:
                    raise _Interrupted("model-deadline-exhausted")
                if not self._same_authority(candidate, task):
                    return fail("model-permission-changed", denied=True)
                result = decode_model_result(task, raw)
                if result is None or result["route"] != {"selection": "selected"} | manifest.identity.model_dump(
                    by_alias=True
                ):
                    raise ModelAdapterFailure("output-invalid", retryable=False)
                if result["status"] not in {"succeeded", "degraded"}:
                    raise ModelAdapterFailure("runtime-failed", retryable=False)
                owned = json.loads(canonical_bytes(result))
                owned["policyDecision"] = {
                    "decisionId": attempt_id,
                    "policyVersion": "1.0.0",
                    "outcome": "allowed",
                    "reasonCodes": ["model-current-policy-allowed"],
                }
                owned["latency"] = {"queueMs": 0, "executionMs": elapsed(), "totalMs": elapsed()}
                if candidate.manifest_hash != first_hash:
                    owned["status"] = "degraded"
                    owned["diagnostics"].append(
                        {"code": "model-route-fallback", "retryable": False, "partialOutputDisposition": "none"}
                    )
                validated = decode_model_result(task, owned)
                if validated is None:
                    raise ModelAdapterFailure("output-invalid", retryable=False)
                return finish(validated)
            except _Interrupted as error:
                return fail(error.code, denied=error.code == "model-permission-changed")
            except ModelAdapterFailure as error:
                reservation.failed = True
                emit(
                    "attempt-failed",
                    attempt_id=attempt_id,
                    manifest_hash=candidate.manifest_hash,
                    reason_codes=(error.code,),
                )
                if not error.retryable:
                    return fail("model-" + error.code)
                if time.monotonic() >= deadline:
                    return fail("model-deadline-exhausted")
                emit("retry", reason_codes=("model-retry-within-budget",))
                pause_until = min(
                    deadline, time.monotonic() + policy.initial_backoff_ms * used[candidate.manifest_hash] / 1000
                )
                while time.monotonic() < pause_until and not cancel_token.is_cancelled():
                    await asyncio.sleep(min(0.01, pause_until - time.monotonic()))
            except asyncio.CancelledError:
                cancel_token.cancel()
                return fail("model-cancelled")
            finally:
                reservation.release()
        return fail("model-attempt-budget-exhausted")

    async def _invoke(
        self,
        adapter: ModelAdapter,
        task: ModelTaskSnapshot,
        references: tuple[Mapping[str, Any], ...],
        attempt_id: str,
        token: CancellationToken,
        deadline: float,
        authorized: Callable[[], bool],
        expected_manifest_hash: str,
        reservation: _CircuitReservation,
    ) -> object:
        async def work() -> object:
            try:
                if await adapter.health() is not True:
                    raise ModelAdapterFailure("temporarily-unavailable", retryable=True)
                if not authorized():
                    raise _Interrupted("model-permission-changed")
                if canonical_hash(ModelManifest.model_validate(adapter.describe())) != expected_manifest_hash:
                    raise ModelAdapterFailure("runtime-failed", retryable=False)
                if token.is_cancelled():
                    raise _Interrupted("model-cancelled")
                return await adapter.execute(task, references, attempt_id=attempt_id, cancel_token=token)
            except ModelAdapterFailure, _Interrupted:
                raise
            except Exception:
                raise ModelAdapterFailure("runtime-failed", retryable=False) from None

        pending = asyncio.create_task(work())
        reservation.execution_stopped = False
        try:
            while not pending.done():
                if token.is_cancelled():
                    raise _Interrupted("model-cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ModelAdapterFailure("provider-timeout", retryable=True)
                await asyncio.wait({pending}, timeout=min(0.01, remaining))
            return pending.result()
        finally:
            if not pending.done():
                pending.cancel()
                pending.add_done_callback(_consume_completion)
                cancellation = asyncio.create_task(adapter.cancel(attempt_id))
                await asyncio.wait({cancellation}, timeout=0.02)
                if not cancellation.done():
                    cancellation.cancel()
                cancellation.add_done_callback(_consume_completion)
            # Cancellation acknowledgement is not a provider-stop attestation.
            # Leave an unresponsive attempt reserved for supervised recovery;
            # its late output is consumed, never promoted or used as authority.
            reservation.execution_stopped = pending.done()
