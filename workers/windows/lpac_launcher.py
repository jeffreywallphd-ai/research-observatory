"""Trusted Windows LPAC launch adapter for a disposable packaged worker probe.

The probe-only package inventory is generated with the test build. Production
plugin admission must bind an application-signed inventory before using this
adapter. No plugin code is loaded by this module.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import secrets
import shutil
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .protocol import MAX_CONTROL_FRAME, decode_frame, encode_frame

IMAGE_NAME = "research-observatory-plugin-probe-x86_64-pc-windows-msvc"
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_CREATE_SUSPENDED = 0x00000004
_CREATE_NO_WINDOW = 0x08000000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_STARTF_USESTDHANDLES = 0x00000100
_PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 131074
_PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 131081
_PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY = 131087
_PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT = 1
_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
_JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_HANDLE_FLAG_INHERIT = 1


class LPACError(RuntimeError):
    """Fail-closed launch or boundary qualification failure."""


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class _SecurityCapabilities(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
    ]


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _GenericMapping(ctypes.Structure):
    _fields_ = [
        (name, wintypes.DWORD)
        for name in (
            "GenericRead",
            "GenericWrite",
            "GenericExecute",
            "GenericAll",
        )
    ]


def _api() -> tuple[Any, Any, Any, Any]:
    if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise LPACError("lpac-windows-x64-required")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(_SecurityAttributes),
        wintypes.DWORD,
    ]
    kernel.CreatePipe.restype = wintypes.BOOL
    kernel.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
    kernel.SetHandleInformation.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_SecurityAttributes),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    kernel.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(_StartupInfoEx),
        ctypes.POINTER(_ProcessInformation),
    ]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.WriteFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel.WriteFile.restype = wintypes.BOOL
    kernel.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel.ReadFile.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    userenv.CreateAppContainerProfile.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    userenv.CreateAppContainerProfile.restype = ctypes.c_long
    userenv.GetAppContainerFolderPath.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_wchar_p)]
    userenv.GetAppContainerFolderPath.restype = ctypes.c_long
    userenv.DeleteAppContainerProfile.argtypes = [wintypes.LPCWSTR]
    userenv.DeleteAppContainerProfile.restype = ctypes.c_long
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.FreeSid.argtypes = [ctypes.c_void_p]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.DuplicateToken.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(wintypes.HANDLE)]
    advapi.DuplicateToken.restype = wintypes.BOOL
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    advapi.AccessCheck.argtypes = [
        ctypes.c_void_p,
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(_GenericMapping),
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi.AccessCheck.restype = wintypes.BOOL
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    return kernel, advapi, userenv, ole


def _must(ok: Any, code: str) -> None:
    if not ok:
        raise LPACError(f"{code}:{ctypes.get_last_error()}")


def _close(kernel: Any, handle: int | None) -> None:
    if handle and handle != _INVALID_HANDLE:
        kernel.CloseHandle(handle)


def _verified_image(package: Path, inventory: dict[str, Any]) -> Path:
    if not isinstance(inventory, dict) or set(inventory) != {"schemaVersion", "documentType", "imagePath", "files"}:
        raise LPACError("lpac-package-inventory-invalid")
    if inventory["schemaVersion"] != "1.0" or inventory["documentType"] != "disposable-lpac-probe-package":
        raise LPACError("lpac-package-inventory-invalid")
    image_relative = f"{IMAGE_NAME}/{IMAGE_NAME}.exe"
    if inventory["imagePath"] != image_relative or not isinstance(inventory["files"], list):
        raise LPACError("lpac-package-inventory-invalid")
    package = package.resolve(strict=True)
    if not package.is_dir() or package.is_symlink() or package.is_junction():
        raise LPACError("lpac-package-path-invalid")
    expected: dict[str, str] = {}
    for entry in inventory["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise LPACError("lpac-package-inventory-invalid")
        path, digest = entry["path"], entry["sha256"]
        if (
            not isinstance(path, str)
            or not path
            or "\\" in path
            or ":" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or path in expected
        ):
            raise LPACError("lpac-package-inventory-invalid")
        expected[path] = digest
    if image_relative not in expected:
        raise LPACError("lpac-package-image-missing")
    actual: dict[str, str] = {}
    total = 0
    for path in package.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise LPACError("lpac-package-redirect-denied")
        if path.is_file():
            raw = path.read_bytes()
            total += len(raw)
            if total > 134_217_728:
                raise LPACError("lpac-package-oversize")
            actual[path.relative_to(package).as_posix()] = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise LPACError("lpac-package-hash-mismatch")
    return package / image_relative


def _run_icacls(path: Path, *arguments: str) -> None:
    executable = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/icacls.exe"
    result = subprocess.run([str(executable), str(path), *arguments], capture_output=True, timeout=30)
    if result.returncode != 0:
        raise LPACError("lpac-acl-setup-failed")


def _profile(userenv: Any, advapi: Any, ole: Any) -> tuple[str, int, str, Path, Path]:
    name = "ResearchObservatory.PluginProbe." + secrets.token_hex(12)
    sid = ctypes.c_void_p()
    try:
        hr = userenv.CreateAppContainerProfile(name, name, "Disposable LPAC probe", None, 0, ctypes.byref(sid))
        if hr != 0 or not sid.value:
            raise LPACError(f"lpac-profile-creation-failed:0x{hr & 0xFFFFFFFF:08x}")
        sid_text_pointer = ctypes.c_wchar_p()
        _must(advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text_pointer)), "lpac-profile-sid-invalid")
        try:
            sid_text = sid_text_pointer.value
        finally:
            ctypes.WinDLL("kernel32", use_last_error=True).LocalFree(ctypes.cast(sid_text_pointer, ctypes.c_void_p))
        if not sid_text:
            raise LPACError("lpac-profile-sid-invalid")
        folder_pointer = ctypes.c_wchar_p()
        if userenv.GetAppContainerFolderPath(sid_text, ctypes.byref(folder_pointer)) != 0 or not folder_pointer.value:
            raise LPACError("lpac-profile-folder-unavailable")
        try:
            profile_folder = Path(folder_pointer.value).resolve()
        finally:
            ole.CoTaskMemFree(ctypes.cast(folder_pointer, ctypes.c_void_p))
        package_root = profile_folder.parent
        appdata_packages = Path(os.environ["LOCALAPPDATA"]).resolve() / "Packages"
        if not package_root.is_relative_to(appdata_packages) or package_root == appdata_packages:
            raise LPACError("lpac-profile-folder-unsafe")
        temp_folder = profile_folder / "Temp"
        temp_folder.mkdir(parents=True, exist_ok=True)
        return name, sid.value, sid_text, profile_folder, temp_folder
    except BaseException:
        if sid.value:
            advapi.FreeSid(sid)
        userenv.DeleteAppContainerProfile(name)
        raise


def _access_check(advapi: Any, kernel: Any, token: int, principal_sid: str) -> bool:
    """Probe the LPAC property as an access decision, not an unsupported token query."""

    descriptor = ctypes.c_void_p()
    sddl = f"O:SYG:SYD:(A;;RC;;;WD)(A;;RC;;;{principal_sid})"
    _must(
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None),
        "lpac-access-probe-descriptor-invalid",
    )
    try:
        privileges = ctypes.create_string_buffer(1024)
        privileges_length = wintypes.DWORD(len(privileges))
        granted = wintypes.DWORD()
        access_status = wintypes.BOOL()
        mapping = _GenericMapping()
        _must(
            advapi.AccessCheck(
                descriptor,
                token,
                0x00020000,
                ctypes.byref(mapping),
                privileges,
                ctypes.byref(privileges_length),
                ctypes.byref(granted),
                ctypes.byref(access_status),
            ),
            "lpac-access-probe-failed",
        )
        return bool(access_status.value)
    finally:
        kernel.LocalFree(descriptor)


def _token(advapi: Any, kernel: Any, process: int, expected_sid: str) -> dict[str, Any]:
    token = wintypes.HANDLE()
    _must(advapi.OpenProcessToken(process, 0xA, ctypes.byref(token)), "lpac-token-unavailable")
    try:

        def information(kind: int) -> bytes:
            if kind == 29:
                value = wintypes.DWORD()
                returned = wintypes.DWORD()
                _must(
                    advapi.GetTokenInformation(
                        token, kind, ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(returned)
                    ),
                    f"lpac-token-information-unavailable-{kind}",
                )
                if returned.value != ctypes.sizeof(value):
                    raise LPACError("lpac-token-information-invalid")
                return value.value.to_bytes(4, "little")
            size = wintypes.DWORD()
            advapi.GetTokenInformation(token, kind, None, 0, ctypes.byref(size))
            if not 0 < size.value <= 65_536:
                raise LPACError("lpac-token-information-invalid")
            buffer = ctypes.create_string_buffer(size.value)
            _must(
                advapi.GetTokenInformation(token, kind, buffer, size, ctypes.byref(size)),
                "lpac-token-information-unavailable",
            )
            return buffer.raw[: size.value]

        app_container = int.from_bytes(information(29)[:4], "little") != 0
        capability_count = int.from_bytes(information(30)[:4], "little")
        # TokenAppContainerSid returns a pointer into the same call buffer; keep
        # it alive while converting the SID to a string.
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 31, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        _must(advapi.GetTokenInformation(token, 31, buffer, size, ctypes.byref(size)), "lpac-token-sid-unavailable")
        sid = ctypes.c_void_p.from_buffer(buffer).value
        sid_pointer = ctypes.c_wchar_p()
        _must(sid and advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_pointer)), "lpac-token-sid-invalid")
        try:
            sid_text = sid_pointer.value
        finally:
            kernel.LocalFree(ctypes.cast(sid_pointer, ctypes.c_void_p))
        if not app_container or capability_count != 0 or sid_text != expected_sid:
            raise LPACError("lpac-token-not-isolated")
        impersonation = wintypes.HANDLE()
        _must(advapi.DuplicateToken(token, 2, ctypes.byref(impersonation)), "lpac-token-duplicate-failed")
        try:
            own_package_allowed = _access_check(advapi, kernel, impersonation, expected_sid)
            all_packages_allowed = _access_check(advapi, kernel, impersonation, "S-1-15-2-1")
        finally:
            _close(kernel, impersonation.value)
        if not own_package_allowed or all_packages_allowed:
            raise LPACError("lpac-all-application-packages-not-denied")
        return {
            "appContainer": True,
            "lessPrivileged": True,
            "capabilityCount": capability_count,
            "allApplicationPackagesDenied": True,
        }
    finally:
        _close(kernel, token.value)


def _current_user_sid(advapi: Any, kernel: Any) -> str:
    token = wintypes.HANDLE()
    _must(advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x8, ctypes.byref(token)), "lpac-owner-token-unavailable")
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not 0 < size.value <= 65_536:
            raise LPACError("lpac-owner-sid-invalid")
        buffer = ctypes.create_string_buffer(size.value)
        _must(advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)), "lpac-owner-sid-unavailable")
        sid = ctypes.c_void_p.from_buffer(buffer).value
        pointer = ctypes.c_wchar_p()
        _must(sid and advapi.ConvertSidToStringSidW(sid, ctypes.byref(pointer)), "lpac-owner-sid-invalid")
        try:
            if not pointer.value:
                raise LPACError("lpac-owner-sid-invalid")
            return pointer.value
        finally:
            kernel.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))
    finally:
        _close(kernel, token.value)


def _pipe(kernel: Any, attributes: _SecurityAttributes) -> tuple[int, int]:
    read = wintypes.HANDLE()
    write = wintypes.HANDLE()
    _must(
        kernel.CreatePipe(ctypes.byref(read), ctypes.byref(write), ctypes.byref(attributes), 0),
        "lpac-pipe-creation-failed",
    )
    return read.value, write.value


def _write(kernel: Any, handle: int, data: bytes) -> None:
    for start in range(0, len(data), 32_768):
        chunk = ctypes.create_string_buffer(data[start : start + 32_768])
        written = wintypes.DWORD()
        _must(
            kernel.WriteFile(handle, chunk, len(chunk.raw) - 1, ctypes.byref(written), None), "lpac-pipe-write-failed"
        )
        if written.value != len(chunk.raw) - 1:
            raise LPACError("lpac-pipe-short-write")


def _read(kernel: Any, handle: int) -> bytes:
    chunks = []
    total = 0
    while True:
        buffer = ctypes.create_string_buffer(32_768)
        count = wintypes.DWORD()
        if not kernel.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None):
            if ctypes.get_last_error() == 109:  # ERROR_BROKEN_PIPE
                return b"".join(chunks)
            raise LPACError("lpac-pipe-read-failed")
        if count.value == 0:
            return b"".join(chunks)
        total += count.value
        if total > MAX_CONTROL_FRAME + 4:
            raise LPACError("lpac-worker-output-oversize")
        chunks.append(buffer.raw[: count.value])


def _launch(image: Path, sid: int, sid_text: str, request: dict[str, Any]) -> dict[str, Any]:
    kernel, advapi, _, _ = _api()
    attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), None, True)
    child_stdin = parent_stdin = parent_stdout = child_stdout = parent_stderr = child_stderr = job = None
    process = _ProcessInformation()
    attribute_list = None
    created = assigned = False
    try:
        child_stdin, parent_stdin = _pipe(kernel, attributes)
        parent_stdout, child_stdout = _pipe(kernel, attributes)
        parent_stderr, child_stderr = _pipe(kernel, attributes)
        _must(kernel.SetHandleInformation(parent_stdin, _HANDLE_FLAG_INHERIT, 0), "lpac-handle-policy-failed")
        _must(kernel.SetHandleInformation(parent_stdout, _HANDLE_FLAG_INHERIT, 0), "lpac-handle-policy-failed")
        _must(kernel.SetHandleInformation(parent_stderr, _HANDLE_FLAG_INHERIT, 0), "lpac-handle-policy-failed")
        handles = (wintypes.HANDLE * 3)(child_stdin, child_stdout, child_stderr)
        capabilities = _SecurityCapabilities(sid, None, 0, 0)
        policy = wintypes.DWORD(_PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT)
        size = ctypes.c_size_t()
        kernel.InitializeProcThreadAttributeList(None, 3, 0, ctypes.byref(size))
        if not size.value or size.value > 65_536:
            raise LPACError("lpac-attribute-allocation-invalid")
        buffer = ctypes.create_string_buffer(size.value)
        attribute_list = ctypes.c_void_p(ctypes.addressof(buffer))
        _must(
            kernel.InitializeProcThreadAttributeList(attribute_list, 3, 0, ctypes.byref(size)),
            "lpac-attribute-creation-failed",
        )
        for name, value, length in (
            (_PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, ctypes.byref(capabilities), ctypes.sizeof(capabilities)),
            (_PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY, ctypes.byref(policy), ctypes.sizeof(policy)),
            (_PROC_THREAD_ATTRIBUTE_HANDLE_LIST, ctypes.byref(handles), ctypes.sizeof(handles)),
        ):
            _must(
                kernel.UpdateProcThreadAttribute(attribute_list, 0, name, value, length, None, None),
                "lpac-attribute-update-failed",
            )
        startup = _StartupInfoEx()
        startup.StartupInfo.cb = ctypes.sizeof(_StartupInfoEx)
        startup.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = child_stdin
        startup.StartupInfo.hStdOutput = child_stdout
        startup.StartupInfo.hStdError = child_stderr
        startup.lpAttributeList = attribute_list
        env_fields = {
            "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "TEMP": os.environ["TEMP"],
            "TMP": os.environ["TEMP"],
            "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        }
        env_block = ctypes.create_unicode_buffer(
            "\0".join(f"{key}={value}" for key, value in sorted(env_fields.items())) + "\0\0"
        )
        command = ctypes.create_unicode_buffer(f'"{image}"')
        _must(
            kernel.CreateProcessW(
                str(image),
                command,
                None,
                None,
                True,
                _CREATE_NO_WINDOW | _CREATE_SUSPENDED | _CREATE_UNICODE_ENVIRONMENT | _EXTENDED_STARTUPINFO_PRESENT,
                env_block,
                str(image.parent),
                ctypes.byref(startup),
                ctypes.byref(process),
            ),
            "lpac-process-creation-failed",
        )
        created = True
        _close(kernel, child_stdin)
        child_stdin = None
        _close(kernel, child_stdout)
        child_stdout = None
        _close(kernel, child_stderr)
        child_stderr = None
        token = _token(advapi, kernel, process.hProcess, sid_text)
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise LPACError("lpac-job-creation-failed")
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | _JOB_OBJECT_LIMIT_JOB_MEMORY | _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        )
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        limits.JobMemoryLimit = 256 * 1024 * 1024
        _must(
            kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)), "lpac-job-limit-failed"
        )
        _must(kernel.AssignProcessToJobObject(job, process.hProcess), "lpac-job-assignment-failed")
        assigned = True
        if kernel.ResumeThread(process.hThread) == 0xFFFFFFFF:
            raise LPACError("lpac-process-resume-failed")
        _write(kernel, parent_stdin, encode_frame(request))
        _close(kernel, parent_stdin)
        parent_stdin = None
        waited = kernel.WaitForSingleObject(process.hProcess, 60_000)
        if waited != 0:
            raise LPACError("lpac-worker-timeout-or-wait-failed")
        exit_code = wintypes.DWORD()
        _must(kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(exit_code)), "lpac-worker-exit-unavailable")
        if exit_code.value != 0:
            diagnostic = _read(kernel, parent_stderr)[:4096].decode("utf-8", errors="replace")
            raise LPACError(f"lpac-worker-failed:{exit_code.value}:{diagnostic}")
        response = decode_frame(_read(kernel, parent_stdout), expected_nonce=request["jobNonce"], expected_sequence=1)
        if (
            set(response) != {"protocolVersion", "jobNonce", "sequence", "operation", "probes"}
            or response["operation"] != "probe-result"
        ):
            raise LPACError("lpac-worker-response-invalid")
        return {"token": token, "probes": response["probes"]}
    finally:
        if created:
            if assigned:
                kernel.TerminateJobObject(job, 1)
            else:
                kernel.TerminateProcess(process.hProcess, 1)
        _close(kernel, process.hThread)
        _close(kernel, process.hProcess)
        _close(kernel, job)
        for handle in (child_stdin, parent_stdin, parent_stdout, child_stdout, parent_stderr, child_stderr):
            _close(kernel, handle)
        if attribute_list:
            kernel.DeleteProcThreadAttributeList(attribute_list)


def _validated_loopback_observation(value: Any) -> dict[str, Any]:
    """Reject a connection or an ambiguous network-stage report."""

    if not isinstance(value, dict) or set(value) != {
        "startupCode",
        "connectAttempted",
        "connectOutcome",
        "connectErrorCode",
    }:
        raise LPACError("lpac-network-observation-invalid")
    startup = value["startupCode"]
    attempted = value["connectAttempted"]
    outcome = value["connectOutcome"]
    error = value["connectErrorCode"]
    if not isinstance(startup, int) or isinstance(startup, bool) or not 0 <= startup < 2**32:
        raise LPACError("lpac-network-observation-invalid")
    if not isinstance(attempted, bool):
        raise LPACError("lpac-network-observation-invalid")
    if attempted:
        if startup != 0 or outcome != "denied" or not isinstance(error, int) or isinstance(error, bool) or error <= 0:
            raise LPACError("lpac-network-connection-not-denied")
    elif outcome != "not-tested" or (
        startup == 0 and (not isinstance(error, int) or isinstance(error, bool) or error <= 0)
    ) or (startup != 0 and error is not None):
        raise LPACError("lpac-network-observation-invalid")
    return value


def run_probe(
    package: Path, inventory: dict[str, Any], *, read_path: Path, write_path: Path, loopback_port: int
) -> dict[str, Any]:
    """Run one fixed adversarial probe; preserve each network attempt stage.

    This is a test-only feasibility vertical. It is not a plugin dispatcher or
    evidence of a production broker, grant, durable job or audit integration.
    """

    _verified_image(package, inventory)
    kernel, advapi, userenv, ole = _api()
    name: str | None = None
    sid: int | None = None
    sid_text: str | None = None
    try:
        name, sid, sid_text, profile, temp = _profile(userenv, advapi, ole)
        runtime_root = profile / "runtime"
        shutil.copytree(package, runtime_root)
        image = _verified_image(runtime_root, inventory)
        user_sid = _current_user_sid(advapi, kernel)
        _run_icacls(profile.parent, "/grant", f"*{sid_text}:(OI)(CI)(RX)", f"*{user_sid}:(OI)(CI)(RX)", "/T")
        _run_icacls(profile.parent, "/deny", f"*{sid_text}:(OI)(CI)(W)", "/T")
        _run_icacls(profile, "/deny", f"*{sid_text}:(WD,AD,DC)")
        _run_icacls(temp, "/deny", f"*{sid_text}:(WD,AD,DC)")
        request = {
            "protocolVersion": "1.0",
            "jobNonce": secrets.token_hex(16),
            "sequence": 0,
            "operation": "probe",
            "readPath": str(read_path.resolve(strict=True)),
            "writePath": str(write_path.resolve(strict=False)),
            "loopbackPort": loopback_port,
        }
        result = _launch(image, sid, sid_text, request)
        probes = result["probes"]
        _validated_loopback_observation(probes.get("directLoopback") if isinstance(probes, dict) else None)
        expected_denials = {
            "unrelatedRead": "denied",
            "outsideWrite": "denied",
            "profileWrite": "denied",
            "tempWrite": "denied",
            "parentEnvironmentSecret": "denied",
        }
        observed_denials = {key: value for key, value in probes.items() if key != "directLoopback"}
        if observed_denials != expected_denials:
            mismatched = sorted(
                key
                for key in expected_denials.keys() | observed_denials.keys()
                if observed_denials.get(key) != expected_denials.get(key)
            )
            raise LPACError("lpac-ambient-authority-not-denied:" + ",".join(mismatched))
        return result
    finally:
        if sid:
            advapi.FreeSid(sid)
        if name and userenv.DeleteAppContainerProfile(name) != 0 and sys.exc_info()[0] is None:
            raise LPACError("lpac-profile-cleanup-failed")
