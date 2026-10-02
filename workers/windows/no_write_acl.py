"""Reversible, per-object Windows ACL lockdown for one disposable LPAC job.

The profile is created for this job and the runtime tree is copied to a fresh
application-owned directory. No pre-existing user project/vault ACL is changed.
Restoration uses pre-opened handles, and verifies the original owner/DACL SDDL.
"""

from __future__ import annotations

import ctypes
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lpac_launcher import LPACError, _close, _current_user_sid, _run_icacls

_READ_CONTROL = 0x00020000
_WRITE_DAC = 0x00040000
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_OWNER_AND_DACL = 0x00000001 | 0x00000004
_DACL_ONLY = 0x00000004
_PROTECTED_DACL = 0x80000000
_UNPROTECTED_DACL = 0x20000000
_SE_FILE_OBJECT = 1
_WRITE_ACCESS = (0x00000002, 0x00000004, 0x00000010, 0x00000040, 0x00000100, 0x00010000, _WRITE_DAC, 0x00080000)


def _security_api(kernel: Any, advapi: Any) -> None:
    advapi.ImpersonateLoggedOnUser.argtypes = [wintypes.HANDLE]
    advapi.ImpersonateLoggedOnUser.restype = wintypes.BOOL
    advapi.RevertToSelf.argtypes = []
    advapi.RevertToSelf.restype = wintypes.BOOL
    advapi.GetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetSecurityInfo.restype = wintypes.DWORD
    advapi.SetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi.SetSecurityInfo.restype = wintypes.DWORD
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL


def _sddl(kernel: Any, advapi: Any, handle: int) -> str:
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    code = advapi.GetSecurityInfo(
        handle,
        _SE_FILE_OBJECT,
        _OWNER_AND_DACL,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if code or not owner.value or not dacl.value or not descriptor.value:
        raise LPACError("lpac-acl-snapshot-failed")
    try:
        value = ctypes.c_wchar_p()
        length = wintypes.DWORD()
        if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, _OWNER_AND_DACL, ctypes.byref(value), ctypes.byref(length)
        ):
            raise LPACError("lpac-acl-snapshot-failed")
        try:
            if not value.value or "D:" not in value.value:
                raise LPACError("lpac-acl-snapshot-failed")
            return value.value
        finally:
            kernel.LocalFree(ctypes.cast(value, ctypes.c_void_p))
    finally:
        kernel.LocalFree(descriptor)


class _SavedAcl:
    __slots__ = ("dacl", "descriptor", "handle", "path", "sddl")

    def __init__(self, path: Path, handle: int, dacl: int, descriptor: int, sddl: str):
        self.path = path
        self.handle = handle
        self.dacl = dacl
        self.descriptor = descriptor
        self.sddl = sddl


@dataclass(slots=True)
class AclRestoration:
    restored: bool = False


