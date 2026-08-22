#!/usr/bin/env python3
"""Research Observatory baseline 1.3 wave-campaign task controller.

The execution hierarchy is Roadmap -> durable Wave campaign -> capability
contribution -> ordered Slice -> Task -> Wave exit gate. Descriptive aliases are
human-facing; numeric IDs remain immutable evidence keys. Tasks remain the
atomic claim/evidence unit.
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
CAMPAIGN_SCOPES = {"wave", "amendment-hold", "capability-wave"}  # capability-wave is historical only.
COMPLETION_STATES = {"PENDING", "IN_PROGRESS", "REVIEW", "APPROVED", "CHANGES_REQUESTED", "BLOCKED", "PAUSED"}
CONTROL_TOOL_REVISION = 3
AMENDMENT_TERMINAL_STATES = {"ADOPTED", "DEFERRED", "WITHDRAWN"}
BOOTSTRAP_REVIEW_RESULTS = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes-requested",
    "BLOCKED": "blocked",
}
AMENDMENT_TASK_IMMUTABLE_FIELDS = (
    "id",
    "amendment_id",
    "title",
    "objective",
    "dependencies",
    "acceptance_criteria",
    "verification_commands",
    "packet_task_sha256",
)
REVIEW_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
VERIFICATION_COMMAND_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
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
    for amendment in document.get("wave_amendments", []):
        for task in amendment.get("tasks", []):
            task.pop("_amendment_id", None)
            task.pop("_position", None)
            task.pop("_target_wave", None)
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


def amendment_identity_snapshot(data: dict[str, Any]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (str(amendment["id"]), tuple(str(task["id"]) for task in amendment.get("tasks", [])))
        for amendment in data.get("wave_amendments", [])
    )


def approved_wave_snapshot(data: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            str(wave["id"]),
            hashlib.sha256(
                json.dumps(wave.get("approval") or {}, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        )
        for wave in data.get("waves", [])
        if (wave.get("approval") or {}).get("status") == "APPROVED"
    )


def amendment_history_snapshot(data: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    snapshot: dict[str, tuple[str, ...]] = {}
    for amendment in data.get("wave_amendments", []):
        amendment_id = str(amendment["id"])
        snapshot[amendment_id] = tuple(
            json.dumps(event, sort_keys=True, separators=(",", ":"))
            for event in (amendment.get("lifecycle") or {}).get("history", [])
        )
        snapshot[f"{amendment_id}:bootstrap"] = tuple(
            json.dumps(attempt, sort_keys=True, separators=(",", ":"))
            for attempt in (amendment.get("bootstrap") or {}).get("attempts", [])
        )
        snapshot[f"{amendment_id}:exit-review"] = tuple(
            json.dumps(attempt, sort_keys=True, separators=(",", ":"))
            for attempt in ((amendment.get("completion") or {}).get("exit_review_control") or {}).get("attempts", [])
        )
    return snapshot


def wave_checkpoint_history_snapshot(data: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    return {
        str(wave["id"]): tuple(
            json.dumps(checkpoint, sort_keys=True, separators=(",", ":")) for checkpoint in wave.get("checkpoints", [])
        )
        for wave in data.get("waves", [])
    }


def task_review_history_snapshot(data: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    snapshot: dict[str, tuple[str, ...]] = {}
    task_documents = [
        task
        for capability in data.get("capabilities", [])
        for slice_ in capability.get("slices", [])
        for task in slice_.get("tasks", [])
    ]
    task_documents.extend(task for amendment in data.get("wave_amendments", []) for task in amendment.get("tasks", []))
    for task in task_documents:
        control = task.get("review_control") or {}
        snapshot[str(task["id"])] = tuple(
            json.dumps(attempt, sort_keys=True, separators=(",", ":")) for attempt in control.get("attempts", [])
        )
    return snapshot


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
    seen_amendment_ids: set[str] = set()
    for amendment in data.get("wave_amendments", []):
        amendment_id = str(amendment["id"])
        if amendment_id in seen_amendment_ids:
            raise SystemExit(f"Duplicate Wave amendment ID: {amendment_id}")
        seen_amendment_ids.add(amendment_id)
        for position, task in enumerate(amendment.get("tasks", [])):
            task_id = str(task["id"])
            if task_id in tasks:
                raise SystemExit(f"Duplicate task ID: {task_id}")
            task["_amendment_id"] = amendment_id
            task["_position"] = position
            task["_target_wave"] = amendment.get("target_wave")
            tasks[task_id] = task
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
    expected_amendment_identity: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
    expected_approved_waves: tuple[tuple[str, str], ...] | None = None,
    expected_amendment_history: dict[str, tuple[str, ...]] | None = None,
    expected_task_review_history: dict[str, tuple[str, ...]] | None = None,
    expected_wave_checkpoint_history: dict[str, tuple[str, ...]] | None = None,
    schema_path: Path | None = None,
    repo: Path | None = None,
) -> None:
    document = serializable_backlog(data)
    if expected_identity is not None and identity_snapshot(document) != expected_identity:
        raise SystemExit(
            "Stable backlog IDs or their hierarchy changed during a taskctl transition; no update was written"
        )
    if expected_amendment_identity is not None and amendment_identity_snapshot(document) != expected_amendment_identity:
        raise SystemExit("Wave amendment IDs or task inventory changed outside the materialization transition")
    if expected_approved_waves is not None and approved_wave_snapshot(document) != expected_approved_waves:
        raise SystemExit("An immutable APPROVED Wave approval changed during a taskctl transition")
    if expected_amendment_history is not None:
        current_history = amendment_history_snapshot(document)
        for amendment_id, prior in expected_amendment_history.items():
            current = current_history.get(amendment_id)
            if current is None or current[: len(prior)] != prior:
                raise SystemExit(f"Append-only lifecycle history changed for {amendment_id}")
    if expected_task_review_history is not None:
        current_history = task_review_history_snapshot(document)
        for task_id, prior in expected_task_review_history.items():
            current = current_history.get(task_id)
            if current is None or current[: len(prior)] != prior:
                raise SystemExit(f"Append-only task review history changed for {task_id}")
    if expected_wave_checkpoint_history is not None:
        current_history = wave_checkpoint_history_snapshot(document)
        for wave_id, prior in expected_wave_checkpoint_history.items():
            current = current_history.get(wave_id)
            if current is None or current[: len(prior)] != prior:
                raise SystemExit(f"Append-only Wave checkpoint history changed for {wave_id}")
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
        expected_amendment_identity=getattr(args, "source_amendment_identity", None),
        expected_approved_waves=getattr(args, "source_approved_waves", None),
        expected_amendment_history=getattr(args, "source_amendment_history", None),
        expected_task_review_history=getattr(args, "source_task_review_history", None),
        expected_wave_checkpoint_history=getattr(args, "source_wave_checkpoint_history", None),
        repo=getattr(args, "repo_root", None),
    )


def wave_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {wave["id"]: wave for wave in data.get("waves", [])}


def wave_approval_base_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["wave_id"]): item for item in data.get("wave_approval_bases", [])}


def wave_amendment_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in data.get("wave_amendments", [])}


def active_amendment_campaigns(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        amendment
        for amendment in data.get("wave_amendments", [])
        if (amendment.get("campaign") or {}).get("status") == "ACTIVE"
    ]


def blocking_wave_amendments(data: dict[str, Any], wave_id: str) -> list[dict[str, Any]]:
    return [
        amendment
        for amendment in data.get("wave_amendments", [])
        if amendment.get("target_wave") == wave_id
        and amendment.get("kind") == "gate-integrity-safety-defect"
        and (amendment.get("lifecycle") or {}).get("status") not in AMENDMENT_TERMINAL_STATES
    ]


def approved_unbootstrapped_amendment(backlog_path: str, data: dict[str, Any], wave_id: str) -> dict[str, Any] | None:
    """Project an approved interrupt before B00 can represent it in the backlog."""
    if data.get("wave_amendments"):
        return None
    repo = Path(backlog_path).resolve().parent.parent
    approval_dir = repo / "planning" / "wave-amendment-approvals"
    for path in sorted(approval_dir.glob("W*.A*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            continue
        if (
            record.get("status") == "APPROVED"
            and record.get("targetWave") == wave_id
            and record.get("changeRequestId")
            and record.get("bootstrapUnit")
        ):
            effective = record.get("effectiveBase") or {}
            relative = path.relative_to(repo).as_posix()
            return {
                "id": record.get("amendmentId"),
                "change_request_id": record.get("changeRequestId"),
                "target_wave": wave_id,
                "kind": "gate-integrity-safety-defect",
                "approval_reference": {
                    "path": relative,
                    "introduction_commit": approval_introduction_commit(repo, relative),
                },
                "lifecycle": {"status": "APPROVED", "history": []},
                "bootstrap": {"id": record.get("bootstrapUnit"), "status": "PENDING"},
                "campaign": None,
                "tasks": [],
                "_base_packet": effective.get("originalPacketCommit"),
                "_legacy_amendment": effective.get("legacyAmendmentId"),
                "_legacy_packet": effective.get("legacyAmendmentPacketCommit"),
            }
    return None


def amendment_for_task(data: dict[str, Any], task: dict[str, Any]) -> dict[str, Any] | None:
    amendment_id = task.get("_amendment_id") or task.get("amendment_id")
    return wave_amendment_map(data).get(str(amendment_id)) if amendment_id else None


def task_wave(task: dict[str, Any]) -> str | None:
    value = task.get("wave", task.get("_target_wave"))
    return str(value) if value is not None else None


def active_wave_campaigns(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [wave for wave in data.get("waves", []) if (wave.get("campaign") or {}).get("status") == "ACTIVE"]


def wave_complete(
    wave_id: str,
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    data: dict[str, Any] | None = None,
) -> bool:
    wave_slices = [slice_ for slice_ in slices.values() if slice_.get("wave") == wave_id]
    amendments = wave_amendment_map(data or {})
    wave_tasks = [
        task
        for task in tasks.values()
        if task_wave(task) == wave_id
        and not (
            amendment_for_task(data or {}, task) is not None
            and (
                amendments.get(str(task.get("_amendment_id") or task.get("amendment_id")), {}).get("lifecycle") or {}
            ).get("status")
            in {"DEFERRED", "WITHDRAWN"}
        )
    ]
    return (
        bool(wave_slices)
        and bool(wave_tasks)
        and all(task.get("status") == "DONE" for task in wave_tasks)
        and all(slice_.get("completion", {}).get("status") == "APPROVED" for slice_ in wave_slices)
    )


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
            task["id"] for task in tasks.values() if task_wave(task) == wave_id and task.get("status") != "DONE"
        )
        incomplete_slices = sorted(
            slice_["id"]
            for slice_ in slices.values()
            if slice_.get("wave") == wave_id and slice_.get("completion", {}).get("status") != "APPROVED"
        )
        wave = wave_map(data).get(wave_id, {})
        wave_completion = (wave.get("completion") or {}).get("status")
        incomplete_wave_review = wave_completion != "APPROVED"
        if not incomplete_tasks and not incomplete_slices and not incomplete_wave_review:
            continue
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
                "wave_completion": wave_completion,
            }
        amendments = blocking_wave_amendments(data, wave_id)
        if amendments:
            return {
                "state": "AMENDMENT_INTERRUPTED",
                "current_wave": wave_id,
                "blocked_wave": wave_id,
                "next_gate": gate_after_wave(data, wave_id),
                "amendment": amendments[0],
                "incomplete_tasks": incomplete_tasks,
                "incomplete_slices": incomplete_slices,
                "wave_completion": wave_completion,
            }
        return {
            "state": "ACTIVE_WAVE",
            "current_wave": wave_id,
            "blocked_wave": None,
            "next_gate": gate_after_wave(data, wave_id),
            "incomplete_tasks": incomplete_tasks,
            "incomplete_slices": incomplete_slices,
            "wave_completion": wave_completion,
        }
    return {
        "state": "COMPLETE",
        "current_wave": None,
        "blocked_wave": None,
        "next_gate": None,
        "incomplete_tasks": [],
        "incomplete_slices": [],
        "wave_completion": None,
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
            if dep.endswith(".B00") and dep == f"{task.get('_amendment_id') or task.get('amendment_id')}.B00":
                continue
            if dep not in tasks:
                errors.append(f"{tid}: missing dependency {dep}")

    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(task_id: str) -> list[str] | None:
        state[task_id] = 1
        stack.append(task_id)
        for dependency in tasks[task_id].get("dependencies", []):
            if dependency.endswith(".B00"):
                continue
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
    return all(
        (dep.endswith(".B00") and dep == f"{task.get('_amendment_id') or task.get('amendment_id')}.B00")
        or tasks.get(dep, {}).get("status") == "DONE"
        for dep in task.get("dependencies", [])
    )


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
    amendment = amendment_for_task(data, task)
    if amendment is not None:
        bootstrap = amendment.get("bootstrap") or {}
        campaign = amendment.get("campaign") or {}
        return (
            bootstrap.get("status") == "APPROVED"
            and campaign.get("status") == "ACTIVE"
            and task_dependencies_done(task, tasks)
        )
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
    wave_id = task_wave(task) or "W99"
    priority = str(task.get("priority", "P0"))
    return int(wave_id[1:]), int(priority[1:]), task["id"]


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


def ready_tasks_in_wave(
    data: dict[str, Any],
    wave: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    profile: str,
    platform: str,
) -> list[dict[str, Any]]:
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    return sorted(
        [
            task
            for task in tasks.values()
            if task_wave(task) == wave.get("id")
            and task.get("status") == "READY"
            and profile_matches(task, profile)
            and platform_matches(task, platform)
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
    task: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    actor: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if data is not None:
        amendment = amendment_for_task(data, task)
        if amendment is not None:
            campaign = amendment.get("campaign") or {}
            if campaign.get("status") != "ACTIVE" or campaign.get("scope") != "wave-amendment":
                raise SystemExit(f"Wave amendment {amendment['id']} campaign is not ACTIVE")
            require_active_lease(amendment, actor, f"Wave amendment {amendment['id']}")
            return amendment
    if data is not None:
        active_waves = active_wave_campaigns(data)
        if active_waves:
            wave = active_waves[0]
            campaign = wave.get("campaign") or {}
            if wave.get("id") != task.get("wave") or campaign.get("scope") != "wave":
                raise SystemExit(f"Task {task['id']} is outside the active Wave campaign {wave.get('id')}")
            require_active_lease(wave, actor, f"Wave {wave['id']}")
            return wave

    # Historical capability-wave campaigns remain readable and resumable only
    # for already-recorded ledgers. New work starts through `taskctl wave start`.
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


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def normalized_deferred_checks(selection: dict[str, Any]) -> list[str]:
    deferred = selection.get("deferred", [])
    if isinstance(deferred, str):
        return [deferred] if deferred.strip() else []
    if isinstance(deferred, list) and all(isinstance(item, str) and item.strip() for item in deferred):
        return list(dict.fromkeys(deferred))
    return []


def selected_command_ids(selection: dict[str, Any], *, require_nonempty: bool = False) -> list[str]:
    value = selection.get("selectedCommandIds", [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and VERIFICATION_COMMAND_ID_PATTERN.fullmatch(item) for item in value
    ):
        raise ValueError("verificationSelection.selectedCommandIds must contain privacy-safe command IDs")
    if len(value) != len(set(value)):
        raise ValueError("verificationSelection.selectedCommandIds must be unique")
    if require_nonempty and not value:
        raise ValueError("Atomic submission requires non-empty verificationSelection.selectedCommandIds")
    return list(value)


def canonical_verification_command_ids(repo: Path) -> set[str]:
    contract_path = repo / "verification-profiles.json"
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load canonical verification command inventory: {exc}") from exc
    commands = contract.get("commands")
    if not isinstance(commands, dict) or not all(
        isinstance(command_id, str) and VERIFICATION_COMMAND_ID_PATTERN.fullmatch(command_id) for command_id in commands
    ):
        raise ValueError("canonical verification command inventory is invalid")
    return set(commands)


def require_canonical_selected_command_ids(command_ids: list[str], repo: Path) -> None:
    unknown = sorted(set(command_ids) - canonical_verification_command_ids(repo))
    if unknown:
        raise ValueError(f"unknown canonical verification command IDs: {', '.join(unknown)}")


def task_submission_packet_sha256(packet: dict[str, Any]) -> str:
    payload = copy.deepcopy(packet)
    payload.pop("packet_sha256", None)
    return canonical_json_sha256(payload)


def task_open_findings(attempts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    open_findings: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        for closure in attempt.get("closures", []):
            open_findings.pop(str(closure.get("finding_id")), None)
        for finding in attempt.get("findings", []):
            open_findings[str(finding.get("id"))] = finding
    return open_findings


def task_submission_packet_errors(
    task: dict[str, Any],
    packet: dict[str, Any],
    *,
    expected_id: str,
    expected_prior_id: str | None,
    expected_prior_submission: dict[str, Any] | None,
    expected_open_ids: list[str],
    repo: Path | None,
) -> list[str]:
    task_id = str(task.get("id"))
    errors: list[str] = []
    if packet.get("id") != expected_id:
        errors.append(f"{task_id}: task review submission IDs are not sequential")
    if packet.get("prior_attempt_id") != expected_prior_id:
        errors.append(f"{task_id}: submission does not link to the prior review attempt")
    if sorted(str(item) for item in packet.get("open_finding_ids", [])) != expected_open_ids:
        errors.append(f"{task_id}: remediation submission does not replay the exact open finding IDs")
    if packet.get("acceptance_criteria_sha256") != canonical_json_sha256(task.get("acceptance_criteria", [])):
        errors.append(f"{task_id}: frozen acceptance criteria hash differs from the task")
    if packet.get("packet_sha256") != task_submission_packet_sha256(packet):
        errors.append(f"{task_id}: immutable task submission packet hash mismatch")
    reference = packet.get("evidence_reference") or {}
    if reference not in task.get("evidence", []):
        errors.append(f"{task_id}: submission evidence reference is not attached to the task")
    if reference.get("commit") != packet.get("candidate_commit"):
        errors.append(f"{task_id}: submission candidate differs from its evidence reference")
    if packet.get("submitted_by") != task.get("owner"):
        errors.append(f"{task_id}: submission author differs from the task owner")
    if repo is None:
        return errors
    relative = str(reference.get("path") or "")
    pure = PurePosixPath(relative)
    if not relative.startswith("artifacts/evidence/") or pure.is_absolute() or ".." in pure.parts:
        return [*errors, f"{task_id}: unsafe task submission evidence path"]
    try:
        payload = repo.joinpath(*pure.parts).read_bytes()
        manifest = parse_evidence_payload(payload, pure.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [*errors, f"{task_id}: cannot load task submission evidence: {exc}"]
    selection = manifest.get("verificationSelection")
    checks = manifest.get("checks")
    selected_checks = (
        [str(item.get("command")) for item in checks if isinstance(item, dict) and item.get("command")]
        if isinstance(checks, list)
        else []
    )
    if not isinstance(selection, dict):
        errors.append(f"{task_id}: controlled submission lacks structured verificationSelection")
        selection = {}
    try:
        manifest_command_ids = selected_command_ids(selection)
    except ValueError as exc:
        errors.append(f"{task_id}: {exc}")
        manifest_command_ids = []
    packet_command_ids = packet.get("selected_command_ids", [])
    if packet_command_ids != manifest_command_ids:
        errors.append(f"{task_id}: frozen command-ID selection differs from its evidence manifest")
    try:
        require_canonical_selected_command_ids(manifest_command_ids, repo)
    except ValueError as exc:
        errors.append(f"{task_id}: {exc}")
    if packet_command_ids != manifest_command_ids and isinstance(packet_command_ids, list):
        try:
            require_canonical_selected_command_ids(packet_command_ids, repo)
        except ValueError as exc:
            errors.append(f"{task_id}: {exc}")
    if packet.get("candidate_commit") != manifest.get("commit"):
        errors.append(f"{task_id}: submission candidate differs from its evidence manifest")
    if packet.get("base_commit") != manifest.get("baseCommit"):
        errors.append(f"{task_id}: submission base differs from its evidence manifest")
    if packet.get("branch") != manifest.get("branch"):
        errors.append(f"{task_id}: submission branch differs from its evidence manifest")
    if packet.get("changed_paths") != manifest.get("changedFiles"):
        errors.append(f"{task_id}: frozen changed-path identity differs from its evidence manifest")
    if packet.get("selected_checks") != selected_checks:
        errors.append(f"{task_id}: frozen selected-check identity differs from its evidence manifest")
    if packet.get("deferred_checks") != normalized_deferred_checks(selection):
        errors.append(f"{task_id}: frozen deferred-check identity differs from its evidence manifest")
    if packet.get("selection_rationale") != selection.get("riskAnalysis"):
        errors.append(f"{task_id}: frozen verification rationale differs from its evidence manifest")
    if packet.get("selection_sha256") != canonical_json_sha256(selection):
        errors.append(f"{task_id}: frozen verification-selection hash differs from its evidence manifest")
    if expected_prior_submission is not None:
        supersedes = manifest.get("supersedes")
        prior_reference = expected_prior_submission.get("evidence_reference") or {}
        if not isinstance(supersedes, dict) or any(
            supersedes.get(field) != prior_reference.get(field) for field in ("path", "sha256", "commit")
        ):
            errors.append(f"{task_id}: remediation evidence does not supersede the immediately preceding submission")
        if packet.get("base_commit") != expected_prior_submission.get("candidate_commit"):
            errors.append(f"{task_id}: remediation base is not the immediately preceding candidate")
    if int(expected_id[1:]) >= 3 and expected_open_ids:
        rationale = str(selection.get("riskAnalysis") or "")
        prior_rationale = str((expected_prior_submission or {}).get("selection_rationale") or "")
        if rationale == prior_rationale or any(finding_id not in rationale for finding_id in expected_open_ids):
            errors.append(
                f"{task_id}: remediation after round two requires expanded risk analysis naming every open finding"
            )
    return errors


def build_task_review_telemetry_event(task: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    submission = attempt.get("submission") or {}
    review = attempt.get("review") or {}
    submitted_at = submission.get("submitted_at")
    reviewed_at = review.get("reviewed_at")
    if not isinstance(submitted_at, str) or not isinstance(reviewed_at, str):
        raise ValueError("review telemetry requires submitted and reviewed timestamps")
    try:
        duration = (parse_time(reviewed_at) - parse_time(submitted_at)).total_seconds()
    except (TypeError, ValueError) as exc:
        raise ValueError("review telemetry timestamps are invalid") from exc
    if duration < 0:
        raise ValueError("review telemetry duration cannot be negative")
    duration_seconds = int(duration)
    outcome = review.get("result")
    if outcome not in {"approved", "changes-requested", "blocked"}:
        raise ValueError("review telemetry outcome is invalid")
    counts = {severity: 0 for severity in REVIEW_SEVERITY_ORDER}
    blocking = 0
    findings = attempt.get("findings") or []
    for finding in findings:
        severity = finding.get("severity")
        if severity not in counts:
            raise ValueError("review telemetry finding severity is invalid")
        counts[str(severity)] += 1
        if finding.get("blocking") is True:
            blocking += 1
    command_ids = submission.get("selected_command_ids", [])
    if not isinstance(command_ids, list) or not all(isinstance(item, str) for item in command_ids):
        raise ValueError("review telemetry command IDs are invalid")
    amendment_id = task.get("_amendment_id") or task.get("amendment_id")
    return {
        "task_id": str(task.get("id")),
        "amendment_id": str(amendment_id) if amendment_id is not None else None,
        "attempt_id": str(submission.get("id")),
        "submitted_at": submitted_at,
        "reviewed_at": reviewed_at,
        "duration_seconds": duration_seconds,
        "outcome": outcome,
        "finding_counts": {
            **counts,
            "blocking": blocking,
            "total": len(findings),
        },
        "command_ids": list(command_ids),
        "remediation": {
            "prior_attempt_id": submission.get("prior_attempt_id"),
            "replayed_finding_ids": sorted(str(item) for item in submission.get("open_finding_ids", [])),
            "closed_finding_ids": sorted(str(closure.get("finding_id")) for closure in attempt.get("closures", [])),
        },
    }


def task_review_telemetry_errors(
    task: dict[str, Any],
    attempt: dict[str, Any],
    repo: Path | None,
) -> list[str]:
    event = attempt.get("telemetry")
    submission = attempt.get("submission") or {}
    command_ids = submission.get("selected_command_ids")
    if event is None:
        if isinstance(command_ids, list) and command_ids:
            return [
                f"{task.get('id')}: prospective review attempt {submission.get('id')} "
                "lacks required privacy-safe telemetry"
            ]
        return []
    task_id = str(task.get("id"))
    errors: list[str] = []
    try:
        expected = build_task_review_telemetry_event(task, attempt)
    except ValueError as exc:
        return [f"{task_id}: {exc}"]
    if event != expected:
        errors.append(f"{task_id}: stored review telemetry differs from its exact privacy-safe projection")
    command_ids = expected["command_ids"]
    try:
        if not all(VERIFICATION_COMMAND_ID_PATTERN.fullmatch(item) for item in command_ids):
            raise ValueError("review telemetry contains a non-privacy-safe command ID")
        if len(command_ids) != len(set(command_ids)):
            raise ValueError("review telemetry command IDs are not unique")
        if repo is not None:
            require_canonical_selected_command_ids(command_ids, repo)
    except ValueError as exc:
        errors.append(f"{task_id}: {exc}")
    return errors


def task_review_telemetry_events(tasks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for task_id in sorted(tasks):
        for attempt in (tasks[task_id].get("review_control") or {}).get("attempts", []):
            event = attempt.get("telemetry")
            submission = attempt.get("submission") or {}
            if event is None and submission.get("selected_command_ids"):
                raise ValueError(
                    f"{task_id}: prospective review attempt {submission.get('id')} "
                    "lacks required privacy-safe telemetry"
                )
            if isinstance(event, dict):
                events.append(copy.deepcopy(event))
    return events


def task_review_control_errors(task: dict[str, Any], repo: Path | None) -> list[str]:
    control = task.get("review_control")
    if control is None:
        return []
    task_id = str(task.get("id"))
    errors: list[str] = []
    attempts = control.get("attempts") or []
    open_findings: dict[str, dict[str, Any]] = {}
    seen_finding_ids: set[str] = set()
    closed_finding_ids: set[str] = set()
    prior_id: str | None = None
    prior_submission: dict[str, Any] | None = None
    for position, attempt in enumerate(attempts, start=1):
        packet = attempt.get("submission") or {}
        expected_id = f"R{position:02d}"
        expected_open = sorted(open_findings)
        errors.extend(
            task_submission_packet_errors(
                task,
                packet,
                expected_id=expected_id,
                expected_prior_id=prior_id,
                expected_prior_submission=prior_submission,
                expected_open_ids=expected_open,
                repo=repo,
            )
        )
        if position >= 3 and expected_open and not str(packet.get("root_cause_analysis") or "").strip():
            errors.append(f"{task_id}: remediation after round two requires root-cause escalation")
        findings = attempt.get("findings") or []
        severities = [REVIEW_SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
        if severities != sorted(severities):
            errors.append(f"{task_id}: review findings are not severity-ranked")
        for closure in attempt.get("closures") or []:
            finding_id = str(closure.get("finding_id"))
            if finding_id not in open_findings or finding_id in closed_finding_ids:
                errors.append(f"{task_id}: review closure does not name one open prior finding")
            else:
                open_findings.pop(finding_id)
                closed_finding_ids.add(finding_id)
        for finding in findings:
            finding_id = str(finding.get("id"))
            criterion_index = finding.get("criterion_index")
            if finding_id in seen_finding_ids:
                errors.append(f"{task_id}: review finding ID {finding_id} is not globally unique")
            seen_finding_ids.add(finding_id)
            if type(criterion_index) is not int or not 1 <= criterion_index <= len(task.get("acceptance_criteria", [])):
                errors.append(f"{task_id}: review finding {finding_id} is outside the acceptance criteria")
            open_findings[finding_id] = finding
        review = attempt.get("review") or {}
        result = review.get("result")
        blocking_open = [item for item in open_findings.values() if item.get("blocking") is True]
        if result == "approved" and blocking_open:
            errors.append(f"{task_id}: approved review retains an open blocking finding")
        if result in {"changes-requested", "blocked"} and not blocking_open:
            errors.append(f"{task_id}: adverse review lacks an open blocking finding")
        ledger = attempt.get("ledger") or {}
        if repo is not None:
            relative = str(ledger.get("path") or "")
            pure = PurePosixPath(relative)
            if not relative.startswith("artifacts/evidence/") or pure.is_absolute() or ".." in pure.parts:
                errors.append(f"{task_id}: unsafe task review ledger path")
            else:
                try:
                    payload = repo.joinpath(*pure.parts).read_bytes()
                    ledger_document = parse_evidence_payload(payload, pure.suffix)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
                    errors.append(f"{task_id}: cannot load task review ledger: {exc}")
                else:
                    if evidence_sha256(payload) != ledger.get("sha256"):
                        errors.append(f"{task_id}: task review ledger hash mismatch")
                    if (
                        ledger_document.get("task_id") != task_id
                        or ledger_document.get("attempt_id") != expected_id
                        or ledger_document.get("candidate_commit") != packet.get("candidate_commit")
                        or ledger_document.get("reviewer") != review.get("reviewer")
                        or ledger_document.get("result") != result
                        or ledger_document.get("notes", "") != review.get("notes")
                        or ledger_document.get("findings") != findings
                        or ledger_document.get("closures") != (attempt.get("closures") or [])
                    ):
                        errors.append(f"{task_id}: stored review round differs from its immutable ledger")
        errors.extend(task_review_telemetry_errors(task, attempt, repo))
        prior_id = expected_id
        prior_submission = packet
    current = control.get("current_submission")
    if current is not None:
        errors.extend(
            task_submission_packet_errors(
                task,
                current,
                expected_id=f"R{len(attempts) + 1:02d}",
                expected_prior_id=prior_id,
                expected_prior_submission=prior_submission,
                expected_open_ids=sorted(open_findings),
                repo=repo,
            )
        )
        if len(attempts) >= 2 and open_findings and not str(current.get("root_cause_analysis") or "").strip():
            errors.append(f"{task_id}: remediation after round two requires root-cause escalation")
        if task.get("status") != "REVIEW":
            errors.append(f"{task_id}: current task submission exists outside REVIEW")
    elif task.get("status") == "REVIEW":
        errors.append(f"{task_id}: REVIEW task lacks its current immutable submission")
    if attempts:
        latest_review = attempts[-1].get("review") or {}
        if task.get("review") != latest_review:
            errors.append(f"{task_id}: legacy latest-review projection differs from append-only history")
        if task.get("status") == "DONE" and latest_review.get("result") != "approved":
            errors.append(f"{task_id}: DONE task lacks an approved append-only review round")
    return errors


def git_commit_exists(repo: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=repo, capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def git_is_ancestor(repo: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def git_blob(repo: Path, commit: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=repo, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


def historical_wave_approval(repo: Path, record_commit: str, wave_id: str) -> dict[str, Any] | None:
    payload = git_blob(repo, record_commit, "planning/backlog.yaml")
    if payload is None:
        return None
    try:
        document = yaml.safe_load(payload.decode("utf-8"))
    except UnicodeError, yaml.YAMLError:
        return None
    wave = next((item for item in document.get("waves", []) if item.get("id") == wave_id), None)
    return copy.deepcopy((wave or {}).get("approval"))


def approval_introduction_commit(repo: Path, relative_path: str) -> str | None:
    result = subprocess.run(
        ["git", "log", "--format=%H", "--diff-filter=A", "--", relative_path],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    commits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return commits[-1] if result.returncode == 0 and len(commits) == 1 else None


def load_json_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def amendment_approval_errors(repo: Path, reference: dict[str, Any], amendment: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    relative = str(reference.get("path") or "")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not relative.startswith("planning/wave-amendment-approvals/"):
        return [f"{amendment.get('id')}: unsafe amendment approval path"]
    path = repo.joinpath(*pure.parts)
    try:
        payload = path.read_bytes()
        record = json.loads(payload)
        schema = load_json_schema(repo / "planning/wave-amendment-approvals/wave-amendment-approval.schema.json")
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    except (OSError, json.JSONDecodeError, SchemaError, ValidationError) as exc:
        return [f"{amendment.get('id')}: invalid approval record: {exc}"]
    if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
        errors.append(f"{amendment.get('id')}: amendment approval hash mismatch")
    introduced = approval_introduction_commit(repo, relative)
    if introduced != reference.get("introduction_commit"):
        errors.append(f"{amendment.get('id')}: amendment approval introduction commit mismatch")
    if introduced:
        committed = git_blob(repo, introduced, relative)
        if committed != payload:
            errors.append(f"{amendment.get('id')}: immutable amendment approval was rewritten")
        if not git_is_ancestor(repo, introduced):
            errors.append(f"{amendment.get('id')}: amendment approval is not on current history")
    if record.get("amendmentId") != amendment.get("id"):
        errors.append(f"{amendment.get('id')}: approval record amendment identity mismatch")
    if record.get("targetWave") != amendment.get("target_wave"):
        errors.append(f"{amendment.get('id')}: approval record target Wave mismatch")
    if record.get("changeRequestId") != amendment.get("change_request_id"):
        errors.append(f"{amendment.get('id')}: approval record ECR identity mismatch")
    return errors


def bootstrap_scope_addendum_errors(
    repo: Path,
    reference: dict[str, Any],
    amendment_id: str,
    bootstrap_id: str,
) -> list[str]:
    errors: list[str] = []
    relative = str(reference.get("path") or "")
    pure = PurePosixPath(relative)
    expected_prefix = f"planning/wave-amendment-approvals/{bootstrap_id}.addendum-"
    if pure.is_absolute() or ".." in pure.parts or not relative.startswith(expected_prefix):
        return [f"{bootstrap_id}: unsafe bootstrap scope-addendum path"]
    path = repo.joinpath(*pure.parts)
    try:
        payload = path.read_bytes()
        record = json.loads(payload)
        schema = load_json_schema(repo / "planning/wave-amendment-approvals/bootstrap-scope-addendum.schema.json")
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    except (OSError, json.JSONDecodeError, SchemaError, ValidationError) as exc:
        return [f"{bootstrap_id}: invalid bootstrap scope addendum: {exc}"]
    if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
        errors.append(f"{bootstrap_id}: bootstrap scope-addendum hash mismatch")
    introduced = approval_introduction_commit(repo, relative)
    if introduced != reference.get("introduction_commit"):
        errors.append(f"{bootstrap_id}: bootstrap scope-addendum introduction commit mismatch")
    if introduced:
        if git_blob(repo, introduced, relative) != payload:
            errors.append(f"{bootstrap_id}: immutable bootstrap scope addendum was rewritten")
        if not git_is_ancestor(repo, introduced):
            errors.append(f"{bootstrap_id}: bootstrap scope addendum is not on current history")
    if record.get("amendmentId") != amendment_id or record.get("bootstrapUnit") != bootstrap_id:
        errors.append(f"{bootstrap_id}: bootstrap scope-addendum identity mismatch")
    candidate = record.get("candidateAtDecision")
    if not isinstance(candidate, str) or not git_commit_exists(repo, candidate):
        errors.append(f"{bootstrap_id}: bootstrap scope-addendum candidate is invalid")
    elif introduced and not git_is_ancestor(repo, candidate, introduced):
        errors.append(f"{bootstrap_id}: scope addendum does not descend from the reviewed candidate")
    return errors


def load_bootstrap_scope_addenda(
    repo: Path,
    amendment_id: str,
    bootstrap_id: str,
) -> tuple[list[str], list[dict[str, str]]]:
    approval_dir = repo / "planning" / "wave-amendment-approvals"
    additional_paths: list[str] = []
    references: list[dict[str, str]] = []
    for path in sorted(approval_dir.glob(f"{bootstrap_id}.addendum-*.json")):
        relative = path.relative_to(repo).as_posix()
        payload = path.read_bytes()
        introduced = approval_introduction_commit(repo, relative)
        reference = {
            "path": relative,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "introduction_commit": introduced or "",
        }
        errors = bootstrap_scope_addendum_errors(repo, reference, amendment_id, bootstrap_id)
        if errors:
            raise SystemExit("Invalid bootstrap scope addendum:\n- " + "\n- ".join(errors))
        record = json.loads(payload)
        additional_paths.extend(str(item) for item in record.get("authorizedAdditionalPaths", []))
        references.append(reference)
    if len(additional_paths) != len(set(additional_paths)):
        raise SystemExit("Bootstrap scope addenda contain duplicate authorized paths")
    return additional_paths, references


def bootstrap_review_projection_errors(
    label: str,
    status: str,
    implementer: str | None,
    review: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    reviewer = review.get("reviewer")
    result = review.get("result")
    reviewed_at = review.get("reviewed_at")
    if status == "REVIEW":
        if any(value is not None for value in (reviewer, result, reviewed_at, review.get("notes"))):
            errors.append(f"{label}: REVIEW bootstrap must have an empty review projection")
        return errors
    expected_result = BOOTSTRAP_REVIEW_RESULTS.get(status)
    if expected_result is None:
        errors.append(f"{label}: bootstrap status {status} is not review-coherent")
        return errors
    if result != expected_result or not reviewer or not reviewed_at:
        errors.append(f"{label}: {status} bootstrap lacks its complete independent review projection")
    if reviewer and reviewer == implementer:
        errors.append(f"{label}: bootstrap reviewer is not independent from the implementer")
    return errors


def bootstrap_authorized_patterns(
    repo: Path,
    packet: dict[str, Any],
    bootstrap: dict[str, Any],
) -> list[str]:
    patterns = [str(item) for item in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", [])]
    for reference in bootstrap.get("scope_addenda", []):
        relative = str(reference.get("path") or "")
        path = repo.joinpath(*PurePosixPath(relative).parts)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            continue
        patterns.extend(str(item) for item in record.get("authorizedAdditionalPaths", []))
    return patterns


def bootstrap_path_is_authorized(path: str, patterns: list[str], bootstrap_id: str) -> bool:
    return amendment_path_authorized(path, patterns) or path.startswith(f"artifacts/evidence/{bootstrap_id}")


def bootstrap_attempt_errors(
    repo: Path,
    amendment_id: str,
    bootstrap_id: str,
    required_outcomes: list[str],
    attempt: dict[str, Any],
    *,
    expected_base: str | None,
    lineage_base: str,
    allowed_patterns: list[str],
    require_current_branch: bool = False,
) -> list[str]:
    errors: list[str] = []
    candidate = str(attempt.get("implementation_commit") or "")
    implementer = str(attempt.get("implementer") or "")
    submission_branch = str(attempt.get("submission_branch") or "")
    if not implementer:
        errors.append(f"{bootstrap_id}: bootstrap attempt lacks an implementer")
    if not submission_branch:
        errors.append(f"{bootstrap_id}: bootstrap attempt lacks its frozen submission branch")
    if not git_commit_exists(repo, candidate):
        errors.append(f"{bootstrap_id}: bootstrap implementation commit is invalid")
    else:
        if candidate == lineage_base or not git_is_ancestor(repo, lineage_base, candidate):
            errors.append(f"{bootstrap_id}: bootstrap candidate does not strictly descend from its prior candidate")
        if not git_is_ancestor(repo, candidate):
            errors.append(f"{bootstrap_id}: bootstrap candidate is not on current history")
    evidence = attempt.get("evidence") or []
    if len(evidence) != 1 or not isinstance(evidence[0], dict):
        return [*errors, f"{bootstrap_id}: bootstrap attempt must bind exactly one evidence manifest"]
    reference = evidence[0]
    relative = str(reference.get("path") or "")
    pure = PurePosixPath(relative)
    if not relative.startswith("artifacts/evidence/") or pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        return [*errors, f"{bootstrap_id}: unsafe bootstrap evidence path"]
    evidence_path = repo.joinpath(*pure.parts)
    try:
        payload = evidence_path.read_bytes()
        manifest = parse_evidence_payload(payload, evidence_path.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [*errors, f"{bootstrap_id}: invalid bootstrap evidence: {exc}"]
    if evidence_sha256(payload) != reference.get("sha256"):
        errors.append(f"{bootstrap_id}: bootstrap evidence hash mismatch")
    if reference.get("commit") != candidate or manifest.get("commit") != candidate:
        errors.append(f"{bootstrap_id}: bootstrap evidence does not bind the frozen candidate")
    manifest_base = str(manifest.get("baseCommit") or "")
    if expected_base is not None and manifest_base != expected_base:
        errors.append(f"{bootstrap_id}: bootstrap evidence base does not match the frozen review boundary")
    evidence_base = expected_base or manifest_base
    if expected_base is None and (
        not git_commit_exists(repo, manifest_base)
        or not git_is_ancestor(repo, lineage_base, manifest_base)
        or not git_is_ancestor(repo, manifest_base, candidate)
    ):
        errors.append(f"{bootstrap_id}: remediation evidence base is outside the frozen candidate lineage")
    virtual_task = {
        "id": bootstrap_id,
        "branch": submission_branch,
        "base_sha": evidence_base,
        "worktree": repo.as_posix(),
        "acceptance_criteria": required_outcomes,
    }
    errors.extend(
        f"{bootstrap_id}: {error}"
        for error in validate_task_evidence(
            virtual_task,
            manifest,
            expected_commit=candidate,
            expected_base_commit=evidence_base,
        )
    )
    errors.extend(f"{bootstrap_id}: {error}" for error in changed_file_errors(virtual_task, manifest, repo))
    if require_current_branch:
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True, check=False
        )
        if current_branch.returncode != 0 or current_branch.stdout.strip() != submission_branch:
            errors.append(f"{bootstrap_id}: bootstrap submission branch does not match the current codex branch")
    scope = subprocess.run(
        ["git", "diff", "--name-only", lineage_base, candidate, "--"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if scope.returncode != 0:
        errors.append(f"{bootstrap_id}: cannot resolve bootstrap candidate scope")
    else:
        outside = [
            path
            for path in scope.stdout.splitlines()
            if path and not bootstrap_path_is_authorized(path, allowed_patterns, bootstrap_id)
        ]
        if outside:
            errors.append(f"{bootstrap_id}: bootstrap changed path is outside approved scope: {outside[0]}")
    return errors


def bootstrap_packet_errors(
    repo: Path,
    amendment: dict[str, Any],
    approval: dict[str, Any],
    packet: dict[str, Any],
    *,
    require_current_branch: bool = False,
) -> list[str]:
    bootstrap = amendment.get("bootstrap") or {}
    if not bootstrap:
        return []
    amendment_id = str(amendment.get("id"))
    bootstrap_id = str(bootstrap.get("id") or "")
    packet_unit = packet.get("bootstrapUnit") or {}
    errors: list[str] = []
    if approval.get("status") != "APPROVED" or approval.get("amendmentId") != amendment_id:
        errors.append(f"{amendment_id}: bootstrap does not descend from an approved amendment record")
    if bootstrap_id != packet_unit.get("id"):
        errors.append(f"{amendment_id}: bootstrap identity differs from the approved packet")
    attempts = bootstrap.get("attempts") or []
    expected_attempt_ids = [f"R{index:02d}" for index in range(1, len(attempts) + 1)]
    if [str(item.get("id")) for item in attempts] != expected_attempt_ids:
        errors.append(f"{bootstrap_id}: bootstrap attempt IDs are not sequential")
    allowed_patterns = bootstrap_authorized_patterns(repo, packet, bootstrap)
    approval_commit = str(amendment.get("approval_reference", {}).get("introduction_commit") or "")
    lineage_base = approval_commit
    seen_evidence: set[tuple[str, str, str]] = set()
    for position, attempt in enumerate([*attempts, bootstrap]):
        attempt_label = str(attempt.get("id") or bootstrap_id)
        attempt_status = str(attempt.get("status") or "")
        attempt_review = attempt.get("review") or {}
        if attempt is not bootstrap:
            attempt_status = {
                "changes-requested": "CHANGES_REQUESTED",
                "blocked": "BLOCKED",
            }.get(str(attempt_review.get("result")), "")
        errors.extend(
            bootstrap_review_projection_errors(
                attempt_label,
                attempt_status,
                str(attempt.get("implementer") or ""),
                attempt_review,
            )
        )
        candidate = str(attempt.get("implementation_commit") or "")
        evidence = attempt.get("evidence") or []
        if evidence and isinstance(evidence[0], dict):
            identity = (
                str(evidence[0].get("path") or ""),
                str(evidence[0].get("sha256") or ""),
                candidate,
            )
            if identity in seen_evidence:
                errors.append(f"{bootstrap_id}: bootstrap attempt reuses frozen evidence")
            seen_evidence.add(identity)
        errors.extend(
            bootstrap_attempt_errors(
                repo,
                amendment_id,
                bootstrap_id,
                [str(item) for item in packet_unit.get("requiredOutcomes", [])],
                attempt,
                expected_base=approval_commit if position == 0 else None,
                lineage_base=lineage_base,
                allowed_patterns=allowed_patterns,
                require_current_branch=require_current_branch and attempt is bootstrap,
            )
        )
        lineage_base = candidate
    return errors


def immutable_amendment_task_errors(
    amendment: dict[str, Any],
    packet: dict[str, Any],
) -> list[str]:
    actual_tasks = amendment.get("tasks") or []
    packet_tasks = packet.get("taskInventory") or []
    if not actual_tasks:
        return []
    errors: list[str] = []
    if len(actual_tasks) != len(packet_tasks):
        return [f"{amendment.get('id')}: materialized task count differs from the approved packet"]
    for position, (actual, packet_task) in enumerate(zip(actual_tasks, packet_tasks, strict=True), start=1):
        expected = materialized_amendment_task(str(amendment.get("id")), packet_task)
        for field in AMENDMENT_TASK_IMMUTABLE_FIELDS:
            if actual.get(field) != expected.get(field):
                errors.append(
                    f"{actual.get('id') or position}: immutable amendment task field {field} "
                    "differs from the approved packet"
                )
    return errors


def require_amendment_packet_integrity(
    repo: Path,
    amendment: dict[str, Any],
    approval: dict[str, Any],
    packet: dict[str, Any],
    *,
    require_current_branch: bool = False,
) -> None:
    errors = [
        *bootstrap_packet_errors(
            repo,
            amendment,
            approval,
            packet,
            require_current_branch=require_current_branch,
        ),
        *immutable_amendment_task_errors(amendment, packet),
    ]
    if errors:
        raise SystemExit("Invalid Wave amendment packet state:\n- " + "\n- ".join(errors))


def require_runtime_amendment_integrity(backlog_path: str, amendment: dict[str, Any]) -> None:
    repo = discover_repository(backlog_path)
    approval, packet, _payload = load_amendment_authority(repo, str(amendment.get("id")))
    require_amendment_packet_integrity(repo, amendment, approval, packet)


def wave_authority_errors(data: dict[str, Any], repo: Path | None) -> list[str]:
    errors: list[str] = []
    control = data.get("control_plane")
    bases = data.get("wave_approval_bases", [])
    amendments = data.get("wave_amendments", [])
    if control is None and not bases and not amendments:
        return errors
    if not isinstance(control, dict) or control.get("revision") != CONTROL_TOOL_REVISION:
        errors.append("control plane revision is missing or unsupported")
    elif int(control.get("minimum_tool_revision", 0)) > CONTROL_TOOL_REVISION:
        errors.append("this taskctl revision is too old for the active control plane")
    base_ids = [str(item.get("wave_id")) for item in bases]
    if len(base_ids) != len(set(base_ids)):
        errors.append("duplicate Wave approval base identity")
    amendment_ids = [str(item.get("id")) for item in amendments]
    if len(amendment_ids) != len(set(amendment_ids)):
        errors.append("duplicate Wave amendment identity")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for amendment in amendments:
        grouped.setdefault(str(amendment.get("target_wave")), []).append(amendment)
    for wave_id, ordered in grouped.items():
        expected_ids = [f"{wave_id}.A{index:02d}" for index in range(1, len(ordered) + 1)]
        actual_ids = [str(item.get("id")) for item in ordered]
        if actual_ids != expected_ids:
            errors.append(f"{wave_id}: Wave amendment chain is gapped, reordered, or forked")
    if repo is None:
        return errors
    waves = wave_map(data)
    base_map = wave_approval_base_map(data)
    for wave_id, base in base_map.items():
        approval = base.get("approval") or {}
        if canonical_json_sha256(approval) != base.get("canonical_sha256"):
            errors.append(f"{wave_id}: base approval canonical hash mismatch")
        historical = historical_wave_approval(repo, str(base.get("record_commit")), wave_id)
        if historical != approval:
            errors.append(f"{wave_id}: base approval does not match its historical record commit")
        if approval.get("approved_commit") != base.get("packet_commit"):
            errors.append(f"{wave_id}: base approval packet commit mismatch")
        for commit in (base.get("packet_commit"), base.get("record_commit")):
            if not isinstance(commit, str) or not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
                errors.append(f"{wave_id}: base authority commit is missing or not ancestral: {commit}")
    for amendment in amendments:
        errors.extend(amendment_approval_errors(repo, amendment.get("approval_reference") or {}, amendment))
        bootstrap = amendment.get("bootstrap") or {}
        for reference in bootstrap.get("scope_addenda", []):
            errors.extend(
                bootstrap_scope_addendum_errors(
                    repo,
                    reference,
                    str(amendment.get("id")),
                    str(bootstrap.get("id")),
                )
            )
        record_path = repo.joinpath(*PurePosixPath(amendment["approval_reference"]["path"]).parts)
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            continue
        packet_commit = (record.get("packet") or {}).get("commit")
        if not isinstance(packet_commit, str) or not git_commit_exists(repo, packet_commit):
            errors.append(f"{amendment['id']}: packet commit is invalid")
        elif not git_is_ancestor(repo, packet_commit, amendment["approval_reference"]["introduction_commit"]):
            errors.append(f"{amendment['id']}: approval does not descend from its packet")
        if amendment.get("id") == "W1.A01":
            effective = (record.get("migration") or {}).get("effectiveApproval")
            if effective != (waves.get("W1") or {}).get("approval"):
                errors.append("W1.A01: migrated effective approval does not equal the current W1 projection")
            historical = historical_wave_approval(
                repo, str((record.get("migration") or {}).get("historicalRecordCommit")), "W1"
            )
            if historical != effective:
                errors.append("W1.A01: migrated approval does not match a223a6f history")
        if amendment.get("id") == "W1.A02":
            packet = record.get("packet") or {}
            packet_path = repo.joinpath(*PurePosixPath(str(packet.get("path") or "")).parts)
            try:
                packet_payload = packet_path.read_bytes()
                packet_document = json.loads(packet_payload)
            except OSError, json.JSONDecodeError:
                errors.append("W1.A02: approved packet is unreadable")
                continue
            if hashlib.sha256(packet_payload).hexdigest() != packet.get("sha256"):
                errors.append("W1.A02: approved packet hash mismatch")
            committed_packet = git_blob(repo, str(packet.get("commit")), str(packet.get("path")))
            if committed_packet != packet_payload:
                errors.append("W1.A02: approved packet differs from its immutable Git blob")
            task_ids = [str(item.get("id")) for item in packet_document.get("taskInventory", [])]
            if task_ids != record.get("authorizedTaskIds"):
                errors.append("W1.A02: approved task inventory mismatch")
            errors.extend(bootstrap_packet_errors(repo, amendment, record, packet_document))
            errors.extend(immutable_amendment_task_errors(amendment, packet_document))
    active_id = (control or {}).get("active_amendment")
    if active_id is not None and active_id not in amendment_ids:
        errors.append("control plane active amendment does not exist")
    return errors


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
    errors.extend(wave_authority_errors(data, repo))
    if repo is not None:
        errors.extend(evidence_reference_errors(tasks, repo))
    for task in tasks.values():
        errors.extend(task_review_control_errors(task, repo))
    waves = wave_map(data)
    active_waves = active_wave_campaigns(data)
    active_amendments = active_amendment_campaigns(data)
    if len(active_waves) > 1:
        errors.append("More than one ACTIVE Wave campaign exists; default automation permits one Wave")
    active = active_capabilities(capabilities)
    if len(active) > 1:
        errors.append("More than one ACTIVE legacy capability-wave campaign exists")
    if active_waves and active:
        errors.append("A Wave campaign and legacy capability-wave campaign cannot be ACTIVE together")
    if len(active_amendments) > 1:
        errors.append("More than one ACTIVE Wave amendment campaign exists")
    if active_amendments and (active_waves or active):
        errors.append("A Wave amendment campaign cannot run beside an ACTIVE ordinary campaign")
    for wave_id, wave in waves.items():
        approval = wave.get("approval") or {}
        expected_capability_ids = sorted(
            capability["id"]
            for capability in capabilities.values()
            if any(slice_.get("wave") == wave_id for slice_ in capability.get("slices", []))
        )
        expected_slice_ids = [
            slice_["id"]
            for capability in capabilities.values()
            for slice_ in capability.get("slices", [])
            if slice_.get("wave") == wave_id
        ]
        if approval.get("status") not in {"PENDING", "APPROVED", "CHANGES_REQUESTED"}:
            errors.append(f"{wave_id}: invalid pre-Wave approval status")
        if approval.get("status") == "APPROVED" and (
            not approval.get("approved_by")
            or not approval.get("approved_at")
            or re.fullmatch(r"[0-9a-f]{40}", str(approval.get("approved_commit") or "")) is None
        ):
            errors.append(f"{wave_id}: approved pre-Wave packet lacks reviewer, time, or immutable commit")
        if approval.get("status") == "APPROVED" and approval.get("capability_ids") != expected_capability_ids:
            errors.append(f"{wave_id}: approved pre-Wave capability inventory is not exact")
        if approval.get("status") == "APPROVED" and approval.get("slice_ids") != expected_slice_ids:
            errors.append(f"{wave_id}: approved pre-Wave slice inventory is not exact")
        if approval.get("status") == "APPROVED" and wave_id != "W0" and not approval.get("decision_ids"):
            errors.append(f"{wave_id}: approved pre-Wave packet lacks its binding decision inventory")
        if approval.get("status") != "APPROVED" and (
            approval.get("capability_ids") or approval.get("decision_ids") or approval.get("slice_ids")
        ):
            errors.append(f"{wave_id}: pending pre-Wave approval cannot carry an approved inventory")
        campaign = wave.get("campaign") or {}
        if campaign:
            if campaign.get("status") not in CAMPAIGN_STATES:
                errors.append(f"{wave_id}: invalid Wave campaign status")
            if campaign.get("status") == "ACTIVE" and (
                campaign.get("scope") != "wave"
                or not campaign.get("owner")
                or not campaign.get("branch")
                or not campaign.get("base_sha")
                or not campaign.get("worktree")
                or not campaign.get("lease")
                or approval.get("status") != "APPROVED"
            ):
                errors.append(
                    f"{wave_id}: ACTIVE Wave campaign requires approved packet, wave scope, owner, branch, "
                    "base SHA, worktree, and lease"
                )
            if campaign.get("owner") and campaign["owner"] != campaign["owner"].strip():
                errors.append(f"{wave_id}: Wave campaign owner identity is not normalized")
            if (
                repo is not None
                and campaign.get("status") == "ACTIVE"
                and campaign.get("worktree")
                and Path(campaign["worktree"]).resolve() != repo
            ):
                errors.append(f"{wave_id}: ACTIVE Wave campaign worktree does not match the repository")
            lease = campaign.get("lease")
            if lease and lease.get("claimed_by") != campaign.get("owner"):
                errors.append(f"{wave_id}: Wave campaign lease owner does not match campaign owner")
        completion = wave.get("completion") or {}
        if completion.get("status") not in COMPLETION_STATES:
            errors.append(f"{wave_id}: invalid Wave completion status")
        if completion.get("status") == "APPROVED" and (
            not completion.get("reviewer") or not completion.get("reviewed_at") or not completion.get("evidence")
        ):
            errors.append(f"{wave_id}: approved Wave completion lacks reviewer, time, or evidence")
        if completion.get("reviewer") and completion.get("reviewer") == campaign.get("owner"):
            errors.append(f"{wave_id}: Wave reviewer is not independent from the campaign owner")
        for checkpoint in wave.get("checkpoints", []):
            if not checkpoint.get("id") or not checkpoint.get("kind") or not checkpoint.get("evidence"):
                errors.append(f"{wave_id}: every integration checkpoint requires id, kind, and evidence")
            if repo is not None:
                for reference in checkpoint.get("evidence", []):
                    if isinstance(reference, dict):
                        errors.extend(
                            bound_evidence_reference_errors(
                                repo,
                                reference,
                                expected_type=str(reference.get("type") or ""),
                                label=f"{wave_id}/{checkpoint.get('id')}",
                            )
                        )
    aliases: dict[str, str] = {}
    for cid, capability in capabilities.items():
        if capability.get("execution_mode") not in {"wave_contribution", "capability_campaign"}:
            errors.append(f"{cid}: execution_mode must be wave_contribution")
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
            wave_owner = ((waves.get(str(slice_.get("wave"))) or {}).get("campaign") or {}).get("owner")
            if completion.get("reviewer") and completion["reviewer"] == wave_owner:
                errors.append(f"{sid}: slice reviewer is not independent from the Wave campaign owner")
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
    control_active = (data.get("control_plane") or {}).get("active_amendment")
    active_campaign_ids = [
        str(amendment.get("id"))
        for amendment in data.get("wave_amendments", [])
        if ((amendment.get("campaign") or {}).get("status")) == "ACTIVE"
    ]
    expected_active = active_campaign_ids[0] if len(active_campaign_ids) == 1 else None
    if len(active_campaign_ids) > 1:
        errors.append("more than one Wave amendment campaign is ACTIVE")
    if control_active != expected_active:
        errors.append("control plane active_amendment does not exactly match the sole ACTIVE amendment campaign")
    for amendment in data.get("wave_amendments", []):
        amendment_id = str(amendment.get("id"))
        target_wave = str(amendment.get("target_wave"))
        lifecycle = amendment.get("lifecycle") or {}
        history = lifecycle.get("history") or []
        if history and lifecycle.get("status") != history[-1].get("status"):
            errors.append(f"{amendment_id}: lifecycle status is not the last append-only event")
        if [event.get("id") for event in history] != [f"E{index:02d}" for index in range(1, len(history) + 1)]:
            errors.append(f"{amendment_id}: lifecycle event IDs are not sequential")
        bootstrap = amendment.get("bootstrap") or {}
        campaign = amendment.get("campaign") or {}
        task_list = amendment.get("tasks", [])
        if amendment.get("kind") == "gate-integrity-safety-defect" and bootstrap.get("id") != f"{amendment_id}.B00":
            errors.append(f"{amendment_id}: interrupting amendment lacks its exact bootstrap identity")
        if amendment.get("kind") != "migrated-replanning":
            bootstrap_status = bootstrap.get("status")
            campaign_status = campaign.get("status")
            wave_campaign = (waves.get(target_wave) or {}).get("campaign") or {}
            executable_states = {"MATERIALIZED", "ACTIVE", "PAUSED", "REVIEW", "BLOCKED", "ADOPTED"}
            if lifecycle.get("status") in executable_states and bootstrap_status != "APPROVED":
                errors.append(f"{amendment_id}: executable lifecycle requires an independently approved bootstrap")
            if lifecycle.get("status") in executable_states and not task_list:
                errors.append(f"{amendment_id}: executable lifecycle requires the exact materialized task inventory")
            expected_campaign_status = {
                "MATERIALIZED": None,
                "ACTIVE": "ACTIVE",
                "PAUSED": "PAUSED",
                "BLOCKED": "PAUSED",
            }.get(str(lifecycle.get("status")))
            if lifecycle.get("status") in {"MATERIALIZED", "ACTIVE", "PAUSED", "REVIEW", "BLOCKED"}:
                campaign_matches = (
                    campaign_status in {"REVIEW", "COMPLETE"}
                    if lifecycle.get("status") == "REVIEW"
                    else campaign_status == expected_campaign_status
                )
                if not campaign_matches:
                    errors.append(
                        f"{amendment_id}: lifecycle {lifecycle.get('status')} is inconsistent with campaign state"
                    )
                if wave_campaign.get("status") != "PAUSED" or wave_campaign.get("scope") != "amendment-hold":
                    errors.append(f"{amendment_id}: executable lifecycle requires the paused amendment-hold Wave")
            if campaign_status == "COMPLETE" and lifecycle.get("status") not in {"REVIEW", "ADOPTED"}:
                errors.append(f"{amendment_id}: COMPLETE campaign is inconsistent with lifecycle state")
            if lifecycle.get("status") == "APPROVED" and (task_list or campaign):
                errors.append(f"{amendment_id}: unmaterialized APPROVED lifecycle cannot have tasks or a campaign")
            if lifecycle.get("status") in AMENDMENT_TERMINAL_STATES:
                if campaign_status in {"ACTIVE", "REVIEW"} or control_active == amendment_id:
                    errors.append(f"{amendment_id}: terminal lifecycle retains active execution state")
                if wave_campaign.get("scope") != "wave":
                    errors.append(f"{amendment_id}: terminal lifecycle did not restore ordinary Wave scope")
        if campaign:
            if campaign.get("status") in {"ACTIVE", "REVIEW"} and (
                campaign.get("scope") != "wave-amendment"
                or not campaign.get("owner")
                or not campaign.get("branch")
                or not campaign.get("base_sha")
                or not campaign.get("worktree")
            ):
                errors.append(f"{amendment_id}: active amendment campaign lacks identity, target, or lease")
            if campaign.get("status") == "ACTIVE" and not campaign.get("lease"):
                errors.append(f"{amendment_id}: ACTIVE amendment campaign lacks a lease")
            if campaign.get("owner") and campaign.get("owner") != campaign.get("owner", "").strip():
                errors.append(f"{amendment_id}: amendment owner identity is not normalized")
            if (
                repo is not None
                and campaign.get("status") in {"ACTIVE", "REVIEW"}
                and campaign.get("worktree")
                and Path(campaign["worktree"]).resolve() != repo
            ):
                errors.append(f"{amendment_id}: amendment worktree does not match the repository")
            lease = campaign.get("lease")
            if lease and lease.get("claimed_by") != campaign.get("owner"):
                errors.append(f"{amendment_id}: amendment lease owner mismatch")
        if lifecycle.get("status") in {"MATERIALIZED", "ACTIVE", "PAUSED", "REVIEW", "BLOCKED"}:
            wave_campaign = (waves.get(target_wave) or {}).get("campaign") or {}
            if wave_campaign.get("status") != "PAUSED" or wave_campaign.get("scope") != "amendment-hold":
                errors.append(f"{amendment_id}: materialized interrupt requires a paused amendment-hold Wave")
        for position, task in enumerate(task_list):
            task_id = str(task.get("id"))
            if task_id != f"{amendment_id}.T{position + 1:02d}":
                errors.append(f"{task_id}: amendment task identity/order mismatch")
            if task.get("amendment_id") != amendment_id:
                errors.append(f"{task_id}: amendment_id mismatch")
            if task.get("packet_task_sha256") != task.get("packet_task_sha256", "").lower():
                errors.append(f"{task_id}: packet task hash is not normalized")
            status = task.get("status")
            if status not in VALID_STATUSES:
                errors.append(f"{task_id}: invalid amendment task status {status}")
            if status == "READY" and not task_can_be_ready(data, capabilities, slices, tasks, gates, task):
                errors.append(f"{task_id}: READY while amendment dependencies or campaign are incomplete")
            if status in {"IN_PROGRESS", "REVIEW"} and (
                not task.get("owner")
                or not task.get("branch")
                or not task.get("base_sha")
                or not task.get("worktree")
                or not task.get("lease")
            ):
                errors.append(f"{task_id}: active amendment task lacks owner, Git identity, worktree, or lease")
            review = task.get("review") or {}
            if review.get("reviewer") and review.get("reviewer") == task.get("owner"):
                errors.append(f"{task_id}: amendment task reviewer is not independent")
            if status == "DONE" and (
                not task.get("evidence")
                or review.get("result") != "approved"
                or not review.get("reviewer")
                or not review.get("reviewed_at")
            ):
                errors.append(f"{task_id}: DONE without evidence and independent approval")
            if status == "DONE" and task.get("lease") is not None:
                errors.append(f"{task_id}: DONE amendment task must release its lease")
        completion = amendment.get("completion") or {}
        if completion.get("status") == "APPROVED" and (
            any(task.get("status") != "DONE" for task in task_list)
            or not completion.get("reviewer")
            or not completion.get("reviewed_at")
            or not completion.get("evidence")
        ):
            errors.append(f"{amendment_id}: approved completion lacks DONE tasks, reviewer, time, or evidence")
        errors.extend(amendment_exit_review_control_errors(data, amendment, repo))
        if (
            lifecycle.get("status") == "ADOPTED"
            and repo is not None
            and completion.get("exit_review_control") is not None
        ):
            control = completion.get("exit_review_control") or {}
            attempts = control.get("attempts") or []
            if not attempts or (attempts[-1].get("review") or {}).get("result") != "approved":
                errors.append(f"{amendment_id}: adopted amendment lacks an immutable approved exit review")
            adoption_checkpoints = [
                checkpoint
                for checkpoint in (waves.get(target_wave) or {}).get("checkpoints", [])
                if checkpoint.get("kind") == "security"
                and any(
                    isinstance(reference, dict) and reference.get("type") == "amendment-adoption-evidence"
                    for reference in checkpoint.get("evidence", [])
                )
            ]
            if not adoption_checkpoints:
                errors.append(f"{amendment_id}: adopted amendment lacks a bound security checkpoint")
            else:
                for reference in adoption_checkpoints[-1].get("evidence", []):
                    if isinstance(reference, dict):
                        errors.extend(
                            bound_evidence_reference_errors(
                                repo,
                                reference,
                                expected_type="amendment-adoption-evidence",
                                expected_amendment=amendment_id,
                                label=f"{amendment_id}/adoption",
                            )
                        )
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
                if task_wave(task) == gate.get("after_wave") and task["status"] != "DONE"
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
            wave_completion = (waves.get(str(gate.get("after_wave"))) or {}).get("completion", {})
            if wave_completion.get("status") != "APPROVED":
                errors.append(f"{gid}: APPROVED before independent Wave completion review")
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
    bootstrap_interrupt = approved_unbootstrapped_amendment(args.file, data, str(program.get("current_wave")))
    if bootstrap_interrupt is not None:
        print(
            wave_amendment_stop_handoff(
                args, data, {**program, "state": "AMENDMENT_INTERRUPTED", "amendment": bootstrap_interrupt}
            )
        )
        return
    if program.get("state") == "AMENDMENT_INTERRUPTED":
        print(wave_amendment_stop_handoff(args, data, program))
        return
    print("Program state:", program["state"])
    print("Current global wave:", program.get("current_wave") or "complete")
    print("Next global gate:", gate_transition_label(program.get("next_gate")))
    print(
        "Capability completion:",
        dict(sorted(Counter(c.get("completion", {}).get("status") for c in capabilities.values()).items())),
    )
    print(
        "Wave campaign states:",
        dict(sorted(Counter((wave.get("campaign") or {}).get("status", "NONE") for wave in data["waves"]).items())),
    )
    print(
        "Slice completion:",
        dict(sorted(Counter(s.get("completion", {}).get("status") for s in slices.values()).items())),
    )
    print("Task states:", dict(sorted(Counter(t["status"] for t in tasks.values()).items())))
    print("Gate states:", dict(sorted(Counter(g["status"] for g in gates.values()).items())))
    active_wave = active_wave_campaigns(data)
    print(
        "Active Wave campaign:",
        (str(active_wave[0]["id"]) if active_wave else "none"),
    )


def command_next_capability(args, data, capabilities, slices, tasks, gates) -> None:
    """Compatibility view: Wave is now the start/lease unit, not capability."""
    refresh_derived_states(data, capabilities, slices, tasks, gates)
    program = global_program_position(data, slices, tasks, gates)
    bootstrap_interrupt = approved_unbootstrapped_amendment(args.file, data, str(program.get("current_wave")))
    if bootstrap_interrupt is not None:
        print(
            wave_amendment_stop_handoff(
                args, data, {**program, "state": "AMENDMENT_INTERRUPTED", "amendment": bootstrap_interrupt}
            )
        )
        return
    if program.get("state") == "AMENDMENT_INTERRUPTED":
        print(wave_amendment_stop_handoff(args, data, program))
        return
    active = active_wave_campaigns(data)
    if active:
        wave = active[0]
        print_yaml(
            {
                "program": {
                    "state": program["state"],
                    "currentWave": program.get("current_wave"),
                    "nextGlobalGate": gate_transition_label(program.get("next_gate")),
                },
                "activeWave": {
                    "wave": wave["id"],
                    "title": wave.get("title"),
                    "campaign": wave.get("campaign"),
                },
            }
        )
        return
    if program.get("state") == "GATE_PENDING":
        print(global_gate_stop_handoff(args, data, program, capabilities, tasks, gates))
        return
    wave_id = str(program.get("current_wave"))
    wave = wave_map(data).get(wave_id, {})
    if (wave.get("approval") or {}).get("status") != "APPROVED":
        repo = Path(args.file).resolve().parent.parent
        relative = f"planning/review-site/waves/{wave_id}.html"
        uri = (repo / relative).resolve().as_uri()
        contributing = sorted(
            {
                capability_display(capabilities[task["capability_id"]])
                for task in tasks.values()
                if task_wave(task) == wave_id and task.get("capability_id") in capabilities
            }
        )
        slice_ids = sorted(slice_["id"] for slice_ in slices.values() if slice_.get("wave") == wave_id)
        print(
            f"STOPPED AT PRE-WAVE APPROVAL: {wave_id} — {wave.get('title')}\n"
            "Approval is not yet legal for execution. The complete packet must bind every contributing capability "
            "decision and slice plan at one immutable commit.\n"
            f"Review materials: {uri} ({relative})\n"
            f"Capability contributions ({len(contributing)}): {', '.join(contributing)}\n"
            f"Ordered slices ({len(slice_ids)}): {', '.join(slice_ids)}\n"
            "Decision alternatives:\n"
            "  A (recommended): review the complete Wave page, apply any documented overrides, then record one "
            "commit-bound Wave approval. This preserves coherent cross-capability interfaces and one execution lease.\n"
            "  B: defer the Wave without executing it; preserve approval as PENDING.\n"
            "  C: govern a Wave-scope change through canonical plans/backlog and regenerate the packet; do not approve "
            "a subset.\n"
            f"Approval command after a clean immutable review commit: python tools/planctl.py --repo . wave approve "
            f"{wave_id} --by <reviewer> --commit <git-sha>"
        )
        return
    if not any(
        task_wave(task) == wave_id
        and task.get("status") == "READY"
        and profile_matches(task, args.profile)
        and platform_matches(task, args.platform)
        for task in tasks.values()
    ):
        print(
            f"No eligible task in {program.get('current_wave') or 'the completed roadmap'} "
            f"for profile {args.profile} and platform {args.platform}"
        )
        return
    view = {
        "program": {
            "state": program["state"],
            "currentWave": wave_id,
            "nextGlobalGate": gate_transition_label(program.get("next_gate")),
        },
        "wave": wave_id,
        "title": wave.get("title"),
        "goal": wave.get("goal"),
        "preWaveApproval": (wave.get("approval") or {}).get("status"),
        "reviewPage": f"planning/review-site/waves/{wave_id}.html",
    }
    view["start_command"] = (
        f"python tools/taskctl.py wave start {wave_id} --agent <agent> "
        f"--branch codex/{wave_id.lower()}-<slug> --base-sha <sha> "
        f"--worktree <absolute-repository-path> --profile {args.profile} --platform {args.platform}"
    )
    print_yaml(view)


def wave_amendment_stop_handoff(
    args: argparse.Namespace,
    data: dict[str, Any],
    program: dict[str, Any],
) -> str:
    amendment = program.get("amendment")
    if not isinstance(amendment, dict):
        wave_id = str(program.get("current_wave"))
        blockers = blocking_wave_amendments(data, wave_id)
        if not blockers:
            raise SystemExit("Wave amendment handoff requested without an interrupting amendment")
        amendment = blockers[0]
    amendment_id = str(amendment["id"])
    ecr_id = str(amendment.get("change_request_id") or "historical-amendment")
    wave_id = str(amendment.get("target_wave"))
    repo = Path(args.file).resolve().parent.parent
    detail_relative = f"planning/review-site/enablers/{ecr_id}.html"
    detail_uri = (repo / detail_relative).resolve().as_uri()
    proposal_relative = f"planning/enabler-change-requests/{ecr_id}.md"
    proposal_uri = (repo / proposal_relative).resolve().as_uri()
    approval_relative = str((amendment.get("approval_reference") or {}).get("path") or "")
    approval_uri = (repo / approval_relative).resolve().as_uri() if approval_relative else "unrecorded"
    wave_relative = f"planning/review-site/waves/{wave_id}.html"
    wave_uri = (repo / wave_relative).resolve().as_uri()
    lifecycle = (amendment.get("lifecycle") or {}).get("status", "UNKNOWN")
    bootstrap = (amendment.get("bootstrap") or {}).get("status", "NOT-RECORDED")
    campaign = (amendment.get("campaign") or {}).get("status", "NOT-ACTIVE")
    task_states = (
        ", ".join(f"{task.get('id')}={task.get('status')}" for task in amendment.get("tasks", [])) or "not materialized"
    )
    base = wave_approval_base_map(data).get(wave_id, {})
    ordered = [item for item in data.get("wave_amendments", []) if item.get("target_wave") == wave_id]
    authority = ", ".join(
        f"{item.get('id')}={((item.get('approval_reference') or {}).get('introduction_commit') or 'unrecorded')}"
        for item in ordered
    )
    base_packet = base.get("packet_commit") or amendment.get("_base_packet") or "unrecorded"
    if not authority and amendment.get("_legacy_amendment"):
        authority = (
            f"{amendment.get('_legacy_amendment')}={amendment.get('_legacy_packet')}; "
            f"{amendment_id}={((amendment.get('approval_reference') or {}).get('introduction_commit') or 'unrecorded')}"
        )
    if bootstrap == "PENDING":
        next_command = (
            f"python tools/taskctl.py amendment bootstrap-submit {amendment_id} --agent <agent> "
            "--approval-commit 6e9c440102a5c463bb35d81f4dbdc3453d9ce029 --implementation-commit <HEAD> "
            "--evidence <B00-criterion-manifest>"
        )
    elif bootstrap == "REVIEW":
        next_command = (
            f"python tools/taskctl.py amendment bootstrap-review {amendment_id} --reviewer <independent-reviewer> "
            "--result approved --note <review-disposition>"
        )
    elif bootstrap in {"CHANGES_REQUESTED", "BLOCKED"}:
        next_command = (
            f"python tools/taskctl.py amendment bootstrap-resubmit {amendment_id} --agent <agent> "
            "--implementation-commit <HEAD> --evidence <remediation-criterion-manifest>"
        )
    elif bootstrap == "APPROVED" and lifecycle == "APPROVED":
        next_command = f"python tools/taskctl.py amendment materialize {amendment_id} --agent <agent>"
    elif lifecycle == "MATERIALIZED":
        next_command = (
            f"python tools/taskctl.py amendment activate {amendment_id} --agent <agent> --branch <codex-branch> "
            "--base-sha <HEAD> --worktree <absolute-repository-path> --profile LOC --platform windows-x64"
        )
    elif campaign == "ACTIVE":
        ready = next((task.get("id") for task in amendment.get("tasks", []) if task.get("status") == "READY"), None)
        next_command = (
            f"python tools/taskctl.py claim {ready} --agent <agent> --branch <codex-branch> --base-sha <HEAD> "
            "--worktree <absolute-repository-path> --profile LOC --platform windows-x64"
            if ready
            else f"complete the current {amendment_id} task or amendment review before another claim"
        )
    elif lifecycle == "REVIEW":
        next_command = (
            f"python tools/taskctl.py amendment review {amendment_id} --reviewer <independent-reviewer> "
            "--result approved --note <review-disposition>"
        )
    else:
        next_command = f"continue the governed {amendment_id} lifecycle; ordinary {wave_id} execution remains held"
    return (
        f"STOPPED AT WAVE AMENDMENT {amendment_id} ({ecr_id})\n"
        f"State: lifecycle={lifecycle}; bootstrap={bootstrap}; amendment-campaign={campaign}; tasks={task_states}.\n"
        f"Authority: base={base_packet}; ordered amendments: {authority or 'unrecorded'}.\n"
        "Ordinary Wave resumption is NOT LEGAL while this interrupting amendment remains unfinished.\n"
        "Review materials:\n"
        f"  - Amendment detail: {detail_uri} ({detail_relative})\n"
        f"  - Canonical proposal: {proposal_uri} ({proposal_relative})\n"
        f"  - Immutable approval: {approval_uri} ({approval_relative or 'unrecorded'})\n"
        f"  - Wave packet: {wave_uri} ({wave_relative})\n"
        "Decision alternatives:\n"
        "  A (recommended): complete the bounded bootstrap/tasks, independent reviews, and adoption checkpoint.\n"
        "  B: record an explicit append-only defer disposition with a reviewed safe-resume condition.\n"
        "  C: record an explicit append-only withdrawal with rationale and a reviewed safe-resume condition.\n"
        f"Resume condition: {amendment_id}.B00 approved, every authorized task DONE with independent approval, "
        f"amendment exit independently APPROVED, and a {wave_id} control/security adoption checkpoint recorded; "
        "then `python tools/taskctl.py wave resume "
        f"{wave_id} --agent <agent> --branch <codex-branch> --base-sha <HEAD> --worktree "
        "<absolute-repository-path> --profile LOC --platform windows-x64`.\n"
        f"Exact next command: {next_command}"
    )


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
        task["id"] for task in tasks.values() if task_wave(task) == preceding_wave and task.get("status") != "DONE"
    )
    prerequisite_capabilities = sorted(
        {
            task["capability_id"]
            for task in tasks.values()
            if task_wave(task) == preceding_wave and task.get("capability_id") in capabilities
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
    wave_relative = f"planning/review-site/waves/{preceding_wave}.html"
    wave_uri = (repo / wave_relative).resolve().as_uri()
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
        f'--note "<decision rationale>"; then approve and start only a READY Wave campaign in '
        f"{', '.join(gate.get('unlocks_waves', []))}."
    )
    return (
        f"STOPPED AT RELEASE GATE {gate_id}: {gate.get('name')}\n"
        f"Approval state: {readiness}.\n"
        f"What the eventual approval must establish:\n{criteria}\n"
        "Review materials:\n"
        f"  - Complete Wave packet and exit decision: {wave_uri} ({wave_relative})\n"
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
    amendments = active_amendment_campaigns(data)
    if amendments:
        amendment = amendments[0]
        candidates = sorted(
            (task for task in amendment.get("tasks", []) if task.get("status") == "READY"),
            key=task_sort_key,
        )
        if candidates:
            print_yaml(candidates[0])
            return
        program = global_program_position(data, slices, tasks, gates)
        print(wave_amendment_stop_handoff(args, data, program))
        return
    active = active_wave_campaigns(data)
    if not active:
        command_next_capability(args, data, capabilities, slices, tasks, gates)
        return
    wave = active[0]
    wave_id = str(wave["id"])
    candidates = ready_tasks_in_wave(data, wave, capabilities, slices, tasks, gates, args.profile, args.platform)
    if not candidates:
        if wave_complete(wave_id, slices, tasks, data):
            print(
                f"WAVE IMPLEMENTATION COMPLETE: {wave_id}. Run the complete affected/full Wave-exit matrix, attach "
                f"criterion-linked Wave evidence, then submit with `python tools/taskctl.py wave submit {wave_id} "
                "--agent <agent> --evidence <wave-qualification-evidence>`."
            )
            return
        waiting = sorted(
            task["id"]
            for task in tasks.values()
            if task_wave(task) == wave_id and task.get("status") in {"IN_PROGRESS", "REVIEW", "BLOCKED"}
        )
        print(
            f"No READY task in active Wave campaign {wave_id}. Complete the current task/slice review or resolve the "
            f"recorded blocker. Active items: {', '.join(waiting) or 'none'}."
        )
        return
    task = dict(candidates[0])
    task["displayCapability"] = capability_display(capabilities[task["capability_id"]])
    task["displaySlice"] = slice_display(slices[task["slice_id"]])
    print_yaml(task)


def require_wave_planning_ready(args: argparse.Namespace, wave_id: str) -> None:
    if wave_id == "W0":
        return
    repo = Path(args.file).resolve().parents[1]
    command = [
        sys.executable,
        str(repo / "tools" / "planctl.py"),
        "--repo",
        str(repo),
        "wave",
        "ready",
        wave_id,
        "--require-approved",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        return
    detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip())
    review_page = repo / "planning" / "review-site" / "waves" / f"{wave_id}.html"
    review_uri = review_page.resolve().as_uri() if review_page.exists() else f"file://{review_page.resolve()}"
    raise SystemExit(
        f"Pre-Wave planning gate failed for {wave_id}. The complete Wave packet—including every decision "
        "classified as binding in this Wave and every Wave slice plan—must be approved together at one immutable "
        "commit. Inherited and future decisions are nonbinding context.\n"
        + (detail + "\n" if detail else "")
        + f"Planning review page: {review_uri}\nRepository-relative page: "
        f"planning/review-site/waves/{wave_id}.html"
    )


def append_amendment_event(amendment: dict[str, Any], status: str, actor: str, rationale: str) -> None:
    history = amendment.setdefault("lifecycle", {}).setdefault("history", [])
    event = {
        "id": f"E{len(history) + 1:02d}",
        "status": status,
        "actor": normalized_identity(actor, "Amendment actor"),
        "at": utc_now(),
        "rationale": rationale.strip() or f"Transitioned to {status}",
    }
    history.append(event)
    amendment["lifecycle"]["status"] = status


def load_amendment_authority(repo: Path, amendment_id: str) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    approval_path = repo / "planning" / "wave-amendment-approvals" / f"{amendment_id}.json"
    try:
        approval_payload = approval_path.read_bytes()
        approval = json.loads(approval_payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load immutable approval for {amendment_id}: {exc}") from exc
    if approval.get("status") != "APPROVED" or approval.get("amendmentId") != amendment_id:
        raise SystemExit(f"{amendment_id} does not have an exact APPROVED amendment record")
    packet_info = approval.get("packet") or {}
    packet_path = repo.joinpath(*PurePosixPath(str(packet_info.get("path") or "")).parts)
    try:
        packet_payload = packet_path.read_bytes()
        packet = json.loads(packet_payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load approved packet for {amendment_id}: {exc}") from exc
    if hashlib.sha256(packet_payload).hexdigest() != packet_info.get("sha256"):
        raise SystemExit(f"{amendment_id} packet hash does not match its immutable approval")
    if git_blob(repo, str(packet_info.get("commit")), str(packet_info.get("path"))) != packet_payload:
        raise SystemExit(f"{amendment_id} packet bytes differ from the approved Git blob")
    if packet.get("proposedAmendmentId") != amendment_id:
        raise SystemExit(f"{amendment_id} packet identity mismatch")
    if [item.get("id") for item in packet.get("taskInventory", [])] != approval.get("authorizedTaskIds"):
        raise SystemExit(f"{amendment_id} task inventory differs from the approved packet")
    return approval, packet, approval_payload


def require_clean_repository(repo: Path, *, allowed_untracked: set[str] | None = None) -> None:
    tracked = subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=False)
    if tracked.returncode != 0:
        raise SystemExit("Tracked worktree changes exist; the amendment transition requires an exact clean commit")
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if untracked.returncode != 0:
        raise SystemExit("Cannot inspect untracked files before amendment transition")
    unexpected = sorted(set(untracked.stdout.splitlines()) - (allowed_untracked or set()))
    if unexpected:
        raise SystemExit(f"Untracked source exists outside the authorized transition: {unexpected[0]}")


def git_head_branch(repo: Path) -> tuple[str, str]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False)
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True, check=False)
    if head.returncode != 0 or branch.returncode != 0:
        raise SystemExit("Cannot resolve the exact Git state for amendment evidence")
    head_value = head.stdout.strip()
    branch_value = branch.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", head_value) is None or not branch_value.startswith("codex/"):
        raise SystemExit("Amendment evidence requires a full Git commit on a codex branch")
    return head_value, branch_value


def safe_evidence_relative(repo: Path, value: str, label: str) -> tuple[str, Path]:
    path = Path(value).resolve()
    try:
        relative = path.relative_to(repo).as_posix()
    except ValueError as exc:
        raise SystemExit(f"{label} must be inside the repository") from exc
    pure = PurePosixPath(relative)
    if not relative.startswith("artifacts/evidence/") or pure.is_absolute() or ".." in pure.parts:
        raise SystemExit(f"{label} must be a safe path under artifacts/evidence")
    return relative, path


def bound_evidence_reference_errors(
    repo: Path,
    reference: dict[str, Any],
    *,
    expected_type: str,
    expected_amendment: str | None = None,
    label: str,
) -> list[str]:
    errors: list[str] = []
    if reference.get("type") != expected_type:
        errors.append(f"{label}: evidence type is not {expected_type}")
    if expected_amendment is not None and reference.get("amendment_id") != expected_amendment:
        errors.append(f"{label}: evidence amendment identity mismatch")
    relative = str(reference.get("path") or "")
    pure = PurePosixPath(relative)
    if not relative.startswith("artifacts/evidence/") or pure.is_absolute() or ".." in pure.parts:
        return [*errors, f"{label}: unsafe evidence path"]
    commit = str(reference.get("commit") or "")
    if not git_commit_exists(repo, commit):
        return [*errors, f"{label}: evidence commit does not exist"]
    if not git_is_ancestor(repo, commit):
        errors.append(f"{label}: evidence commit is not on current history")
    payload = git_blob(repo, commit, relative)
    if payload is None:
        return [*errors, f"{label}: evidence is absent from its bound commit"]
    if evidence_sha256(payload) != reference.get("sha256"):
        errors.append(f"{label}: evidence hash differs from its bound Git blob")
    try:
        manifest = parse_evidence_payload(payload, PurePosixPath(relative).suffix)
    except (UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [*errors, f"{label}: bound evidence is invalid: {exc}"]
    if manifest.get("amendmentId") != reference.get("amendment_id"):
        errors.append(f"{label}: bound evidence payload amendment identity mismatch")
    return errors


def amendment_exit_packet_sha256(packet: dict[str, Any]) -> str:
    payload = copy.deepcopy(packet)
    payload.pop("packet_sha256", None)
    return canonical_json_sha256(payload)


def amendment_exit_open_findings(attempts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    open_findings: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        for closure in attempt.get("closures", []):
            open_findings.pop(str(closure.get("finding_id")), None)
        for finding in attempt.get("findings", []):
            open_findings[str(finding.get("id"))] = finding
    return open_findings


def amendment_exit_manifest_checks(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    checks = manifest.get("checks")
    if not isinstance(checks, list) or not checks:
        return [], ["amendment exit evidence requires at least one selected check"]
    commands: list[str] = []
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("command"), str) or not check["command"].strip():
            errors.append("every amendment exit check requires a non-empty command")
            continue
        commands.append(str(check["command"]))
        if check.get("result") != "passed":
            errors.append(f"amendment exit check did not pass: {check['command']}")
    if len(commands) != len(set(commands)):
        errors.append("amendment exit selected checks must be unique")
    return commands, errors


def amendment_exit_manifest_errors(
    data: dict[str, Any],
    amendment: dict[str, Any],
    packet: dict[str, Any],
    manifest: dict[str, Any],
    *,
    strict_state: bool,
) -> list[str]:
    amendment_id = str(amendment.get("id"))
    errors: list[str] = []
    if manifest.get("documentType") != "wave-amendment-exit-evidence":
        errors.append(f"{amendment_id}: invalid amendment exit document type")
    if manifest.get("amendmentId") != amendment_id:
        errors.append(f"{amendment_id}: exit evidence amendment identity mismatch")
    if manifest.get("changeRequestId") != amendment.get("change_request_id"):
        errors.append(f"{amendment_id}: exit evidence change-request identity mismatch")
    if manifest.get("targetWave") != amendment.get("target_wave"):
        errors.append(f"{amendment_id}: exit evidence target Wave mismatch")
    declared = str(manifest.get("candidateCommit") or "")
    if re.fullmatch(r"[0-9a-f]{40}", declared) is None:
        errors.append(f"{amendment_id}: exit evidence lacks a full candidate commit")
    branch = str(manifest.get("branch") or "")
    if not branch.startswith("codex/"):
        errors.append(f"{amendment_id}: exit evidence branch is not a codex branch")
    _commands, check_errors = amendment_exit_manifest_checks(manifest)
    errors.extend(f"{amendment_id}: {error}" for error in check_errors)
    if strict_state:
        wave = get(wave_map(data), str(amendment.get("target_wave")), "wave")
        wave_campaign = wave.get("campaign") or {}
        recorded_wave = manifest.get("waveCampaign")
        expected_wave = {
            "status": wave_campaign.get("status"),
            "scope": wave_campaign.get("scope"),
            "pauseReason": wave_campaign.get("pause_reason"),
        }
        if recorded_wave != expected_wave:
            errors.append(f"{amendment_id}: exit evidence waveCampaign is not the exact paused Wave state")
        recorded_amendment = manifest.get("amendmentCampaign")
        if recorded_amendment != {"status": "ACTIVE", "scope": "wave-amendment", "pauseReason": None}:
            errors.append(f"{amendment_id}: exit evidence amendmentCampaign is not the exact pre-submit state")
        if manifest.get("requiredNextTransition") != "independent amendment exit review":
            errors.append(f"{amendment_id}: exit evidence does not name the required next transition")
    if canonical_json_sha256(packet.get("acceptanceCriteria", [])) == canonical_json_sha256([]):
        errors.append(f"{amendment_id}: approved amendment packet has no exit criteria")
    return errors


def historical_amendment_completion(repo: Path, commit: str, amendment_id: str) -> dict[str, Any] | None:
    payload = git_blob(repo, commit, "planning/backlog.yaml")
    if payload is None:
        return None
    try:
        document = yaml.safe_load(payload.decode("utf-8"))
    except UnicodeError, yaml.YAMLError:
        return None
    amendment = next(
        (item for item in document.get("wave_amendments", []) if item.get("id") == amendment_id),
        None,
    )
    return copy.deepcopy((amendment or {}).get("completion"))


def amendment_exit_submission_errors(
    data: dict[str, Any],
    amendment: dict[str, Any],
    approved_packet: dict[str, Any],
    submission: dict[str, Any],
    *,
    expected_id: str,
    expected_prior_id: str | None,
    expected_prior_submission: dict[str, Any] | None,
    expected_open_ids: list[str],
    repo: Path,
    strict_state: bool,
) -> list[str]:
    amendment_id = str(amendment.get("id"))
    errors: list[str] = []
    if submission.get("id") != expected_id:
        errors.append(f"{amendment_id}: amendment exit attempt IDs are not sequential")
    if submission.get("prior_attempt_id") != expected_prior_id:
        errors.append(f"{amendment_id}: amendment exit submission does not link its prior attempt")
    candidate_commit = str(submission.get("candidate_commit") or "")
    if expected_prior_submission is not None:
        prior_candidate = str(expected_prior_submission.get("candidate_commit") or "")
        if candidate_commit == prior_candidate or not git_is_ancestor(repo, prior_candidate, candidate_commit):
            errors.append(f"{amendment_id}: amendment exit remediation is not a strict descendant")
    if sorted(str(item) for item in submission.get("open_finding_ids", [])) != expected_open_ids:
        errors.append(f"{amendment_id}: amendment exit remediation does not replay the exact open findings")
    criteria_hash = canonical_json_sha256(approved_packet.get("acceptanceCriteria", []))
    if submission.get("acceptance_criteria_sha256") != criteria_hash:
        errors.append(f"{amendment_id}: amendment exit criteria hash differs from the approved packet")
    if submission.get("selected_checks_sha256") != canonical_json_sha256(submission.get("selected_checks", [])):
        errors.append(f"{amendment_id}: amendment exit selected-check hash mismatch")
    if submission.get("packet_sha256") != amendment_exit_packet_sha256(submission):
        errors.append(f"{amendment_id}: amendment exit packet hash mismatch")
    reference = submission.get("evidence_reference") or {}
    errors.extend(
        bound_evidence_reference_errors(
            repo,
            reference,
            expected_type="amendment-exit-evidence",
            expected_amendment=amendment_id,
            label=f"{amendment_id}/{expected_id}",
        )
    )
    if reference.get("commit") != submission.get("candidate_commit"):
        errors.append(f"{amendment_id}: exit candidate differs from the evidence Git binding")
    payload = git_blob(repo, str(reference.get("commit") or ""), str(reference.get("path") or ""))
    if payload is None:
        return errors
    try:
        manifest = parse_evidence_payload(payload, PurePosixPath(str(reference.get("path"))).suffix)
    except (UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [*errors, f"{amendment_id}: invalid amendment exit evidence: {exc}"]
    if submission.get("declared_candidate_commit") != manifest.get("candidateCommit"):
        errors.append(f"{amendment_id}: declared exit candidate differs from the bound evidence")
    if submission.get("branch") != manifest.get("branch"):
        errors.append(f"{amendment_id}: frozen exit branch differs from the bound evidence")
    selected_checks, check_errors = amendment_exit_manifest_checks(manifest)
    errors.extend(f"{amendment_id}: {error}" for error in check_errors)
    if submission.get("selected_checks") != selected_checks:
        errors.append(f"{amendment_id}: frozen selected checks differ from the bound evidence")
    errors.extend(amendment_exit_manifest_errors(data, amendment, approved_packet, manifest, strict_state=strict_state))
    return errors


def amendment_exit_ledger_errors(
    repo: Path,
    amendment_id: str,
    attempt: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    ledger = attempt.get("ledger") or {}
    relative = str(ledger.get("path") or "")
    pure = PurePosixPath(relative)
    if not relative.startswith("artifacts/evidence/") or pure.is_absolute() or ".." in pure.parts:
        return [f"{amendment_id}: unsafe amendment exit review ledger path"]
    path = repo.joinpath(*pure.parts)
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"{amendment_id}: cannot load amendment exit review ledger: {exc}"]
    if evidence_sha256(payload) != ledger.get("sha256"):
        errors.append(f"{amendment_id}: amendment exit review ledger hash mismatch")
    submission = attempt.get("submission") or {}
    review = attempt.get("review") or {}
    reference = submission.get("evidence_reference") or {}
    expected = {
        "amendment_id": amendment_id,
        "attempt_id": submission.get("id"),
        "reviewed_state_commit": review.get("reviewed_state_commit"),
        "reviewer": review.get("reviewer"),
        "result": review.get("result"),
    }
    for field, value in expected.items():
        if document.get(field) != value:
            errors.append(f"{amendment_id}: exit review ledger {field} differs from the frozen review")
    ledger_evidence = document.get("evidence") or {}
    if any(ledger_evidence.get(field) != reference.get(field) for field in ("path", "sha256")):
        errors.append(f"{amendment_id}: exit review ledger evidence binding mismatch")
    if document.get("findings") != attempt.get("findings") or document.get("closures") != attempt.get("closures"):
        errors.append(f"{amendment_id}: exit review ledger finding or closure history mismatch")
    return errors


def amendment_exit_review_control_errors(
    data: dict[str, Any],
    amendment: dict[str, Any],
    repo: Path | None,
) -> list[str]:
    completion = amendment.get("completion") or {}
    control = completion.get("exit_review_control")
    if control is None:
        return []
    amendment_id = str(amendment.get("id"))
    errors: list[str] = []
    attempts = control.get("attempts") or []
    expected_ids = [f"R{index:02d}" for index in range(1, len(attempts) + 1)]
    actual_ids = [str((attempt.get("submission") or {}).get("id")) for attempt in attempts]
    if actual_ids != expected_ids:
        errors.append(f"{amendment_id}: amendment exit review attempts are not sequential")
    if repo is None:
        return errors
    try:
        _approval, approved_packet, _payload = load_amendment_authority(repo, amendment_id)
    except SystemExit as exc:
        return [*errors, str(exc)]
    open_findings: dict[str, dict[str, Any]] = {}
    prior_id: str | None = None
    prior_submission: dict[str, Any] | None = None
    seen_findings: set[str] = set()
    for index, attempt in enumerate(attempts, start=1):
        submission = attempt.get("submission") or {}
        expected_open = sorted(open_findings)
        review = attempt.get("review") or {}
        strict_state = not (
            index == 1
            and review.get("result") == "changes-requested"
            and submission.get("declared_candidate_commit") != submission.get("candidate_commit")
        )
        errors.extend(
            amendment_exit_submission_errors(
                data,
                amendment,
                approved_packet,
                submission,
                expected_id=f"R{index:02d}",
                expected_prior_id=prior_id,
                expected_prior_submission=prior_submission,
                expected_open_ids=expected_open,
                repo=repo,
                strict_state=strict_state,
            )
        )
        reviewed_state = str(review.get("reviewed_state_commit") or "")
        if not git_commit_exists(repo, reviewed_state) or not git_is_ancestor(repo, reviewed_state):
            errors.append(f"{amendment_id}: reviewed amendment exit state is absent from current history")
        elif not git_is_ancestor(repo, str(submission.get("candidate_commit") or ""), reviewed_state):
            errors.append(f"{amendment_id}: reviewed exit state does not descend from its candidate")
        else:
            historical = historical_amendment_completion(repo, reviewed_state, amendment_id) or {}
            historical_current = (historical.get("exit_review_control") or {}).get("current_submission")
            if historical_current is None:
                if not (
                    index == 1
                    and historical.get("status") == "REVIEW"
                    and submission.get("evidence_reference", {}).get("path") in historical.get("evidence", [])
                ):
                    errors.append(f"{amendment_id}: reviewed exit state lacks its exact frozen submission")
            elif historical_current != submission:
                errors.append(f"{amendment_id}: reviewed exit submission differs from its frozen backlog state")
        findings = attempt.get("findings") or []
        ordering = [REVIEW_SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
        if ordering != sorted(ordering):
            errors.append(f"{amendment_id}: amendment exit findings are not severity-ranked")
        for finding in findings:
            finding_id = str(finding.get("id") or "")
            if finding_id in seen_findings:
                errors.append(f"{amendment_id}: duplicate amendment exit finding ID {finding_id}")
            seen_findings.add(finding_id)
            criterion_index = finding.get("criterion_index")
            if type(criterion_index) is not int or not 1 <= criterion_index <= len(
                approved_packet.get("acceptanceCriteria", [])
            ):
                errors.append(f"{amendment_id}: exit finding {finding_id} has an invalid criterion index")
        closures = attempt.get("closures") or []
        closure_ids = [str(item.get("finding_id") or "") for item in closures]
        if len(closure_ids) != len(set(closure_ids)) or not set(closure_ids).issubset(open_findings):
            errors.append(f"{amendment_id}: amendment exit closures do not target unique open findings")
        for closure_id in closure_ids:
            open_findings.pop(closure_id, None)
        for finding in findings:
            open_findings[str(finding.get("id"))] = finding
        if review.get("result") == "approved" and any(item.get("blocking") is True for item in open_findings.values()):
            errors.append(f"{amendment_id}: amendment exit approval retains open blocking findings")
        errors.extend(amendment_exit_ledger_errors(repo, amendment_id, attempt))
        prior_id = f"R{index:02d}"
        prior_submission = submission
    current = control.get("current_submission")
    if current is not None:
        errors.extend(
            amendment_exit_submission_errors(
                data,
                amendment,
                approved_packet,
                current,
                expected_id=f"R{len(attempts) + 1:02d}",
                expected_prior_id=prior_id,
                expected_prior_submission=prior_submission,
                expected_open_ids=sorted(open_findings),
                repo=repo,
                strict_state=True,
            )
        )
        if completion.get("status") != "REVIEW":
            errors.append(f"{amendment_id}: current exit submission requires REVIEW completion")
    elif attempts:
        latest = attempts[-1].get("review") or {}
        expected_status = {
            "approved": "APPROVED",
            "changes-requested": "CHANGES_REQUESTED",
            "blocked": "BLOCKED",
        }.get(str(latest.get("result")))
        if completion.get("status") != expected_status:
            errors.append(f"{amendment_id}: completion projection differs from the latest immutable exit review")
        if any(completion.get(field) != latest.get(field) for field in ("reviewer", "reviewed_at", "notes")):
            errors.append(f"{amendment_id}: latest amendment exit review projection was flattened or altered")
    return errors


def amendment_path_authorized(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif path == pattern:
            return True
    return False


def command_amendment_status(args, data, capabilities, slices, tasks, gates) -> None:
    amendments = wave_amendment_map(data)
    if args.amendment:
        print_yaml(get(amendments, args.amendment, "Wave amendment"))
        return
    for amendment in data.get("wave_amendments", []):
        print(
            f"{amendment['id']}\t{amendment.get('change_request_id') or 'historical'}\t"
            f"{(amendment.get('lifecycle') or {}).get('status')}\t{amendment.get('target_wave')}"
        )


def command_amendment_bootstrap_submit(args, data, capabilities, slices, tasks, gates) -> None:
    if data.get("control_plane") or data.get("wave_approval_bases") or data.get("wave_amendments"):
        raise SystemExit("The amendment control plane is already bootstrapped; duplicate bootstrap is denied")
    repo = discover_repository(args.file)
    approval, packet, _approval_payload = load_amendment_authority(repo, args.amendment)
    approval_commit = str(args.approval_commit)
    implementation_commit = str(args.implementation_commit)
    introduction = approval_introduction_commit(repo, f"planning/wave-amendment-approvals/{args.amendment}.json")
    if approval_commit != introduction:
        raise SystemExit("Approval commit must equal the immutable approval-record introduction commit")
    if implementation_commit == approval_commit or not git_is_ancestor(repo, approval_commit, implementation_commit):
        raise SystemExit("Bootstrap implementation must strictly descend from the human approval commit")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False)
    if head.returncode != 0 or head.stdout.strip() != implementation_commit:
        raise SystemExit("Bootstrap implementation commit must equal current HEAD")
    evidence_path = Path(args.evidence).resolve()
    try:
        evidence_relative = evidence_path.relative_to(repo).as_posix()
    except ValueError as exc:
        raise SystemExit("Bootstrap evidence must be inside the repository") from exc
    if not evidence_relative.startswith("artifacts/evidence/"):
        raise SystemExit("Bootstrap evidence must be under artifacts/evidence")
    try:
        evidence_payload = evidence_path.read_bytes()
        manifest = parse_evidence_payload(evidence_payload, evidence_path.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid bootstrap evidence: {exc}") from exc
    bootstrap_unit = packet.get("bootstrapUnit") or {}
    additional_paths, scope_addenda = load_bootstrap_scope_addenda(
        repo,
        args.amendment,
        str(bootstrap_unit.get("id")),
    )
    agent = normalized_identity(args.agent, "Bootstrap implementer")
    virtual_task = {
        "id": bootstrap_unit.get("id"),
        "branch": manifest.get("branch"),
        "base_sha": approval_commit,
        "worktree": repo.as_posix(),
        "acceptance_criteria": bootstrap_unit.get("requiredOutcomes", []),
    }
    evidence_errors = exact_commit_errors(
        virtual_task,
        manifest,
        repo,
        evidence_path=evidence_path,
        expected_base_commit=approval_commit,
    )
    if manifest.get("commit") != implementation_commit:
        evidence_errors.append("bootstrap evidence commit must equal the implementation commit")
    actual = subprocess.run(
        ["git", "diff", "--name-only", approval_commit, implementation_commit, "--"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    changed_files = [line for line in actual.stdout.splitlines() if line]
    patterns = [str(item) for item in bootstrap_unit.get("authorizedPaths", [])] + additional_paths
    outside = [path for path in changed_files if not amendment_path_authorized(path, patterns)]
    if actual.returncode != 0:
        evidence_errors.append("cannot resolve bootstrap changed-file scope")
    if outside:
        evidence_errors.append(f"bootstrap changed path is outside approved scope: {outside[0]}")
    if evidence_errors:
        raise SystemExit("Invalid bootstrap evidence:\n- " + "\n- ".join(evidence_errors))
    base_packet = str((approval.get("effectiveBase") or {}).get("originalPacketCommit"))
    base_record = str((approval.get("effectiveBase") or {}).get("originalApprovalRecordCommit"))
    base_approval = historical_wave_approval(repo, base_record, str(approval.get("targetWave")))
    if not isinstance(base_approval, dict) or base_approval.get("approved_commit") != base_packet:
        raise SystemExit("Original W1 approval cannot be reproduced from immutable history")
    legacy_path = "planning/wave-amendment-approvals/W1.A01.json"
    current_path = f"planning/wave-amendment-approvals/{args.amendment}.json"
    legacy_payload = (repo / legacy_path).read_bytes()
    current_payload = (repo / current_path).read_bytes()
    legacy_record = json.loads(legacy_payload)
    if (legacy_record.get("migration") or {}).get("effectiveApproval") != (
        wave_map(data).get(str(approval.get("targetWave")), {}).get("approval")
    ):
        raise SystemExit("Legacy W1.A01 does not reproduce the current effective Wave approval")
    now = utc_now()
    data["control_plane"] = {
        "revision": CONTROL_TOOL_REVISION,
        "minimum_tool_revision": CONTROL_TOOL_REVISION,
        "active_amendment": None,
    }
    data["wave_approval_bases"] = [
        {
            "wave_id": approval["targetWave"],
            "packet_commit": base_packet,
            "record_commit": base_record,
            "approval": base_approval,
            "canonical_sha256": canonical_json_sha256(base_approval),
        }
    ]
    data["wave_amendments"] = [
        {
            "id": "W1.A01",
            "change_request_id": None,
            "target_wave": approval["targetWave"],
            "kind": "migrated-replanning",
            "approval_reference": {
                "path": legacy_path,
                "sha256": hashlib.sha256(legacy_payload).hexdigest(),
                "introduction_commit": approval_introduction_commit(repo, legacy_path),
            },
            "lifecycle": {
                "status": "ADOPTED",
                "history": [
                    {
                        "id": "E01",
                        "status": "ADOPTED",
                        "actor": "repository-owner",
                        "at": now,
                        "rationale": "Migrated immutable historical W1 amendment authority.",
                    }
                ],
            },
            "bootstrap": None,
            "campaign": None,
            "tasks": [],
            "completion": {
                "status": "APPROVED",
                "reviewer": "repository-owner",
                "reviewed_at": now,
                "evidence": [legacy_path],
                "notes": "Historical authority migration only.",
            },
        },
        {
            "id": args.amendment,
            "change_request_id": approval.get("changeRequestId"),
            "target_wave": approval["targetWave"],
            "kind": packet.get("classification"),
            "approval_reference": {
                "path": current_path,
                "sha256": hashlib.sha256(current_payload).hexdigest(),
                "introduction_commit": introduction,
            },
            "lifecycle": {
                "status": "APPROVED",
                "history": [
                    {
                        "id": "E01",
                        "status": "APPROVED",
                        "actor": approval["approvedBy"],
                        "at": approval["approvedAt"],
                        "rationale": approval["decision"],
                    }
                ],
            },
            "bootstrap": {
                "id": bootstrap_unit["id"],
                "status": "REVIEW",
                "implementer": agent,
                "implementation_commit": implementation_commit,
                "submission_branch": str(manifest.get("branch") or ""),
                "scope_addenda": scope_addenda,
                "evidence": [
                    {
                        "type": "criterion-manifest",
                        "path": evidence_relative,
                        "sha256": evidence_sha256(evidence_payload),
                        "commit": implementation_commit,
                        "recorded_at": now,
                    }
                ],
                "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
            },
            "campaign": None,
            "tasks": [],
            "completion": {"status": "PENDING", "reviewer": None, "reviewed_at": None, "evidence": [], "notes": None},
        },
    ]
    save_validated(
        args.file,
        data,
        expected_sha256=getattr(args, "source_sha256", None),
        expected_identity=getattr(args, "source_identity", None),
        expected_approved_waves=getattr(args, "source_approved_waves", None),
        repo=repo,
    )
    print(f"Submitted {bootstrap_unit['id']} for independent review")


def command_amendment_bootstrap_review(args, data, capabilities, slices, tasks, gates) -> None:
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    bootstrap = amendment.get("bootstrap") or {}
    if bootstrap.get("status") != "REVIEW":
        raise SystemExit("Bootstrap is not awaiting independent review")
    reviewer = normalized_identity(args.reviewer, "Bootstrap reviewer")
    if reviewer == bootstrap.get("implementer"):
        raise SystemExit("Bootstrap reviewer must be independent from the implementer")
    repo = discover_repository(args.file)
    require_clean_repository(repo)
    approval, packet, _payload = load_amendment_authority(repo, args.amendment)
    require_amendment_packet_integrity(
        repo,
        amendment,
        approval,
        packet,
        require_current_branch=True,
    )
    result_status = {
        "approved": "APPROVED",
        "changes-requested": "CHANGES_REQUESTED",
        "blocked": "BLOCKED",
    }[args.result]
    bootstrap["status"] = result_status
    bootstrap["review"] = {
        "reviewer": reviewer,
        "result": args.result,
        "reviewed_at": utc_now(),
        "notes": args.note,
    }
    persist(args, data)
    print(f"Bootstrap review for {args.amendment}: {result_status}")


def command_amendment_bootstrap_resubmit(args, data, capabilities, slices, tasks, gates) -> None:
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    bootstrap = amendment.get("bootstrap") or {}
    if bootstrap.get("status") not in {"CHANGES_REQUESTED", "BLOCKED"}:
        raise SystemExit("Bootstrap resubmission requires a preserved changes-requested or blocked review")
    repo = discover_repository(args.file)
    approval, packet, _payload = load_amendment_authority(repo, args.amendment)
    require_amendment_packet_integrity(repo, amendment, approval, packet)
    implementation_commit = str(args.implementation_commit)
    previous_candidate = str(bootstrap.get("implementation_commit") or "")
    if (
        implementation_commit == previous_candidate
        or not git_commit_exists(repo, implementation_commit)
        or not git_is_ancestor(repo, previous_candidate, implementation_commit)
    ):
        raise SystemExit("Bootstrap remediation must freeze a strict descendant of the prior candidate")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False)
    if head.returncode != 0 or head.stdout.strip() != implementation_commit:
        raise SystemExit("Bootstrap remediation commit must equal current HEAD")
    evidence_path = Path(args.evidence).resolve()
    try:
        evidence_relative = evidence_path.relative_to(repo).as_posix()
    except ValueError as exc:
        raise SystemExit("Bootstrap evidence must be inside the repository") from exc
    if not evidence_relative.startswith("artifacts/evidence/"):
        raise SystemExit("Bootstrap evidence must be under artifacts/evidence")
    require_clean_repository(repo, allowed_untracked={evidence_relative})
    try:
        evidence_payload = evidence_path.read_bytes()
        _manifest = parse_evidence_payload(evidence_payload, evidence_path.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid bootstrap evidence: {exc}") from exc
    agent = normalized_identity(args.agent, "Bootstrap remediation implementer")
    evidence_reference = {
        "type": "criterion-manifest",
        "path": evidence_relative,
        "sha256": evidence_sha256(evidence_payload),
        "commit": implementation_commit,
        "recorded_at": utc_now(),
    }
    candidate = {
        "status": "REVIEW",
        "implementer": agent,
        "implementation_commit": implementation_commit,
        "submission_branch": str(_manifest.get("branch") or ""),
        "evidence": [evidence_reference],
        "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
    }
    errors = bootstrap_attempt_errors(
        repo,
        args.amendment,
        str(bootstrap.get("id")),
        [str(item) for item in (packet.get("bootstrapUnit") or {}).get("requiredOutcomes", [])],
        candidate,
        expected_base=None,
        lineage_base=previous_candidate,
        allowed_patterns=bootstrap_authorized_patterns(repo, packet, bootstrap),
        require_current_branch=True,
    )
    if errors:
        raise SystemExit("Invalid bootstrap remediation evidence:\n- " + "\n- ".join(errors))
    prior_review = copy.deepcopy(bootstrap.get("review") or {})
    attempt_id = f"R{len(bootstrap.get('attempts') or []) + 1:02d}"
    bootstrap.setdefault("attempts", []).append(
        {
            "id": attempt_id,
            "implementer": bootstrap.get("implementer"),
            "implementation_commit": previous_candidate,
            "submission_branch": bootstrap.get("submission_branch"),
            "evidence": copy.deepcopy(bootstrap.get("evidence") or []),
            "review": prior_review,
        }
    )
    bootstrap.update(
        status="REVIEW",
        implementer=agent,
        implementation_commit=implementation_commit,
        submission_branch=str(_manifest.get("branch") or ""),
        evidence=[evidence_reference],
        review={"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
    )
    persist(args, data)
    print(f"Resubmitted {bootstrap.get('id')} as {attempt_id} -> current REVIEW")


def materialized_amendment_task(amendment_id: str, packet_task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": packet_task["id"],
        "amendment_id": amendment_id,
        "title": packet_task["title"],
        "objective": packet_task["objective"],
        "dependencies": list(packet_task.get("dependencies", [])),
        "acceptance_criteria": list(packet_task.get("acceptanceCriteria", [])),
        "verification_commands": list(packet_task.get("verification", [])),
        "packet_task_sha256": canonical_json_sha256(packet_task),
        "status": "NOT_STARTED",
        "owner": None,
        "branch": None,
        "base_sha": None,
        "worktree": None,
        "lease": None,
        "started_at": None,
        "updated_at": None,
        "completed_at": None,
        "blocker": None,
        "implementation_notes": "",
        "evidence": [],
        "verification_state": None,
        "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
    }


def command_amendment_materialize(args, data, capabilities, slices, tasks, gates) -> None:
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    if (amendment.get("bootstrap") or {}).get("status") != "APPROVED":
        raise SystemExit("Independent bootstrap approval is required before task materialization")
    if amendment.get("tasks") or (amendment.get("lifecycle") or {}).get("status") != "APPROVED":
        raise SystemExit("Amendment tasks have already been materialized or the lifecycle is not APPROVED")
    actor = normalized_identity(args.agent, "Materialization actor")
    repo = discover_repository(args.file)
    require_clean_repository(repo)
    approval, packet, _payload = load_amendment_authority(repo, args.amendment)
    require_amendment_packet_integrity(repo, amendment, approval, packet)
    packet_tasks = packet.get("taskInventory", [])
    authorized = approval.get("authorizedTaskIds", [])
    if [task.get("id") for task in packet_tasks] != authorized:
        raise SystemExit("Only the exact approved task inventory may be materialized")
    amendment["tasks"] = [materialized_amendment_task(args.amendment, task) for task in packet_tasks]
    target_wave = get(wave_map(data), str(amendment["target_wave"]), "wave")
    wave_campaign = target_wave.get("campaign") or {}
    if wave_campaign.get("status") != "PAUSED":
        raise SystemExit("Target Wave must be PAUSED before amendment materialization")
    if any(
        task.get("status") in {"IN_PROGRESS", "REVIEW"} and amendment_for_task(data, task) is None
        for task in tasks.values()
    ):
        raise SystemExit("Ordinary task work must be quiescent before amendment materialization")
    wave_campaign["scope"] = "amendment-hold"
    append_amendment_event(amendment, "MATERIALIZED", actor, "Materialized the exact human-approved task inventory.")
    save_validated(
        args.file,
        data,
        expected_sha256=getattr(args, "source_sha256", None),
        expected_identity=getattr(args, "source_identity", None),
        expected_approved_waves=getattr(args, "source_approved_waves", None),
        expected_amendment_history=getattr(args, "source_amendment_history", None),
        repo=repo,
    )
    print(f"Materialized {', '.join(authorized)} from {args.amendment}")


def command_amendment_activate(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    require_execution_target(args.profile, args.platform)
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    lifecycle = (amendment.get("lifecycle") or {}).get("status")
    if lifecycle not in {"MATERIALIZED", "PAUSED"}:
        raise SystemExit("Only a MATERIALIZED or PAUSED amendment may be activated")
    if active_amendment_campaigns(data) or active_wave_campaigns(data) or active_capabilities(capabilities):
        raise SystemExit("Another amendment, Wave, or legacy capability campaign is ACTIVE")
    wave = get(wave_map(data), str(amendment["target_wave"]), "wave")
    wave_campaign = wave.get("campaign") or {}
    if wave_campaign.get("status") != "PAUSED" or wave_campaign.get("scope") != "amendment-hold":
        raise SystemExit("Target Wave is not at the validated amendment-hold boundary")
    agent, branch, base_sha, worktree = git_execution_identity(
        args.file, agent=args.agent, branch=args.branch, base_sha=args.base_sha, worktree=args.worktree
    )
    if wave_campaign.get("owner") != agent or wave_campaign.get("branch") != branch:
        raise SystemExit("Amendment activation must retain the paused Wave owner and codex branch")
    repo = discover_repository(args.file)
    require_clean_repository(repo)
    approval, packet, _payload = load_amendment_authority(repo, args.amendment)
    require_amendment_packet_integrity(repo, amendment, approval, packet)
    expected = {item["id"]: canonical_json_sha256(item) for item in packet.get("taskInventory", [])}
    actual = {item["id"]: item.get("packet_task_sha256") for item in amendment.get("tasks", [])}
    if actual != expected:
        raise SystemExit("Materialized task inventory or packet hashes differ from the approved packet")
    if any(
        task.get("status") in {"IN_PROGRESS", "REVIEW"} and amendment_for_task(data, task) is None
        for task in tasks.values()
    ):
        raise SystemExit("Ordinary task work is not quiescent")
    now = utc_now()
    amendment["campaign"] = {
        "status": "ACTIVE",
        "scope": "wave-amendment",
        "owner": agent,
        "branch": branch,
        "worktree": worktree,
        "base_sha": base_sha,
        "profile": args.profile,
        "platform": args.platform,
        "started_at": ((amendment.get("campaign") or {}).get("started_at") or now),
        "updated_at": now,
        "pause_reason": None,
        "lease": new_lease(agent, args.lease_hours),
    }
    data["control_plane"]["active_amendment"] = args.amendment
    append_amendment_event(amendment, "ACTIVE", agent, "Activated the bounded amendment campaign.")
    _data, _caps, _slices, refreshed_tasks, _gates = index_backlog(data)
    refresh_derived_states(data, _caps, _slices, refreshed_tasks, _gates)
    persist(args, data)
    print(f"Activated Wave amendment {args.amendment}")


def command_amendment_pause(args, data, capabilities, slices, tasks, gates) -> None:
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    campaign = amendment.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit("Only an ACTIVE amendment may be paused")
    require_active_lease(amendment, args.agent, f"Wave amendment {args.amendment}")
    if any(task.get("status") in {"IN_PROGRESS", "REVIEW"} for task in amendment.get("tasks", [])):
        raise SystemExit("Resolve or block the active amendment task before pausing")
    campaign.update(status="PAUSED", updated_at=utc_now(), pause_reason=args.reason, lease=None)
    data["control_plane"]["active_amendment"] = None
    append_amendment_event(amendment, "PAUSED", args.agent, args.reason)
    persist(args, data)


def build_amendment_exit_submission(
    args: argparse.Namespace,
    data: dict[str, Any],
    amendment: dict[str, Any],
    evidence_value: str,
    *,
    migration_state_commit: str | None = None,
) -> dict[str, Any]:
    repo = discover_repository(args.file)
    _approval, approved_packet, _payload = load_amendment_authority(repo, str(amendment["id"]))
    relative, path = safe_evidence_relative(repo, evidence_value, "Amendment exit evidence")
    candidate, current_branch = git_head_branch(repo)
    if migration_state_commit is not None:
        candidate = migration_state_commit
    payload = git_blob(repo, candidate, relative)
    if payload is None:
        raise SystemExit("Amendment exit evidence must exist in the exact candidate commit")
    try:
        manifest = parse_evidence_payload(payload, path.suffix)
    except (UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid amendment exit evidence: {exc}") from exc
    branch = str(manifest.get("branch") or "")
    if migration_state_commit is None:
        require_clean_repository(repo)
        declared_candidate = str(manifest.get("candidateCommit") or "")
        if (
            branch != current_branch
            or not git_commit_exists(repo, declared_candidate)
            or not git_is_ancestor(repo, declared_candidate, candidate)
        ):
            raise SystemExit(
                "Amendment exit evidence must name an implementation candidate on the current codex-branch history"
            )
        strict_errors = amendment_exit_manifest_errors(
            data,
            amendment,
            approved_packet,
            manifest,
            strict_state=True,
        )
        if strict_errors:
            raise SystemExit("Invalid amendment exit evidence:\n- " + "\n- ".join(strict_errors))
    else:
        if not git_is_ancestor(repo, migration_state_commit):
            raise SystemExit("Historical amendment exit review state is not on current history")
    selected_checks, check_errors = amendment_exit_manifest_checks(manifest)
    if check_errors:
        raise SystemExit("Invalid amendment exit evidence:\n- " + "\n- ".join(check_errors))
    control = (amendment.get("completion") or {}).get("exit_review_control") or {
        "version": 1,
        "attempts": [],
        "current_submission": None,
    }
    attempts = control.get("attempts") or []
    open_ids = sorted(amendment_exit_open_findings(attempts))
    submitted_at = utc_now()
    if migration_state_commit is not None:
        review_events = [
            event for event in (amendment.get("lifecycle") or {}).get("history", []) if event.get("status") == "REVIEW"
        ]
        if review_events:
            submitted_at = str(review_events[-1].get("at"))
    submitted_by = str((amendment.get("campaign") or {}).get("owner") or "codex")
    if hasattr(args, "agent"):
        submitted_by = normalized_identity(str(args.agent), "Amendment exit submitter")
    submission = {
        "id": f"R{len(attempts) + 1:02d}",
        "submitted_by": submitted_by,
        "submitted_at": submitted_at,
        "candidate_commit": candidate,
        "declared_candidate_commit": str(manifest.get("candidateCommit")),
        "branch": branch,
        "evidence_reference": {
            "type": "amendment-exit-evidence",
            "amendment_id": str(amendment["id"]),
            "path": relative,
            "sha256": evidence_sha256(payload),
            "commit": candidate,
        },
        "acceptance_criteria_sha256": canonical_json_sha256(approved_packet.get("acceptanceCriteria", [])),
        "selected_checks": selected_checks,
        "selected_checks_sha256": canonical_json_sha256(selected_checks),
        "prior_attempt_id": str((attempts[-1].get("submission") or {}).get("id")) if attempts else None,
        "open_finding_ids": open_ids,
    }
    submission["packet_sha256"] = amendment_exit_packet_sha256(submission)
    return submission


def load_amendment_exit_review_ledger(
    repo: Path,
    value: str,
) -> tuple[str, bytes, dict[str, Any]]:
    relative, path = safe_evidence_relative(repo, value, "Amendment exit review ledger")
    try:
        payload = path.read_bytes()
        ledger = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid amendment exit review ledger: {exc}") from exc
    if not isinstance(ledger, dict):
        raise SystemExit("Amendment exit review ledger root must be an object")
    return relative, payload, ledger


def prepare_amendment_exit_attempt(
    amendment: dict[str, Any],
    submission: dict[str, Any],
    ledger_relative: str,
    ledger_payload: bytes,
    ledger: dict[str, Any],
    *,
    reviewer: str,
    result: str,
) -> dict[str, Any]:
    amendment_id = str(amendment.get("id"))
    if ledger.get("amendment_id") != amendment_id or ledger.get("attempt_id") != submission.get("id"):
        raise SystemExit("Amendment exit review ledger identity does not match the current submission")
    if ledger.get("reviewer") != reviewer or ledger.get("result") != result:
        raise SystemExit("Amendment exit review ledger disposition does not match the command")
    ledger_evidence = ledger.get("evidence") or {}
    reference = submission.get("evidence_reference") or {}
    if any(ledger_evidence.get(field) != reference.get(field) for field in ("path", "sha256")):
        raise SystemExit("Amendment exit review ledger does not bind the submitted evidence")
    findings = ledger.get("findings")
    closures = ledger.get("closures")
    if not isinstance(findings, list) or not isinstance(closures, list):
        raise SystemExit("Amendment exit review ledger requires finding and closure arrays")
    finding_ids = [str(item.get("id") or "") for item in findings if isinstance(item, dict)]
    if len(finding_ids) != len(findings) or len(finding_ids) != len(set(finding_ids)):
        raise SystemExit("Amendment exit review findings require unique IDs")
    ordering = [REVIEW_SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
    if ordering != sorted(ordering) or any(value == 99 for value in ordering):
        raise SystemExit("Amendment exit review findings must be severity-ranked")
    control = (amendment.get("completion") or {}).get("exit_review_control") or {}
    open_findings = amendment_exit_open_findings(control.get("attempts") or [])
    closure_ids = [str(item.get("finding_id") or "") for item in closures if isinstance(item, dict)]
    if len(closure_ids) != len(closures) or len(closure_ids) != len(set(closure_ids)):
        raise SystemExit("Amendment exit closures require unique finding IDs")
    if not set(closure_ids).issubset(open_findings):
        raise SystemExit("Amendment exit closure does not target an open prior finding")
    for closure_id in closure_ids:
        open_findings.pop(closure_id, None)
    for finding in findings:
        open_findings[str(finding["id"])] = finding
    if result == "approved" and any(item.get("blocking") is True for item in open_findings.values()):
        raise SystemExit("Amendment exit approval is denied while blocking findings remain open")
    reviewed_state = str(ledger.get("reviewed_state_commit") or "")
    if re.fullmatch(r"[0-9a-f]{40}", reviewed_state) is None:
        raise SystemExit("Amendment exit review ledger lacks the exact reviewed state commit")
    review = {
        "reviewer": reviewer,
        "result": result,
        "reviewed_at": utc_now(),
        "reviewed_state_commit": reviewed_state,
        "notes": ledger.get("notes"),
    }
    return {
        "submission": submission,
        "review": review,
        "ledger": {"path": ledger_relative, "sha256": evidence_sha256(ledger_payload)},
        "findings": findings,
        "closures": closures,
    }


def command_amendment_submit(args, data, capabilities, slices, tasks, gates) -> None:
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    require_runtime_amendment_integrity(args.file, amendment)
    campaign = amendment.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit("Amendment campaign must be ACTIVE")
    require_active_lease(amendment, args.agent, f"Wave amendment {args.amendment}")
    if not amendment.get("tasks") or any(task.get("status") != "DONE" for task in amendment["tasks"]):
        raise SystemExit("Every authorized amendment task must be DONE before exit submission")
    evidence_values = list(args.evidence or [])
    if args.from_path:
        evidence_values = [args.from_path]
    if not evidence_values:
        raise SystemExit("Amendment exit evidence is required")
    if len(evidence_values) != 1:
        raise SystemExit("Controlled amendment exit submission binds exactly one evidence file")
    submission = build_amendment_exit_submission(args, data, amendment, evidence_values[0])
    completion = amendment["completion"]
    control = completion.setdefault("exit_review_control", {"version": 1, "attempts": [], "current_submission": None})
    if control.get("current_submission") is not None:
        raise SystemExit("An amendment exit submission is already awaiting review")
    control["current_submission"] = submission
    campaign.update(status="REVIEW", updated_at=utc_now(), lease=None)
    completion.update(
        status="REVIEW",
        reviewer=None,
        reviewed_at=None,
        evidence=[submission["evidence_reference"]["path"]],
        notes=args.note,
    )
    data["control_plane"]["active_amendment"] = None
    append_amendment_event(amendment, "REVIEW", args.agent, args.note or "Submitted amendment exit for review.")
    persist(args, data)


def command_amendment_review(args, data, capabilities, slices, tasks, gates) -> None:
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    require_runtime_amendment_integrity(args.file, amendment)
    campaign = amendment.get("campaign") or {}
    completion = amendment.get("completion") or {}
    if campaign.get("status") != "REVIEW" or completion.get("status") != "REVIEW":
        raise SystemExit("Amendment must be submitted for exit REVIEW")
    reviewer = normalized_identity(args.reviewer, "Amendment reviewer")
    if reviewer == campaign.get("owner"):
        raise SystemExit("Amendment reviewer must be independent from the campaign owner")
    if not args.from_path:
        raise SystemExit("Controlled amendment exit review requires --from <review-ledger>")
    repo = discover_repository(args.file)
    ledger_relative, ledger_payload, ledger = load_amendment_exit_review_ledger(repo, args.from_path)
    control = completion.get("exit_review_control")
    if control is None:
        reviewed_state = str(ledger.get("reviewed_state_commit") or "")
        evidence_values = list(completion.get("evidence") or [])
        if len(evidence_values) != 1:
            raise SystemExit("Legacy amendment exit review must bind exactly one submitted evidence path")
        submission = build_amendment_exit_submission(
            args,
            data,
            amendment,
            str(evidence_values[0]),
            migration_state_commit=reviewed_state,
        )
        control = {"version": 1, "attempts": [], "current_submission": submission}
        completion["exit_review_control"] = control
    current_submission = control.get("current_submission")
    if not isinstance(current_submission, dict):
        raise SystemExit("Amendment exit review lacks a frozen current submission")
    current_head, _branch = git_head_branch(repo)
    reviewed_state = str(ledger.get("reviewed_state_commit") or "")
    if control.get("attempts") and reviewed_state != current_head:
        raise SystemExit("Remediation review must bind the exact current frozen submission state")
    if not git_is_ancestor(repo, reviewed_state, current_head):
        raise SystemExit("Reviewed amendment exit state is not on current history")
    require_clean_repository(repo, allowed_untracked={ledger_relative})
    attempt = prepare_amendment_exit_attempt(
        amendment,
        current_submission,
        ledger_relative,
        ledger_payload,
        ledger,
        reviewer=reviewer,
        result=args.result,
    )
    control.setdefault("attempts", []).append(attempt)
    control["current_submission"] = None
    now = str((attempt.get("review") or {}).get("reviewed_at"))
    notes = str(ledger.get("notes") or args.note or "")
    if args.result == "approved":
        campaign.update(status="COMPLETE", updated_at=now, lease=None)
        completion.update(status="APPROVED", reviewer=reviewer, reviewed_at=now, notes=notes)
    else:
        state = "CHANGES_REQUESTED" if args.result == "changes-requested" else "BLOCKED"
        campaign.update(status="PAUSED", updated_at=now, pause_reason=notes or state, lease=None)
        completion.update(status=state, reviewer=reviewer, reviewed_at=now, notes=notes)
        append_amendment_event(
            amendment, "PAUSED" if state == "CHANGES_REQUESTED" else "BLOCKED", reviewer, notes or state
        )
    persist(args, data)


def command_amendment_adopt(args, data, capabilities, slices, tasks, gates) -> None:
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    require_runtime_amendment_integrity(args.file, amendment)
    completion = amendment.get("completion") or {}
    campaign = amendment.get("campaign") or {}
    if completion.get("status") != "APPROVED" or campaign.get("status") != "COMPLETE":
        raise SystemExit("Independent approved amendment-exit review is required before adoption")
    if not amendment.get("tasks") or any(task.get("status") != "DONE" for task in amendment["tasks"]):
        raise SystemExit("Every amendment task must be DONE and independently approved before adoption")
    if not args.from_path:
        raise SystemExit("Controlled adoption requires --from <checkpoint-evidence>")
    actor = normalized_identity(args.agent, "Adoption actor")
    repo = discover_repository(args.file)
    require_clean_repository(repo)
    current_head, current_branch = git_head_branch(repo)
    relative, path = safe_evidence_relative(repo, args.from_path, "Adoption checkpoint evidence")
    payload = git_blob(repo, current_head, relative)
    if payload is None:
        raise SystemExit("Adoption checkpoint evidence must exist in current HEAD")
    try:
        manifest = parse_evidence_payload(payload, path.suffix)
    except (UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid adoption checkpoint evidence: {exc}") from exc
    latest_attempts = (completion.get("exit_review_control") or {}).get("attempts") or []
    if not latest_attempts:
        raise SystemExit("Adoption requires immutable amendment exit review history")
    latest_review = latest_attempts[-1].get("review") or {}
    reviewed_completion_commit = str(manifest.get("reviewedCompletionCommit") or "")
    historical = historical_amendment_completion(repo, reviewed_completion_commit, str(amendment["id"])) or {}
    historical_attempts = (historical.get("exit_review_control") or {}).get("attempts") or []
    if (
        manifest.get("documentType") != "wave-amendment-adoption-evidence"
        or manifest.get("amendmentId") != amendment.get("id")
        or manifest.get("targetWave") != amendment.get("target_wave")
        or manifest.get("candidateCommit") != reviewed_completion_commit
        or manifest.get("branch") != current_branch
        or not git_is_ancestor(repo, reviewed_completion_commit, current_head)
        or not historical_attempts
        or historical_attempts[-1] != latest_attempts[-1]
        or (historical_attempts[-1].get("review") or {}).get("result") != "approved"
        or latest_review.get("result") != "approved"
    ):
        raise SystemExit("Adoption checkpoint does not bind the exact approved amendment exit history")
    reference = {
        "type": "amendment-adoption-evidence",
        "amendment_id": str(amendment["id"]),
        "path": relative,
        "sha256": evidence_sha256(payload),
        "commit": current_head,
    }
    wave = get(wave_map(data), str(amendment["target_wave"]), "wave")
    wave_campaign = wave.get("campaign") or {}
    if wave_campaign.get("status") != "PAUSED" or wave_campaign.get("scope") != "amendment-hold":
        raise SystemExit("Target Wave is not at the amendment-hold adoption boundary")
    checkpoints = wave.setdefault("checkpoints", [])
    checkpoint_id = f"{wave['id']}.CP{len(checkpoints) + 1:02d}"
    checkpoints.append(
        {
            "id": checkpoint_id,
            "kind": "security",
            "recorded_by": actor,
            "recorded_at": utc_now(),
            "evidence": [reference],
            "notes": args.note or f"Adopted {args.amendment} control-plane amendment.",
        }
    )
    wave_campaign["scope"] = "wave"
    data["control_plane"]["active_amendment"] = None
    append_amendment_event(amendment, "ADOPTED", actor, args.note or f"Adopted via {checkpoint_id}.")
    persist(args, data)
    print(f"Adopted {args.amendment}; {wave['id']} remains PAUSED until an explicit Wave resume")


def command_amendment_dispose(args, data, capabilities, slices, tasks, gates) -> None:
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    lifecycle = (amendment.get("lifecycle") or {}).get("status")
    if lifecycle in AMENDMENT_TERMINAL_STATES:
        raise SystemExit("A terminal amendment disposition cannot be repeated")
    campaign = amendment.get("campaign") or {}
    if campaign.get("status") in {"ACTIVE", "REVIEW"}:
        raise SystemExit("Pause the amendment and resolve active/review work before disposition")
    if any(task.get("status") in {"IN_PROGRESS", "REVIEW"} for task in amendment.get("tasks", [])):
        raise SystemExit("Active or review amendment tasks must be resolved before disposition")
    reviewer = normalized_identity(args.reviewer, "Amendment disposition reviewer")
    implementer = (amendment.get("bootstrap") or {}).get("implementer")
    if reviewer in {implementer, campaign.get("owner")}:
        raise SystemExit("Amendment disposition reviewer must be independent from implementation ownership")
    safe_resume = args.safe_resume_condition.strip()
    if not safe_resume:
        raise SystemExit("An explicit safe-resume condition is required")
    if not args.evidence:
        raise SystemExit("Disposition evidence is required")
    terminal = "DEFERRED" if args.result == "deferred" else "WITHDRAWN"
    for task in amendment.get("tasks", []):
        if task.get("status") not in {"DONE", "CANCELLED"}:
            task.update(status="DEFERRED", lease=None, updated_at=utc_now())
    amendment["completion"].update(
        status="PAUSED",
        reviewer=reviewer,
        reviewed_at=utc_now(),
        evidence=args.evidence,
        notes=f"{args.note}\nSafe-resume condition: {safe_resume}".strip(),
    )
    wave = get(wave_map(data), str(amendment["target_wave"]), "wave")
    wave_campaign = wave.get("campaign") or {}
    if wave_campaign.get("status") != "PAUSED":
        raise SystemExit("Target Wave must remain PAUSED during amendment disposition")
    wave_campaign["scope"] = "wave"
    checkpoints = wave.setdefault("checkpoints", [])
    checkpoint_id = f"{wave['id']}.CP{len(checkpoints) + 1:02d}"
    checkpoints.append(
        {
            "id": checkpoint_id,
            "kind": "security",
            "recorded_by": reviewer,
            "recorded_at": utc_now(),
            "evidence": args.evidence,
            "notes": f"{terminal} {args.amendment}; safe-resume condition: {safe_resume}",
        }
    )
    data["control_plane"]["active_amendment"] = None
    append_amendment_event(
        amendment,
        terminal,
        reviewer,
        f"{args.note or terminal}; safe-resume condition: {safe_resume}",
    )
    persist(args, data)
    print(f"Recorded append-only {terminal} disposition for {args.amendment}; {wave['id']} remains PAUSED")


def command_wave_status(args, data, capabilities, slices, tasks, gates) -> None:
    waves = wave_map(data)
    selected = [get(waves, args.wave, "wave")] if args.wave else list(waves.values())
    for wave in selected:
        wave_id = str(wave["id"])
        view = {
            "id": wave_id,
            "title": wave.get("title"),
            "goal": wave.get("goal"),
            "approval": wave.get("approval"),
            "campaign": wave.get("campaign"),
            "checkpoints": wave.get("checkpoints", []),
            "completion": wave.get("completion"),
            "task_states": dict(Counter(task["status"] for task in tasks.values() if task_wave(task) == wave_id)),
            "slice_completion": dict(
                Counter(
                    slice_.get("completion", {}).get("status")
                    for slice_ in slices.values()
                    if slice_.get("wave") == wave_id
                )
            ),
        }
        if wave_id in wave_approval_base_map(data):
            view["approvalAuthority"] = {
                "base": wave_approval_base_map(data)[wave_id],
                "amendments": [
                    amendment
                    for amendment in data.get("wave_amendments", [])
                    if amendment.get("target_wave") == wave_id
                ],
            }
        print_yaml(view)


def command_wave_start(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    require_execution_target(args.profile, args.platform)
    wave = get(wave_map(data), args.wave, "wave")
    pending_bootstrap = approved_unbootstrapped_amendment(args.file, data, str(wave["id"]))
    if pending_bootstrap is not None:
        raise SystemExit(f"Wave {wave['id']} is interrupted by approved amendment {pending_bootstrap['id']}")
    if blocking_wave_amendments(data, str(wave["id"])):
        raise SystemExit(f"Wave {wave['id']} is interrupted by an unfinished approved amendment")
    program = global_program_position(data, slices, tasks, gates)
    if program.get("state") != "ACTIVE_WAVE" or program.get("current_wave") != wave["id"]:
        raise SystemExit(
            f"Wave {wave['id']} cannot start at program position {program.get('state')}/"
            f"{program.get('current_wave')}; next gate is {gate_transition_label(program.get('next_gate'))}"
        )
    if (wave.get("approval") or {}).get("status") != "APPROVED":
        raise SystemExit(f"Wave {wave['id']} has no approved pre-Wave packet")
    require_wave_planning_ready(args, str(wave["id"]))
    if active_wave_campaigns(data) or active_capabilities(capabilities):
        raise SystemExit("Another Wave or legacy capability campaign is ACTIVE")
    prior = wave.get("campaign") or {}
    if prior.get("status") not in {None, "PLANNED"}:
        raise SystemExit(f"Wave cannot start from campaign state {prior.get('status')}")
    agent, branch, base_sha, worktree = git_execution_identity(
        args.file,
        agent=args.agent,
        branch=args.branch,
        base_sha=args.base_sha,
        worktree=args.worktree,
    )
    candidates = ready_tasks_in_wave(data, wave, capabilities, slices, tasks, gates, args.profile, args.platform)
    if not candidates:
        raise SystemExit("Wave has no READY task for the requested profile/platform")
    now = utc_now()
    wave["campaign"] = {
        "status": "ACTIVE",
        "scope": "wave",
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
    wave["completion"].update(status="IN_PROGRESS", reviewer=None, reviewed_at=None, evidence=[], notes=None)
    persist(args, data)
    print(f"Started durable Wave campaign {wave['id']} — {wave.get('title')}")


def command_wave_pause(args, data, capabilities, slices, tasks, gates) -> None:
    wave = get(wave_map(data), args.wave, "wave")
    campaign = wave.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit("Only an ACTIVE Wave may be paused")
    require_active_lease(wave, args.agent, f"Wave {wave['id']}")
    if any(
        task.get("wave") == wave["id"] and task.get("status") in {"IN_PROGRESS", "REVIEW"} for task in tasks.values()
    ):
        raise SystemExit("Resolve or explicitly block active/review tasks before pausing the Wave")
    campaign.update(
        status="PAUSED",
        pause_reason=args.reason,
        pause_category=args.category,
        updated_at=utc_now(),
        lease=None,
    )
    wave["completion"]["status"] = "PAUSED"
    persist(args, data)


def command_wave_renew(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    wave = get(wave_map(data), args.wave, "wave")
    campaign = wave.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit("Only an ACTIVE Wave lease may be renewed")
    if campaign.get("owner") != args.agent:
        raise SystemExit(f"Wave {wave['id']} is owned by {campaign.get('owner')}, not {args.agent}")
    if lease_is_active(wave):
        require_active_lease(wave, args.agent, f"Wave {wave['id']}")
    campaign["lease"] = new_lease(args.agent, args.lease_hours)
    campaign["updated_at"] = utc_now()
    persist(args, data)


def command_wave_resume(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    require_execution_target(args.profile, args.platform)
    wave = get(wave_map(data), args.wave, "wave")
    pending_bootstrap = approved_unbootstrapped_amendment(args.file, data, str(wave["id"]))
    if pending_bootstrap is not None:
        raise SystemExit(
            f"Wave {wave['id']} cannot resume until approved amendment {pending_bootstrap['id']} is adopted"
        )
    if blocking_wave_amendments(data, str(wave["id"])):
        raise SystemExit(f"Wave {wave['id']} cannot resume until its interrupting amendment is adopted or disposed")
    campaign = wave.get("campaign") or {}
    if campaign.get("status") != "PAUSED":
        raise SystemExit("Only a PAUSED Wave may be resumed")
    if active_wave_campaigns(data) or active_capabilities(capabilities):
        raise SystemExit("Another Wave or legacy capability campaign is ACTIVE")
    program = global_program_position(data, slices, tasks, gates)
    review_remediation = (wave.get("completion") or {}).get("status") in {"CHANGES_REQUESTED", "BLOCKED"}
    if not review_remediation and (program.get("state") != "ACTIVE_WAVE" or program.get("current_wave") != wave["id"]):
        raise SystemExit("Paused Wave is outside the current program position")
    require_wave_planning_ready(args, str(wave["id"]))
    agent, branch, base_sha, worktree = git_execution_identity(
        args.file,
        agent=args.agent,
        branch=args.branch,
        base_sha=args.base_sha,
        worktree=args.worktree,
    )
    if campaign.get("owner") != agent:
        raise SystemExit(f"Paused Wave is owned by {campaign.get('owner')}, not {agent}")
    if campaign.get("branch") and campaign.get("branch") != branch:
        raise SystemExit("Paused Wave must resume on its recorded branch")
    campaign.update(
        status="ACTIVE",
        branch=branch,
        worktree=worktree,
        base_sha=base_sha,
        profile=args.profile,
        platform=args.platform,
        updated_at=utc_now(),
        pause_reason=None,
        pause_category=None,
        lease=new_lease(agent, args.lease_hours),
    )
    wave["completion"]["status"] = "IN_PROGRESS"
    persist(args, data)


def command_wave_checkpoint(args, data, capabilities, slices, tasks, gates) -> None:
    wave = get(wave_map(data), args.wave, "wave")
    campaign = wave.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit("Integration checkpoints require an ACTIVE Wave")
    require_active_lease(wave, args.agent, f"Wave {wave['id']}")
    if not args.evidence:
        raise SystemExit("Integration checkpoint evidence is required")
    checkpoints = wave.setdefault("checkpoints", [])
    checkpoint_id = f"{wave['id']}.CP{len(checkpoints) + 1:02d}"
    checkpoints.append(
        {
            "id": checkpoint_id,
            "kind": args.kind,
            "recorded_by": normalized_identity(args.agent, "Checkpoint actor"),
            "recorded_at": utc_now(),
            "evidence": args.evidence,
            "notes": args.note,
        }
    )
    campaign["updated_at"] = utc_now()
    persist(args, data)
    print(f"Recorded {checkpoint_id} ({args.kind})")


def command_wave_submit(args, data, capabilities, slices, tasks, gates) -> None:
    wave = get(wave_map(data), args.wave, "wave")
    if blocking_wave_amendments(data, str(wave["id"])):
        raise SystemExit(f"Wave {wave['id']} cannot submit while an interrupting amendment is unfinished")
    campaign = wave.get("campaign") or {}
    if campaign.get("status") != "ACTIVE":
        raise SystemExit("Wave campaign must be ACTIVE")
    require_active_lease(wave, args.agent, f"Wave {wave['id']}")
    if not wave_complete(str(wave["id"]), slices, tasks, data):
        raise SystemExit("Every Wave task must be DONE and every slice independently APPROVED before Wave submission")
    if not args.evidence:
        raise SystemExit("Full Wave-exit qualification evidence is required")
    campaign.update(status="REVIEW", updated_at=utc_now(), lease=None)
    wave["completion"].update(status="REVIEW", evidence=args.evidence, notes=args.note)
    persist(args, data)


def command_wave_review(args, data, capabilities, slices, tasks, gates) -> None:
    wave = get(wave_map(data), args.wave, "wave")
    if blocking_wave_amendments(data, str(wave["id"])):
        raise SystemExit(f"Wave {wave['id']} cannot complete review while an interrupting amendment is unfinished")
    campaign = wave.get("campaign") or {}
    completion = wave.get("completion") or {}
    if campaign.get("status") != "REVIEW" or completion.get("status") != "REVIEW":
        raise SystemExit("Wave must be submitted for REVIEW")
    reviewer = normalized_identity(args.reviewer, "Wave reviewer")
    if reviewer == campaign.get("owner"):
        raise SystemExit("Wave reviewer must be independent from the campaign owner")
    now = utc_now()
    if args.result == "approved":
        campaign.update(status="COMPLETE", updated_at=now, lease=None)
        completion.update(status="APPROVED", reviewer=reviewer, reviewed_at=now, notes=args.note)
    elif args.result == "changes-requested":
        campaign.update(
            status="PAUSED",
            updated_at=now,
            pause_reason="Wave review changes requested",
            pause_category="review-remediation",
            lease=None,
        )
        completion.update(status="CHANGES_REQUESTED", reviewer=reviewer, reviewed_at=now, notes=args.note)
    else:
        campaign.update(
            status="PAUSED",
            updated_at=now,
            pause_reason=args.note or "Wave review blocked",
            pause_category="review-remediation",
            lease=None,
        )
        completion.update(status="BLOCKED", reviewer=reviewer, reviewed_at=now, notes=args.note)
    persist(args, data)


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
    active_waves = active_wave_campaigns(data)
    if active_waves:
        wave = active_waves[0]
        require_active_lease(wave, args.agent, f"Wave {wave['id']}")
        if slice_.get("wave") != wave.get("id") or current_slice(capability, str(wave["id"])) is not slice_:
            raise SystemExit("Only a current dependency-eligible slice in the active Wave may be submitted")
    else:
        if (capability.get("campaign") or {}).get("status") != "ACTIVE":
            raise SystemExit("The parent legacy capability campaign must be ACTIVE")
        require_active_lease(capability, args.agent, f"Capability {capability['id']}")
        wave_id = campaign_wave(capability)
        if wave_id is None or slice_.get("wave") != wave_id or current_slice(capability, wave_id) is not slice_:
            raise SystemExit("Only the current slice in the active legacy capability-wave increment may be submitted")
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
    active_waves = active_wave_campaigns(data)
    campaign_holder: dict[str, Any]
    if active_waves:
        campaign_holder = active_waves[0]
        if campaign_holder.get("id") != slice_.get("wave"):
            raise SystemExit("Slice review must belong to the active Wave campaign")
    else:
        campaign_holder = capability
        campaign = capability.get("campaign") or {}
        if campaign.get("status") != "ACTIVE" or campaign.get("wave") != slice_.get("wave"):
            raise SystemExit("Slice review must belong to the active legacy capability-wave increment")
    if reviewer == (campaign_holder.get("campaign") or {}).get("owner"):
        raise SystemExit("Slice reviewer must be independent from the Wave campaign owner")
    now = utc_now()
    if args.result == "approved":
        slice_["completion"].update(status="APPROVED", reviewer=reviewer, reviewed_at=now, notes=args.note)
        slice_["status"] = "DONE"
        wave_id = str(slice_["wave"])
        if (
            not active_waves
            and capability_wave_complete(capability, wave_id)
            and any(
                candidate.get("completion", {}).get("status") != "APPROVED"
                for candidate in capability.get("slices", [])
                if candidate.get("wave") != wave_id
            )
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
        amendment = amendment_for_task(data, task)
        if amendment is None:
            raise SystemExit("Task is not eligible for the requested profile/platform")
    amendment = amendment_for_task(data, task)
    if amendment is not None:
        require_runtime_amendment_integrity(args.file, amendment)
        campaign = amendment.get("campaign") or {}
        if campaign.get("status") != "ACTIVE" or campaign.get("scope") != "wave-amendment":
            raise SystemExit(f"Wave amendment {amendment['id']} campaign is not ACTIVE")
        require_active_lease(amendment, agent, f"Wave amendment {amendment['id']}")
        if args.profile != campaign.get("profile") or args.platform != campaign.get("platform"):
            raise SystemExit("Task claim profile/platform must match the active amendment campaign")
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
        print(f"Claimed {task['id']} within Wave amendment {amendment['id']}")
        return
    blockers = blocking_wave_amendments(data, str(task.get("wave")))
    if blockers:
        raise SystemExit(f"Ordinary task claim denied while {blockers[0]['id']} interrupts {task.get('wave')}")
    active_waves = active_wave_campaigns(data)
    if active_waves:
        holder = active_waves[0]
        campaign = holder["campaign"]
        if holder.get("id") != task.get("wave") or campaign.get("scope") != "wave":
            raise SystemExit("Task is outside the active Wave campaign")
        require_active_lease(holder, agent, f"Wave {holder['id']}")
    else:
        active = active_capabilities(capabilities)
        if not active:
            raise SystemExit(f"No ACTIVE Wave campaign. Start {task['wave']} before claiming tasks.")
        if active[0]["id"] != task["capability_id"]:
            raise SystemExit(f"Active legacy campaign is {active[0]['id']}; task belongs to {task['capability_id']}")
        holder = active[0]
        campaign = active[0]["campaign"]
        require_active_lease(holder, agent, f"Capability {active[0]['id']}")
        if campaign.get("scope") != "capability-wave" or campaign.get("wave") != task.get("wave"):
            raise SystemExit("Task is outside the active legacy capability-wave increment")
    if args.profile != campaign.get("profile") or args.platform != campaign.get("platform"):
        raise SystemExit("Task claim profile/platform must match the active Wave campaign")
    selected_slice = current_slice(capabilities[task["capability_id"]], str(task["wave"]))
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
    require_task_campaign_lease(task, capabilities, args.agent, data)
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
    require_task_campaign_lease(task, capabilities, args.agent, data)
    if lease_is_active(task):
        require_active_lease(task, args.agent, f"Task {task['id']}")
    task["lease"] = new_lease(args.agent, args.lease_hours)
    task["updated_at"] = utc_now()
    persist(args, data)
    print(f"Renewed task lease for {task['id']}")


def prepare_task_evidence(
    task: dict[str, Any],
    repo: Path,
    from_file: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence_path = Path(from_file).resolve()
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
    control = task.get("review_control") or {}
    attempts = control.get("attempts") or []
    if attempts:
        prior_submission = attempts[-1].get("submission") or {}
        prior_reference = prior_submission.get("evidence_reference") or {}
        if not isinstance(supersedes, dict) or any(
            supersedes.get(field) != prior_reference.get(field) for field in ("path", "sha256", "commit")
        ):
            raise SystemExit(
                "Remediation evidence must supersede the immediately preceding submission's exact evidence reference"
            )
        expected_base_commit = prior_submission.get("candidate_commit")
    else:
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
    return (
        {
            "type": "criterion-manifest",
            "path": relative_evidence_path,
            "sha256": payload_sha256,
            "commit": manifest["commit"],
            "recorded_at": utc_now(),
        },
        manifest,
    )


def build_task_submission_packet(
    task: dict[str, Any],
    manifest: dict[str, Any],
    reference: dict[str, Any],
    agent: str,
    repo: Path,
) -> dict[str, Any]:
    selection = manifest.get("verificationSelection")
    if not isinstance(selection, dict) or not str(selection.get("riskAnalysis") or "").strip():
        raise SystemExit("Atomic submission requires verificationSelection.riskAnalysis")
    checks = manifest.get("checks") or []
    selected_checks = [str(item.get("command")) for item in checks if isinstance(item, dict) and item.get("command")]
    if not selected_checks or len(selected_checks) != len(set(selected_checks)):
        raise SystemExit("Atomic submission requires unique selected check commands")
    try:
        command_ids = selected_command_ids(selection, require_nonempty=True)
        require_canonical_selected_command_ids(command_ids, repo)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    control = task.get("review_control") or {"version": 1, "attempts": [], "current_submission": None}
    if control.get("current_submission") is not None:
        raise SystemExit("Task already has a frozen submission awaiting review")
    attempts = control.get("attempts") or []
    open_findings = task_open_findings(attempts)
    disposition = manifest.get("reviewerDisposition") or {}
    declared_open = disposition.get("openFindingIds", [])
    if not isinstance(declared_open, list) or sorted(str(item) for item in declared_open) != sorted(open_findings):
        raise SystemExit("Remediation evidence must replay the exact open finding IDs")
    root_cause = disposition.get("rootCauseAnalysis")
    if len(attempts) >= 2 and open_findings and not (isinstance(root_cause, str) and root_cause.strip()):
        raise SystemExit("Remediation after round two requires rootCauseAnalysis")
    if len(attempts) >= 2 and open_findings:
        prior_submission = attempts[-1].get("submission") or {}
        risk_analysis = str(selection.get("riskAnalysis") or "")
        if risk_analysis == str(prior_submission.get("selection_rationale") or "") or any(
            finding_id not in risk_analysis for finding_id in open_findings
        ):
            raise SystemExit("Remediation after round two requires expanded riskAnalysis naming every open finding ID")
    packet = {
        "id": f"R{len(attempts) + 1:02d}",
        "submitted_by": agent,
        "submitted_at": utc_now(),
        "candidate_commit": manifest["commit"],
        "base_commit": manifest["baseCommit"],
        "branch": manifest["branch"],
        "evidence_reference": copy.deepcopy(reference),
        "acceptance_criteria_sha256": canonical_json_sha256(task.get("acceptance_criteria", [])),
        "changed_paths": list(manifest.get("changedFiles") or []),
        "selected_checks": selected_checks,
        "deferred_checks": normalized_deferred_checks(selection),
        "selection_rationale": str(selection["riskAnalysis"]),
        "selection_sha256": canonical_json_sha256(selection),
        "prior_attempt_id": (attempts[-1].get("submission") or {}).get("id") if attempts else None,
        "open_finding_ids": sorted(open_findings),
        "root_cause_analysis": root_cause if isinstance(root_cause, str) and root_cause.strip() else None,
    }
    if command_ids:
        packet["selected_command_ids"] = command_ids
    packet["packet_sha256"] = task_submission_packet_sha256(packet)
    return packet


def command_evidence(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    amendment = amendment_for_task(data, task)
    if amendment is not None:
        require_runtime_amendment_integrity(args.file, amendment)
    if task["status"] != "IN_PROGRESS":
        raise SystemExit("Evidence may be attached only while IN_PROGRESS")
    require_task_campaign_lease(task, capabilities, args.agent, data)
    require_active_lease(task, args.agent, f"Task {task['id']}")
    if int((data.get("control_plane") or {}).get("minimum_tool_revision", 0)) >= 3:
        raise SystemExit("Use taskctl submit --from to attach evidence and enter REVIEW atomically")
    repo = discover_repository(args.file)
    reference, _manifest = prepare_task_evidence(task, repo, args.from_file)
    task.setdefault("evidence", []).append(reference)
    task["verification_state"] = "passed"
    task["updated_at"] = utc_now()
    persist(args, data)


def command_submit(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    amendment = amendment_for_task(data, task)
    if amendment is not None:
        require_runtime_amendment_integrity(args.file, amendment)
    if task["status"] != "IN_PROGRESS":
        raise SystemExit("Only IN_PROGRESS tasks may be submitted")
    require_task_campaign_lease(task, capabilities, args.agent, data)
    require_active_lease(task, args.agent, f"Task {task['id']}")
    if getattr(args, "from_file", None):
        repo = discover_repository(args.file)
        reference, manifest = prepare_task_evidence(task, repo, args.from_file)
        packet = build_task_submission_packet(task, manifest, reference, str(args.agent), repo)
        task.setdefault("evidence", []).append(reference)
        task["verification_state"] = "passed"
        task["review_control"] = task.get("review_control") or {
            "version": 1,
            "attempts": [],
            "current_submission": None,
        }
        task["review_control"]["current_submission"] = packet
    else:
        if int((data.get("control_plane") or {}).get("minimum_tool_revision", 0)) >= 3:
            raise SystemExit("Controlled task submission requires --from for atomic evidence attachment")
        if task.get("verification_state") != "passed" or not task.get("evidence"):
            raise SystemExit("Verification must pass and evidence must be attached before REVIEW")
    task["status"] = "REVIEW"
    task["updated_at"] = utc_now()
    task["implementation_notes"] = ((task.get("implementation_notes") or "") + "\n" + args.note).strip()
    persist(args, data)


def prepare_task_review_attempt(
    task: dict[str, Any],
    reviewer: str,
    result: str,
    from_file: str,
    note: str,
    repo: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    control = task.get("review_control") or {}
    submission = control.get("current_submission")
    if not isinstance(submission, dict):
        raise SystemExit("Controlled review requires one frozen current submission")
    ledger_path = Path(from_file).resolve()
    try:
        relative = ledger_path.relative_to(repo).as_posix()
    except ValueError as exc:
        raise SystemExit("Task review ledger must be stored inside the repository") from exc
    if not relative.startswith("artifacts/evidence/") or "\\" in relative:
        raise SystemExit("Task review ledger must be stored under artifacts/evidence")
    try:
        payload = ledger_path.read_bytes()
        document = parse_evidence_payload(payload, ledger_path.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid task review ledger: {exc}") from exc
    if document.get("task_id") != task.get("id"):
        raise SystemExit("Task review ledger task_id does not match")
    if document.get("attempt_id") != submission.get("id"):
        raise SystemExit("Task review ledger attempt_id does not match the frozen submission")
    if document.get("candidate_commit") != submission.get("candidate_commit"):
        raise SystemExit("Task review ledger candidate_commit does not match the frozen submission")
    if document.get("reviewer") != reviewer or document.get("result") != result:
        raise SystemExit("Task review ledger reviewer/result does not match the review command")
    ledger_note = document.get("notes", "")
    if not isinstance(ledger_note, str) or (note and note != ledger_note):
        raise SystemExit("Task review ledger notes do not match the review command")
    findings = document.get("findings")
    closures = document.get("closures")
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        raise SystemExit("Task review ledger findings must be a list of structured findings")
    if not isinstance(closures, list) or not all(isinstance(item, dict) for item in closures):
        raise SystemExit("Task review ledger closures must be a list of structured closures")
    severities = [REVIEW_SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
    if 99 in severities or severities != sorted(severities):
        raise SystemExit("Task review findings must use known severities in descending severity order")
    existing_attempts = control.get("attempts") or []
    seen_ids = {str(finding.get("id")) for attempt in existing_attempts for finding in attempt.get("findings", [])}
    new_ids = [str(finding.get("id")) for finding in findings]
    if len(new_ids) != len(set(new_ids)) or seen_ids.intersection(new_ids):
        raise SystemExit("Task review finding IDs must be globally unique")
    open_before = task_open_findings(existing_attempts)
    closure_ids = [str(closure.get("finding_id")) for closure in closures]
    if len(closure_ids) != len(set(closure_ids)) or any(item not in open_before for item in closure_ids):
        raise SystemExit("Every task review closure must name one unique open prior finding")
    open_after = dict(open_before)
    for finding_id in closure_ids:
        open_after.pop(finding_id)
    for finding in findings:
        open_after[str(finding.get("id"))] = finding
    blocking_after = [finding for finding in open_after.values() if finding.get("blocking") is True]
    if result == "approved" and blocking_after:
        raise SystemExit("Task approval is denied while a blocking finding remains open")
    if result in {"changes-requested", "blocked"} and not blocking_after:
        raise SystemExit("An adverse task review requires at least one open blocking finding")
    prior_ledgers = [attempt.get("ledger") or {} for attempt in existing_attempts]
    payload_hash = evidence_sha256(payload)
    if any(item.get("path") == relative or item.get("sha256") == payload_hash for item in prior_ledgers):
        raise SystemExit("Task review ledger path/hash is already recorded")
    review: dict[str, Any] = {
        "reviewer": reviewer,
        "result": result,
        "reviewed_at": utc_now(),
        "notes": ledger_note,
    }
    attempt: dict[str, Any] = {
        "submission": copy.deepcopy(submission),
        "review": review,
        "ledger": {"path": relative, "sha256": payload_hash},
        "findings": copy.deepcopy(findings),
        "closures": copy.deepcopy(closures),
    }
    attempt["telemetry"] = build_task_review_telemetry_event(task, attempt)
    try:
        require_canonical_selected_command_ids(attempt["telemetry"]["command_ids"], repo)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return attempt, review


def command_review_telemetry(args, data, capabilities, slices, tasks, gates) -> None:
    del data, capabilities, slices, gates
    errors = [
        error
        for task in tasks.values()
        for attempt in (task.get("review_control") or {}).get("attempts", [])
        for error in task_review_telemetry_errors(task, attempt, getattr(args, "repo_root", None))
    ]
    if errors:
        raise SystemExit("Invalid review telemetry:\n- " + "\n- ".join(errors))
    print(json.dumps(task_review_telemetry_events(tasks), indent=2, sort_keys=True))


def command_review(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    amendment = amendment_for_task(data, task)
    if amendment is not None:
        require_runtime_amendment_integrity(args.file, amendment)
    if task["status"] != "REVIEW":
        raise SystemExit("Only REVIEW tasks may be reviewed")
    reviewer = normalized_identity(args.reviewer, "Reviewer")
    if reviewer == task.get("owner"):
        raise SystemExit("Task reviewer must be independent from the task owner")
    now = utc_now()
    control = task.get("review_control")
    if control is not None:
        if not getattr(args, "from_file", None):
            raise SystemExit("Controlled task review requires --from with a consolidated finding ledger")
        repo = discover_repository(args.file)
        attempt, review = prepare_task_review_attempt(
            task,
            reviewer,
            args.result,
            args.from_file,
            args.note,
            repo,
        )
        control.setdefault("attempts", []).append(attempt)
        control["current_submission"] = None
        task["review"] = review
        now = str(review["reviewed_at"])
    else:
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
    if task["status"] == "REVIEW" and task.get("review_control") is not None:
        raise SystemExit("A controlled REVIEW submission must receive an independent disposition before remediation")
    holder = require_task_campaign_lease(task, capabilities, agent, data)
    amendment = amendment_for_task(data, task)
    if amendment is not None:
        if not task_can_be_ready(data, capabilities, slices, tasks, gates, task):
            raise SystemExit("Amendment task cannot be reopened while its dependency is incomplete")
        if any(
            gate.get("status") == "APPROVED" and gate.get("after_wave") == task_wave(task) for gate in gates.values()
        ):
            raise SystemExit("Task cannot be reopened after its Wave release gate is APPROVED")
        lease = task.get("lease")
        if lease_is_active(task) and lease and lease.get("claimed_by") != agent:
            raise SystemExit(f"Task {task['id']} has an active lease owned by {lease.get('claimed_by')}")
        review_projection = (
            task.get("review")
            if task.get("review_control") is not None
            else {
                "reviewer": None,
                "result": None,
                "reviewed_at": None,
                "notes": f"Reopened: {args.reason}",
            }
        )
        task.update(
            status="IN_PROGRESS",
            owner=agent,
            updated_at=utc_now(),
            completed_at=None,
            verification_state=None,
            blocker=None,
            review=review_projection,
            lease=new_lease(agent, args.lease_hours),
        )
        persist(args, data)
        return
    capability = capabilities[task["capability_id"]]
    active_wave_id = holder.get("id") if holder in active_wave_campaigns(data) else campaign_wave(capability)
    wave_remediation = (
        holder in active_wave_campaigns(data)
        and (holder.get("completion") or {}).get("status") in {"IN_PROGRESS", "CHANGES_REQUESTED", "BLOCKED"}
        and wave_complete(str(active_wave_id), slices, tasks, data)
    )
    if not wave_remediation and current_slice(capability, str(active_wave_id)) is not slices[task["slice_id"]]:
        raise SystemExit("Only a task in the active Wave campaign's current capability slice may be reopened")
    if not task_can_be_ready(data, capabilities, slices, tasks, gates, task):
        raise SystemExit("Task cannot be reopened while dependencies or the activation gate are incomplete")
    if any(gate.get("status") == "APPROVED" and gate.get("after_wave") == task.get("wave") for gate in gates.values()):
        raise SystemExit("Task cannot be reopened after its wave release gate is APPROVED")
    lease = task.get("lease")
    if lease_is_active(task) and lease and lease.get("claimed_by") != agent:
        raise SystemExit(f"Task {task['id']} has an active lease owned by {lease.get('claimed_by')}")
    review_projection = (
        task.get("review")
        if task.get("review_control") is not None
        else {
            "reviewer": None,
            "result": None,
            "reviewed_at": None,
            "notes": f"Reopened: {args.reason}",
        }
    )
    task.update(
        status="IN_PROGRESS",
        owner=agent,
        updated_at=utc_now(),
        completed_at=None,
        verification_state=None,
        blocker=None,
        cancellation=None,
        review=review_projection,
        lease=new_lease(agent, args.lease_hours),
    )
    if wave_remediation:
        parent_slice = slices[task["slice_id"]]
        parent_slice["status"] = "IN_PROGRESS"
        parent_slice.setdefault("completion", {})["status"] = "CHANGES_REQUESTED"
    persist(args, data)


def command_cancel(args, data, capabilities, slices, tasks, gates) -> None:
    task = get(tasks, args.task, "task")
    if amendment_for_task(data, task) is not None:
        raise SystemExit("Approved amendment tasks cannot be cancelled; use an append-only amendment disposition")
    if task["status"] in {"DONE", "CANCELLED"}:
        raise SystemExit(f"{task['status']} tasks cannot transition to CANCELLED")
    actor = normalized_identity(args.actor, "Cancellation actor")
    holder = require_task_campaign_lease(task, capabilities, actor, data)
    capability = capabilities[task["capability_id"]]
    active_wave_id = holder.get("id") if holder in active_wave_campaigns(data) else campaign_wave(capability)
    if current_slice(capability, str(active_wave_id)) is not slices[task["slice_id"]]:
        raise SystemExit("Only a task in the active Wave campaign's current capability slice may be cancelled")
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
    pending_bootstrap = approved_unbootstrapped_amendment(args.file, data, str(gate.get("after_wave")))
    if pending_bootstrap is not None:
        raise SystemExit(
            f"Release gate {gate['id']} cannot approve while approved amendment {pending_bootstrap['id']} is unfinished"
        )
    ordered_gates = [candidate for candidate in data.get("release_gates", []) if isinstance(candidate, dict)]
    gate_index = next(index for index, candidate in enumerate(ordered_gates) if candidate.get("id") == gate["id"])
    prior_pending = [
        str(candidate.get("id")) for candidate in ordered_gates[:gate_index] if candidate.get("status") != "APPROVED"
    ]
    if prior_pending:
        raise SystemExit(
            f"Release gate {gate['id']} cannot approve before upstream gate {prior_pending[0]} is APPROVED"
        )
    blockers = blocking_wave_amendments(data, str(gate.get("after_wave")))
    if blockers:
        raise SystemExit(
            f"Release gate {gate['id']} cannot approve while interrupting amendment {blockers[0]['id']} is unfinished"
        )
    incomplete = sorted(
        task["id"] for task in tasks.values() if task_wave(task) == gate.get("after_wave") and task["status"] != "DONE"
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
    wave = get(wave_map(data), str(gate.get("after_wave")), "wave")
    if (wave.get("completion") or {}).get("status") != "APPROVED":
        raise SystemExit(
            f"Release gate {gate['id']} cannot approve before {wave['id']} passes independent Wave qualification review"
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
            if task_wave(task) == wid and task["status"] == "DEFERRED":
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
    sub.add_parser("review-telemetry")
    n = sub.add_parser("next")
    n.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    n.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    nc = sub.add_parser("next-capability")
    nc.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    nc.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    sh = sub.add_parser("show")
    sh.add_argument("task")
    amendment = sub.add_parser("amendment")
    ams = amendment.add_subparsers(dest="amendment_command", required=True)
    amstat = ams.add_parser("status")
    amstat.add_argument("amendment", nargs="?")
    ambs = ams.add_parser("bootstrap-submit")
    ambs.add_argument("amendment")
    ambs.add_argument("--agent", required=True)
    ambs.add_argument("--approval-commit", required=True)
    ambs.add_argument("--implementation-commit", required=True)
    ambs.add_argument("--evidence", required=True)
    ambr = ams.add_parser("bootstrap-review")
    ambr.add_argument("amendment")
    ambr.add_argument("--reviewer", required=True)
    ambr.add_argument("--result", choices=["approved", "changes-requested", "blocked"], required=True)
    ambr.add_argument("--note", default="")
    ambrs = ams.add_parser("bootstrap-resubmit")
    ambrs.add_argument("amendment")
    ambrs.add_argument("--agent", required=True)
    ambrs.add_argument("--implementation-commit", required=True)
    ambrs.add_argument("--evidence", required=True)
    ammat = ams.add_parser("materialize")
    ammat.add_argument("amendment")
    ammat.add_argument("--agent", required=True)
    amact = ams.add_parser("activate")
    amact.add_argument("amendment")
    amact.add_argument("--agent", required=True)
    amact.add_argument("--branch", required=True)
    amact.add_argument("--base-sha", required=True)
    amact.add_argument("--worktree", required=True)
    amact.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    amact.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    amact.add_argument("--lease-hours", type=int, default=24)
    ampause = ams.add_parser("pause")
    ampause.add_argument("amendment")
    ampause.add_argument("--agent", required=True)
    ampause.add_argument("--reason", required=True)
    amsubmit = ams.add_parser("submit")
    amsubmit.add_argument("amendment")
    amsubmit.add_argument("--agent", required=True)
    amsubmit.add_argument("--evidence", action="append")
    amsubmit.add_argument("--from", dest="from_path")
    amsubmit.add_argument("--note", default="")
    amreview = ams.add_parser("review")
    amreview.add_argument("amendment")
    amreview.add_argument("--reviewer", required=True)
    amreview.add_argument("--result", choices=["approved", "changes-requested", "blocked"], required=True)
    amreview.add_argument("--from", dest="from_path")
    amreview.add_argument("--note", default="")
    amadopt = ams.add_parser("adopt")
    amadopt.add_argument("amendment")
    amadopt.add_argument("--agent", required=True)
    amadopt.add_argument("--evidence", action="append")
    amadopt.add_argument("--from", dest="from_path")
    amadopt.add_argument("--note", default="")
    amdispose = ams.add_parser("dispose")
    amdispose.add_argument("amendment")
    amdispose.add_argument("--reviewer", required=True)
    amdispose.add_argument("--result", choices=["deferred", "withdrawn"], required=True)
    amdispose.add_argument("--safe-resume-condition", required=True)
    amdispose.add_argument("--evidence", action="append", required=True)
    amdispose.add_argument("--note", default="")
    wave = sub.add_parser("wave")
    ws = wave.add_subparsers(dest="wave_command", required=True)
    wstat = ws.add_parser("status")
    wstat.add_argument("wave", nargs="?")
    wstart = ws.add_parser("start")
    wstart.add_argument("wave")
    wstart.add_argument("--agent", required=True)
    wstart.add_argument("--branch", required=True)
    wstart.add_argument("--base-sha", required=True)
    wstart.add_argument("--worktree", required=True)
    wstart.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    wstart.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    wstart.add_argument("--lease-hours", type=int, default=24)
    wpause = ws.add_parser("pause")
    wpause.add_argument("wave")
    wpause.add_argument(
        "--category",
        choices=[
            "infeasible",
            "external-dependency",
            "hardware-unavailable",
            "human-decision",
            "approved-design-gate",
        ],
        required=True,
    )
    wpause.add_argument("--agent", required=True)
    wpause.add_argument("--reason", required=True)
    wrenew = ws.add_parser("renew")
    wrenew.add_argument("wave")
    wrenew.add_argument("--agent", required=True)
    wrenew.add_argument("--lease-hours", type=int, default=24)
    wresume = ws.add_parser("resume")
    wresume.add_argument("wave")
    wresume.add_argument("--agent", required=True)
    wresume.add_argument("--branch", required=True)
    wresume.add_argument("--base-sha", required=True)
    wresume.add_argument("--worktree", required=True)
    wresume.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    wresume.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    wresume.add_argument("--lease-hours", type=int, default=24)
    checkpoint = ws.add_parser("checkpoint")
    checkpoint.add_argument("wave")
    checkpoint.add_argument("--agent", required=True)
    checkpoint.add_argument(
        "--kind", choices=["interface", "risk-cluster", "mid-wave", "migration", "security"], required=True
    )
    checkpoint.add_argument("--evidence", action="append", required=True)
    checkpoint.add_argument("--note", default="")
    wsubmit = ws.add_parser("submit")
    wsubmit.add_argument("wave")
    wsubmit.add_argument("--agent", required=True)
    wsubmit.add_argument("--evidence", action="append", required=True)
    wsubmit.add_argument("--note", default="")
    wreview = ws.add_parser("review")
    wreview.add_argument("wave")
    wreview.add_argument("--reviewer", required=True)
    wreview.add_argument("--result", choices=["approved", "changes-requested", "blocked"], required=True)
    wreview.add_argument("--note", default="")
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
    submit.add_argument("--from", dest="from_file")
    submit.add_argument("--note", default="")
    rev = sub.add_parser("review")
    rev.add_argument("task")
    rev.add_argument("--reviewer", required=True)
    rev.add_argument("--result", choices=["approved", "changes-requested", "blocked"], required=True)
    rev.add_argument("--from", dest="from_file")
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
    args.source_amendment_identity = amendment_identity_snapshot(data)
    args.source_approved_waves = approved_wave_snapshot(data)
    args.source_amendment_history = amendment_history_snapshot(data)
    args.source_task_review_history = task_review_history_snapshot(data)
    args.source_wave_checkpoint_history = wave_checkpoint_history_snapshot(data)
    args.repo_root = discover_repository(args.file)
    if args.command == "validate":
        command_validate(args, data, capabilities, slices, tasks, gates)
    elif args.command == "status":
        command_status(args, data, capabilities, slices, tasks, gates)
    elif args.command == "review-telemetry":
        command_review_telemetry(args, data, capabilities, slices, tasks, gates)
    elif args.command == "next":
        command_next(args, data, capabilities, slices, tasks, gates)
    elif args.command == "next-capability":
        command_next_capability(args, data, capabilities, slices, tasks, gates)
    elif args.command == "show":
        task = dict(get(tasks, args.task, "task"))
        if amendment_for_task(data, task) is None:
            task["displayCapability"] = capability_display(capabilities[task["capability_id"]])
            task["displaySlice"] = slice_display(slices[task["slice_id"]])
        print_yaml(task)
    elif args.command == "amendment" and args.amendment_command == "status":
        command_amendment_status(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "bootstrap-submit":
        command_amendment_bootstrap_submit(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "bootstrap-review":
        command_amendment_bootstrap_review(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "bootstrap-resubmit":
        command_amendment_bootstrap_resubmit(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "materialize":
        command_amendment_materialize(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "activate":
        command_amendment_activate(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "pause":
        command_amendment_pause(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "submit":
        command_amendment_submit(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "review":
        command_amendment_review(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "adopt":
        command_amendment_adopt(args, data, capabilities, slices, tasks, gates)
    elif args.command == "amendment" and args.amendment_command == "dispose":
        command_amendment_dispose(args, data, capabilities, slices, tasks, gates)
    elif args.command == "wave" and args.wave_command == "status":
        command_wave_status(args, data, capabilities, slices, tasks, gates)
    elif args.command == "wave" and args.wave_command == "start":
        command_wave_start(args, data, capabilities, slices, tasks, gates)
    elif args.command == "wave" and args.wave_command == "pause":
        command_wave_pause(args, data, capabilities, slices, tasks, gates)
    elif args.command == "wave" and args.wave_command == "renew":
        command_wave_renew(args, data, capabilities, slices, tasks, gates)
    elif args.command == "wave" and args.wave_command == "resume":
        command_wave_resume(args, data, capabilities, slices, tasks, gates)
    elif args.command == "wave" and args.wave_command == "checkpoint":
        command_wave_checkpoint(args, data, capabilities, slices, tasks, gates)
    elif args.command == "wave" and args.wave_command == "submit":
        command_wave_submit(args, data, capabilities, slices, tasks, gates)
    elif args.command == "wave" and args.wave_command == "review":
        command_wave_review(args, data, capabilities, slices, tasks, gates)
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
