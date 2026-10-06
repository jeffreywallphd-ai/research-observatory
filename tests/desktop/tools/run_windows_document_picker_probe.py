"""Exercise the real owned Windows document picker in the Tauri test fixture.

All inputs are synthetic and ignored. The external UIA helper verifies the
app-owned dialog, writes only the SHA-verified fixture path to its File name
control, and invokes one exact Open control. No renderer file/path/bytes API is
used. A missing fixture event, ambiguous control, or timeout is adverse evidence.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import queue
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import run_windows_document_drop_probe as drop

ACTION_WRAPPER = Path(__file__).with_name("windows_file_dialog_action.ps1")
DATABASE_VERIFIER = Path(__file__).with_name("verify_document_attachment_fixture.py")
SOURCE_NAME = "document-drop-source.txt"
OBSERVATION_MARKER = "inside"
UUID_V7 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
SELECTION_FIELDS = {
    "projectId",
    "workId",
    "workRevisionId",
    "versionId",
    "versionRevisionId",
    "sourceAssertionRevisionId",
}


def selection_ids(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != SELECTION_FIELDS:
        raise drop.ProbeFailure("picker-selection-shape-invalid")
    project = value["projectId"]
    if not isinstance(project, str):
        raise drop.ProbeFailure("picker-project-id-invalid")
    try:
        parsed = UUID(project)
    except TypeError, ValueError, AttributeError:
        raise drop.ProbeFailure("picker-project-id-invalid") from None
    if str(parsed) != project or parsed.version not in {4, 7}:
        raise drop.ProbeFailure("picker-project-id-invalid")
    if any(
        not isinstance(value[name], str) or not UUID_V7.fullmatch(value[name])
        for name in SELECTION_FIELDS - {"projectId"}
    ):
        raise drop.ProbeFailure("picker-selection-id-invalid")
    return value


def synthetic_source(fixture_root: Path) -> Path:
    source = fixture_root / "temporary" / SOURCE_NAME
    canonical_root = fixture_root.resolve(strict=True)
    canonical_source = source.resolve(strict=True)
    if canonical_source != canonical_root / "temporary" / SOURCE_NAME or not source.is_file() or source.is_symlink():
        raise drop.ProbeFailure("synthetic-source-location-invalid")
    if not 0 < source.stat().st_size <= 8192:
        raise drop.ProbeFailure("synthetic-source-size-invalid")
    if drop.file_hash(source) != drop.SYNTHETIC_SOURCE_SHA256:
        raise drop.ProbeFailure("synthetic-source-digest-mismatch")
    return source


def _exact_fixture_entry(path: Path, expected: Path, *, directory: bool) -> bool:
    metadata = path.lstat()
    if path.is_symlink() or getattr(metadata, "st_file_attributes", 0) & getattr(
        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
    ):
        return False
    kind_matches = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    return kind_matches and path.resolve(strict=True) == expected


def picker_source(fixture_root: Path) -> Path:
    """Verify the exact file admitted by the fixture's projects-only picker guard."""
    source = fixture_root / "projects" / SOURCE_NAME
    try:
        if (
            not _exact_fixture_entry(fixture_root, fixture_root, directory=True)
            or not _exact_fixture_entry(fixture_root / "projects", fixture_root / "projects", directory=True)
            or not _exact_fixture_entry(source, source, directory=False)
        ):
            raise drop.ProbeFailure("picker-source-location-invalid")
        if not 0 < source.stat().st_size <= 8192:
            raise drop.ProbeFailure("picker-source-size-invalid")
        if drop.file_hash(source) != drop.SYNTHETIC_SOURCE_SHA256:
            raise drop.ProbeFailure("picker-source-digest-mismatch")
    except OSError:
        raise drop.ProbeFailure("picker-source-location-invalid") from None
    except RuntimeError:
        raise drop.ProbeFailure("picker-source-location-invalid") from None
    return source


def prepare_picker_source(fixture_root: Path) -> Path:
    """Copy a verified seeded source into the test-owned picker admission root."""
    try:
        if (
            not _exact_fixture_entry(fixture_root, fixture_root, directory=True)
            or not _exact_fixture_entry(fixture_root / "temporary", fixture_root / "temporary", directory=True)
            or not _exact_fixture_entry(fixture_root / "projects", fixture_root / "projects", directory=True)
        ):
            raise drop.ProbeFailure("picker-source-fixture-invalid")
        seed = synthetic_source(fixture_root)
        if not _exact_fixture_entry(seed, seed, directory=False):
            raise drop.ProbeFailure("synthetic-source-location-invalid")
        target = fixture_root / "projects" / SOURCE_NAME
        if target.exists() or target.is_symlink():
            raise drop.ProbeFailure("picker-source-target-exists")
        payload = seed.read_bytes()
        if not 0 < len(payload) <= 8192 or hashlib.sha256(payload).hexdigest() != drop.SYNTHETIC_SOURCE_SHA256:
            raise drop.ProbeFailure("synthetic-source-digest-mismatch")
        with target.open("xb") as output:
            output.write(payload)
        selected = picker_source(fixture_root)
        if drop.file_hash(seed) != drop.SYNTHETIC_SOURCE_SHA256:
            raise drop.ProbeFailure("synthetic-source-digest-mismatch")
        return selected
    except OSError:
        raise drop.ProbeFailure("picker-source-copy-unavailable") from None
    except RuntimeError:
        raise drop.ProbeFailure("picker-source-copy-unavailable") from None


