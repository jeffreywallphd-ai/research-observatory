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
from functools import lru_cache
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from governance_kernel import KernelValidationError, project_paused_corrections
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=(TypeError, ValueError))
def valid_json_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None


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
CONTROL_TOOL_REVISION = 12
GCR_ADOPTION_REVISION = 7
RECOVERY_BASE_REVISION = 6
GCR_ADOPTION_TRANSACTION_PATHS = (
    "planning/governance-control-recovery/GCR-0001.B00.adoption-transaction.json",
    "planning/governance-control-recovery/GCR-0001.B00.adoption-backlog.next",
    "planning/governance-control-recovery/GCR-0001.B00.adoption-state.next",
    "planning/governance-control-recovery/GCR-0002.B00.adoption.lock",
    "planning/governance-control-recovery/GCR-0002.B00.adoption-transaction.json",
    "planning/governance-control-recovery/GCR-0002.B00.adoption-backlog.next",
    "planning/governance-control-recovery/GCR-0002.B00.adoption-state.next",
    "planning/governance-control-recovery/GCR-0003.B00.adoption.lock",
    "planning/governance-control-recovery/GCR-0003.B00.adoption-transaction.json",
    "planning/governance-control-recovery/GCR-0003.B00.adoption-backlog.next",
    "planning/governance-control-recovery/GCR-0003.B00.adoption-state.next",
    "planning/governance-control-recovery/GCR-0007.B00.adoption.lock",
    "planning/governance-control-recovery/GCR-0007.B00.adoption-transaction.json",
    "planning/governance-control-recovery/GCR-0007.B00.adoption-backlog.next",
    "planning/governance-control-recovery/GCR-0007.B00.adoption-state.next",
)
AMENDMENT_TERMINAL_STATES = {"ADOPTED", "DEFERRED", "WITHDRAWN", "SUPERSEDED"}
EXACT_T03_RECOVERY = {
    "task_id": "CAP-02.S04.T03",
    "wave_id": "W1",
    "amendment_id": "W1.A03",
    "hold_id": "HOLD-W1-GRR-0001",
    "branch": "codex/w1-windows-local-runtime",
    "manifest_path": "artifacts/evidence/task-recovery/CAP-02.S04.T03.json",
    "manifest_schema": "planning/enabler-change-requests/task-recovery-manifest.schema.json",
    "base": "bfb8797398707bece9e0662c0d995fabaced9979",
    "foundation": "461faf2870786609dea5a8e5214df380843329bb",
    "candidate": "59079efccc122a7d56a9f18efc20030851bf32a9",
    "block_record": "1c1d9ba427a55024687a62ca0c364acaccdbb7e2",
    "pause_record": "c7d543136fcd75c8f93dc8e669e59d54de433c02",
}
EXACT_T03_RESUME_COMMIT_PATHS = {
    "docs/planning-implementation-plan.md": "M",
    "planning/backlog.yaml": "M",
    "planning/review-site/manifest.json": "M",
    "planning/review-site/waves/W1.html": "M",
    "planning/status-summary.md": "M",
}
HISTORICAL_W1_A04_WITNESS = {
    "path": "artifacts/evidence/W1.A04.B00.json",
    "sha256": "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c",
    "task_id": "W1.A04.B00",
    "commit": "214ac1aac53b4396ee29f7a935ddcac2a34618b6",
}
BOOTSTRAP_SCOPE_ADDENDUM_SCHEMA_PATH = "planning/wave-amendment-approvals/bootstrap-scope-addendum.schema.json"
BOOTSTRAP_SCOPE_CONTROL_CUTOVER = "e886dd196e767b52ec253ce5286a0064d5a59c2f"
BOOTSTRAP_ADDENDUM_BLOB_CONTROL_CUTOVER = "3e1119e1ef913432fa473e95e6d86283e4ed3658"
TASK_RECOVERY_CONTRACT_FIELDS = (
    "id",
    "capability_id",
    "slice_id",
    "title",
    "objective",
    "deliverables",
    "acceptance_criteria",
    "dependencies",
    "priority",
    "wave",
    "deployment_profiles",
    "platform_targets",
    "estimate",
    "risk",
    "review_gate",
    "experience_change",
    "verification_profiles",
    "verification_commands",
)
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
        snapshot[f"{amendment_id}:correction"] = (
            json.dumps(amendment.get("correction"), sort_keys=True, separators=(",", ":")),
        )
    return snapshot


