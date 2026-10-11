"""Windows current-user DPAPI adapter for the local profile credential port."""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import json
import os
import queue
import re
import secrets
import stat
import struct
import threading
import uuid
from contextlib import contextmanager, suppress
from ctypes import wintypes
from dataclasses import asdict, fields
from functools import cache
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from nacl import bindings as sodium
from nacl.exceptions import CryptoError

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .logging import emit_log_record
from .ports.credential_store import (
    CredentialStore,
    CredentialStoreProblem,
    SecretAccessContext,
    SecretAccessDenied,
    SecretAuditEvent,
    SecretAuditSink,
    SecretConflict,
    SecretCorrupt,
    SecretKind,
    SecretLease,
    SecretNotFound,
    SecretPurpose,
    SecretRecord,
    SecretReference,
    SecretUnavailable,
)
from .ports.database_keys import (
    DatabaseKeyConflict,
    DatabaseKeyLease,
    DatabaseKeyProvider,
    DatabaseKeyUnavailable,
    validate_database_key_identity,
)
from .ports.object_store_keys import ObjectMasterKey, ObjectMasterKeyProvider
from .ports.project_recovery import (
    RecoveryNativeInspection,
    RecoveryNativeSession,
    RecoveryOwnershipWitness,
    RecoveryProcessIdentity,
    RecoveryVerificationProblem,
)

_CRYPTPROTECT_UI_FORBIDDEN = 0x00000001
_ROOT_FILE = ".profile-vault-root-v1.dpapi"
_LOCK_FILE = ".profile-vault.lock"
_ROOT_MAGIC = b"RO-PROFILE-VAULT-ROOT-V1\0"
_ROOT_KEY_BYTES = sodium.crypto_aead_xchacha20poly1305_ietf_KEYBYTES
_ROOT_PLAINTEXT_BYTES = len(_ROOT_MAGIC) + _ROOT_KEY_BYTES + hashlib.sha256().digest_size
_RECORD_MAGIC = b"ROVLT1\0"
_RECORDS_DIRECTORY = "records"
_RECORD_SUFFIX = ".sealed"
_RECORD_METADATA_LENGTH = struct.Struct(">I")
_MAX_SECRET_BYTES = 1024 * 1024
_MAX_RECORD_BYTES = _MAX_SECRET_BYTES + 16 * 1024
_VERSION = re.compile(r"^[0-9a-f]{32}$")
_OBJECT_KEY_VERSION = "object-key-v1"
_LOCAL_ACTOR_FILE = ".local-actor-v1.dpapi"
_LOCAL_ACTOR_MAGIC = b"RO-LOCAL-ACTOR-V1\0"
_LOCAL_ACTOR_BYTES = len(_LOCAL_ACTOR_MAGIC) + 36 + hashlib.sha256().digest_size
_LOCAL_APP_DATA = uuid.UUID("f1b32785-6fba-4fcf-9d55-7b8e7f157091")
_RECOVERY_MAX_RECORD_BYTES = 16 * 1024
_RECOVERY_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECOVERY_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class _RecoverySecurityAttributes(ctypes.Structure):
    _fields_ = (("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p), ("inherit", wintypes.BOOL))


class _RecoveryFileInformation(ctypes.Structure):
    _fields_ = (
        ("attributes", wintypes.DWORD),
        ("created", wintypes.FILETIME),
        ("accessed", wintypes.FILETIME),
        ("written", wintypes.FILETIME),
        ("volume", wintypes.DWORD),
        ("size_high", wintypes.DWORD),
        ("size_low", wintypes.DWORD),
        ("links", wintypes.DWORD),
        ("index_high", wintypes.DWORD),
        ("index_low", wintypes.DWORD),
    )


@cache
def _recovery_windows_api() -> dict[str, Any]:
    if os.name != "nt":
        raise RecoveryVerificationProblem("ownership-platform-unavailable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    definitions = {
        "CreateFileW": (
            kernel,
            [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            ],
            wintypes.HANDLE,
        ),
        "CreateDirectoryW": (kernel, [wintypes.LPCWSTR, ctypes.c_void_p], wintypes.BOOL),
        "CloseHandle": (kernel, [wintypes.HANDLE], wintypes.BOOL),
        "GetCurrentProcess": (kernel, [], wintypes.HANDLE),
        "GetProcessTimes": (
            kernel,
            [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
            wintypes.BOOL,
        ),
        "GetModuleFileNameW": (kernel, [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD], wintypes.DWORD),
        "GetFileInformationByHandle": (kernel, [wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
        "ReadFile": (
            kernel,
            [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p],
            wintypes.BOOL,
        ),
        "WriteFile": (
            kernel,
            [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p],
            wintypes.BOOL,
        ),
        "SetFilePointerEx": (
            kernel,
            [wintypes.HANDLE, ctypes.c_longlong, ctypes.c_void_p, wintypes.DWORD],
            wintypes.BOOL,
        ),
        "FlushFileBuffers": (kernel, [wintypes.HANDLE], wintypes.BOOL),
        "SetFileInformationByHandle": (
            kernel,
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
            wintypes.BOOL,
        ),
        "OpenProcessToken": (
            security,
            [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)],
            wintypes.BOOL,
        ),
        "GetTokenInformation": (
            security,
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)],
            wintypes.BOOL,
        ),
        "ConvertSidToStringSidW": (security, [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)], wintypes.BOOL),
        "ConvertStringSecurityDescriptorToSecurityDescriptorW": (
            security,
            [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p],
            wintypes.BOOL,
        ),
        "GetSecurityInfo": (
            security,
            [
                wintypes.HANDLE,
                ctypes.c_int,
                wintypes.DWORD,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ],
            wintypes.DWORD,
        ),
        "GetAce": (security, [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)], wintypes.BOOL),
        "GetSecurityDescriptorControl": (
            security,
            [ctypes.c_void_p, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)],
            wintypes.BOOL,
        ),
    }
    api: dict[str, Any] = {}
    for name, (library, arguments, result) in definitions.items():
        function = getattr(library, name)
        function.argtypes, function.restype = arguments, result
        api[name] = function
    api["LocalFree"] = _dpapi()["local_free"]
    return api


def _recovery_sid_text(sid: int | None) -> str:
    api = _recovery_windows_api()
    text = wintypes.LPWSTR()
    if not sid or not api["ConvertSidToStringSidW"](sid, ctypes.byref(text)):
        raise RecoveryVerificationProblem("ownership-principal-unavailable")
    try:
        return str(text.value)
    finally:
        api["LocalFree"](text)


def _recovery_current_sid() -> str:
    api = _recovery_windows_api()
    token = wintypes.HANDLE()
    if not api["OpenProcessToken"](api["GetCurrentProcess"](), 0x0008, ctypes.byref(token)):
        raise RecoveryVerificationProblem("ownership-principal-unavailable")
    try:
        size = wintypes.DWORD()
        api["GetTokenInformation"](token, 1, None, 0, ctypes.byref(size))
        if not 8 <= size.value <= 65536:
            raise RecoveryVerificationProblem("ownership-principal-unavailable")
        buffer = ctypes.create_string_buffer(size.value)
        if not api["GetTokenInformation"](token, 1, buffer, size, ctypes.byref(size)):
            raise RecoveryVerificationProblem("ownership-principal-unavailable")
        return _recovery_sid_text(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])
    finally:
        api["CloseHandle"](token)


