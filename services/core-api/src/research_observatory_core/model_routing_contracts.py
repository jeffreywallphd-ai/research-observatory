"""Owned routing policy, bounded audit records and cooperative cancellation."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Self, cast

from pydantic import Field, model_validator

from .model_gateway_contracts import (
    ModelTaskSnapshot,
    _model_task_decode_scope,
    decode_model_result,
    decode_model_task,
)
from .model_registry_contracts import (
    ModelDeployment,
    ModelManifest,
    ModelRegistryResolution,
    RegistryCode,
    RegistryHash,
    RegistryModel,
    RegistryTime,
    RegistryUuid,
    canonical_bytes,
    canonical_hash,
)


@dataclass
class _TaskDecodeMemo:
    owner_thread: int = field(default_factory=threading.get_ident)
    active: bool = True
    text: str | None = None
    snapshot: ModelTaskSnapshot | None = None


_TASK_DECODE_MEMO: ContextVar[_TaskDecodeMemo | None] = ContextVar("routing-task-decode", default=None)


@contextmanager
def routing_contract_scope():
    """Reuse pure task decoding within one call, never permission or history.

    Retain at most one small exact-text task. Clear even inherited contexts when
    the invocation ends; no global cache can retain project data after closure.
    """
    memo = _TaskDecodeMemo()
    token = _TASK_DECODE_MEMO.set(memo)
    try:
        with _model_task_decode_scope():
            yield
    finally:
        memo.active = False
        memo.text = None
        memo.snapshot = None
        _TASK_DECODE_MEMO.reset(token)


def _canonical_task(text: str) -> ModelTaskSnapshot:
    memo = _TASK_DECODE_MEMO.get()
    if memo is not None and memo.owner_thread != threading.get_ident():
        memo = None
    if memo is not None and memo.active and memo.text == text and memo.snapshot is not None:
        return memo.snapshot
    task = decode_model_task(json.loads(text))
    if task is None or canonical_bytes(task).decode() != text:
        raise ValueError("routing task bytes are invalid")
    if memo is not None and memo.active and len(text) <= 64_000:
        memo.text, memo.snapshot = text, task
    return task


class RoutingPolicy(RegistryModel):
    """Core-owned constraints; never a caller-supplied authorization grant."""

    schema_version: Literal["1.0"] = "1.0"
    project_id: Annotated[str, Field(min_length=1, max_length=128)]
    revision: Annotated[int, Field(strict=True, ge=1, le=2**31 - 1)]
    permitted_deployments: tuple[ModelDeployment, ...] = ("local",)
    preferred_manifest_ids: Annotated[tuple[RegistryCode, ...], Field(max_length=1000)] = ()
    maximum_attempts: Annotated[int, Field(strict=True, ge=1, le=8)] = 3
    maximum_retries_per_route: Annotated[int, Field(strict=True, ge=0, le=2)] = 1
    initial_backoff_ms: Annotated[int, Field(strict=True, ge=0, le=1000)] = 10
    attempt_timeout_ms: Annotated[int, Field(strict=True, ge=1, le=300_000)] = 30_000
    maximum_cost_microunits: Annotated[int, Field(strict=True, ge=0, le=10**12)] = 0
    circuit_failure_threshold: Annotated[int, Field(strict=True, ge=1, le=10)] = 3
    circuit_cooldown_ms: Annotated[int, Field(strict=True, ge=100, le=60_000)] = 1000

    @model_validator(mode="after")
    def sets_are_bounded(self) -> Self:
        if self.permitted_deployments != tuple(sorted(set(self.permitted_deployments))):
            raise ValueError("routing deployments must be sorted and unique")
        if len(set(self.preferred_manifest_ids)) != len(self.preferred_manifest_ids):
            raise ValueError("routing preferences must be unique")
        return self

    def cost_limit(self, permission_cap: int | None) -> int:
        """Restrictions can narrow, never enlarge, the current witness cap."""
        return (
            self.maximum_cost_microunits
            if permission_cap is None
            else min(self.maximum_cost_microunits, permission_cap)
        )


class RoutingEvent(RegistryModel):
    event_id: RegistryUuid
    kind: Literal["admitted", "routes", "attempt-started", "attempt-failed", "retry", "completed", "interrupted"]
    occurred_at_ms: RegistryTime
    attempt_number: Annotated[int, Field(strict=True, ge=0, le=8)] = 0
    attempt_id: RegistryUuid | None = None
    manifest_hash: RegistryHash | None = None
    manifest: ModelManifest | None = None
    policy_revision: RegistryCode | None = None
    rights_revision: RegistryCode | None = None
    reason_codes: Annotated[tuple[RegistryCode, ...], Field(max_length=64)] = ()
    elapsed_ms: Annotated[int, Field(strict=True, ge=0, le=86_400_000)] = 0
    reserved_cost_microunits: Annotated[int, Field(strict=True, ge=0, le=10**12)] = 0
    effective_cost_limit_microunits: Annotated[int, Field(strict=True, ge=0, le=10**12)] | None = None
    resolution: ModelRegistryResolution | None = None
    result_json: Annotated[str, Field(max_length=8_000_000)] | None = None

    @model_validator(mode="after")
    def event_fields_match_kind(self) -> Self:
        if self.kind != "attempt-started" and (
            self.manifest is not None
            or self.policy_revision is not None
            or self.rights_revision is not None
            or self.reserved_cost_microunits != 0
            or self.effective_cost_limit_microunits is not None
        ):
            raise ValueError("only an attempt may carry dispatch authority")
        if self.kind not in {"attempt-started", "attempt-failed"} and (
            self.attempt_id is not None or self.manifest_hash is not None
        ):
            raise ValueError("routing event carries an unrelated attempt identity")
        if self.kind != "routes" and self.resolution is not None:
            raise ValueError("only route evaluation carries alternatives")
        if self.kind == "admitted" and (self.attempt_number != 0 or self.elapsed_ms != 0 or self.reason_codes):
            raise ValueError("admission cannot claim an executed attempt")
        if self.kind == "attempt-failed" and len(self.reason_codes) != 1:
            raise ValueError("attempt failure requires one classified reason")
        return self


class RoutingRun(RegistryModel):
    project_id: Annotated[str, Field(min_length=1, max_length=128)]
    task_id: RegistryUuid
    task_hash: RegistryHash
    task_json: Annotated[str, Field(max_length=8_000_000)]
    policy: RoutingPolicy
    session_id: RegistryUuid
    events: Annotated[tuple[RoutingEvent, ...], Field(min_length=1, max_length=64)]

    @property
    def revision(self) -> int:
        return len(self.events)

    @property
    def terminal(self) -> bool:
        return self.events[-1].kind in {"completed", "interrupted"}

    @model_validator(mode="after")
    def validate_history(self) -> Self:
        task = _canonical_task(self.task_json)
        if (
            self.task_hash != "sha256:" + hashlib.sha256(self.task_json.encode()).hexdigest()
            or self.task_id != task["taskId"]
            or self.project_id != self.policy.project_id
            or self.events[0].kind != "admitted"
        ):
            raise ValueError("routing request authority is invalid")
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError("routing event identities repeat")
        previous_attempt = 0
        active: RoutingEvent | None = None
        resolution: ModelRegistryResolution | None = None
        spent = 0
        attempt_ids: set[str] = set()
        attempts_by_manifest: dict[str, int] = {}
        for index, event in enumerate(self.events):
            if index and event.kind == "admitted":
                raise ValueError("routing admission repeats")
            if index and event.occurred_at_ms < self.events[index - 1].occurred_at_ms:
                raise ValueError("routing time moved backwards")
            if event.kind == "attempt-started":
                if (
                    event.attempt_number != previous_attempt + 1
                    or event.attempt_id is None
                    or event.manifest_hash is None
                ):
                    raise ValueError("routing attempt sequence is invalid")
                if active is not None or event.attempt_id in attempt_ids or event.manifest is None:
                    raise ValueError("routing attempt authority is incomplete")
                if (
                    canonical_hash(event.manifest) != event.manifest_hash
                    or resolution is None
                    or not any(
                        (item.manifest_hash, item.policy_revision, item.rights_revision)
                        == (event.manifest_hash, event.policy_revision, event.rights_revision)
                        and event.effective_cost_limit_microunits
                        == self.policy.cost_limit(item.maximum_cost_microunits)
                        for item in resolution.eligible
                    )
                ):
                    raise ValueError("routing attempt lacks eligible manifest authority")
                cost = event.manifest.cost_microunits_per_thousand_tokens
                requirements = cast(Mapping[str, Any], task["requirements"])
                if (
                    cost is None
                    or event.reserved_cost_microunits
                    != (cost * (int(requirements["maxInputTokens"]) + int(requirements["maxOutputTokens"])) + 999)
                    // 1000
                ):
                    raise ValueError("routing cost reservation is invalid")
                spent += event.reserved_cost_microunits
                if event.effective_cost_limit_microunits is None or spent > event.effective_cost_limit_microunits:
                    raise ValueError("routing cumulative cost exceeds current permission")
                attempts_by_manifest[event.manifest_hash] = attempts_by_manifest.get(event.manifest_hash, 0) + 1
                if event.manifest.deployment not in self.policy.permitted_deployments or (
                    attempts_by_manifest[event.manifest_hash] > self.policy.maximum_retries_per_route + 1
                ):
                    raise ValueError("routing attempt exceeds policy")
                attempt_ids.add(event.attempt_id)
                active = event
                previous_attempt = event.attempt_number
            elif event.attempt_number > previous_attempt:
                raise ValueError("routing event precedes its attempt")
            if event.kind == "attempt-failed":
                if active is None or (event.attempt_id, event.manifest_hash, event.attempt_number) != (
                    active.attempt_id,
                    active.manifest_hash,
                    active.attempt_number,
                ):
                    raise ValueError("routing failure has no matching active attempt")
                active = None
            if event.kind == "retry" and (index == 0 or self.events[index - 1].kind != "attempt-failed"):
                raise ValueError("routing retry has no failed predecessor")
            if event.resolution is not None and (
                event.resolution.project_id != self.project_id or event.resolution.task_hash != self.task_hash
            ):
                raise ValueError("routing alternatives have different authority")
            if event.kind == "routes":
                if active is not None:
                    raise ValueError("routing cannot reselect during an active attempt")
                resolution = event.resolution
            if event.kind in {"completed", "interrupted"}:
                if index != len(self.events) - 1 or event.result_json is None:
                    raise ValueError("terminal routing record is incomplete")
            elif event.result_json is not None:
                raise ValueError("nonterminal routing record carries a result")
            if event.result_json is not None:
                value = json.loads(event.result_json)
                if decode_model_result(task, value) is None or canonical_bytes(value).decode() != event.result_json:
                    raise ValueError("routing result is invalid")
                if event.kind == "interrupted" and (
                    value["status"] != "failed"
                    or value["output"] is not None
                    or value["diagnostics"][0]["code"] != "model-prior-execution-uncertain"
                ):
                    raise ValueError("interrupted routing cannot claim a known result")
                if value["status"] in {"succeeded", "degraded"} and (
                    active is None
                    or active.manifest is None
                    or value["route"]
                    != {
                        "selection": "selected",
                        **active.manifest.identity.model_dump(by_alias=True),
                    }
                    or value["policyDecision"]["decisionId"] != active.attempt_id
                ):
                    raise ValueError("routing result lacks its active route authority")
        if previous_attempt > self.policy.maximum_attempts:
            raise ValueError("routing attempt budget exceeded")
        if spent > self.policy.maximum_cost_microunits:
            raise ValueError("routing monetary budget exceeded")
        return self


class CircuitState(RegistryModel):
    manifest_hash: RegistryHash
    revision: Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)] = 0
    failures: Annotated[int, Field(strict=True, ge=0, le=10)] = 0
    open_until_ms: RegistryTime = 0
    active_attempt_id: RegistryUuid | None = None
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None

    @model_validator(mode="after")
    def attributable_transition(self) -> Self:
        if self.revision > 0 and self.trace_id is None:
            raise ValueError("circuit transition requires a real trace identity")
        if self.revision == 0 and (
            self.failures or self.open_until_ms or self.active_attempt_id is not None or self.trace_id is not None
        ):
            raise ValueError("unrecorded circuit state cannot carry authority")
        return self


class CancellationToken:
    """Thread-safe signal. Adapters must implement bounded cooperative cancel."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


def input_references(task_value: object) -> tuple[Mapping[str, Any], ...]:
    task = decode_model_task(task_value)
    if task is None:
        raise ValueError("model task is invalid")
    result: list[Mapping[str, Any]] = []

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            if all(key in value for key in ("aggregateId", "revisionId", "contentHash", "role")):
                result.append(value)
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, tuple):
            for child in value:
                visit(child)

    visit(task["input"])
    return tuple(result)
