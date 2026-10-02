"""Core-side launch of one signed connector package in a zero-capability LPAC.

Core must recheck the current publisher trust, grant, project policy and job
fence before this call and before each broker callback. The worker receives no
path, URL, plan, credential, database handle or secret over its private pipes.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import queue
import shutil
import threading
import time
from collections.abc import Callable, Mapping
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_observatory_core.connectors.plugin_manifest import _VERIFIED_SEAL, VerifiedPluginPackage

from . import lpac_launcher as win
from .no_write_acl import AclRestoration, no_write_lpac_acl, verify_lpac_no_write
from .protocol import MAX_BINARY_FRAME, MAX_CONTROL_FRAME, decode_frame, encode_frame
from .recovery_guardian import GuardianError, GuardianProcess, start_guardian
from .runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime, _safe_path, verify_worker_runtime

_MAX_BROKER_CALLS = 64
_CALL_KEYS = frozenset({"operation", "identifier", "query", "repositoryId", "cursor", "pageSize", "credentialScope"})


@dataclass(frozen=True, slots=True)
class WorkerResult:
    output: bytes
    token: dict[str, Any]
    broker_calls: int


def _read_exact(kernel: Any, handle: int, length: int) -> bytes:
    parts: list[bytes] = []
    remaining = length
    while remaining:
        buffer = ctypes.create_string_buffer(min(remaining, 32_768))
        count = wintypes.DWORD()
        if not kernel.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None) or count.value == 0:
            raise win.LPACError("lpac-worker-pipe-truncated")
        parts.append(buffer.raw[: count.value])
        remaining -= count.value
    return b"".join(parts)


def _read_control(kernel: Any, handle: int, nonce: str, sequence: int) -> dict[str, Any]:
    prefix = _read_exact(kernel, handle, 4)
    length = int.from_bytes(prefix, "big")
    if not 0 < length <= MAX_CONTROL_FRAME:
        raise win.LPACError("lpac-worker-control-oversize")
    return decode_frame(prefix + _read_exact(kernel, handle, length), expected_nonce=nonce, expected_sequence=sequence)


def _read_binary(kernel: Any, handle: int) -> bytes:
    length = int.from_bytes(_read_exact(kernel, handle, 4), "big")
    if length > MAX_BINARY_FRAME:
        raise win.LPACError("lpac-worker-binary-oversize")
    return _read_exact(kernel, handle, length)


def _write_binary(kernel: Any, handle: int, value: bytes) -> None:
    if not isinstance(value, bytes) or len(value) > MAX_BINARY_FRAME:
        raise win.LPACError("lpac-worker-binary-oversize")
    win._write(kernel, handle, len(value).to_bytes(4, "big") + value)


def _wait_for_worker_exit(
    kernel: Any, process_handle: int, deadline: float, cancelled: Callable[[], bool] | None
) -> None:
    """Keep cancellation live even after a hostile worker emitted valid output."""

    while True:
        if cancelled is not None and cancelled():
            raise win.LPACError("lpac-worker-cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise win.LPACError("lpac-worker-timeout")
        waited = kernel.WaitForSingleObject(process_handle, max(1, min(50, int(remaining * 1000))))
        if waited == 0:
            return
        if waited != 0x102:
            raise win.LPACError("lpac-worker-wait-failed")


def _stage_plugin(package: VerifiedPluginPackage, package_files: Mapping[str, bytes], image: Path) -> str:
    if not isinstance(package, VerifiedPluginPackage) or package._seal is not _VERIFIED_SEAL:
        raise win.LPACError("lpac-plugin-unverified")
    manifest = package.manifest
    declared = {item.path: item.sha256.removeprefix("sha256:") for item in manifest.files}
    if not isinstance(package_files, Mapping) or set(package_files) != set(declared):
        raise win.LPACError("lpac-plugin-file-set-invalid")
    package_hash = hashlib.sha256(b"research-observatory-connector-package-v1\x00")
    total = 0
    assets = image.parent / "_internal" / "plugin-assets"
    if assets.exists() or (image.parent / "_internal" / "plugin").exists():
        raise win.LPACError("lpac-plugin-asset-collision")
    assets.mkdir()
    for relative in sorted(declared):
        raw = package_files[relative]
        if (
            not _safe_path(relative)
            or not isinstance(raw, bytes)
            or len(raw) > 16 * 1_048_576
            or hashlib.sha256(raw).hexdigest() != declared[relative]
        ):
            raise win.LPACError("lpac-plugin-byte-mismatch")
        total += len(raw)
        if total > 64 * 1_048_576:
            raise win.LPACError("lpac-plugin-oversize")
        encoded_path = relative.encode("utf-8")
        package_hash.update(len(encoded_path).to_bytes(4, "big"))
        package_hash.update(encoded_path)
        package_hash.update(len(raw).to_bytes(8, "big"))
        package_hash.update(raw)
        target = assets.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    if "sha256:" + package_hash.hexdigest() != package.package_sha256:
        raise win.LPACError("lpac-plugin-package-mismatch")
    entry = manifest.entry_point
    if entry not in declared:
        raise win.LPACError("lpac-plugin-entry-invalid")
    fixed_entry = image.parent / "_internal" / "plugin" / "connector.py"
    fixed_entry.parent.mkdir()
    fixed_entry.write_bytes(package_files[entry])
    return declared[entry]


def _dialogue(
    kernel: Any,
    parent_stdin: int,
    parent_stdout: int,
    request: dict[str, Any],
    input_data: bytes,
    broker_callback: Callable[[dict[str, Any]], bytes],
) -> tuple[bytes, int]:
    nonce = request["jobNonce"]
    win._write(kernel, parent_stdin, encode_frame(request))
    _write_binary(kernel, parent_stdin, input_data)
    sequence = 1
    calls = 0
    while True:
        frame = _read_control(kernel, parent_stdout, nonce, sequence)
        operation = frame["operation"]
        if operation == "invoke-result":
            if set(frame) != {"protocolVersion", "jobNonce", "sequence", "operation", "outputLength", "outputSha256"}:
                raise win.LPACError("lpac-worker-result-invalid")
            output = _read_binary(kernel, parent_stdout)
            if (
                type(frame["outputLength"]) is not int
                or frame["outputLength"] != len(output)
                or frame["outputSha256"] != hashlib.sha256(output).hexdigest()
            ):
                raise win.LPACError("lpac-worker-result-invalid")
            return output, calls
        if operation != "broker-call" or set(frame) != {"protocolVersion", "jobNonce", "sequence", "operation", "call"}:
            raise win.LPACError("lpac-worker-operation-invalid")
        call = frame["call"]
        if not isinstance(call, dict) or not 0 < len(call) <= len(_CALL_KEYS) or not set(call) <= _CALL_KEYS:
            raise win.LPACError("lpac-worker-broker-call-invalid")
        calls += 1
        if calls > _MAX_BROKER_CALLS:
            raise win.LPACError("lpac-worker-broker-call-limit")
        response = broker_callback(call)
        if not isinstance(response, bytes) or len(response) > MAX_BINARY_FRAME:
            raise win.LPACError("lpac-worker-broker-response-invalid")
        win._write(
            kernel,
            parent_stdin,
            encode_frame(
                {
                    "protocolVersion": "1.0",
                    "jobNonce": nonce,
                    "sequence": sequence + 1,
                    "operation": "broker-result",
                    "responseLength": len(response),
                    "responseSha256": hashlib.sha256(response).hexdigest(),
                }
            ),
        )
        _write_binary(kernel, parent_stdin, response)
        sequence += 2


def _launch_signed_worker(
    image: Path,
    sid: int,
    sid_text: str,
    profile: Path,
    temp: Path,
    request: dict[str, Any],
    memory_mib: int,
    wall_seconds: int,
    dialogue: Callable[[Any, int, int, dict[str, Any]], tuple[bytes, int]],
    cancelled: Callable[[], bool] | None,
) -> WorkerResult:
    kernel, advapi, _, _ = win._api()
    attributes = win._SecurityAttributes(ctypes.sizeof(win._SecurityAttributes), None, True)
    child_stdin = parent_stdin = parent_stdout = child_stdout = parent_stderr = child_stderr = job = None
    process = win._ProcessInformation()
    attribute_list = None
    created = assigned = False
    try:
        child_stdin, parent_stdin = win._pipe(kernel, attributes)
        parent_stdout, child_stdout = win._pipe(kernel, attributes)
        parent_stderr, child_stderr = win._pipe(kernel, attributes)
        for handle in (parent_stdin, parent_stdout, parent_stderr):
            win._must(kernel.SetHandleInformation(handle, win._HANDLE_FLAG_INHERIT, 0), "lpac-handle-policy-failed")
        handles = (wintypes.HANDLE * 3)(child_stdin, child_stdout, child_stderr)
        capabilities = win._SecurityCapabilities(sid, None, 0, 0)
        policy = wintypes.DWORD(win._PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT)
        size = ctypes.c_size_t()
        kernel.InitializeProcThreadAttributeList(None, 3, 0, ctypes.byref(size))
        if not 0 < size.value <= 65_536:
            raise win.LPACError("lpac-attribute-allocation-invalid")
        buffer = ctypes.create_string_buffer(size.value)
        attribute_list = ctypes.c_void_p(ctypes.addressof(buffer))
        win._must(
            kernel.InitializeProcThreadAttributeList(attribute_list, 3, 0, ctypes.byref(size)),
            "lpac-attribute-creation-failed",
        )
        for name, value, length in (
            (win._PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, ctypes.byref(capabilities), ctypes.sizeof(capabilities)),
            (win._PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY, ctypes.byref(policy), ctypes.sizeof(policy)),
            (win._PROC_THREAD_ATTRIBUTE_HANDLE_LIST, ctypes.byref(handles), ctypes.sizeof(handles)),
        ):
            win._must(
                kernel.UpdateProcThreadAttribute(attribute_list, 0, name, value, length, None, None),
                "lpac-attribute-update-failed",
            )
        startup = win._StartupInfoEx()
        startup.StartupInfo.cb = ctypes.sizeof(win._StartupInfoEx)
        startup.StartupInfo.dwFlags = win._STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = child_stdin
        startup.StartupInfo.hStdOutput = child_stdout
        startup.StartupInfo.hStdError = child_stderr
        startup.lpAttributeList = attribute_list
        environment = {
            "LOCALAPPDATA": str(profile),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "TEMP": str(temp),
            "TMP": str(temp),
            "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        }
        env_block = ctypes.create_unicode_buffer(
            "\0".join(f"{key}={value}" for key, value in sorted(environment.items())) + "\0\0"
        )
        command = ctypes.create_unicode_buffer(f'"{image}"')
        win._must(
            kernel.CreateProcessW(
                str(image),
                command,
                None,
                None,
                True,
                win._CREATE_NO_WINDOW
                | win._CREATE_SUSPENDED
                | win._CREATE_UNICODE_ENVIRONMENT
                | win._EXTENDED_STARTUPINFO_PRESENT,
                env_block,
                str(image.parent),
                ctypes.byref(startup),
                ctypes.byref(process),
            ),
            "lpac-process-creation-failed",
        )
        created = True
        for handle in (child_stdin, child_stdout, child_stderr):
            win._close(kernel, handle)
        child_stdin = child_stdout = child_stderr = None
        token = win._token(advapi, kernel, process.hProcess, sid_text)
        verify_lpac_no_write(kernel, advapi, process.hProcess, profile.parent, image.parent.parent)
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise win.LPACError("lpac-job-creation-failed")
        parent_affinity = ctypes.c_size_t()
        system_affinity = ctypes.c_size_t()
        win._must(
            kernel.GetProcessAffinityMask(
                kernel.GetCurrentProcess(), ctypes.byref(parent_affinity), ctypes.byref(system_affinity)
            ),
            "lpac-parent-affinity-unavailable",
        )
        if not parent_affinity.value:
            raise win.LPACError("lpac-parent-affinity-invalid")
        one_cpu = parent_affinity.value & -parent_affinity.value
        limits = win._ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            win._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | win._JOB_OBJECT_LIMIT_JOB_MEMORY
            | win._JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | win._JOB_OBJECT_LIMIT_AFFINITY
        )
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        limits.BasicLimitInformation.Affinity = one_cpu
        limits.JobMemoryLimit = memory_mib * 1_048_576
        win._must(
            kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)), "lpac-job-limit-failed"
        )
        win._must(kernel.AssignProcessToJobObject(job, process.hProcess), "lpac-job-assignment-failed")
        assigned = True
        worker_affinity = ctypes.c_size_t()
        worker_system = ctypes.c_size_t()
        win._must(
            kernel.GetProcessAffinityMask(process.hProcess, ctypes.byref(worker_affinity), ctypes.byref(worker_system)),
            "lpac-worker-affinity-unavailable",
        )
        if worker_affinity.value != one_cpu:
            raise win.LPACError("lpac-worker-cpu-concurrency-unbounded")
        if kernel.ResumeThread(process.hThread) == 0xFFFFFFFF:
            raise win.LPACError("lpac-process-resume-failed")
        completed: queue.Queue[tuple[bytes, int] | BaseException] = queue.Queue(maxsize=1)

        def exchange() -> None:
            try:
                completed.put(dialogue(kernel, parent_stdin, parent_stdout, request))
            except BaseException as exc:
                completed.put(exc)

        thread = threading.Thread(target=exchange, name="lpac-plugin-pipes", daemon=True)
        thread.start()
        deadline = time.monotonic() + wall_seconds
        while True:
            if cancelled is not None and cancelled():
                raise win.LPACError("lpac-worker-cancelled")
            if time.monotonic() >= deadline:
                raise win.LPACError("lpac-worker-timeout")
            try:
                result = completed.get(timeout=0.05)
            except queue.Empty:
                continue
            if isinstance(result, BaseException):
                if isinstance(result, win.LPACError):
                    raise result
                raise win.LPACError("lpac-worker-protocol-or-broker-failed") from None
            output, calls = result
            _wait_for_worker_exit(kernel, process.hProcess, deadline, cancelled)
            exit_code = wintypes.DWORD()
            win._must(
                kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(exit_code)), "lpac-worker-exit-unavailable"
            )
            if exit_code.value != 0:
                raise win.LPACError(f"lpac-worker-failed:{exit_code.value}")
            if win._read(kernel, parent_stdout):
                raise win.LPACError("lpac-worker-trailing-output")
            return WorkerResult(output, token, calls)
    finally:
        if created:
            if assigned:
                kernel.TerminateJobObject(job, 1)
            else:
                kernel.TerminateProcess(process.hProcess, 1)
        for owned_handle in (
            process.hThread,
            process.hProcess,
            job,
            child_stdin,
            parent_stdin,
            parent_stdout,
            child_stdout,
            parent_stderr,
            child_stderr,
        ):
            win._close(kernel, owned_handle)
        if attribute_list:
            kernel.DeleteProcThreadAttributeList(attribute_list)


def run_connector(
    runtime: SignedWorkerRuntime,
    package: VerifiedPluginPackage,
    package_files: Mapping[str, bytes],
    *,
    job_nonce: str,
    invocation_id: str,
    operation: str,
    input_data: bytes,
    broker_callback: Callable[[dict[str, Any]], bytes],
    cancelled: Callable[[], bool] | None = None,
) -> WorkerResult:
    """Launch one exact signed worker and verified plugin; fail closed on denial."""

    if runtime.application_public_key != APPLICATION_INVENTORY_PUBLIC_KEY:
        raise win.LPACError("lpac-worker-application-pin-mismatch")
    verify_worker_runtime(runtime)
    if not isinstance(package, VerifiedPluginPackage) or package._seal is not _VERIFIED_SEAL:
        raise win.LPACError("lpac-plugin-unverified")
    if (
        not isinstance(job_nonce, str)
        or len(job_nonce) != 32
        or any(char not in "0123456789abcdef" for char in job_nonce)
        or not isinstance(invocation_id, str)
        or not 0 < len(invocation_id) <= 128
        or operation not in package.manifest.operations
        or not isinstance(input_data, bytes)
        or len(input_data) > MAX_BINARY_FRAME
        or not callable(broker_callback)
    ):
        raise win.LPACError("lpac-invocation-invalid")
    profile_limits = package.manifest.resource_profile

    def prepare_request(image: Path) -> dict[str, Any]:
        entry_sha = _stage_plugin(package, package_files, image)
        return {
            "protocolVersion": "1.0",
            "jobNonce": job_nonce,
            "sequence": 0,
            "operation": "invoke",
            "invocationId": invocation_id,
            "connectorOperation": operation,
            "inputSha256": hashlib.sha256(input_data).hexdigest(),
            "inputLength": len(input_data),
            "pluginSha256": entry_sha,
        }

    def dialogue(kernel: Any, parent_stdin: int, parent_stdout: int, request: dict[str, Any]) -> tuple[bytes, int]:
        return _dialogue(kernel, parent_stdin, parent_stdout, request, input_data, broker_callback)

    return _run_signed_worker(
        runtime,
        prepare_request=prepare_request,
        dialogue=dialogue,
        memory_mib=profile_limits.committed_memory_mi_b,
        wall_seconds=profile_limits.wall_time_seconds,
        cancelled=cancelled,
    )


def _run_signed_worker(
    runtime: SignedWorkerRuntime,
    *,
    prepare_request: Callable[[Path], dict[str, Any]],
    dialogue: Callable[[Any, int, int, dict[str, Any]], tuple[bytes, int]],
    memory_mib: int,
    wall_seconds: int,
    cancelled: Callable[[], bool] | None,
) -> WorkerResult:
    """Shared exact signed-runtime, LPAC, Job and guardian lifecycle."""

    if runtime.application_public_key != APPLICATION_INVENTORY_PUBLIC_KEY:
        raise win.LPACError("lpac-worker-application-pin-mismatch")
    verify_worker_runtime(runtime)
    if not 1 <= memory_mib <= 4096 or not 1 <= wall_seconds <= 900:
        raise win.LPACError("lpac-worker-profile-invalid")
    kernel, advapi, userenv, _ole = win._api()
    name: str | None = None
    sid: int | None = None
    sid_text: str | None = None
    runtime_root: Path | None = None
    runtime_parent: Path | None = None
    guardian: GuardianProcess | None = None
    acl_started = False
    acl_status = AclRestoration()
    try:
        guardian = start_guardian()
        name, sid_text, profile, temp, runtime_root = (
            guardian.name,
            guardian.sid_text,
            guardian.profile,
            guardian.temp,
            guardian.runtime,
        )
        runtime_parent = runtime_root.parent
        sid = win._derive_profile_sid(userenv, advapi, kernel, name, sid_text)
        localappdata = Path(os.environ["LOCALAPPDATA"]).resolve(strict=True)
        # AppContainer-hosted desktop installs have a long LOCALAPPDATA prefix.
        # Keep this job-owned leaf short so Windows APIs without long-path
        # support can still load the signed onedir runtime.
        if runtime_parent != (localappdata / "RoWorker").resolve(strict=True):
            raise win.LPACError("lpac-runtime-parent-invalid")
        if any(runtime_root.iterdir()):
            raise win.LPACError("lpac-runtime-owned-root-invalid")
        shutil.copytree(runtime.package, runtime_root, dirs_exist_ok=True)
        staged_runtime = SignedWorkerRuntime(
            runtime_root, runtime.inventory_bytes, runtime.signature, runtime.application_public_key
        )
        image = verify_worker_runtime(staged_runtime)
        request = prepare_request(image)
        guardian.seal()
        acl_started = True
        with no_write_lpac_acl(profile, temp, runtime_root, sid_text, kernel, advapi, restoration=acl_status):

            def cancelled_or_guardian_lost() -> bool:
                return not guardian.alive() or (cancelled is not None and cancelled())

            try:
                result = _launch_signed_worker(
                    image,
                    sid,
                    sid_text,
                    profile,
                    temp,
                    request,
                    memory_mib,
                    wall_seconds,
                    dialogue,
                    cancelled_or_guardian_lost,
                )
            except win.LPACError:
                if not guardian.alive():
                    raise GuardianError("lpac-guardian-exited") from None
                raise
        return result
    finally:
        guardian_error: GuardianError | None = None
        guardian_recovered = False
        if guardian:
            try:
                guardian_recovered = guardian.finish(restored=acl_status.restored)
            except GuardianError as exc:
                guardian_error = exc
        if sid:
            advapi.FreeSid(sid)
        # A timed-out guardian still owns exact cleanup and may be waiting on
        # an OS file lock. Never race it or kill its remaining authority.
        if guardian and not guardian_recovered and not guardian.alive() and (not acl_started or acl_status.restored):
            try:
                if name and profile.parent.exists() and userenv.DeleteAppContainerProfile(name) != 0:
                    raise win.LPACError("lpac-profile-cleanup-failed")
            finally:
                if runtime_root and runtime_root.exists():
                    resolved = runtime_root.resolve(strict=True)
                    if (
                        resolved.parent != runtime_parent
                        or len(resolved.name) != 16
                        or any(char not in "0123456789abcdef" for char in resolved.name)
                        or runtime_root.is_symlink()
                        or runtime_root.is_junction()
                    ):
                        raise win.LPACError("lpac-runtime-cleanup-target-invalid")
                    shutil.rmtree(resolved)
        if guardian_error:
            raise guardian_error
