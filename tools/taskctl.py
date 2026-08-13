#!/usr/bin/env python3
"""Research Observatory baseline 1.3 wave-scoped task controller.

The execution hierarchy is Roadmap -> Wave -> Capability increment -> ordered
Slice -> Task -> Wave exit gate. Descriptive aliases are human-facing; numeric
IDs remain immutable evidence keys. Tasks remain the atomic claim/evidence unit.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

VALID_STATUSES = {"NOT_STARTED", "READY", "IN_PROGRESS", "BLOCKED", "REVIEW", "DONE", "DEFERRED", "CANCELLED"}
ACTIVE_PROFILES = {"LOC", "LAB", "UNI", "CLD", "ALL"}
PLATFORMS = {
    "platform-neutral",
    "windows-x64",
    "macos-arm64",
    "linux-x64",
    "linux-arm64",
    "linux-server",
    "cloud",
    "ALL",
}
CAMPAIGN_STATES = {"PLANNED", "ACTIVE", "PAUSED", "REVIEW", "COMPLETE", "CANCELLED"}
CAMPAIGN_SCOPES = {"capability-wave"}
COMPLETION_STATES = {"PENDING", "IN_PROGRESS", "REVIEW", "APPROVED", "CHANGES_REQUESTED", "BLOCKED", "PAUSED"}
LEGACY_UNVERIFIED_POLICY = "pre-exact-evidence-hosted-ci-residual-v1"
LEGACY_UNVERIFIED_REFERENCES: dict[str, dict[str, Any]] = {
    "artifacts/evidence/CAP-00.S03.T02.json": {
        "taskId": "CAP-00.S03.T02",
        "commit": "9877766796b94bfa63faf35c767b095191f203ab",
        "sha256": "6073e80a4362a7688fbf9e3c478259fa789ea5e411b508cb55db7ebd2a9f22c6",
        "unverifiedItems": [
            "No remote workflow run was created because the approved repository policy does not authorize a "
            "remote push; local validators cover the workflow contract."
        ],
    },
    "artifacts/evidence/CAP-00.S03.T02.review-fix.json": {
        "taskId": "CAP-00.S03.T02",
        "commit": "7fe9165caf44aeb59f6e2bb2549dcb23a059afbb",
        "sha256": "1c3f2e26e7f5d8a678d02a4001ca4883e2a8af8d69a9c09b61fee6636f5e8cf7",
        "unverifiedItems": [
            "No remote workflow run was created because remote push is outside the approved local integration policy."
        ],
    },
    "artifacts/evidence/CAP-00.S03.T03.json": {
        "taskId": "CAP-00.S03.T03",
        "commit": "7352470d1f9fcd7cacea1bfa604df364a70c1a37",
        "sha256": "3e137f48d93bc282573d40f33c0c0fd90ee17f2e45ce4e6d7de5d1e0f0f9d89b",
        "unverifiedItems": [
            "No remote GitHub Actions run was created because remote push is outside the approved local integration "
            "policy; the workflow contract and hosted commands were validated locally."
        ],
    },
    "artifacts/evidence/CAP-00.S03.T03.review-fix.json": {
        "taskId": "CAP-00.S03.T03",
        "commit": "ce2474676425416a77822cea3e47fab804dc33d3",
        "sha256": "44327b2c7ace55114775ad16fd5c61978d9f1ed5fa879e3ad73a5ed51f9bd991",
        "unverifiedItems": [
            "No remote GitHub Actions run was created because remote push is outside the approved local integration "
            "policy; the CI workflow contract and both security commands passed locally."
        ],
    },
}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def serializable_backlog(data: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(data)
    for capability in document.get("capabilities", []):
        for slice_ in capability.get("slices", []):
            slice_.pop("_position", None)
    return document


def identity_snapshot(data: dict[str, Any]) -> tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...]:
    return tuple(
        (
            capability["id"],
            tuple(
                (slice_["id"], tuple(task["id"] for task in slice_.get("tasks", [])))
                for slice_ in capability.get("slices", [])
            ),
        )
        for capability in data.get("capabilities", [])
    )


@contextmanager
def exclusive_backlog_lock(destination: Path) -> Iterator[None]:
    lock_path = destination.with_name(f"{destination.name}.taskctl.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if lock_path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            set_backlog_lock(handle, unlock=False)
        except OSError as exc:
            raise SystemExit(f"Backlog is locked by another taskctl writer: {destination}") from exc
        try:
            yield
        finally:
            handle.seek(0)
            set_backlog_lock(handle, unlock=True)


def set_backlog_lock(handle: Any, *, unlock: bool) -> None:
    if os.name == "nt":
        import msvcrt

        operation = msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK
        msvcrt.locking(handle.fileno(), operation, 1)
    else:
        import fcntl

        fcntl_api = vars(fcntl)
        flock = fcntl_api["flock"]
        operation = fcntl_api["LOCK_UN"] if unlock else fcntl_api["LOCK_EX"] | fcntl_api["LOCK_NB"]
        flock(handle.fileno(), operation)


def save_atomic(
    path: str,
    data: dict[str, Any],
    *,
    expected_sha256: str | None = None,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = serializable_backlog(data)
    with exclusive_backlog_lock(destination):
        if expected_sha256 is not None:
            try:
                actual_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
            except OSError as exc:
                raise SystemExit(f"Cannot verify backlog before save: {destination}: {exc}") from exc
            if actual_sha256 != expected_sha256:
                raise SystemExit(
                    "Backlog changed after taskctl loaded it; no update was written. Reload and retry the command."
                )
        fd, temp_name = tempfile.mkstemp(prefix=f"{destination.name}.", suffix=".tmp", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump(document, handle, sort_keys=False, allow_unicode=True, width=120)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def _json_path(parts: Any) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def backlog_schema_errors(data: Any, schema_path: Path | None = None) -> list[str]:
    schema_file = schema_path or Path(__file__).resolve().parents[1] / "planning" / "backlog.schema.json"
    try:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        return [f"Cannot load backlog schema {schema_file}: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[ValidationError] = []

    def collect(error: ValidationError) -> None:
        if error.context:
            for nested in error.context:
                collect(nested)
        else:
            errors.append(error)

    for validation_error in validator.iter_errors(data):
        collect(validation_error)
    errors.sort(key=lambda error: (*tuple(str(part) for part in error.absolute_path), error.message))
    return [f"{_json_path(error.absolute_path)}: {error.message}" for error in errors]


def load(
    path: str,
    *,
    validate_schema: bool = True,
    schema_path: Path | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Cannot load backlog {path}: {exc}") from exc
    if validate_schema:
        schema_errors = backlog_schema_errors(data, schema_path=schema_path)
        if schema_errors:
            raise SystemExit("Backlog schema validation failed:\n- " + "\n- ".join(schema_errors))
    return index_backlog(data)


def index_backlog(
    data: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    tasks: dict[str, dict[str, Any]] = {}
    slices: dict[str, dict[str, Any]] = {}
    capabilities: dict[str, dict[str, Any]] = {}
    for capability in data.get("capabilities", []):
        cid = capability["id"]
        if cid in capabilities:
            raise SystemExit(f"Duplicate capability ID: {cid}")
        capabilities[cid] = capability
        for position, slice_ in enumerate(capability.get("slices", [])):
            sid = slice_["id"]
            if sid in slices:
                raise SystemExit(f"Duplicate slice ID: {sid}")
            slice_["_position"] = position
            slices[sid] = slice_
            for task in slice_.get("tasks", []):
                tid = task["id"]
                if tid in tasks:
                    raise SystemExit(f"Duplicate task ID: {tid}")
                tasks[tid] = task
    seen_wave_ids: set[str] = set()
    for wave in data.get("waves", []):
        if wave["id"] in seen_wave_ids:
            raise SystemExit(f"Duplicate wave ID: {wave['id']}")
        seen_wave_ids.add(wave["id"])
    gates: dict[str, dict[str, Any]] = {}
    for gate in data.get("release_gates", []):
        if gate["id"] in gates:
            raise SystemExit(f"Duplicate release gate ID: {gate['id']}")
        gates[gate["id"]] = gate
    return data, capabilities, slices, tasks, gates


def save_validated(
    path: str,
    data: dict[str, Any],
    *,
    expected_sha256: str | None = None,
    expected_identity: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] | None = None,
    schema_path: Path | None = None,
    repo: Path | None = None,
) -> None:
    document = serializable_backlog(data)
    if expected_identity is not None and identity_snapshot(document) != expected_identity:
        raise SystemExit(
            "Stable backlog IDs or their hierarchy changed during a taskctl transition; no update was written"
        )
    schema_errors = backlog_schema_errors(document, schema_path=schema_path)
    if schema_errors:
        raise SystemExit("Refusing to save invalid backlog schema:\n- " + "\n- ".join(schema_errors))
    indexed = index_backlog(document)
    semantic_errors = validate(*indexed, repo=repo)
    if semantic_errors:
        raise SystemExit("Refusing to save invalid backlog state:\n- " + "\n- ".join(semantic_errors))
    save_atomic(path, document, expected_sha256=expected_sha256)


def persist(args: argparse.Namespace, data: dict[str, Any]) -> None:
    save_validated(
        args.file,
        data,
        expected_sha256=getattr(args, "source_sha256", None),
        expected_identity=getattr(args, "source_identity", None),
        repo=getattr(args, "repo_root", None),
    )


def wave_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {wave["id"]: wave for wave in data.get("waves", [])}


def ordered_wave_ids(data: dict[str, Any]) -> list[str]:
    return [str(wave["id"]) for wave in data.get("waves", [])]


def gate_after_wave(data: dict[str, Any], wave_id: str) -> dict[str, Any] | None:
    return next(
        (gate for gate in data.get("release_gates", []) if gate.get("after_wave") == wave_id),
        None,
    )


def capability_wave_slices(capability: dict[str, Any], wave_id: str) -> list[dict[str, Any]]:
    return [slice_ for slice_ in capability.get("slices", []) if slice_.get("wave") == wave_id]


def campaign_wave(capability: dict[str, Any]) -> str | None:
    value = (capability.get("campaign") or {}).get("wave")
    return str(value) if value is not None else None


def capability_wave_complete(capability: dict[str, Any], wave_id: str) -> bool:
    slices = capability_wave_slices(capability, wave_id)
    return bool(slices) and all(slice_.get("completion", {}).get("status") == "APPROVED" for slice_ in slices)


def global_program_position(
    data: dict[str, Any],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return the earliest unfinished program wave or the gate that blocks it.

    Waves are the primary execution axis. Capability numbering and a capability's
    future slices never advance this position.
    """

    for wave_id in ordered_wave_ids(data):
        incomplete_tasks = sorted(
            task["id"] for task in tasks.values() if task.get("wave") == wave_id and task.get("status") != "DONE"
        )
        incomplete_slices = sorted(
            slice_["id"]
            for slice_ in slices.values()
            if slice_.get("wave") == wave_id and slice_.get("completion", {}).get("status") != "APPROVED"
        )
        if not incomplete_tasks and not incomplete_slices:
            continue
        wave = wave_map(data).get(wave_id, {})
        activation_gate_id = wave.get("activation_gate")
        activation_gate = gates.get(activation_gate_id) if isinstance(activation_gate_id, str) else None
        if activation_gate is not None and activation_gate.get("status") != "APPROVED":
            return {
                "state": "GATE_PENDING",
                "current_wave": activation_gate.get("after_wave"),
                "blocked_wave": wave_id,
                "next_gate": activation_gate,
                "incomplete_tasks": incomplete_tasks,
                "incomplete_slices": incomplete_slices,
            }
        return {
            "state": "ACTIVE_WAVE",
            "current_wave": wave_id,
            "blocked_wave": None,
            "next_gate": gate_after_wave(data, wave_id),
            "incomplete_tasks": incomplete_tasks,
            "incomplete_slices": incomplete_slices,
        }
    return {
        "state": "COMPLETE",
        "current_wave": None,
        "blocked_wave": None,
        "next_gate": None,
        "incomplete_tasks": [],
        "incomplete_slices": [],
    }


