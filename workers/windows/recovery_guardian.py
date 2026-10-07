"""Trusted, per-job ACL guardian for a disposable connector LPAC job.

The Core sidecar starts this process outside its kill-on-close Job before ACL
lockdown. The guardian receives only job-owned profile/runtime identities over
private stdio, holds exact pre-lockdown DACL handles, and waits for Core's pipe
to close. It never receives plugin IPC, research input, or credentials.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from . import lpac_launcher as win
from .file_paths import extended_path
from .no_write_acl import _open_saved, _restore, _SavedAcl, _security_api, _tree, restore_open_acl_handles

_PROFILE_NAME = re.compile(r"ResearchObservatory\.PluginProbe\.[0-9a-f]{24}\Z")
_RUNTIME_LEAF = re.compile(r"[0-9a-f]{16}\Z")
_MAX_COMMAND = 4096
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000
_CREATE_NO_WINDOW = 0x08000000


class GuardianError(win.LPACError):
    """A guardian handshake, restoration, or job-owned cleanup failed."""


@dataclass(slots=True)
class GuardianProcess:
    process: subprocess.Popen[bytes]
    nonce: str
    name: str
    sid_text: str
    profile: Path
    temp: Path
    runtime: Path

    def alive(self) -> bool:
        return self.process.poll() is None

    def seal(self) -> None:
        """Snapshot every staged object before Core may apply strict ACLs."""

        if self.process.stdin is None or self.process.stdout is None:
            raise GuardianError("lpac-guardian-pipes-unavailable")
        _send(self.process.stdin, {"operation": "seal", "nonce": self.nonce})
        if _read_with_timeout(self.process.stdout, 10) != {"operation": "ready", "nonce": self.nonce}:
            raise GuardianError("lpac-guardian-seal-invalid")

    def finish(self, *, restored: bool) -> bool:
        """Keep backup handles until verified cleanup on normal or crash exit."""

        if self.process.stdin is None or self.process.stdout is None:
            raise GuardianError("lpac-guardian-pipes-unavailable")
        if restored:
            with suppress(OSError):
                _send(self.process.stdin, {"operation": "release", "nonce": self.nonce})
        self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired as exc:
            # The guardian is the only process that can still hold recovery
            # authority after a Core crash. Leave it alive to retry cleanup.
            self.process.stdout.close()
            raise GuardianError("lpac-guardian-cleanup-pending") from exc
        response = _receive(self.process.stdout)
        self.process.stdout.close()
        if self.process.returncode != 0 or response != {"operation": "done", "nonce": self.nonce}:
            code = response.get("code", "failed") if response.get("operation") == "failed" else "protocol"
            raise GuardianError(f"lpac-guardian-cleanup-failed:{code}")
        return True


def _send(pipe: IO[bytes], frame: dict[str, str]) -> None:
    payload = json.dumps(frame, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(payload) > _MAX_COMMAND:
        raise GuardianError("lpac-guardian-frame-oversize")
    pipe.write(payload + b"\n")
    pipe.flush()


def _receive(pipe: IO[bytes]) -> dict[str, str]:
    payload = pipe.readline(_MAX_COMMAND + 1)
    if not payload or len(payload) > _MAX_COMMAND or not payload.endswith(b"\n"):
        raise GuardianError("lpac-guardian-frame-invalid")
    try:
        frame = json.loads(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        raise GuardianError("lpac-guardian-frame-invalid") from exc
    if not isinstance(frame, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in frame.items()
    ):
        raise GuardianError("lpac-guardian-frame-invalid")
    return frame


def _read_with_timeout(pipe: IO[bytes], seconds: int) -> dict[str, str]:
    result: list[dict[str, str] | BaseException] = []

    def read() -> None:
        try:
            result.append(_receive(pipe))
        except BaseException as exc:
            result.append(exc)

    thread = threading.Thread(target=read, name="lpac-guardian-ready", daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise GuardianError("lpac-guardian-handshake-timeout")
    if not result or isinstance(result[0], BaseException):
        raise GuardianError("lpac-guardian-handshake-failed")
    return result[0]


def _guardian_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--plugin-acl-guardian"]
    return [sys.executable, "-m", __name__]


def start_guardian() -> GuardianProcess:
    """Start a trusted sibling that owns the profile and runtime from inception."""

    if os.name != "nt":
        raise GuardianError("lpac-guardian-windows-only")
    nonce = os.urandom(16).hex()
    frozen = getattr(sys, "frozen", False)
    command = _guardian_command()
    environment = {
        "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
    }
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        cwd=None if frozen else str(Path(__file__).resolve().parents[2]),
        env=environment,
        creationflags=_CREATE_BREAKAWAY_FROM_JOB | _CREATE_NO_WINDOW,
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        _send(process.stdin, {"operation": "create", "nonce": nonce})
        frame = _read_with_timeout(process.stdout, 10)
        if set(frame) != {"operation", "nonce", "name", "sid", "profile", "temp", "runtime"} or (
            frame["operation"] != "created" or frame["nonce"] != nonce
        ):
            raise GuardianError("lpac-guardian-handshake-invalid")
        kernel, advapi, userenv, ole = win._api()
        profile = Path(frame["profile"])
        temp = Path(frame["temp"])
        runtime = Path(frame["runtime"])
        if temp != profile / "Temp" or not temp.is_dir():
            raise GuardianError("lpac-guardian-profile-layout-invalid")
        _owned_paths(frame["name"], frame["sid"], profile, runtime, userenv, ole)
        # Verify the derived SID independently in Core before trusting it.
        sid = win._derive_profile_sid(userenv, advapi, kernel, frame["name"], frame["sid"])
        advapi.FreeSid(sid)
        return GuardianProcess(process, nonce, frame["name"], frame["sid"], profile, temp, runtime)
    except BaseException:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            # A failed handshake can follow successful resource creation.
            # Never discard the guardian's cleanup authority on a timeout.
            if process.stdout:
                process.stdout.close()
            raise GuardianError("lpac-guardian-handshake-cleanup-pending") from None
        if process.stdout:
            process.stdout.close()
        raise


def _owned_paths(name: str, sid_text: str, profile: Path, runtime: Path, userenv: Any, ole: Any) -> tuple[Path, Path]:
    if not _PROFILE_NAME.fullmatch(name) or not re.fullmatch(r"S-1-15-2-(?:[0-9]+-){6}[0-9]+", sid_text):
        raise GuardianError("lpac-guardian-identity-invalid")
    if profile.name != "AC" or runtime.is_symlink() or runtime.is_junction():
        raise GuardianError("lpac-guardian-layout-invalid")
    local = Path(os.environ["LOCALAPPDATA"]).resolve(strict=True)
    package_parent = (local / "Packages").resolve(strict=True)
    runtime_parent = (local / "RoWorker").resolve(strict=True)
    profile_root = profile.parent
    if (
        profile_root.is_symlink()
        or profile_root.is_junction()
        or profile_root.resolve(strict=True).parent != package_parent
        or profile_root.name.casefold() != name.casefold()
        or runtime.resolve(strict=True).parent != runtime_parent
        or not _RUNTIME_LEAF.fullmatch(runtime.name)
    ):
        raise GuardianError("lpac-guardian-root-invalid")
    folder = ctypes.c_wchar_p()
    if userenv.GetAppContainerFolderPath(sid_text, ctypes.byref(folder)) != 0 or not folder.value:
        raise GuardianError("lpac-guardian-profile-identity-invalid")
    try:
        if Path(folder.value).resolve(strict=True) != profile.resolve(strict=True):
            raise GuardianError("lpac-guardian-profile-identity-invalid")
    finally:
        ole.CoTaskMemFree(ctypes.cast(folder, ctypes.c_void_p))
    _tree(profile_root)
    _tree(runtime)
    return profile_root, runtime_parent


def _present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _restore_present(kernel: Any, advapi: Any, saved: list[_SavedAcl]) -> None:
    existing: list[_SavedAcl] = []
    for item in saved:
        if _present(item.path):
            existing.append(item)
        else:
            win._close(kernel, item.handle)
            kernel.LocalFree(item.descriptor)
    if existing:
        _restore(kernel, advapi, existing)


def _recover(
    kernel: Any,
    advapi: Any,
    userenv: Any,
    name: str,
    profile_root: Path,
    runtime: Path,
    runtime_parent: Path,
    profile_saved: list[_SavedAcl],
    runtime_saved: list[_SavedAcl],
) -> None:
    # Keep the original WRITE_DAC handles alive until the exact DACLs are
    # restored and verified. A transient sharing/AV denial must not strand
    # objects with their lockdown DACL after the Core process has died.
    backoff = 0.1
    while profile_saved or runtime_saved:
        try:
            if profile_saved:
                restore_open_acl_handles(kernel, advapi, profile_saved)
            if runtime_saved:
                restore_open_acl_handles(kernel, advapi, runtime_saved)
        except OSError, win.LPACError:
            time.sleep(backoff)
            backoff = min(backoff * 2, 1.0)
            continue
        for item in (*profile_saved, *runtime_saved):
            win._close(kernel, item.handle)
            kernel.LocalFree(item.descriptor)
        profile_saved.clear()
        runtime_saved.clear()
    # Restored DACLs make the exact resources recoverable without elevated
    # authority. Continue owning and retrying deletion until OS locks clear.
    backoff = 0.1
    while True:
        if _present(runtime) and (
            runtime.is_symlink() or runtime.is_junction() or runtime.resolve(strict=True).parent != runtime_parent
        ):
            # A redirected path is a terminal identity failure, not a
            # transient sharing lock. Never follow or delete its target.
            raise GuardianError("lpac-guardian-runtime-target-changed")
        try:
            if _present(profile_root) and userenv.DeleteAppContainerProfile(name) != 0:
                raise GuardianError("lpac-guardian-profile-cleanup-pending")
            if _present(runtime):
                shutil.rmtree(extended_path(runtime))
            if not _present(profile_root) and not _present(runtime):
                return
        except OSError:
            pass
        except GuardianError as exc:
            if str(exc) != "lpac-guardian-profile-cleanup-pending":
                raise
        time.sleep(backoff)
        backoff = min(backoff * 2, 1.0)


def guardian_main(stdin: IO[bytes] | None = None, stdout: IO[bytes] | None = None) -> int:
    """Run in an installed Core sidecar guardian mode, without API startup."""

    incoming = stdin or sys.stdin.buffer
    outgoing = stdout or sys.stdout.buffer
    kernel, advapi, userenv, ole = win._api()
    _security_api(kernel, advapi)
    profile_saved: list[_SavedAcl] = []
    runtime_saved: list[_SavedAcl] = []
    nonce = name = None
    sid = None
    profile_root = runtime = runtime_parent = None
    created = False
    runtime_owned = False
    recovery_started = False
    try:
        frame = _receive(incoming)
        if set(frame) != {"operation", "nonce"} or frame["operation"] != "create":
            raise GuardianError("lpac-guardian-create-invalid")
        nonce = frame["nonce"]
        if not re.fullmatch(r"[0-9a-f]{32}", nonce):
            raise GuardianError("lpac-guardian-nonce-invalid")
        for _ in range(3):
            try:
                name, sid, sid_text, profile, temp = win._profile(userenv, advapi, ole)
                break
            except win.LPACError as exc:
                if "lpac-profile-creation-failed:0x800700b7" not in str(exc):
                    raise
        else:
            raise GuardianError("lpac-guardian-profile-identity-unavailable")
        created = True
        profile_root = profile.parent
        local = Path(os.environ["LOCALAPPDATA"]).resolve(strict=True)
        runtime_parent = local / "RoWorker"
        runtime_parent.mkdir(parents=True, exist_ok=True)
        runtime_parent = runtime_parent.resolve(strict=True)
        if not runtime_parent.is_relative_to(local) or runtime_parent.name != "RoWorker":
            raise GuardianError("lpac-guardian-runtime-parent-invalid")
        for _ in range(3):
            runtime = runtime_parent / secrets.token_hex(8)
            try:
                runtime.mkdir()
                runtime_owned = True
                break
            except FileExistsError:
                continue
        else:
            raise GuardianError("lpac-guardian-runtime-identity-unavailable")
        profile_root, runtime_parent = _owned_paths(name, sid_text, profile, runtime, userenv, ole)
        _send(
            outgoing,
            {
                "operation": "created",
                "nonce": nonce,
                "name": name,
                "sid": sid_text,
                "profile": str(profile),
                "temp": str(temp),
                "runtime": str(runtime),
            },
        )
        command = incoming.readline(_MAX_COMMAND + 1)
        if command:
            if len(command) > _MAX_COMMAND or not command.endswith(b"\n"):
                raise GuardianError("lpac-guardian-seal-invalid")
            if json.loads(command) != {"operation": "seal", "nonce": nonce}:
                raise GuardianError("lpac-guardian-seal-invalid")
            user_sid = win._current_user_sid(advapi, kernel)
            for path in _tree(profile_root):
                profile_saved.append(_open_saved(kernel, advapi, path, user_sid))
            for path in _tree(runtime):
                runtime_saved.append(_open_saved(kernel, advapi, path, user_sid))
            _send(outgoing, {"operation": "ready", "nonce": nonce})
            followup = incoming.readline(_MAX_COMMAND + 1)
            if followup:
                if len(followup) > _MAX_COMMAND or not followup.endswith(b"\n"):
                    raise GuardianError("lpac-guardian-release-invalid")
                if json.loads(followup) != {"operation": "release", "nonce": nonce}:
                    raise GuardianError("lpac-guardian-release-invalid")
        # Before seal the original DACLs are still writable. After seal the
        # backup handles cover every staged object, even if Core dies mid-lock.
        recovery_started = True
        _recover(
            kernel,
            advapi,
            userenv,
            name,
            profile_root,
            runtime,
            runtime_parent,
            profile_saved,
            runtime_saved,
        )
        _send(outgoing, {"operation": "done", "nonce": nonce})
        return 0
    except BaseException as exc:
        # Never send paths, profile names, input data, or raw exception text.
        cleanup_failed = False
        if created and name and profile_root and runtime_owned and runtime and runtime_parent:
            if not recovery_started:
                recovery_started = True
                try:
                    _recover(
                        kernel,
                        advapi,
                        userenv,
                        name,
                        profile_root,
                        runtime,
                        runtime_parent,
                        profile_saved,
                        runtime_saved,
                    )
                except BaseException:
                    cleanup_failed = True
        elif created and name:
            # Creation may fail before a runtime root exists. Only this process
            # created the profile, so its exact name is safe to release.
            if runtime_owned and runtime and runtime_parent:
                try:
                    if (
                        runtime.is_symlink()
                        or runtime.is_junction()
                        or runtime.resolve(strict=True).parent != runtime_parent
                    ):
                        raise GuardianError("lpac-guardian-runtime-target-changed")
                    shutil.rmtree(extended_path(runtime))
                except BaseException:
                    cleanup_failed = True
            if userenv.DeleteAppContainerProfile(name) != 0:
                cleanup_failed = True
        if nonce:
            if cleanup_failed:
                code = "lpac-guardian-cleanup-failed"
            elif isinstance(exc, (GuardianError, win.LPACError)):
                code = str(exc)
            else:
                frame_info = exc.__traceback__
                while frame_info and frame_info.tb_next:
                    frame_info = frame_info.tb_next
                code = (
                    f"unexpected:{type(exc).__name__}:{frame_info.tb_frame.f_code.co_name}:{frame_info.tb_lineno}"
                    if frame_info
                    else "unexpected"
                )
            with suppress(OSError):
                _send(outgoing, {"operation": "failed", "nonce": nonce, "code": code})
        return 2
    finally:
        if sid:
            advapi.FreeSid(sid)


if __name__ == "__main__":
    raise SystemExit(guardian_main())