def require_exact_window(process: subprocess.Popen[str], ready: dict[str, Any]) -> dict[str, Any]:
    preflight = drop.window_preflight(process, ready)
    required = (
        "ownerPresent",
        "ownerVisible",
        "ownerPidMatches",
        "ownerTitleMatches",
        "ownerClassMatches",
        "foregroundRootMatches",
    )
    if not all(preflight[name] is True for name in required):
        raise drop.ProbeFailure("picker-owner-preflight-failed")
    if not preflight["insideHit"]["rootReached"] or not preflight["outsideHit"]["rootReached"]:
        raise drop.ProbeFailure("picker-owner-screen-hit-failed")
    return preflight


def dialog_action(action: str, owner_hwnd: int, owner_pid: int, fixture_root: Path, raw_file: Path) -> dict[str, Any]:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ACTION_WRAPPER),
        "-Action",
        action,
        "-OwnerHwnd",
        str(owner_hwnd),
        "-OwnerPid",
        str(owner_pid),
        "-TimeoutMilliseconds",
        "15000",
        "-FixtureRoot",
        str(fixture_root),
    ]
    try:
        # Exact dialog, file-name, Open and closure each have their own 15 s bound.
        completed = subprocess.run(command, capture_output=True, text=True, timeout=70, check=False)
    except subprocess.TimeoutExpired as timeout:

        def encoded(value: bytes | str | None) -> bytes:
            return value.encode("utf-8", errors="replace") if isinstance(value, str) else value or b""

        raw_file.write_bytes(encoded(timeout.stdout) + b"\n--- STDERR ---\n" + encoded(timeout.stderr))
        raise drop.ProbeFailure(f"picker-uia-watchdog-{action}") from None
    raw_file.write_text(
        completed.stdout + "\n--- STDERR ---\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise drop.ProbeFailure(f"picker-uia-process-failed-{action}")
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except IndexError, json.JSONDecodeError:
        raise drop.ProbeFailure(f"picker-uia-result-missing-{action}") from None
    if not isinstance(result, dict) or result.get("kind") != "windows-file-dialog-uia":
        raise drop.ProbeFailure(f"picker-uia-result-invalid-{action}")
    if result.get("action") != action or result.get("dialogExactOwnerAndPid") is not True:
        raise drop.ProbeFailure(f"picker-uia-owner-invalid-{action}")
    if result.get("failureCode") is not None:
        code = result["failureCode"]
        if not isinstance(code, str) or not re.fullmatch(r"[a-z-]{1,60}", code):
            code = "unclassified"
        raise drop.ProbeFailure(f"picker-uia-{code}-{action}")
    expected_status = "selected" if action == "select" else "cancelled"
    if result.get("status") != expected_status or result.get("dialogClosed") is not True:
        raise drop.ProbeFailure(f"picker-uia-incomplete-{action}")
    if action == "select" and (
        result.get("sourceDigestVerified") is not True or result.get("sourceSha256") != drop.SYNTHETIC_SOURCE_SHA256
    ):
        raise drop.ProbeFailure("picker-uia-source-unverified")
    return {"action": action, "status": result["status"], "rawSha256": drop.file_hash(raw_file)}


def native_counters(event: dict[str, Any]) -> dict[str, int]:
    observed = drop.counters(event, "native")
    names = ("oleEnter", "oleOver", "oleDrop", "heldStage", "candidate")
    if any(type(observed.get(name)) is not int for name in names):
        raise drop.ProbeFailure("picker-native-counter-missing")
    if not drop.no_renderer_values(drop.counters(event, "html5")) or not drop.no_renderer_values(
        drop.counters(event, "tauri")
    ):
        raise drop.ProbeFailure("picker-renderer-file-or-tauri-drag-observed")
    return {name: observed[name] for name in names}


def safe_picker_event(event: dict[str, Any]) -> dict[str, Any]:
    kind = event.get("kind")
    if kind == "document-attachment-probe-picker-action":
        if set(event) != {"kind", "status"} or event["status"] not in {
            "clicked",
            "reopening",
            "control-unavailable",
            "reopen-unavailable",
            "observer-unavailable",
            "eval-unavailable",
        }:
            raise drop.ProbeFailure("picker-action-shape-invalid")
    elif kind == "document-attachment-probe-picker-result":
        if set(event) != {"kind", "status", "operationId", "candidateId", "code"}:
            raise drop.ProbeFailure("picker-result-shape-invalid")
        if event["status"] not in {"selected", "cancelled", "rejected"}:
            raise drop.ProbeFailure("picker-result-status-invalid")
        if not isinstance(event["operationId"], str) or not UUID_V7.fullmatch(event["operationId"]):
            raise drop.ProbeFailure("picker-result-operation-invalid")
        candidate = event["candidateId"]
        if event["status"] == "selected":
            if not isinstance(candidate, str) or not UUID_V7.fullmatch(candidate):
                raise drop.ProbeFailure("picker-result-candidate-invalid")
        elif candidate is not None:
            raise drop.ProbeFailure("picker-result-unexpected-candidate")
        code = event["code"]
        if code is not None and (not isinstance(code, str) or not re.fullmatch(r"[a-z-]{1,40}", code)):
            raise drop.ProbeFailure("picker-result-code-invalid")
        if event["status"] in {"selected", "cancelled"} and code is not None:
            raise drop.ProbeFailure("picker-result-unexpected-code")
    elif kind == "document-attachment-probe-action-state":
        if set(event) != {
            "kind",
            "pickerAction",
            "commitAction",
            "candidateVisible",
            "paneVisible",
            "sourceSelected",
            "pickerControlCount",
            "pickerControlEnabled",
        }:
            raise drop.ProbeFailure("picker-action-state-shape-invalid")
        if event["pickerAction"] not in {
            None,
            "clicked",
            "reopening",
            "reopen-timeout",
            "source-unavailable",
        } or event["commitAction"] not in {
            None,
            "reviewing",
            "clicked",
            "control-timeout",
            "candidate-lost",
        }:
            raise drop.ProbeFailure("picker-action-state-value-invalid")
        if any(type(event[name]) is not bool for name in ("candidateVisible", "paneVisible", "sourceSelected")):
            raise drop.ProbeFailure("picker-action-state-boolean-invalid")
        if (
            type(event["pickerControlCount"]) is not int
            or not 0 <= event["pickerControlCount"] <= 32
            or type(event["pickerControlEnabled"]) is not bool
            or (event["pickerControlCount"] != 1 and event["pickerControlEnabled"])
        ):
            raise drop.ProbeFailure("picker-action-state-control-invalid")
    else:
        raise drop.ProbeFailure("picker-event-kind-invalid")
    return event


def safe_commit_event(event: dict[str, Any]) -> dict[str, Any]:
    kind = event.get("kind")
    if kind == "document-attachment-probe-commit-action":
        if set(event) != {"kind", "status"} or event["status"] not in {
            "reviewing",
            "candidate-unavailable",
            "observer-unavailable",
            "eval-unavailable",
        }:
            raise drop.ProbeFailure("picker-commit-action-shape-invalid")
    elif kind == "document-attachment-probe-commit":
        if event.get("status") == "unverified":
            if set(event) != {"kind", "status", "code"} or event["code"] not in {
                "fixture-unavailable",
                "identity-invalid",
                "receipt-unavailable",
            }:
                raise drop.ProbeFailure("picker-commit-rejection-shape-invalid")
        else:
            expected = {
                "kind",
                "status",
                "receiptSaved",
                "selectionIds",
                "operationId",
                "commandId",
                "candidateId",
                "attachmentId",
                "documentRevisionId",
            }
            if set(event) != expected or event["status"] != "attached" or event["receiptSaved"] is not True:
                raise drop.ProbeFailure("picker-commit-shape-invalid")
            selection_ids(event["selectionIds"])
            if any(
                not isinstance(event[name], str) or not UUID_V7.fullmatch(event[name])
                for name in (
                    "operationId",
                    "commandId",
                    "candidateId",
                    "attachmentId",
                    "documentRevisionId",
                )
            ):
                raise drop.ProbeFailure("picker-commit-id-invalid")
    else:
        raise drop.ProbeFailure("picker-commit-kind-invalid")
    return event


class StagePairEvents(Protocol):
    picker_results: list[dict[str, Any]]
    stage: list[dict[str, Any]]


class PickerReadout(Protocol):
    def readout(self) -> tuple[dict[str, Any], dict[str, Any]]: ...


def wait_for_picker_control(
    fixture: PickerReadout,
    *,
    timeout: float,
    observations: list[dict[str, Any]] | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        observed, state = fixture.readout()
        safe_picker_event(state)
        if observed.get("uiError") is not None or observed.get("uiPhase") != 8:
            raise drop.ProbeFailure("picker-control-ui-sequence-invalid")
        if observations is not None:
            observations.append(
                {
                    "paneVisible": state["paneVisible"],
                    "sourceSelected": state["sourceSelected"],
                    "pickerControlCount": state["pickerControlCount"],
                    "pickerControlEnabled": state["pickerControlEnabled"],
                }
            )
        if state["pickerControlCount"] > 1 or (state["pickerControlCount"] != 1 and state["pickerControlEnabled"]):
            raise drop.ProbeFailure("picker-control-ambiguous")
        if (
            state["paneVisible"] is True
            and state["sourceSelected"] is True
            and state["pickerControlCount"] == 1
            and state["pickerControlEnabled"] is True
        ):
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise drop.ProbeFailure("picker-control-readiness-timeout")
        time.sleep(min(0.25, remaining))


class FixtureEvents:
    def __init__(self, events: queue.Queue[dict[str, Any]], process: subprocess.Popen[str]) -> None:
        self.events = events
        self.process = process
        self.stage: list[dict[str, Any]] = []
        self.picker_actions: list[dict[str, Any]] = []
        self.picker_results: list[dict[str, Any]] = []
        self.action_states: list[dict[str, Any]] = []
        self.observations: list[dict[str, Any]] = []
        self.commit_actions: list[dict[str, Any]] = []
        self.commits: list[dict[str, Any]] = []
        self.ended: dict[str, Any] | None = None

    def _accept(self, event: dict[str, Any]) -> None:
        kind = event.get("kind")
        if kind in {"document-drop-probe-stage-finish", "document-drop-probe-stage-result"}:
            self.stage.append(drop.safe_stage_event(event))
        elif kind == "document-attachment-probe-picker-action":
            self.picker_actions.append(safe_picker_event(event))
        elif kind == "document-attachment-probe-picker-result":
            self.picker_results.append(safe_picker_event(event))
        elif kind == "document-attachment-probe-action-state":
            self.action_states.append(safe_picker_event(event))
        elif kind == "document-attachment-probe-commit-action":
            self.commit_actions.append(safe_commit_event(event))
        elif kind == "document-attachment-probe-commit":
            self.commits.append(safe_commit_event(event))
        elif kind == "document-drop-probe-observation":
            self.observations.append(event)
        elif kind == "document-drop-probe-end":
            self.ended = event
        elif kind in {"document-drop-probe-failure", "driver-invalid-fixture-jsonl", "driver-fixture-eof"}:
            raise drop.ProbeFailure(f"picker-fixture-{kind}")

    def wait(self, predicate: Any, timeout: float, label: str) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise drop.ProbeFailure(f"picker-timeout-{label}")
            try:
                event = self.events.get(timeout=min(0.25, remaining))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise drop.ProbeFailure(f"picker-fixture-exited-before-{label}") from None
                continue
            self._accept(event)

    def choose(self) -> str:
        previous = len(self.picker_actions)
        drop.send(self.process, {"action": "choose"})
        self.wait(lambda: len(self.picker_actions) > previous, 20, "choose-action")
        if len(self.picker_actions) != previous + 1:
            raise drop.ProbeFailure("picker-choose-action-duplicate")
        status = self.picker_actions[-1]["status"]
        if status not in {"clicked", "reopening"}:
            raise drop.ProbeFailure(f"picker-choose-{status}")
        return status

    def commit_project_only(self) -> None:
        previous = len(self.commit_actions)
        drop.send(self.process, {"action": "commit-project-only"})
        self.wait(lambda: len(self.commit_actions) > previous, 20, "commit-action")
        if len(self.commit_actions) != previous + 1 or self.commit_actions[-1]["status"] != "reviewing":
            raise drop.ProbeFailure("picker-commit-action-denied")

    def readout(self) -> tuple[dict[str, Any], dict[str, Any]]:
        before_observations = len(self.observations)
        before_states = len(self.action_states)
        drop.send(self.process, {"action": "observe", "attempt": OBSERVATION_MARKER})
        self.wait(
            lambda: len(self.observations) > before_observations and len(self.action_states) > before_states,
            20,
            "readout",
        )
        if len(self.observations) != before_observations + 1 or len(self.action_states) != before_states + 1:
            raise drop.ProbeFailure("picker-readout-duplicate")
        observation, state = self.observations[-1], self.action_states[-1]
        if (
            observation.get("attempt") != OBSERVATION_MARKER
            or observation.get("uiError") is not None
            or observation.get("uiPhase") != 8
        ):
            raise drop.ProbeFailure("picker-observation-invalid")
        native_counters(observation)
        return observation, state


def exact_stage_pair(
    fixture: StagePairEvents,
    *,
    stage_start: int,
    picker_start: int,
    expected_status: str,
) -> tuple[str, str | None] | None:
    picker_results = fixture.picker_results[picker_start:]
    stage = fixture.stage[stage_start:]
    if len(picker_results) > 1 or len(stage) > 2:
        raise drop.ProbeFailure("picker-operation-result-duplicate")
    expected_stage_status = "candidate" if expected_status == "selected" else "cancelled"
    if any(item["status"] != expected_stage_status for item in stage):
        raise drop.ProbeFailure("picker-stage-unexpected-status")
    if not picker_results:
        return None
    marker = picker_results[0]
    if marker["status"] != expected_status:
        raise drop.ProbeFailure(f"picker-operation-{marker['status']}")
    if any(item["operationId"] != marker["operationId"] or item["status"] != expected_stage_status for item in stage):
        raise drop.ProbeFailure("picker-stage-operation-or-status-mismatch")
    if any(item["candidateId"] != marker["candidateId"] or item["code"] is not None for item in stage):
        raise drop.ProbeFailure("picker-stage-candidate-or-code-mismatch")
    if len(stage) < 2:
        return None
    if {item["kind"] for item in stage} != {
        "document-drop-probe-stage-result",
        "document-drop-probe-stage-finish",
    }:
        raise drop.ProbeFailure("picker-stage-pair-invalid")
    finish = next(item for item in stage if item["kind"] == "document-drop-probe-stage-finish")
    if (
        finish["protectedClosureEntered"] is not True
        or finish["protectedCommitSucceeded"] is not True
        or finish["eventEmitSucceeded"] is not True
        or finish["deliveryCode"] is not None
    ):
        raise drop.ProbeFailure("picker-stage-delivery-incomplete")
    return marker["operationId"], marker["candidateId"]


def wait_for_picker_outcome(
    fixture: FixtureEvents,
    *,
    action: str,
    stage_start: int,
    picker_start: int,
    initial: dict[str, int],
    timeout: float,
    observations: list[dict[str, Any]],
) -> tuple[str, str | None]:
    deadline = time.monotonic() + timeout
    while True:
        observed, state = fixture.readout()
        current = native_counters(observed)
        observations.append({"native": current, "actionState": state})
        if any(current[name] != initial[name] for name in ("oleEnter", "oleOver", "oleDrop", "heldStage")):
            raise drop.ProbeFailure(f"picker-unexpected-ole-activity-{action}")
        candidate_delta = current["candidate"] - initial["candidate"]
        if (action == "cancel" and candidate_delta != 0) or (action == "select" and candidate_delta not in {0, 1}):
            raise drop.ProbeFailure(f"picker-native-candidate-count-invalid-{action}")
        pair = exact_stage_pair(
            fixture,
            stage_start=stage_start,
            picker_start=picker_start,
            expected_status="cancelled" if action == "cancel" else "selected",
        )
        if action == "cancel":
            if state["candidateVisible"]:
                raise drop.ProbeFailure("picker-cancellation-visible-candidate")
            ui_ready = state["paneVisible"] is False
        else:
            if state["pickerAction"] in {"reopen-timeout", "source-unavailable"}:
                raise drop.ProbeFailure(f"picker-reopen-{state['pickerAction']}")
            ui_ready = (
                state["pickerAction"] == "clicked"
                and state["candidateVisible"] is True
                and state["paneVisible"] is True
                and state["sourceSelected"] is True
            )
        if pair is not None and ui_ready and (action == "cancel" or candidate_delta == 1):
            return pair
        if time.monotonic() >= deadline:
            raise drop.ProbeFailure(f"picker-{action}-outcome-timeout")
        time.sleep(1)


def wait_for_commit(
    fixture: FixtureEvents,
    *,
    selection: dict[str, str],
    operation_id: str,
    candidate_id: str,
    initial: dict[str, int],
    timeout: float,
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        observed, state = fixture.readout()
        current = native_counters(observed)
        observations.append({"native": current, "actionState": state})
        if any(current[name] != initial[name] for name in ("oleEnter", "oleOver", "oleDrop", "heldStage")):
            raise drop.ProbeFailure("picker-commit-unexpected-ole-activity")
        if current["candidate"] != initial["candidate"] + 1:
            raise drop.ProbeFailure("picker-commit-candidate-count-changed")
        if state["commitAction"] in {"control-timeout", "candidate-lost"}:
            raise drop.ProbeFailure(f"picker-commit-{state['commitAction']}")
        if len(fixture.commits) > 1:
            raise drop.ProbeFailure("picker-commit-result-duplicate")
        if fixture.commits:
            committed = fixture.commits[0]
            if committed["status"] == "unverified":
                raise drop.ProbeFailure(f"picker-commit-{committed['code']}")
            if (
                committed["selectionIds"] != selection
                or committed["operationId"] != operation_id
                or committed["candidateId"] != candidate_id
            ):
                raise drop.ProbeFailure("picker-commit-selection-or-operation-mismatch")
            if state["commitAction"] == "clicked":
                return committed
        if time.monotonic() >= deadline:
            raise drop.ProbeFailure("picker-commit-timeout")
        time.sleep(1)


def exact_commit_receipt(fixture_root: Path, expected: dict[str, Any]) -> str:
    receipt = fixture_root / "t01-document-commit.json"
    if not receipt.is_file() or receipt.is_symlink() or receipt.resolve(strict=True) != receipt:
        raise drop.ProbeFailure("picker-commit-receipt-unavailable")
    if not 0 < receipt.stat().st_size <= 4096:
        raise drop.ProbeFailure("picker-commit-receipt-size-invalid")
    try:
        parsed = json.loads(receipt.read_text(encoding="utf-8"))
    except OSError, UnicodeError, ValueError:
        raise drop.ProbeFailure("picker-commit-receipt-invalid") from None
    required = {
        "schemaVersion",
        "selection",
        "operationId",
        "commandId",
        "candidateId",
        "attachmentId",
        "documentRevisionId",
    }
    if (
        not isinstance(parsed, dict)
        or set(parsed) != required
        or parsed["schemaVersion"] != "1.0"
        or parsed["selection"] != expected["selectionIds"]
        or any(parsed[name] != expected[name] for name in required - {"schemaVersion", "selection"})
    ):
        raise drop.ProbeFailure("picker-commit-receipt-identity-mismatch")
    return drop.file_hash(receipt)


def verify_database(
    fixture_root: Path,
    selection: dict[str, str],
    committed: dict[str, Any],
    raw_file: Path,
) -> dict[str, Any]:
    args = [
        sys.executable,
        str(DATABASE_VERIFIER),
        "--fixture-root",
        str(fixture_root),
        "--project-id",
        selection["projectId"],
        "--work-id",
        selection["workId"],
        "--work-revision-id",
        selection["workRevisionId"],
        "--version-id",
        selection["versionId"],
        "--version-revision-id",
        selection["versionRevisionId"],
        "--source-assertion-revision-id",
        selection["sourceAssertionRevisionId"],
        "--source-sha256",
        drop.SYNTHETIC_SOURCE_SHA256,
        "--operation-id",
        committed["operationId"],
        "--command-id",
        committed["commandId"],
        "--candidate-id",
        committed["candidateId"],
        "--attachment-id",
        committed["attachmentId"],
        "--document-revision-id",
        committed["documentRevisionId"],
    ]
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as timeout:

        def encoded(value: bytes | str | None) -> bytes:
            return value.encode("utf-8", errors="replace") if isinstance(value, str) else value or b""

        raw_file.write_bytes(encoded(timeout.stdout) + b"\n--- STDERR ---\n" + encoded(timeout.stderr))
        raise drop.ProbeFailure("picker-database-verifier-timeout") from None
    raw_file.write_text(completed.stdout + "\n--- STDERR ---\n" + completed.stderr, encoding="utf-8")
    try:
        value = json.loads(completed.stdout.strip().splitlines()[-1])
    except IndexError, ValueError:
        raise drop.ProbeFailure("picker-database-verifier-output-invalid") from None
    if not isinstance(value, dict) or value.get("schemaVersion") != "1.0":
        raise drop.ProbeFailure("picker-database-verifier-output-invalid")
    if completed.returncode != 0 or value.get("status") != "passed":
        code = value.get("failureCode")
        if not isinstance(code, str) or not re.fullmatch(r"[a-z-]{1,80}", code):
            code = "unclassified"
        raise drop.ProbeFailure(f"picker-database-{code}")
    if (
        value.get("projectId") != selection["projectId"]
        or value.get("workId") != selection["workId"]
        or value.get("versionId") != selection["versionId"]
        or value.get("sourceAssertionRevisionId") != selection["sourceAssertionRevisionId"]
        or value.get("operationId") != committed["operationId"]
        or value.get("commandId") != committed["commandId"]
        or value.get("candidateId") != committed["candidateId"]
        or value.get("attachmentId") != committed["attachmentId"]
        or value.get("documentRevisionId") != committed["documentRevisionId"]
        or value.get("objectSha256") != drop.SYNTHETIC_SOURCE_SHA256
        or value.get("reopenedStatus") != "committed"
    ):
        raise drop.ProbeFailure("picker-database-verifier-identity-mismatch")
    return value


def run_resume(
    app_binary: Path,
    nonce: str,
    environment: dict[str, str],
    stem: str,
    fixture_root: Path,
    selection: dict[str, str],
    committed: dict[str, Any],
    result: dict[str, Any],
) -> None:
    stdout_file = drop.SCRATCH / f"{stem}.resume.fixture.jsonl"
    stderr_file = drop.SCRATCH / f"{stem}.resume.fixture.stderr.log"
    events: queue.Queue[dict[str, Any]] = queue.Queue()
    resume = result["resume"] = {"status": "incomplete"}
    seed_receipt = fixture_root / "t01-document-seed.json"
    if not seed_receipt.is_file() or seed_receipt.is_symlink():
        raise drop.ProbeFailure("picker-seed-receipt-unavailable")
    seed_before = drop.file_hash(seed_receipt)
    commit_before = exact_commit_receipt(fixture_root, committed)
    process: subprocess.Popen[str] | None = None
    ready: dict[str, Any] | None = None
    status: dict[str, Any] | None = None
    started: dict[str, Any] | None = None
    ended: dict[str, Any] | None = None

    def accept(event: dict[str, Any]) -> None:
        nonlocal ready, status, started, ended
        kind = event.get("kind")
        if kind == "tauri-directory-start":
            if started is not None:
                raise drop.ProbeFailure("picker-resume-start-duplicate")
            started = event
        elif kind == "document-attachment-probe-resume-ready":
            if ready is not None or set(event) != {
                "kind",
                "selectionIds",
                "resumedOriginalFixture",
                "reseeding",
            }:
                raise drop.ProbeFailure("picker-resume-ready-invalid")
            ready = event
        elif kind == "document-attachment-probe-resume-status":
            expected = {
                "kind",
                "status",
                "exact",
                "selectionIds",
                "operationId",
                "commandId",
                "candidateId",
                "attachmentId",
                "documentRevisionId",
            }
            if status is not None or set(event) != expected:
                raise drop.ProbeFailure("picker-resume-status-shape-invalid")
            status = event
        elif kind == "document-drop-probe-end":
            ended = event
        elif kind == "document-attachment-probe-resume-failure":
            code = event.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[a-z-]{1,40}", code):
                code = "unclassified"
            raise drop.ProbeFailure(f"picker-resume-{code}")
        elif kind in {
            "document-drop-probe-stage-result",
            "document-drop-probe-stage-finish",
            "document-drop-probe-native-decision",
            "document-drop-probe-armed",
            "document-drop-probe-observation",
            "document-attachment-probe-picker-result",
            "document-attachment-probe-commit",
        }:
            raise drop.ProbeFailure("picker-resume-new-stage-or-drag-event")
        elif kind in {"document-drop-probe-failure", "driver-invalid-fixture-jsonl", "driver-fixture-eof"}:
            raise drop.ProbeFailure(f"picker-resume-{kind}")

    def await_resume(predicate: Any, timeout: float, label: str) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise drop.ProbeFailure(f"picker-resume-timeout-{label}")
            try:
                event = events.get(timeout=min(0.25, remaining))
            except queue.Empty:
                if process is not None and process.poll() is not None:
                    raise drop.ProbeFailure(f"picker-resume-exited-before-{label}") from None
                continue
            accept(event)

    with stderr_file.open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.Popen(
                [str(app_binary), "--tauri-directory", "document-drop-resume", nonce],
                cwd=drop.ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=environment,
            )
            threading.Thread(target=drop.read_events, args=(process, stdout_file, events), daemon=True).start()
            await_resume(lambda: ready is not None, 160, "ready")
            if (
                started is None
                or started.get("mode") != "document-drop-resume"
                or started.get("fixture") != f"artifacts/tmp/directory-dialog-{nonce}"
                or type(started.get("ownerHwnd")) is not int
                or started["ownerHwnd"] == 0
                or ready is None
                or ready["selectionIds"] != selection
                or ready["resumedOriginalFixture"] is not True
                or ready["reseeding"] is not False
            ):
                raise drop.ProbeFailure("picker-resume-fixture-identity-invalid")
            resume["ready"] = ready
            await_resume(lambda: status is not None, 190, "status")
            if status is None or status["status"] not in {"processing", "available"} or status["exact"] is not True:
                raise drop.ProbeFailure("picker-resume-status-not-exact")
            if status["selectionIds"] != selection or any(
                status[name] != committed[name]
                for name in ("operationId", "commandId", "candidateId", "attachmentId", "documentRevisionId")
            ):
                raise drop.ProbeFailure("picker-resume-status-identity-mismatch")
            resume["statusEvent"] = status
        finally:
            if process is not None:
                try:
                    drop.send(process, {"action": "close"})
                    await_resume(lambda: ended is not None, 20, "end")
                    if ended is None or ended.get("exitCode") != 0 or process.wait(timeout=10) != 0:
                        raise drop.ProbeFailure("picker-resume-exit-incomplete")
                except drop.ProbeFailure, OSError, ValueError, subprocess.TimeoutExpired:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    resume["cleanupFailureCode"] = "picker-resume-close-incomplete"
                if process.stdin is not None:
                    with contextlib.suppress(OSError):
                        process.stdin.close()
                resume["fixtureReturnCode"] = process.returncode
            resume["fixtureJsonlSha256"] = drop.file_hash(stdout_file) if stdout_file.exists() else None
            resume["fixtureStderrSha256"] = drop.file_hash(stderr_file)
    if resume.get("cleanupFailureCode") is not None or ended is None:
        raise drop.ProbeFailure("picker-resume-close-incomplete")
    native = drop.counters(ended, "native")
    counter_names = ("oleEnter", "oleOver", "oleDrop", "heldStage", "candidate")
    if any(type(native.get(name)) is not int or native[name] != 0 for name in counter_names):
        raise drop.ProbeFailure("picker-resume-native-drag-or-candidate-observed")
    if drop.file_hash(seed_receipt) != seed_before or exact_commit_receipt(fixture_root, committed) != commit_before:
        raise drop.ProbeFailure("picker-resume-receipt-changed")
    resume["seedReceiptSha256"] = seed_before
    resume["commitReceiptSha256"] = commit_before
    resume["native"] = {name: native[name] for name in counter_names}
    resume["status"] = "passed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-exe", type=Path, required=True)
    parser.add_argument("--app-sha256", required=True)
    parser.add_argument("--worker-build", type=Path, required=True)
    parser.add_argument("--guardian-exe", type=Path, required=True)
    parser.add_argument("--guardian-sha256", required=True)
    parser.add_argument("--candidate-wait-seconds", type=int, default=190)
    parser.add_argument("--nonce", default=f"drop-picker-{secrets.token_hex(6)}")
    parser.add_argument("--require-five-target-install", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"drop-[A-Za-z0-9-]{1,60}", args.nonce):
        raise SystemExit("picker-nonce-invalid")
    if not 1 <= args.candidate_wait_seconds <= 190:
        raise SystemExit("picker-candidate-wait-invalid")
    drop.SCRATCH.mkdir(parents=True, exist_ok=True)
    fixture_root = drop.SCRATCH / f"directory-dialog-{args.nonce}"
    if fixture_root.exists():
        raise SystemExit("picker-fixture-already-exists")
    drop.exact_fixture_title_contract()
    app_binary = drop.exact_binary(args.app_exe)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.app_sha256) or drop.file_hash(app_binary) != args.app_sha256.lower():
        raise SystemExit("picker-app-binary-digest-mismatch")
    signed_worker, guardian = drop.qualification_inputs(args.worker_build, args.guardian_exe, args.guardian_sha256)
    drop.current_cursor(drop.cursor_api()[0])  # Confirm an interactive desktop before opening the app.
    stem = f"CAP-05.S01.T01.picker-{args.nonce}"
    stdout_file = drop.SCRATCH / f"{stem}.fixture.jsonl"
    stderr_file = drop.SCRATCH / f"{stem}.fixture.stderr.log"
    result_file = drop.SCRATCH / f"{stem}.result.json"
    events: queue.Queue[dict[str, Any]] = queue.Queue()
    result: dict[str, Any] = {
        "schemaVersion": "1.0",
        "kind": "built-tauri-real-windows-document-picker",
        "status": "incomplete",
        "binarySha256": drop.file_hash(app_binary),
        "signedWorkerInventorySha256": drop.file_hash(signed_worker / "inventory.json"),
        "signedWorkerSignatureSha256": drop.file_hash(signed_worker / "inventory.sig"),
        "guardianSha256": args.guardian_sha256.lower(),
        "syntheticSourceSha256": drop.SYNTHETIC_SOURCE_SHA256,
        "windowPreflights": [],
        "dialogActions": [],
        "stageEvents": [],
        "pickerActions": [],
        "pickerResults": [],
        "pickerReadinessObservations": [],
        "selectedCandidateObservations": [],
        "cancelObservations": [],
        "commitActions": [],
        "commitEvents": [],
        "commitObservations": [],
        "databaseVerifications": [],
    }
    stage_events = result["stageEvents"]
    process: subprocess.Popen[str] | None = None
    fixture: FixtureEvents | None = None
    selection: dict[str, str] | None = None
    committed: dict[str, Any] | None = None
    environment = os.environ.copy()
    environment["RO_W2_SIGNED_WORKER_BUILD"] = str(signed_worker)
    environment["RO_W2_CORE_SIDECAR_GUARDIAN"] = str(guardian)
    environment["RO_W2_CORE_SIDECAR_GUARDIAN_SHA256"] = args.guardian_sha256.lower()
    with stderr_file.open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.Popen(
                [
                    str(app_binary),
                    "--tauri-directory",
                    "document-drop-five" if args.require_five_target_install else "document-drop",
                    args.nonce,
                ],
                cwd=drop.ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=environment,
            )
            reader = threading.Thread(target=drop.read_events, args=(process, stdout_file, events), daemon=True)
            reader.start()
            if args.require_five_target_install:
                result["fiveTargetInstallation"] = drop.safe_five_install(
                    drop.await_event(events, process, "document-drop-probe-five-install", 125, stage_events)
                )
            ready = drop.await_event(events, process, "document-drop-probe-ready", 125, stage_events)
            if ready.get("armed") is not False or ready.get("observationInstalled") is not True:
                raise drop.ProbeFailure("picker-fixture-not-ready")
            if stage_events:
                raise drop.ProbeFailure("picker-stage-event-before-ready")
            fixture = FixtureEvents(events, process)
            result["stageEvents"] = fixture.stage
            result["pickerActions"] = fixture.picker_actions
            result["pickerResults"] = fixture.picker_results
            result["commitActions"] = fixture.commit_actions
            result["commitEvents"] = fixture.commits
            prepare_picker_source(fixture_root)
            initial = native_counters(ready)
            if any(initial.values()):
                raise drop.ProbeFailure("picker-fixture-native-counters-not-zero")
            selection = selection_ids(ready.get("selectionIds"))
            result["selectionIds"] = selection
            owner = ready.get("ownerHwnd")
            if type(owner) is not int or owner == 0:
                raise drop.ProbeFailure("picker-owner-unavailable")
            operation_ids: list[str] = []
            for action in ("cancel", "select"):
                stage_start = len(fixture.stage)
                picker_start = len(fixture.picker_results)
                result["windowPreflights"].append({"action": action, **require_exact_window(process, ready)})
                if action == "cancel":
                    wait_for_picker_control(
                        fixture,
                        timeout=20,
                        observations=result["pickerReadinessObservations"],
                    )
                choose_status = fixture.choose()
                if choose_status != ("clicked" if action == "cancel" else "reopening"):
                    raise drop.ProbeFailure(f"picker-unexpected-choose-state-{action}")
                raw_file = drop.SCRATCH / f"{stem}.{action}.uia.raw.log"
                result["dialogActions"].append(dialog_action(action, owner, process.pid, fixture_root, raw_file))
                if action == "select":
                    synthetic_source(fixture_root)
                    picker_source(fixture_root)
                observations = (
                    result["cancelObservations"] if action == "cancel" else result["selectedCandidateObservations"]
                )
                operation_id, candidate_id = wait_for_picker_outcome(
                    fixture,
                    action=action,
                    stage_start=stage_start,
                    picker_start=picker_start,
                    initial=initial,
                    timeout=30 if action == "cancel" else args.candidate_wait_seconds,
                    observations=observations,
                )
                if operation_id in operation_ids:
                    raise drop.ProbeFailure("picker-operation-reused")
                operation_ids.append(operation_id)
                if action == "cancel":
                    if candidate_id is not None:
                        raise drop.ProbeFailure("picker-cancellation-created-candidate")
                    result["cancelOperationId"] = operation_id
                    result["cancelNoCandidate"] = True
                    continue
                if candidate_id is None:
                    raise drop.ProbeFailure("picker-selected-candidate-missing")
                result["selectedOperationId"] = operation_id
                result["candidateId"] = candidate_id
            fixture.commit_project_only()
            committed = wait_for_commit(
                fixture,
                selection=selection,
                operation_id=result["selectedOperationId"],
                candidate_id=result["candidateId"],
                initial=initial,
                timeout=args.candidate_wait_seconds,
                observations=result["commitObservations"],
            )
            result["commitReceiptSha256"] = exact_commit_receipt(fixture_root, committed)
        except (drop.ProbeFailure, OSError, ValueError) as error:
            result["failureCode"] = str(error) if isinstance(error, drop.ProbeFailure) else "picker-driver-os-error"
        finally:
            if process is not None:
                try:
                    drop.send(process, {"action": "close"})
                    ended: dict[str, Any] | None
                    if fixture is None:
                        ended = drop.await_event(events, process, "document-drop-probe-end", 20, stage_events)
                    else:
                        fixture.wait(lambda: fixture.ended is not None, 20, "end")
                        ended = fixture.ended
                    if ended is None:
                        raise drop.ProbeFailure("picker-fixture-end-missing")
                    if ended.get("exitCode") != 0 or process.wait(timeout=10) != 0:
                        raise drop.ProbeFailure("picker-fixture-exit-incomplete")
                except drop.ProbeFailure, OSError, ValueError, subprocess.TimeoutExpired:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    if result["status"] == "passed":
                        result["status"] = "incomplete"
                        result["failureCode"] = "picker-fixture-close-incomplete"
                if process.stdin is not None:
                    with contextlib.suppress(OSError):
                        process.stdin.close()
                result["fixtureReturnCode"] = process.returncode
    if "failureCode" not in result:
        if (
            fixture is None
            or selection is None
            or committed is None
            or len(fixture.picker_actions) != 2
            or len(fixture.picker_results) != 2
            or len(fixture.stage) != 4
            or len(fixture.commit_actions) != 1
            or len(fixture.commits) != 1
        ):
            result["failureCode"] = "picker-final-event-count-invalid"
        elif fixture.ended is None or result.get("fixtureReturnCode") != 0:
            result["failureCode"] = "picker-fixture-close-incomplete"
        else:
            try:
                end_native = drop.counters(fixture.ended, "native")
                if (
                    any(
                        type(end_native.get(name)) is not int or end_native[name] != 0
                        for name in (
                            "oleEnter",
                            "oleOver",
                            "oleDrop",
                            "heldStage",
                        )
                    )
                    or type(end_native.get("candidate")) is not int
                    or end_native["candidate"] != 1
                ):
                    raise drop.ProbeFailure("picker-final-native-counters-invalid")
                before_raw = drop.SCRATCH / f"{stem}.before-resume.database.raw.log"
                before = verify_database(fixture_root, selection, committed, before_raw)
                result["databaseVerifications"].append({"phase": "before-resume", **before})
                run_resume(app_binary, args.nonce, environment, stem, fixture_root, selection, committed, result)
                after_raw = drop.SCRATCH / f"{stem}.after-resume.database.raw.log"
                after = verify_database(fixture_root, selection, committed, after_raw)
                result["databaseVerifications"].append({"phase": "after-resume", **after})
                if before != after:
                    raise drop.ProbeFailure("picker-database-restart-drift")
                result["status"] = "passed"
            except (drop.ProbeFailure, OSError, ValueError) as error:
                result["failureCode"] = str(error) if isinstance(error, drop.ProbeFailure) else "picker-driver-os-error"
    result["fixtureJsonlSha256"] = drop.file_hash(stdout_file) if stdout_file.exists() else None
    result["fixtureStderrSha256"] = drop.file_hash(stderr_file)
    result["dialogRawSha256"] = {
        action: drop.file_hash(raw_file)
        for action in ("cancel", "select")
        if (raw_file := drop.SCRATCH / f"{stem}.{action}.uia.raw.log").exists()
    }
    result["databaseRawSha256"] = {
        phase: drop.file_hash(raw_file)
        for phase in ("before-resume", "after-resume")
        if (raw_file := drop.SCRATCH / f"{stem}.{phase}.database.raw.log").exists()
    }
    result_file.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