def gate_transition_label(gate: dict[str, Any] | None) -> str:
    if not gate:
        return "none"
    unlocks = ", ".join(str(item) for item in gate.get("unlocks_waves", [])) or "no wave"
    return f"{gate.get('id')} — {gate.get('after_wave')} exit / {unlocks} activation"


def gate_is_open(data: dict[str, Any], gates: dict[str, dict[str, Any]], wave_id: str) -> bool:
    wave = wave_map(data).get(wave_id)
    if not wave:
        return False
    gate_id = wave.get("activation_gate")
    return gate_id is None or gates.get(gate_id, {}).get("status") == "APPROVED"


def profile_matches(item: dict[str, Any], requested: str) -> bool:
    profiles = set(item.get("deployment_profiles", []))
    return requested == "ALL" or "ALL" in profiles or requested in profiles


def platform_matches(item: dict[str, Any], requested: str) -> bool:
    targets = set(item.get("platform_targets", ["platform-neutral"]))
    return requested == "ALL" or "platform-neutral" in targets or requested in targets


def dependency_graph_errors(tasks: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for tid, task in tasks.items():
        for dep in task.get("dependencies", []):
            if dep not in tasks:
                errors.append(f"{tid}: missing dependency {dep}")

    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(task_id: str) -> list[str] | None:
        state[task_id] = 1
        stack.append(task_id)
        for dependency in tasks[task_id].get("dependencies", []):
            if dependency not in tasks:
                continue
            if state.get(dependency, 0) == 0:
                cycle = visit(dependency)
                if cycle:
                    return cycle
            elif state[dependency] == 1:
                start = stack.index(dependency)
                return [*stack[start:], dependency]
        stack.pop()
        state[task_id] = 2
        return None

    for task_id in sorted(tasks):
        if state.get(task_id, 0) == 0:
            cycle = visit(task_id)
            if cycle:
                errors.append(f"Dependency cycle detected: {' -> '.join(cycle)}")
                break
    return errors


def slice_dependency_errors(slices: dict[str, dict[str, Any]], tasks: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for slice_id, slice_ in slices.items():
        for dependency in slice_.get("depends_on", []):
            if dependency not in tasks:
                errors.append(f"{slice_id}: missing dependency {dependency}")
    return errors


def previous_slices_approved(capability: dict[str, Any], slice_: dict[str, Any]) -> bool:
    position = slice_.get("_position", 0)
    return all(s.get("completion", {}).get("status") == "APPROVED" for s in capability.get("slices", [])[:position])


def task_dependencies_done(task: dict[str, Any], tasks: dict[str, dict[str, Any]]) -> bool:
    return all(tasks.get(dep, {}).get("status") == "DONE" for dep in task.get("dependencies", []))


def slice_dependencies_done(slice_: dict[str, Any], tasks: dict[str, dict[str, Any]]) -> bool:
    return all(tasks.get(dep, {}).get("status") == "DONE" for dep in slice_.get("depends_on", []))


def task_can_be_ready(
    data: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    task: dict[str, Any],
) -> bool:
    capability = capabilities[task["capability_id"]]
    slice_ = slices[task["slice_id"]]
    return (
        task_dependencies_done(task, tasks)
        and slice_dependencies_done(slice_, tasks)
        and gate_is_open(data, gates, task["wave"])
        and previous_slices_approved(capability, slice_)
    )


def refresh_derived_states(
    data: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
) -> int:
    changed = 0
    for task in tasks.values():
        if task["status"] not in {"NOT_STARTED", "READY"}:
            continue
        new_status = "READY" if task_can_be_ready(data, capabilities, slices, tasks, gates, task) else "NOT_STARTED"
        if task["status"] != new_status:
            task["status"] = new_status
            task["updated_at"] = utc_now()
            changed += 1
    for _cid, capability in capabilities.items():
        for slice_ in capability.get("slices", []):
            if slice_["status"] in {"DEFERRED", "CANCELLED", "BLOCKED", "REVIEW", "DONE"}:
                continue
            statuses = {task["status"] for task in slice_["tasks"]}
            new = (
                "IN_PROGRESS"
                if statuses & {"IN_PROGRESS", "REVIEW", "DONE"}
                else ("READY" if statuses & {"READY"} else "NOT_STARTED")
            )
            if slice_["status"] != new:
                slice_["status"] = new
                changed += 1
    return changed


def active_capabilities(capabilities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in capabilities.values() if (c.get("campaign") or {}).get("status") == "ACTIVE"]


def capability_display(capability: dict[str, Any]) -> str:
    alias = capability.get("alias")
    return f"{alias} ({capability['id']})" if alias else str(capability["id"])


def display_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def slice_display(slice_: dict[str, Any]) -> str:
    alias = slice_.get("alias") or f"SLICE-{display_slug(str(slice_.get('title', 'untitled')))}"
    return f"{alias} ({slice_['id']})"


def capability_sort_key(capability: dict[str, Any], wave_id: str) -> tuple[int, str]:
    slices = capability_wave_slices(capability, wave_id)
    incomplete = [s for s in slices if s.get("completion", {}).get("status") != "APPROVED"]
    first = incomplete[0] if incomplete else slices[-1]
    return int(first["priority"][1:]), capability["id"]


def task_sort_key(task: dict[str, Any]) -> tuple[int, int, str]:
    return int(task["wave"][1:]), int(task["priority"][1:]), task["id"]


def eligible_capabilities(
    data: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    profile: str,
    platform: str,
) -> list[dict[str, Any]]:
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    program = global_program_position(data, slices, tasks, gates)
    active_wave = program.get("current_wave") if program.get("state") == "ACTIVE_WAVE" else None
    if not isinstance(active_wave, str):
        return []
    eligible: list[dict[str, Any]] = []
    for capability in capabilities.values():
        if capability.get("completion", {}).get("status") == "APPROVED":
            continue
        campaign_state = (capability.get("campaign") or {}).get("status")
        pause_category = (capability.get("campaign") or {}).get("pause_category")
        if campaign_state in {"ACTIVE", "REVIEW", "COMPLETE", "CANCELLED"}:
            continue
        if campaign_state == "PAUSED" and pause_category != "wave-complete":
            continue
        incomplete = [
            s
            for s in capability_wave_slices(capability, active_wave)
            if s.get("completion", {}).get("status") != "APPROVED"
        ]
        if not incomplete:
            continue
        current = incomplete[0]
        if not previous_slices_approved(capability, current):
            continue
        if not profile_matches(current, profile) or not platform_matches(current, platform):
            continue
        if not gate_is_open(data, gates, current["wave"]):
            continue
        if any(
            task["status"] == "READY" and profile_matches(task, profile) and platform_matches(task, platform)
            for task in current["tasks"]
        ):
            eligible.append(capability)
    return sorted(eligible, key=lambda capability: capability_sort_key(capability, active_wave))


def current_slice(capability: dict[str, Any], wave_id: str | None = None) -> dict[str, Any] | None:
    for slice_ in capability.get("slices", []):
        if wave_id is not None and slice_.get("wave") != wave_id:
            continue
        if slice_.get("completion", {}).get("status") != "APPROVED":
            return slice_
    return None


def ready_tasks_in_campaign(
    data: dict[str, Any],
    capability: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    profile: str,
    platform: str,
) -> list[dict[str, Any]]:
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    wave_id = campaign_wave(capability)
    if wave_id is None:
        return []
    slice_ = current_slice(capability, wave_id)
    if not slice_:
        return []
    return sorted(
        [
            t
            for t in slice_["tasks"]
            if t["status"] == "READY" and profile_matches(t, profile) and platform_matches(t, platform)
        ],
        key=task_sort_key,
    )


def get(mapping: dict[str, dict[str, Any]], id_: str, label: str) -> dict[str, Any]:
    try:
        return mapping[id_]
    except KeyError as exc:
        raise SystemExit(f"Unknown {label}: {id_}") from exc


def get_capability(capabilities: dict[str, dict[str, Any]], identity: str) -> dict[str, Any]:
    if identity in capabilities:
        return capabilities[identity]
    matches = [capability for capability in capabilities.values() if capability.get("alias") == identity]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(f"Unknown capability: {identity}")


def lease_is_active(holder: dict[str, Any]) -> bool:
    lease = holder.get("lease") or (holder.get("campaign") or {}).get("lease")
    if not lease:
        return False
    try:
        return parse_time(lease["expires_at"]) > dt.datetime.now(dt.UTC)
    except KeyError, ValueError:
        return False


def require_active_lease(holder: dict[str, Any], actor: str, label: str) -> None:
    actor = actor.strip()
    if not actor:
        raise SystemExit(f"{label} actor must be non-empty")
    campaign = holder.get("campaign") or {}
    owner = holder.get("owner") or campaign.get("owner")
    lease = holder.get("lease") or campaign.get("lease")
    if owner != actor:
        raise SystemExit(f"{label} is owned by {owner or '<unclaimed>'}, not {actor}")
    if not lease:
        raise SystemExit(f"{label} has no active lease")
    if lease.get("claimed_by") != actor:
        raise SystemExit(f"{label} lease belongs to {lease.get('claimed_by') or '<unknown>'}, not {actor}")
    if not lease_is_active(holder):
        raise SystemExit(f"{label} lease has expired; renew or reopen it before mutation")


def require_positive_lease_hours(hours: int) -> None:
    if hours <= 0:
        raise SystemExit("Lease duration must be greater than zero hours")


def require_execution_target(profile: str, platform: str) -> None:
    if profile == "ALL" or platform == "ALL":
        raise SystemExit("Execution commands require one concrete deployment profile and platform")


def normalized_identity(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SystemExit(f"{label} identity must be non-empty")
    return normalized


def git_execution_identity(
    backlog_path: str,
    *,
    agent: str,
    branch: str,
    base_sha: str,
    worktree: str | None,
) -> tuple[str, str, str, str]:
    agent = normalized_identity(agent, "Agent")
    branch = normalized_identity(branch, "Branch")
    if re.fullmatch(r"[0-9a-f]{40}", base_sha) is None:
        raise SystemExit("Base SHA must be a full lowercase 40-character Git commit")
    if not worktree:
        raise SystemExit("A canonical Git worktree is required")
    repo = discover_repository(backlog_path)
    if Path(worktree).resolve() != repo:
        raise SystemExit(f"Worktree must resolve to the canonical repository {repo}")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False)
    if head.returncode != 0 or head.stdout.strip() != base_sha:
        raise SystemExit("Base SHA must equal the current Git HEAD")
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True, check=False
    )
    if current_branch.returncode != 0 or current_branch.stdout.strip() != branch:
        raise SystemExit("Branch must equal the current Git branch")
    return agent, branch, base_sha, repo.as_posix()


def require_task_campaign_lease(
    task: dict[str, Any], capabilities: dict[str, dict[str, Any]], actor: str
) -> dict[str, Any]:
    capability = capabilities[task["capability_id"]]
    campaign = capability.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit(f"Capability {capability['id']} campaign is not ACTIVE")
    if campaign.get("scope") != "capability-wave" or campaign.get("wave") != task.get("wave"):
        raise SystemExit(
            f"Task {task['id']} is outside the active "
            f"{capability['id']}/{campaign.get('wave')} capability-wave increment"
        )
    require_active_lease(capability, actor, f"Capability {capability['id']}")
    return capability


def new_lease(agent: str, hours: int) -> dict[str, str]:
    claimed = dt.datetime.now(dt.UTC).replace(microsecond=0)
    return {
        "claimed_by": agent,
        "claimed_at": claimed.isoformat(),
        "expires_at": (claimed + dt.timedelta(hours=hours)).isoformat(),
    }


def parse_evidence_payload(payload: bytes, suffix: str) -> dict[str, Any]:
    text = payload.decode("utf-8")
    manifest = yaml.safe_load(text) if suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    if not isinstance(manifest, dict):
        raise ValueError("evidence manifest root must be an object")
    return manifest


def load_evidence(path: str) -> dict[str, Any]:
    evidence_path = Path(path)
    if not evidence_path.exists():
        raise SystemExit(f"Evidence file does not exist: {path}")
    return parse_evidence_payload(evidence_path.read_bytes(), evidence_path.suffix)


def evidence_sha256(payload: bytes) -> str:
    """Hash repository text canonically so Git EOL conversion cannot invalidate evidence."""
    return hashlib.sha256(payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def legacy_unverified_policy_errors(
    reference: dict[str, Any], manifest: dict[str, Any], actual_sha256: str
) -> tuple[bool, list[str]]:
    policy = reference.get("legacy_policy")
    if policy is None:
        return False, []
    if policy != LEGACY_UNVERIFIED_POLICY:
        return False, [f"unsupported legacy evidence policy {policy!r}"]
    path = reference.get("path", "")
    expected = LEGACY_UNVERIFIED_REFERENCES.get(path)
    if expected is None:
        return False, [f"legacy evidence policy is not authorized for {path!r}"]
    errors: list[str] = []
    for field in ("commit", "sha256"):
        actual = reference.get(field) if field == "commit" else actual_sha256
        if actual != expected[field]:
            errors.append(f"legacy evidence {field} does not match its immutable policy anchor")
    if manifest.get("taskId") != expected["taskId"]:
        errors.append("legacy evidence taskId does not match its immutable policy anchor")
    if manifest.get("commit") != expected["commit"]:
        errors.append("legacy evidence manifest commit does not match its immutable policy anchor")
    if manifest.get("unverifiedItems") != expected["unverifiedItems"]:
        errors.append("legacy evidence unverifiedItems do not match the immutable hosted-CI residual")
    return not errors, errors


def validate_task_evidence(
    task: dict[str, Any],
    manifest: dict[str, Any],
    *,
    expected_commit: str | None = None,
    expected_base_commit: str | None = None,
    allow_disclosed_unverified: bool = False,
) -> list[str]:
    errors: list[str] = []
    if manifest.get("taskId") != task["id"]:
        errors.append("taskId does not match")
    if expected_base_commit is not None and manifest.get("baseCommit") != expected_base_commit:
        errors.append(f"baseCommit must equal the expected evidence base {expected_base_commit}")
    if manifest.get("branch") != task.get("branch"):
        errors.append("branch does not match the claimed task branch")
    commit = manifest.get("commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        errors.append("commit must be a full lowercase 40-character Git SHA")
    elif expected_commit is not None and commit != expected_commit:
        errors.append(f"commit must equal current HEAD {expected_commit}")
    checks = manifest.get("checks", [])
    if not isinstance(checks, list) or not checks:
        errors.append("at least one check is required")
        checks = []
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("command"), str) or not check["command"].strip():
            errors.append("every check requires a non-empty command")
        if not isinstance(check, dict) or type(check.get("exitCode")) is not int or check.get("exitCode") != 0:
            command = check.get("command", "<unknown>") if isinstance(check, dict) else "<invalid>"
            errors.append(f"check failed: {command}")
    criteria = manifest.get("acceptanceCriteria", [])
    if not isinstance(criteria, list):
        criteria = []
    mapped_indexes = [
        item.get("criterion_index")
        for item in criteria
        if isinstance(item, dict) and type(item.get("criterion_index")) is int
    ]
    mapped = set(mapped_indexes)
    expected = set(range(1, len(task.get("acceptance_criteria", [])) + 1))
    if mapped != expected or len(mapped_indexes) != len(mapped):
        errors.append(f"criterion evidence must map exactly to indexes {sorted(expected)}")
    for item in criteria:
        if not isinstance(item, dict):
            continue
        evidence = item.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(statement, str) and statement.strip() for statement in evidence)
        ):
            errors.append(
                f"criterion {item.get('criterion_index', '<unknown>')} requires non-empty evidence statements"
            )
    if "unverifiedItems" not in manifest or not isinstance(manifest.get("unverifiedItems"), list):
        errors.append("unverifiedItems must be present as a list")
    elif manifest.get("unverifiedItems") and not allow_disclosed_unverified:
        errors.append("unverifiedItems must be empty before evidence attachment")
    return errors


