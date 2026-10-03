"""Run a bounded real Windows OLE drop against the built Tauri test fixture.

The fixture seeds one synthetic protected project, opens the actual product pane,
and emits native-computed screen points. This driver supplies an independent OS
CF_HDROP source; it never calls a product drop command or sends WM_DROPFILES.
Raw paths and runtime logs stay in ignored artifacts/tmp. A timeout or missing
observation is adverse evidence, never a pass.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import json
import os
import queue
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = ROOT / "artifacts" / "tmp"
SOURCE_WRAPPER = Path(__file__).with_name("windows_ole_file_drag.ps1")
APP_NAME = "project_contract_probe.exe"
EXPECTED_FIXTURE_WINDOW_TITLE = "Research Observatory — SYNTHETIC T01 document-drop"
SYNTHETIC_SOURCE_SHA256 = "b83fc32249fefc9f92520155a0f78353d02a23365d582bb39bc060c096890d91"
ATTEMPTS = (
    ("inside-disarmed", "insideScreen"),
    ("outside-armed", "outsideScreen"),
    ("inside", "insideScreen"),
)


class ProbeFailure(Exception):
    pass


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MonitorInfo(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint), ("monitor", Rect), ("work", Rect), ("flags", ctypes.c_uint)]


def cursor_api() -> tuple[Any, Any]:
    if os.name != "nt":
        raise ProbeFailure("windows-required")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_cursor = user32.GetCursorPos
    get_cursor.argtypes = [ctypes.POINTER(Point)]
    get_cursor.restype = ctypes.c_int
    set_cursor = user32.SetCursorPos
    set_cursor.argtypes = [ctypes.c_int, ctypes.c_int]
    set_cursor.restype = ctypes.c_int
    return get_cursor, set_cursor


def current_cursor(get_cursor: Any) -> Point:
    point = Point()
    if not get_cursor(ctypes.byref(point)):
        raise ProbeFailure(f"interactive-cursor-unavailable-win32-{ctypes.get_last_error()}")
    return point


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_binary(candidate: Path) -> Path:
    expected = (ROOT / "target" / "debug" / "examples" / APP_NAME).resolve()
    actual = candidate.resolve(strict=True)
    if actual != expected or not actual.is_file():
        raise ProbeFailure("built-fixture-binary-not-exact")
    return actual


def exact_fixture_title_contract() -> None:
    source = (ROOT / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
    required = (
        'builder.title(format!("Research Observatory — SYNTHETIC {} {}",',
        'else if mode.is_document_attachment() { "T01" }',
        'Self::DocumentDrop => "document-drop",',
    )
    if EXPECTED_FIXTURE_WINDOW_TITLE != "Research Observatory — SYNTHETIC T01 document-drop" or any(
        fragment not in source for fragment in required
    ):
        raise ProbeFailure("fixture-title-contract-changed")


def qualification_inputs(worker_build: Path, guardian: Path, guardian_sha256: str) -> tuple[Path, Path]:
    worker_build = worker_build.resolve(strict=True)
    guardian = guardian.resolve(strict=True)
    scratch = SCRATCH.resolve(strict=True)
    if scratch not in worker_build.parents or scratch not in guardian.parents:
        raise ProbeFailure("qualification-input-outside-ignored-scratch")
    if (
        not worker_build.is_dir()
        or not (worker_build / "package").is_dir()
        or not (worker_build / "inventory.json").is_file()
        or not (worker_build / "inventory.sig").is_file()
    ):
        raise ProbeFailure("signed-worker-build-incomplete")
    if not guardian.is_file():
        raise ProbeFailure("frozen-guardian-unavailable")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", guardian_sha256) or file_hash(guardian) != guardian_sha256.lower():
        raise ProbeFailure("frozen-guardian-digest-mismatch")
    return worker_build, guardian


def read_events(process: subprocess.Popen[str], output: Path, events: queue.Queue[dict[str, Any]]) -> None:
    assert process.stdout is not None
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for line in process.stdout:
            stream.write(line)
            stream.flush()
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("event-not-object")
                events.put(item)
            except ValueError, json.JSONDecodeError:
                events.put({"kind": "driver-invalid-fixture-jsonl"})
    events.put({"kind": "driver-fixture-eof"})


def await_event(
    events: queue.Queue[dict[str, Any]],
    process: subprocess.Popen[str],
    kind: str,
    timeout: float,
    stage_events: list[dict[str, Any]],
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
        except queue.Empty:
            if process.poll() is not None:
                raise ProbeFailure(f"fixture-exited-before-{kind}") from None
            continue
        if event.get("kind") == kind:
            return event
        if event.get("kind") in {"document-drop-probe-stage-finish", "document-drop-probe-stage-result"}:
            stage_events.append(safe_stage_event(event))
            continue
        if event.get("kind") == "document-drop-probe-failure":
            raise ProbeFailure(f"fixture-reported-failure-before-{kind}")
        if event.get("kind") == "driver-fixture-eof":
            try:
                code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                raise ProbeFailure(f"fixture-stdout-closed-before-{kind}") from None
            raise ProbeFailure(f"fixture-eof-before-{kind}-ntstatus-0x{code & 0xFFFFFFFF:08X}")
        if event.get("kind") == "driver-invalid-fixture-jsonl":
            raise ProbeFailure(f"fixture-output-failed-before-{kind}")
    raise ProbeFailure(f"fixture-timeout-before-{kind}")


def safe_stage_event(event: dict[str, Any]) -> dict[str, Any]:
    kind = event.get("kind")
    common = {"kind", "operationId", "status", "code", "candidateId"}
    finish = {"protectedClosureEntered", "protectedCommitSucceeded", "eventEmitSucceeded", "deliveryCode"}
    if kind == "document-drop-probe-stage-finish":
        if set(event) != common | finish:
            raise ProbeFailure("stage-finish-shape-invalid")
        if any(type(event[name]) is not bool for name in finish - {"deliveryCode"}):
            raise ProbeFailure("stage-finish-boolean-invalid")
        if event["deliveryCode"] not in {
            None,
            "lock-denied",
            "session-denied",
            "operation-denied",
            "event-failed",
            "state-unavailable",
            "other-denied",
        }:
            raise ProbeFailure("stage-finish-delivery-code-invalid")
        allowed_status = {"candidate", "rejected", "cancelled", "unavailable"}
    elif kind == "document-drop-probe-stage-result":
        if set(event) != common:
            raise ProbeFailure("stage-result-shape-invalid")
        allowed_status = {"candidate", "rejected", "cancelled"}
    else:
        raise ProbeFailure("stage-event-kind-invalid")
    if event["status"] not in allowed_status:
        raise ProbeFailure("stage-event-status-invalid")
    if not isinstance(event["operationId"], str) or not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", event["operationId"]
    ):
        raise ProbeFailure("stage-event-operation-id-invalid")
    candidate_id = event["candidateId"]
    if candidate_id is not None and (
        not isinstance(candidate_id, str)
        or not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", candidate_id)
    ):
        raise ProbeFailure("stage-event-candidate-id-invalid")
    if event["status"] == "candidate" and candidate_id is None:
        raise ProbeFailure("stage-event-candidate-id-missing")
    code = event["code"]
    if code is not None and (not isinstance(code, str) or not re.fullmatch(r"[a-z-]{1,40}", code)):
        raise ProbeFailure("stage-event-code-invalid")
    return event


def stage_failure(stage_events: list[dict[str, Any]]) -> str | None:
    for event in stage_events:
        if event["status"] != "candidate":
            return f"stage-{event['status']}-{event['code'] or 'no-code'}"
        if event["kind"] == "document-drop-probe-stage-finish" and (
            not event["protectedCommitSucceeded"] or not event["eventEmitSucceeded"]
        ):
            return f"stage-delivery-{event['deliveryCode'] or 'unknown'}"
    return None


def stage_succeeded(stage_events: list[dict[str, Any]]) -> bool:
    finishes = [event for event in stage_events if event["kind"] == "document-drop-probe-stage-finish"]
    results = [event for event in stage_events if event["kind"] == "document-drop-probe-stage-result"]
    if len(finishes) > 1 or len(results) > 1:
        raise ProbeFailure("stage-result-duplicate")
    if not finishes or not results:
        return False
    finish, result = finishes[0], results[0]
    if finish["operationId"] != result["operationId"] or finish["candidateId"] != result["candidateId"]:
        raise ProbeFailure("stage-result-identity-mismatch")
    return (
        finish["status"] == result["status"] == "candidate"
        and finish["protectedClosureEntered"] is True
        and finish["protectedCommitSucceeded"] is True
        and finish["eventEmitSucceeded"] is True
        and finish["deliveryCode"] is None
    )


def send(process: subprocess.Popen[str], command: dict[str, str]) -> None:
    if process.poll() is not None or process.stdin is None:
        raise ProbeFailure("fixture-control-unavailable")
    process.stdin.write(json.dumps(command, separators=(",", ":")) + "\n")
    process.stdin.flush()


def point_from_ready(ready: dict[str, Any], key: str) -> tuple[int, int]:
    point = ready.get(key)
    if not isinstance(point, dict):
        raise ProbeFailure(f"fixture-{key}-unavailable")
    x, y = point.get("x"), point.get("y")
    if type(x) is not int or type(y) is not int or abs(x) > 32768 or abs(y) > 32768:
        raise ProbeFailure(f"fixture-{key}-invalid")
    return x, y


def window_preflight(process: subprocess.Popen[str], ready: dict[str, Any]) -> dict[str, Any]:
    hwnd = ready.get("ownerHwnd")
    if type(hwnd) is not int or hwnd == 0:
        raise ProbeFailure("fixture-owner-hwnd-unavailable")
    inside = point_from_ready(ready, "insideScreen")
    outside = point_from_ready(ready, "outsideScreen")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [ctypes.c_void_p]
    user32.IsWindow.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_uint
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.WindowFromPoint.argtypes = [Point]
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    user32.MonitorFromPoint.argtypes = [Point, ctypes.c_uint]
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = ctypes.c_int

    def owner_of(window: int | None) -> tuple[int, int]:
        pid = ctypes.c_uint()
        thread = user32.GetWindowThreadProcessId(window, ctypes.byref(pid)) if window else 0
        return thread, pid.value

    def safe_class(window: int | None) -> str:
        if not window:
            return "<none>"
        buffer = ctypes.create_unicode_buffer(256)
        value = buffer.value if user32.GetClassNameW(window, buffer, len(buffer)) else ""
        return value if re.fullmatch(r"[A-Za-z0-9_. #+-]{1,128}", value) else "<other>"

    root_thread, root_pid = owner_of(hwnd)

    def hit(point: tuple[int, int]) -> dict[str, Any]:
        leaf = user32.WindowFromPoint(Point(*point))
        classes: list[str] = []
        processes: list[bool] = []
        threads: list[bool] = []
        current = leaf
        root_reached = False
        for _ in range(16):
            if not current:
                break
            thread, pid = owner_of(current)
            classes.append(safe_class(current))
            processes.append(pid != 0 and pid == root_pid)
            threads.append(thread != 0 and thread == root_thread)
            if current == hwnd:
                root_reached = True
                break
            current = user32.GetParent(current)
        return {
            "classChainLeafToRoot": classes,
            "sameProcessAsRoot": processes,
            "sameThreadAsRoot": threads,
            "rootReached": root_reached and user32.GetAncestor(leaf, 2) == hwnd,
        }

    def work_area(point: tuple[int, int]) -> dict[str, int]:
        monitor = user32.MonitorFromPoint(Point(*point), 2)
        info = MonitorInfo()
        info.size = ctypes.sizeof(MonitorInfo)
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ProbeFailure("monitor-work-area-unavailable")
        return {name: int(getattr(info.work, name)) for name in ("left", "top", "right", "bottom")}

    inside_work = work_area(inside)
    outside_work = work_area(outside)

    def within(point: tuple[int, int], area: dict[str, int]) -> bool:
        return area["left"] <= point[0] < area["right"] and area["top"] <= point[1] < area["bottom"]

    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, len(title))
    foreground = user32.GetForegroundWindow()
    result = {
        "ownerPresent": bool(user32.IsWindow(hwnd)),
        "ownerVisible": bool(user32.IsWindowVisible(hwnd)),
        "ownerPidMatches": root_pid == process.pid,
        "ownerTitleMatches": title.value == EXPECTED_FIXTURE_WINDOW_TITLE,
        "ownerClassMatches": safe_class(hwnd) == "Tauri Window",
        "foregroundRootMatches": bool(foreground and user32.GetAncestor(foreground, 2) == hwnd),
        "insideHit": hit(inside),
        "outsideHit": hit(outside),
        "insideWorkArea": inside_work,
        "outsideWorkArea": outside_work,
        "insideWithinWorkArea": within(inside, inside_work),
        "outsideWithinWorkArea": within(outside, outside_work),
    }
    return result


def counters(event: dict[str, Any], key: str) -> dict[str, Any]:
    result = event.get(key)
    if not isinstance(result, dict) or not result:
        raise ProbeFailure(f"fixture-{key}-observation-unavailable")
    return result


def no_renderer_values(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value) and all(no_renderer_values(item) for item in value.values())
    if isinstance(value, list):
        return all(no_renderer_values(item) for item in value)
    return type(value) is int and value == 0


def inspect_observation(
    previous: dict[str, Any], current: dict[str, Any], attempt: str, *, allow_pending_candidate: bool = False
) -> dict[str, Any]:
    if current.get("attempt") != attempt:
        raise ProbeFailure(f"fixture-attempt-mismatch-{attempt}")
    if current.get("uiPhase") != 8 or current.get("uiError") is not None:
        raise ProbeFailure(f"fixture-ui-observation-invalid-{attempt}")
    before, after = counters(previous, "native"), counters(current, "native")
    names = ("oleEnter", "oleOver", "oleDrop", "heldStage", "candidate")
    if any(type(before.get(name)) is not int or type(after.get(name)) is not int for name in names):
        raise ProbeFailure(f"native-counter-missing-{attempt}")
    delta = {name: after[name] - before[name] for name in names}
    if any(value < 0 for value in delta.values()):
        raise ProbeFailure(f"native-counter-reversed-{attempt}")
    if not no_renderer_values(counters(current, "html5")) or not no_renderer_values(counters(current, "tauri")):
        raise ProbeFailure(f"renderer-file-or-tauri-drag-observed-{attempt}")
    scope_supported = after.get("scopeCheckSupported")
    scope_allowed = after.get("scopeAllowed")
    # In this pinned Tauri build, protocol-asset is absent and allow_file /
    # allow_directory compile to no-ops. Keep that exact-feature source proof
    # separate from this OS observation; never report an unsupported read as zero.
    if (scope_supported is False and scope_allowed is None) or (scope_supported is True and scope_allowed is False):
        pass
    else:
        raise ProbeFailure(f"scope-grant-observation-invalid-{attempt}")
    if attempt != "inside":
        if delta["heldStage"] or delta["candidate"]:
            raise ProbeFailure(f"denied-drop-staged-{attempt}")
        expected_armed = attempt == "outside-armed"
        if current.get("armed") is not expected_armed:
            raise ProbeFailure(f"arming-state-mismatch-{attempt}")
    elif (
        delta["oleDrop"] != 1
        or delta["heldStage"] != 1
        or delta["candidate"] not in ((0, 1) if allow_pending_candidate else (1,))
    ):
        raise ProbeFailure("inside-drop-not-staged-exactly-once")
    return delta


def target_hit(source_result: dict[str, Any], attempt: str) -> dict[str, Any]:
    hit = source_result.get("motionTarget")
    if not isinstance(hit, dict) or set(hit) != {
        "classChainLeafToRoot",
        "sameProcessAsRoot",
        "sameThreadAsRoot",
        "rootReached",
    }:
        raise ProbeFailure(f"external-ole-target-hit-missing-{attempt}")
    classes = hit["classChainLeafToRoot"]
    processes = hit["sameProcessAsRoot"]
    threads = hit["sameThreadAsRoot"]
    if (
        not isinstance(classes, list)
        or not 1 <= len(classes) <= 16
        or not all(isinstance(name, str) and 0 < len(name) <= 256 for name in classes)
        or not isinstance(processes, list)
        or not isinstance(threads, list)
        or len(processes) != len(classes)
        or len(threads) != len(classes)
        or not all(type(value) is bool for value in processes + threads)
        or hit["rootReached"] is not True
    ):
        raise ProbeFailure(f"external-ole-target-hit-invalid-{attempt}")
    return hit


def run_source(
    stem: str,
    attempt: str,
    fixture_root: Path,
    ready: dict[str, Any],
    point_key: str,
    get_cursor: Any,
    set_cursor: Any,
) -> tuple[dict[str, Any], Path]:
    source = fixture_root / "temporary" / "document-drop-source.txt"
    if not source.is_file() or source.is_symlink() or source.resolve() != source:
        raise ProbeFailure("synthetic-source-unavailable")
    if file_hash(source) != SYNTHETIC_SOURCE_SHA256:
        raise ProbeFailure("synthetic-source-digest-mismatch")
    x, y = point_from_ready(ready, point_key)
    hwnd = ready.get("ownerHwnd")
    if type(hwnd) is not int or hwnd == 0:
        raise ProbeFailure("fixture-owner-hwnd-unavailable")
    request_file = SCRATCH / f"{stem}.{attempt}.request.json"
    raw_file = SCRATCH / f"{stem}.{attempt}.ole.raw.log"
    request_file.write_text(
        json.dumps(
            {
                "sourcePaths": [str(source)],
                "targetX": x,
                "targetY": y,
                "expectedRootHwnd": hwnd,
                "timeoutMilliseconds": 3000,
            }
        ),
        encoding="utf-8",
    )
    previous_cursor = current_cursor(get_cursor)
    command = [
        "powershell.exe",
        "-ExecutionPolicy",
        "Bypass",
        "-NoProfile",
        "-NonInteractive",
        "-STA",
        "-File",
        str(SOURCE_WRAPPER),
        "-RequestJson",
        str(request_file),
    ]
    try:
        try:
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=12)
            raw_file.write_text(
                f"exit={completed.returncode}\n" + completed.stderr + completed.stdout,
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired as error:
            raw_file.write_text(
                "external-ole-source-timeout\n" + str(error.stderr or "") + str(error.stdout or ""),
                encoding="utf-8",
            )
            raise ProbeFailure(f"external-ole-source-timeout-{attempt}") from None
    finally:
        if not set_cursor(previous_cursor.x, previous_cursor.y):
            raise ProbeFailure(f"cursor-restore-failed-{attempt}") from None
    if completed.returncode != 0:
        raise ProbeFailure(f"external-ole-source-failed-{attempt}")
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except IndexError, json.JSONDecodeError:
        raise ProbeFailure(f"external-ole-result-missing-{attempt}") from None
    if (
        result.get("kind") != "windows-ole-file-drag"
        or result.get("sourceCount") != 1
        or result.get("initialTargetWindowConfirmed") is not True
        or result.get("motionHitTestMatched") is not True
        or result.get("dropRequested") is not True
        or result.get("failureCode") is not None
    ):
        raise ProbeFailure(f"external-ole-source-incomplete-{attempt}")
    return result, raw_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-exe", type=Path, required=True)
    parser.add_argument("--worker-build", type=Path, required=True)
    parser.add_argument("--guardian-exe", type=Path, required=True)
    parser.add_argument("--guardian-sha256", required=True)
    parser.add_argument("--candidate-wait-seconds", type=int, default=60)
    parser.add_argument("--nonce", default=f"drop-{secrets.token_hex(6)}")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", args.nonce):
        raise SystemExit("probe-nonce-invalid")
    if not 1 <= args.candidate_wait_seconds <= 190:
        raise SystemExit("probe-candidate-wait-invalid")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    fixture_root = SCRATCH / f"directory-dialog-{args.nonce}"
    if fixture_root.exists():
        raise SystemExit("probe-fixture-already-exists")
    exact_fixture_title_contract()
    app_binary = exact_binary(args.app_exe)
    signed_worker_build, frozen_guardian = qualification_inputs(
        args.worker_build, args.guardian_exe, args.guardian_sha256
    )
    get_cursor, set_cursor = cursor_api()
    current_cursor(get_cursor)  # Fail before starting Tauri on a noninteractive desktop.
    stem = f"CAP-05.S01.T01.os-drop-{args.nonce}"
    stdout_file = SCRATCH / f"{stem}.fixture.jsonl"
    stderr_file = SCRATCH / f"{stem}.fixture.stderr.log"
    result_file = SCRATCH / f"{stem}.result.json"
    events: queue.Queue[dict[str, Any]] = queue.Queue()
    summary: dict[str, Any] = {
        "schemaVersion": "1.0",
        "kind": "built-tauri-real-windows-ole-document-drop",
        "binarySha256": file_hash(app_binary),
        "signedWorkerInventorySha256": file_hash(signed_worker_build / "inventory.json"),
        "signedWorkerSignatureSha256": file_hash(signed_worker_build / "inventory.sig"),
        "frozenGuardianSha256": args.guardian_sha256.lower(),
        "candidateWaitLimitSeconds": args.candidate_wait_seconds,
        "status": "incomplete",
        "attempts": [],
        "stageEvents": [],
        "windowPreflights": [],
    }
    stage_events = summary["stageEvents"]
    process: subprocess.Popen[str] | None = None
    started = time.monotonic()
    app_environment = os.environ.copy()
    app_environment["RO_W2_SIGNED_WORKER_BUILD"] = str(signed_worker_build)
    app_environment["RO_W2_CORE_SIDECAR_GUARDIAN"] = str(frozen_guardian)
    app_environment["RO_W2_CORE_SIDECAR_GUARDIAN_SHA256"] = args.guardian_sha256.lower()
    with stderr_file.open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.Popen(
                [str(app_binary), "--tauri-directory", "document-drop", args.nonce],
                cwd=ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=app_environment,
            )
            reader = threading.Thread(target=read_events, args=(process, stdout_file, events), daemon=True)
            reader.start()
            ready = await_event(events, process, "document-drop-probe-ready", 125, stage_events)
            if ready.get("observationInstalled") is not True:
                raise ProbeFailure("fixture-observation-not-installed")
            if ready.get("armed") is not False:
                raise ProbeFailure("fixture-not-disarmed-at-ready")
            inside = point_from_ready(ready, "insideScreen")
            outside = point_from_ready(ready, "outsideScreen")
            if inside == outside:
                raise ProbeFailure("fixture-zone-points-not-distinct")
            target_classes = ready.get("targetClasses")
            if (
                not isinstance(target_classes, list)
                or not target_classes
                or not all(isinstance(name, str) and name for name in target_classes)
            ):
                raise ProbeFailure("native-drop-target-classes-unavailable")
            if not no_renderer_values(counters(ready, "html5")) or not no_renderer_values(counters(ready, "tauri")):
                raise ProbeFailure("renderer-drag-observed-before-os-attempt")
            previous = ready
            for attempt, point_key in ATTEMPTS:
                if attempt == "outside-armed":
                    send(process, {"action": "arm"})
                    armed = await_event(events, process, "document-drop-probe-armed", 20, stage_events)
                    if armed.get("armed") is not True:
                        raise ProbeFailure("actual-pane-arm-not-confirmed")
                preflight = window_preflight(process, ready)
                summary["windowPreflights"].append({"attempt": attempt, **preflight})
                if (
                    not all(
                        preflight[key]
                        for key in (
                            "ownerPresent",
                            "ownerVisible",
                            "ownerPidMatches",
                            "ownerTitleMatches",
                            "ownerClassMatches",
                            "foregroundRootMatches",
                            "insideWithinWorkArea",
                            "outsideWithinWorkArea",
                        )
                    )
                    or not preflight["insideHit"]["rootReached"]
                    or not preflight["outsideHit"]["rootReached"]
                ):
                    raise ProbeFailure(f"fixture-window-preflight-failed-{attempt}")
                source_result, raw_file = run_source(
                    stem,
                    attempt,
                    fixture_root,
                    ready,
                    point_key,
                    get_cursor,
                    set_cursor,
                )
                if attempt == "inside" and stage_events:
                    raise ProbeFailure("stage-event-before-inside-drop")
                hit = target_hit(source_result, attempt)
                summary["lastSource"] = {"attempt": attempt, "effect": source_result.get("effect"), "targetHit": hit}
                expected_effect = "Copy" if attempt == "inside" else "None"
                if source_result.get("effect") != expected_effect:
                    raise ProbeFailure(f"external-ole-effect-unexpected-{attempt}")
                send(process, {"action": "observe", "attempt": attempt})
                observed = await_event(events, process, "document-drop-probe-observation", 20, stage_events)
                delta = inspect_observation(previous, observed, attempt, allow_pending_candidate=attempt == "inside")
                if attempt == "inside":
                    first_drop_delta = {name: delta[name] for name in ("oleEnter", "oleOver", "oleDrop", "heldStage")}
                    wait_started = time.monotonic()
                    # The caller can bound observation beyond the signed worker
                    # and enclosing Core stage deadlines without another drop.
                    wait_deadline = wait_started + args.candidate_wait_seconds
                    summary["insideCandidateObservations"] = []
                    while True:
                        summary["insideCandidateObservations"].append(
                            {"nativeDelta": delta, "armed": observed.get("armed")}
                        )
                        if {name: delta[name] for name in first_drop_delta} != first_drop_delta:
                            raise ProbeFailure("inside-additional-native-drag-observed")
                        if failure := stage_failure(stage_events):
                            raise ProbeFailure(failure)
                        if delta["candidate"] == 1 and stage_succeeded(stage_events):
                            break
                        if time.monotonic() >= wait_deadline:
                            raise ProbeFailure("inside-candidate-timeout")
                        time.sleep(1)
                        send(process, {"action": "observe", "attempt": attempt})
                        observed = await_event(
                            events,
                            process,
                            "document-drop-probe-observation",
                            min(10, max(0.1, wait_deadline - time.monotonic())),
                            stage_events,
                        )
                        delta = inspect_observation(previous, observed, attempt, allow_pending_candidate=True)
                    summary["insideCandidateWaitMilliseconds"] = int((time.monotonic() - wait_started) * 1000)
                summary["attempts"].append(
                    {
                        "attempt": attempt,
                        "effect": source_result["effect"],
                        "nativeDelta": delta,
                        "oleRawSha256": file_hash(raw_file),
                        "targetHit": hit,
                        "heldAndCandidateExpected": attempt == "inside",
                        "scopeObservation": "unsupported"
                        if observed["native"]["scopeCheckSupported"] is False
                        else "synthetic-source-not-allowed",
                    }
                )
                previous = observed
            summary["status"] = "passed"
        except (ProbeFailure, OSError, ValueError) as error:
            summary["failureCode"] = str(error) if isinstance(error, ProbeFailure) else "driver-os-error"
        finally:
            if process is not None:
                try:
                    send(process, {"action": "close"})
                    ended = await_event(events, process, "document-drop-probe-end", 20, stage_events)
                    if ended.get("exitCode") != 0:
                        raise ProbeFailure("fixture-exit-code-nonzero")
                    if process.wait(timeout=10) != 0:
                        raise ProbeFailure("fixture-exit-nonzero")
                except ProbeFailure, OSError, ValueError, subprocess.TimeoutExpired:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    if summary["status"] == "passed":
                        summary["status"] = "incomplete"
                        summary["failureCode"] = "fixture-close-or-exit-incomplete"
                if process.stdin is not None:
                    with contextlib.suppress(OSError):
                        process.stdin.close()
                summary["fixtureReturnCode"] = process.returncode
                if process.returncode is not None:
                    summary["fixtureReturnHex"] = f"0x{process.returncode & 0xFFFFFFFF:08X}"
    summary["elapsedMilliseconds"] = int((time.monotonic() - started) * 1000)
    summary["fixtureJsonlSha256"] = file_hash(stdout_file) if stdout_file.exists() else None
    summary["fixtureStderrSha256"] = file_hash(stderr_file)
    result_file.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    reported = summary.copy()
    if observations := summary.get("insideCandidateObservations"):
        reported["insideCandidateObservations"] = {"count": len(observations), "last": observations[-1]}
    print(json.dumps(reported, sort_keys=True))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