def _recovery_check_acl(handle: int, sid: str, *, exact: bool) -> None:
    """Use actual held owner/DACL; never trust mode bits or a declared principal."""

    api = _recovery_windows_api()
    owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    if (
        api["GetSecurityInfo"](
            handle, 1, 0x00000005, ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(descriptor)
        )
        != 0
    ):
        raise RecoveryVerificationProblem("ownership-security-unavailable")
    try:
        if _recovery_sid_text(owner.value) != sid or not dacl.value:
            raise RecoveryVerificationProblem("ownership-security-invalid")
        control, revision = wintypes.WORD(), wintypes.DWORD()
        if not api["GetSecurityDescriptorControl"](descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise RecoveryVerificationProblem("ownership-security-unavailable")
        count = ctypes.c_ushort.from_address(dacl.value + 4).value
        if not 1 <= count <= 64 or (exact and (count != 2 or not control.value & 0x1000)):
            raise RecoveryVerificationProblem("ownership-security-invalid")
        permitted: set[str] = set()
        for index in range(count):
            ace = ctypes.c_void_p()
            if not api["GetAce"](dacl, index, ctypes.byref(ace)) or not ace.value:
                raise RecoveryVerificationProblem("ownership-security-unavailable")
            ace_type, flags = ctypes.string_at(ace, 2)
            size = ctypes.c_ushort.from_address(ace.value + 2).value
            # Supported ACCESS_ALLOWED_ACE only. Unknown object/callback ACEs deny.
            if ace_type != 0 or size < 16 or (exact and flags):
                raise RecoveryVerificationProblem("ownership-security-invalid")
            if not exact and flags & 0x08:
                # INHERIT_ONLY_ACE does not grant rights on this parent object.
                # New private children use protected explicit DACLs instead.
                continue
            mask = ctypes.c_uint32.from_address(ace.value + 4).value
            trustee = _recovery_sid_text(ace.value + 8)
            if exact:
                if trustee not in (sid, "S-1-5-18") or mask != 0x001F01FF or trustee in permitted:
                    raise RecoveryVerificationProblem("ownership-security-invalid")
            elif trustee not in (sid, "S-1-5-18", "S-1-5-32-544") and mask & 0x500D0156:
                raise RecoveryVerificationProblem("ownership-parent-write-authority")
            permitted.add(trustee)
        if exact and permitted != {sid, "S-1-5-18"}:
            raise RecoveryVerificationProblem("ownership-security-invalid")
    finally:
        if descriptor.value:
            api["LocalFree"](descriptor)


@contextmanager
def _recovery_security_attributes(sid: str) -> Any:
    api = _recovery_windows_api()
    descriptor = ctypes.c_void_p()
    if not api["ConvertStringSecurityDescriptorToSecurityDescriptorW"](
        f"O:{sid}D:P(A;;FA;;;{sid})(A;;FA;;;SY)", 1, ctypes.byref(descriptor), None
    ):
        raise RecoveryVerificationProblem("ownership-security-unavailable")
    attributes = _RecoverySecurityAttributes(ctypes.sizeof(_RecoverySecurityAttributes), descriptor, False)
    try:
        yield ctypes.byref(attributes)
    finally:
        api["LocalFree"](descriptor)


class _RecoveryHeldFile:
    def __init__(self, path: Path, handle: int, sid: str, *, directory: bool = False, exact_acl: bool = True) -> None:
        self.path, self.handle, self.sid = path, handle, sid
        self.directory, self.exact_acl = directory, exact_acl
        self._lifetime = threading.RLock()
        self.parents: list[_RecoveryHeldFile] = []
        try:
            self.identity = self._information()
            self.validate()
        except BaseException:
            self.close()
            raise

    def _information(self) -> str:
        info = _RecoveryFileInformation()
        if not self.handle or not _recovery_windows_api()["GetFileInformationByHandle"](
            self.handle, ctypes.byref(info)
        ):
            raise RecoveryVerificationProblem("ownership-file-unavailable")
        if info.attributes & 0x400 or bool(info.attributes & 0x10) != self.directory:
            raise RecoveryVerificationProblem("ownership-file-unsafe")
        if not self.directory and (
            info.links != 1 or (info.size_high << 32 | info.size_low) > _RECOVERY_MAX_RECORD_BYTES
        ):
            raise RecoveryVerificationProblem("ownership-file-unsafe")
        return f"{info.volume:08x}:{info.index_high << 32 | info.index_low:016x}"

    def validate(self) -> None:
        with self._lifetime:
            self._validate()

    def _validate(self) -> None:
        for parent in self.parents:
            parent.validate()
        if self._information() != self.identity:
            raise RecoveryVerificationProblem("ownership-file-changed")
        # Path stat may fail while a renamed file is held exclusively. Bind the
        # current name and reparse attributes through an actual metadata handle.
        api = _recovery_windows_api()
        named = api["CreateFileW"](
            str(self.path), 0x80, 7, None, 3, 0x00200000 | (0x02000000 if self.directory else 0), None
        )
        if named in (None, ctypes.c_void_p(-1).value):
            raise RecoveryVerificationProblem("ownership-file-unavailable")
        try:
            info = _RecoveryFileInformation()
            if not api["GetFileInformationByHandle"](named, ctypes.byref(info)):
                raise RecoveryVerificationProblem("ownership-file-unavailable")
            identity = f"{info.volume:08x}:{info.index_high << 32 | info.index_low:016x}"
            if identity != self.identity or info.attributes & 0x400:
                raise RecoveryVerificationProblem("ownership-file-changed")
        finally:
            api["CloseHandle"](named)
        _recovery_check_acl(self.handle, self.sid, exact=self.exact_acl)

    def read(self) -> bytes:
        with self._lifetime:
            return self._read()

    def _read(self) -> bytes:
        self.validate()
        api = _recovery_windows_api()
        if not api["SetFilePointerEx"](self.handle, 0, None, 0):
            raise RecoveryVerificationProblem("ownership-file-unavailable")
        buffer = ctypes.create_string_buffer(_RECOVERY_MAX_RECORD_BYTES + 1)
        count = wintypes.DWORD()
        if not api["ReadFile"](self.handle, buffer, len(buffer), ctypes.byref(count), None):
            raise RecoveryVerificationProblem("ownership-file-unavailable")
        if count.value > _RECOVERY_MAX_RECORD_BYTES:
            raise RecoveryVerificationProblem("ownership-file-unsafe")
        self.validate()
        return buffer.raw[: count.value]

    def write_new(self, material: bytes) -> None:
        with self._lifetime:
            self._write_new(material)

    def _write_new(self, material: bytes) -> None:
        self.validate()
        if not 0 < len(material) <= _RECOVERY_MAX_RECORD_BYTES or self.read():
            raise RecoveryVerificationProblem("ownership-file-unsafe")
        api = _recovery_windows_api()
        buffer = ctypes.create_string_buffer(material)
        written = wintypes.DWORD()
        if not api["WriteFile"](
            self.handle, buffer, len(material), ctypes.byref(written), None
        ) or written.value != len(material):
            raise RecoveryVerificationProblem("ownership-publication-failed")
        if not api["FlushFileBuffers"](self.handle) or self.read() != material:
            raise RecoveryVerificationProblem("ownership-publication-failed")

    def close(self) -> None:
        with self._lifetime:
            self._close()

    def _close(self) -> None:
        if self.handle:
            handle, self.handle = self.handle, 0
            _recovery_windows_api()["CloseHandle"](handle)
        for parent in reversed(self.parents):
            parent.close()
        self.parents.clear()

    def publish(self, destination: Path) -> None:
        with self._lifetime:
            self._publish(destination)

    def _publish(self, destination: Path) -> None:
        """Atomic held-file rename to an absent name; never replace a record."""

        class Rename(ctypes.Structure):
            _fields_ = (
                ("flags", wintypes.DWORD),
                ("root", wintypes.HANDLE),
                ("length", wintypes.DWORD),
                ("name", wintypes.WCHAR * 1),
            )

        self.validate()
        name = str(destination).encode("utf-16-le")
        buffer = ctypes.create_string_buffer(
            max(ctypes.sizeof(Rename), Rename.name.offset + len(name) + ctypes.sizeof(wintypes.WCHAR))
        )
        record = Rename.from_buffer(buffer)
        record.flags, record.root, record.length = 0, None, len(name)
        ctypes.memmove(ctypes.addressof(buffer) + Rename.name.offset, name, len(name))
        if not _recovery_windows_api()["SetFileInformationByHandle"](self.handle, 22, buffer, len(buffer)):
            raise RecoveryVerificationProblem("ownership-publication-failed")
        self.path = destination
        self.validate()

    def __enter__(self) -> _RecoveryHeldFile:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _recovery_open(
    path: Path,
    sid: str,
    *,
    create: bool = False,
    exclusion: bool = False,
    directory: bool = False,
    exact_acl: bool = True,
) -> _RecoveryHeldFile:
    api = _recovery_windows_api()
    access = 0x80000000 | 0x00020000 | (0x40000000 if create or exclusion else 0) | (0x10000 if create else 0)
    flags = 0x00200000 | (0x02000000 if directory else 0)
    disposition = 4 if exclusion else (1 if create else 3)
    with _recovery_security_attributes(sid) as attributes:
        # Directory handles deny DELETE/rename but allow child publication's
        # internal write access to the parent. Immutable leaves still deny writers.
        share = 3 if directory else (0 if create or exclusion else 1)
        handle = api["CreateFileW"](str(path), access, share, attributes, disposition, flags, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise RecoveryVerificationProblem("ownership-file-unavailable")
    return _RecoveryHeldFile(path, handle, sid, directory=directory, exact_acl=exact_acl)


def _recovery_machine_protect(material: bytes) -> bytes:
    """Fixed outer scope; no request or record selects DPAPI protection flags."""

    api = _dpapi()
    buffer = (ctypes.c_ubyte * len(material)).from_buffer_copy(material)
    input_blob = _DataBlob(len(material), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = _DataBlob()
    if not api["protect"](ctypes.byref(input_blob), None, None, None, None, 0x00000005, ctypes.byref(output_blob)):
        raise RecoveryVerificationProblem("ownership-sealing-unavailable")
    try:
        if not output_blob.data or not 0 < output_blob.length <= _RECOVERY_MAX_RECORD_BYTES:
            raise RecoveryVerificationProblem("ownership-sealing-unavailable")
        return ctypes.string_at(output_blob.data, output_blob.length)
    finally:
        if output_blob.data:
            api["local_free"](output_blob.data)


def _recovery_json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate ownership record field")
        result[key] = value
    return result


def _recovery_exact(value: object, record: type) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(record)}:
        raise RecoveryVerificationProblem("ownership-record-invalid")
    return value


def _recovery_session_from_document(document: object) -> RecoveryNativeSession:
    session = dict(_recovery_exact(document, RecoveryNativeSession))
    for key in ("native", "core"):
        process = _recovery_exact(session[key], RecoveryProcessIdentity)
        if (
            type(process["process_id"]) is not int
            or not 1 <= process["process_id"] <= 0xFFFFFFFF
            or not isinstance(process["creation_filetime"], str)
            or re.fullmatch(r"[0-9a-f]{16}", process["creation_filetime"]) is None
            or not isinstance(process["executable_identity"], str)
            or _RECOVERY_HEX.fullmatch(process["executable_identity"]) is None
        ):
            raise RecoveryVerificationProblem("ownership-record-invalid")
        session[key] = RecoveryProcessIdentity(**process)
    if any(
        not isinstance(session[key], str) or _RECOVERY_HEX.fullmatch(session[key]) is None
        for key in ("principal_reference", "launch_session")
    ):
        raise RecoveryVerificationProblem("ownership-record-invalid")
    return RecoveryNativeSession(**session)


def _recovery_witness_from_document(document: object) -> RecoveryOwnershipWitness:
    data = dict(_recovery_exact(document, RecoveryOwnershipWitness))
    data["native_session"] = _recovery_session_from_document(data["native_session"])
    if (
        data["schema_version"] != "1.0"
        or data["purpose"] != "project-session-recovery"
        or data["disposition"] not in ("created", "opened", "closed")
        or any(
            not isinstance(data[key], str) or _RECOVERY_UUID.fullmatch(data[key]) is None
            for key in ("project_id", "core_instance_id")
        )
        or any(
            not isinstance(data[key], str) or _RECOVERY_HEX.fullmatch(data[key]) is None
            for key in ("witness_id", "recovery_token_sha256", "manifest_sha256", "audit_sha256")
        )
        or not isinstance(data["canonical_root"], str)
        or not Path(data["canonical_root"]).is_absolute()
        or len(data["canonical_root"]) > 4096
        or not isinstance(data["root_file_identity"], str)
        or re.fullmatch(r"[0-9a-f]{8}:[0-9a-f]{16}", data["root_file_identity"]) is None
        or type(data["audit_byte_count"]) is not int
        or not 0 <= data["audit_byte_count"] <= 8 * 1024 * 1024
        or not isinstance(data["initial_heartbeat"], str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z", data["initial_heartbeat"]) is None
    ):
        raise RecoveryVerificationProblem("ownership-record-invalid")
    return RecoveryOwnershipWitness(**data)


class WindowsProjectRecoveryWitnessStore:
    """Nonportable trusted issuance, dual DPAPI witness and stable exclusion.

    Receipt assurance comes from fixed creation calls and current-user protected
    immutable storage. CryptUnprotectData alone never proves an input's scope.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.sid = _recovery_current_sid()
        self._owned_projects: dict[str, _RecoveryHeldFile] = {}
        self._ownership_mutex = threading.RLock()
        if not self.root.is_absolute() or self.root.resolve(strict=False) != self.root:
            raise RecoveryVerificationProblem("ownership-storage-unsafe")
        with _recovery_open(self.root.parent, self.sid, directory=True, exact_acl=False):
            if not self.root.exists():
                with _recovery_security_attributes(self.sid) as attributes:
                    if not _recovery_windows_api()["CreateDirectoryW"](str(self.root), attributes):
                        raise RecoveryVerificationProblem("ownership-storage-unavailable")
            with _recovery_open(self.root, self.sid, directory=True):
                pass

    @property
    def principal_reference(self) -> str:
        return hashlib.sha256(self.sid.encode("utf-8")).hexdigest()

    def acquire_project(self, project_id: str) -> _RecoveryHeldFile:
        if _RECOVERY_UUID.fullmatch(project_id) is None:
            raise RecoveryVerificationProblem("ownership-project-invalid")
        parent = _recovery_open(self.root.parent, self.sid, directory=True, exact_acl=False)
        private_root: _RecoveryHeldFile | None = None
        held: _RecoveryHeldFile | None = None
        try:
            private_root = _recovery_open(self.root, self.sid, directory=True)
            # Stable persistent leaf: never delete, rename or replace this file.
            held = _recovery_open(self.root / f"{project_id}.exclusion", self.sid, exclusion=True)
            held.parents = [parent, private_root]
            if held.read():
                held.close()
                raise RecoveryVerificationProblem("ownership-exclusion-invalid")
            with self._ownership_mutex:
                self._owned_projects[project_id] = held
            return held
        except BaseException:
            if held is not None:
                held.close()
            if private_root is not None:
                private_root.close()
            parent.close()
            raise

    def _name(self, project_id: str, core_instance_id: str, disposition: str, token_sha256: str) -> str:
        if (
            any(_RECOVERY_UUID.fullmatch(value) is None for value in (project_id, core_instance_id))
            or disposition not in ("created", "opened", "closed")
            or _RECOVERY_HEX.fullmatch(token_sha256) is None
        ):
            raise RecoveryVerificationProblem("ownership-record-invalid")
        # Fixed-length, collision-resistant lookup keeps immutable acquisitions
        # distinct without exceeding Windows path limits inside a local profile.
        identity = json.dumps([project_id, core_instance_id, token_sha256], separators=(",", ":")).encode()
        return f"{hashlib.sha256(identity).hexdigest()}.{disposition}"

    def issue(self, witness: RecoveryOwnershipWitness) -> None:
        checked = _recovery_witness_from_document(asdict(witness))
        if (
            checked.native_session.principal_reference != self.principal_reference
            or checked.native_session.core.process_id != os.getpid()
        ):
            raise RecoveryVerificationProblem("ownership-principal-mismatch")
        with self._ownership_mutex:
            exclusion = self._owned_projects.get(checked.project_id)
            if exclusion is None:
                raise RecoveryVerificationProblem("ownership-exclusion-unavailable")
        # A concurrent caller cannot close/reacquire this exact exclusion during
        # sealing, publication or readback. No mutable on-disk lease is added.
        with exclusion._lifetime:
            exclusion.validate()
            self._issue_owned(checked)

    def check_nonterminal(self, project_id: str, core_instance_id: str, *, token_sha256: str) -> None:
        name = self._name(project_id, core_instance_id, "closed", token_sha256)
        api = _recovery_windows_api()
        with (
            _recovery_open(self.root.parent, self.sid, directory=True, exact_acl=False),
            _recovery_open(self.root, self.sid, directory=True),
        ):
            for suffix in (".sealed", ".issuance.json"):
                handle = api["CreateFileW"](str(self.root / (name + suffix)), 0x80, 7, None, 3, 0x00200000, None)
                if handle not in (None, ctypes.c_void_p(-1).value):
                    api["CloseHandle"](handle)
                    raise RecoveryVerificationProblem("ownership-terminal")
                if ctypes.get_last_error() != 2:  # Only actual FILE_NOT_FOUND means absent.
                    raise RecoveryVerificationProblem("ownership-terminal-unavailable")

    def _issue_owned(self, checked: RecoveryOwnershipWitness) -> None:
        name = self._name(
            checked.project_id, checked.core_instance_id, checked.disposition, checked.recovery_token_sha256
        )
        material = bytearray(json.dumps(asdict(checked), sort_keys=True, separators=(",", ":")).encode("utf-8"))
        inner = b""
        try:
            inner = WindowsCurrentUserDataProtector().protect(material)
            sealed = _recovery_machine_protect(inner)
        finally:
            _zero(material)
        with _recovery_open(self.root, self.sid, directory=True):
            stage_token = secrets.token_hex(16)
            with _recovery_open(self.root / (name + ".sealed.stage-" + stage_token), self.sid, create=True) as blob:
                blob.write_new(sealed)
                blob.publish(self.root / (name + ".sealed"))
                receipt = {
                    "schemaVersion": "1.0",
                    "purpose": "trusted-project-witness-issuance",
                    "principalReference": self.principal_reference,
                    "innerFlags": 1,
                    "outerFlags": 5,
                    "order": "user-then-machine",
                    "innerSHA256": hashlib.sha256(inner).hexdigest(),
                    "innerBytes": len(inner),
                    "sealedSHA256": hashlib.sha256(sealed).hexdigest(),
                    "sealedBytes": len(sealed),
                    "sealedFileIdentity": blob.identity,
                    "witnessSHA256": hashlib.sha256(
                        json.dumps(asdict(checked), sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest(),
                }
                encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
                with _recovery_open(
                    self.root / (name + ".issuance.stage-" + stage_token), self.sid, create=True
                ) as anchor:
                    anchor.write_new(encoded)
                    anchor.publish(self.root / (name + ".issuance.json"))
                blob.validate()
            if (
                self.read(
                    checked.project_id,
                    checked.core_instance_id,
                    checked.disposition,
                    token_sha256=checked.recovery_token_sha256,
                )
                != checked
            ):
                raise RecoveryVerificationProblem("ownership-publication-failed")

    def read(
        self,
        project_id: str,
        core_instance_id: str,
        disposition: str,
        *,
        token_sha256: str,
    ) -> RecoveryOwnershipWitness:
        name = self._name(project_id, core_instance_id, disposition, token_sha256)
        with (
            _recovery_open(self.root.parent, self.sid, directory=True, exact_acl=False),
            _recovery_open(self.root, self.sid, directory=True),
            _recovery_open(self.root / (name + ".sealed"), self.sid) as blob,
            _recovery_open(self.root / (name + ".issuance.json"), self.sid) as anchor,
        ):
            sealed, receipt_bytes = blob.read(), anchor.read()
            try:
                receipt = json.loads(receipt_bytes, object_pairs_hook=_recovery_json_pairs)
            except ValueError, UnicodeError, RecursionError:
                raise RecoveryVerificationProblem("ownership-issuance-invalid") from None
            expected_keys = {
                "schemaVersion",
                "purpose",
                "principalReference",
                "innerFlags",
                "outerFlags",
                "order",
                "innerSHA256",
                "innerBytes",
                "sealedSHA256",
                "sealedBytes",
                "sealedFileIdentity",
                "witnessSHA256",
            }
            if (
                not isinstance(receipt, dict)
                or set(receipt) != expected_keys
                or receipt["schemaVersion"] != "1.0"
                or receipt["purpose"] != "trusted-project-witness-issuance"
                or receipt["principalReference"] != self.principal_reference
                or type(receipt["innerFlags"]) is not int
                or receipt["innerFlags"] != 1
                or type(receipt["outerFlags"]) is not int
                or receipt["outerFlags"] != 5
                or receipt["order"] != "user-then-machine"
                or type(receipt["sealedBytes"]) is not int
                or type(receipt["innerBytes"]) is not int
                or not 1 <= receipt["innerBytes"] <= _RECOVERY_MAX_RECORD_BYTES
                or receipt["sealedFileIdentity"] != blob.identity
                or receipt["sealedBytes"] != len(sealed)
                or receipt["sealedSHA256"] != hashlib.sha256(sealed).hexdigest()
            ):
                raise RecoveryVerificationProblem("ownership-issuance-invalid")
            inner = bytearray()
            material = bytearray()
            try:
                inner = WindowsCurrentUserDataProtector().unprotect(sealed)
                if receipt["innerBytes"] != len(inner) or receipt["innerSHA256"] != hashlib.sha256(inner).hexdigest():
                    raise RecoveryVerificationProblem("ownership-issuance-invalid")
                material = WindowsCurrentUserDataProtector().unprotect(bytes(inner))
                if receipt["witnessSHA256"] != hashlib.sha256(material).hexdigest():
                    raise RecoveryVerificationProblem("ownership-issuance-invalid")
                checked = _recovery_witness_from_document(json.loads(material, object_pairs_hook=_recovery_json_pairs))
                if (
                    checked.project_id != project_id
                    or checked.core_instance_id != core_instance_id
                    or checked.disposition != disposition
                    or checked.recovery_token_sha256 != token_sha256
                    or checked.native_session.principal_reference != self.principal_reference
                ):
                    raise RecoveryVerificationProblem("ownership-record-mismatch")
                if blob.read() != sealed or anchor.read() != receipt_bytes:
                    raise RecoveryVerificationProblem("ownership-record-changed")
                return checked
            except SecretUnavailable, ValueError, UnicodeError, RecursionError:
                raise RecoveryVerificationProblem("ownership-record-unavailable") from None
            finally:
                _zero(inner)
                _zero(material)


def _recovery_current_process_identity() -> RecoveryProcessIdentity:
    api = _recovery_windows_api()
    times = [wintypes.FILETIME() for _ in range(4)]
    if not api["GetProcessTimes"](api["GetCurrentProcess"](), *(ctypes.byref(value) for value in times)):
        raise RecoveryVerificationProblem("ownership-process-unavailable")
    path = ctypes.create_unicode_buffer(4096)
    count = api["GetModuleFileNameW"](None, path, len(path))
    if not 1 <= count < len(path):
        raise RecoveryVerificationProblem("ownership-process-unavailable")
    handle = api["CreateFileW"](path.value, 0x80, 3, None, 3, 0x00200000, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise RecoveryVerificationProblem("ownership-process-unavailable")
    try:
        info = _RecoveryFileInformation()
        if (
            not api["GetFileInformationByHandle"](handle, ctypes.byref(info))
            or info.attributes & 0x410
            or info.links != 1
        ):
            raise RecoveryVerificationProblem("ownership-process-unavailable")
        identity = f"{info.volume:08x}:{info.index_high << 32 | info.index_low:016x}"
        return RecoveryProcessIdentity(
            os.getpid(),
            f"{times[0].dwHighDateTime << 32 | times[0].dwLowDateTime:016x}",
            hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        )
    finally:
        api["CloseHandle"](handle)


class WindowsRecoveryNativeAuthority:
    """Private inherited-pipe port; HTTP/renderer JSON cannot bind a session.

    One bounded writer and pending map keep pipe and OS-query waits outside the
    lifecycle mutex. Native attests its actual owned child and independently
    inspects old process identities and local source/destination authority.
    """

    PREFIX = b"ro-project-control-v1 "
    MAX_BYTES = 16 * 1024

    def __init__(self, output: BinaryIO) -> None:
        self._output = output
        self._mutex = threading.RLock()
        self._ready = threading.Event()
        self._session: RecoveryNativeSession | None = None
        self._closed = False
        self._pending: dict[str, tuple[threading.Event, list[object]]] = {}
        self._writes: queue.Queue[bytearray] = queue.Queue(maxsize=8)
        self._writer = threading.Thread(target=self._write_control, name="project-native-writer", daemon=True)
        self._writer.start()

    def _write_control(self) -> None:
        try:
            while True:
                with self._mutex:
                    if self._closed:
                        return
                try:
                    record = self._writes.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    with self._mutex:
                        if self._closed:
                            return
                    self._output.write(record)
                    self._output.flush()
                finally:
                    record[:] = b"\x00" * len(record)
        except OSError, ValueError:
            self.close()

    def _send(self, document: dict[str, object]) -> None:
        encoded = bytearray(self.PREFIX + json.dumps(document, separators=(",", ":")).encode("utf-8") + b"\n")
        if len(encoded) > self.MAX_BYTES:
            raise RecoveryVerificationProblem("native-proof-request-invalid")
        with self._mutex:
            try:
                if self._closed:
                    raise RecoveryVerificationProblem("native-proof-unavailable")
                self._writes.put_nowait(encoded)
            except queue.Full, RecoveryVerificationProblem:
                encoded[:] = b"\x00" * len(encoded)
                raise RecoveryVerificationProblem("native-proof-unavailable") from None

    def announce(self) -> None:
        self._send({"kind": "hello", "schema_version": "1.0"})

    def receive(self, payload: bytes) -> None:
        try:
            document = json.loads(payload, object_pairs_hook=_recovery_json_pairs)
            if not isinstance(document, dict) or document.get("schema_version") != "1.0":
                raise ValueError("invalid native control record")
            session: RecoveryNativeSession | None = None
            if document.get("kind") == "bind":
                if set(document) != {"kind", "schema_version", "session"}:
                    raise ValueError("invalid native binding")
                # OS identity queries do not hold the pending/close mutex.
                session = _recovery_session_from_document(document["session"])
                actual = _recovery_current_process_identity()
                if (
                    session.core != actual
                    or session.native.process_id == actual.process_id
                    or session.principal_reference != hashlib.sha256(_recovery_current_sid().encode()).hexdigest()
                ):
                    raise ValueError("native binding mismatch")
            with self._mutex:
                if self._closed:
                    return
                if document.get("kind") == "bind":
                    if session is None or self._session is not None:
                        raise ValueError("invalid native binding")
                    self._session = session
                    self._ready.set()
                elif document.get("kind") == "inspection":
                    if set(document) != {"kind", "schema_version", "request_id", "inspection"}:
                        raise ValueError("invalid native response")
                    request_id = document["request_id"]
                    if not isinstance(request_id, str) or re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
                        raise ValueError("invalid native response")
                    pending = self._pending.get(request_id)
                    if pending is not None:
                        pending[1].append(document["inspection"])
                        pending[0].set()
                else:
                    raise ValueError("invalid native response")
        except ValueError, UnicodeError, RecursionError, RecoveryVerificationProblem:
            self.close()

    def current_session(self) -> RecoveryNativeSession:
        self._ready.wait(timeout=1.0)
        with self._mutex:
            if self._closed or self._session is None:
                raise RecoveryVerificationProblem("native-proof-unavailable")
            return self._session

    def inspect(self, witness: RecoveryOwnershipWitness, source: Path, destination: Path) -> RecoveryNativeInspection:
        session = self.current_session()
        request_id = secrets.token_hex(16)
        pending: tuple[threading.Event, list[object]] = (threading.Event(), [])
        with self._mutex:
            if self._closed or len(self._pending) >= 4:
                raise RecoveryVerificationProblem("native-proof-unavailable")
            self._pending[request_id] = pending
        try:
            self._send(
                {
                    "kind": "inspect",
                    "schema_version": "1.0",
                    "request_id": request_id,
                    "witness": asdict(witness),
                    "source": str(source),
                    "destination": str(destination),
                }
            )
            if not pending[0].wait(timeout=2.5) or len(pending[1]) != 1:
                raise RecoveryVerificationProblem("native-proof-unavailable")
            data = _recovery_exact(pending[1][0], RecoveryNativeInspection)
            with self._mutex:
                if self._closed or self._session != session:
                    raise RecoveryVerificationProblem("native-proof-unavailable")
            if (
                data["launch_session"] != session.launch_session
                or data["principal_reference"] != session.principal_reference
                or any(
                    data[key] not in ("dead", "live", "pid-reused", "unknown")
                    for key in ("native_owner_state", "core_owner_state")
                )
                or any(
                    not isinstance(data[key], str) or re.fullmatch(r"[0-9a-f]{8}:[0-9a-f]{16}", data[key]) is None
                    for key in ("source_file_identity", "destination_parent_identity")
                )
            ):
                raise RecoveryVerificationProblem("native-proof-invalid")
            return RecoveryNativeInspection(**data)
        finally:
            with self._mutex:
                self._pending.pop(request_id, None)

    def close(self) -> None:
        with self._mutex:
            self._closed = True
            self._session = None
            self._ready.set()
            for event, _values in self._pending.values():
                event.set()
            while True:
                try:
                    record = self._writes.get_nowait()
                except queue.Empty:
                    break
                record[:] = b"\x00" * len(record)


class _DataBlob(ctypes.Structure):
    _fields_ = (("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte)))


class _Guid(ctypes.Structure):
    _fields_ = (
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", ctypes.c_ubyte * 8),
    )


class _DataProtector(Protocol):
    def protect(self, material: bytearray) -> bytes: ...

    def unprotect(self, protected: bytes) -> bytearray: ...


@cache
def _dpapi() -> dict[str, Any]:
    if os.name != "nt":
        raise SecretUnavailable("Windows credential protection is unavailable")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    protect = crypt32.CryptProtectData
    protect.argtypes = (
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    )
    protect.restype = wintypes.BOOL
    unprotect = crypt32.CryptUnprotectData
    unprotect.argtypes = (
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    )
    unprotect.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = (ctypes.c_void_p,)
    local_free.restype = ctypes.c_void_p
    return {"protect": protect, "unprotect": unprotect, "local_free": local_free}


class WindowsCurrentUserDataProtector:
    """Non-interactive, current-user DPAPI binding; machine scope is never used."""

    def protect(self, material: bytearray) -> bytes:
        if not isinstance(material, bytearray) or not material:
            raise ValueError("DPAPI plaintext is invalid")
        api = _dpapi()
        input_buffer = (ctypes.c_ubyte * len(material)).from_buffer(material)
        input_blob = _DataBlob(len(material), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output_blob = _DataBlob()
        if not api["protect"](
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        ):
            raise SecretUnavailable("Windows credential protection is unavailable") from None
        try:
            if not output_blob.data or output_blob.length <= 0:
                raise SecretUnavailable("Windows credential protection is unavailable")
            return ctypes.string_at(output_blob.data, output_blob.length)
        finally:
            if output_blob.data:
                api["local_free"](output_blob.data)

    def unprotect(self, protected: bytes) -> bytearray:
        if not isinstance(protected, bytes) or not protected:
            raise SecretUnavailable("Windows credential protection is unavailable")
        api = _dpapi()
        input_buffer = (ctypes.c_ubyte * len(protected)).from_buffer_copy(protected)
        input_blob = _DataBlob(len(protected), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output_blob = _DataBlob()
        if not api["unprotect"](
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        ):
            raise SecretUnavailable("Windows credential protection is unavailable") from None
        try:
            if not output_blob.data or output_blob.length <= 0:
                raise SecretUnavailable("Windows credential protection is unavailable")
            return bytearray(ctypes.string_at(output_blob.data, output_blob.length))
        finally:
            if output_blob.data:
                ctypes.memset(output_blob.data, 0, output_blob.length)
                api["local_free"](output_blob.data)


def _guid(value: uuid.UUID) -> _Guid:
    raw = value.bytes_le
    data1, data2, data3 = struct.unpack("<IHH", raw[:8])
    return _Guid(data1, data2, data3, (ctypes.c_ubyte * 8).from_buffer_copy(raw[8:]))


def default_windows_profile_vault_path() -> Path:
    """Resolve LocalAppData through the Windows known-folder authority."""

    if os.name != "nt":
        raise SecretUnavailable("Windows credential protection is unavailable")
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    known_folder = shell32.SHGetKnownFolderPath
    known_folder.argtypes = (
        ctypes.POINTER(_Guid),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.LPWSTR),
    )
    known_folder.restype = ctypes.c_long
    free = ole32.CoTaskMemFree
    free.argtypes = (ctypes.c_void_p,)
    free.restype = None
    value = wintypes.LPWSTR()
    status = known_folder(ctypes.byref(_guid(_LOCAL_APP_DATA)), 0, None, ctypes.byref(value))
    if status != 0 or not value.value:
        raise SecretUnavailable("Windows profile storage is unavailable")
    try:
        return Path(value.value) / "Research Observatory" / "security" / "profile-default"
    finally:
        free(value)


def _zero(material: bytearray) -> None:
    material[:] = b"\0" * len(material)


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("credential record write failed")
        view = view[written:]


def _sync_directory(path: Path) -> None:
    with suppress(OSError):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _redirected(path: Path) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return True
    return stat.S_ISLNK(status.st_mode) or bool(getattr(status, "st_file_attributes", 0) & 0x400)


def _canonical_reference(reference: SecretReference) -> bytes:
    if not isinstance(reference, SecretReference):
        raise ValueError("secret reference is invalid")
    return json.dumps(
        {
            "kind": reference.kind.value,
            "name": reference.name,
            "profileId": reference.profile_id,
            "subjectId": reference.subject_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reference_token(root_key: bytearray, reference_bytes: bytes) -> str:
    return hmac.digest(root_key, b"audit\0" + reference_bytes, "sha256")[:16].hex()


def _record_name(root_key: bytearray, reference_bytes: bytes) -> str:
    return hmac.digest(root_key, b"record\0" + reference_bytes, "sha256").hex() + _RECORD_SUFFIX


def _record_aad(reference_bytes: bytes) -> bytes:
    return _RECORD_MAGIC + hashlib.sha256(reference_bytes).digest()


def _default_audit(event: SecretAuditEvent) -> None:
    emit_log_record(
        "security.credential-access",
        level="INFO",
        fields={
            "auditContext": event.audit_context,
            "callingCapability": event.calling_capability,
            "operation": event.operation,
            "outcome": event.outcome,
            "purpose": event.purpose.value,
            "reasonCode": event.reason_code,
            "referenceToken": event.reference_token,
        },
    )


_LOCK_REGISTRY_GUARD = threading.RLock()
_LOCK_REGISTRY: dict[str, threading.RLock] = {}


def _vault_lock(root: Path) -> threading.RLock:
    key = os.path.normcase(str(root))
    with _LOCK_REGISTRY_GUARD:
        return _LOCK_REGISTRY.setdefault(key, threading.RLock())


@contextmanager
def _cross_process_lock(root: Path) -> Any:
    """Serialize root creation and record CAS across supervised Core processes."""

    path = root / _LOCK_FILE
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
    descriptor = -1
    locked = False
    try:
        descriptor = os.open(path, flags, 0o600)
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1 or _redirected(path):
            raise SecretAccessDenied("credential vault lock authority is invalid")
        if status.st_size == 0:
            _write_all(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            locked = True
        yield
    except SecretAccessDenied, SecretUnavailable:
        raise
    except OSError:
        raise SecretUnavailable("credential vault lock is unavailable") from None
    finally:
        if descriptor >= 0:
            if locked:
                import msvcrt

                with suppress(OSError):
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            os.close(descriptor)


class WindowsCredentialStore(CredentialStore):
    """Opaque authenticated records under one current-user-protected profile root."""

    def __init__(
        self,
        root: Path,
        *,
        audit_sink: SecretAuditSink | None = None,
        protector: _DataProtector | None = None,
    ) -> None:
        candidate = Path(root)
        if not candidate.is_absolute():
            raise ValueError("credential vault root must be absolute")
        self._root = candidate
        self._audit = audit_sink if audit_sink is not None else _default_audit
        if not callable(self._audit):
            raise ValueError("credential audit sink is invalid")
        self._protector = protector if protector is not None else WindowsCurrentUserDataProtector()
        if not callable(getattr(self._protector, "protect", None)) or not callable(
            getattr(self._protector, "unprotect", None)
        ):
            raise ValueError("credential data protector is invalid")
        self._lock = _vault_lock(candidate)

    def _ensure_root(self) -> tuple[Path, Path]:
        try:
            self._root.mkdir(parents=True, mode=0o700, exist_ok=True)
            absolute = Path(os.path.abspath(self._root))
            resolved = self._root.resolve(strict=True)
        except FileExistsError, NotADirectoryError, RuntimeError:
            raise SecretAccessDenied("credential vault authority is invalid") from None
        except OSError:
            raise SecretUnavailable("credential vault authority is unavailable") from None
        if os.path.normcase(str(absolute)) != os.path.normcase(str(resolved)) or _redirected(self._root):
            raise SecretAccessDenied("credential vault authority is invalid")
        try:
            status = self._root.stat()
        except OSError:
            raise SecretUnavailable("credential vault authority is unavailable") from None
        if not stat.S_ISDIR(status.st_mode):
            raise SecretAccessDenied("credential vault authority is invalid")
        records = self._root / _RECORDS_DIRECTORY
        try:
            records.mkdir(mode=0o700, exist_ok=True)
            records_status = records.stat()
        except FileExistsError, NotADirectoryError:
            raise SecretAccessDenied("credential record authority is invalid") from None
        except OSError:
            raise SecretUnavailable("credential record authority is unavailable") from None
        if _redirected(records) or not stat.S_ISDIR(records_status.st_mode):
            raise SecretAccessDenied("credential vault authority is invalid")
        return self._root / _ROOT_FILE, records

    @staticmethod
    def _read_private(path: Path, *, maximum: int, missing: type[SecretUnavailable]) -> bytes:
        try:
            status = path.lstat()
            if (
                _redirected(path)
                or not stat.S_ISREG(status.st_mode)
                or status.st_nlink != 1
                or not 0 < status.st_size <= maximum
            ):
                raise SecretCorrupt("protected credential record is invalid")
            payload = path.read_bytes()
            after = path.lstat()
            if (status.st_dev, status.st_ino, status.st_size) != (after.st_dev, after.st_ino, after.st_size):
                raise SecretCorrupt("protected credential record changed")
            return payload
        except FileNotFoundError:
            raise missing("protected credential record is unavailable") from None
        except SecretCorrupt:
            raise
        except OSError:
            raise SecretUnavailable("protected credential record is unavailable") from None

    @staticmethod
    def _atomic_write(path: Path, payload: bytes, *, replace: bool) -> None:
        staging = path.parent / f".{secrets.token_hex(16)}.partial"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = -1
        try:
            descriptor = os.open(staging, flags, 0o600)
            _write_all(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            if replace:
                os.replace(staging, path)
            else:
                try:
                    os.link(staging, path)
                except FileExistsError:
                    raise SecretConflict("secret record already exists") from None
                staging.unlink()
            _sync_directory(path.parent)
        except SecretConflict:
            raise
        except OSError:
            raise SecretUnavailable("protected credential record could not be stored") from None
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            with suppress(OSError):
                staging.unlink()

    def _root_key(self) -> bytearray:
        root_file, records = self._ensure_root()
        if not root_file.exists():
            # Called under the vault lock. A lost root cannot make existing
            # encrypted records appear to be absent under a newly generated key.
            try:
                if next(records.iterdir(), None) is not None:
                    raise SecretUnavailable("Windows credential protection is unavailable")
            except OSError:
                raise SecretUnavailable("Windows credential protection is unavailable") from None
            key = bytearray(secrets.token_bytes(_ROOT_KEY_BYTES))
            plaintext = bytearray(_ROOT_MAGIC + key + hashlib.sha256(_ROOT_MAGIC + key).digest())
            try:
                protected = self._protector.protect(plaintext)
                with suppress(SecretConflict):
                    self._atomic_write(root_file, protected, replace=False)
            finally:
                _zero(plaintext)
                _zero(key)
        protected = self._read_private(root_file, maximum=64 * 1024, missing=SecretUnavailable)
        plaintext = self._protector.unprotect(protected)
        try:
            if len(plaintext) != _ROOT_PLAINTEXT_BYTES or not plaintext.startswith(_ROOT_MAGIC):
                raise SecretUnavailable("Windows credential protection is unavailable")
            key = bytearray(plaintext[len(_ROOT_MAGIC) : len(_ROOT_MAGIC) + _ROOT_KEY_BYTES])
            expected = hashlib.sha256(_ROOT_MAGIC + key).digest()
            observed = bytes(plaintext[-hashlib.sha256().digest_size :])
            if not hmac.compare_digest(observed, expected):
                _zero(key)
                raise SecretUnavailable("Windows credential protection is unavailable")
            return key
        finally:
            _zero(plaintext)

    def _emit(self, operation: str, reference_bytes: bytes, root_key: bytearray, context: SecretAccessContext) -> None:
        if not isinstance(context, SecretAccessContext):
            raise ValueError("secret access context is invalid")
        event = SecretAuditEvent(
            operation=operation,  # type: ignore[arg-type]
            outcome="authorized",
            reason_code=f"secret-{operation}-authorized",
            reference_token=_reference_token(root_key, reference_bytes),
            audit_context=context.audit_context,
            calling_capability=context.calling_capability,
            purpose=context.purpose,
        )
        try:
            self._audit(event)
        except Exception:
            raise SecretAccessDenied("credential audit authority is unavailable") from None

    @staticmethod
    def _encode_record(
        reference: SecretReference,
        reference_bytes: bytes,
        material: bytes | bytearray,
        root_key: bytearray,
        version: str,
    ) -> bytes:
        metadata = json.dumps(
            {
                "kind": reference.kind.value,
                "name": reference.name,
                "profileId": reference.profile_id,
                "schemaVersion": "1.0",
                "subjectId": reference.subject_id,
                "version": version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        plaintext = bytearray(_RECORD_METADATA_LENGTH.pack(len(metadata)) + metadata + material)
        nonce = secrets.token_bytes(sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES)
        try:
            ciphertext = sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
                bytes(plaintext),
                _record_aad(reference_bytes),
                nonce,
                bytes(root_key),
            )
            return _RECORD_MAGIC + nonce + ciphertext
        finally:
            _zero(plaintext)

    @staticmethod
    def _decode_record(
        payload: bytes,
        reference: SecretReference,
        reference_bytes: bytes,
        root_key: bytearray,
    ) -> tuple[SecretRecord, bytearray]:
        nonce_bytes = sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES
        if len(payload) <= len(_RECORD_MAGIC) + nonce_bytes or not payload.startswith(_RECORD_MAGIC):
            raise SecretCorrupt("protected credential record is invalid")
        nonce = payload[len(_RECORD_MAGIC) : len(_RECORD_MAGIC) + nonce_bytes]
        ciphertext = payload[len(_RECORD_MAGIC) + nonce_bytes :]
        try:
            plaintext = bytearray(
                sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
                    ciphertext,
                    _record_aad(reference_bytes),
                    nonce,
                    bytes(root_key),
                )
            )
        except CryptoError:
            raise SecretCorrupt("protected credential record authentication failed") from None
        try:
            if len(plaintext) <= _RECORD_METADATA_LENGTH.size:
                raise SecretCorrupt("protected credential record is invalid")
            metadata_length = _RECORD_METADATA_LENGTH.unpack(plaintext[: _RECORD_METADATA_LENGTH.size])[0]
            metadata_end = _RECORD_METADATA_LENGTH.size + metadata_length
            if not _RECORD_METADATA_LENGTH.size < metadata_end < len(plaintext):
                raise SecretCorrupt("protected credential record is invalid")
            try:
                metadata = json.loads(bytes(plaintext[_RECORD_METADATA_LENGTH.size : metadata_end]))
            except UnicodeError, json.JSONDecodeError:
                raise SecretCorrupt("protected credential record is invalid") from None
            expected = {
                "kind": reference.kind.value,
                "name": reference.name,
                "profileId": reference.profile_id,
                "schemaVersion": "1.0",
                "subjectId": reference.subject_id,
            }
            if not isinstance(metadata, dict) or set(metadata) != {*expected, "version"}:
                raise SecretCorrupt("protected credential record is invalid")
            if any(metadata.get(field) != value for field, value in expected.items()):
                raise SecretCorrupt("protected credential record scope differs")
            version = metadata.get("version")
            if not isinstance(version, str) or _VERSION.fullmatch(version) is None:
                raise SecretCorrupt("protected credential record is invalid")
            material = bytearray(plaintext[metadata_end:])
            if not material or len(material) > _MAX_SECRET_BYTES:
                _zero(material)
                raise SecretCorrupt("protected credential record is invalid")
            return SecretRecord(version, reference.kind), material
        finally:
            _zero(plaintext)

    def put(
        self,
        reference: SecretReference,
        material: bytes | bytearray,
        context: SecretAccessContext,
        *,
        expected_version: str | None = None,
    ) -> SecretRecord:
        if not isinstance(material, (bytes, bytearray)) or not material or len(material) > _MAX_SECRET_BYTES:
            raise ValueError("secret material is invalid")
        if expected_version is not None and (
            not isinstance(expected_version, str) or _VERSION.fullmatch(expected_version) is None
        ):
            raise ValueError("expected secret version is invalid")
        reference_bytes = _canonical_reference(reference)
        with self._lock:
            self._ensure_root()
            with _cross_process_lock(self._root):
                root_key = self._root_key()
                try:
                    self._emit("put", reference_bytes, root_key, context)
                    _root_file, records = self._ensure_root()
                    path = records / _record_name(root_key, reference_bytes)
                    exists = path.exists()
                    if exists:
                        if expected_version is None:
                            raise SecretConflict("secret record already exists")
                        payload = self._read_private(path, maximum=_MAX_RECORD_BYTES, missing=SecretNotFound)
                        current, current_material = self._decode_record(payload, reference, reference_bytes, root_key)
                        _zero(current_material)
                        if current.version != expected_version:
                            raise SecretConflict("secret record version differs")
                    elif expected_version is not None:
                        raise SecretConflict("secret record version differs")
                    version = secrets.token_hex(16)
                    payload = self._encode_record(reference, reference_bytes, material, root_key, version)
                    self._atomic_write(path, payload, replace=exists)
                    return SecretRecord(version, reference.kind)
                finally:
                    _zero(root_key)

    def lease_record(
        self,
        reference: SecretReference,
        context: SecretAccessContext,
    ) -> tuple[SecretRecord, SecretLease]:
        reference_bytes = _canonical_reference(reference)
        with self._lock:
            self._ensure_root()
            with _cross_process_lock(self._root):
                root_key = self._root_key()
                try:
                    self._emit("lease", reference_bytes, root_key, context)
                    _root_file, records = self._ensure_root()
                    path = records / _record_name(root_key, reference_bytes)
                    payload = self._read_private(path, maximum=_MAX_RECORD_BYTES, missing=SecretNotFound)
                    record, material = self._decode_record(payload, reference, reference_bytes, root_key)
                    return record, SecretLease(material)
                finally:
                    _zero(root_key)

    def lease(self, reference: SecretReference, context: SecretAccessContext) -> SecretLease:
        _record, lease = self.lease_record(reference, context)
        return lease


class WindowsLocalActorIdentityProvider:
    """Resolve one opaque, stable human actor authority for the current OS profile."""

    def __init__(self, root: Path, *, protector: _DataProtector | None = None) -> None:
        candidate = Path(root)
        if not candidate.is_absolute():
            raise ValueError("local actor vault root must be absolute")
        self._root = candidate
        self._protector = protector if protector is not None else WindowsCurrentUserDataProtector()
        if not callable(getattr(self._protector, "protect", None)) or not callable(
            getattr(self._protector, "unprotect", None)
        ):
            raise ValueError("local actor data protector is invalid")
        self._lock = _vault_lock(candidate)

    def actor_id(self) -> str:
        store = WindowsCredentialStore(self._root, protector=self._protector)
        with self._lock:
            store._ensure_root()
            with _cross_process_lock(self._root):
                path = self._root / _LOCAL_ACTOR_FILE
                if not path.exists():
                    actor_id = new_uuid_v7()
                    actor_bytes = actor_id.encode("ascii")
                    plaintext = bytearray(
                        _LOCAL_ACTOR_MAGIC + actor_bytes + hashlib.sha256(_LOCAL_ACTOR_MAGIC + actor_bytes).digest()
                    )
                    try:
                        protected = self._protector.protect(plaintext)
                        with suppress(SecretConflict):
                            store._atomic_write(path, protected, replace=False)
                    finally:
                        _zero(plaintext)
                protected = store._read_private(path, maximum=64 * 1024, missing=SecretUnavailable)
                plaintext = self._protector.unprotect(protected)
                try:
                    if len(plaintext) != _LOCAL_ACTOR_BYTES or not plaintext.startswith(_LOCAL_ACTOR_MAGIC):
                        raise SecretCorrupt("protected local actor identity is invalid")
                    actor_bytes = bytes(plaintext[len(_LOCAL_ACTOR_MAGIC) : len(_LOCAL_ACTOR_MAGIC) + 36])
                    expected = hashlib.sha256(_LOCAL_ACTOR_MAGIC + actor_bytes).digest()
                    observed = bytes(plaintext[-hashlib.sha256().digest_size :])
                    if not hmac.compare_digest(observed, expected):
                        raise SecretCorrupt("protected local actor identity authentication failed")
                    try:
                        actor_id = actor_bytes.decode("ascii")
                    except UnicodeError:
                        raise SecretCorrupt("protected local actor identity is invalid") from None
                    if not is_uuid_v7(actor_id):
                        raise SecretCorrupt("protected local actor identity is invalid")
                    return actor_id
                finally:
                    _zero(plaintext)


class WindowsDatabaseKeyProvider(DatabaseKeyProvider):
    """Store active and staged per-project SQLCipher keys below the DPAPI vault root."""

    _ACTIVE_NAME = "database-active-v1"

    def __init__(self, store: CredentialStore, *, profile_id: str) -> None:
        if not isinstance(store, CredentialStore):
            raise ValueError("credential store is invalid")
        self._store = store
        self._profile_id = profile_id

    @staticmethod
    def _context() -> SecretAccessContext:
        return SecretAccessContext(
            calling_capability="CAP-02.S04",
            purpose=SecretPurpose.DATABASE_ENCRYPTION,
            audit_context=secrets.token_hex(16),
        )

    def _reference(self, project_id: str, name: str) -> SecretReference:
        return SecretReference(
            profile_id=self._profile_id,
            kind=SecretKind.ENCRYPTION_KEY_MATERIAL,
            subject_id=project_id,
            name=name,
        )

    def _lease(self, reference: SecretReference, *, create: bool) -> DatabaseKeyLease:
        try:
            record, secret = self._store.lease_record(reference, self._context())
        except SecretNotFound:
            if not create:
                raise DatabaseKeyUnavailable("project database key is unavailable") from None
            material = bytearray(secrets.token_bytes(_ROOT_KEY_BYTES))
            try:
                with suppress(SecretConflict):
                    self._store.put(reference, material, self._context())
            finally:
                _zero(material)
            try:
                record, secret = self._store.lease_record(reference, self._context())
            except SecretNotFound:
                raise DatabaseKeyUnavailable("project database key is unavailable") from None
        except CredentialStoreProblem:
            raise DatabaseKeyUnavailable("project database key is unavailable") from None
        return DatabaseKeyLease(record.version, secret)

    def active_key(self, project_id: str, *, create: bool) -> DatabaseKeyLease:
        validate_database_key_identity(project_id)
        return self._lease(self._reference(project_id, self._ACTIVE_NAME), create=create)

    def staged_rekey(self, project_id: str, operation_id: str, *, create: bool) -> DatabaseKeyLease:
        validate_database_key_identity(project_id, operation_id)
        return self._lease(self._reference(project_id, f"database-rekey-{operation_id}"), create=create)

    def activate_rekey(
        self,
        project_id: str,
        operation_id: str,
        *,
        expected_active_version: str,
    ) -> str:
        validate_database_key_identity(project_id, operation_id)
        pending = self._reference(project_id, f"database-rekey-{operation_id}")
        active = self._reference(project_id, self._ACTIVE_NAME)
        try:
            with self._store.lease(pending, self._context()) as lease:
                material = lease.use(bytearray)
            try:
                record = self._store.put(
                    active,
                    material,
                    self._context(),
                    expected_version=expected_active_version,
                )
            finally:
                _zero(material)
        except SecretConflict:
            raise DatabaseKeyConflict("database key activation conflicted") from None
        except CredentialStoreProblem:
            raise DatabaseKeyUnavailable("staged database key is unavailable") from None
        return record.version


class WindowsObjectMasterKeyProvider(ObjectMasterKeyProvider):
    """Bind the S03 object-key port to one profile-vault secret namespace."""

    def __init__(self, store: CredentialStore, *, profile_id: str) -> None:
        if not isinstance(store, CredentialStore):
            raise ValueError("credential store is invalid")
        self._store = store
        self._reference = SecretReference(
            profile_id=profile_id,
            kind=SecretKind.ENCRYPTION_KEY_MATERIAL,
            subject_id="object-store",
            name=_OBJECT_KEY_VERSION,
        )

    @staticmethod
    def _context() -> SecretAccessContext:
        return SecretAccessContext(
            calling_capability="CAP-02.S03",
            purpose=SecretPurpose.OBJECT_ENCRYPTION,
            audit_context=secrets.token_hex(16),
        )

    def _read(self) -> ObjectMasterKey:
        with self._store.lease(self._reference, self._context()) as lease:
            key_bytes = lease.use(bytes)
        if len(key_bytes) != _ROOT_KEY_BYTES:
            raise SecretCorrupt("object encryption key material is invalid")
        return ObjectMasterKey(_OBJECT_KEY_VERSION, key_bytes)

    def active_object_master_key(self) -> ObjectMasterKey:
        try:
            return self._read()
        except SecretNotFound:
            key = bytearray(secrets.token_bytes(_ROOT_KEY_BYTES))
            try:
                with suppress(SecretConflict):
                    self._store.put(self._reference, key, self._context())
            finally:
                _zero(key)
            return self._read()

    def object_master_key(self, key_version: str) -> ObjectMasterKey | None:
        if key_version != _OBJECT_KEY_VERSION:
            return None
        return self._read()


def create_windows_object_key_provider(root: Path | None = None) -> ObjectMasterKeyProvider:
    vault_root = default_windows_profile_vault_path() if root is None else Path(root)
    return WindowsObjectMasterKeyProvider(
        WindowsCredentialStore(vault_root),
        profile_id="local-default",
    )


def create_windows_database_key_provider(root: Path | None = None) -> DatabaseKeyProvider:
    vault_root = default_windows_profile_vault_path() if root is None else Path(root)
    return WindowsDatabaseKeyProvider(
        WindowsCredentialStore(vault_root),
        profile_id="local-default",
    )


def create_windows_local_actor_identity(root: Path | None = None) -> str:
    vault_root = default_windows_profile_vault_path() if root is None else Path(root)
    return WindowsLocalActorIdentityProvider(vault_root).actor_id()


__all__ = [
    "WindowsCredentialStore",
    "WindowsCurrentUserDataProtector",
    "WindowsDatabaseKeyProvider",
    "WindowsLocalActorIdentityProvider",
    "WindowsObjectMasterKeyProvider",
    "create_windows_database_key_provider",
    "create_windows_local_actor_identity",
    "create_windows_object_key_provider",
    "default_windows_profile_vault_path",
]