def _open_saved(kernel: Any, advapi: Any, path: Path, user_sid: str) -> _SavedAcl:
    handle = kernel.CreateFileW(
        str(path),
        _READ_CONTROL | _WRITE_DAC,
        7,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise LPACError("lpac-acl-restore-handle-unavailable")
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    try:
        code = advapi.GetSecurityInfo(
            handle,
            _SE_FILE_OBJECT,
            _OWNER_AND_DACL,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if code or not owner.value or not dacl.value or not descriptor.value:
            raise LPACError("lpac-acl-backup-failed")
        owner_text = ctypes.c_wchar_p()
        if not advapi.ConvertSidToStringSidW(owner, ctypes.byref(owner_text)):
            raise LPACError("lpac-acl-owner-unavailable")
        try:
            if owner_text.value != user_sid:
                raise LPACError("lpac-acl-owner-mismatch")
        finally:
            kernel.LocalFree(ctypes.cast(owner_text, ctypes.c_void_p))
        original = _sddl(kernel, advapi, handle)
        return _SavedAcl(path, handle, dacl.value, descriptor.value, original)
    except BaseException:
        if descriptor.value:
            kernel.LocalFree(descriptor)
        _close(kernel, handle)
        raise


def _tree(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise LPACError("lpac-acl-root-invalid")
    paths = [root, *root.rglob("*")]
    for path in paths:
        if not path.is_relative_to(root) or path.is_symlink() or path.is_junction():
            raise LPACError("lpac-acl-redirect-denied")
        if not path.is_file() and not path.is_dir():
            raise LPACError("lpac-acl-object-invalid")
    return paths


def verify_lpac_no_write(kernel: Any, advapi: Any, process: int, profile_root: Path, runtime: Path) -> None:
    """Probe actual opens under the suspended worker token before execution."""

    _security_api(kernel, advapi)
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(process, 0xA, ctypes.byref(token)):
        raise LPACError("lpac-acl-token-unavailable")
    impersonation = wintypes.HANDLE()
    try:
        if not advapi.DuplicateToken(token, 2, ctypes.byref(impersonation)):
            raise LPACError("lpac-acl-token-duplicate-failed")
        if not advapi.ImpersonateLoggedOnUser(impersonation):
            raise LPACError(f"lpac-acl-token-impersonation-failed:{ctypes.get_last_error()}")
        try:
            for path in (*_tree(profile_root), *_tree(runtime)):
                for access in _WRITE_ACCESS:
                    handle = kernel.CreateFileW(
                        str(path), access, 7, None, _OPEN_EXISTING, _FILE_FLAG_BACKUP_SEMANTICS, None
                    )
                    if handle and handle != ctypes.c_void_p(-1).value:
                        _close(kernel, handle)
                        raise LPACError(f"lpac-acl-worker-write-authority:{access:x}:{path.name}")
                    if ctypes.get_last_error() != 5:
                        raise LPACError(f"lpac-acl-denial-unverified:{ctypes.get_last_error()}:{path.name}")
        finally:
            if not advapi.RevertToSelf():
                raise LPACError("lpac-acl-token-revert-failed")
    finally:
        _close(kernel, impersonation.value)
        _close(kernel, token.value)


def _restore(kernel: Any, advapi: Any, saved: list[_SavedAcl]) -> None:
    errors: list[str] = []
    for item in reversed(saved):
        flags = item.sddl.split("D:", 1)[1].split("(", 1)[0]
        protection = _PROTECTED_DACL if "P" in flags else _UNPROTECTED_DACL
        code = advapi.SetSecurityInfo(
            item.handle,
            _SE_FILE_OBJECT,
            _DACL_ONLY | protection,
            None,
            None,
            item.dacl,
            None,
        )
        if code:
            errors.append("restore")
        _close(kernel, item.handle)
        kernel.LocalFree(item.descriptor)
    if errors:
        raise LPACError("lpac-acl-restore-failed")
    for item in saved:
        handle = kernel.CreateFileW(
            str(item.path),
            _READ_CONTROL,
            7,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if not handle or handle == ctypes.c_void_p(-1).value:
            raise LPACError("lpac-acl-restoration-unverified")
        try:
            if _sddl(kernel, advapi, handle) != item.sddl:
                raise LPACError("lpac-acl-restoration-mismatch")
        finally:
            _close(kernel, handle)


def restore_open_acl_handles(kernel: Any, advapi: Any, saved: list[_SavedAcl]) -> None:
    """Restore exact DACLs while a crash guardian keeps its backup handles."""

    for item in reversed(saved):
        flags = item.sddl.split("D:", 1)[1].split("(", 1)[0]
        protection = _PROTECTED_DACL if "P" in flags else _UNPROTECTED_DACL
        code = advapi.SetSecurityInfo(
            item.handle,
            _SE_FILE_OBJECT,
            _DACL_ONLY | protection,
            None,
            None,
            item.dacl,
            None,
        )
        if code:
            raise LPACError("lpac-acl-restore-failed")
    for item in saved:
        if _sddl(kernel, advapi, item.handle) != item.sddl:
            raise LPACError("lpac-acl-restoration-mismatch")


@contextmanager
def no_write_lpac_acl(
    profile: Path,
    temp: Path,
    runtime: Path,
    sid_text: str,
    kernel: Any,
    advapi: Any,
    *,
    restoration: AclRestoration | None = None,
) -> Iterator[AclRestoration]:
    """Lock down only new job-owned objects, restoring exact descriptors after exit."""

    if profile.name != "AC" or temp.parent != profile or temp.name != "Temp":
        raise LPACError("lpac-profile-layout-invalid")
    profile_root = profile.parent
    if runtime == profile_root or runtime.is_relative_to(profile_root):
        raise LPACError("lpac-runtime-root-invalid")
    _security_api(kernel, advapi)
    user_sid = _current_user_sid(advapi, kernel)
    runtime_saved: list[_SavedAcl] = []
    profile_saved: list[_SavedAcl] = []
    restoration = restoration or AclRestoration()
    try:
        runtime_paths = _tree(runtime)
        profile_paths = _tree(profile_root)
        for path in runtime_paths:
            runtime_saved.append(_open_saved(kernel, advapi, path, user_sid))
        for path in profile_paths:
            profile_saved.append(_open_saved(kernel, advapi, path, user_sid))
        for path in sorted(runtime_paths, key=lambda item: (-len(item.parts), str(item).lower())):
            _run_icacls(path, "/inheritance:r")
            _run_icacls(
                path,
                "/grant:r",
                f"*{sid_text}:(RX)",
                f"*{user_sid}:(RX)",
                "*S-1-5-18:(F)",
                "*S-1-5-32-544:(F)",
            )
            _run_icacls(path, "/deny", f"*{user_sid}:(WDAC,WO)", "*S-1-3-4:(WDAC,WO)")
        _run_icacls(profile_root, "/grant", f"*{sid_text}:(OI)(CI)(RX)", f"*{user_sid}:(OI)(CI)(RX)", "/T")
        _run_icacls(profile_root, "/deny", f"*{sid_text}:(OI)(CI)(W)", "/T")
        _run_icacls(profile, "/deny", f"*{sid_text}:(WD,AD,DC)")
        _run_icacls(temp, "/deny", f"*{sid_text}:(WD,AD,DC)")
        for path in sorted(profile_paths, key=lambda item: (-len(item.parts), str(item).lower())):
            denial = "(WD,AD,WEA,WA,DC,D,WDAC,WO)" if path.is_dir() else "(WD,AD,WEA,WA,D,WDAC,WO)"
            _run_icacls(path, "/deny", f"*{user_sid}:{denial}", "*S-1-3-4:(WDAC,WO)")
        yield restoration
    finally:
        try:
            if profile_saved:
                _restore(kernel, advapi, profile_saved)
        finally:
            if runtime_saved:
                _restore(kernel, advapi, runtime_saved)
        restoration.restored = True