def wave_checkpoint_history_snapshot(data: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    return {
        str(wave["id"]): tuple(
            json.dumps(checkpoint, sort_keys=True, separators=(",", ":")) for checkpoint in wave.get("checkpoints", [])
        )
        for wave in data.get("waves", [])
    }


def wave_resume_history_snapshot(data: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Freeze durable Wave resume records while permitting one authorized append."""
    return {
        str(wave["id"]): tuple(
            json.dumps(record, sort_keys=True, separators=(",", ":"))
            for record in (wave.get("campaign") or {}).get("resume_records", [])
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


def recovery_history_snapshot(data: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Freeze immutable recovery-review attempts without freezing live projections."""
    snapshot: dict[str, tuple[str, ...]] = {}
    for hold in (data.get("control_plane") or {}).get("recovery_holds", []):
        hold_id = str(hold["id"])
        snapshot[hold_id] = tuple(
            json.dumps(attempt, sort_keys=True, separators=(",", ":"))
            for attempt in (hold.get("bootstrap") or {}).get("attempts", [])
        )
        for supplement in hold.get("supplements", []):
            snapshot[f"{hold_id}/{supplement.get('id')}"] = tuple(
                json.dumps(attempt, sort_keys=True, separators=(",", ":"))
                for attempt in (supplement.get("bootstrap") or {}).get("attempts", [])
            )
    return snapshot


def released_recovery_hold_snapshot(data: dict[str, Any]) -> dict[str, str]:
    """Freeze every terminal recovery hold as one immutable record."""
    return {
        str(hold["id"]): json.dumps(hold, sort_keys=True, separators=(",", ":"))
        for hold in (data.get("control_plane") or {}).get("recovery_holds", [])
        if hold.get("status") == "RELEASED"
    }


def task_recovery_history_snapshot(data: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Freeze the one-time exact-candidate recovery projection on ordinary tasks."""
    snapshot: dict[str, tuple[str, ...]] = {}
    for capability in data.get("capabilities", []):
        for slice_ in capability.get("slices", []):
            for task in slice_.get("tasks", []):
                recovery = task.get("recovery_control")
                snapshot[str(task["id"])] = (
                    (json.dumps(recovery, sort_keys=True, separators=(",", ":")),) if recovery is not None else ()
                )
    return snapshot


def exact_record_snapshot(
    data: dict[str, Any],
    collection: str,
    *,
    identities: set[str] | None = None,
    identity_field: str = "id",
) -> dict[str, str]:
    """Canonical full-record snapshot for authority that must not change."""
    document = serializable_backlog(data)
    snapshot: dict[str, str] = {}
    for item in document.get(collection, []):
        identity = str(item.get(identity_field) or "")
        if identities is None or identity in identities:
            snapshot[identity] = json.dumps(item, sort_keys=True, separators=(",", ":"))
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
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
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
    expected_wave_resume_history: dict[str, tuple[str, ...]] | None = None,
    authorized_wave_resume_append: str | None = None,
    expected_recovery_history: dict[str, tuple[str, ...]] | None = None,
    expected_released_recovery_holds: dict[str, str] | None = None,
    expected_task_recovery_history: dict[str, tuple[str, ...]] | None = None,
    expected_frozen_waves: dict[str, str] | None = None,
    expected_frozen_wave_bases: dict[str, str] | None = None,
    expected_frozen_amendments: dict[str, str] | None = None,
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
    if expected_wave_resume_history is not None:
        current_history = wave_resume_history_snapshot(document)
        for wave_id, prior in expected_wave_resume_history.items():
            current = current_history.get(wave_id)
            if current is None or current[: len(prior)] != prior:
                raise SystemExit(f"Append-only Wave resume history changed for {wave_id}")
            appended = len(current) - len(prior)
            if appended and (wave_id != authorized_wave_resume_append or appended != 1):
                raise SystemExit(f"Unauthorized Wave resume history append for {wave_id}")
        if authorized_wave_resume_append is not None and (
            authorized_wave_resume_append not in expected_wave_resume_history
            or len(current_history.get(authorized_wave_resume_append, ()))
            != len(expected_wave_resume_history[authorized_wave_resume_append]) + 1
        ):
            raise SystemExit(f"Authorized Wave resume record was not appended for {authorized_wave_resume_append}")
    if expected_recovery_history is not None:
        current_history = recovery_history_snapshot(document)
        for hold_id, prior in expected_recovery_history.items():
            current = current_history.get(hold_id)
            if current is None or current[: len(prior)] != prior:
                raise SystemExit(f"Append-only governance recovery history changed for {hold_id}")
    if expected_released_recovery_holds is not None:
        current_holds = {
            str(hold.get("id")): json.dumps(hold, sort_keys=True, separators=(",", ":"))
            for hold in (document.get("control_plane") or {}).get("recovery_holds", [])
        }
        for hold_id, frozen in expected_released_recovery_holds.items():
            if current_holds.get(hold_id) != frozen:
                raise SystemExit(f"Terminal governance recovery hold changed for {hold_id}")
    if expected_task_recovery_history is not None:
        current_history = task_recovery_history_snapshot(document)
        for task_id, prior in expected_task_recovery_history.items():
            current = current_history.get(task_id)
            if current is None or current[: len(prior)] != prior:
                raise SystemExit(f"Append-only task recovery history changed for {task_id}")
    for collection, identity_field, expected_records, label in (
        ("waves", "id", expected_frozen_waves, "Wave"),
        ("wave_approval_bases", "wave_id", expected_frozen_wave_bases, "Wave approval base"),
        ("wave_amendments", "id", expected_frozen_amendments, "Wave amendment"),
    ):
        if expected_records is None:
            continue
        current_records = exact_record_snapshot(
            document,
            collection,
            identities=set(expected_records),
            identity_field=identity_field,
        )
        for identity, frozen_record in expected_records.items():
            if current_records.get(identity) != frozen_record:
                raise SystemExit(f"Frozen {label} record changed for {identity}")
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
        expected_wave_resume_history=getattr(args, "source_wave_resume_history", None),
        authorized_wave_resume_append=getattr(args, "authorized_wave_resume_append", None),
        expected_recovery_history=getattr(args, "source_recovery_history", None),
        expected_released_recovery_holds=getattr(args, "source_released_recovery_holds", None),
        expected_task_recovery_history=getattr(args, "source_task_recovery_history", None),
        repo=getattr(args, "repo_root", None),
    )


def wave_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {wave["id"]: wave for wave in data.get("waves", [])}


def wave_approval_base_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["wave_id"]): item for item in data.get("wave_approval_bases", [])}


def wave_amendment_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in data.get("wave_amendments", [])}


def active_recovery_holds(data: dict[str, Any]) -> list[dict[str, Any]]:
    control = data.get("control_plane") or {}
    return [hold for hold in control.get("recovery_holds", []) if hold.get("status") == "ACTIVE"]


def active_amendment_campaigns(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        amendment
        for amendment in data.get("wave_amendments", [])
        if (amendment.get("campaign") or {}).get("status") == "ACTIVE"
    ]


def blocking_wave_amendments(data: dict[str, Any], wave_id: str) -> list[dict[str, Any]]:
    relations = correction_roles(data)
    frozen = {relation["parentId"] for relation in relations if relation["parentFrozen"]}
    return [
        amendment
        for amendment in data.get("wave_amendments", [])
        if amendment.get("target_wave") == wave_id
        and amendment.get("kind") != "migrated-replanning"
        and (amendment.get("lifecycle") or {}).get("status") not in AMENDMENT_TERMINAL_STATES
        and amendment.get("id") not in frozen
    ]


def correction_roles(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Use only serialized authority, never index_backlog's task annotations."""
    try:
        return [
            dict(relation)
            for relation in project_paused_corrections(serializable_backlog(data).get("wave_amendments", []))
        ]
    except KernelValidationError as exc:
        raise SystemExit(f"Invalid paused amendment correction: {exc}") from exc


def is_unexecuted_superseded_reservation(amendment: dict[str, Any]) -> bool:
    """Recognize a terminal reservation that never acquired execution authority."""
    lifecycle = amendment.get("lifecycle") or {}
    history = lifecycle.get("history") or []
    completion = amendment.get("completion") or {}
    migration_actor = str(history[-1].get("actor") or "") if history else ""
    return (
        lifecycle.get("status") == "SUPERSEDED"
        and [event.get("status") for event in history] == ["APPROVED", "SUPERSEDED"]
        and re.fullmatch(r"governance-migration:GOV-MIG-[0-9]{4}", migration_actor) is not None
        and amendment.get("bootstrap") is None
        and amendment.get("campaign") is None
        and amendment.get("tasks") == []
        and completion.get("status") == "PENDING"
        and completion.get("reviewer") is None
        and completion.get("reviewed_at") is None
        and completion.get("evidence") == []
        and completion.get("exit_review_control") is None
    )


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
            in {"DEFERRED", "WITHDRAWN", "SUPERSEDED"}
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

    active_holds = active_recovery_holds(data)
    if active_holds:
        hold = active_holds[0]
        return {
            "state": "RECOVERY_INTERRUPTED",
            "current_wave": hold.get("target_wave"),
            "blocked_wave": hold.get("target_wave"),
            "next_gate": gate_after_wave(data, str(hold.get("target_wave"))),
            "recovery_hold": hold,
            "incomplete_tasks": sorted(
                task["id"]
                for task in tasks.values()
                if task_wave(task) == hold.get("target_wave") and task.get("status") != "DONE"
            ),
            "incomplete_slices": sorted(
                slice_["id"]
                for slice_ in slices.values()
                if slice_.get("wave") == hold.get("target_wave")
                and slice_.get("completion", {}).get("status") != "APPROVED"
            ),
            "wave_completion": (wave_map(data).get(str(hold.get("target_wave")), {}).get("completion") or {}).get(
                "status"
            ),
        }

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


def transitive_task_dependents(
    task_id: str,
    tasks: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    dependents: list[dict[str, Any]] = []
    seen = {task_id}
    frontier = {task_id}
    while frontier:
        next_frontier: set[str] = set()
        for candidate_id in sorted(tasks):
            if candidate_id in seen:
                continue
            candidate = tasks[candidate_id]
            parent_slice = slices.get(str(candidate.get("slice_id"))) or {}
            dependency_ids = {
                *(str(dependency) for dependency in candidate.get("dependencies", [])),
                *(str(dependency) for dependency in parent_slice.get("depends_on", [])),
            }
            if frontier.intersection(dependency_ids):
                seen.add(candidate_id)
                next_frontier.add(candidate_id)
                dependents.append(candidate)
        frontier = next_frontier
    return dependents


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
    frozen_parents = {relation["parentId"] for relation in correction_roles(data) if relation["parentFrozen"]}
    for task in tasks.values():
        if task.get("_amendment_id") in frozen_parents:
            continue
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


def git_commit_parents(repo: Path, commit: str) -> list[str]:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%P", commit],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip().split() if result.returncode == 0 else []


def git_name_status_delta(repo: Path, parent: str, commit: str) -> dict[str, str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", "--no-renames", "-z", parent, commit],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        fields = result.stdout.decode("utf-8", errors="strict").split("\0")
    except UnicodeError:
        return {}
    fields = fields[:-1] if fields and fields[-1] == "" else fields
    if len(fields) % 2:
        return {}
    return {fields[offset + 1]: fields[offset] for offset in range(0, len(fields), 2)}


def git_commits_changing_path_after(repo: Path, ancestor: str, path: str) -> list[str]:
    result = subprocess.run(
        ["git", "rev-list", "--reverse", "--ancestry-path", f"{ancestor}..HEAD", "--", path],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip().splitlines() if result.returncode == 0 else []


@lru_cache(maxsize=512)
def git_blob(repo: Path, commit: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=repo, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


def governance_control_adoption_finalization_errors(
    repo: Path,
    evidence_commit: str,
    state_payload: bytes,
    expected_generation: dict[str, Any],
) -> list[str]:
    """Derive and validate the unique exact GCR adoption-finalization commit."""
    if not git_commit_exists(repo, evidence_commit) or not git_is_ancestor(repo, evidence_commit):
        return ["GCR-0001 adoption evidence commit is absent from current history"]
    state_path = "planning/governance-control-recovery/GCR-0001.B00.state.json"
    backlog_path = "planning/backlog.yaml"
    matches = [
        commit
        for commit in git_commits_changing_path_after(repo, evidence_commit, state_path)
        if git_blob(repo, commit, state_path) == state_payload
    ]
    if not matches:
        return ["GCR-0001 adoption is pending its exact finalization commit"]
    if len(matches) != 1:
        return ["GCR-0001 adoption finalization commit is not unique"]
    finalization_commit = matches[0]
    if git_commit_parents(repo, finalization_commit) != [evidence_commit]:
        return ["GCR-0001 adoption finalization is not the direct child of its evidence commit"]
    expected_delta = {backlog_path: "M", state_path: "M"}
    if git_name_status_delta(repo, evidence_commit, finalization_commit) != expected_delta:
        return ["GCR-0001 adoption finalization commit is not the exact two-path transition"]
    finalization_backlog = git_blob(repo, finalization_commit, backlog_path)
    try:
        finalization_document = yaml.safe_load((finalization_backlog or b"").decode("utf-8"))
    except UnicodeError, yaml.YAMLError:
        return ["GCR-0001 adoption finalization backlog blob is malformed"]
    if not isinstance(finalization_document, dict):
        return ["GCR-0001 adoption finalization backlog blob is malformed"]
    finalization_control = finalization_document.get("control_plane") or {}
    if (
        finalization_control.get("revision") != GCR_ADOPTION_REVISION
        or finalization_control.get("minimum_tool_revision") != GCR_ADOPTION_REVISION
        or finalization_control.get("control_generations") != [expected_generation]
    ):
        return ["GCR-0001 adoption finalization does not freeze the exact revision-7 generation"]
    return []


def safe_control_path(
    repo: Path,
    relative: str,
    *,
    prefix: str,
    label: str,
    require_exists: bool = True,
) -> Path:
    if not relative or "\\" in relative or ":" in relative or re.search(r"(?:^|/)\.{1,2}(?:/|$)", relative):
        raise ValueError(f"{label} is not a canonical repository-relative POSIX path")
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or relative != pure.as_posix()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or (relative != prefix and not relative.startswith(prefix.rstrip("/") + "/"))
    ):
        raise ValueError(f"{label} is outside {prefix} or is not canonically spelled")
    current = repo
    junction = getattr(os.path, "isjunction", lambda _path: False)
    for part in pure.parts:
        current = current / part
        if (current.exists() or current.is_symlink()) and (current.is_symlink() or junction(current)):
            raise ValueError(f"{label} traverses a symlink or junction")
    candidate = repo.joinpath(*pure.parts)
    try:
        candidate.resolve(strict=False).relative_to(repo.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} resolves outside the repository") from exc
    if require_exists and not candidate.is_file():
        raise ValueError(f"{label} is not an existing regular file")
    return candidate


def canonical_control_artifact_path(
    repo: Path,
    value: str,
    *,
    prefix: str,
    label: str,
    require_exists: bool = True,
) -> tuple[str, Path]:
    """Validate the raw CLI/reference spelling before any path normalization."""
    try:
        path = safe_control_path(
            repo,
            value,
            prefix=prefix,
            label=label,
            require_exists=require_exists,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return value, path


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
    try:
        path = safe_control_path(
            repo,
            relative,
            prefix="planning/wave-amendment-approvals",
            label="Amendment approval",
        )
        payload = path.read_bytes()
        record = json.loads(payload)
        schema = load_json_schema(repo / "planning/wave-amendment-approvals/wave-amendment-approval.schema.json")
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(record)
    except (OSError, ValueError, json.JSONDecodeError, SchemaError, ValidationError) as exc:
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
    try:
        path = safe_control_path(
            repo,
            relative,
            prefix="planning/wave-amendment-approvals",
            label="Bootstrap scope addendum",
        )
        payload = path.read_bytes()
        record = json.loads(payload)
        schema = load_json_schema(repo / "planning/wave-amendment-approvals/bootstrap-scope-addendum.schema.json")
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(record)
    except (OSError, ValueError, json.JSONDecodeError, SchemaError, ValidationError) as exc:
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
    scope_addenda = bootstrap.get("scope_addenda", [])
    if scope_addenda:
        patterns.append(BOOTSTRAP_SCOPE_ADDENDUM_SCHEMA_PATH)
    for reference in scope_addenda:
        relative = str(reference.get("path") or "")
        if relative:
            patterns.append(relative)
        path = repo.joinpath(*PurePosixPath(relative).parts)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            continue
        patterns.extend(str(item) for item in record.get("authorizedAdditionalPaths", []))
    return patterns


def bootstrap_candidate_authorization(
    repo: Path,
    packet: dict[str, Any],
    references: list[dict[str, str]],
    candidate: str,
    bootstrap_id: str,
) -> tuple[list[str], list[str]]:
    """Bind addendum path authority to the latest applicable introduction blob."""
    errors: list[str] = []
    applicable: list[dict[str, str]] = []
    prior_introduction: str | None = None
    for reference in references:
        introduction = str(reference.get("introduction_commit") or "")
        if (
            prior_introduction
            and introduction != prior_introduction
            and not git_is_ancestor(repo, prior_introduction, introduction)
        ):
            errors.append(f"{bootstrap_id}: bootstrap scope addenda are not in one ordered history")
        prior_introduction = introduction
        if introduction == candidate or git_is_ancestor(repo, introduction, candidate):
            applicable.append(reference)

    latest_authority: dict[str, str] = {}
    for reference in applicable:
        relative = str(reference.get("path") or "")
        path = repo.joinpath(*PurePosixPath(relative).parts)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{bootstrap_id}: cannot read authenticated bootstrap scope addendum: {exc}")
            continue
        introduction = str(reference.get("introduction_commit") or "")
        for authorized_path in record.get("authorizedAdditionalPaths", []):
            latest_authority[str(authorized_path)] = introduction

    for authorized_path, introduction in latest_authority.items():
        binding_required = git_commit_exists(repo, BOOTSTRAP_ADDENDUM_BLOB_CONTROL_CUTOVER) and (
            introduction == BOOTSTRAP_ADDENDUM_BLOB_CONTROL_CUTOVER
            or git_is_ancestor(repo, BOOTSTRAP_ADDENDUM_BLOB_CONTROL_CUTOVER, introduction)
        )
        if not binding_required:
            continue
        if git_blob(repo, candidate, authorized_path) != git_blob(repo, introduction, authorized_path):
            errors.append(
                f"{bootstrap_id}: addendum-authorized path changed after its latest authority boundary: "
                f"{authorized_path}"
            )
    patterns = bootstrap_authorized_patterns(
        repo,
        packet,
        {"scope_addenda": applicable},
    )
    return patterns, errors


def bootstrap_resubmission_scope_addenda(
    repo: Path,
    amendment_id: str,
    bootstrap_id: str,
    bootstrap: dict[str, Any],
    previous_candidate: str,
    implementation_commit: str,
) -> tuple[list[str], list[dict[str, str]]]:
    """Authenticate and append newly introduced scope addenda for a remediation."""
    additional_paths, discovered = load_bootstrap_scope_addenda(repo, amendment_id, bootstrap_id)
    frozen = list(bootstrap.get("scope_addenda") or [])
    discovered_by_path = {str(item.get("path") or ""): item for item in discovered}
    frozen_paths: set[str] = set()
    for reference in frozen:
        relative = str(reference.get("path") or "")
        if not relative or relative in frozen_paths:
            raise SystemExit(f"{bootstrap_id}: frozen bootstrap scope-addendum references are invalid")
        frozen_paths.add(relative)
        if discovered_by_path.get(relative) != reference:
            raise SystemExit(f"{bootstrap_id}: frozen bootstrap scope addendum is missing or differs")

    appended: list[dict[str, str]] = []
    for reference in discovered:
        relative = str(reference.get("path") or "")
        if relative in frozen_paths:
            continue
        record_path = repo.joinpath(*PurePosixPath(relative).parts)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        decision_candidate = str(record.get("candidateAtDecision") or "")
        if decision_candidate != previous_candidate and not git_is_ancestor(
            repo, previous_candidate, decision_candidate
        ):
            raise SystemExit(f"{bootstrap_id}: new scope addendum does not descend from the prior candidate")
        if decision_candidate != implementation_commit and not git_is_ancestor(
            repo, decision_candidate, implementation_commit
        ):
            raise SystemExit(f"{bootstrap_id}: new scope addendum is outside the remediation lineage")
        appended.append(reference)
    return additional_paths, [*frozen, *appended]


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
    try:
        evidence_path = safe_control_path(
            repo,
            relative,
            prefix="artifacts/evidence",
            label="Bootstrap evidence",
        )
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
    frozen_scope_base = attempt.get("scope_base_commit")
    scope_base = evidence_base
    scope_required = (
        expected_base is None
        and git_commit_exists(repo, BOOTSTRAP_SCOPE_CONTROL_CUTOVER)
        and git_is_ancestor(repo, BOOTSTRAP_SCOPE_CONTROL_CUTOVER, candidate)
    )
    if frozen_scope_base is None:
        if scope_required:
            errors.append(
                f"{bootstrap_id}: current bootstrap remediation lacks its frozen prior-candidate authority scope"
            )
    else:
        if not isinstance(frozen_scope_base, str) or frozen_scope_base != lineage_base:
            errors.append(f"{bootstrap_id}: bootstrap authority scope does not start at its prior candidate")
        else:
            scope_base = frozen_scope_base
    scope = subprocess.run(
        ["git", "diff", "--name-only", scope_base, candidate, "--"],
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
    errors: list[str] = []
    expected_correction = (packet.get("authorityChain") or {}).get("pausedPredecessor")
    if amendment.get("correction") != expected_correction:
        errors.append(f"{amendment.get('id')}: correction relation differs from its immutable approved packet")
    if expected_correction is not None:
        from planctl import _paused_predecessor_errors

        errors.extend(_paused_predecessor_errors(repo, expected_correction, str(amendment.get("id"))))
        if not git_is_ancestor(
            repo,
            str(expected_correction.get("effectiveStateCommit") or ""),
            str((approval.get("packet") or {}).get("commit") or ""),
        ):
            errors.append(f"{amendment.get('id')}: correction packet does not descend from its paused predecessor")
    bootstrap = amendment.get("bootstrap") or {}
    if not bootstrap:
        return errors
    amendment_id = str(amendment.get("id"))
    bootstrap_id = str(bootstrap.get("id") or "")
    packet_unit = packet.get("bootstrapUnit") or {}
    if approval.get("status") != "APPROVED" or approval.get("amendmentId") != amendment_id:
        errors.append(f"{amendment_id}: bootstrap does not descend from an approved amendment record")
    if bootstrap_id != packet_unit.get("id"):
        errors.append(f"{amendment_id}: bootstrap identity differs from the approved packet")
    attempts = bootstrap.get("attempts") or []
    expected_attempt_ids = [f"R{index:02d}" for index in range(1, len(attempts) + 1)]
    if [str(item.get("id")) for item in attempts] != expected_attempt_ids:
        errors.append(f"{bootstrap_id}: bootstrap attempt IDs are not sequential")
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
        allowed_patterns, authorization_errors = bootstrap_candidate_authorization(
            repo,
            packet,
            list(bootstrap.get("scope_addenda") or []),
            candidate,
            bootstrap_id,
        )
        errors.extend(authorization_errors)
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


def recovery_review_history_errors(
    repo: Path,
    hold: dict[str, Any],
    packet: dict[str, Any],
    *,
    supplement: dict[str, Any] | None = None,
) -> list[str]:
    """Validate immutable recovery ledgers and their sequential finding state."""
    errors: list[str] = []
    request_id = str(hold.get("recovery_request_id") or "")
    supplement_id = str((supplement or {}).get("id") or "")
    bootstrap = (supplement or {}).get("bootstrap") or hold.get("bootstrap") or {}
    bootstrap_id = str(bootstrap.get("id") or "")
    attempts = bootstrap.get("attempts") or []
    prior_open: set[str] = set()
    blocking_ids: set[str] = set()
    seen_finding_ids: set[str] = set()
    criterion_count = len(packet.get("acceptanceCriteria") or [])
    for attempt_index, attempt in enumerate(attempts):
        attempt_id = str(attempt.get("id") or "")
        candidate = str(attempt.get("implementation_commit") or "")
        evidence = attempt.get("evidence") or {}
        reference = attempt.get("ledger") or {}
        expected_path = f"planning/governance-recovery-approvals/{bootstrap_id}.review-{attempt_id}.json"
        if reference.get("path") != expected_path:
            errors.append(f"{bootstrap_id}/{attempt_id}: review ledger path is not canonical")
            continue
        try:
            path = safe_control_path(
                repo,
                expected_path,
                prefix="planning/governance-recovery-approvals",
                label=f"{bootstrap_id}/{attempt_id} review ledger",
            )
            payload = path.read_bytes()
            ledger = json.loads(payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{bootstrap_id}/{attempt_id}: cannot load review ledger: {exc}")
            continue
        if not isinstance(ledger, dict):
            errors.append(f"{bootstrap_id}/{attempt_id}: review ledger root is not an object")
            continue
        if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
            errors.append(f"{bootstrap_id}/{attempt_id}: review ledger hash mismatch")
        review = attempt.get("review") or {}
        reviewer = str(ledger.get("reviewer") or "").strip()
        result = str(ledger.get("result") or "")
        expected_fields = {
            "schemaVersion": "1.0",
            "documentType": (
                "governance-recovery-supplement-bootstrap-review"
                if supplement is not None
                else "governance-recovery-bootstrap-review"
            ),
            "recoveryRequestId": request_id,
            "bootstrapUnit": bootstrap_id,
            "attemptId": attempt_id,
            "candidateCommit": candidate,
            "reviewer": reviewer,
            "result": result,
            "evidence": {"path": evidence.get("path"), "sha256": evidence.get("sha256")},
        }
        if supplement is not None:
            expected_fields["supplementId"] = supplement_id
        if any(ledger.get(field) != expected for field, expected in expected_fields.items()):
            errors.append(f"{bootstrap_id}/{attempt_id}: review ledger differs from the frozen attempt")
        reviewed_state = str(ledger.get("reviewedStateCommit") or "")
        if not git_commit_exists(repo, reviewed_state) or not git_is_ancestor(repo, reviewed_state):
            errors.append(f"{bootstrap_id}/{attempt_id}: reviewed state is absent from current history")
        elif reviewed_state == candidate or not git_is_ancestor(repo, candidate, reviewed_state):
            errors.append(f"{bootstrap_id}/{attempt_id}: reviewed state does not descend from its candidate")
        else:
            historical = historical_backlog_document(repo, reviewed_state)
            historical_hold = next(
                (
                    item
                    for item in ((historical or {}).get("control_plane") or {}).get("recovery_holds", [])
                    if item.get("recovery_request_id") == request_id
                ),
                None,
            )
            historical_supplement = None
            if supplement is not None:
                historical_supplement = next(
                    (
                        item
                        for item in (historical_hold or {}).get("supplements", [])
                        if item.get("id") == supplement_id
                    ),
                    None,
                )
            historical_bootstrap = (
                (historical_supplement or {}).get("bootstrap")
                if supplement is not None
                else (historical_hold or {}).get("bootstrap")
            ) or {}
            expected_submission = {
                "attempt_id": attempt_id,
                "candidate_commit": candidate,
                "evidence_sha256": evidence.get("sha256"),
                "acceptance_criteria_sha256": canonical_json_sha256(packet.get("acceptanceCriteria", [])),
            }
            if (
                (historical_hold or {}).get("id") != hold.get("id")
                or (supplement is not None and historical_supplement is None)
                or (
                    supplement is not None
                    and any(
                        (historical_supplement or {}).get(field) != supplement.get(field)
                        for field in (
                            "id",
                            "predecessor_control_revision",
                            "packet_reference",
                            "approval_reference",
                            "created_at",
                        )
                    )
                )
                or historical_bootstrap.get("id") != bootstrap_id
                or historical_bootstrap.get("status") != "REVIEW"
                or historical_bootstrap.get("current_submission") != expected_submission
                or historical_bootstrap.get("implementation_commit") != candidate
                or historical_bootstrap.get("submission_branch") != attempt.get("submission_branch")
                or historical_bootstrap.get("evidence") != evidence
                or historical_bootstrap.get("review")
                != {"reviewer": None, "result": None, "reviewed_at": None, "notes": None}
            ):
                errors.append(f"{bootstrap_id}/{attempt_id}: reviewed state lacks its exact frozen submission")
            if historical_bootstrap.get("attempts") != attempts[:attempt_index]:
                errors.append(f"{bootstrap_id}/{attempt_id}: reviewed state does not preserve exact prior attempts")
        if not reviewer or reviewer == attempt.get("implementer") or reviewer != review.get("reviewer"):
            errors.append(f"{bootstrap_id}/{attempt_id}: review independence or reviewer projection is invalid")
        if result not in set(BOOTSTRAP_REVIEW_RESULTS.values()) or result != review.get("result"):
            errors.append(f"{bootstrap_id}/{attempt_id}: review result projection is invalid")
        if not review.get("reviewed_at"):
            errors.append(f"{bootstrap_id}/{attempt_id}: review projection lacks its timestamp")
        findings = ledger.get("findings")
        closures = ledger.get("closures")
        if not isinstance(findings, list) or not isinstance(closures, list):
            errors.append(f"{bootstrap_id}/{attempt_id}: review findings/closures are invalid")
            continue
        ordering = [
            REVIEW_SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings if isinstance(item, dict)
        ]
        if len(ordering) != len(findings) or ordering != sorted(ordering) or any(value == 99 for value in ordering):
            errors.append(f"{bootstrap_id}/{attempt_id}: review findings are not valid and severity-ranked")
        finding_ids: set[str] = set()
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_id = str(finding.get("id") or "")
            criterion_index = finding.get("criterionIndex")
            if (
                not finding_id
                or finding_id in finding_ids
                or finding_id in seen_finding_ids
                or type(finding.get("blocking")) is not bool
                or type(criterion_index) is not int
                or not 1 <= criterion_index <= criterion_count
                or not str(finding.get("title") or "").strip()
                or not str(finding.get("reproduction") or "").strip()
                or not str(finding.get("requiredRemediation") or "").strip()
            ):
                errors.append(f"{bootstrap_id}/{attempt_id}: review finding is invalid or duplicated")
                continue
            finding_ids.add(finding_id)
            seen_finding_ids.add(finding_id)
            if finding.get("blocking") is True:
                blocking_ids.add(finding_id)
        closure_ids = [str(item.get("findingId") or "") for item in closures if isinstance(item, dict)]
        if (
            len(closure_ids) != len(closures)
            or len(closure_ids) != len(set(closure_ids))
            or not set(closure_ids).issubset(prior_open)
        ):
            errors.append(f"{bootstrap_id}/{attempt_id}: review closures are not append-only and valid")
        prior_open = (prior_open - set(closure_ids)) | finding_ids
        if result == "approved" and findings:
            errors.append(f"{bootstrap_id}/{attempt_id}: approved review introduces new findings")
        if result == "approved" and prior_open & blocking_ids:
            errors.append(f"{bootstrap_id}/{attempt_id}: approval retains open blocking findings")
    return errors


def recovery_bootstrap_projection_errors(
    label: str,
    bootstrap: dict[str, Any],
) -> list[str]:
    """Validate the mutable projection shared by base and supplemental recovery bootstraps."""
    errors: list[str] = []
    attempts = bootstrap.get("attempts") or []
    expected_attempts = [f"R{index:02d}" for index in range(1, len(attempts) + 1)]
    if [str(item.get("id")) for item in attempts] != expected_attempts:
        errors.append(f"{label}: bootstrap review attempts are not append-only and sequential")
    for attempt in attempts:
        review = attempt.get("review") or {}
        if review.get("reviewer") == attempt.get("implementer"):
            errors.append(f"{label}/{attempt.get('id')}: bootstrap review is not independent")
    status = str(bootstrap.get("status") or "")
    current = bootstrap.get("current_submission")
    if status == "REVIEW" and current is None:
        errors.append(f"{label}: REVIEW bootstrap lacks its frozen current submission")
    if status != "REVIEW" and current is not None:
        errors.append(f"{label}: non-REVIEW bootstrap retains a mutable current submission")
    if attempts and status != "REVIEW":
        latest = attempts[-1]
        latest_review = latest.get("review") or {}
        expected_status = {
            "approved": "APPROVED",
            "changes-requested": "CHANGES_REQUESTED",
            "blocked": "BLOCKED",
        }.get(str(latest_review.get("result") or ""))
        if status != expected_status:
            errors.append(f"{label}: bootstrap status differs from the latest immutable review")
        for field in ("implementation_commit", "submission_branch", "evidence", "review"):
            if bootstrap.get(field) != latest.get(field):
                errors.append(f"{label}: bootstrap {field} differs from the latest immutable attempt")
    if status in {"REVIEW", "APPROVED", "CHANGES_REQUESTED", "BLOCKED"} and (
        not bootstrap.get("implementation_commit") or not bootstrap.get("evidence")
    ):
        errors.append(f"{label}: submitted bootstrap lacks commit-bound evidence")
    return errors


def recovery_v4_supplement_packet_review_errors(
    repo: Path,
    supplement_id: str,
    approval: dict[str, Any],
    packet: dict[str, Any],
    packet_payload: bytes,
    packet_commit: str,
    approval_introduction: str,
) -> list[str]:
    """Fail closed unless the complete v4 review history is immutable and fully resolved."""

    def reject(message: str) -> None:
        raise ValueError(message)

    try:
        schema_name = (
            "governance-recovery-supplement-approval.v5.schema.json"
            if approval.get("$schema")
            == "../governance-recovery-requests/governance-recovery-supplement-approval.v5.schema.json"
            else "governance-recovery-supplement-approval.v4.schema.json"
        )
        schema = load_json_schema(repo / "planning/governance-recovery-requests" / schema_name)
        projection = approval.get("independentPacketReview") or {}
        newest_attempt = str(projection.get("attemptId") or "")
        current_attempt = newest_attempt
        reference = projection.get("ledger") or {}
        expected_result: str | None = None
        successor_candidate: str | None = None
        seen: set[tuple[str, str, str]] = set()
        newest_to_oldest: list[tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = []
        packet_relative = f"planning/governance-recovery-requests/{supplement_id}.packet.json"
        while True:
            attempt_match = re.fullmatch(r"R([0-9]{2,})", current_attempt)
            attempt_number = int(attempt_match.group(1)) if attempt_match else 0
            if attempt_number < 1 or current_attempt != f"R{attempt_number:02d}":
                reject("attempt identity is invalid")
            relative = str(reference.get("path") or "")
            expected_relative = f"planning/governance-recovery-requests/{supplement_id}.review-{current_attempt}.json"
            review_commit = str(reference.get("commit") or "")
            identity = (current_attempt, relative, review_commit)
            if relative != expected_relative or identity in seen:
                reject("history is noncanonical or cyclic")
            seen.add(identity)
            path = safe_control_path(
                repo,
                relative,
                prefix="planning/governance-recovery-requests",
                label=f"{supplement_id} v4 packet-review ledger",
            )
            ledger_payload = path.read_bytes()
            ledger = json.loads(ledger_payload)
            Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(ledger)
            if (
                hashlib.sha256(ledger_payload).hexdigest() != reference.get("sha256")
                or approval_introduction_commit(repo, relative) != review_commit
                or not git_commit_exists(repo, review_commit)
                or not git_is_ancestor(repo, review_commit)
                or git_blob(repo, review_commit, relative) != ledger_payload
            ):
                reject("ledger hash, introduction, history, or Git blob is invalid")
            candidate = str(ledger.get("candidateCommit") or "")
            round_packet_payload: bytes | None
            if current_attempt == newest_attempt:
                round_packet = packet
                round_packet_payload = packet_payload
                if candidate != packet_commit:
                    reject("latest candidate is stale")
            else:
                round_packet_payload = git_blob(repo, candidate, packet_relative)
                round_packet = json.loads(round_packet_payload or b"")
            if not isinstance(round_packet, dict):
                reject("historical packet is not an object")
            findings = ledger.get("findings") or []
            closures = ledger.get("closures") or []
            finding_ids = [str(item.get("id") or "") for item in findings]
            closure_ids = [str(item.get("findingId") or "") for item in closures]
            reviewer = str(ledger.get("reviewer") or "")
            severities = [REVIEW_SEVERITY_ORDER.get(str(item.get("severity") or ""), 99) for item in findings]
            if (
                ledger.get("documentType") != "governance-recovery-supplement-packet-review"
                or ledger.get("recoveryRequestId") != supplement_id.split(".", 1)[0]
                or ledger.get("supplementId") != supplement_id
                or ledger.get("attemptId") != current_attempt
                or (expected_result is not None and ledger.get("result") != expected_result)
                or round_packet_payload is None
                or ledger.get("packetSha256") != hashlib.sha256(round_packet_payload or b"").hexdigest()
                or review_commit == candidate
                or not git_is_ancestor(repo, candidate, review_commit)
                or (
                    successor_candidate is not None
                    and (
                        review_commit == successor_candidate
                        or not git_is_ancestor(repo, review_commit, successor_candidate)
                    )
                )
                or not reviewer
                or reviewer != reviewer.strip()
                or reviewer == approval.get("approvedBy")
                or severities != sorted(severities)
                or len(finding_ids) != len(set(finding_ids))
                or len(closure_ids) != len(set(closure_ids))
                or any(
                    not finding_id.startswith(f"{supplement_id}-{current_attempt}-F")
                    or int(finding.get("criterionIndex") or 0) > len(round_packet.get("acceptanceCriteria") or [])
                    for finding_id, finding in zip(finding_ids, findings, strict=True)
                )
            ):
                reject("identity, ordering, independence, packet binding, or ancestry is invalid")
            newest_to_oldest.append((ledger, findings, closures))
            prior = ledger.get("priorAttempt")
            if attempt_number == 1:
                if prior is not None:
                    reject("R01 names a predecessor")
                break
            if prior is None:
                reject("history is truncated before R01")
            prior_attempt = str((prior or {}).get("attemptId") or "")
            if prior_attempt != f"R{attempt_number - 1:02d}" or (prior or {}).get("result") not in {
                "changes-requested",
                "blocked",
            }:
                reject("predecessor is skipped or non-adverse")
            reference = (prior or {}).get("ledger") or {}
            expected_result = str((prior or {}).get("result") or "")
            successor_candidate = candidate
            current_attempt = prior_attempt

        open_findings: dict[str, dict[str, Any]] = {}
        all_finding_ids: set[str] = set()
        closed_finding_ids: list[str] = []
        chronological = list(reversed(newest_to_oldest))
        for index, (ledger, findings, closures) in enumerate(chronological):
            for closure in closures:
                finding_id = str(closure.get("findingId") or "")
                finding = open_findings.get(finding_id)
                if finding is None or (
                    finding.get("blocking") is True and closure.get("disposition") == "accepted-risk"
                ):
                    reject("closure is stale, duplicated, or unsafe")
                del open_findings[finding_id]
                closed_finding_ids.append(finding_id)
            for finding in findings:
                finding_id = str(finding.get("id") or "")
                if finding_id in all_finding_ids:
                    reject("finding history is duplicated")
                all_finding_ids.add(finding_id)
                open_findings[finding_id] = finding
            result = ledger.get("result")
            is_latest = index == len(chronological) - 1
            if result == "approved":
                if not is_latest or ledger.get("approvalAvailable") is not True or findings or open_findings:
                    reject("approval retains unresolved or new findings")
            elif (
                result not in {"changes-requested", "blocked"}
                or ledger.get("approvalAvailable") is not False
                or not open_findings
            ):
                reject("adverse disposition is inconsistent")
        latest = newest_to_oldest[0][0]
        latest_commit = str((projection.get("ledger") or {}).get("commit") or "")
        if (
            latest.get("result") != "approved"
            or projection.get("candidateCommit") != packet_commit
            or projection.get("result") != "APPROVED"
            or sorted(projection.get("closedFindingIds") or []) != sorted(closed_finding_ids)
            or sorted(projection.get("openFindingIds") or []) != sorted(open_findings)
            or latest_commit == approval_introduction
            or not git_is_ancestor(repo, latest_commit, approval_introduction)
        ):
            reject("approval projection is unresolved, stale, forked, or inconsistent")
    except (OSError, ValueError, json.JSONDecodeError, SchemaError, ValidationError) as exc:
        return [f"{supplement_id}: invalid v4 packet-review history: {exc}"]
    return []


def recovery_v5_installed_control_errors(
    data: dict[str, Any],
    repo: Path,
    packet: dict[str, Any],
    supplement_id: str,
) -> list[str]:
    """Authenticate the exact non-circular GCR-0007 P-to-A-to-F authority."""
    errors: list[str] = []
    authority = packet.get("installedControlRecovery") or {}
    transition = authority.get("controlTransition") or {}
    topology = authority.get("topology") or {}
    generations = (data.get("control_plane") or {}).get("control_generations") or []
    generation = generations[-1] if len(generations) == 4 else {}
    generation_approval = generation.get("approval_reference") or {}
    generation_review = generation.get("review_reference") or {}
    references = {
        "approval": authority.get("approval") or {},
        "review": authority.get("latestApprovedReview") or {},
        "state": authority.get("adoptedState") or {},
        "evidence": authority.get("adoptionEvidence") or {},
    }
    expected_paths = {
        "approval": "planning/governance-control-recovery/GCR-0007.approval.json",
        "state": "planning/governance-control-recovery/GCR-0007.B00.state.json",
    }
    approved_state = str(topology.get("approvedStateCommit") or "")
    evidence_commit = str(topology.get("adoptionEvidenceCommit") or "")
    finalization_commit = str(topology.get("finalizationCommit") or "")
    if (
        authority.get("controlRecoveryId") != "GCR-0007"
        or authority.get("bootstrapUnit") != "GCR-0007.B00"
        or transition
        != {
            "predecessorRevision": 11,
            "successorRevision": 11,
            "supportedControlCeiling": 12,
            "generationNeutral": True,
        }
        or generation.get("id") != "GCR-0007"
        or generation.get("bootstrap_id") != "GCR-0007.B00"
        or generation.get("hold_id") != "HOLD-W1-GRR-0002"
        or generation.get("predecessor_revision") != 11
        or generation.get("successor_revision") != 11
        or generation.get("supported_control_ceiling") != 12
        or generation.get("generation_neutral") is not True
        or references["approval"]
        != {
            "path": generation_approval.get("path"),
            "sha256": generation_approval.get("sha256"),
            "commit": generation_approval.get("introduction_commit"),
        }
        or references["review"]
        != {
            "path": generation_review.get("path"),
            "sha256": generation_review.get("sha256"),
            "commit": generation_review.get("approved_state_commit"),
        }
        or approved_state != generation_review.get("approved_state_commit")
        or evidence_commit != references["evidence"].get("commit")
        or finalization_commit != references["state"].get("commit")
    ):
        errors.append(f"{supplement_id}: installed GCR-0007 authority differs from the live generation")

    documents: dict[str, dict[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for label, reference in references.items():
        relative = str(reference.get("path") or "")
        if label in expected_paths and relative != expected_paths[label]:
            errors.append(f"{supplement_id}: installed GCR-0007 {label} path is not canonical")
            continue
        if (
            label == "review"
            and re.fullmatch(
                r"planning/governance-control-recovery/GCR-0007\.B00\.review-R[0-9]{2,}\.json",
                relative,
            )
            is None
        ):
            errors.append(f"{supplement_id}: installed GCR-0007 review path is not canonical")
            continue
        if (
            label == "evidence"
            and re.fullmatch(
                r"artifacts/evidence/governance-control-recovery/GCR-0007\.B00\.adoption(?:-R[0-9]{2})?\.json",
                relative,
            )
            is None
        ):
            errors.append(f"{supplement_id}: installed GCR-0007 evidence path is not canonical")
            continue
        commit = str(reference.get("commit") or "")
        try:
            path = safe_control_path(
                repo,
                relative,
                prefix=(
                    "artifacts/evidence/governance-control-recovery"
                    if label == "evidence"
                    else "planning/governance-control-recovery"
                ),
                label=f"{supplement_id} installed GCR-0007 {label}",
            )
            payload = path.read_bytes()
            document = json.loads(payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{supplement_id}: cannot load installed GCR-0007 {label}: {exc}")
            continue
        if not isinstance(document, dict):
            errors.append(f"{supplement_id}: installed GCR-0007 {label} must be an object")
            continue
        documents[label] = document
        payloads[label] = payload
        if (
            hashlib.sha256(payload).hexdigest() != reference.get("sha256")
            or not git_commit_exists(repo, commit)
            or not git_is_ancestor(repo, commit)
            or git_blob(repo, commit, relative) != payload
        ):
            errors.append(f"{supplement_id}: installed GCR-0007 {label} binding is invalid")

    approval = documents.get("approval") or {}
    review = documents.get("review") or {}
    state = documents.get("state") or {}
    evidence = documents.get("evidence") or {}
    activation = state.get("activation") or {}
    attempts = state.get("attempts") or {}
    latest_attempt_id = sorted(attempts)[-1] if isinstance(attempts, dict) and attempts else ""
    latest_attempt_value = attempts.get(latest_attempt_id) if isinstance(attempts, dict) and latest_attempt_id else {}
    latest_attempt: dict[str, Any] = latest_attempt_value if isinstance(latest_attempt_value, dict) else {}
    expected_evidence_relative = (
        "artifacts/evidence/governance-control-recovery/GCR-0007.B00.adoption.json"
        if latest_attempt_id == "R02"
        else f"artifacts/evidence/governance-control-recovery/GCR-0007.B00.adoption-{latest_attempt_id}.json"
    )
    if (
        approval.get("controlRecoveryId") != "GCR-0007"
        or approval.get("documentType") != "governance-control-recovery-successor-approval"
        or review.get("controlRecoveryId") != "GCR-0007"
        or review.get("bootstrapUnit") != "GCR-0007.B00"
        or review.get("result") != "approved"
        or review.get("findings") != []
        or state.get("controlRecoveryId") != "GCR-0007"
        or state.get("bootstrapUnit") != "GCR-0007.B00"
        or state.get("status") != "HEADROOM_ACTIVATION_FINALIZATION"
        or (latest_attempt.get("review") or {}).get("result") != "approved"
        or (latest_attempt.get("ledger") or {}).get("path") != references["review"].get("path")
        or (latest_attempt.get("ledger") or {}).get("sha256") != references["review"].get("sha256")
        or activation.get("approvedStateCommit") != approved_state
        or activation.get("adoptionEvidence") != references["evidence"]
        or references["evidence"].get("path") != expected_evidence_relative
        or activation.get("predecessorRevision") != 11
        or activation.get("successorRevision") != 11
        or activation.get("supportedControlCeiling") != 12
        or activation.get("generationNeutral") is not True
        or activation.get("ordinaryExecutionAuthority") is not False
        or evidence.get("controlRecoveryId") != "GCR-0007"
        or evidence.get("bootstrapUnit") != "GCR-0007.B00"
        or evidence.get("approvedStateCommit") != approved_state
        or evidence.get("predecessorRevision") != 11
        or evidence.get("successorRevision") != 11
        or evidence.get("supportedControlCeiling") != 12
        or evidence.get("generationNeutral") is not True
        or "adoptionEvidenceCommit" in evidence
        or "finalizationCommit" in evidence
    ):
        errors.append(f"{supplement_id}: installed GCR-0007 state/evidence authority is invalid")

    state_relative = expected_paths["state"]
    evidence_relative = str(references["evidence"].get("path") or "")
    review_relative = str(references["review"].get("path") or "")
    reviewed_state = str(generation_review.get("reviewed_state_commit") or "")
    ledger_commit = approval_introduction_commit(repo, review_relative)
    approved_payload = git_blob(repo, approved_state, state_relative)
    try:
        approved_document = json.loads(approved_payload or b"")
    except UnicodeError, json.JSONDecodeError:
        approved_document = {}
    approved_attempts = approved_document.get("attempts") or {}
    approved_latest_value = (
        approved_attempts.get(sorted(approved_attempts)[-1])
        if isinstance(approved_attempts, dict) and approved_attempts
        else {}
    )
    approved_latest: dict[str, Any] = approved_latest_value if isinstance(approved_latest_value, dict) else {}
    if (
        approval_introduction_commit(repo, expected_paths["approval"]) != generation_approval.get("introduction_commit")
        or review.get("reviewedStateCommit") != reviewed_state
        or not ledger_commit
        or git_blob(repo, ledger_commit, review_relative) != payloads.get("review")
        or git_commit_parents(repo, ledger_commit) != [reviewed_state]
        or git_name_status_delta(repo, reviewed_state, ledger_commit) != {review_relative: "A"}
        or git_commit_parents(repo, approved_state) != [ledger_commit]
        or git_name_status_delta(repo, ledger_commit, approved_state) != {state_relative: "M"}
        or approved_document.get("status") != "APPROVED"
        or approved_document.get("currentSubmission") is not None
        or approved_document.get("activation") is not None
        or (approved_latest.get("review") or {}).get("result") != "approved"
        or (approved_latest.get("review") or {}).get("reviewedStateCommit") != reviewed_state
        or (approved_latest.get("ledger") or {}).get("path") != review_relative
        or (approved_latest.get("ledger") or {}).get("sha256") != references["review"].get("sha256")
        or git_commit_parents(repo, evidence_commit) != [approved_state]
        or git_name_status_delta(repo, approved_state, evidence_commit) != {evidence_relative: "A"}
        or git_commit_parents(repo, finalization_commit) != [evidence_commit]
        or git_name_status_delta(repo, evidence_commit, finalization_commit)
        != {"planning/backlog.yaml": "M", state_relative: "M"}
    ):
        errors.append(f"{supplement_id}: installed GCR-0007 S-to-L-to-P-to-A-to-F topology is invalid")
    final_backlog_payload = git_blob(repo, finalization_commit, "planning/backlog.yaml")
    try:
        final_backlog = yaml.safe_load((final_backlog_payload or b"").decode("utf-8"))
    except UnicodeError, yaml.YAMLError:
        final_backlog = {}
    final_control = (final_backlog or {}).get("control_plane") or {}
    final_generations = final_control.get("control_generations") or []
    if (
        git_blob(repo, finalization_commit, state_relative) != payloads.get("state")
        or final_control.get("revision") != 11
        or final_control.get("minimum_tool_revision") != 11
        or len(final_generations) != 4
        or final_generations[-1] != generation
    ):
        errors.append(f"{supplement_id}: installed GCR-0007 finalization is not the exact neutral successor")
    return errors


def recovery_supplement_authority_errors(
    data: dict[str, Any],
    repo: Path,
    hold: dict[str, Any],
    supplement: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Bind a supplemental bootstrap to its immutable packet, approval, base GRR, and target amendment."""
    errors: list[str] = []
    supplement_id = str(supplement.get("id") or "")
    bootstrap = supplement.get("bootstrap") or {}
    bootstrap_id = str(bootstrap.get("id") or "")
    references = (
        ("approval", supplement.get("approval_reference") or {}, "introduction_commit"),
        ("packet", supplement.get("packet_reference") or {}, "commit"),
    )
    loaded: dict[str, dict[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for label, reference, commit_field in references:
        relative = str(reference.get("path") or "")
        try:
            path = safe_control_path(
                repo,
                relative,
                prefix=(
                    "planning/governance-recovery-approvals"
                    if label == "approval"
                    else "planning/governance-recovery-requests"
                ),
                label=f"{supplement_id} {label}",
            )
            payload = path.read_bytes()
            document = json.loads(payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{supplement_id}: cannot load {label} reference: {exc}")
            continue
        loaded[label] = document
        payloads[label] = payload
        if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
            errors.append(f"{supplement_id}: {label} reference hash mismatch")
        commit = str(reference.get(commit_field) or "")
        if not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
            errors.append(f"{supplement_id}: {label} authority commit is absent from current history")
        elif git_blob(repo, commit, relative) != payload:
            errors.append(f"{supplement_id}: {label} reference differs from its bound Git blob")
    approval = loaded.get("approval") or {}
    packet = loaded.get("packet") or {}
    approval_packet = approval.get("packet") or {}
    if (
        approval.get("documentType") != "governance-recovery-supplement-approval"
        or approval.get("status") != "APPROVED"
        or approval.get("recoveryRequestId") != hold.get("recovery_request_id")
        or approval.get("supplementId") != supplement_id
        or approval.get("targetWave") != hold.get("target_wave")
        or approval.get("supplementalBootstrapUnit") != bootstrap_id
    ):
        errors.append(f"{supplement_id}: supplemental approval identity, status, Wave, or bootstrap mismatch")
    if (
        packet.get("documentType") != "governance-recovery-supplement-packet"
        or packet.get("recoveryRequestId") != hold.get("recovery_request_id")
        or packet.get("supplementId") != supplement_id
        or packet.get("targetWave") != hold.get("target_wave")
        or (packet.get("supplementalBootstrap") or {}).get("id") != bootstrap_id
    ):
        errors.append(f"{supplement_id}: supplemental packet identity, Wave, or bootstrap mismatch")
    packet_reference = supplement.get("packet_reference") or {}
    if (
        approval_packet.get("commit") != packet_reference.get("commit")
        or approval_packet.get("path") != packet_reference.get("path")
        or approval_packet.get("sha256") != packet_reference.get("sha256")
    ):
        errors.append(f"{supplement_id}: approval does not bind the exact supplemental packet")
    execution = approval.get("executionAuthority") or {}
    if execution.get("supplementalBootstrapOnly") is not True or any(
        execution.get(field) is not False
        for field in (
            "postBootstrapExecution",
            "amendmentMaterialization",
            "ordinaryWaveResume",
            "taskExecution",
            "releaseGateApproval",
        )
    ):
        errors.append(f"{supplement_id}: supplemental approval is not bootstrap-only")
    if approval.get("$schema") in {
        "../governance-recovery-requests/governance-recovery-supplement-approval.v4.schema.json",
        "../governance-recovery-requests/governance-recovery-supplement-approval.v5.schema.json",
    }:
        approval_reference = supplement.get("approval_reference") or {}
        approval_relative = str(approval_reference.get("path") or "")
        approval_introduction = str(approval_reference.get("introduction_commit") or "")
        if approval_introduction_commit(repo, approval_relative) != approval_introduction:
            errors.append(f"{supplement_id}: v4 human approval lacks a unique immutable introduction")
        if not git_is_ancestor(repo, str(packet_reference.get("commit") or ""), approval_introduction):
            errors.append(f"{supplement_id}: v4 human approval does not descend from its packet")
        errors.extend(
            recovery_v4_supplement_packet_review_errors(
                repo,
                supplement_id,
                approval,
                packet,
                payloads.get("packet") or b"",
                str(packet_reference.get("commit") or ""),
                approval_introduction,
            )
        )
    else:
        review = approval.get("independentPacketReview") or {}
        if (
            review.get("result") != "APPROVED"
            or review.get("candidateCommit") != packet_reference.get("commit")
            or review.get("packetSha256") != packet_reference.get("sha256")
            or review.get("reviewer") == approval.get("approvedBy")
            or review.get("openFindingIds") != []
        ):
            errors.append(f"{supplement_id}: supplemental packet review is absent, stale, or not independent")
    base = packet.get("baseRecoveryAuthority") or {}
    base_packet = base.get("packet") or {}
    base_approval = base.get("approval") or {}
    if (
        base_packet.get("path") != (hold.get("packet_reference") or {}).get("path")
        or base_packet.get("sha256") != (hold.get("packet_reference") or {}).get("sha256")
        or base_packet.get("commit") != (hold.get("packet_reference") or {}).get("commit")
        or base_approval.get("path") != (hold.get("approval_reference") or {}).get("path")
        or base_approval.get("sha256") != (hold.get("approval_reference") or {}).get("sha256")
        or base_approval.get("introductionCommit") != (hold.get("approval_reference") or {}).get("introduction_commit")
        or base.get("holdId") != hold.get("id")
        or base.get("bootstrapUnit") != (hold.get("bootstrap") or {}).get("id")
    ):
        errors.append(f"{supplement_id}: base recovery authority differs from the active hold")
    latest = base.get("latestApprovedReview") or {}
    base_attempts = (hold.get("bootstrap") or {}).get("attempts") or []
    if not base_attempts:
        errors.append(f"{supplement_id}: base recovery bootstrap lacks immutable review history")
    else:
        base_last = base_attempts[-1]
        ledger = base_last.get("ledger") or {}
        try:
            ledger_path = safe_control_path(
                repo,
                str(ledger.get("path") or ""),
                prefix="planning/governance-recovery-approvals",
                label=f"{supplement_id} base latest review ledger",
            )
            ledger_document = json.loads(ledger_path.read_bytes())
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{supplement_id}: cannot load base latest review ledger: {exc}")
            ledger_document = {}
        if (
            latest.get("attemptId") != base_last.get("id")
            or latest.get("path") != ledger.get("path")
            or latest.get("sha256") != ledger.get("sha256")
            or latest.get("candidateCommit") != base_last.get("implementation_commit")
            or latest.get("reviewedStateCommit") != ledger_document.get("reviewedStateCommit")
            or ledger_document.get("result") != "approved"
        ):
            errors.append(f"{supplement_id}: base recovery latest approved review binding mismatch")
    target = packet.get("targetAmendmentAuthority") or {}
    target_approval = target.get("amendmentApproval") or {}
    target_bootstrap = target.get("bootstrap") or {}
    if packet.get("schemaVersion") == "4.0-recovery-supplement-proposal":
        installed_control = packet.get("installedControlRecovery") or {}
        generations = (data.get("control_plane") or {}).get("control_generations") or []
        generation: dict[str, Any] = next((item for item in generations if item.get("id") == "GCR-0003"), {})
        installed_approval = installed_control.get("approval") or {}
        installed_review = installed_control.get("latestApprovedReview") or {}
        installed_state = installed_control.get("adoptedState") or {}
        installed_evidence = installed_control.get("adoptionEvidence") or {}
        generation_approval = generation.get("approval_reference") or {}
        generation_review = generation.get("review_reference") or {}
        if (
            installed_control.get("controlRecoveryId") != "GCR-0003"
            or installed_control.get("bootstrapUnit") != "GCR-0003.B00"
            or (installed_control.get("controlTransition") or {})
            != {"predecessorRevision": 9, "successorRevision": 10, "supportedControlCeiling": 11}
            or generation.get("id") != "GCR-0003"
            or generation.get("bootstrap_id") != "GCR-0003.B00"
            or generation.get("predecessor_revision") != 9
            or generation.get("successor_revision") != 10
            or generation.get("supported_control_ceiling") != 11
            or installed_approval
            != {
                "path": generation_approval.get("path"),
                "sha256": generation_approval.get("sha256"),
                "commit": generation_approval.get("introduction_commit"),
            }
            or installed_review
            != {
                "path": generation_review.get("path"),
                "sha256": generation_review.get("sha256"),
                "commit": generation_review.get("approved_state_commit"),
            }
            or installed_control.get("adoptionCommit") != installed_state.get("commit")
        ):
            errors.append(f"{supplement_id}: installed GCR-0003 authority differs from the live generation")
        loaded_installed: dict[str, dict[str, Any]] = {}
        for label, reference in (
            ("state", installed_state),
            ("evidence", installed_evidence),
        ):
            relative = str(reference.get("path") or "")
            commit = str(reference.get("commit") or "")
            try:
                path = safe_control_path(
                    repo,
                    relative,
                    prefix=(
                        "planning/governance-control-recovery"
                        if label == "state"
                        else "artifacts/evidence/governance-control-recovery"
                    ),
                    label=f"{supplement_id} installed GCR-0003 {label}",
                )
                payload = path.read_bytes()
                loaded_installed[label] = json.loads(payload)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{supplement_id}: cannot load installed GCR-0003 {label}: {exc}")
                continue
            if (
                hashlib.sha256(payload).hexdigest() != reference.get("sha256")
                or not git_commit_exists(repo, commit)
                or not git_is_ancestor(repo, commit)
                or git_blob(repo, commit, relative) != payload
            ):
                errors.append(f"{supplement_id}: installed GCR-0003 {label} binding is invalid")
        installed_state_document = loaded_installed.get("state") or {}
        installed_evidence_document = loaded_installed.get("evidence") or {}
        adoption = installed_state_document.get("adoption") or {}
        if (
            installed_state.get("path") != "planning/governance-control-recovery/GCR-0003.B00.state.json"
            or installed_evidence.get("path")
            != "artifacts/evidence/governance-control-recovery/GCR-0003.B00.adoption.json"
            or installed_state_document.get("status") != "ADOPTION_FINALIZATION"
            or adoption.get("predecessorRevision") != 9
            or adoption.get("successorRevision") != 10
            or adoption.get("supportedControlCeiling") != 11
            or adoption.get("evidence") != installed_evidence
            or installed_evidence_document.get("controlRecoveryId") != "GCR-0003"
            or installed_evidence_document.get("predecessorRevision") != 9
            or installed_evidence_document.get("successorRevision") != 10
            or installed_evidence_document.get("supportedControlCeiling") != 11
        ):
            errors.append(f"{supplement_id}: installed GCR-0003 state/evidence authority is invalid")
    if packet.get("schemaVersion") == "5.0-recovery-supplement-proposal":
        errors.extend(recovery_v5_installed_control_errors(data, repo, packet, supplement_id))
    if packet.get("schemaVersion") in {
        "2.0-recovery-supplement-proposal",
        "3.0-recovery-supplement-proposal",
        "4.0-recovery-supplement-proposal",
        "5.0-recovery-supplement-proposal",
    }:
        transition = packet.get("controlTransition") or {}
        if supplement.get("predecessor_control_revision") != transition.get("predecessorRevision") or supplement.get(
            "successor_control_revision"
        ) != transition.get("successorRevision"):
            errors.append(f"{supplement_id}: installed control transition differs from its packet")
        amendment_id = str(target_approval.get("id") or "")
        target_amendment = wave_amendment_map(data).get(amendment_id) or {}
        expected_approval_reference = {
            "path": target_approval.get("path"),
            "sha256": target_approval.get("sha256"),
            "introduction_commit": target_approval.get("introductionCommit"),
        }
        terminal_migration_projection = bool(target_amendment) and (
            target_amendment.get("change_request_id") == (target.get("changeRequestPacket") or {}).get("id")
            and target_amendment.get("target_wave") == packet.get("targetWave")
            and target_amendment.get("kind") == "gate-integrity-safety-defect"
            and target_amendment.get("approval_reference") == expected_approval_reference
            and (target_amendment.get("lifecycle") or {}).get("status") == "SUPERSEDED"
            and target_amendment.get("bootstrap") is None
            and target_amendment.get("campaign") is None
            and target_amendment.get("tasks") == []
        )
        if (target_amendment and not terminal_migration_projection) or target.get("backlogPresence") is not False:
            errors.append(f"{supplement_id}: pre-append target amendment was fabricated in backlog state")
        approval_relative = str(target_approval.get("path") or "")
        try:
            approval_path = safe_control_path(
                repo,
                approval_relative,
                prefix="planning/wave-amendment-approvals",
                label=f"{supplement_id} target amendment approval",
            )
            approval_payload = approval_path.read_bytes()
            approval_document = json.loads(approval_payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{supplement_id}: cannot load target amendment approval: {exc}")
            approval_document = {}
            approval_payload = b""
        introduction = str(target_approval.get("introductionCommit") or "")
        if (
            hashlib.sha256(approval_payload).hexdigest() != target_approval.get("sha256")
            or not git_commit_exists(repo, introduction)
            or not git_is_ancestor(repo, introduction)
            or git_blob(repo, introduction, approval_relative) != approval_payload
            or approval_document.get("status") != "APPROVED"
            or approval_document.get("amendmentId") != amendment_id
        ):
            errors.append(f"{supplement_id}: target amendment approval is stale or invalid")
        candidate = str(target_bootstrap.get("candidateCommit") or "")
        evidence = target_bootstrap.get("evidence") or {}
        evidence_relative = str(evidence.get("path") or "")
        try:
            evidence_path = safe_control_path(
                repo,
                evidence_relative,
                prefix="artifacts/evidence",
                label=f"{supplement_id} target bootstrap evidence",
            )
            evidence_payload = evidence_path.read_bytes()
            evidence_document = json.loads(evidence_payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{supplement_id}: cannot load target bootstrap evidence: {exc}")
            evidence_document = {}
            evidence_payload = b""
        if (
            not git_commit_exists(repo, candidate)
            or not git_is_ancestor(repo, candidate)
            or evidence.get("commit") != candidate
            or hashlib.sha256(evidence_payload).hexdigest() != evidence.get("sha256")
            or evidence_document.get("taskId") != target_bootstrap.get("id")
            or evidence_document.get("commit") != candidate
        ):
            errors.append(f"{supplement_id}: target bootstrap candidate/evidence authority mismatch")
    else:
        amendment = wave_amendment_map(data).get(str(target_approval.get("id") or "")) or {}
        amendment_reference = amendment.get("approval_reference") or {}
        actual_bootstrap = amendment.get("bootstrap") or {}
        actual_evidence = (actual_bootstrap.get("evidence") or [{}])[0]
        if (
            target_approval.get("path") != amendment_reference.get("path")
            or target_approval.get("sha256") != amendment_reference.get("sha256")
            or target_approval.get("introductionCommit") != amendment_reference.get("introduction_commit")
            or target_bootstrap.get("id") != actual_bootstrap.get("id")
            or target_bootstrap.get("candidateCommit") != actual_bootstrap.get("implementation_commit")
            or target_bootstrap.get("evidence", {}).get("path") != actual_evidence.get("path")
            or target_bootstrap.get("evidence", {}).get("sha256") != actual_evidence.get("sha256")
            or target_bootstrap.get("evidence", {}).get("commit") != actual_evidence.get("commit")
            or actual_bootstrap.get("status") != "APPROVED"
        ):
            errors.append(f"{supplement_id}: target amendment approval/bootstrap authority mismatch")
    ecr_reference = target.get("changeRequestPacket") or {}
    try:
        ecr_path = safe_control_path(
            repo,
            str(ecr_reference.get("path") or ""),
            prefix="planning/enabler-change-requests",
            label=f"{supplement_id} target ECR packet",
        )
        ecr_payload = ecr_path.read_bytes()
    except (OSError, ValueError) as exc:
        errors.append(f"{supplement_id}: target ECR packet is invalid: {exc}")
    else:
        if hashlib.sha256(ecr_payload).hexdigest() != ecr_reference.get("sha256"):
            errors.append(f"{supplement_id}: target ECR packet hash mismatch")
        commit = str(ecr_reference.get("commit") or "")
        if not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
            errors.append(f"{supplement_id}: target ECR packet commit is absent from current history")
        elif git_blob(repo, commit, str(ecr_reference.get("path") or "")) != ecr_payload:
            errors.append(f"{supplement_id}: target ECR packet differs from its bound Git blob")
    return errors, packet


def recovery_hold_errors(data: dict[str, Any], repo: Path | None) -> list[str]:
    """Validate the append-only recovery interruption projected by recoveryctl."""
    errors: list[str] = []
    control = data.get("control_plane") or {}
    control_revision = int(control.get("revision") or 0)
    holds = control.get("recovery_holds", [])
    if control_revision == 4 and any("supplements" in hold for hold in holds):
        errors.append("control revision 4 cannot contain recovery supplements")
    if control_revision >= 5 and any("supplements" not in hold for hold in holds):
        errors.append(f"control revision {control_revision} requires an explicit recovery supplement ledger")
    hold_ids = [str(item.get("id")) for item in holds]
    request_ids = [str(item.get("recovery_request_id")) for item in holds]
    if len(hold_ids) != len(set(hold_ids)):
        errors.append("duplicate governance recovery hold identity")
    if len(request_ids) != len(set(request_ids)):
        errors.append("duplicate governance recovery request identity")
    if len(active_recovery_holds(data)) > 1:
        errors.append("more than one governance recovery hold is ACTIVE")
    expected_requests = [f"GRR-{index:04d}" for index in range(1, len(holds) + 1)]
    if request_ids != expected_requests:
        errors.append("governance recovery requests are gapped, reordered, or nonconsecutive")
    active_positions = [index for index, hold in enumerate(holds) if hold.get("status") == "ACTIVE"]
    if active_positions and active_positions != [len(holds) - 1]:
        errors.append("only the latest consecutive governance recovery hold may be ACTIVE")
    if any(
        hold.get("status") != "RELEASED" for hold in holds[: active_positions[0] if active_positions else len(holds)]
    ):
        errors.append("every predecessor governance recovery hold must be terminally RELEASED")
    amendment_records_by_wave: dict[str, list[dict[str, Any]]] = {}
    for amendment in data.get("wave_amendments", []):
        amendment_records_by_wave.setdefault(str(amendment.get("target_wave")), []).append(amendment)
    waves = wave_map(data)
    for hold in holds:
        hold_id = str(hold.get("id") or "")
        request_id = str(hold.get("recovery_request_id") or "")
        wave_id = str(hold.get("target_wave") or "")
        bootstrap = hold.get("bootstrap") or {}
        post = hold.get("post_bootstrap") or {}
        if hold_id != f"HOLD-{wave_id}-{request_id}":
            errors.append(f"{hold_id}: recovery hold, Wave, and request identities are not bound")
        if bootstrap.get("id") != f"{request_id}.B00":
            errors.append(f"{hold_id}: bootstrap identity is outside the recovery request namespace")
        ordered_records = amendment_records_by_wave.get(wave_id, [])
        ordered = [str(item.get("id")) for item in ordered_records]
        required_amendment = str(post.get("required_amendment_id") or "")
        expected_amendment = f"{wave_id}.A{len(ordered) + 1:02d}"
        if required_amendment not in ordered and required_amendment != expected_amendment:
            errors.append(f"{hold_id}: required amendment is not the next consecutive {wave_id} identity")
        prior_records = (
            ordered_records[: ordered.index(required_amendment)] if required_amendment in ordered else ordered_records
        )
        prior_ecr_numbers = [
            int(str(item.get("change_request_id")).removeprefix("ECR-"))
            for item in prior_records
            if re.fullmatch(r"ECR-[0-9]{4}", str(item.get("change_request_id") or ""))
        ]
        if post.get("required_change_request_id") != f"ECR-{max(prior_ecr_numbers, default=0) + 1:04d}":
            errors.append(f"{hold_id}: post-bootstrap change-request identity is not consecutive")
        task_ids = [str(item) for item in post.get("required_proposed_task_ids", [])]
        expected_tasks = [f"{required_amendment}.T{index:02d}" for index in range(1, len(task_ids) + 1)]
        if not task_ids or task_ids != expected_tasks:
            errors.append(f"{hold_id}: proposed task identities are outside the required amendment namespace")
        if post.get("execution_authority") is not False:
            errors.append(f"{hold_id}: recovery approval must not grant post-bootstrap execution authority")
        attempts = bootstrap.get("attempts") or []
        expected_attempts = [f"R{index:02d}" for index in range(1, len(attempts) + 1)]
        if [str(item.get("id")) for item in attempts] != expected_attempts:
            errors.append(f"{hold_id}: bootstrap review attempts are not append-only and sequential")
        for attempt in attempts:
            review = attempt.get("review") or {}
            if review.get("reviewer") == attempt.get("implementer"):
                errors.append(f"{hold_id}/{attempt.get('id')}: bootstrap review is not independent")
        status = str(bootstrap.get("status") or "")
        current = bootstrap.get("current_submission")
        if status == "REVIEW" and current is None:
            errors.append(f"{hold_id}: REVIEW bootstrap lacks its frozen current submission")
        if status != "REVIEW" and current is not None:
            errors.append(f"{hold_id}: non-REVIEW bootstrap retains a mutable current submission")
        if attempts and status != "REVIEW":
            latest = attempts[-1]
            latest_review = latest.get("review") or {}
            expected_status = {
                "approved": "APPROVED",
                "changes-requested": "CHANGES_REQUESTED",
                "blocked": "BLOCKED",
            }.get(str(latest_review.get("result") or ""))
            if status != expected_status:
                errors.append(f"{hold_id}: bootstrap status differs from the latest immutable review")
            for field in ("implementation_commit", "submission_branch", "evidence", "review"):
                if bootstrap.get(field) != latest.get(field):
                    errors.append(f"{hold_id}: bootstrap {field} differs from the latest immutable attempt")
        if status in {"REVIEW", "APPROVED", "CHANGES_REQUESTED", "BLOCKED"} and (
            not bootstrap.get("implementation_commit") or not bootstrap.get("evidence")
        ):
            errors.append(f"{hold_id}: submitted bootstrap lacks commit-bound evidence")
        supplements = hold.get("supplements", [])
        expected_supplements = [f"{request_id}.S{index:02d}" for index in range(1, len(supplements) + 1)]
        actual_supplements = [str(item.get("id") or "") for item in supplements]
        if actual_supplements != expected_supplements or len(actual_supplements) != len(set(actual_supplements)):
            errors.append(f"{hold_id}: recovery supplements are gapped, reordered, duplicated, or cross-request")
        nonapproved_supplements = [
            item for item in supplements if ((item.get("bootstrap") or {}).get("status") != "APPROVED")
        ]
        if len(nonapproved_supplements) > 1 or (
            nonapproved_supplements and nonapproved_supplements[0] is not supplements[-1]
        ):
            errors.append(f"{hold_id}: only the latest recovery supplement may remain non-approved")
        if supplements and status != "APPROVED":
            errors.append(f"{hold_id}: supplemental recovery requires the base bootstrap to remain APPROVED")
        if nonapproved_supplements:
            required = wave_amendment_map(data).get(required_amendment) or {}
            campaign = (waves.get(wave_id) or {}).get("campaign") or {}
            latest_nonapproved = nonapproved_supplements[0]
            if latest_nonapproved.get("successor_control_revision") is not None:
                if required or campaign.get("scope") != "wave":
                    errors.append(
                        f"{hold_id}: unapproved v2 recovery supplement requires the repair amendment "
                        "to remain absent under ordinary Wave scope"
                    )
            elif (
                (required.get("lifecycle") or {}).get("status") != "APPROVED"
                or required.get("tasks")
                or campaign.get("scope") != "wave"
            ):
                errors.append(
                    f"{hold_id}: unapproved latest recovery supplement requires the exact repair amendment "
                    "to remain unmaterialized under ordinary Wave scope"
                )
        for index, supplement in enumerate(supplements, start=1):
            supplement_id = str(supplement.get("id") or "")
            supplement_bootstrap = supplement.get("bootstrap") or {}
            if supplement_bootstrap.get("id") != f"{request_id}.B{index:02d}":
                errors.append(f"{supplement_id}: supplemental bootstrap identity is not sequential and request-bound")
            predecessor = int(supplement.get("predecessor_control_revision") or 0)
            successor_value = supplement.get("successor_control_revision")
            if successor_value is None:
                if index != 1 or predecessor != 4:
                    errors.append(f"{supplement_id}: legacy supplement transition is invalid")
                successor = 6
            else:
                successor = int(successor_value or 0)
                if successor <= predecessor:
                    errors.append(f"{supplement_id}: successor control revision is not greater than predecessor")
            errors.extend(recovery_bootstrap_projection_errors(supplement_id, supplement_bootstrap))
        if int(control.get("revision") or 0) >= GCR_ADOPTION_REVISION:
            transitions = [
                (
                    int(generation.get("predecessor_revision") or 0),
                    int(generation.get("successor_revision") or 0),
                    str(generation.get("id") or ""),
                )
                for generation in control.get("control_generations", [])
            ]
            transitions.extend(
                (
                    int(supplement.get("predecessor_control_revision") or 0),
                    int(supplement.get("successor_control_revision") or 6),
                    str(supplement.get("id") or ""),
                )
                for recovery_hold in control.get("recovery_holds", [])
                for supplement in recovery_hold.get("supplements", [])
            )
            transitions.extend(
                (
                    int(increment.get("predecessor_revision") or 0),
                    int(increment.get("successor_revision") or 0),
                    str(increment.get("id") or ""),
                )
                for increment in control.get("maintenance_increments", [])
            )
            ordered_transitions = sorted(transitions, key=lambda item: (item[0], item[1], item[2]))
            cursor = min((item[0] for item in ordered_transitions), default=RECOVERY_BASE_REVISION)
            for predecessor, successor, transition_id in ordered_transitions:
                exact_neutral_generation = transition_id == "GCR-0007" and predecessor == successor == 11
                if predecessor != cursor or (successor <= predecessor and not exact_neutral_generation):
                    errors.append(f"{transition_id}: control transition does not continue the interleaved global chain")
                    break
                cursor = successor
            if ordered_transitions and cursor != int(control.get("revision") or 0):
                errors.append("interleaved global control transition chain does not reach the live revision")
        if hold.get("status") == "ACTIVE":
            campaign = (waves.get(wave_id) or {}).get("campaign") or {}
            if campaign.get("status") != "PAUSED" or campaign.get("scope") not in {"wave", "amendment-hold"}:
                errors.append(f"{hold_id}: active recovery requires a paused target Wave")
            if hold.get("released_at") is not None:
                errors.append(f"{hold_id}: active recovery hold has a release timestamp")
        elif hold.get("released_at") is None:
            errors.append(f"{hold_id}: released recovery hold lacks a release timestamp")
        if repo is None:
            continue
        if status == "REVIEW":
            evidence = bootstrap.get("evidence") or {}
            relative = str(evidence.get("path") or "")
            try:
                path = safe_control_path(
                    repo,
                    relative,
                    prefix="planning/governance-recovery-approvals",
                    label=f"{hold_id} current evidence",
                )
                evidence_payload = path.read_bytes()
            except (OSError, ValueError) as exc:
                errors.append(f"{hold_id}: invalid current evidence reference: {exc}")
            else:
                current_sha = hashlib.sha256(evidence_payload).hexdigest()
                if current_sha != evidence.get("sha256") or current_sha != (current or {}).get("evidence_sha256"):
                    errors.append(f"{hold_id}: current evidence hash does not match the frozen submission")
                if evidence.get("commit") != (current or {}).get("candidate_commit"):
                    errors.append(f"{hold_id}: current evidence commit does not match the frozen submission")
        for attempt in attempts:
            attempt_id = str(attempt.get("id") or "")
            for label, reference in (
                ("evidence", attempt.get("evidence") or {}),
                ("review ledger", attempt.get("ledger") or {}),
            ):
                relative = str(reference.get("path") or "")
                try:
                    path = safe_control_path(
                        repo,
                        relative,
                        prefix="planning/governance-recovery-approvals",
                        label=f"{hold_id}/{attempt_id} {label}",
                    )
                    reference_payload = path.read_bytes()
                except (OSError, ValueError) as exc:
                    errors.append(f"{hold_id}/{attempt_id}: invalid {label} reference: {exc}")
                    continue
                if hashlib.sha256(reference_payload).hexdigest() != reference.get("sha256"):
                    errors.append(f"{hold_id}/{attempt_id}: {label} reference hash mismatch")
        for supplement in supplements:
            supplement_id = str(supplement.get("id") or "")
            supplement_bootstrap = supplement.get("bootstrap") or {}
            current_supplement = supplement_bootstrap.get("current_submission") or {}
            if supplement_bootstrap.get("status") == "REVIEW":
                evidence = supplement_bootstrap.get("evidence") or {}
                relative = str(evidence.get("path") or "")
                try:
                    path = safe_control_path(
                        repo,
                        relative,
                        prefix="planning/governance-recovery-approvals",
                        label=f"{supplement_id} current evidence",
                    )
                    evidence_payload = path.read_bytes()
                except (OSError, ValueError) as exc:
                    errors.append(f"{supplement_id}: invalid current evidence reference: {exc}")
                else:
                    current_sha = hashlib.sha256(evidence_payload).hexdigest()
                    if (
                        current_sha != evidence.get("sha256")
                        or current_sha != current_supplement.get("evidence_sha256")
                        or evidence.get("commit") != current_supplement.get("candidate_commit")
                    ):
                        errors.append(f"{supplement_id}: current evidence differs from its frozen submission")
            supplement_errors, supplement_packet = recovery_supplement_authority_errors(data, repo, hold, supplement)
            errors.extend(supplement_errors)
            if supplement_packet:
                errors.extend(
                    recovery_review_history_errors(
                        repo,
                        hold,
                        supplement_packet,
                        supplement=supplement,
                    )
                )
        references = (
            ("approval", hold.get("approval_reference") or {}, "introduction_commit"),
            ("packet", hold.get("packet_reference") or {}, "commit"),
        )
        loaded: dict[str, dict[str, Any]] = {}
        for label, reference, commit_field in references:
            relative = str(reference.get("path") or "")
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
                errors.append(f"{hold_id}: unsafe {label} reference path")
                continue
            path = repo.joinpath(*pure.parts)
            try:
                payload = path.read_bytes()
                loaded[label] = json.loads(payload)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                errors.append(f"{hold_id}: cannot load {label} reference: {exc}")
                continue
            if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
                errors.append(f"{hold_id}: {label} reference hash mismatch")
            commit = str(reference.get(commit_field) or "")
            if not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
                errors.append(f"{hold_id}: {label} authority commit is absent from current history")
            elif git_blob(repo, commit, relative) != payload:
                errors.append(f"{hold_id}: {label} reference differs from its bound Git blob")
        approval = loaded.get("approval") or {}
        packet = loaded.get("packet") or {}
        if approval.get("status") != "APPROVED" or approval.get("recoveryRequestId") != request_id:
            errors.append(f"{hold_id}: recovery approval identity or status mismatch")
        if approval.get("targetWave") != wave_id or approval.get("bootstrapUnit") != bootstrap.get("id"):
            errors.append(f"{hold_id}: recovery approval Wave/bootstrap binding mismatch")
        if (approval.get("executionAuthority") or {}).get("bootstrapOnly") is not True or (
            approval.get("executionAuthority") or {}
        ).get("postBootstrapExecution") is not False:
            errors.append(f"{hold_id}: recovery approval authority is not bootstrap-only")
        if packet.get("recoveryRequestId") != request_id or packet.get("targetWave") != wave_id:
            errors.append(f"{hold_id}: recovery packet identity mismatch")
        if (packet.get("controlHold") or {}).get("id") != hold_id:
            errors.append(f"{hold_id}: recovery packet hold identity mismatch")
        if (packet.get("bootstrapUnit") or {}).get("id") != bootstrap.get("id"):
            errors.append(f"{hold_id}: recovery packet bootstrap identity mismatch")
        packet_post = packet.get("postBootstrap") or {}
        if (
            packet_post.get("requiredChangeRequestId") != post.get("required_change_request_id")
            or packet_post.get("requiredAmendmentId") != required_amendment
            or packet_post.get("requiredProposedTaskIds") != task_ids
            or packet_post.get("postBootstrapExecutionAuthority") is not False
        ):
            errors.append(f"{hold_id}: recovery packet post-bootstrap binding mismatch")
        errors.extend(recovery_review_history_errors(repo, hold, packet))
    errors.extend(governance_control_generation_errors(data, repo))
    return errors


def governance_control_generation_errors(data: dict[str, Any], repo: Path | None) -> list[str]:
    """Validate the one-time GCR generation and its exact approved authority."""
    errors: list[str] = []
    if repo is not None:
        transaction_artifacts = [
            relative for relative in GCR_ADOPTION_TRANSACTION_PATHS if os.path.lexists(repo / relative)
        ]
        if transaction_artifacts:
            errors.append(
                "GCR-0001 adoption transaction requires explicit gcrctl recovery: " + ", ".join(transaction_artifacts)
            )
    control = data.get("control_plane") or {}
    revision = int(control.get("revision") or 0)
    maintenance = control.get("maintenance_increments") or []
    if revision < 12 and maintenance:
        errors.append("control revisions before 12 cannot contain maintenance increments")
    if revision >= 12:
        if len(maintenance) != 1:
            errors.append("control revision 12 requires exactly one bounded maintenance increment")
        else:
            increment = maintenance[0] or {}
            amendment = wave_amendment_map(data).get(str(increment.get("amendment_id") or "")) or {}
            if (
                increment.get("id") != "MI-0001"
                or increment.get("kind") != "post-migration-amendment-bootstrap"
                or increment.get("predecessor_revision") != 11
                or increment.get("successor_revision") != 12
                or amendment.get("kind") != "product-scope-security-experience"
                or increment.get("change_request_id") != amendment.get("change_request_id")
                or increment.get("approval_reference") != amendment.get("approval_reference")
                or not increment.get("applied_by")
                or not valid_json_datetime(increment.get("applied_at"))
            ):
                errors.append("control revision 12 maintenance increment identity or authority is invalid")
            if repo is not None and amendment:
                try:
                    _approval, packet, _payload = load_amendment_authority(
                        repo, str(increment.get("amendment_id") or "")
                    )
                except SystemExit as exc:
                    errors.append(f"control revision 12 maintenance authority is invalid: {exc}")
                else:
                    if packet.get("schemaVersion") not in {"4.0-proposal", "4.1-proposal"} or packet.get(
                        "migrationAuthority"
                    ) != increment.get("migration_reference"):
                        errors.append("control revision 12 maintenance increment differs from its v4 authority")
    live_state: dict[str, Any] = {}
    if repo is not None:
        state_path = repo / "planning/governance-control-recovery/GCR-0001.B00.state.json"
        if state_path.is_file() and not state_path.is_symlink():
            try:
                loaded_state = json.loads(state_path.read_bytes())
                if isinstance(loaded_state, dict):
                    live_state = loaded_state
            except OSError, UnicodeError, json.JSONDecodeError:
                errors.append("GCR-0001 live state is unreadable or malformed")
    generations = control.get("control_generations") or []
    if revision < GCR_ADOPTION_REVISION:
        if generations:
            errors.append("control revisions before 7 cannot contain GCR generation records")
        if live_state.get("status") == "ADOPTED" or live_state.get("adoption") is not None:
            errors.append("control revision 6 cannot coexist with an adopted GCR-0001 live state")
        return errors
    expected_generation_counts = (
        {3, 4}
        if revision >= 12
        else {3, 4}
        if revision == 11
        else {3}
        if revision >= 10
        else {2}
        if revision >= 9
        else {1}
    )
    if len(generations) not in expected_generation_counts:
        rendered = " or ".join(str(item) for item in sorted(expected_generation_counts))
        return [f"control revision {revision} requires exactly {rendered} GCR generation record(s)"]
    generation = generations[0] or {}
    if (
        generation.get("id") != "GCR-0001"
        or generation.get("bootstrap_id") != "GCR-0001.B00"
        or generation.get("hold_id") != "HOLD-W1-GRR-0002"
        or generation.get("predecessor_revision") != 6
        or generation.get("successor_revision") != GCR_ADOPTION_REVISION
    ):
        errors.append("GCR-0001 generation identity or 6-to-7 transition is invalid")
    if len(generations) == 4:
        neutral = generations[3] or {}
        if (
            neutral.get("id") != "GCR-0007"
            or neutral.get("bootstrap_id") != "GCR-0007.B00"
            or neutral.get("hold_id") != "HOLD-W1-GRR-0002"
            or neutral.get("predecessor_revision") != 11
            or neutral.get("successor_revision") != 11
            or neutral.get("supported_control_ceiling") != 12
            or neutral.get("generation_neutral") is not True
        ):
            errors.append("GCR-0007 generation identity or neutral 11-to-11 transition is invalid")
    successors = [
        int(supplement.get("successor_control_revision") or 0)
        for hold in control.get("recovery_holds", [])
        for supplement in hold.get("supplements", [])
        if supplement.get("successor_control_revision") is not None
    ]
    successors.extend(int(item.get("successor_revision") or 0) for item in maintenance)
    latest_successor = max(
        [int((generations[-1] or {}).get("successor_revision") or 0), *successors],
        default=GCR_ADOPTION_REVISION,
    )
    if latest_successor != revision:
        errors.append("control revision differs from the latest explicit generation transition")
    if repo is None:
        return errors
    references = (
        ("approval", generation.get("approval_reference") or {}, "introduction_commit"),
        ("review", generation.get("review_reference") or {}, "approved_state_commit"),
    )
    loaded: dict[str, dict[str, Any]] = {}
    for label, reference, commit_field in references:
        relative = str(reference.get("path") or "")
        try:
            path = safe_control_path(
                repo,
                relative,
                prefix="planning/governance-control-recovery",
                label=f"GCR-0001 {label}",
            )
            payload = path.read_bytes()
            loaded[label] = json.loads(payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"GCR-0001 cannot load {label} authority: {exc}")
            continue
        if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
            errors.append(f"GCR-0001 {label} authority hash mismatch")
        commit = str(reference.get(commit_field) or "")
        if not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
            errors.append(f"GCR-0001 {label} authority commit is absent from current history")
        elif git_blob(repo, commit, relative) != payload:
            errors.append(f"GCR-0001 {label} authority differs from its immutable Git blob")
    approval = loaded.get("approval") or {}
    review = loaded.get("review") or {}
    if approval.get("status") != "APPROVED" or approval.get("controlRecoveryId") != "GCR-0001":
        errors.append("GCR-0001 approval identity or status mismatch")
    if review.get("result") != "approved" or review.get("controlRecoveryId") != "GCR-0001":
        errors.append("GCR-0001 bootstrap review identity or status mismatch")
    if review.get("reviewedStateCommit") != (generation.get("review_reference") or {}).get("reviewed_state_commit"):
        errors.append("GCR-0001 generation review-state binding mismatch")
    review_reference = generation.get("review_reference") or {}
    reviewed_state = str(review_reference.get("reviewed_state_commit") or "")
    approved_state = str(review_reference.get("approved_state_commit") or "")
    if (
        not git_commit_exists(repo, reviewed_state)
        or not git_is_ancestor(repo, reviewed_state)
        or reviewed_state == approved_state
        or not git_is_ancestor(repo, reviewed_state, approved_state)
    ):
        errors.append("GCR-0001 approved state does not strictly descend from its reviewed state")
    review_relative = str(review_reference.get("path") or "")
    if (
        approval_introduction_commit(repo, review_relative) != approved_state
        or git_commit_parents(repo, approved_state) != [reviewed_state]
        or git_name_status_delta(repo, reviewed_state, approved_state)
        != {
            review_relative: "A",
            "planning/governance-control-recovery/GCR-0001.B00.state.json": "M",
        }
    ):
        errors.append("GCR-0001 approved state is not the canonical exact review-ledger application commit")
    state_payload = git_blob(
        repo,
        approved_state,
        "planning/governance-control-recovery/GCR-0001.B00.state.json",
    )
    try:
        approved_state_document = json.loads(state_payload or b"")
    except UnicodeError, json.JSONDecodeError:
        approved_state_document = {}
    approved_attempts = approved_state_document.get("attempts") or []
    latest_attempt = approved_attempts[-1] if approved_attempts else {}
    if (
        approved_state_document.get("controlRecoveryId") != "GCR-0001"
        or approved_state_document.get("bootstrapUnit") != "GCR-0001.B00"
        or approved_state_document.get("status") != "APPROVED"
        or approved_state_document.get("currentSubmission") is not None
        or approved_state_document.get("adoption") is not None
        or (latest_attempt.get("review") or {}).get("result") != "approved"
        or (latest_attempt.get("review") or {}).get("reviewedStateCommit") != reviewed_state
        or (latest_attempt.get("ledger") or {}).get("path") != review_reference.get("path")
        or (latest_attempt.get("ledger") or {}).get("sha256") != review_reference.get("sha256")
    ):
        errors.append("GCR-0001 approved-state Git blob does not reproduce the approved review")
    adoption = live_state.get("adoption") or {}
    evidence = adoption.get("evidence") or {}
    evidence_relative = str(evidence.get("path") or "")
    evidence_commit = str(evidence.get("commit") or "")
    try:
        evidence_path = safe_control_path(
            repo,
            evidence_relative,
            prefix="artifacts/evidence/governance-control-recovery",
            label="GCR-0001 adoption evidence",
        )
        evidence_payload = evidence_path.read_bytes()
        evidence_document = json.loads(evidence_payload)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"GCR-0001 cannot load adoption evidence: {exc}")
        evidence_payload = b""
        evidence_document = {}
    if (
        live_state.get("status") != "ADOPTION_FINALIZATION"
        or adoption.get("predecessorRevision") != 6
        or adoption.get("successorRevision") != GCR_ADOPTION_REVISION
        or adoption.get("reviewedStateCommit") != approved_state
        or evidence_relative != "artifacts/evidence/governance-control-recovery/GCR-0001.B00.adoption.json"
        or hashlib.sha256(evidence_payload).hexdigest() != evidence.get("sha256")
        or not git_commit_exists(repo, evidence_commit)
        or not git_is_ancestor(repo, evidence_commit)
        or git_blob(repo, evidence_commit, evidence_relative) != evidence_payload
        or evidence_document.get("reviewedStateCommit") != approved_state
    ):
        errors.append("GCR-0001 live adoption state/evidence does not match the adopted generation")
    live_state_path = repo / "planning/governance-control-recovery/GCR-0001.B00.state.json"
    if (
        live_state.get("status") == "ADOPTION_FINALIZATION"
        and live_state_path.is_file()
        and not live_state_path.is_symlink()
    ):
        errors.extend(
            governance_control_adoption_finalization_errors(
                repo,
                evidence_commit,
                live_state_path.read_bytes(),
                generation,
            )
        )
    if revision >= 9:
        errors.extend(governance_control_v2_generation_errors(repo, generations[1]))
    if revision >= 10:
        errors.extend(governance_control_v3_generation_errors(repo, generations[2]))
    if len(generations) == 4:
        errors.extend(governance_control_v4_generation_errors(repo, generations[3]))
    return errors


def governance_control_v2_generation_errors(repo: Path, generation: dict[str, Any]) -> list[str]:
    """Validate the exact GCR-0002 8-to-9 generation and finalization."""
    errors: list[str] = []
    if (
        generation.get("id") != "GCR-0002"
        or generation.get("bootstrap_id") != "GCR-0002.B00"
        or generation.get("hold_id") != "HOLD-W1-GRR-0002"
        or generation.get("predecessor_revision") != 8
        or generation.get("successor_revision") != 9
    ):
        return ["GCR-0002 generation identity or 8-to-9 transition is invalid"]
    approval_reference = generation.get("approval_reference") or {}
    review_reference = generation.get("review_reference") or {}
    references = (
        (
            "approval",
            approval_reference,
            "introduction_commit",
            "planning/governance-control-recovery/GCR-0002.approval.json",
        ),
        ("review", review_reference, "approved_state_commit", str(review_reference.get("path") or "")),
    )
    loaded: dict[str, dict[str, Any]] = {}
    for label, reference, commit_field, expected_path in references:
        relative = str(reference.get("path") or "")
        if relative != expected_path:
            errors.append(f"GCR-0002 {label} path is not canonical")
            continue
        try:
            path = safe_control_path(
                repo,
                relative,
                prefix="planning/governance-control-recovery",
                label=f"GCR-0002 {label}",
            )
            payload = path.read_bytes()
            loaded[label] = json.loads(payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"GCR-0002 cannot load {label} authority: {exc}")
            continue
        if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
            errors.append(f"GCR-0002 {label} authority hash mismatch")
        commit = str(reference.get(commit_field) or "")
        if not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
            errors.append(f"GCR-0002 {label} authority commit is absent from current history")
        elif git_blob(repo, commit, relative) != payload:
            errors.append(f"GCR-0002 {label} authority differs from its immutable Git blob")
    approval = loaded.get("approval") or {}
    review = loaded.get("review") or {}
    if approval.get("status") != "APPROVED" or approval.get("controlRecoveryId") != "GCR-0002":
        errors.append("GCR-0002 approval identity or status mismatch")
    if review.get("result") != "approved" or review.get("controlRecoveryId") != "GCR-0002":
        errors.append("GCR-0002 bootstrap review identity or status mismatch")
    reviewed_state = str(review_reference.get("reviewed_state_commit") or "")
    approved_state = str(review_reference.get("approved_state_commit") or "")
    state_relative = "planning/governance-control-recovery/GCR-0002.B00.state.json"
    review_relative = str(review_reference.get("path") or "")
    if (
        review.get("reviewedStateCommit") != reviewed_state
        or approval_introduction_commit(repo, review_relative) != approved_state
        or git_commit_parents(repo, approved_state) != [reviewed_state]
        or git_name_status_delta(repo, reviewed_state, approved_state) != {review_relative: "A", state_relative: "M"}
    ):
        errors.append("GCR-0002 approved state is not the canonical exact review-ledger application commit")
    approved_payload = git_blob(repo, approved_state, state_relative)
    try:
        approved_document = json.loads(approved_payload or b"")
    except UnicodeError, json.JSONDecodeError:
        approved_document = {}
    attempts = approved_document.get("attempts") or []
    latest = attempts[-1] if attempts else {}
    if (
        approved_document.get("controlRecoveryId") != "GCR-0002"
        or approved_document.get("bootstrapUnit") != "GCR-0002.B00"
        or approved_document.get("status") != "APPROVED"
        or approved_document.get("currentSubmission") is not None
        or approved_document.get("adoption") is not None
        or (latest.get("review") or {}).get("result") != "approved"
        or (latest.get("review") or {}).get("reviewedStateCommit") != reviewed_state
        or (latest.get("ledger") or {}).get("path") != review_relative
        or (latest.get("ledger") or {}).get("sha256") != review_reference.get("sha256")
    ):
        errors.append("GCR-0002 approved-state Git blob does not reproduce the approved review")
    live_path = repo / state_relative
    try:
        live_state = json.loads(live_path.read_bytes())
    except OSError, UnicodeError, json.JSONDecodeError:
        return [*errors, "GCR-0002 live state is unreadable or malformed"]
    adoption = live_state.get("adoption") or {}
    evidence = adoption.get("evidence") or {}
    evidence_relative = str(evidence.get("path") or "")
    evidence_commit = str(evidence.get("commit") or "")
    try:
        evidence_path = safe_control_path(
            repo,
            evidence_relative,
            prefix="artifacts/evidence/governance-control-recovery",
            label="GCR-0002 adoption evidence",
        )
        evidence_payload = evidence_path.read_bytes()
        evidence_document = json.loads(evidence_payload)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"GCR-0002 cannot load adoption evidence: {exc}")
        evidence_payload = b""
        evidence_document = {}
    if (
        live_state.get("status") != "ADOPTION_FINALIZATION"
        or adoption.get("predecessorRevision") != 8
        or adoption.get("successorRevision") != 9
        or adoption.get("reviewedStateCommit") != approved_state
        or evidence_relative != "artifacts/evidence/governance-control-recovery/GCR-0002.B00.adoption.json"
        or hashlib.sha256(evidence_payload).hexdigest() != evidence.get("sha256")
        or not git_commit_exists(repo, evidence_commit)
        or not git_is_ancestor(repo, evidence_commit)
        or git_blob(repo, evidence_commit, evidence_relative) != evidence_payload
        or evidence_document.get("reviewedStateCommit") != approved_state
    ):
        errors.append("GCR-0002 live adoption state/evidence does not match the adopted generation")
    if git_commit_parents(repo, evidence_commit) != [approved_state] or git_name_status_delta(
        repo, approved_state, evidence_commit
    ) != {evidence_relative: "A"}:
        errors.append("GCR-0002 adoption evidence is not the exact direct child of its approved state")
    matches = [
        commit
        for commit in git_commits_changing_path_after(repo, evidence_commit, state_relative)
        if git_blob(repo, commit, state_relative) == live_path.read_bytes()
    ]
    if len(matches) != 1:
        errors.append("GCR-0002 adoption finalization commit is absent or not unique")
    else:
        finalization = matches[0]
        if git_commit_parents(repo, finalization) != [evidence_commit] or git_name_status_delta(
            repo, evidence_commit, finalization
        ) != {"planning/backlog.yaml": "M", state_relative: "M"}:
            errors.append("GCR-0002 adoption finalization is not the exact direct-child two-path transition")
        finalization_backlog = git_blob(repo, finalization, "planning/backlog.yaml")
        try:
            finalization_document = yaml.safe_load((finalization_backlog or b"").decode("utf-8"))
        except UnicodeError, yaml.YAMLError:
            finalization_document = {}
        finalization_control = (finalization_document or {}).get("control_plane") or {}
        final_generations = finalization_control.get("control_generations") or []
        if (
            finalization_control.get("revision") != 9
            or finalization_control.get("minimum_tool_revision") != 9
            or len(final_generations) != 2
            or final_generations[1] != generation
            or (final_generations[0] or {}).get("id") != "GCR-0001"
        ):
            errors.append("GCR-0002 finalization does not freeze the exact revision-9 generation ledger")
    return errors


def governance_control_v3_generation_errors(repo: Path, generation: dict[str, Any]) -> list[str]:
    """Validate the exact GCR-0003 9-to-10 generation and finalization."""
    errors: list[str] = []
    if (
        generation.get("id") != "GCR-0003"
        or generation.get("bootstrap_id") != "GCR-0003.B00"
        or generation.get("hold_id") != "HOLD-W1-GRR-0002"
        or generation.get("predecessor_revision") != 9
        or generation.get("successor_revision") != 10
        or generation.get("supported_control_ceiling") != 11
    ):
        return ["GCR-0003 generation identity or 9-to-10 transition is invalid"]
    approval_reference = generation.get("approval_reference") or {}
    review_reference = generation.get("review_reference") or {}
    references = (
        (
            "approval",
            approval_reference,
            "introduction_commit",
            "planning/governance-control-recovery/GCR-0003.approval.json",
        ),
        ("review", review_reference, "approved_state_commit", str(review_reference.get("path") or "")),
    )
    loaded: dict[str, dict[str, Any]] = {}
    for label, reference, commit_field, expected_path in references:
        relative = str(reference.get("path") or "")
        if relative != expected_path:
            errors.append(f"GCR-0003 {label} path is not canonical")
            continue
        try:
            path = safe_control_path(
                repo,
                relative,
                prefix="planning/governance-control-recovery",
                label=f"GCR-0003 {label}",
            )
            payload = path.read_bytes()
            loaded[label] = json.loads(payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"GCR-0003 cannot load {label} authority: {exc}")
            continue
        if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
            errors.append(f"GCR-0003 {label} authority hash mismatch")
        commit = str(reference.get(commit_field) or "")
        if not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
            errors.append(f"GCR-0003 {label} authority commit is absent from current history")
        elif git_blob(repo, commit, relative) != payload:
            errors.append(f"GCR-0003 {label} authority differs from its immutable Git blob")
    approval = loaded.get("approval") or {}
    review = loaded.get("review") or {}
    if approval.get("status") != "APPROVED" or approval.get("controlRecoveryId") != "GCR-0003":
        errors.append("GCR-0003 approval identity or status mismatch")
    if review.get("result") != "approved" or review.get("controlRecoveryId") != "GCR-0003":
        errors.append("GCR-0003 bootstrap review identity or status mismatch")
    reviewed_state = str(review_reference.get("reviewed_state_commit") or "")
    approved_state = str(review_reference.get("approved_state_commit") or "")
    state_relative = "planning/governance-control-recovery/GCR-0003.B00.state.json"
    review_relative = str(review_reference.get("path") or "")
    if (
        review.get("reviewedStateCommit") != reviewed_state
        or approval_introduction_commit(repo, review_relative) != approved_state
        or git_commit_parents(repo, approved_state) != [reviewed_state]
        or git_name_status_delta(repo, reviewed_state, approved_state) != {review_relative: "A", state_relative: "M"}
    ):
        errors.append("GCR-0003 approved state is not the canonical exact review-ledger application commit")
    approved_payload = git_blob(repo, approved_state, state_relative)
    try:
        approved_document = json.loads(approved_payload or b"")
    except UnicodeError, json.JSONDecodeError:
        approved_document = {}
    attempts = approved_document.get("attempts") or []
    latest = attempts[-1] if attempts else {}
    if (
        approved_document.get("controlRecoveryId") != "GCR-0003"
        or approved_document.get("bootstrapUnit") != "GCR-0003.B00"
        or approved_document.get("status") != "APPROVED"
        or approved_document.get("currentSubmission") is not None
        or approved_document.get("adoption") is not None
        or (latest.get("review") or {}).get("result") != "approved"
        or (latest.get("review") or {}).get("reviewedStateCommit") != reviewed_state
        or (latest.get("ledger") or {}).get("path") != review_relative
        or (latest.get("ledger") or {}).get("sha256") != review_reference.get("sha256")
    ):
        errors.append("GCR-0003 approved-state Git blob does not reproduce the approved review")
    live_path = repo / state_relative
    try:
        live_state = json.loads(live_path.read_bytes())
    except OSError, UnicodeError, json.JSONDecodeError:
        return [*errors, "GCR-0003 live state is unreadable or malformed"]
    adoption = live_state.get("adoption") or {}
    evidence = adoption.get("evidence") or {}
    evidence_relative = str(evidence.get("path") or "")
    evidence_commit = str(evidence.get("commit") or "")
    try:
        evidence_path = safe_control_path(
            repo,
            evidence_relative,
            prefix="artifacts/evidence/governance-control-recovery",
            label="GCR-0003 adoption evidence",
        )
        evidence_payload = evidence_path.read_bytes()
        evidence_document = json.loads(evidence_payload)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"GCR-0003 cannot load adoption evidence: {exc}")
        evidence_payload = b""
        evidence_document = {}
    if (
        live_state.get("status") != "ADOPTION_FINALIZATION"
        or adoption.get("predecessorRevision") != 9
        or adoption.get("successorRevision") != 10
        or adoption.get("supportedControlCeiling") != 11
        or adoption.get("reviewedStateCommit") != approved_state
        or evidence_relative != "artifacts/evidence/governance-control-recovery/GCR-0003.B00.adoption.json"
        or hashlib.sha256(evidence_payload).hexdigest() != evidence.get("sha256")
        or not git_commit_exists(repo, evidence_commit)
        or not git_is_ancestor(repo, evidence_commit)
        or git_blob(repo, evidence_commit, evidence_relative) != evidence_payload
        or evidence_document.get("reviewedStateCommit") != approved_state
    ):
        errors.append("GCR-0003 live adoption state/evidence does not match the adopted generation")
    if git_commit_parents(repo, evidence_commit) != [approved_state] or git_name_status_delta(
        repo, approved_state, evidence_commit
    ) != {evidence_relative: "A"}:
        errors.append("GCR-0003 adoption evidence is not the exact direct child of its approved state")
    matches = [
        commit
        for commit in git_commits_changing_path_after(repo, evidence_commit, state_relative)
        if git_blob(repo, commit, state_relative) == live_path.read_bytes()
    ]
    if len(matches) != 1:
        errors.append("GCR-0003 adoption finalization commit is absent or not unique")
    else:
        finalization = matches[0]
        if git_commit_parents(repo, finalization) != [evidence_commit] or git_name_status_delta(
            repo, evidence_commit, finalization
        ) != {"planning/backlog.yaml": "M", state_relative: "M"}:
            errors.append("GCR-0003 adoption finalization is not the exact direct-child two-path transition")
        finalization_backlog = git_blob(repo, finalization, "planning/backlog.yaml")
        try:
            finalization_document = yaml.safe_load((finalization_backlog or b"").decode("utf-8"))
        except UnicodeError, yaml.YAMLError:
            finalization_document = {}
        finalization_control = (finalization_document or {}).get("control_plane") or {}
        final_generations = finalization_control.get("control_generations") or []
        if (
            finalization_control.get("revision") != 10
            or finalization_control.get("minimum_tool_revision") != 10
            or len(final_generations) != 3
            or final_generations[2] != generation
            or (final_generations[0] or {}).get("id") != "GCR-0001"
            or (final_generations[1] or {}).get("id") != "GCR-0002"
        ):
            errors.append("GCR-0003 finalization does not freeze the exact revision-10 generation ledger")
    return errors


def governance_control_v4_generation_errors(repo: Path, generation: dict[str, Any]) -> list[str]:
    """Validate the exact non-circular GCR-0007 neutral generation and S-L-P-A-F finalization."""
    errors: list[str] = []
    if (
        generation.get("id") != "GCR-0007"
        or generation.get("bootstrap_id") != "GCR-0007.B00"
        or generation.get("hold_id") != "HOLD-W1-GRR-0002"
        or generation.get("predecessor_revision") != 11
        or generation.get("successor_revision") != 11
        or generation.get("supported_control_ceiling") != 12
        or generation.get("generation_neutral") is not True
    ):
        return ["GCR-0007 generation identity or neutral 11-to-11 transition is invalid"]
    approval_reference = generation.get("approval_reference") or {}
    review_reference = generation.get("review_reference") or {}
    references = (
        (
            "approval",
            approval_reference,
            "introduction_commit",
            "planning/governance-control-recovery/GCR-0007.approval.json",
        ),
        ("review", review_reference, "approved_state_commit", str(review_reference.get("path") or "")),
    )
    loaded: dict[str, dict[str, Any]] = {}
    for label, reference, commit_field, expected_path in references:
        relative = str(reference.get("path") or "")
        if relative != expected_path or (
            label == "review"
            and re.fullmatch(
                r"planning/governance-control-recovery/GCR-0007\.B00\.review-R[0-9]{2,}\.json",
                relative,
            )
            is None
        ):
            errors.append(f"GCR-0007 {label} path is not canonical")
            continue
        try:
            path = safe_control_path(
                repo,
                relative,
                prefix="planning/governance-control-recovery",
                label=f"GCR-0007 {label}",
            )
            payload = path.read_bytes()
            loaded[label] = json.loads(payload)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"GCR-0007 cannot load {label} authority: {exc}")
            continue
        if hashlib.sha256(payload).hexdigest() != reference.get("sha256"):
            errors.append(f"GCR-0007 {label} authority hash mismatch")
        commit = str(reference.get(commit_field) or "")
        if not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
            errors.append(f"GCR-0007 {label} authority commit is absent from current history")
        elif git_blob(repo, commit, relative) != payload:
            errors.append(f"GCR-0007 {label} authority differs from its immutable Git blob")
    approval = loaded.get("approval") or {}
    review = loaded.get("review") or {}
    if (
        approval.get("documentType") != "governance-control-recovery-successor-approval"
        or approval.get("controlRecoveryId") != "GCR-0007"
        or approval.get("ordinaryExecutionAuthority") is not False
    ):
        errors.append("GCR-0007 approval identity or scope mismatch")
    if (
        review.get("result") != "approved"
        or review.get("controlRecoveryId") != "GCR-0007"
        or review.get("bootstrapUnit") != "GCR-0007.B00"
        or review.get("findings") != []
    ):
        errors.append("GCR-0007 bootstrap review identity or status mismatch")
    reviewed_state = str(review_reference.get("reviewed_state_commit") or "")
    approved_state = str(review_reference.get("approved_state_commit") or "")
    state_relative = "planning/governance-control-recovery/GCR-0007.B00.state.json"
    review_relative = str(review_reference.get("path") or "")
    ledger_commit = approval_introduction_commit(repo, review_relative)
    if (
        review.get("reviewedStateCommit") != reviewed_state
        or not ledger_commit
        or git_blob(repo, ledger_commit, review_relative) != (repo / review_relative).read_bytes()
        or git_commit_parents(repo, ledger_commit) != [reviewed_state]
        or git_name_status_delta(repo, reviewed_state, ledger_commit) != {review_relative: "A"}
        or git_commit_parents(repo, approved_state) != [ledger_commit]
        or git_name_status_delta(repo, ledger_commit, approved_state) != {state_relative: "M"}
    ):
        errors.append("GCR-0007 approved state is not the canonical S-to-L-to-P review application")
    approved_payload = git_blob(repo, approved_state, state_relative)
    try:
        approved_document = json.loads(approved_payload or b"")
    except UnicodeError, json.JSONDecodeError:
        approved_document = {}
    attempts = approved_document.get("attempts") or {}
    latest_attempt_id = sorted(attempts)[-1] if isinstance(attempts, dict) and attempts else ""
    latest_value = attempts.get(latest_attempt_id) if isinstance(attempts, dict) and latest_attempt_id else {}
    latest: dict[str, Any] = latest_value if isinstance(latest_value, dict) else {}
    expected_evidence_relative = (
        "artifacts/evidence/governance-control-recovery/GCR-0007.B00.adoption.json"
        if latest_attempt_id == "R02"
        else f"artifacts/evidence/governance-control-recovery/GCR-0007.B00.adoption-{latest_attempt_id}.json"
    )
    if (
        approved_document.get("controlRecoveryId") != "GCR-0007"
        or approved_document.get("bootstrapUnit") != "GCR-0007.B00"
        or approved_document.get("status") != "APPROVED"
        or approved_document.get("currentSubmission") is not None
        or approved_document.get("activation") is not None
        or (latest.get("review") or {}).get("result") != "approved"
        or (latest.get("review") or {}).get("reviewedStateCommit") != reviewed_state
        or (latest.get("ledger") or {}).get("path") != review_relative
        or (latest.get("ledger") or {}).get("sha256") != review_reference.get("sha256")
    ):
        errors.append("GCR-0007 approved-state Git blob does not reproduce the approved review")
    live_path = repo / state_relative
    try:
        live_payload = live_path.read_bytes()
        live_state = json.loads(live_payload)
    except OSError, UnicodeError, json.JSONDecodeError:
        return [*errors, "GCR-0007 live state is unreadable or malformed"]
    activation = live_state.get("activation") or {}
    evidence = activation.get("adoptionEvidence") or {}
    evidence_relative = str(evidence.get("path") or "")
    evidence_commit = str(evidence.get("commit") or "")
    try:
        evidence_path = safe_control_path(
            repo,
            evidence_relative,
            prefix="artifacts/evidence/governance-control-recovery",
            label="GCR-0007 adoption evidence",
        )
        evidence_payload = evidence_path.read_bytes()
        evidence_document = json.loads(evidence_payload)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"GCR-0007 cannot load adoption evidence: {exc}")
        evidence_payload = b""
        evidence_document = {}
    if (
        live_state.get("status") != "HEADROOM_ACTIVATION_FINALIZATION"
        or activation.get("approvedStateCommit") != approved_state
        or activation.get("predecessorRevision") != 11
        or activation.get("successorRevision") != 11
        or activation.get("supportedControlCeiling") != 12
        or activation.get("generationNeutral") is not True
        or activation.get("ordinaryExecutionAuthority") is not False
        or re.fullmatch(
            r"artifacts/evidence/governance-control-recovery/GCR-0007\.B00\.adoption(?:-R[0-9]{2})?\.json",
            evidence_relative,
        )
        is None
        or evidence_relative != expected_evidence_relative
        or hashlib.sha256(evidence_payload).hexdigest() != evidence.get("sha256")
        or not git_commit_exists(repo, evidence_commit)
        or not git_is_ancestor(repo, evidence_commit)
        or git_blob(repo, evidence_commit, evidence_relative) != evidence_payload
        or evidence_document.get("approvedStateCommit") != approved_state
        or evidence_document.get("controlRecoveryId") != "GCR-0007"
        or evidence_document.get("predecessorRevision") != 11
        or evidence_document.get("successorRevision") != 11
        or evidence_document.get("supportedControlCeiling") != 12
        or evidence_document.get("generationNeutral") is not True
        or "adoptionEvidenceCommit" in evidence_document
        or "finalizationCommit" in evidence_document
    ):
        errors.append("GCR-0007 live activation/evidence does not match the adopted generation")
    if git_commit_parents(repo, evidence_commit) != [approved_state] or git_name_status_delta(
        repo, approved_state, evidence_commit
    ) != {evidence_relative: "A"}:
        errors.append("GCR-0007 adoption evidence is not the exact direct child of its approved state")
    matches = [
        commit
        for commit in git_commits_changing_path_after(repo, evidence_commit, state_relative)
        if git_blob(repo, commit, state_relative) == live_payload
    ]
    if len(matches) != 1:
        errors.append("GCR-0007 adoption finalization commit is absent or not unique")
    else:
        finalization = matches[0]
        if git_commit_parents(repo, finalization) != [evidence_commit] or git_name_status_delta(
            repo, evidence_commit, finalization
        ) != {"planning/backlog.yaml": "M", state_relative: "M"}:
            errors.append("GCR-0007 adoption finalization is not the exact direct-child two-path transition")
        final_backlog_payload = git_blob(repo, finalization, "planning/backlog.yaml")
        try:
            final_backlog = yaml.safe_load((final_backlog_payload or b"").decode("utf-8"))
        except UnicodeError, yaml.YAMLError:
            final_backlog = {}
        final_control = (final_backlog or {}).get("control_plane") or {}
        final_generations = final_control.get("control_generations") or []
        if (
            final_control.get("revision") != 11
            or final_control.get("minimum_tool_revision") != 11
            or len(final_generations) != 4
            or final_generations[-1] != generation
            or [item.get("id") for item in final_generations[:3]] != ["GCR-0001", "GCR-0002", "GCR-0003"]
        ):
            errors.append("GCR-0007 finalization does not freeze the exact neutral generation ledger")
    return errors


def wave_authority_errors(data: dict[str, Any], repo: Path | None) -> list[str]:
    errors: list[str] = []
    control = data.get("control_plane")
    bases = data.get("wave_approval_bases", [])
    amendments = data.get("wave_amendments", [])
    if control is None and not bases and not amendments:
        return errors
    if not isinstance(control, dict) or control.get("revision") not in set(range(4, CONTROL_TOOL_REVISION + 1)):
        errors.append("control plane revision is missing or unsupported")
    elif int(control.get("minimum_tool_revision", 0)) > CONTROL_TOOL_REVISION:
        errors.append("this taskctl revision is too old for the active control plane")
    elif int(control.get("minimum_tool_revision", 0)) != int(control.get("revision", 0)):
        errors.append("control plane revision and minimum tool revision differ")
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
    for amendment in amendments:
        if "correction" in amendment and (amendment.get("lifecycle") or {}).get("status") == "ADOPTED":
            from planctl import _paused_predecessor_errors

            binding = amendment["correction"]
            parent = wave_amendment_map(serializable_backlog(data)).get(str(binding.get("id")))
            errors.extend(
                _paused_predecessor_errors(repo, binding, str(amendment.get("id")), returned_parent=parent or {})
            )
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
        try:
            record_path = safe_control_path(
                repo,
                str(amendment["approval_reference"]["path"]),
                prefix="planning/wave-amendment-approvals",
                label="Wave amendment approval",
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except OSError, ValueError, json.JSONDecodeError:
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
        packet = record.get("packet") or {}
        if packet.get("path") and packet.get("sha256"):
            packet_path = repo.joinpath(*PurePosixPath(str(packet.get("path") or "")).parts)
            try:
                packet_payload = packet_path.read_bytes()
                packet_document = json.loads(packet_payload)
            except OSError, json.JSONDecodeError:
                errors.append(f"{amendment['id']}: approved packet is unreadable")
                continue
            if hashlib.sha256(packet_payload).hexdigest() != packet.get("sha256"):
                errors.append(f"{amendment['id']}: approved packet hash mismatch")
            committed_packet = git_blob(repo, str(packet.get("commit")), str(packet.get("path")))
            if committed_packet != packet_payload:
                errors.append(f"{amendment['id']}: approved packet differs from its immutable Git blob")
            task_ids = [str(item.get("id")) for item in packet_document.get("taskInventory", [])]
            if task_ids != record.get("authorizedTaskIds"):
                errors.append(f"{amendment['id']}: approved task inventory mismatch")
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
    allowed_untracked: set[str] | None = None,
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
        base_sha = expected_base_commit or task.get("base_sha")
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
        allowed.update(allowed_untracked or set())
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
    allowed_untracked: set[str] | None = None,
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
        allowed_untracked=allowed_untracked,
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
                attempts = (task.get("review_control") or {}).get("attempts") or []
                first_submission = (attempts[0].get("submission") or {}) if attempts else {}
                if first_submission:
                    expected_base_commit = first_submission.get("base_commit")
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


def wave_resume_record_errors(
    data: dict[str, Any],
    wave_id: str,
    campaign: dict[str, Any],
    repo: Path | None,
) -> list[str]:
    """Validate durable PAUSED-to-ACTIVE resume authority without self-reference."""
    errors: list[str] = []
    records = campaign.get("resume_records", [])
    if not isinstance(records, list):
        return [f"{wave_id}: Wave resume history is malformed"]
    control_revision = int((data.get("control_plane") or {}).get("revision", 0))
    if wave_id == "W1" and control_revision >= 6 and campaign.get("status") == "ACTIVE" and not records:
        errors.append(f"{wave_id}: revision-6 resumed Wave campaign lacks its durable resume record")
    expected_ids = [f"{wave_id}.R{index:02d}" for index in range(1, len(records) + 1)]
    actual_ids = [str(record.get("id")) if isinstance(record, dict) else "<malformed>" for record in records]
    if actual_ids != expected_ids:
        errors.append(f"{wave_id}: Wave resume record IDs are duplicated, gapped, reordered, or cross-Wave")
    commits: list[str] = []
    previous_time: dt.datetime | None = None
    for record in records:
        if not isinstance(record, dict):
            errors.append(f"{wave_id}: Wave resume record is malformed")
            continue
        record_id = str(record.get("id") or "<unknown>")
        if record.get("wave_id") != wave_id:
            errors.append(f"{record_id}: Wave resume record is cross-Wave")
        if (
            record.get("control_revision") not in range(RECOVERY_BASE_REVISION, CONTROL_TOOL_REVISION + 1)
            or record.get("prior_status") != "PAUSED"
        ):
            errors.append(f"{record_id}: Wave resume record control or prior-state boundary is invalid")
        actor = str(record.get("actor") or "")
        if not actor or actor != actor.strip():
            errors.append(f"{record_id}: Wave resume actor identity is not normalized")
        commit = str(record.get("pre_resume_commit") or "")
        commits.append(commit)
        try:
            resumed_at = parse_time(str(record.get("resumed_at") or ""))
        except ValueError:
            resumed_at = None
            errors.append(f"{record_id}: Wave resume timestamp is invalid")
        if resumed_at is not None and previous_time is not None and resumed_at < previous_time:
            errors.append(f"{record_id}: Wave resume timestamps are stale or reordered")
        if resumed_at is not None:
            previous_time = resumed_at
        if repo is None:
            continue
        if not git_commit_exists(repo, commit) or not git_is_ancestor(repo, commit):
            errors.append(f"{record_id}: pre-resume commit is missing or non-ancestral")
            continue
        historical = historical_backlog_document(repo, commit)
        historical_revision = int(((historical or {}).get("control_plane") or {}).get("revision", 0))
        if historical_revision != record.get("control_revision"):
            errors.append(f"{record_id}: control revision differs from the bound PAUSED campaign")
        historical_wave = next(
            (item for item in (historical or {}).get("waves", []) if item.get("id") == wave_id),
            None,
        )
        prior = (historical_wave or {}).get("campaign") or {}
        if prior.get("status") != "PAUSED":
            errors.append(f"{record_id}: pre-resume commit does not contain the bound PAUSED campaign")
            continue
        if canonical_json_sha256(prior) != record.get("prior_campaign_sha256"):
            errors.append(f"{record_id}: prior PAUSED campaign hash is stale or rewritten")
        for field in ("branch", "profile", "platform"):
            if record.get(field) != prior.get(field):
                errors.append(f"{record_id}: {field} differs from the bound PAUSED campaign")
        try:
            if Path(str(record.get("worktree") or "")).resolve() != Path(str(prior.get("worktree") or "")).resolve():
                errors.append(f"{record_id}: worktree differs from the bound PAUSED campaign")
        except OSError:
            errors.append(f"{record_id}: worktree cannot be resolved")
        if record.get("actor") != prior.get("owner"):
            errors.append(f"{record_id}: actor differs from the bound PAUSED campaign owner")
        try:
            if resumed_at is not None and resumed_at < parse_time(str(prior.get("updated_at") or "")):
                errors.append(f"{record_id}: resume timestamp predates the PAUSED campaign boundary")
        except ValueError:
            errors.append(f"{record_id}: bound PAUSED campaign timestamp is invalid")
    if len(commits) != len(set(commits)):
        errors.append(f"{wave_id}: duplicate pre-resume commit exists in Wave resume history")
    if records and isinstance(records[-1], dict):
        latest = records[-1]
        projection = {
            "base_sha": latest.get("pre_resume_commit"),
            "branch": latest.get("branch"),
            "worktree": latest.get("worktree"),
            "profile": latest.get("profile"),
            "platform": latest.get("platform"),
            "owner": latest.get("actor"),
        }
        current = {field: campaign.get(field) for field in projection}
        if current != projection:
            errors.append(f"{wave_id}: latest Wave resume record is stale or has the wrong campaign identity")
        try:
            if parse_time(str(latest.get("resumed_at") or "")) > parse_time(str(campaign.get("updated_at") or "")):
                errors.append(f"{wave_id}: latest Wave resume record postdates the campaign projection")
        except ValueError:
            pass
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
    errors.extend(recovery_hold_errors(data, repo))
    if repo is not None:
        errors.extend(evidence_reference_errors(tasks, repo))
    for task in tasks.values():
        errors.extend(task_review_control_errors(task, repo))
        if repo is not None:
            errors.extend(task_recovery_projection_errors(data, task, repo))
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
            errors.extend(wave_resume_record_errors(data, wave_id, campaign, repo))
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
    ordered_amendments: dict[str, list[dict[str, Any]]] = {}
    executable_hold_states = {"MATERIALIZED", "ACTIVE", "PAUSED", "REVIEW", "BLOCKED"}
    try:
        relations = project_paused_corrections(serializable_backlog(data).get("wave_amendments", []))
    except KernelValidationError as exc:
        errors.append(f"Invalid paused amendment correction: {exc}")
        relations = []
    suspended_parents = {relation["parentId"] for relation in relations if relation["phase"] == "executing"}
    owner_exceptions = {
        (relation["parentId"], relation["correctionId"])
        for relation in relations
        if relation["phase"] in {"pending-entry", "returned"}
    }
    hold_owners: dict[str, list[dict[str, Any]]] = {}
    for amendment in data.get("wave_amendments", []):
        target_wave = str(amendment.get("target_wave"))
        ordered_amendments.setdefault(target_wave, []).append(amendment)
        if (
            amendment.get("kind") != "migrated-replanning"
            and ((amendment.get("lifecycle") or {}).get("status")) in executable_hold_states
            and amendment.get("id") not in suspended_parents
        ):
            hold_owners.setdefault(target_wave, []).append(amendment)
    for wave_id, ordered in ordered_amendments.items():
        wave_campaign = (waves.get(wave_id) or {}).get("campaign") or {}
        owners = hold_owners.get(wave_id, [])
        if len(owners) > 1:
            errors.append(f"{wave_id}: more than one amendment owns the shared amendment-hold scope")
        if wave_campaign.get("scope") == "amendment-hold":
            if len(owners) != 1:
                errors.append(f"{wave_id}: amendment-hold scope requires exactly one executable amendment owner")
            else:
                owner = owners[0]
                owner_position = ordered.index(owner)
                if owner_position != len(ordered) - 1 and not (
                    owner_position == len(ordered) - 2
                    and (str(owner.get("id")), str(ordered[-1].get("id"))) in owner_exceptions
                ):
                    errors.append(f"{wave_id}: amendment-hold owner is not the latest consecutive amendment")
                for predecessor in ordered[:owner_position]:
                    if (
                        predecessor.get("kind") != "migrated-replanning"
                        and ((predecessor.get("lifecycle") or {}).get("status")) != "ADOPTED"
                        and not is_unexecuted_superseded_reservation(predecessor)
                        and not (
                            predecessor.get("id") in suspended_parents
                            and (owner.get("correction") or {}).get("id") == predecessor.get("id")
                        )
                    ):
                        errors.append(
                            f"{predecessor.get('id')}: predecessor of the amendment-hold owner is neither ADOPTED "
                            "nor an unexecuted migration-superseded reservation"
                        )
        elif owners:
            errors.append(f"{wave_id}: executable amendment owner requires the shared amendment-hold scope")
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
        if (
            amendment.get("kind") == "gate-integrity-safety-defect"
            and lifecycle.get("status") != "SUPERSEDED"
            and bootstrap.get("id") != f"{amendment_id}.B00"
        ):
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
                later_owner = False
                owners = hold_owners.get(target_wave, [])
                ordered = ordered_amendments.get(target_wave, [])
                valid_hold_predecessor = lifecycle.get("status") == "ADOPTED" or is_unexecuted_superseded_reservation(
                    amendment
                )
                if valid_hold_predecessor and len(owners) == 1 and amendment in ordered:
                    later_owner = ordered.index(owners[0]) > ordered.index(amendment)
                returned_owner = any(
                    relation["correctionId"] == amendment_id
                    and relation["phase"] == "returned"
                    and relation["holdOwner"] == (owners[0].get("id") if len(owners) == 1 else None)
                    for relation in relations
                )
                if wave_campaign.get("scope") != "wave" and not later_owner and not returned_owner:
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
            adoption_checkpoints = amendment_adoption_checkpoints(
                waves.get(target_wave) or {},
                amendment_id,
            )
            if not adoption_checkpoints:
                errors.append(f"{amendment_id}: adopted amendment lacks a bound security checkpoint")
            else:
                for reference in adoption_checkpoints[-1].get("evidence", []):
                    if isinstance(reference, dict):
                        errors.extend(amendment_adoption_reference_errors(repo, reference, amendment))
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
    if program.get("state") == "RECOVERY_INTERRUPTED":
        print(recovery_stop_handoff(args, data, program))
        return
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
    if program.get("state") == "RECOVERY_INTERRUPTED":
        print(recovery_stop_handoff(args, data, program))
        return
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


def recovery_stop_handoff(args: argparse.Namespace, data: dict[str, Any], program: dict[str, Any]) -> str:
    hold = program.get("recovery_hold")
    if not isinstance(hold, dict):
        holds = active_recovery_holds(data)
        if not holds:
            raise SystemExit("Recovery handoff requested without an active hold")
        hold = holds[0]
    repo = Path(args.file).resolve().parent.parent
    request_id = str(hold.get("recovery_request_id"))
    wave_id = str(hold.get("target_wave"))
    bootstrap = hold.get("bootstrap") or {}
    post = hold.get("post_bootstrap") or {}
    packet_relative = str((hold.get("packet_reference") or {}).get("path") or "")
    proposal_relative = f"planning/governance-recovery-requests/{request_id}.md"
    review_relative = f"planning/governance-recovery-requests/{request_id}-review.html"
    approval_relative = str((hold.get("approval_reference") or {}).get("path") or "")
    wave_relative = f"planning/review-site/waves/{wave_id}.html"

    def linked(relative: str) -> str:
        return f"{(repo / relative).resolve().as_uri()} ({relative})" if relative else "unrecorded"

    status = str(bootstrap.get("status") or "UNKNOWN")
    if status == "IN_PROGRESS":
        next_step = (
            f"finish and commit only {bootstrap.get('id')} within the approved path boundary, then run "
            f"`python tools/recoveryctl.py --repo . bootstrap-submit {request_id} --agent <agent> "
            "--implementation-commit <HEAD> --evidence <criterion-manifest>`"
        )
    elif status == "REVIEW":
        next_step = (
            f"independently review frozen {bootstrap.get('id')} and run `python tools/recoveryctl.py --repo . "
            f"bootstrap-review {request_id} --reviewer <independent-reviewer> --from <finding-ledger>`"
        )
    elif status in {"CHANGES_REQUESTED", "BLOCKED"}:
        next_step = (
            f"commit a strict-descendant bounded remediation and run `python tools/recoveryctl.py --repo . "
            f"bootstrap-resubmit {request_id} --agent <agent> --implementation-commit <HEAD> "
            "--evidence <remediation-manifest>`"
        )
    else:
        next_step = (
            f"prepare and independently review {post.get('required_change_request_id')}/"
            f"{post.get('required_amendment_id')}; "
            "obtain a separate exact-commit human approval before any amendment bootstrap or task execution"
        )
    authority = ", ".join(
        f"{item.get('id')}={((item.get('approval_reference') or {}).get('introduction_commit') or 'unrecorded')}"
        for item in data.get("wave_amendments", [])
        if item.get("target_wave") == wave_id
    )
    return (
        f"STOPPED AT GOVERNANCE RECOVERY {request_id} ({hold.get('id')})\n"
        f"State: hold={hold.get('status')}; bootstrap={bootstrap.get('id')}={status}; target Wave={wave_id}.\n"
        "Ordinary Wave/task/amendment/gate mutation is NOT LEGAL while this hold remains active. "
        f"The GRR grants no execution authority to {post.get('required_amendment_id')} or its proposed tasks.\n"
        f"Authority: base={(wave_approval_base_map(data).get(wave_id) or {}).get('packet_commit')}; "
        f"ordered amendments: {authority or 'none'}.\n"
        "Review materials:\n"
        f"  - Frozen recovery packet: {linked(packet_relative)}\n"
        f"  - Canonical recovery proposal: {linked(proposal_relative)}\n"
        f"  - Human review: {linked(review_relative)}\n"
        f"  - Immutable approval: {linked(approval_relative)}\n"
        f"  - Paused Wave packet: {linked(wave_relative)}\n"
        "Decision alternatives:\n"
        "  A (recommended): complete the bounded bootstrap review, then use a separately approved "
        "ordinary ECR/amendment.\n"
        "  B: leave the recovery and Wave paused indefinitely without executing either lane.\n"
        "  C: record an append-only withdrawn/deferred safe-resume disposition when the controller "
        "supports it; never bypass the hold.\n"
        "Release condition: independently approve the recovery bootstrap; separately approve, execute, "
        "independently exit-review, "
        f"and adopt {post.get('required_amendment_id')} with a bound control/security checkpoint; "
        "then explicitly release the "
        f"hold and resume {wave_id}.\n"
        f"Exact next action: {next_step}"
    )


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
    program = global_program_position(data, slices, tasks, gates)
    if program.get("state") == "RECOVERY_INTERRUPTED":
        print(recovery_stop_handoff(args, data, program))
        return
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
        program = global_program_position(data, slices, tasks, gates)
        wave = wave_map(data).get(str(program.get("current_wave") or "")) or {}
        campaign = wave.get("campaign") or {}
        if program.get("state") == "ACTIVE_WAVE" and campaign.get("status") == "PAUSED":
            print(
                f"WAVE PAUSED AND READY TO RESUME: {wave['id']}. Commit any completed control migration, then run "
                f"`python tools/taskctl.py --file planning/backlog.yaml wave resume {wave['id']} --agent <agent> "
                "--branch <codex-branch> --base-sha <HEAD> --worktree <absolute-repository-path> "
                f"--profile {campaign.get('profile') or args.profile} "
                f"--platform {campaign.get('platform') or args.platform}`."
            )
            return
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
    approval_relative = f"planning/wave-amendment-approvals/{amendment_id}.json"
    try:
        approval_path = safe_control_path(
            repo,
            approval_relative,
            prefix="planning/wave-amendment-approvals",
            label="Immutable amendment approval",
        )
        approval_payload = approval_path.read_bytes()
        approval = json.loads(approval_payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load immutable approval for {amendment_id}: {exc}") from exc
    if approval.get("status") != "APPROVED" or approval.get("amendmentId") != amendment_id:
        raise SystemExit(f"{amendment_id} does not have an exact APPROVED amendment record")
    packet_info = approval.get("packet") or {}
    packet_relative = str(packet_info.get("path") or "")
    try:
        packet_path = safe_control_path(
            repo,
            packet_relative,
            prefix="planning/enabler-change-requests",
            label="Approved amendment packet",
        )
        packet_payload = packet_path.read_bytes()
        packet = json.loads(packet_payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
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


def wave_resume_allowed_untracked(data: dict[str, Any], wave_id: str, repo: Path) -> set[str]:
    """Authenticate the one retained historic witness required by released W1 recovery history."""
    if wave_id != "W1":
        return set()
    superseded = next(
        (
            amendment
            for amendment in data.get("wave_amendments", [])
            if amendment.get("id") == "W1.A04" and (amendment.get("lifecycle") or {}).get("status") == "SUPERSEDED"
        ),
        None,
    )
    if superseded is not None:
        # The canonical authority checks authenticate the exact W1.A04 approval
        # and GOV-MIG-0001 supersession. The retained untracked witness is no
        # longer live mutation authority and must not be opened merely to admit
        # a later, independently approved amendment transition.
        return {HISTORICAL_W1_A04_WITNESS["path"]}
    control = data.get("control_plane") or {}
    holds = control.get("recovery_holds") or []
    hold: dict[str, Any] = next((item for item in holds if item.get("id") == "HOLD-W1-GRR-0002"), {})
    if (
        int(control.get("revision") or 0) < 11
        or int(control.get("minimum_tool_revision") or 0) < 11
        or hold.get("recovery_request_id") != "GRR-0002"
        or hold.get("target_wave") != "W1"
        or hold.get("status") != "RELEASED"
    ):
        return set()
    relative = HISTORICAL_W1_A04_WITNESS["path"]
    try:
        witness_path = safe_control_path(
            repo,
            relative,
            prefix="artifacts/evidence",
            label="Historical W1.A04 recovery witness",
        )
        payload = witness_path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Historical W1.A04 recovery witness is unavailable or invalid: {exc}") from exc
    if (
        hashlib.sha256(payload).hexdigest() != HISTORICAL_W1_A04_WITNESS["sha256"]
        or document.get("schemaVersion") != "1.0"
        or document.get("documentType") != "task-criterion-evidence"
        or document.get("taskId") != HISTORICAL_W1_A04_WITNESS["task_id"]
        or document.get("commit") != HISTORICAL_W1_A04_WITNESS["commit"]
    ):
        raise SystemExit("Historical W1.A04 recovery witness bytes or authority identity are not exact")
    return {relative}


def task_evidence_allowed_untracked(
    data: dict[str, Any],
    task: dict[str, Any],
    repo: Path,
) -> set[str]:
    """Admit the exact retained witness while freezing W1 task evidence."""
    wave_id = task_wave(task)
    if wave_id != "W1":
        return set()
    return wave_resume_allowed_untracked(data, wave_id, repo)


def amendment_transition_allowed_untracked(data: dict[str, Any], amendment_id: str, repo: Path) -> set[str]:
    amendment = wave_amendment_map(data).get(amendment_id) or {}
    wave_id = str(amendment.get("target_wave") or "")
    return wave_resume_allowed_untracked(data, wave_id, repo) if wave_id else set()


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
    path = Path(value).resolve(strict=False)
    try:
        relative = path.relative_to(repo).as_posix()
    except ValueError as exc:
        raise SystemExit(f"{label} must be inside the repository") from exc
    try:
        safe = safe_control_path(
            repo,
            relative,
            prefix="artifacts/evidence",
            label=label,
            require_exists=False,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return relative, safe


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
    expected_document_type = {
        "amendment-exit-evidence": "wave-amendment-exit-evidence",
        "amendment-adoption-evidence": "wave-amendment-adoption-evidence",
    }.get(expected_type)
    if expected_document_type is None or manifest.get("documentType") != expected_document_type:
        errors.append(f"{label}: bound evidence payload documentType does not match its reference type")
    return errors


def amendment_adoption_reference_errors(
    repo: Path,
    reference: dict[str, Any],
    amendment: dict[str, Any],
) -> list[str]:
    amendment_id = str(amendment.get("id"))
    errors = bound_evidence_reference_errors(
        repo,
        reference,
        expected_type="amendment-adoption-evidence",
        expected_amendment=amendment_id,
        label=f"{amendment_id}/adoption",
    )
    payload = git_blob(repo, str(reference.get("commit") or ""), str(reference.get("path") or ""))
    if payload is None:
        return errors
    try:
        manifest = parse_evidence_payload(payload, PurePosixPath(str(reference.get("path") or "")).suffix)
    except UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError:
        return errors
    if manifest.get("targetWave") != amendment.get("target_wave"):
        errors.append(f"{amendment_id}: adoption evidence target Wave mismatch")
    if manifest.get("correctionReturn") != amendment.get("correction") or (
        "correctionReturn" in manifest and "correction" not in amendment
    ):
        errors.append(f"{amendment_id}: adoption evidence does not bind the exact correction return")
    completion = amendment.get("completion") or {}
    attempts = (completion.get("exit_review_control") or {}).get("attempts") or []
    if not attempts:
        return [*errors, f"{amendment_id}: adoption evidence lacks immutable exit review history"]
    latest_attempt = attempts[-1]
    latest_submission = latest_attempt.get("submission") or {}
    latest_review = latest_attempt.get("review") or {}
    reviewed_completion = str(manifest.get("reviewedCompletionCommit") or "")
    reference_commit = str(reference.get("commit") or "")
    if manifest.get("candidateCommit") != reviewed_completion:
        errors.append(f"{amendment_id}: adoption evidence candidate differs from reviewed completion")
    if manifest.get("branch") != latest_submission.get("branch"):
        errors.append(f"{amendment_id}: adoption evidence branch differs from the approved exit submission")
    if not git_commit_exists(repo, reviewed_completion) or not git_is_ancestor(
        repo, reviewed_completion, reference_commit
    ):
        errors.append(f"{amendment_id}: adoption evidence reviewed completion is outside checkpoint history")
    else:
        historical = historical_amendment_completion(repo, reviewed_completion, amendment_id) or {}
        historical_attempts = (historical.get("exit_review_control") or {}).get("attempts") or []
        if (
            not historical_attempts
            or historical_attempts[-1] != latest_attempt
            or (historical_attempts[-1].get("review") or {}).get("result") != "approved"
            or latest_review.get("result") != "approved"
        ):
            errors.append(f"{amendment_id}: adoption evidence does not bind the exact approved exit history")
    return errors


def amendment_adoption_checkpoints(wave: dict[str, Any], amendment_id: str) -> list[dict[str, Any]]:
    return [
        checkpoint
        for checkpoint in wave.get("checkpoints", [])
        if checkpoint.get("kind") == "security"
        and any(
            isinstance(reference, dict)
            and reference.get("type") == "amendment-adoption-evidence"
            and reference.get("amendment_id") == amendment_id
            for reference in checkpoint.get("evidence", [])
        )
    ]


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


def historical_backlog_document(repo: Path, commit: str) -> dict[str, Any] | None:
    payload = git_blob(repo, commit, "planning/backlog.yaml")
    if payload is None:
        return None
    try:
        document = yaml.safe_load(payload.decode("utf-8"))
    except UnicodeError, yaml.YAMLError:
        return None
    return document if isinstance(document, dict) else None


def task_recovery_boundary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        field: copy.deepcopy(value)
        for field, value in task.items()
        if field != "recovery_control" and not field.startswith("_")
    }


def task_recovery_contract(task: dict[str, Any]) -> dict[str, Any]:
    return {field: copy.deepcopy(task.get(field)) for field in TASK_RECOVERY_CONTRACT_FIELDS}


def historical_task(repo: Path, commit: str, task_id: str) -> dict[str, Any] | None:
    document = historical_backlog_document(repo, commit)
    if document is None:
        return None
    try:
        return copy.deepcopy(index_backlog(document)[3].get(task_id))
    except KeyError, TypeError, SystemExit:
        return None


def exact_recovery_selected_checks() -> list[dict[str, Any]]:
    base = EXACT_T03_RECOVERY["base"]
    candidate = EXACT_T03_RECOVERY["candidate"]
    return [
        {
            "id": "cumulative-ui-gate",
            "command": (
                f".venv\\Scripts\\python.exe tools\\ui_change_gate.py --repo . --base {base} --head {candidate}"
            ),
            "exitCode": 0,
        },
        {
            "id": "privacy-controls-and-contract",
            "command": (
                ".venv\\Scripts\\python.exe -m unittest -v "
                "tests.security.test_privacy_controls tests.contracts.test_privacy_policy_contract"
            ),
            "exitCode": 0,
        },
    ]


def git_parent(repo: Path, commit: str) -> str | None:
    result = subprocess.run(["git", "rev-parse", f"{commit}^"], cwd=repo, capture_output=True, text=True, check=False)
    parent = result.stdout.strip()
    return parent if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", parent) else None


def git_changed_paths(repo: Path, base: str, candidate: str) -> list[str] | None:
    result = subprocess.run(
        ["git", "diff", "--name-only", base, candidate, "--"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted(result.stdout.splitlines()) if result.returncode == 0 else None


def exact_recovery_manifest_errors(
    data: dict[str, Any],
    task: dict[str, Any],
    manifest: dict[str, Any],
    repo: Path,
    *,
    require_current_candidate_bytes: bool,
) -> list[str]:
    errors: list[str] = []
    schema_path = repo / EXACT_T03_RECOVERY["manifest_schema"]
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(manifest)
    except (OSError, json.JSONDecodeError, SchemaError, ValidationError) as exc:
        return [f"invalid exact task-recovery manifest: {exc}"]

    expected_header = {
        "schemaVersion": "1.0",
        "documentType": "exact-historical-task-recovery",
        "taskId": EXACT_T03_RECOVERY["task_id"],
        "branch": EXACT_T03_RECOVERY["branch"],
    }
    for field, expected_header_value in expected_header.items():
        if manifest.get(field) != expected_header_value:
            errors.append(f"exact recovery manifest {field} mismatch")

    authority = manifest.get("authority") or {}
    amendment = wave_amendment_map(data).get(EXACT_T03_RECOVERY["amendment_id"]) or {}
    approval_reference = amendment.get("approval_reference") or {}
    expected_authority = {
        "waveId": EXACT_T03_RECOVERY["wave_id"],
        "amendmentId": EXACT_T03_RECOVERY["amendment_id"],
        "holdId": EXACT_T03_RECOVERY["hold_id"],
        "approvalPath": approval_reference.get("path"),
        "approvalSha256": approval_reference.get("sha256"),
        "approvalIntroductionCommit": approval_reference.get("introduction_commit"),
    }
    for field, expected_authority_value in expected_authority.items():
        if authority.get(field) != expected_authority_value:
            errors.append(f"recovery authority {field} mismatch")
    try:
        approval, _packet, approval_payload = load_amendment_authority(repo, EXACT_T03_RECOVERY["amendment_id"])
    except SystemExit as exc:
        errors.append(str(exc))
        approval = {}
        approval_payload = b""
    packet_reference = approval.get("packet") or {}
    for field, expected_packet_value in (
        ("packetCommit", packet_reference.get("commit")),
        ("packetPath", packet_reference.get("path")),
        ("packetSha256", packet_reference.get("sha256")),
    ):
        if authority.get(field) != expected_packet_value:
            errors.append(f"recovery authority {field} mismatch")
    if approval_payload and hashlib.sha256(approval_payload).hexdigest() != authority.get("approvalSha256"):
        errors.append("recovery authority approval bytes mismatch")
    if approval.get("approvedBy") == task.get("owner"):
        errors.append("recovery authority is self-approved by the task owner")

    commits = manifest.get("commits") or {}
    expected_commits = {
        "base": EXACT_T03_RECOVERY["base"],
        "foundation": EXACT_T03_RECOVERY["foundation"],
        "candidate": EXACT_T03_RECOVERY["candidate"],
        "blockRecord": EXACT_T03_RECOVERY["block_record"],
        "pauseRecord": EXACT_T03_RECOVERY["pause_record"],
    }
    if commits != expected_commits:
        errors.append("exact recovery manifest commit boundary mismatch")
    ordered: list[str] = [
        str(commits.get("base") or ""),
        str(commits.get("foundation") or ""),
        str(commits.get("candidate") or ""),
        str(commits.get("blockRecord") or ""),
        str(commits.get("pauseRecord") or ""),
    ]
    if not all(isinstance(commit, str) and git_commit_exists(repo, commit) for commit in ordered):
        errors.append("one or more exact recovery commits do not exist")
    else:
        for ancestor, descendant in pairwise(ordered):
            if ancestor == descendant or not git_is_ancestor(repo, ancestor, descendant):
                errors.append("exact recovery commit lineage is not strictly ancestral")
                break
        if git_parent(repo, str(commits.get("blockRecord"))) != commits.get("candidate"):
            errors.append("T03 block record is not the direct child of the exact product candidate")
        if git_parent(repo, str(commits.get("pauseRecord"))) != commits.get("blockRecord"):
            errors.append("W1 pause record is not the direct child of the exact T03 block record")
        if not git_is_ancestor(repo, str(commits.get("pauseRecord"))):
            errors.append("exact T03 pause record is not on current Git history")

    block_task = historical_task(repo, str(commits.get("blockRecord")), EXACT_T03_RECOVERY["task_id"])
    pause_task = historical_task(repo, str(commits.get("pauseRecord")), EXACT_T03_RECOVERY["task_id"])
    task_hashes = manifest.get("historicalTaskSha256") or {}
    if block_task is None or canonical_json_sha256(task_recovery_boundary(block_task)) != task_hashes.get(
        "blockRecord"
    ):
        errors.append("exact T03 block-record task boundary hash mismatch")
    if pause_task is None or canonical_json_sha256(task_recovery_boundary(pause_task)) != task_hashes.get(
        "pauseRecord"
    ):
        errors.append("exact T03 pause-record task boundary hash mismatch")
    if (
        block_task is not None
        and pause_task is not None
        and task_recovery_boundary(block_task) != task_recovery_boundary(pause_task)
    ):
        errors.append("T03 task boundary changed between block and Wave pause records")
    if pause_task is not None and task_recovery_contract(task) != task_recovery_contract(pause_task):
        errors.append("current T03 immutable task contract differs from the exact pause record")

    declared_paths = manifest.get("changedPaths") or []
    actual_paths = git_changed_paths(repo, str(commits.get("base")), str(commits.get("candidate")))
    if declared_paths != sorted(declared_paths) or len(declared_paths) != len(set(declared_paths)):
        errors.append("exact recovery changedPaths must be sorted and unique")
    if actual_paths is None or declared_paths != actual_paths:
        errors.append("exact recovery changedPaths differ from Git")

    ui = manifest.get("uiEvidence") or {}
    ui_path = str(ui.get("path") or "")
    try:
        current_ui_path = safe_control_path(
            repo,
            ui_path,
            prefix="artifacts/evidence/ui-change",
            label="T03 UI evidence contract",
        )
        current_ui_payload = current_ui_path.read_bytes()
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        current_ui_payload = b""
    candidate_ui_payload = git_blob(repo, str(commits.get("candidate")), ui_path)
    if candidate_ui_payload is None or evidence_sha256(candidate_ui_payload) != ui.get("sha256"):
        errors.append("T03 UI evidence contract hash differs from the exact candidate")
    if current_ui_payload and current_ui_payload != candidate_ui_payload:
        errors.append("T03 UI evidence contract bytes changed after the exact candidate")
    try:
        ui_contract = json.loads((candidate_ui_payload or b"").decode("utf-8"))
    except UnicodeError, json.JSONDecodeError:
        ui_contract = {}
        errors.append("T03 UI evidence contract is not valid JSON")
    reference = ui_contract.get("reference") or {}
    experience = task.get("experience_change") or {}
    for manifest_field, contract_field, experience_field in (
        ("referenceId", "referenceId", "reference_id"),
        ("referenceVersion", "version", "reference_version"),
        ("packageSha256", "packageSha256", "reference_package_sha256"),
        ("approvalCommit", "approvalCommit", "reference_approval_commit"),
        ("previousReferenceId", "previousReferenceId", "previous_reference_id"),
    ):
        if ui.get(manifest_field) != reference.get(contract_field) or ui.get(manifest_field) != experience.get(
            experience_field
        ):
            errors.append(f"T03 approved reference {manifest_field} mismatch")
    if ui_contract.get("taskId") != task.get("id") or experience.get("contract_path") != ui_path:
        errors.append("T03 UI evidence task/path binding mismatch")

    checks = manifest.get("selectedChecks") or []
    ids = [item.get("id") for item in checks if isinstance(item, dict)]
    commands = [item.get("command") for item in checks if isinstance(item, dict)]
    if len(ids) != len(set(ids)) or len(commands) != len(set(commands)):
        errors.append("exact recovery selected checks must have unique IDs and commands")
    if checks != exact_recovery_selected_checks():
        errors.append("exact recovery selected checks differ from the approved executable inventory")
    if manifest.get("unverifiedItems") != []:
        errors.append("exact recovery manifest must contain zero unverified items")

    if require_current_candidate_bytes and actual_paths is not None:
        protected_candidate_paths = [
            path
            for path in actual_paths
            if path.startswith(("apps/desktop/", "services/core-api/", "packages/contracts/"))
            or path
            in {
                "artifacts/evidence/ui-change/CAP-02.S04.T03.json",
                "docs/adr/ADR-0019-enforce-project-privacy-through-append-only-local-policy.md",
                "docs/architecture/privacy-controls.md",
                "tests/contracts/test_privacy_policy_contract.py",
                "tests/security/test_privacy_controls.py",
            }
        ]
        for path in protected_candidate_paths:
            if git_blob(repo, str(commits.get("candidate")), path) != git_blob(repo, "HEAD", path):
                errors.append(f"protected T03 candidate bytes changed after implementation: {path}")
                break
    return errors


def exact_t03_resume_commit_errors(
    data: dict[str, Any],
    wave: dict[str, Any],
    repo: Path,
    current_head: str,
) -> list[str]:
    """Bind T03 recovery to the committed result of one exact Wave resume."""
    campaign = wave.get("campaign") or {}
    errors = wave_resume_record_errors(data, str(wave.get("id") or ""), campaign, repo)
    records = campaign.get("resume_records") or []
    if not records or not isinstance(records[-1], dict):
        return [*errors, "Exact T03 recovery requires a durable Wave resume record"]
    resume = records[-1]
    pre_resume = str(resume.get("pre_resume_commit") or "")
    if pre_resume == current_head:
        errors.append("Exact T03 recovery current HEAD must contain the committed resume transition")
    if git_commit_parents(repo, current_head) != [pre_resume]:
        errors.append("Exact T03 recovery HEAD is not the direct child of the recorded pre-resume commit")
    delta = git_name_status_delta(repo, pre_resume, current_head)
    if delta != EXACT_T03_RESUME_COMMIT_PATHS:
        errors.append("Exact T03 recovery resume commit must modify only the five generated Wave-resume paths")
    if campaign.get("base_sha") != pre_resume:
        errors.append("Exact T03 recovery campaign base differs from the durable pre-resume authority")
    return errors


def run_exact_recovery_checks(repo: Path) -> list[str]:
    commands = [
        [
            sys.executable,
            str(repo / "tools" / "ui_change_gate.py"),
            "--repo",
            str(repo),
            "--base",
            EXACT_T03_RECOVERY["base"],
            "--head",
            EXACT_T03_RECOVERY["candidate"],
        ],
        [
            sys.executable,
            "-m",
            "unittest",
            "-v",
            "tests.security.test_privacy_controls",
            "tests.contracts.test_privacy_policy_contract",
        ],
    ]
    errors: list[str] = []
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip())
            errors.append(f"recomputed recovery check {index + 1} failed" + (f": {detail}" if detail else ""))
    return errors


def task_recovery_projection_errors(data: dict[str, Any], task: dict[str, Any], repo: Path) -> list[str]:
    recovery = task.get("recovery_control")
    if recovery is None:
        return []
    task_id = str(task.get("id") or "")
    if task_id != EXACT_T03_RECOVERY["task_id"]:
        return [f"{task_id}: task recovery projection is outside the exact authorized task"]
    errors: list[str] = []
    manifest_reference = recovery.get("manifest") or {}
    relative = str(manifest_reference.get("path") or "")
    try:
        path = safe_control_path(
            repo,
            relative,
            prefix="artifacts/evidence/task-recovery",
            label="Task recovery manifest",
        )
        payload = path.read_bytes()
        manifest = json.loads(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"{task_id}: invalid task recovery manifest: {exc}"]
    if evidence_sha256(payload) != manifest_reference.get("sha256"):
        errors.append(f"{task_id}: task recovery manifest hash mismatch")
    errors.extend(
        f"{task_id}: {error}"
        for error in exact_recovery_manifest_errors(
            data,
            task,
            manifest,
            repo,
            require_current_candidate_bytes=False,
        )
    )
    historical = recovery.get("historical") or {}
    expected_historical = {
        "base": EXACT_T03_RECOVERY["base"],
        "foundation": EXACT_T03_RECOVERY["foundation"],
        "candidate": EXACT_T03_RECOVERY["candidate"],
        "block_record": EXACT_T03_RECOVERY["block_record"],
        "pause_record": EXACT_T03_RECOVERY["pause_record"],
        "block_task_sha256": (manifest.get("historicalTaskSha256") or {}).get("blockRecord"),
        "pause_task_sha256": (manifest.get("historicalTaskSha256") or {}).get("pauseRecord"),
    }
    if historical != expected_historical:
        errors.append(f"{task_id}: task recovery historical projection mismatch")
    pause_task = historical_task(repo, EXACT_T03_RECOVERY["pause_record"], task_id)
    if pause_task is None or recovery.get("original_blocked_state") != task_recovery_boundary(pause_task):
        errors.append(f"{task_id}: original blocked state is not the exact immutable pause boundary")
    authority = recovery.get("authority") or {}
    if (
        authority.get("amendment_id") != EXACT_T03_RECOVERY["amendment_id"]
        or authority.get("hold_id") != EXACT_T03_RECOVERY["hold_id"]
    ):
        errors.append(f"{task_id}: task recovery authority projection mismatch")
    new_base = str(recovery.get("new_base_sha") or "")
    if not git_commit_exists(repo, new_base) or not git_is_ancestor(repo, new_base):
        errors.append(f"{task_id}: task recovery execution base is not on current Git history")
    return errors


def historical_amendment_completion(repo: Path, commit: str, amendment_id: str) -> dict[str, Any] | None:
    document = historical_backlog_document(repo, commit)
    if document is None:
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
        reviewed_state = str(review.get("reviewed_state_commit") or "")
        strict_state = not (
            index == 1
            and review.get("result") == "changes-requested"
            and submission.get("declared_candidate_commit") != submission.get("candidate_commit")
        )
        validation_data = data
        validation_amendment = amendment
        historical_document: dict[str, Any] | None = None
        historical_amendment: dict[str, Any] | None = None
        if strict_state:
            historical_document = historical_backlog_document(repo, reviewed_state)
            if historical_document is not None:
                historical_amendment = next(
                    (item for item in historical_document.get("wave_amendments", []) if item.get("id") == amendment_id),
                    None,
                )
            if historical_amendment is None:
                errors.append(f"{amendment_id}: reviewed exit state lacks historical Wave/amendment state")
            else:
                assert historical_document is not None
                validation_data = historical_document
                validation_amendment = historical_amendment
        errors.extend(
            amendment_exit_submission_errors(
                validation_data,
                validation_amendment,
                approved_packet,
                submission,
                expected_id=f"R{index:02d}",
                expected_prior_id=prior_id,
                expected_prior_submission=prior_submission,
                expected_open_ids=expected_open,
                repo=repo,
                strict_state=strict_state and historical_amendment is not None,
            )
        )
        if not git_commit_exists(repo, reviewed_state) or not git_is_ancestor(repo, reviewed_state):
            errors.append(f"{amendment_id}: reviewed amendment exit state is absent from current history")
        elif not git_is_ancestor(repo, str(submission.get("candidate_commit") or ""), reviewed_state):
            errors.append(f"{amendment_id}: reviewed exit state does not descend from its candidate")
        else:
            historical = copy.deepcopy((historical_amendment or {}).get("completion")) or {}
            if not historical:
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
        if pattern.endswith("/**") or pattern.endswith("/*"):
            suffix_length = 3 if pattern.endswith("/**") else 2
            prefix = pattern[:-suffix_length].rstrip("/")
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


def exact_w1_a04_historic_submission_errors(
    repo: Path,
    data: dict[str, Any],
    hold: dict[str, Any],
    args: argparse.Namespace,
    approval: dict[str, Any],
    packet: dict[str, Any],
    approval_payload: bytes,
    *,
    approval_commit: str,
    implementation_commit: str,
    evidence_relative: str,
    evidence_payload: bytes,
) -> list[str]:
    """Authenticate the sole post-B02 historic W1.A04 bootstrap submission."""
    errors: list[str] = []
    control = data.get("control_plane") or {}
    expected_candidate = "214ac1aac53b4396ee29f7a935ddcac2a34618b6"
    expected_evidence = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
    expected_approval_commit = "4f92ba991fd19a2c0ae413b34416a2901d7f84b9"
    expected_approval_sha = "4c40aba122f87cd7a3ddc82a52fbefc089b40d6e894c991548954c73b19869ab"
    expected_packet = {
        "path": "planning/enabler-change-requests/ECR-0003.packet.json",
        "sha256": "3ed869e5c8e894c665b9972400d9fd20de458a302abbbc9aa52da7c8eb440687",
        "commit": "77896d26ddac0569e286fe8481c0676408c716b1",
    }
    expected_s02_packet = {
        "path": "planning/governance-recovery-requests/GRR-0002.S02.packet.json",
        "sha256": "14452cb6e6f3959996458d7b84df0105a7f6e4bbf3f4c5fc36e9d0f0506d43c8",
        "commit": "070f408ed257b3c1345a29c3be2c2f882952b856",
    }
    expected_s02_approval = {
        "path": "planning/governance-recovery-approvals/GRR-0002.S02.json",
        "sha256": "389d9f5595faf8a1a8de233783ac122e34d6b2d61c011cef58203764b6dfe7a1",
        "introduction_commit": "106921c269942401bab4cc4f732f4d1fb97b8abe",
    }
    packet_reference = approval.get("packet") or {}
    active_holds = active_recovery_holds(data)
    supplements = hold.get("supplements") or []
    supplement = supplements[-1] if supplements else {}
    bootstrap = supplement.get("bootstrap") or {}
    attempts = bootstrap.get("attempts") or []
    latest_attempt = attempts[-1] if attempts else {}
    if (
        args.amendment != "W1.A04"
        or approval_commit != expected_approval_commit
        or implementation_commit != expected_candidate
        or evidence_relative != "artifacts/evidence/W1.A04.B00.json"
        or hashlib.sha256(evidence_payload).hexdigest() != expected_evidence
        or hashlib.sha256(approval_payload).hexdigest() != expected_approval_sha
        or approval.get("amendmentId") != "W1.A04"
        or approval.get("changeRequestId") != "ECR-0003"
        or approval.get("targetWave") != "W1"
        or approval.get("status") != "APPROVED"
        or packet_reference.get("path") != expected_packet["path"]
        or packet_reference.get("sha256") != expected_packet["sha256"]
        or packet_reference.get("commit") != expected_packet["commit"]
        or packet.get("changeRequestId") != "ECR-0003"
        or packet.get("proposedAmendmentId") != "W1.A04"
        or (packet.get("bootstrapUnit") or {}).get("id") != "W1.A04.B00"
    ):
        errors.append("historic amendment, candidate, evidence, or ECR authority is not exact")
    if (
        control.get("revision") != 11
        or control.get("minimum_tool_revision") != 11
        or len(active_holds) != 1
        or active_holds[0] != hold
        or hold.get("id") != "HOLD-W1-GRR-0002"
        or hold.get("recovery_request_id") != "GRR-0002"
        or hold.get("target_wave") != "W1"
        or hold.get("status") != "ACTIVE"
        or (hold.get("bootstrap") or {}).get("status") != "APPROVED"
        or (hold.get("post_bootstrap") or {}).get("required_change_request_id") != "ECR-0003"
        or (hold.get("post_bootstrap") or {}).get("required_amendment_id") != "W1.A04"
        or [item.get("id") for item in supplements] != ["GRR-0002.S01", "GRR-0002.S02"]
        or supplement.get("predecessor_control_revision") != 10
        or supplement.get("successor_control_revision") != 11
        or supplement.get("packet_reference") != expected_s02_packet
        or supplement.get("approval_reference") != expected_s02_approval
    ):
        errors.append("historic submission lacks the exact active revision-11 S02 authority")
    if (
        bootstrap.get("id") != "GRR-0002.B02"
        or bootstrap.get("status") != "APPROVED"
        or bootstrap.get("current_submission") is not None
        or (bootstrap.get("review") or {}).get("result") != "approved"
        or not attempts
        or (latest_attempt.get("review") or {}).get("result") != "approved"
        or latest_attempt.get("implementation_commit") != bootstrap.get("implementation_commit")
        or latest_attempt.get("evidence") != bootstrap.get("evidence")
    ):
        errors.append("historic submission requires an independently approved exact B02 attempt")
    try:
        s02_relative = expected_s02_approval["path"]
        s02_path = safe_control_path(
            repo,
            s02_relative,
            prefix="planning/governance-recovery-approvals",
            label="GRR-0002.S02 approval",
        )
        s02_payload = s02_path.read_bytes()
    except (OSError, ValueError) as exc:
        errors.append(f"historic submission cannot authenticate the S02 approval: {exc}")
    else:
        introduction = expected_s02_approval["introduction_commit"]
        if (
            hashlib.sha256(s02_payload).hexdigest() != expected_s02_approval["sha256"]
            or approval_introduction_commit(repo, s02_relative) != introduction
            or git_blob(repo, introduction, s02_relative) != s02_payload
        ):
            errors.append("historic submission S02 approval bytes or introduction are not exact")
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if untracked.returncode != 0 or untracked.stdout.splitlines() != [evidence_relative]:
        errors.append("historic submission requires the witness as the sole untracked path")
    return errors


def materialized_superseded_reservation(
    repo: Path,
    wave_id: str,
    reservation: dict[str, Any],
    migration: dict[str, Any],
) -> dict[str, Any]:
    """Project one approved, unmaterialized reservation as terminal history."""
    amendment_id = str(reservation.get("id") or "")
    migration_id = str(migration.get("migrationId") or migration.get("id") or "")
    if not migration_id:
        raise SystemExit(f"Cannot materialize reserved amendment {amendment_id}: migration identity is absent")
    reference = reservation.get("approvalReference") or {}
    relative = str(reference.get("path") or "")
    try:
        approval_path = safe_control_path(
            repo,
            relative,
            prefix="planning/wave-amendment-approvals",
            label=f"{amendment_id} reserved approval",
        )
        approval_payload = approval_path.read_bytes()
        approval = json.loads(approval_payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot authenticate reserved amendment {amendment_id}: {exc}") from exc
    introduction = approval_introduction_commit(repo, relative)
    if (
        hashlib.sha256(approval_payload).hexdigest() != reference.get("sha256")
        or introduction != reference.get("introductionCommit")
        or git_blob(repo, introduction, relative) != approval_payload
        or approval.get("status") != "APPROVED"
        or approval.get("amendmentId") != amendment_id
        or approval.get("targetWave") != wave_id
        or approval.get("changeRequestId") != reservation.get("changeRequestId")
    ):
        raise SystemExit(f"Reserved amendment {amendment_id} approval authority is not exact")
    packet_reference = approval.get("packet") or {}
    packet_relative = str(packet_reference.get("path") or "")
    try:
        packet_path = safe_control_path(
            repo,
            packet_relative,
            prefix="planning/enabler-change-requests",
            label=f"{amendment_id} reserved packet",
        )
        packet_payload = packet_path.read_bytes()
        packet = json.loads(packet_payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot authenticate reserved amendment packet {amendment_id}: {exc}") from exc
    if (
        packet_reference.get("commit") != reservation.get("packetCommit")
        or hashlib.sha256(packet_payload).hexdigest() != packet_reference.get("sha256")
        or git_blob(repo, str(packet_reference.get("commit") or ""), packet_relative) != packet_payload
        or packet.get("proposedAmendmentId") != amendment_id
        or packet.get("changeRequestId") != reservation.get("changeRequestId")
    ):
        raise SystemExit(f"Reserved amendment {amendment_id} packet authority is not exact")
    return {
        "id": amendment_id,
        "change_request_id": reservation.get("changeRequestId"),
        "target_wave": wave_id,
        "kind": packet.get("classification"),
        "approval_reference": {
            "path": relative,
            "sha256": reference.get("sha256"),
            "introduction_commit": introduction,
        },
        "lifecycle": {
            "status": "SUPERSEDED",
            "history": [
                {
                    "id": "E01",
                    "status": "APPROVED",
                    "actor": approval.get("approvedBy"),
                    "at": approval.get("approvedAt"),
                    "rationale": approval.get("decision"),
                },
                {
                    "id": "E02",
                    "status": "SUPERSEDED",
                    "actor": f"governance-migration:{migration_id}",
                    "at": migration.get("authorizedAt"),
                    "rationale": (
                        "Recorded the approved but unmaterialized reservation as terminal superseded history under "
                        f"{migration_id}; no bootstrap, task, campaign, or product authority was executed."
                    ),
                },
            ],
        },
        "bootstrap": None,
        "campaign": None,
        "tasks": [],
        "completion": {
            "status": "PENDING",
            "reviewer": None,
            "reviewed_at": None,
            "evidence": [],
            "notes": "Approved reservation was never materialized or executed and is terminally superseded.",
        },
    }


def command_amendment_v4_bootstrap_submit(
    args: argparse.Namespace,
    data: dict[str, Any],
    tasks: dict[str, dict[str, Any]],
    *,
    repo: Path,
    approval: dict[str, Any],
    packet: dict[str, Any],
    approval_payload: bytes,
    frozen_amendments: dict[str, str],
    frozen_wave_bases: dict[str, str],
) -> None:
    """Append post-migration reservations and the next approved v4 amendment."""
    ecr_check = subprocess.run(
        [
            sys.executable,
            str(repo / "tools" / "planctl.py"),
            "--repo",
            str(repo),
            "ecr",
            "validate",
            str(approval.get("changeRequestId")),
            "--require-approved",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if ecr_check.returncode != 0:
        detail = "\n".join(part.strip() for part in (ecr_check.stdout, ecr_check.stderr) if part.strip())
        raise SystemExit(f"Post-migration amendment authority validation failed:\n{detail}")
    wave_id = str(packet.get("targetWave") or "")
    existing = [item for item in data.get("wave_amendments", []) if item.get("target_wave") == wave_id]
    chain = packet.get("authorityChain") or {}
    ordered = chain.get("orderedAmendments") or []
    reserved = chain.get("reservedAmendments") or []
    paused = chain.get("pausedPredecessor")
    if paused is not None:
        ordered = [*ordered, paused]
    adopted_ids = [str(item.get("id") or "") for item in ordered]
    reserved_ids = [str(item.get("id") or "") for item in reserved]

    def amendment_ordinal(amendment_id: str) -> int:
        match = re.fullmatch(rf"{re.escape(wave_id)}\.A(\d{{2}})", amendment_id)
        return int(match.group(1)) if match else 100

    predecessor_ids = sorted(
        [*adopted_ids, *reserved_ids],
        key=amendment_ordinal,
    )
    expected_predecessors = [f"{wave_id}.A{index:02d}" for index in range(1, len(predecessor_ids) + 1)]
    existing_ids = [str(item.get("id") or "") for item in existing]
    missing_predecessors = predecessor_ids[len(existing_ids) :]
    if (
        len(predecessor_ids) != len(set(predecessor_ids))
        or any(amendment_ordinal(item) == 100 for item in predecessor_ids)
        or adopted_ids != sorted(adopted_ids, key=amendment_ordinal)
        or reserved_ids != sorted(reserved_ids, key=amendment_ordinal)
        or predecessor_ids != expected_predecessors
        or existing_ids != predecessor_ids[: len(existing_ids)]
        or any(item not in existing_ids for item in adopted_ids)
        or any(item not in reserved_ids for item in missing_predecessors)
    ):
        raise SystemExit("Post-migration amendment predecessor authority differs from the canonical backlog")
    expected_id = f"{wave_id}.A{len(predecessor_ids) + 1:02d}"
    if args.amendment != expected_id or packet.get("proposedAmendmentId") != expected_id:
        raise SystemExit(f"Only the next post-migration Wave amendment may be appended: {expected_id}")
    control = data.get("control_plane") or {}
    activation = packet.get("activationBoundary") or {}
    maintenance = control.get("maintenance_increments") or []
    first_post_migration_bootstrap = not maintenance and bool(missing_predecessors)
    if (
        (
            first_post_migration_bootstrap
            and (control.get("revision") != 11 or control.get("minimum_tool_revision") != 11)
        )
        or (
            not first_post_migration_bootstrap
            and (
                control.get("revision") != CONTROL_TOOL_REVISION
                or control.get("minimum_tool_revision") != CONTROL_TOOL_REVISION
            )
        )
        or control.get("active_amendment") is not None
        or active_recovery_holds(data)
        or activation.get("activeRecoveryHolds") != []
    ):
        raise SystemExit("Post-migration amendment requires the exact released supported control boundary")
    wave = get(wave_map(data), wave_id, "wave")
    campaign = wave.get("campaign") or {}
    if (
        activation.get("waveStatus") != "PAUSED"
        or campaign.get("status") != "PAUSED"
        or campaign.get("scope") != ("amendment-hold" if paused is not None else "wave")
        or campaign.get("lease") is not None
    ):
        raise SystemExit("Target Wave is not at the exact paused Wave-scope activation boundary")
    denied = set(activation.get("ordinaryTaskStatesDenied") or [])
    if denied != {"IN_PROGRESS", "REVIEW"} or any(
        task_wave(task) == wave_id and task.get("status") in denied for task in tasks.values()
    ):
        raise SystemExit("Ordinary Wave task work is not quiescent at the approved activation boundary")
    if active_amendment_campaigns(data) or activation.get("otherEnablerCampaignDenied") is not True:
        raise SystemExit("Another enabler campaign is active at the approved activation boundary")
    migration_reference = packet.get("migrationAuthority") or {}
    migration_relative = str(migration_reference.get("path") or "")
    try:
        migration_path = safe_control_path(
            repo,
            migration_relative,
            prefix="planning/governance-migrations",
            label="Post-migration amendment authority",
        )
        migration_payload = migration_path.read_bytes()
        migration = json.loads(migration_payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot authenticate the governance migration: {exc}") from exc
    if (
        hashlib.sha256(migration_payload).hexdigest() != migration_reference.get("sha256")
        or git_blob(repo, str(migration_reference.get("commit") or ""), migration_relative) != migration_payload
        or migration.get("migrationId") != migration_reference.get("id")
        or migration.get("status") != "adopted"
    ):
        raise SystemExit("Post-migration amendment authority is not exact")
    approval_relative = f"planning/wave-amendment-approvals/{args.amendment}.json"
    introduction = approval_introduction_commit(repo, approval_relative)
    approval_commit = str(args.approval_commit)
    if approval_commit != introduction:
        raise SystemExit("Approval commit must equal the immutable approval-record introduction commit")
    implementation_commit = str(args.implementation_commit)
    head, current_branch = git_head_branch(repo)
    if (
        implementation_commit == approval_commit
        or implementation_commit != head
        or not git_is_ancestor(repo, approval_commit, implementation_commit)
    ):
        raise SystemExit("Post-migration bootstrap implementation must be current HEAD and descend from approval")
    evidence_relative, evidence_path = canonical_control_artifact_path(
        repo,
        str(args.evidence),
        prefix="artifacts/evidence",
        label="Post-migration amendment bootstrap evidence",
    )
    require_clean_repository(
        repo,
        allowed_untracked={HISTORICAL_W1_A04_WITNESS["path"], evidence_relative},
    )
    try:
        evidence_payload = evidence_path.read_bytes()
        parse_evidence_payload(evidence_payload, evidence_path.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid bootstrap evidence: {exc}") from exc
    bootstrap_unit = packet.get("bootstrapUnit") or {}
    _additional_paths, addendum_references = load_bootstrap_scope_addenda(
        repo, args.amendment, str(bootstrap_unit.get("id"))
    )
    agent = normalized_identity(args.agent, "Bootstrap implementer")
    candidate = {
        "id": str(bootstrap_unit.get("id")),
        "status": "REVIEW",
        "implementer": agent,
        "implementation_commit": implementation_commit,
        "submission_branch": current_branch,
        "scope_addenda": addendum_references,
        "evidence": [
            {
                "type": "criterion-manifest",
                "path": evidence_relative,
                "sha256": evidence_sha256(evidence_payload),
                "commit": implementation_commit,
                "recorded_at": utc_now(),
            }
        ],
        "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
    }
    allowed_patterns, authorization_errors = bootstrap_candidate_authorization(
        repo,
        packet,
        addendum_references,
        implementation_commit,
        str(bootstrap_unit.get("id")),
    )
    errors = [
        *authorization_errors,
        *bootstrap_attempt_errors(
            repo,
            args.amendment,
            str(bootstrap_unit.get("id")),
            [str(item) for item in bootstrap_unit.get("requiredOutcomes", [])],
            candidate,
            expected_base=approval_commit,
            lineage_base=approval_commit,
            allowed_patterns=allowed_patterns,
            require_current_branch=True,
        ),
    ]
    if errors:
        raise SystemExit("Invalid post-migration amendment bootstrap evidence:\n- " + "\n- ".join(errors))
    frozen_waves = exact_record_snapshot(data, "waves", identities={wave_id})
    before_snapshot = amendment_identity_snapshot(data)
    missing_reservations = [reservation for reservation in reserved if reservation.get("id") in missing_predecessors]
    for reservation in missing_reservations:
        data.setdefault("wave_amendments", []).append(
            materialized_superseded_reservation(repo, wave_id, reservation, migration)
        )
    data["wave_amendments"].append(
        {
            "id": args.amendment,
            "change_request_id": approval.get("changeRequestId"),
            "target_wave": wave_id,
            "kind": packet.get("classification"),
            "approval_reference": {
                "path": approval_relative,
                "sha256": hashlib.sha256(approval_payload).hexdigest(),
                "introduction_commit": introduction,
            },
            "lifecycle": {
                "status": "APPROVED",
                "history": [
                    {
                        "id": "E01",
                        "status": "APPROVED",
                        "actor": approval.get("approvedBy"),
                        "at": approval.get("approvedAt"),
                        "rationale": approval.get("decision"),
                    }
                ],
            },
            "bootstrap": candidate,
            "campaign": None,
            "tasks": [],
            "completion": {
                "status": "PENDING",
                "reviewer": None,
                "reviewed_at": None,
                "evidence": [],
                "notes": None,
            },
            **({"correction": copy.deepcopy(paused)} if paused is not None else {}),
        }
    )
    after_snapshot = amendment_identity_snapshot(data)
    expected_suffix = tuple((item, ()) for item in [*missing_predecessors, args.amendment])
    if (
        after_snapshot[: len(before_snapshot)] != before_snapshot
        or after_snapshot[len(before_snapshot) :] != expected_suffix
    ):
        raise SystemExit("Post-migration append would replace, reorder, or fork predecessor amendment authority")
    if first_post_migration_bootstrap:
        control.setdefault("maintenance_increments", []).append(
            {
                "id": "MI-0001",
                "kind": "post-migration-amendment-bootstrap",
                "predecessor_revision": 11,
                "successor_revision": CONTROL_TOOL_REVISION,
                "change_request_id": approval.get("changeRequestId"),
                "amendment_id": args.amendment,
                "approval_reference": {
                    "path": approval_relative,
                    "sha256": hashlib.sha256(approval_payload).hexdigest(),
                    "introduction_commit": introduction,
                },
                "migration_reference": copy.deepcopy(migration_reference),
                "applied_by": agent,
                "applied_at": utc_now(),
            }
        )
        control["revision"] = CONTROL_TOOL_REVISION
        control["minimum_tool_revision"] = CONTROL_TOOL_REVISION
    control["active_amendment"] = None
    save_validated(
        args.file,
        data,
        expected_sha256=getattr(args, "source_sha256", None),
        expected_identity=getattr(args, "source_identity", None),
        expected_approved_waves=getattr(args, "source_approved_waves", None),
        expected_amendment_history=getattr(args, "source_amendment_history", None),
        expected_task_review_history=getattr(args, "source_task_review_history", None),
        expected_wave_checkpoint_history=getattr(args, "source_wave_checkpoint_history", None),
        expected_wave_resume_history=getattr(args, "source_wave_resume_history", None),
        expected_recovery_history=getattr(args, "source_recovery_history", None),
        expected_released_recovery_holds=getattr(args, "source_released_recovery_holds", None),
        expected_frozen_waves=frozen_waves,
        expected_frozen_wave_bases=frozen_wave_bases,
        expected_frozen_amendments=frozen_amendments,
        repo=repo,
    )
    print(f"Appended reserved history and submitted {bootstrap_unit.get('id')} for independent review")


def command_amendment_append_bootstrap_submit(args, data, capabilities, slices, tasks, gates) -> None:
    """Append a later approved amendment without replacing any predecessor."""
    repo = discover_repository(args.file)
    hold_errors = recovery_hold_errors(data, repo)
    if hold_errors:
        raise SystemExit("Invalid governance recovery hold:\n- " + "\n- ".join(hold_errors))
    existing = list(data.get("wave_amendments", []))
    frozen_amendments = exact_record_snapshot(data, "wave_amendments")
    frozen_wave_bases = exact_record_snapshot(
        data,
        "wave_approval_bases",
        identity_field="wave_id",
    )
    if args.amendment in wave_amendment_map(data):
        raise SystemExit(f"Wave amendment {args.amendment} already exists; duplicate append is denied")
    match = re.fullmatch(r"(W(?:[0-9]|1[01]))\.A([0-9]{2})", str(args.amendment))
    if match is None:
        raise SystemExit("Appended Wave amendment identity is invalid")
    wave_id = match.group(1)
    frozen_waves = exact_record_snapshot(data, "waves", identities={wave_id})
    approval, packet, approval_payload = load_amendment_authority(repo, args.amendment)
    if packet.get("schemaVersion") in {"4.0-proposal", "4.1-proposal"}:
        command_amendment_v4_bootstrap_submit(
            args,
            data,
            tasks,
            repo=repo,
            approval=approval,
            packet=packet,
            approval_payload=approval_payload,
            frozen_amendments=frozen_amendments,
            frozen_wave_bases=frozen_wave_bases,
        )
        return
    ordered = [item for item in existing if item.get("target_wave") == wave_id]
    expected_id = f"{wave_id}.A{len(ordered) + 1:02d}"
    if args.amendment != expected_id:
        raise SystemExit(f"Only the next consecutive Wave amendment may be appended: {expected_id}")
    holds = [
        hold
        for hold in active_recovery_holds(data)
        if (hold.get("post_bootstrap") or {}).get("required_amendment_id") == args.amendment
    ]
    if len(holds) != 1 or (holds[0].get("bootstrap") or {}).get("status") != "APPROVED":
        raise SystemExit("A matching active recovery hold with independently approved bootstrap is required")
    hold = holds[0]
    schema_version = str(packet.get("schemaVersion") or "")
    if schema_version not in {"2.0-proposal", "3.0-proposal"}:
        raise SystemExit("Subsequent amendment append requires a supported generic ECR packet")
    if hold.get("recovery_request_id") != "GRR-0001" and schema_version != "3.0-proposal":
        raise SystemExit("Recovery requests after GRR-0001 require the versioned v3 ECR authority binding")
    post = hold.get("post_bootstrap") or {}
    if (
        approval.get("changeRequestId") != post.get("required_change_request_id")
        or approval.get("targetWave") != wave_id
        or approval.get("authorizedTaskIds") != post.get("required_proposed_task_ids")
    ):
        raise SystemExit("Appended amendment approval differs from the recovery hold boundary")
    ecr_check = subprocess.run(
        [
            sys.executable,
            str(repo / "tools" / "planctl.py"),
            "--repo",
            str(repo),
            "ecr",
            "validate",
            str(approval.get("changeRequestId")),
            "--require-approved",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if ecr_check.returncode != 0:
        detail = "\n".join(part.strip() for part in (ecr_check.stdout, ecr_check.stderr) if part.strip())
        raise SystemExit(f"Appended amendment authority validation failed:\n{detail}")
    approval_relative = f"planning/wave-amendment-approvals/{args.amendment}.json"
    introduction = approval_introduction_commit(repo, approval_relative)
    approval_commit = str(args.approval_commit)
    if approval_commit != introduction:
        raise SystemExit("Approval commit must equal the immutable approval-record introduction commit")
    implementation_commit = str(args.implementation_commit)
    if implementation_commit == approval_commit or not git_is_ancestor(repo, approval_commit, implementation_commit):
        raise SystemExit("Amendment bootstrap implementation must strictly descend from the approval commit")
    head, current_branch = git_head_branch(repo)
    evidence_relative, evidence_path = canonical_control_artifact_path(
        repo,
        str(args.evidence),
        prefix="artifacts/evidence",
        label="Appended amendment bootstrap evidence",
    )
    require_clean_repository(repo, allowed_untracked={evidence_relative})
    try:
        evidence_payload = evidence_path.read_bytes()
        parse_evidence_payload(evidence_payload, evidence_path.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid bootstrap evidence: {exc}") from exc
    if implementation_commit != head:
        historic_errors = exact_w1_a04_historic_submission_errors(
            repo,
            data,
            hold,
            args,
            approval,
            packet,
            approval_payload,
            approval_commit=approval_commit,
            implementation_commit=implementation_commit,
            evidence_relative=evidence_relative,
            evidence_payload=evidence_payload,
        )
        if historic_errors:
            raise SystemExit(
                "Amendment bootstrap implementation commit must equal current HEAD; "
                f"historic recovery exception denied: {historic_errors[0]}"
            )
    agent = normalized_identity(args.agent, "Bootstrap implementer")
    bootstrap_unit = packet.get("bootstrapUnit") or {}
    _additional_paths, addendum_references = load_bootstrap_scope_addenda(
        repo, args.amendment, str(bootstrap_unit.get("id"))
    )
    candidate = {
        "id": str(bootstrap_unit.get("id")),
        "status": "REVIEW",
        "implementer": agent,
        "implementation_commit": implementation_commit,
        "submission_branch": current_branch,
        "scope_addenda": addendum_references,
        "evidence": [
            {
                "type": "criterion-manifest",
                "path": evidence_relative,
                "sha256": evidence_sha256(evidence_payload),
                "commit": implementation_commit,
                "recorded_at": utc_now(),
            }
        ],
        "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
    }
    allowed_patterns, authorization_errors = bootstrap_candidate_authorization(
        repo,
        packet,
        addendum_references,
        implementation_commit,
        str(bootstrap_unit.get("id")),
    )
    errors = [
        *authorization_errors,
        *bootstrap_attempt_errors(
            repo,
            args.amendment,
            str(bootstrap_unit.get("id")),
            [str(item) for item in bootstrap_unit.get("requiredOutcomes", [])],
            candidate,
            expected_base=approval_commit,
            lineage_base=approval_commit,
            allowed_patterns=allowed_patterns,
            require_current_branch=True,
        ),
    ]
    if errors:
        raise SystemExit("Invalid appended amendment bootstrap evidence:\n- " + "\n- ".join(errors))
    amendment = {
        "id": args.amendment,
        "change_request_id": approval.get("changeRequestId"),
        "target_wave": wave_id,
        "kind": packet.get("classification"),
        "approval_reference": {
            "path": approval_relative,
            "sha256": hashlib.sha256(approval_payload).hexdigest(),
            "introduction_commit": introduction,
        },
        "lifecycle": {
            "status": "APPROVED",
            "history": [
                {
                    "id": "E01",
                    "status": "APPROVED",
                    "actor": approval.get("approvedBy"),
                    "at": approval.get("approvedAt"),
                    "rationale": approval.get("decision"),
                }
            ],
        },
        "bootstrap": candidate,
        "campaign": None,
        "tasks": [],
        "completion": {"status": "PENDING", "reviewer": None, "reviewed_at": None, "evidence": [], "notes": None},
    }
    before_snapshot = amendment_identity_snapshot(data)
    data.setdefault("wave_amendments", []).append(amendment)
    after_snapshot = amendment_identity_snapshot(data)
    if after_snapshot[:-1] != before_snapshot or after_snapshot[-1] != (args.amendment, ()):
        raise SystemExit("Append transition would replace or reorder predecessor amendment authority")
    save_validated(
        args.file,
        data,
        expected_sha256=getattr(args, "source_sha256", None),
        expected_identity=getattr(args, "source_identity", None),
        expected_approved_waves=getattr(args, "source_approved_waves", None),
        expected_amendment_history=getattr(args, "source_amendment_history", None),
        expected_task_review_history=getattr(args, "source_task_review_history", None),
        expected_wave_checkpoint_history=getattr(args, "source_wave_checkpoint_history", None),
        expected_wave_resume_history=getattr(args, "source_wave_resume_history", None),
        expected_recovery_history=getattr(args, "source_recovery_history", None),
        expected_released_recovery_holds=getattr(args, "source_released_recovery_holds", None),
        expected_frozen_waves=frozen_waves,
        expected_frozen_wave_bases=frozen_wave_bases,
        expected_frozen_amendments=frozen_amendments,
        repo=repo,
    )
    print(f"Appended and submitted {bootstrap_unit.get('id')} for independent review")


def command_amendment_bootstrap_submit(args, data, capabilities, slices, tasks, gates) -> None:
    if data.get("control_plane") or data.get("wave_approval_bases") or data.get("wave_amendments"):
        command_amendment_append_bootstrap_submit(args, data, capabilities, slices, tasks, gates)
        return
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
    _additional_paths, scope_addenda = load_bootstrap_scope_addenda(
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
    patterns, authorization_errors = bootstrap_candidate_authorization(
        repo,
        packet,
        scope_addenda,
        implementation_commit,
        str(bootstrap_unit.get("id")),
    )
    evidence_errors.extend(authorization_errors)
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
        expected_wave_resume_history=getattr(args, "source_wave_resume_history", None),
        expected_recovery_history=getattr(args, "source_recovery_history", None),
        expected_released_recovery_holds=getattr(args, "source_released_recovery_holds", None),
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
    require_clean_repository(
        repo,
        allowed_untracked=amendment_transition_allowed_untracked(data, args.amendment, repo),
    )
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
    require_clean_repository(
        repo,
        allowed_untracked={
            evidence_relative,
            *amendment_transition_allowed_untracked(data, args.amendment, repo),
        },
    )
    try:
        evidence_payload = evidence_path.read_bytes()
        _manifest = parse_evidence_payload(evidence_payload, evidence_path.suffix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Invalid bootstrap evidence: {exc}") from exc
    agent = normalized_identity(args.agent, "Bootstrap remediation implementer")
    _additional_paths, scope_addenda = bootstrap_resubmission_scope_addenda(
        repo,
        args.amendment,
        str(bootstrap.get("id")),
        bootstrap,
        previous_candidate,
        implementation_commit,
    )
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
        "scope_base_commit": previous_candidate,
        "evidence": [evidence_reference],
        "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
    }
    allowed_patterns, authorization_errors = bootstrap_candidate_authorization(
        repo,
        packet,
        scope_addenda,
        implementation_commit,
        str(bootstrap.get("id")),
    )
    errors = [
        *authorization_errors,
        *bootstrap_attempt_errors(
            repo,
            args.amendment,
            str(bootstrap.get("id")),
            [str(item) for item in (packet.get("bootstrapUnit") or {}).get("requiredOutcomes", [])],
            candidate,
            expected_base=None,
            lineage_base=previous_candidate,
            allowed_patterns=allowed_patterns,
            require_current_branch=True,
        ),
    ]
    if errors:
        raise SystemExit("Invalid bootstrap remediation evidence:\n- " + "\n- ".join(errors))
    prior_review = copy.deepcopy(bootstrap.get("review") or {})
    attempt_id = f"R{len(bootstrap.get('attempts') or []) + 1:02d}"
    prior_attempt = {
        "id": attempt_id,
        "implementer": bootstrap.get("implementer"),
        "implementation_commit": previous_candidate,
        "submission_branch": bootstrap.get("submission_branch"),
        "evidence": copy.deepcopy(bootstrap.get("evidence") or []),
        "review": prior_review,
    }
    if bootstrap.get("scope_base_commit") is not None:
        prior_attempt["scope_base_commit"] = bootstrap.get("scope_base_commit")
    bootstrap.setdefault("attempts", []).append(prior_attempt)
    bootstrap.update(
        status="REVIEW",
        implementer=agent,
        implementation_commit=implementation_commit,
        submission_branch=str(_manifest.get("branch") or ""),
        scope_base_commit=previous_candidate,
        evidence=[evidence_reference],
        review={"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
    )
    bootstrap["scope_addenda"] = scope_addenda
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
    require_clean_repository(
        repo,
        allowed_untracked=amendment_transition_allowed_untracked(data, args.amendment, repo),
    )
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
        expected_wave_resume_history=getattr(args, "source_wave_resume_history", None),
        expected_recovery_history=getattr(args, "source_recovery_history", None),
        expected_released_recovery_holds=getattr(args, "source_released_recovery_holds", None),
        repo=repo,
    )
    print(f"Materialized {', '.join(authorized)} from {args.amendment}")


def command_amendment_activate(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    require_execution_target(args.profile, args.platform)
    if any(role["parentId"] == args.amendment and role["parentFrozen"] for role in correction_roles(data)):
        raise SystemExit(
            "A correction freezes this predecessor until independently qualified adoption returns its hold"
        )
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    lifecycle = (amendment.get("lifecycle") or {}).get("status")
    completion = amendment.get("completion") or {}
    exit_control = completion.get("exit_review_control") or {}
    exit_attempts = exit_control.get("attempts") or []
    approved_exit_remediation = (
        lifecycle == "REVIEW"
        and (amendment.get("campaign") or {}).get("status") == "COMPLETE"
        and completion.get("status") == "APPROVED"
        and exit_control.get("current_submission") is None
        and bool(exit_attempts)
        and (exit_attempts[-1].get("review") or {}).get("result") == "approved"
    )
    if lifecycle not in {"MATERIALIZED", "PAUSED"} and not approved_exit_remediation:
        raise SystemExit(
            "Only a MATERIALIZED, PAUSED, or approved-exit amendment awaiting adoption remediation may be activated"
        )
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
    require_clean_repository(
        repo,
        allowed_untracked=amendment_transition_allowed_untracked(data, args.amendment, repo),
    )
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
    activation_rationale = (
        "Reactivated the bounded amendment campaign after a failed adoption transition."
        if approved_exit_remediation
        else "Activated the bounded amendment campaign."
    )
    append_amendment_event(amendment, "ACTIVE", agent, activation_rationale)
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


def command_amendment_renew(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    amendment = get(wave_amendment_map(data), args.amendment, "Wave amendment")
    campaign = amendment.get("campaign") or {}
    if campaign.get("status") != "ACTIVE" or campaign.get("scope") != "wave-amendment":
        raise SystemExit("Only an ACTIVE Wave amendment lease may be renewed")
    if data.get("control_plane", {}).get("active_amendment") != amendment["id"]:
        raise SystemExit(f"Wave amendment {amendment['id']} is not the active amendment")
    if campaign.get("owner") != args.agent:
        raise SystemExit(f"Wave amendment {amendment['id']} is owned by {campaign.get('owner')}, not {args.agent}")
    if lease_is_active(amendment):
        require_active_lease(amendment, args.agent, f"Wave amendment {amendment['id']}")
    campaign["lease"] = new_lease(args.agent, args.lease_hours)
    campaign["updated_at"] = utc_now()
    persist(args, data)
    print(f"Renewed Wave amendment lease for {amendment['id']}")


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
        require_clean_repository(
            repo,
            allowed_untracked=amendment_transition_allowed_untracked(data, args.amendment, repo),
        )
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
    require_clean_repository(
        repo,
        allowed_untracked={
            ledger_relative,
            *amendment_transition_allowed_untracked(data, args.amendment, repo),
        },
    )
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
    if (amendment.get("lifecycle") or {}).get("status") != "REVIEW":
        raise SystemExit("Only an unadopted REVIEW amendment may publish its adoption checkpoint")
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
    require_clean_repository(
        repo,
        allowed_untracked=amendment_transition_allowed_untracked(data, args.amendment, repo),
    )
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
    correction = amendment.get("correction")
    if correction is not None and manifest.get("correctionReturn") != correction:
        raise SystemExit("Correction adoption checkpoint must bind the exact paused-predecessor return relation")
    if correction is None and "correctionReturn" in manifest:
        raise SystemExit("Ordinary amendment adoption cannot acquire an unapproved correction return")
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
    wave_campaign["scope"] = "amendment-hold" if correction is not None else "wave"
    data["control_plane"]["active_amendment"] = None
    append_amendment_event(amendment, "ADOPTED", actor, args.note or f"Adopted via {checkpoint_id}.")
    persist(args, data)
    if correction is not None:
        print(
            f"Adopted {args.amendment}; returned the hold to PAUSED {correction['id']}; explicit activation is required"
        )
    else:
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
    repo = Path(worktree)
    require_clean_repository(
        repo,
        allowed_untracked=wave_resume_allowed_untracked(data, str(wave["id"]), repo),
    )
    if campaign.get("owner") != agent:
        raise SystemExit(f"Paused Wave is owned by {campaign.get('owner')}, not {agent}")
    if campaign.get("branch") and campaign.get("branch") != branch:
        raise SystemExit("Paused Wave must resume on its recorded branch")
    if campaign.get("worktree") and Path(str(campaign["worktree"])).resolve() != Path(worktree).resolve():
        raise SystemExit("Paused Wave must resume in its recorded canonical worktree")
    if campaign.get("profile") != args.profile or campaign.get("platform") != args.platform:
        raise SystemExit("Paused Wave must resume with its recorded profile and platform")
    prior_campaign = copy.deepcopy(campaign)
    now = utc_now()
    resume_records = list(campaign.get("resume_records", []))
    resume_records.append(
        {
            "id": f"{wave['id']}.R{len(resume_records) + 1:02d}",
            "wave_id": wave["id"],
            "control_revision": int((data.get("control_plane") or {}).get("revision", 0)),
            "prior_status": "PAUSED",
            "pre_resume_commit": base_sha,
            "prior_campaign_sha256": canonical_json_sha256(prior_campaign),
            "branch": branch,
            "worktree": worktree,
            "profile": args.profile,
            "platform": args.platform,
            "actor": agent,
            "resumed_at": now,
        }
    )
    campaign.update(
        status="ACTIVE",
        branch=branch,
        worktree=worktree,
        base_sha=base_sha,
        profile=args.profile,
        platform=args.platform,
        updated_at=now,
        pause_reason=None,
        pause_category=None,
        lease=new_lease(agent, args.lease_hours),
        resume_records=resume_records,
    )
    wave["completion"]["status"] = "IN_PROGRESS"
    args.authorized_wave_resume_append = str(wave["id"])
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


def command_recover(args, data, capabilities, slices, tasks, gates) -> None:
    require_positive_lease_hours(args.lease_hours)
    require_execution_target(args.profile, args.platform)
    if args.task != EXACT_T03_RECOVERY["task_id"]:
        raise SystemExit("Exact historical recovery is authorized only for CAP-02.S04.T03")
    agent, branch, base_sha, worktree = git_execution_identity(
        args.file,
        agent=args.agent,
        branch=args.branch,
        base_sha=args.base_sha,
        worktree=args.worktree,
    )
    if branch != EXACT_T03_RECOVERY["branch"]:
        raise SystemExit("Exact T03 recovery requires the approved Codex branch")
    repo = discover_repository(args.file)
    require_clean_repository(
        repo,
        allowed_untracked=wave_resume_allowed_untracked(data, EXACT_T03_RECOVERY["wave_id"], repo),
    )
    preflight_errors = validate(data, capabilities, slices, tasks, gates, repo=repo)
    if preflight_errors:
        raise SystemExit("Exact T03 recovery preflight failed:\n- " + "\n- ".join(preflight_errors))

    task = get(tasks, args.task, "task")
    if task.get("status") != "BLOCKED" or task.get("recovery_control") is not None:
        raise SystemExit("Exact T03 recovery requires the unrecovered BLOCKED task boundary")
    pause_task = historical_task(repo, EXACT_T03_RECOVERY["pause_record"], args.task)
    if pause_task is None or task_recovery_boundary(task) != task_recovery_boundary(pause_task):
        raise SystemExit("Current T03 state differs from the immutable blocked/pause boundary")
    if not task_dependencies_done(task, tasks):
        raise SystemExit("Exact T03 recovery requires every ordinary task dependency to remain DONE")

    amendment = wave_amendment_map(data).get(EXACT_T03_RECOVERY["amendment_id"]) or {}
    approval, packet, _approval_payload = load_amendment_authority(repo, EXACT_T03_RECOVERY["amendment_id"])
    require_amendment_packet_integrity(repo, amendment, approval, packet)
    if (amendment.get("lifecycle") or {}).get("status") != "ADOPTED" or (amendment.get("completion") or {}).get(
        "status"
    ) != "APPROVED":
        raise SystemExit("Exact T03 recovery requires adopted, independently approved W1.A03")
    hold = next(
        (
            item
            for item in (data.get("control_plane") or {}).get("recovery_holds", [])
            if item.get("id") == EXACT_T03_RECOVERY["hold_id"]
        ),
        None,
    )
    if hold is None or hold.get("status") != "RELEASED":
        raise SystemExit("Exact T03 recovery requires released HOLD-W1-GRR-0001")
    wave = wave_map(data).get(EXACT_T03_RECOVERY["wave_id"]) or {}
    campaign = wave.get("campaign") or {}
    if campaign.get("status") != "ACTIVE" or campaign.get("scope") != "wave":
        raise SystemExit("Exact T03 recovery requires explicitly resumed ACTIVE W1 scope wave")
    require_active_lease(wave, agent, "Wave W1")
    if campaign.get("branch") != branch or campaign.get("worktree") != worktree:
        raise SystemExit("Exact T03 recovery branch/worktree must match the resumed W1 campaign")
    if campaign.get("profile") != args.profile or campaign.get("platform") != args.platform:
        raise SystemExit("Exact T03 recovery profile/platform must match the resumed W1 campaign")
    resume_errors = exact_t03_resume_commit_errors(data, wave, repo, base_sha)
    if resume_errors:
        raise SystemExit("Exact T03 committed resume boundary failed:\n- " + "\n- ".join(resume_errors))
    checkpoints = [
        checkpoint
        for checkpoint in wave.get("checkpoints", [])
        if checkpoint.get("kind") == "security"
        and any(
            isinstance(reference, dict) and reference.get("amendment_id") == EXACT_T03_RECOVERY["amendment_id"]
            for reference in checkpoint.get("evidence", [])
        )
    ]
    if not checkpoints:
        raise SystemExit("Exact T03 recovery requires a bound W1.A03 control/security checkpoint")

    relative, manifest_path = canonical_control_artifact_path(
        repo,
        args.from_file,
        prefix="artifacts/evidence/task-recovery",
        label="Task recovery manifest",
    )
    if relative != EXACT_T03_RECOVERY["manifest_path"]:
        raise SystemExit("Exact T03 recovery requires its one canonical manifest path")
    payload = manifest_path.read_bytes()
    if git_blob(repo, base_sha, relative) != payload:
        raise SystemExit("Task recovery manifest must be committed unchanged at the recovery base")
    try:
        manifest = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid task recovery manifest: {exc}") from exc
    manifest_errors = exact_recovery_manifest_errors(
        data,
        task,
        manifest,
        repo,
        require_current_candidate_bytes=True,
    )
    if manifest_errors:
        raise SystemExit("Exact T03 recovery manifest failed:\n- " + "\n- ".join(manifest_errors))
    check_errors = run_exact_recovery_checks(repo)
    if check_errors:
        raise SystemExit("Exact T03 recovery recomputation failed:\n- " + "\n- ".join(check_errors))

    require_amendment_packet_integrity(repo, amendment, approval, packet)
    if task_recovery_contract(task) != task_recovery_contract(pause_task):
        raise SystemExit("Current T03 immutable task contract changed during recovery preflight")
    original = task_recovery_boundary(task)
    task["recovery_control"] = {
        "version": 1,
        "id": "CAP-02.S04.T03.RCV01",
        "manifest": {"path": relative, "sha256": evidence_sha256(payload)},
        "authority": {
            "amendment_id": EXACT_T03_RECOVERY["amendment_id"],
            "hold_id": EXACT_T03_RECOVERY["hold_id"],
            "checkpoint_id": checkpoints[-1]["id"],
        },
        "historical": {
            "base": EXACT_T03_RECOVERY["base"],
            "foundation": EXACT_T03_RECOVERY["foundation"],
            "candidate": EXACT_T03_RECOVERY["candidate"],
            "block_record": EXACT_T03_RECOVERY["block_record"],
            "pause_record": EXACT_T03_RECOVERY["pause_record"],
            "block_task_sha256": manifest["historicalTaskSha256"]["blockRecord"],
            "pause_task_sha256": manifest["historicalTaskSha256"]["pauseRecord"],
        },
        "original_blocked_state": original,
        "recovered_by": agent,
        "recovered_at": utc_now(),
        "new_base_sha": base_sha,
    }
    task.update(
        status="IN_PROGRESS",
        owner=agent,
        branch=branch,
        base_sha=base_sha,
        worktree=worktree,
        lease=new_lease(agent, args.lease_hours),
        updated_at=utc_now(),
        blocker=None,
    )
    persist(args, data)
    print("Recovered CAP-02.S04.T03 to IN_PROGRESS; ordinary evidence and independent review remain required")


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


def task_check_guidance(task: dict[str, Any]) -> list[str]:
    """Render task-scoped selection guidance while preserving the declared inventory."""
    profiles = [str(profile) for profile in task.get("verification_profiles", [])]
    commands = [str(command) for command in task.get("verification_commands", [])]
    base_sha = str(task.get("base_sha") or "")
    wave = str(task.get("wave") or "")
    lines = [
        "Task-scope guidance (advisory; no new gate)",
        "Select the narrowest deterministic checks that prove the task's credible changed-path and contract risks.",
    ]
    if profiles and re.fullmatch(r"[0-9a-f]{40}", base_sha) and re.fullmatch(r"W[0-9]+", wave):
        profile_arguments = " ".join(f"--profile {profile}" for profile in profiles)
        lines.extend(
            [
                "Affected-selection preview (use only when the recorded claim base accurately bounds this task delta):",
                (
                    f"python tools/verify.py {profile_arguments} --affected-base {base_sha} --affected-head HEAD "
                    f"--deferred-gate {wave}-exit --selection-only"
                ),
                "Review selected/deferred command IDs; remove --selection-only only when that selection fits the risk.",
            ]
        )
    lines.extend(["", "Qualification inventory (do not run automatically at ordinary task scope)"])
    lines.extend(commands or ["(no verification commands declared)"])
    return lines


def prepare_task_evidence(
    task: dict[str, Any],
    repo: Path,
    from_file: str,
    *,
    allowed_untracked: set[str] | None = None,
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
        allowed_untracked=allowed_untracked,
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
    reference, _manifest = prepare_task_evidence(
        task,
        repo,
        args.from_file,
        allowed_untracked=task_evidence_allowed_untracked(data, task, repo),
    )
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
        reference, manifest = prepare_task_evidence(
            task,
            repo,
            args.from_file,
            allowed_untracked=task_evidence_allowed_untracked(data, task, repo),
        )
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
    completed_dependents = [
        dependent
        for dependent in transitive_task_dependents(str(task["id"]), tasks, slices)
        if dependent.get("status") in {"IN_PROGRESS", "REVIEW", "DONE"}
    ]
    if completed_dependents and not getattr(args, "cascade_dependents", False):
        dependent_ids = ", ".join(sorted(str(item["id"]) for item in completed_dependents))
        raise SystemExit(
            f"Task has active or completed dependents ({dependent_ids}); "
            "use --cascade-dependents to reopen the dependency chain atomically"
        )
    if completed_dependents:
        active_dependents = sorted(
            str(item["id"]) for item in completed_dependents if item.get("status") in {"IN_PROGRESS", "REVIEW"}
        )
        if active_dependents:
            raise SystemExit(
                "Cannot cascade reopen while dependent tasks are active or awaiting review: "
                + ", ".join(active_dependents)
            )
        if any(item.get("wave") != task.get("wave") for item in completed_dependents):
            raise SystemExit("Cascade reopen cannot cross a Wave boundary")
        frozen_slices = sorted(
            {
                str(item["slice_id"])
                for item in completed_dependents
                if (slices[str(item["slice_id"])].get("completion") or {}).get("status") in {"REVIEW", "APPROVED"}
            }
        )
        if frozen_slices:
            raise SystemExit(
                "Cascade reopen cannot invalidate frozen or independently approved slices: " + ", ".join(frozen_slices)
            )
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
    for dependent in completed_dependents:
        dependent.update(
            status="NOT_STARTED",
            lease=None,
            updated_at=utc_now(),
            completed_at=None,
            blocker=None,
            cancellation=None,
            verification_state=None,
        )
    if wave_remediation:
        parent_slice = slices[task["slice_id"]]
        parent_slice["status"] = "IN_PROGRESS"
        parent_slice.setdefault("completion", {})["status"] = "CHANGES_REQUESTED"
    refresh_derived_states(data, capabilities, slices, tasks, gates)
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


def taskctl_command_is_read_only(args: argparse.Namespace) -> bool:
    if args.command in {"validate", "status", "review-telemetry", "next", "next-capability", "show", "checks"}:
        return True
    nested = {
        "amendment": "amendment_command",
        "wave": "wave_command",
        "capability": "cap_command",
        "slice": "slice_command",
        "gate": "gate_command",
    }
    field = nested.get(args.command)
    return field is not None and getattr(args, field, None) == "status"


def require_recovery_hold_permission(
    args: argparse.Namespace,
    data: dict[str, Any],
    tasks: dict[str, dict[str, Any]],
    repo: Path,
) -> None:
    holds = active_recovery_holds(data)
    if not holds or taskctl_command_is_read_only(args):
        return
    hold = holds[0]
    bootstrap = hold.get("bootstrap") or {}
    post = hold.get("post_bootstrap") or {}
    request_id = str(hold.get("recovery_request_id") or "")
    approved_supplement_files = sorted(
        (repo / "planning" / "governance-recovery-approvals").glob(f"{request_id}.S[0-9][0-9].json")
    )
    supplements = hold.get("supplements", [])
    if approved_supplement_files and (
        not supplements or ((supplements[-1].get("bootstrap") or {}).get("status")) != "APPROVED"
    ):
        expected = approved_supplement_files[-1].stem
        raise SystemExit(
            f"Governance recovery hold {hold.get('id')} denies this mutation until the approved supplemental "
            f"bootstrap for {expected} is installed, evidenced, and independently approved."
        )
    required_amendment = str(post.get("required_amendment_id") or "")
    amendment_command = args.command == "amendment" and getattr(args, "amendment", None) == required_amendment
    task_id = str(getattr(args, "task", "") or "")
    amendment_task_command = (
        args.command in {"claim", "block", "renew", "evidence", "submit", "review", "reopen", "cancel"}
        and task_id.startswith(f"{required_amendment}.T")
        and task_id in tasks
    )
    if bootstrap.get("status") == "APPROVED" and (amendment_command or amendment_task_command):
        approval, packet, _payload = load_amendment_authority(repo, required_amendment)
        if (
            approval.get("changeRequestId") == post.get("required_change_request_id")
            and approval.get("targetWave") == hold.get("target_wave")
            and approval.get("authorizedTaskIds") == post.get("required_proposed_task_ids")
            and [item.get("id") for item in packet.get("taskInventory", [])] == post.get("required_proposed_task_ids")
        ):
            return
    raise SystemExit(
        f"Governance recovery hold {hold.get('id')} denies this mutation. Complete independent "
        f"{bootstrap.get('id')} review and obtain separate exact approval for "
        f"{post.get('required_change_request_id')}/{required_amendment}; Wave/task/gate bypass is unavailable."
    )


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
    amrenew = ams.add_parser("renew")
    amrenew.add_argument("amendment")
    amrenew.add_argument("--agent", required=True)
    amrenew.add_argument("--lease-hours", type=int, default=24)
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
    recover = sub.add_parser("recover")
    recover.add_argument("task")
    recover.add_argument("--agent", required=True)
    recover.add_argument("--branch", required=True)
    recover.add_argument("--base-sha", required=True)
    recover.add_argument("--worktree", required=True)
    recover.add_argument("--profile", choices=sorted(ACTIVE_PROFILES), default="LOC")
    recover.add_argument("--platform", choices=sorted(PLATFORMS), default="windows-x64")
    recover.add_argument("--from", dest="from_file", required=True)
    recover.add_argument("--lease-hours", type=int, default=8)
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
    checks.add_argument(
        "--raw",
        action="store_true",
        help="print only the declared verification-command inventory for machine-compatible use",
    )
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
    reopen.add_argument(
        "--cascade-dependents",
        action="store_true",
        help="atomically demote completed dependent tasks for later revalidation",
    )
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
    args.source_wave_resume_history = wave_resume_history_snapshot(data)
    args.source_recovery_history = recovery_history_snapshot(data)
    args.source_released_recovery_holds = released_recovery_hold_snapshot(data)
    args.source_task_recovery_history = task_recovery_history_snapshot(data)
    args.repo_root = discover_repository(args.file)
    require_recovery_hold_permission(args, data, tasks, args.repo_root)
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
    elif args.command == "amendment" and args.amendment_command == "renew":
        command_amendment_renew(args, data, capabilities, slices, tasks, gates)
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
    elif args.command == "recover":
        command_recover(args, data, capabilities, slices, tasks, gates)
    elif args.command == "block":
        command_block(args, data, capabilities, slices, tasks, gates)
    elif args.command == "renew":
        command_renew(args, data, capabilities, slices, tasks, gates)
    elif args.command == "checks":
        task = get(tasks, args.task, "task")
        output = task.get("verification_commands", []) if args.raw else task_check_guidance(task)
        for command in output:
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