def discover_repository(backlog_path: str) -> Path:
    completed = subprocess.run(
        ["git", "-C", str(Path(backlog_path).resolve().parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise SystemExit(f"Cannot resolve Git repository for exact-commit evidence: {detail or 'git failed'}")
    return Path(completed.stdout.strip()).resolve()


def changed_file_errors(task: dict[str, Any], manifest: dict[str, Any], repo: Path) -> list[str]:
    errors: list[str] = []
    changed_files = manifest.get("changedFiles")
    if (
        not isinstance(changed_files, list)
        or not changed_files
        or not all(
            isinstance(item, str)
            and item
            and not PurePosixPath(item).is_absolute()
            and ".." not in PurePosixPath(item).parts
            and "\\" not in item
            for item in changed_files
        )
    ):
        return ["changedFiles must be a non-empty unique list of safe repository-relative paths"]
    if len(changed_files) != len(set(changed_files)):
        return ["changedFiles must be a non-empty unique list of safe repository-relative paths"]
    base = manifest.get("baseCommit")
    commit = manifest.get("commit")
    if not isinstance(base, str) or not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        return errors
    actual = subprocess.run(
        ["git", "diff", "--name-only", base, commit, "--"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if actual.returncode != 0:
        return [f"cannot resolve changed-file scope: {(actual.stderr or actual.stdout).strip()}"]
    actual_files = set(actual.stdout.splitlines())
    declared_files = set(changed_files)
    if declared_files != actual_files:
        errors.append("changedFiles must exactly match the claimed base-to-commit diff")
    return errors


def committed_manifest_errors(
    task: dict[str, Any],
    manifest: dict[str, Any],
    repo: Path,
    *,
    expected_commit: str | None = None,
    expected_base_commit: str | None = None,
    evidence_path: Path | None = None,
    allow_disclosed_unverified: bool = False,
) -> list[str]:
    errors = validate_task_evidence(
        task,
        manifest,
        expected_commit=expected_commit,
        expected_base_commit=expected_base_commit,
        allow_disclosed_unverified=allow_disclosed_unverified,
    )
    errors.extend(changed_file_errors(task, manifest, repo))
    commit = manifest.get("commit")
    if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit):
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if resolved.returncode != 0 or resolved.stdout.strip() != commit:
            errors.append("commit does not resolve to the named immutable Git commit")
        base_sha = task.get("base_sha")
        if base_sha:
            ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", base_sha, commit],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            if ancestry.returncode == 1:
                errors.append(f"commit is not descended from task base_sha {base_sha}")
            elif ancestry.returncode != 0:
                errors.append(f"cannot verify task base ancestry: {(ancestry.stderr or ancestry.stdout).strip()}")
        manifest_base = manifest.get("baseCommit")
        if isinstance(manifest_base, str) and re.fullmatch(r"[0-9a-f]{40}", manifest_base):
            incremental_ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", manifest_base, commit],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            if incremental_ancestry.returncode == 1:
                errors.append("commit is not descended from manifest baseCommit")
            elif incremental_ancestry.returncode != 0:
                errors.append(
                    f"cannot verify manifest base ancestry: "
                    f"{(incremental_ancestry.stderr or incremental_ancestry.stdout).strip()}"
                )
    if expected_commit is not None:
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True, check=False
        )
        if branch.returncode != 0 or branch.stdout.strip() != task.get("branch"):
            errors.append("task branch does not match the current Git branch")
        worktree = task.get("worktree")
        if not worktree or Path(worktree).resolve() != repo:
            errors.append("task worktree does not match the canonical Git worktree")
        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, capture_output=True, text=True, check=False
        )
        if dirty.returncode != 0:
            errors.append("tracked worktree changes exist outside the exact implementation commit")
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        allowed = {evidence_path.relative_to(repo).as_posix()} if evidence_path is not None else set()
        unexpected = sorted(set(untracked.stdout.splitlines()) - allowed)
        if untracked.returncode != 0:
            errors.append(f"cannot inspect untracked files: {(untracked.stderr or untracked.stdout).strip()}")
        elif unexpected:
            errors.append(f"untracked source exists outside the evidence manifest: {unexpected[0]}")
    return errors


def exact_commit_errors(
    task: dict[str, Any],
    manifest: dict[str, Any],
    repo: Path,
    *,
    evidence_path: Path | None = None,
    expected_base_commit: str | None = None,
) -> list[str]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False)
    if head.returncode != 0:
        return [f"cannot resolve current HEAD: {(head.stderr or head.stdout).strip()}"]
    current_commit = head.stdout.strip()
    return committed_manifest_errors(
        task,
        manifest,
        repo,
        expected_commit=current_commit,
        expected_base_commit=expected_base_commit or task.get("base_sha"),
        evidence_path=evidence_path,
    )


def evidence_reference_errors(tasks: dict[str, dict[str, Any]], repo: Path) -> list[str]:
    errors: list[str] = []
    for task_id, task in tasks.items():
        seen_hashes: set[str] = set()
        seen_commits: set[str] = set()
        seen_references: dict[str, dict[str, Any]] = {}
        for reference_index, reference in enumerate(task.get("evidence", [])):
            raw_path = reference.get("path", "")
            path = PurePosixPath(raw_path)
            if (
                not raw_path.startswith("artifacts/evidence/")
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in raw_path
            ):
                errors.append(f"{task_id}: unsafe evidence path {raw_path!r}")
                continue
            evidence_path = repo.joinpath(*path.parts)
            try:
                payload = evidence_path.read_bytes()
            except OSError as exc:
                errors.append(f"{task_id}: cannot read evidence {raw_path}: {exc}")
                continue
            actual_sha256 = evidence_sha256(payload)
            if actual_sha256 != reference.get("sha256"):
                errors.append(f"{task_id}: evidence hash mismatch for {raw_path}")
                continue
            try:
                manifest = parse_evidence_payload(payload, evidence_path.suffix)
            except (UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
                errors.append(f"{task_id}: invalid evidence manifest {raw_path}: {exc}")
                continue
            if manifest.get("commit") != reference.get("commit"):
                errors.append(f"{task_id}: evidence manifest commit mismatch for {raw_path}")
            allow_legacy_unverified, policy_errors = legacy_unverified_policy_errors(reference, manifest, actual_sha256)
            for error in policy_errors:
                errors.append(f"{task_id}: {raw_path}: {error}")
            expected_base_commit = task.get("base_sha")
            supersedes = manifest.get("supersedes")
            if reference_index == 0:
                if supersedes is not None:
                    errors.append(f"{task_id}: {raw_path}: initial evidence cannot supersede another attachment")
            elif isinstance(supersedes, dict):
                superseded_path = supersedes.get("path")
                prior_reference = seen_references.get(superseded_path) if isinstance(superseded_path, str) else None
                if prior_reference is None:
                    errors.append(f"{task_id}: {raw_path}: supersedes.path must identify a prior evidence attachment")
                else:
                    expected_base_commit = prior_reference.get("commit")
            else:
                errors.append(
                    f"{task_id}: {raw_path}: follow-up evidence must identify a prior attachment with supersedes.path"
                )
            for error in committed_manifest_errors(
                task,
                manifest,
                repo,
                expected_base_commit=expected_base_commit,
                allow_disclosed_unverified=allow_legacy_unverified,
            ):
                errors.append(f"{task_id}: {raw_path}: {error}")
            if actual_sha256 in seen_hashes or reference.get("commit") in seen_commits:
                errors.append(f"{task_id}: logically duplicate evidence attachment {raw_path}")
            seen_hashes.add(actual_sha256)
            seen_commits.add(reference.get("commit"))
            seen_references[raw_path] = reference
    return errors


def validate(
    data: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    *,
    repo: Path | None = None,
) -> list[str]:
    errors = [*dependency_graph_errors(tasks), *slice_dependency_errors(slices, tasks)]
    if repo is not None:
        errors.extend(evidence_reference_errors(tasks, repo))
    waves = wave_map(data)
    active = active_capabilities(capabilities)
    if len(active) > 1:
        errors.append("More than one ACTIVE capability-wave campaign exists; default automation permits one increment")
    aliases: dict[str, str] = {}
    for cid, capability in capabilities.items():
        if capability.get("execution_mode") != "capability_campaign":
            errors.append(f"{cid}: execution_mode must be capability_campaign")
        alias = capability.get("alias")
        if not isinstance(alias, str) or re.fullmatch(r"CAP-[a-z0-9]+(?:-[a-z0-9]+)*", alias) is None:
            errors.append(f"{cid}: alias must be a stable descriptive CAP-<slug> identity")
        elif alias in aliases:
            errors.append(f"{cid}: alias duplicates {aliases[alias]}: {alias}")
        else:
            aliases[alias] = cid
        campaign = capability.get("campaign")
        if campaign:
            if campaign.get("status") not in CAMPAIGN_STATES:
                errors.append(f"{cid}: invalid campaign status")
            if campaign.get("status") == "ACTIVE" and (
                not campaign.get("owner")
                or not campaign.get("branch")
                or not campaign.get("base_sha")
                or not campaign.get("worktree")
                or not campaign.get("lease")
                or campaign.get("scope") not in CAMPAIGN_SCOPES
                or campaign.get("wave") not in waves
            ):
                errors.append(
                    f"{cid}: ACTIVE campaign lacks capability-wave scope, wave, owner, "
                    "branch, base SHA, worktree, or lease"
                )
            campaign_wave_id = campaign.get("wave")
            if campaign_wave_id is not None and not capability_wave_slices(capability, str(campaign_wave_id)):
                errors.append(f"{cid}: campaign wave {campaign_wave_id} has no slice in the capability")
            if campaign.get("pause_category") == "wave-complete" and (
                campaign_wave_id is None or not capability_wave_complete(capability, str(campaign_wave_id))
            ):
                errors.append(f"{cid}: wave-complete pause requires every slice in the campaign wave to be approved")
            if campaign.get("owner") and campaign["owner"] != campaign["owner"].strip():
                errors.append(f"{cid}: campaign owner identity is not normalized")
            if (
                repo is not None
                and campaign.get("status") == "ACTIVE"
                and campaign.get("worktree")
                and Path(campaign["worktree"]).resolve() != repo
            ):
                errors.append(f"{cid}: ACTIVE campaign worktree does not match the repository")
            lease = campaign.get("lease")
            if lease and lease.get("claimed_by") != campaign.get("owner"):
                errors.append(f"{cid}: campaign lease owner does not match campaign owner")
        completion = capability.get("completion", {})
        if completion.get("status") not in COMPLETION_STATES:
            errors.append(f"{cid}: invalid completion status")
        if completion.get("status") == "APPROVED" and (
            not completion.get("reviewer") or not completion.get("reviewed_at") or not completion.get("evidence")
        ):
            errors.append(f"{cid}: approved completion lacks reviewer, time, or evidence")
        if completion.get("reviewer") and completion["reviewer"] == (campaign or {}).get("owner"):
            errors.append(f"{cid}: capability reviewer is not independent from the campaign owner")
        if completion.get("reviewer") and completion["reviewer"] != completion["reviewer"].strip():
            errors.append(f"{cid}: capability reviewer identity is not normalized")
        for position, slice_ in enumerate(capability.get("slices", [])):
            sid = slice_["id"]
            if not sid.startswith(f"{cid}.S"):
                errors.append(f"{sid}: outside capability namespace {cid}")
            if slice_.get("_position") != position:
                errors.append(f"{sid}: inconsistent slice position")
            if slice_["wave"] not in waves:
                errors.append(f"{sid}: unknown wave {slice_['wave']}")
            completion = slice_.get("completion", {})
            if completion.get("status") not in COMPLETION_STATES:
                errors.append(f"{sid}: invalid completion status")
            if completion.get("status") == "APPROVED":
                if any(t["status"] != "DONE" for t in slice_["tasks"]):
                    errors.append(f"{sid}: approved before all tasks are DONE")
                if (
                    not completion.get("reviewer")
                    or not completion.get("reviewed_at")
                    or not completion.get("evidence")
                ):
                    errors.append(f"{sid}: approved completion lacks reviewer, time, or evidence")
            if completion.get("reviewer") and completion["reviewer"] == (campaign or {}).get("owner"):
                errors.append(f"{sid}: slice reviewer is not independent from the campaign owner")
            if completion.get("reviewer") and completion["reviewer"] != completion["reviewer"].strip():
                errors.append(f"{sid}: slice reviewer identity is not normalized")
            for task in slice_["tasks"]:
                tid = task["id"]
                if not tid.startswith(f"{sid}.T"):
                    errors.append(f"{tid}: outside slice namespace {sid}")
                if task.get("capability_id") != cid or task.get("slice_id") != sid:
                    errors.append(f"{tid}: capability_id or slice_id mismatch")
                status = task.get("status")
                if status not in VALID_STATUSES:
                    errors.append(f"{tid}: invalid status {status}")
                if task.get("wave") not in waves:
                    errors.append(f"{tid}: unknown wave {task.get('wave')}")
                if not set(task.get("deployment_profiles", [])).issubset(ACTIVE_PROFILES):
                    errors.append(f"{tid}: invalid deployment profile")
                if not set(task.get("platform_targets", [])).issubset(PLATFORMS - {"ALL"}):
                    errors.append(f"{tid}: invalid platform target")
                if status in {"IN_PROGRESS", "REVIEW", "DONE"} and (
                    not task_dependencies_done(task, tasks) or not slice_dependencies_done(slice_, tasks)
                ):
                    errors.append(f"{tid}: active or completed while task/slice dependencies are incomplete")
                if status == "READY" and not task_can_be_ready(data, capabilities, slices, tasks, gates, task):
                    errors.append(f"{tid}: READY while dependencies, prior slice, or activation gate are incomplete")
                if status == "IN_PROGRESS" and (
                    not task.get("owner")
                    or not task.get("branch")
                    or not task.get("base_sha")
                    or not task.get("worktree")
                    or not task.get("lease")
                ):
                    errors.append(f"{tid}: IN_PROGRESS without owner, branch, base SHA, worktree, and lease")
                if status == "REVIEW" and (
                    not task.get("evidence")
                    or task.get("verification_state") != "passed"
                    or not task.get("owner")
                    or not task.get("branch")
                    or not task.get("base_sha")
                    or not task.get("worktree")
                    or not task.get("lease")
                ):
                    errors.append(f"{tid}: REVIEW without ownership, lease, passed verification, and evidence")
                lease = task.get("lease")
                if task.get("owner") and task["owner"] != task["owner"].strip():
                    errors.append(f"{tid}: task owner identity is not normalized")
                if (
                    repo is not None
                    and status in {"IN_PROGRESS", "REVIEW"}
                    and task.get("worktree")
                    and Path(task["worktree"]).resolve() != repo
                ):
                    errors.append(f"{tid}: active task worktree does not match the repository")
                if lease and lease.get("claimed_by") != task.get("owner"):
                    errors.append(f"{tid}: lease owner does not match task owner")
                review = task.get("review", {})
                if review.get("reviewer") and review["reviewer"] == task.get("owner"):
                    errors.append(f"{tid}: task reviewer is not independent from the task owner")
                if review.get("reviewer") and review["reviewer"] != review["reviewer"].strip():
                    errors.append(f"{tid}: task reviewer identity is not normalized")
                if status == "DONE" and (
                    not task.get("evidence")
                    or review.get("result") != "approved"
                    or not review.get("reviewer")
                    or not review.get("reviewed_at")
                ):
                    errors.append(f"{tid}: DONE without evidence and complete approved review")
                if status == "DONE" and task.get("lease") is not None:
                    errors.append(f"{tid}: DONE task must release its lease")
                if status == "BLOCKED" and not task.get("blocker"):
                    errors.append(f"{tid}: BLOCKED without blocker details")
                if status == "CANCELLED" and not task.get("cancellation"):
                    errors.append(f"{tid}: CANCELLED without rationale")
                if status == "CANCELLED" and task.get("lease") is not None:
                    errors.append(f"{tid}: CANCELLED task must release its lease")
    ordered_gates = [gate for gate in data.get("release_gates", []) if isinstance(gate, dict)]
    for wave_id, wave in waves.items():
        exit_gates = [gate for gate in ordered_gates if gate.get("after_wave") == wave_id]
        if len(exit_gates) != 1:
            errors.append(f"{wave_id}: expected exactly one wave-exit gate, found {len(exit_gates)}")
        activation_gate_id = wave.get("activation_gate")
        if activation_gate_id is None:
            continue
        activation_gate = gates.get(str(activation_gate_id))
        if activation_gate is None:
            errors.append(f"{wave_id}: missing activation gate {activation_gate_id}")
        elif wave_id not in activation_gate.get("unlocks_waves", []):
            errors.append(f"{wave_id}: activation gate {activation_gate_id} does not unlock the wave")
    for gate_index, gate in enumerate(ordered_gates):
        gid = str(gate.get("id"))
        if gate.get("status") == "APPROVED":
            approval = gate.get("approval", {})
            if not approval.get("approved_by") or not approval.get("approved_at") or not approval.get("evidence"):
                errors.append(f"{gid}: APPROVED without approver, timestamp, and evidence")
            if approval.get("approved_by") and approval["approved_by"] != approval["approved_by"].strip():
                errors.append(f"{gid}: release-gate approver identity is not normalized")
            incomplete = sorted(
                task["id"]
                for task in tasks.values()
                if task.get("wave") == gate.get("after_wave") and task["status"] != "DONE"
            )
            if incomplete:
                errors.append(f"{gid}: APPROVED while preceding-wave task {incomplete[0]} is incomplete")
            incomplete_slices = sorted(
                slice_["id"]
                for slice_ in slices.values()
                if slice_.get("wave") == gate.get("after_wave")
                and slice_.get("completion", {}).get("status") != "APPROVED"
            )
            if incomplete_slices:
                errors.append(f"{gid}: APPROVED while preceding-wave slice {incomplete_slices[0]} is incomplete")
            prior_pending = [
                str(prior.get("id")) for prior in ordered_gates[:gate_index] if prior.get("status") != "APPROVED"
            ]
            if prior_pending:
                errors.append(f"{gid}: APPROVED before upstream gate {prior_pending[0]}")
    return errors


def print_yaml(value: Any) -> None:
    print(yaml.safe_dump(value, sort_keys=False, allow_unicode=False).rstrip())


def command_validate(args: argparse.Namespace, data, capabilities, slices, tasks, gates) -> None:
    errors = validate(data, capabilities, slices, tasks, gates, repo=getattr(args, "repo_root", None))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(
        f"Valid backlog: {len(capabilities)} capabilities, {len(slices)} slices, "
        f"{len(tasks)} tasks, {len(gates)} release gates"
    )


def command_status(args, data, capabilities, slices, tasks, gates) -> None:
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    program = global_program_position(data, slices, tasks, gates)
    print("Program state:", program["state"])
    print("Current global wave:", program.get("current_wave") or "complete")
    print("Next global gate:", gate_transition_label(program.get("next_gate")))
    print(
        "Capability completion:",
        dict(sorted(Counter(c.get("completion", {}).get("status") for c in capabilities.values()).items())),
    )
    print(
        "Campaign states:",
        dict(sorted(Counter((c.get("campaign") or {}).get("status", "NONE") for c in capabilities.values()).items())),
    )
    print(
        "Slice completion:",
        dict(sorted(Counter(s.get("completion", {}).get("status") for s in slices.values()).items())),
    )
    print("Task states:", dict(sorted(Counter(t["status"] for t in tasks.values()).items())))
    print("Gate states:", dict(sorted(Counter(g["status"] for g in gates.values()).items())))
    active = active_capabilities(capabilities)
    print(
        "Active capability-wave increment:",
        (f"{capability_display(active[0])}/{campaign_wave(active[0])}" if active else "none"),
    )


def command_next_capability(args, data, capabilities, slices, tasks, gates) -> None:
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    program = global_program_position(data, slices, tasks, gates)
    active = active_capabilities(capabilities)
    if active:
        capability = active[0]
        print_yaml(
            {
                "program": {
                    "state": program["state"],
                    "currentWave": program.get("current_wave"),
                    "nextGlobalGate": gate_transition_label(program.get("next_gate")),
                },
                "activeIncrement": {
                    "capability": capability_display(capability),
                    "canonicalId": capability["id"],
                    "wave": campaign_wave(capability),
                    "campaign": capability.get("campaign"),
                },
            }
        )
        return
    if program.get("state") == "GATE_PENDING":
        print(global_gate_stop_handoff(args, data, program, capabilities, tasks, gates))
        return
    candidates = eligible_capabilities(data, capabilities, slices, tasks, gates, args.profile, args.platform)
    if not candidates:
        print(
            f"No eligible capability-wave increment in {program.get('current_wave') or 'the completed roadmap'} "
            f"for profile {args.profile} and platform {args.platform}"
        )
        return
    capability = candidates[0]
    active_wave = str(program["current_wave"])
    view = {
        "program": {
            "state": program["state"],
            "currentWave": active_wave,
            "nextGlobalGate": gate_transition_label(program.get("next_gate")),
        },
        "capability": capability_display(capability),
        "canonicalId": capability["id"],
        "title": capability["title"],
        "objective": capability["objective"],
        "exit_criteria": capability["exit_criteria"],
        "increment": f"{capability.get('alias', capability['id'])}/{active_wave}",
    }
    selected_slice = current_slice(capability, active_wave)
    if selected_slice is None:
        raise SystemExit(f"Capability {capability['id']} has no current slice in {active_wave}")
    view["current_slice"] = selected_slice["id"]
    view["start_command"] = (
        f"python tools/taskctl.py capability start {capability.get('alias', capability['id'])} "
        f"--wave {active_wave} --agent <agent> "
        f"--branch capability/{capability['id'].lower()}-<slug> --base-sha <sha> "
        f"--worktree <absolute-repository-path> --profile {args.profile} --platform {args.platform}"
    )
    print_yaml(view)


def global_gate_stop_handoff(
    args: argparse.Namespace,
    data: dict[str, Any],
    program: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
) -> str:
    gate = program.get("next_gate")
    if not isinstance(gate, dict):
        raise SystemExit("Global gate handoff requested without a pending release gate")
    gate_id = str(gate["id"])

    repo = Path(args.file).resolve().parent.parent

    def review_link(capability_id: str, suffix: str = "index.html") -> tuple[str, str]:
        relative = f"planning/review-site/{capability_id}/{suffix}"
        return (repo / relative).resolve().as_uri(), relative

    preceding_wave = str(gate.get("after_wave"))
    incomplete = sorted(
        task["id"] for task in tasks.values() if task.get("wave") == preceding_wave and task.get("status") != "DONE"
    )
    prerequisite_capabilities = sorted(
        {
            task["capability_id"]
            for task in tasks.values()
            if task.get("wave") == preceding_wave and task.get("capability_id") in capabilities
        }
    )
    ordered_waves = [str(item.get("id")) for item in data.get("waves", []) if isinstance(item, dict)]
    preceding_index = ordered_waves.index(preceding_wave) if preceding_wave in ordered_waves else -1
    upstream_pending = [
        item["id"]
        for item in data.get("release_gates", [])
        if isinstance(item, dict)
        and item.get("status") != "APPROVED"
        and str(item.get("after_wave")) in ordered_waves
        and ordered_waves.index(str(item.get("after_wave"))) < preceding_index
    ]
    criteria = "\n".join(f"  - {criterion}" for criterion in gate.get("criteria", []))
    prerequisite_links: list[str] = []
    for capability_id in prerequisite_capabilities:
        uri, relative = review_link(capability_id)
        capability = capabilities.get(capability_id, {})
        title = capability.get("title", capability_id)
        prerequisite_links.append(
            f"  - {capability.get('alias', capability_id)} ({capability_id}) {title}: {uri} ({relative})"
        )
    links = "\n".join(prerequisite_links) or "  - No preceding-wave capability pages."
    readiness = (
        f"NOT CURRENTLY APPROVABLE: {len(incomplete)} {preceding_wave} tasks are not DONE"
        + (f"; upstream pending gates: {', '.join(upstream_pending)}" if upstream_pending else "")
        if incomplete
        else "READY FOR HUMAN APPROVAL with at least one exact evidence reference"
    )
    recommendation = (
        "Keep the gate pending, pause this campaign at the documented release gate, complete and approve the "
        "preceding waves/gates in order, assemble criterion-linked gate evidence, then request explicit gate approval "
        "and resume this same campaign."
        if incomplete
        else (
            "Review the criterion-linked evidence and explicitly approve the gate only if every criterion is satisfied."
        )
    )
    resume = (
        f"python tools/taskctl.py gate approve {gate_id} --approver <human> --evidence <criterion-linked-evidence> "
        f'--note "<decision rationale>"; then start only a READY capability-wave increment in '
        f"{', '.join(gate.get('unlocks_waves', []))}."
    )
    return (
        f"STOPPED AT RELEASE GATE {gate_id}: {gate.get('name')}\n"
        f"Approval state: {readiness}.\n"
        f"What the eventual approval must establish:\n{criteria}\n"
        "Review materials:\n"
        f"  - Preceding-wave capability packets:\n{links}\n"
        "Decision alternatives:\n"
        f"  A (recommended): {recommendation}\n"
        "  B: Defer the campaign at this gate without starting prerequisite work; preserve the gate as PENDING.\n"
        "  C: Replan the wave/gate relationship through canonical plans, backlog governance, rationale, and required "
        "approval; do not treat a chat instruction as a gate override.\n"
        f"Resume condition: {resume}"
    )


def command_next(args, data, capabilities, slices, tasks, gates) -> None:
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    program = global_program_position(data, slices, tasks, gates)
    active = active_capabilities(capabilities)
    if not active:
        command_next_capability(args, data, capabilities, slices, tasks, gates)
        return
    campaign = active[0]
    wave_id = campaign_wave(campaign)
    if wave_id is None:
        raise SystemExit(f"Active capability {campaign['id']} lacks an explicit capability-wave scope")
    candidates = ready_tasks_in_campaign(
        data, campaign, capabilities, slices, tasks, gates, args.profile, args.platform
    )
    if not candidates:
        slice_ = current_slice(campaign, wave_id)
        if capability_wave_complete(campaign, wave_id) and any(
            slice_.get("completion", {}).get("status") != "APPROVED"
            for slice_ in campaign.get("slices", [])
            if slice_.get("wave") != wave_id
        ):
            future = current_slice(campaign)
            future_gate = None
            if future is not None:
                future_wave = wave_map(data).get(str(future.get("wave")), {})
                future_gate = gates.get(future_wave.get("activation_gate"))
            print(
                f"CAPABILITY-WAVE INCREMENT COMPLETE: {capability_display(campaign)}/{wave_id}.\n"
                f"Current global wave: {program.get('current_wave')}; next global gate: "
                f"{gate_transition_label(program.get('next_gate'))}.\n"
                f"Future increment: {campaign.get('alias', campaign['id'])}/"
                f"{future.get('wave') if future else 'none'}; "
                f"future blocker: {gate_transition_label(future_gate)}.\n"
                f"Close this increment without advancing the capability: python tools/taskctl.py capability pause "
                f"{campaign['id']} --category wave-complete --agent <agent> "
                f'--reason "{campaign.get("alias", campaign["id"])}/{wave_id} independently approved"; '
                "then run taskctl next to select work in the current global wave."
            )
            return
        print(
            f"No READY task in active capability-wave increment {capability_display(campaign)}/{wave_id} current slice "
            f"{slice_['id'] if slice_ else 'none'}. Complete review, resolve blocker, "
            "or submit/approve the slice."
        )
        return
    task = dict(candidates[0])
    task["displayCapability"] = capability_display(capabilities[task["capability_id"]])
    task["displaySlice"] = slice_display(slices[task["slice_id"]])
    print_yaml(task)


def command_capability_prepare(args, data, capabilities, slices, tasks, gates) -> None:
    capability = get_capability(capabilities, args.capability)
    repo = Path(args.file).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(repo / "tools" / "planctl.py"), "--repo", str(repo), "prepare", capability["id"]],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def command_capability_status(args, data, capabilities, slices, tasks, gates) -> None:
    if args.capability:
        capability = get_capability(capabilities, args.capability)
        summary = {
            k: capability.get(k)
            for k in ["id", "title", "objective", "exit_criteria", "execution_mode", "campaign", "completion"]
        }
        summary["display"] = capability_display(capability)
        summary["slices"] = [
            {
                "id": s["id"],
                "display": slice_display(s),
                "title": s["title"],
                "status": s["status"],
                "completion": s["completion"],
                "task_states": dict(Counter(t["status"] for t in s["tasks"])),
            }
            for s in capability["slices"]
        ]
        print_yaml(summary)
    else:
        for c in sorted(capabilities.values(), key=lambda x: x["id"]):
            print(
                f"{c.get('alias', c['id'])}\tcanonical={c['id']}\t"
                f"campaign={(c.get('campaign') or {}).get('status', 'NONE')}\t"
                f"completion={c.get('completion', {}).get('status')}\t{c['title']}"
            )


def require_capability_planning_ready(args, capability_id: str, wave_id: str) -> None:
    if capability_id == "CAP-00":
        return
    repo = Path(args.file).resolve().parents[1]
    command = [
        sys.executable,
        str(repo / "tools" / "planctl.py"),
        "--repo",
        str(repo),
        "ready",
        capability_id,
        "--wave",
        wave_id,
        "--require-approved",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        streams = []
        for raw in (result.stdout, result.stderr):
            if not raw:
                continue
            cleaned = "\n".join(
                line
                for line in raw.splitlines()
                if "TERM environment variable not set" not in line and line.strip() != "\x1b[3J"
            ).strip()
            if cleaned:
                streams.append(cleaned)
        review_page = repo / "planning" / "review-site" / capability_id / "index.html"
        review_uri = review_page.resolve().as_uri() if review_page.exists() else f"file://{review_page.resolve()}"
        review_rel = f"planning/review-site/{capability_id}/index.html"
        detail = "\n".join(streams)
        message = (
            f"Capability-wave planning gate failed for {capability_id}/{wave_id}. Complete and approve the capability "
            "decision packet and the active-wave slice plans, decisions/ADRs, and governed UI changes before "
            "execution.\n"
            + (detail + "\n" if detail else "")
            + f"Planning review page: {review_uri}\nRepository-relative page: {review_rel}"
        )
        raise SystemExit(message)


def command_capability_start(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    require_execution_target(args.profile, args.platform)
    program = global_program_position(data, slices, tasks, gates)
    if program.get("state") != "ACTIVE_WAVE":
        raise SystemExit(
            f"No capability-wave increment can start while program state is {program.get('state')}; "
            f"next global gate is {gate_transition_label(program.get('next_gate'))}"
        )
    capability = get_capability(capabilities, args.capability)
    wave_id = getattr(args, "wave", None) or str(program["current_wave"])
    if wave_id != program.get("current_wave"):
        raise SystemExit(
            f"Requested increment {capability_display(capability)}/{wave_id} is outside current global wave "
            f"{program.get('current_wave')}"
        )
    require_capability_planning_ready(args, capability["id"], wave_id)
    agent, branch, base_sha, worktree = git_execution_identity(
        args.file,
        agent=args.agent,
        branch=args.branch,
        base_sha=args.base_sha,
        worktree=args.worktree,
    )
    if active_capabilities(capabilities):
        raise SystemExit("Another capability campaign is ACTIVE. Complete or pause it before starting another.")
    prior_campaign = capability.get("campaign") or {}
    new_increment_after_completed_wave = (
        prior_campaign.get("status") == "PAUSED"
        and prior_campaign.get("pause_category") == "wave-complete"
        and prior_campaign.get("wave") != wave_id
        and capability_wave_complete(capability, str(prior_campaign.get("wave")))
    )
    if prior_campaign.get("status") not in {None, "PLANNED"} and not new_increment_after_completed_wave:
        raise SystemExit(f"Capability cannot start from campaign state {prior_campaign.get('status')}")
    candidates = eligible_capabilities(data, capabilities, slices, tasks, gates, args.profile, args.platform)
    if capability not in candidates:
        raise SystemExit(
            "Capability is not eligible for the requested profile/platform or its current slice is not ready"
        )
    now = utc_now()
    capability["campaign"] = {
        "status": "ACTIVE",
        "scope": "capability-wave",
        "wave": wave_id,
        "increment_id": f"{capability.get('alias', capability['id'])}/{wave_id}",
        "owner": agent,
        "branch": branch,
        "worktree": worktree,
        "base_sha": base_sha,
        "profile": args.profile,
        "platform": args.platform,
        "started_at": now,
        "updated_at": now,
        "pause_reason": None,
        "pause_category": None,
        "lease": new_lease(agent, args.lease_hours),
    }
    capability["completion"]["status"] = "IN_PROGRESS"
    persist(args, data)
    print(f"Started capability-wave increment {capability_display(capability)}/{wave_id}")


def command_capability_pause(args, data, capabilities, slices, tasks, gates) -> None:
    capability = get_capability(capabilities, args.capability)
    campaign = capability.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit("Only an ACTIVE capability may be paused")
    require_active_lease(capability, args.agent, f"Capability {args.capability}")
    if any(t["status"] in {"IN_PROGRESS", "REVIEW"} for s in capability["slices"] for t in s["tasks"]):
        raise SystemExit("Resolve or explicitly block active/review tasks before pausing the capability")
    wave_id = campaign.get("wave")
    if args.category == "wave-complete" and (
        not isinstance(wave_id, str) or not capability_wave_complete(capability, wave_id)
    ):
        raise SystemExit("wave-complete pause requires every slice in the active campaign wave to be approved")
    campaign.update(
        status="PAUSED", pause_reason=args.reason, pause_category=args.category, updated_at=utc_now(), lease=None
    )
    capability["completion"]["status"] = "PAUSED"
    persist(args, data)


def command_capability_renew(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    capability = get_capability(capabilities, args.capability)
    campaign = capability.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit("Only an ACTIVE capability lease may be renewed")
    if campaign.get("owner") != args.agent:
        raise SystemExit(f"Capability {args.capability} is owned by {campaign.get('owner')}, not {args.agent}")
    if lease_is_active(capability):
        require_active_lease(capability, args.agent, f"Capability {args.capability}")
    campaign["lease"] = new_lease(args.agent, args.lease_hours)
    campaign["updated_at"] = utc_now()
    persist(args, data)
    print(f"Renewed capability lease for {args.capability}")


def command_capability_resume(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    require_execution_target(args.profile, args.platform)
    if active_capabilities(capabilities):
        raise SystemExit("Another capability campaign is ACTIVE")
    capability = get_capability(capabilities, args.capability)
    campaign = capability.get("campaign") or {}
    if campaign.get("status") != "PAUSED":
        raise SystemExit("Only a PAUSED capability may be resumed")
    agent, branch, base_sha, worktree = git_execution_identity(
        args.file,
        agent=args.agent,
        branch=args.branch,
        base_sha=args.base_sha,
        worktree=args.worktree,
    )
    if campaign.get("owner") != agent:
        raise SystemExit(f"Paused capability is owned by {campaign.get('owner')}, not {agent}")
    if campaign.get("branch") and campaign.get("branch") != branch:
        raise SystemExit("Paused capability must resume on its recorded branch")
    if campaign.get("pause_category") == "wave-complete":
        raise SystemExit(
            "A completed capability-wave increment cannot resume; start the capability in a later active wave"
        )
    wave_id = campaign.get("wave")
    if not isinstance(wave_id, str):
        raise SystemExit("Paused capability lacks a campaign wave")
    require_capability_planning_ready(args, capability["id"], wave_id)
    selected_slice = current_slice(capability, wave_id)
    if selected_slice is None:
        if capability.get("completion", {}).get("status") not in {"CHANGES_REQUESTED", "BLOCKED"}:
            raise SystemExit("Paused capability has no eligible slice or capability-review remediation")
    else:
        program = global_program_position(data, slices, tasks, gates)
        if program.get("state") != "ACTIVE_WAVE" or program.get("current_wave") != wave_id:
            raise SystemExit(
                f"Paused increment {args.capability}/{wave_id} is outside current program position; "
                f"next global gate is {gate_transition_label(program.get('next_gate'))}"
            )
        if (
            not profile_matches(selected_slice, args.profile)
            or not platform_matches(selected_slice, args.platform)
            or not gate_is_open(data, gates, selected_slice["wave"])
            or not slice_dependencies_done(selected_slice, tasks)
        ):
            raise SystemExit(
                "Paused capability is not eligible for the requested profile/platform, gate, or dependencies"
            )
    now = utc_now()
    campaign.update(
        status="ACTIVE",
        owner=agent,
        branch=branch,
        worktree=worktree,
        base_sha=base_sha,
        profile=args.profile,
        platform=args.platform,
        updated_at=now,
        pause_reason=None,
        lease=new_lease(agent, args.lease_hours),
    )
    capability["completion"]["status"] = "IN_PROGRESS"
    persist(args, data)


def command_capability_submit(args, data, capabilities, slices, tasks, gates) -> None:
    capability = get_capability(capabilities, args.capability)
    if (capability.get("campaign") or {}).get("status") != "ACTIVE":
        raise SystemExit("Capability campaign must be ACTIVE")
    require_active_lease(capability, args.agent, f"Capability {args.capability}")
    if any(s.get("completion", {}).get("status") != "APPROVED" for s in capability["slices"]):
        raise SystemExit("All slices must be independently approved before capability submission")
    if not args.evidence:
        raise SystemExit("Capability end-to-end evidence is required")
    capability["campaign"]["status"] = "REVIEW"
    capability["campaign"]["updated_at"] = utc_now()
    capability["campaign"]["lease"] = None
    capability["completion"].update(status="REVIEW", evidence=args.evidence, notes=args.note)
    persist(args, data)


def command_capability_review(args, data, capabilities, slices, tasks, gates) -> None:
    capability = get_capability(capabilities, args.capability)
    if (capability.get("campaign") or {}).get("status") != "REVIEW" or capability.get("completion", {}).get(
        "status"
    ) != "REVIEW":
        raise SystemExit("Capability must be submitted for REVIEW")
    reviewer = normalized_identity(args.reviewer, "Reviewer")
    if reviewer == (capability.get("campaign") or {}).get("owner"):
        raise SystemExit("Capability reviewer must be independent from the campaign owner")
    now = utc_now()
    if args.result == "approved":
        capability["campaign"]["status"] = "COMPLETE"
        capability["completion"].update(status="APPROVED", reviewer=reviewer, reviewed_at=now, notes=args.note)
    elif args.result == "changes-requested":
        capability["campaign"]["status"] = "PAUSED"
        capability["campaign"]["pause_reason"] = "Capability review changes requested"
        capability["completion"].update(status="CHANGES_REQUESTED", reviewer=reviewer, reviewed_at=now, notes=args.note)
    else:
        capability["campaign"]["status"] = "PAUSED"
        capability["campaign"]["pause_reason"] = args.note or "Capability review blocked"
        capability["completion"].update(status="BLOCKED", reviewer=reviewer, reviewed_at=now, notes=args.note)
    persist(args, data)


def command_slice_status(args, data, capabilities, slices, tasks, gates) -> None:
    slice_ = get(slices, args.slice, "slice")
    view = {
        k: slice_.get(k)
        for k in [
            "id",
            "title",
            "outcome",
            "wave",
            "priority",
            "deployment_profiles",
            "platform_targets",
            "status",
            "completion",
        ]
    }
    view["display"] = slice_display(slice_)
    view["tasks"] = [{"id": t["id"], "title": t["title"], "status": t["status"]} for t in slice_["tasks"]]
    print_yaml(view)


def command_slice_submit(args, data, capabilities, slices, tasks, gates) -> None:
    slice_ = get(slices, args.slice, "slice")
    capability = capabilities[slice_["id"].split(".")[0]]
    if (capability.get("campaign") or {}).get("status") != "ACTIVE":
        raise SystemExit("The parent capability campaign must be ACTIVE")
    require_active_lease(capability, args.agent, f"Capability {capability['id']}")
    wave_id = campaign_wave(capability)
    if wave_id is None or slice_.get("wave") != wave_id or current_slice(capability, wave_id) is not slice_:
        raise SystemExit("Only the current slice in the active capability-wave increment may be submitted")
    if any(t["status"] != "DONE" for t in slice_["tasks"]):
        raise SystemExit("Every task in the slice must be DONE")
    if not args.evidence:
        raise SystemExit("Slice integration/end-to-end evidence is required")
    slice_["status"] = "REVIEW"
    slice_["completion"].update(status="REVIEW", evidence=args.evidence, notes=args.note)
    persist(args, data)


def command_slice_review(args, data, capabilities, slices, tasks, gates) -> None:
    slice_ = get(slices, args.slice, "slice")
    if slice_.get("completion", {}).get("status") != "REVIEW":
        raise SystemExit("Slice must be submitted for REVIEW")
    reviewer = normalized_identity(args.reviewer, "Reviewer")
    capability = capabilities[slice_["id"].split(".")[0]]
    campaign = capability.get("campaign") or {}
    if campaign.get("status") != "ACTIVE" or campaign.get("wave") != slice_.get("wave"):
        raise SystemExit("Slice review must belong to the active capability-wave increment")
    if reviewer == (capability.get("campaign") or {}).get("owner"):
        raise SystemExit("Slice reviewer must be independent from the campaign owner")
    now = utc_now()
    if args.result == "approved":
        slice_["completion"].update(status="APPROVED", reviewer=reviewer, reviewed_at=now, notes=args.note)
        slice_["status"] = "DONE"
        wave_id = str(slice_["wave"])
        if capability_wave_complete(capability, wave_id) and any(
            candidate.get("completion", {}).get("status") != "APPROVED"
            for candidate in capability.get("slices", [])
            if candidate.get("wave") != wave_id
        ):
            campaign.update(
                status="PAUSED",
                pause_reason=(
                    f"Capability-wave increment {capability.get('alias', capability['id'])}/{wave_id} complete"
                ),
                pause_category="wave-complete",
                updated_at=now,
                lease=None,
            )
            capability["completion"]["status"] = "PAUSED"
    elif args.result == "changes-requested":
        slice_["completion"].update(status="CHANGES_REQUESTED", reviewer=reviewer, reviewed_at=now, notes=args.note)
        slice_["status"] = "IN_PROGRESS"
    else:
        slice_["completion"].update(status="BLOCKED", reviewer=reviewer, reviewed_at=now, notes=args.note)
        slice_["status"] = "BLOCKED"
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    persist(args, data)


def command_claim(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    require_execution_target(args.profile, args.platform)
    agent, branch, base_sha, worktree = git_execution_identity(
        args.file,
        agent=args.agent,
        branch=args.branch,
        base_sha=args.base_sha,
        worktree=args.worktree,
    )
    task = get(tasks, args.task, "task")
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    if task["status"] != "READY":
        raise SystemExit(f"Task is {task['status']}, not READY")
    if not profile_matches(task, args.profile) or not platform_matches(task, args.platform):
        raise SystemExit("Task is not eligible for the requested profile/platform")
    active = active_capabilities(capabilities)
    if not active:
        raise SystemExit(f"No ACTIVE capability campaign. Start {task['capability_id']} before claiming tasks.")
    if active[0]["id"] != task["capability_id"]:
        raise SystemExit(f"Active campaign is {active[0]['id']}; task belongs to {task['capability_id']}")
    require_active_lease(active[0], agent, f"Capability {active[0]['id']}")
    campaign = active[0]["campaign"]
    if args.profile != campaign.get("profile") or args.platform != campaign.get("platform"):
        raise SystemExit("Task claim profile/platform must match the active capability campaign")
    if campaign.get("scope") != "capability-wave" or campaign.get("wave") != task.get("wave"):
        raise SystemExit("Task is outside the active capability-wave increment")
    selected_slice = current_slice(active[0], str(campaign["wave"]))
    if selected_slice is None or selected_slice["id"] != task["slice_id"]:
        raise SystemExit("Task is outside the active campaign's current slice")
    now = utc_now()
    task.update(
        status="IN_PROGRESS",
        owner=agent,
        branch=branch,
        base_sha=base_sha,
        worktree=worktree,
        started_at=task.get("started_at") or now,
        updated_at=now,
        blocker=None,
        verification_state=None,
        lease=new_lease(agent, args.lease_hours),
    )
    persist(args, data)
    print(f"Claimed {task['id']} within {task['capability_id']} / {task['slice_id']}")


def command_block(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    if task["status"] not in {"IN_PROGRESS", "REVIEW"}:
        raise SystemExit(f"Task cannot be blocked from {task['status']}")
    require_task_campaign_lease(task, capabilities, args.agent)
    require_active_lease(task, args.agent, f"Task {task['id']}")
    task["status"] = "BLOCKED"
    task["blocker"] = {
        "reason": args.reason,
        "next_action": args.next_action,
        "recorded_at": utc_now(),
        "owner": task.get("owner"),
    }
    task["updated_at"] = utc_now()
    task["lease"] = None
    persist(args, data)


def command_renew(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    task = get(tasks, args.task, "task")
    if task["status"] not in {"IN_PROGRESS", "REVIEW"}:
        raise SystemExit("Only an IN_PROGRESS or REVIEW task lease may be renewed")
    if task.get("owner") != args.agent:
        raise SystemExit(f"Task {task['id']} is owned by {task.get('owner')}, not {args.agent}")
    require_task_campaign_lease(task, capabilities, args.agent)
    if lease_is_active(task):
        require_active_lease(task, args.agent, f"Task {task['id']}")
    task["lease"] = new_lease(args.agent, args.lease_hours)
    task["updated_at"] = utc_now()
    persist(args, data)
    print(f"Renewed task lease for {task['id']}")


def command_evidence(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    if task["status"] != "IN_PROGRESS":
        raise SystemExit("Evidence may be attached only while IN_PROGRESS")
    require_task_campaign_lease(task, capabilities, args.agent)
    require_active_lease(task, args.agent, f"Task {task['id']}")
    repo = discover_repository(args.file)
    evidence_path = Path(args.from_file).resolve()
    try:
        relative_evidence_path = evidence_path.relative_to(repo).as_posix()
    except ValueError as exc:
        raise SystemExit("Evidence manifest must be stored inside the repository") from exc
    if not relative_evidence_path.startswith("artifacts/evidence/"):
        raise SystemExit("Evidence manifest must be stored under artifacts/evidence")
    if any(reference.get("path") == relative_evidence_path for reference in task.get("evidence", [])):
        raise SystemExit(f"Evidence manifest is already attached: {relative_evidence_path}")
    try:
        payload = evidence_path.read_bytes()
        manifest = parse_evidence_payload(payload, evidence_path.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid evidence manifest: {exc}") from exc
    payload_sha256 = evidence_sha256(payload)
    existing_evidence = task.get("evidence", [])
    if any(
        reference.get("sha256") == payload_sha256 or reference.get("commit") == manifest.get("commit")
        for reference in existing_evidence
    ):
        raise SystemExit("Logically duplicate evidence content or commit is already attached")
    supersedes = manifest.get("supersedes")
    if supersedes is not None and not isinstance(supersedes, dict):
        raise SystemExit("supersedes must be an object naming an attached manifest")
    superseded_path = (supersedes or {}).get("path")
    if existing_evidence and not superseded_path:
        raise SystemExit("Follow-up evidence must explicitly supersede an attached manifest")
    superseded_reference = next(
        (reference for reference in existing_evidence if reference.get("path") == superseded_path), None
    )
    if superseded_path and superseded_reference is None:
        raise SystemExit("supersedes.path must name an attached evidence manifest")
    expected_base_commit = (
        superseded_reference.get("commit") if superseded_reference is not None else task.get("base_sha")
    )
    errors = exact_commit_errors(
        task,
        manifest,
        repo,
        evidence_path=evidence_path,
        expected_base_commit=expected_base_commit,
    )
    if errors:
        raise SystemExit("Invalid evidence:\n- " + "\n- ".join(errors))
    task.setdefault("evidence", []).append(
        {
            "type": "criterion-manifest",
            "path": relative_evidence_path,
            "sha256": payload_sha256,
            "commit": manifest["commit"],
            "recorded_at": utc_now(),
        }
    )
    task["verification_state"] = "passed"
    task["updated_at"] = utc_now()
    persist(args, data)


def command_submit(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    if task["status"] != "IN_PROGRESS":
        raise SystemExit("Only IN_PROGRESS tasks may be submitted")
    require_task_campaign_lease(task, capabilities, args.agent)
    require_active_lease(task, args.agent, f"Task {task['id']}")
    if task.get("verification_state") != "passed" or not task.get("evidence"):
        raise SystemExit("Verification must pass and evidence must be attached before REVIEW")
    task["status"] = "REVIEW"
    task["updated_at"] = utc_now()
    task["implementation_notes"] = ((task.get("implementation_notes") or "") + "\n" + args.note).strip()
    persist(args, data)


def command_review(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    if task["status"] != "REVIEW":
        raise SystemExit("Only REVIEW tasks may be reviewed")
    reviewer = normalized_identity(args.reviewer, "Reviewer")
    if reviewer == task.get("owner"):
        raise SystemExit("Task reviewer must be independent from the task owner")
    now = utc_now()
    task["review"] = {"reviewer": reviewer, "result": args.result, "reviewed_at": now, "notes": args.note}
    if args.result == "approved":
        task["status"] = "DONE"
        task["completed_at"] = now
        task["lease"] = None
    elif args.result == "changes-requested":
        task["status"] = "IN_PROGRESS"
        task["verification_state"] = None
        require_positive_lease_hours(args.lease_hours)
        task["lease"] = new_lease(task["owner"], args.lease_hours)
    else:
        task["status"] = "BLOCKED"
        task["lease"] = None
        task["blocker"] = {
            "reason": args.note or "Reviewer blocked the task",
            "next_action": "Resolve review blocker",
            "recorded_at": now,
            "owner": task.get("owner"),
        }
    task["updated_at"] = now
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    persist(args, data)


def command_reopen(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    agent = normalized_identity(args.agent, "Agent")
    task = get(tasks, args.task, "task")
    if task["status"] not in {"BLOCKED", "REVIEW", "DONE"}:
        raise SystemExit(f"Task cannot be reopened from {task['status']}")
    capability = require_task_campaign_lease(task, capabilities, agent)
    if current_slice(capability, campaign_wave(capability)) is not slices[task["slice_id"]]:
        raise SystemExit("Only a task in the active capability-wave increment's current slice may be reopened")
    if not task_can_be_ready(data, capabilities, slices, tasks, gates, task):
        raise SystemExit("Task cannot be reopened while dependencies or the activation gate are incomplete")
    if any(gate.get("status") == "APPROVED" and gate.get("after_wave") == task.get("wave") for gate in gates.values()):
        raise SystemExit("Task cannot be reopened after its wave release gate is APPROVED")
    lease = task.get("lease")
    if lease_is_active(task) and lease and lease.get("claimed_by") != agent:
        raise SystemExit(f"Task {task['id']} has an active lease owned by {lease.get('claimed_by')}")
    task.update(
        status="IN_PROGRESS",
        owner=agent,
        updated_at=utc_now(),
        completed_at=None,
        verification_state=None,
        blocker=None,
        cancellation=None,
        review={"reviewer": None, "result": None, "reviewed_at": None, "notes": f"Reopened: {args.reason}"},
        lease=new_lease(agent, args.lease_hours),
    )
    persist(args, data)


def command_cancel(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    if task["status"] in {"DONE", "CANCELLED"}:
        raise SystemExit(f"{task['status']} tasks cannot transition to CANCELLED")
    actor = normalized_identity(args.actor, "Cancellation actor")
    capability = require_task_campaign_lease(task, capabilities, actor)
    if current_slice(capability, campaign_wave(capability)) is not slices[task["slice_id"]]:
        raise SystemExit("Only a task in the active capability-wave increment's current slice may be cancelled")
    if task["status"] in {"IN_PROGRESS", "REVIEW"}:
        require_active_lease(task, actor, f"Task {task['id']}")
    task["status"] = "CANCELLED"
    task["cancellation"] = {
        "reason": args.reason,
        "replacement": args.replacement,
        "cancelled_by": actor,
        "cancelled_at": utc_now(),
    }
    task["lease"] = None
    task["updated_at"] = utc_now()
    persist(args, data)


def command_gate_status(args, data, capabilities, slices, tasks, gates) -> None:
    if args.gate:
        gate = dict(get(gates, args.gate, "gate"))
        gate["display"] = gate_transition_label(gate)
        print_yaml(gate)
    else:
        for gate in data["release_gates"]:
            print(f"{gate_transition_label(gate)}\t{gate['status']}\t{gate['name']}")


def command_gate_approve(args, data, capabilities, slices, tasks, gates) -> None:
    gate = get(gates, args.gate, "gate")
    if gate.get("status") != "PENDING":
        raise SystemExit("Only a PENDING release gate may be approved")
    approver = normalized_identity(args.approver, "Release-gate approver")
    if not args.evidence:
        raise SystemExit("At least one evidence reference is required")
    ordered_gates = [candidate for candidate in data.get("release_gates", []) if isinstance(candidate, dict)]
    gate_index = next(index for index, candidate in enumerate(ordered_gates) if candidate.get("id") == gate["id"])
    prior_pending = [
        str(candidate.get("id")) for candidate in ordered_gates[:gate_index] if candidate.get("status") != "APPROVED"
    ]
    if prior_pending:
        raise SystemExit(
            f"Release gate {gate['id']} cannot approve before upstream gate {prior_pending[0]} is APPROVED"
        )
    incomplete = sorted(
        task["id"] for task in tasks.values() if task.get("wave") == gate.get("after_wave") and task["status"] != "DONE"
    )
    if incomplete:
        raise SystemExit(
            f"Release gate {gate['id']} cannot approve before every {gate.get('after_wave')} task is DONE; "
            f"first incomplete task: {incomplete[0]}"
        )
    incomplete_slices = sorted(
        slice_["id"]
        for slice_ in slices.values()
        if slice_.get("wave") == gate.get("after_wave") and slice_.get("completion", {}).get("status") != "APPROVED"
    )
    if incomplete_slices:
        raise SystemExit(
            f"Release gate {gate['id']} cannot approve before every {gate.get('after_wave')} slice is independently "
            f"approved; first incomplete slice: {incomplete_slices[0]}"
        )
    gate["status"] = "APPROVED"
    gate["approval"] = {
        "approved_by": approver,
        "approved_at": utc_now(),
        "evidence": args.evidence,
        "notes": args.note,
    }
    for wid in gate.get("unlocks_waves", []):
        for task in tasks.values():
            if task["wave"] == wid and task["status"] == "DEFERRED":
                task["status"] = "NOT_STARTED"
                task["updated_at"] = utc_now()
        for slice_ in slices.values():
            if slice_["wave"] == wid and slice_["status"] == "DEFERRED":
                slice_["status"] = "NOT_STARTED"
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    persist(args, data)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", default="planning/backlog.yaml")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("status")
    n = sub.add_parser("next")
    n.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    n.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    nc = sub.add_parser("next-capability")
    nc.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    nc.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    sh = sub.add_parser("show")
    sh.add_argument("task")
    cap = sub.add_parser("capability")
    cs = cap.add_subparsers(dest="cap_command", required=True)
    cstat = cs.add_parser("status")
    cstat.add_argument("capability", nargs="?")
    cprep = cs.add_parser("prepare")
    cprep.add_argument("capability")
    cstart = cs.add_parser("start")
    cstart.add_argument("capability")
    cstart.add_argument("--wave", required=True)
    cstart.add_argument("--agent", required=True)
    cstart.add_argument("--branch", required=True)
    cstart.add_argument("--base-sha", required=True)
    cstart.add_argument("--worktree", required=True)
    cstart.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    cstart.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    cstart.add_argument("--lease-hours", type=int, default=24)
    cpause = cs.add_parser("pause")
    cpause.add_argument("capability")
    cpause.add_argument(
        "--category",
        choices=[
            "infeasible",
            "external-dependency",
            "hardware-unavailable",
            "human-decision",
            "approved-design-gate",
            "wave-complete",
        ],
        required=True,
    )
    cpause.add_argument("--agent", required=True)
    cpause.add_argument("--reason", required=True)
    crenew = cs.add_parser("renew")
    crenew.add_argument("capability")
    crenew.add_argument("--agent", required=True)
    crenew.add_argument("--lease-hours", type=int, default=24)
    cresume = cs.add_parser("resume")
    cresume.add_argument("capability")
    cresume.add_argument("--agent", required=True)
    cresume.add_argument("--branch", required=True)
    cresume.add_argument("--base-sha", required=True)
    cresume.add_argument("--worktree", required=True)
    cresume.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    cresume.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    cresume.add_argument("--lease-hours", type=int, default=24)
    csubmit = cs.add_parser("submit")
    csubmit.add_argument("capability")
    csubmit.add_argument("--agent", required=True)
    csubmit.add_argument("--evidence", action="append", required=True)
    csubmit.add_argument("--note", default="")
    creview = cs.add_parser("review")
    creview.add_argument("capability")
    creview.add_argument("--reviewer", required=True)
    creview.add_argument("--result", choices=["approved", "changes-requested", "blocked"], required=True)
    creview.add_argument("--note", default="")
    sl = sub.add_parser("slice")
    ss = sl.add_subparsers(dest="slice_command", required=True)
    sstat = ss.add_parser("status")
    sstat.add_argument("slice")
    ssubmit = ss.add_parser("submit")
    ssubmit.add_argument("slice")
    ssubmit.add_argument("--agent", required=True)
    ssubmit.add_argument("--evidence", action="append", required=True)
    ssubmit.add_argument("--note", default="")
    sreview = ss.add_parser("review")
    sreview.add_argument("slice")
    sreview.add_argument("--reviewer", required=True)
    sreview.add_argument("--result", choices=["approved", "changes-requested", "blocked"], required=True)
    sreview.add_argument("--note", default="")
    claim = sub.add_parser("claim")
    claim.add_argument("task")
    claim.add_argument("--agent", required=True)
    claim.add_argument("--branch", required=True)
    claim.add_argument("--base-sha", required=True)
    claim.add_argument("--worktree", required=True)
    claim.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    claim.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    claim.add_argument("--lease-hours", type=int, default=8)
    block = sub.add_parser("block")
    block.add_argument("task")
    block.add_argument("--agent", required=True)
    block.add_argument("--reason", required=True)
    block.add_argument("--next-action", required=True)
    renew = sub.add_parser("renew")
    renew.add_argument("task")
    renew.add_argument("--agent", required=True)
    renew.add_argument("--lease-hours", type=int, default=8)
    checks = sub.add_parser("checks")
    checks.add_argument("task")
    ev = sub.add_parser("evidence")
    ev.add_argument("task")
    ev.add_argument("--agent", required=True)
    ev.add_argument("--from", dest="from_file", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("task")
    submit.add_argument("--agent", required=True)
    submit.add_argument("--note", default="")
    rev = sub.add_parser("review")
    rev.add_argument("task")
    rev.add_argument("--reviewer", required=True)
    rev.add_argument("--result", choices=["approved", "changes-requested", "blocked"], required=True)
    rev.add_argument("--lease-hours", type=int, default=8)
    rev.add_argument("--note", default="")
    reopen = sub.add_parser("reopen")
    reopen.add_argument("task")
    reopen.add_argument("--reason", required=True)
    reopen.add_argument("--agent", required=True)
    reopen.add_argument("--lease-hours", type=int, default=8)
    cancel = sub.add_parser("cancel")
    cancel.add_argument("task")
    cancel.add_argument("--reason", required=True)
    cancel.add_argument("--replacement")
    cancel.add_argument("--actor", required=True)
    gate = sub.add_parser("gate")
    gs = gate.add_subparsers(dest="gate_command", required=True)
    gst = gs.add_parser("status")
    gst.add_argument("gate", nargs="?")
    ga = gs.add_parser("approve")
    ga.add_argument("gate")
    ga.add_argument("--approver", required=True)
    ga.add_argument("--evidence", action="append", required=True)
    ga.add_argument("--note", default="")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.source_sha256 = hashlib.sha256(Path(args.file).read_bytes()).hexdigest()
    except OSError as exc:
        raise SystemExit(f"Cannot load backlog {args.file}: {exc}") from exc
    data, capabilities, slices, tasks, gates = load(args.file)
    args.source_identity = identity_snapshot(data)
    args.repo_root = discover_repository(args.file)
    if args.command == "validate":
        command_validate(args, data, capabilities, slices, tasks, gates)
    elif args.command == "status":
        command_status(args, data, capabilities, slices, tasks, gates)
    elif args.command == "next":
        command_next(args, data, capabilities, slices, tasks, gates)
    elif args.command == "next-capability":
        command_next_capability(args, data, capabilities, slices, tasks, gates)
    elif args.command == "show":
        task = dict(get(tasks, args.task, "task"))
        task["displayCapability"] = capability_display(capabilities[task["capability_id"]])
        task["displaySlice"] = slice_display(slices[task["slice_id"]])
        print_yaml(task)
    elif args.command == "capability" and args.cap_command == "prepare":
        command_capability_prepare(args, data, capabilities, slices, tasks, gates)
    elif args.command == "capability" and args.cap_command == "status":
        command_capability_status(args, data, capabilities, slices, tasks, gates)
    elif args.command == "capability" and args.cap_command == "start":
        command_capability_start(args, data, capabilities, slices, tasks, gates)
    elif args.command == "capability" and args.cap_command == "pause":
        command_capability_pause(args, data, capabilities, slices, tasks, gates)
    elif args.command == "capability" and args.cap_command == "renew":
        command_capability_renew(args, data, capabilities, slices, tasks, gates)
    elif args.command == "capability" and args.cap_command == "resume":
        command_capability_resume(args, data, capabilities, slices, tasks, gates)
    elif args.command == "capability" and args.cap_command == "submit":
        command_capability_submit(args, data, capabilities, slices, tasks, gates)
    elif args.command == "capability" and args.cap_command == "review":
        command_capability_review(args, data, capabilities, slices, tasks, gates)
    elif args.command == "slice" and args.slice_command == "status":
        command_slice_status(args, data, capabilities, slices, tasks, gates)
    elif args.command == "slice" and args.slice_command == "submit":
        command_slice_submit(args, data, capabilities, slices, tasks, gates)
    elif args.command == "slice" and args.slice_command == "review":
        command_slice_review(args, data, capabilities, slices, tasks, gates)
    elif args.command == "claim":
        command_claim(args, data, capabilities, slices, tasks, gates)
    elif args.command == "block":
        command_block(args, data, capabilities, slices, tasks, gates)
    elif args.command == "renew":
        command_renew(args, data, capabilities, slices, tasks, gates)
    elif args.command == "checks":
        for command in get(tasks, args.task, "task").get("verification_commands", []):
            print(command)
    elif args.command == "evidence":
        command_evidence(args, data, capabilities, slices, tasks, gates)
    elif args.command == "submit":
        command_submit(args, data, capabilities, slices, tasks, gates)
    elif args.command == "review":
        command_review(args, data, capabilities, slices, tasks, gates)
    elif args.command == "reopen":
        command_reopen(args, data, capabilities, slices, tasks, gates)
    elif args.command == "cancel":
        command_cancel(args, data, capabilities, slices, tasks, gates)
    elif args.command == "gate" and args.gate_command == "status":
        command_gate_status(args, data, capabilities, slices, tasks, gates)
    elif args.command == "gate" and args.gate_command == "approve":
        command_gate_approve(args, data, capabilities, slices, tasks, gates)
    else:
        parser.error("Unsupported command")


if __name__ == "__main__":
    main()
