"""Local project package lifecycle authority.

The project package is authoritative. This module owns the versioned manifest,
classified directories, lock, and audit seam and delegates canonical database
creation and validation to the storage adapter. Domain repositories remain
outside this lifecycle boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, BinaryIO, TypeVar, cast

from .logging import emit_log_record
from .models import (
    ProjectAccessMode,
    ProjectCompatibilityState,
    ProjectLifecycleState,
    ProjectProjection,
    ProjectRecoveryAction,
    ProjectRecoveryProjection,
)
from .ports.object_store import ObjectKeyUnavailable, ObjectStoreProblem
from .ports.project_recovery import (
    RecoveryCopyVerifiedFacts,
    RecoveryExclusion,
    RecoveryNativeAuthority,
    RecoveryNativeSession,
    RecoveryOwnershipWitness,
    RecoveryVerificationProblem,
    RecoveryWitnessStore,
)
from .project_action_mutex import FairProjectActionMutex
from .storage import StorageProblem, initialize_database, validate_canonical_database
from .workflow_profile_contracts import approved_workflow_profile_catalog

_DIRECTORY_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_TEMPLATE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
_PROJECT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$")
_RELEASE_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_MANIFEST_KEYS = {
    "schemaVersion",
    "documentType",
    "projectId",
    "projectRevision",
    "packageFormatVersion",
    "layoutVersion",
    "lifecycleState",
    "applicationCompatibility",
    "databaseProfile",
    "objectFormat",
    "createdAt",
    "modifiedAt",
}
_PROFILE_KEYS = {"schemaVersion", "documentType", "displayName", "templateId"}
_PROJECT_DIRECTORIES = ("state", "objects", "indexes", "cache", "models", "config", "exports", "logs", ".locks", ".tmp")
_WORKFLOW_PROFILES = cast(Sequence[Mapping[str, object]], approved_workflow_profile_catalog()["profiles"])
_IMPLEMENTED_TEMPLATES = frozenset(cast(str, profile["profileId"]) for profile in _WORKFLOW_PROFILES)
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_MAX_AUDIT_BYTES = 8 * 1024 * 1024
_MAX_PROJECT_DOCUMENT_BYTES = 256 * 1024
_CURRENT_PACKAGE_FORMAT = (1, 0, 0)
_CURRENT_APPLICATION_VERSION = (0, 1, 0)
_PROJECT_ACTION_RESULT = TypeVar("_PROJECT_ACTION_RESULT")
_RECOVERY_CHUNK_BYTES = 1024 * 1024
_RECOVERY_FILE_LIMIT = 65536
_RECOVERY_INCOMPLETE_MARKER = ".ro-recovery-incomplete"
_RECOVERY_PORTABLE_ROOTS = frozenset(("state", "objects", "config", "exports", "logs", ".locks"))
_LOCK_KEYS = frozenset(
    ("schemaVersion", "documentType", "projectId", "instanceId", "processId", "heartbeatAt", "recoveryToken")
)


@dataclass(slots=True)
class _OwnedProjectSession:
    exclusion: RecoveryExclusion
    record: dict[str, Any]
    witness: RecoveryOwnershipWitness | None = None
    ready: bool = False
    stop: threading.Event = field(default_factory=threading.Event)
    heartbeat: threading.Thread | None = None
    lock_identity: tuple[int, int] | None = None


@dataclass(slots=True)
class _RecoveryPreview:
    preview_id: str
    root: Path
    destination: Path
    state: str = "unavailable-proof"
    reason_codes: tuple[str, ...] = ()
    witness: RecoveryOwnershipWitness | None = None
    source_signature: str | None = None
    source_display_label: str = "Selected project"
    verified_fact_summary: str | None = None
    target_identity: tuple[int, int] | None = None
    published: bool = False
    cancel: threading.Event = field(default_factory=threading.Event)
    publication_mutex: threading.RLock = field(default_factory=threading.RLock)
    worker: threading.Thread | None = None
    validating: bool = True


@dataclass(slots=True)
class _RecoveryInventory:
    root: Path
    directories: tuple[Path, ...]
    files: dict[Path, tuple[BinaryIO, tuple[int, int, int, int], str]]
    signature: str
    writable_files: frozenset[Path] = frozenset()
    require_empty_derived: bool = False
    incomplete_marker: bool = False
    publication_finalized: bool = False

    def recheck(self, cancel: Callable[[], bool]) -> None:
        # Only the portable roots have files. All created cache/derived roots
        # and the staging root's membership must remain exact and empty.
        if self.require_empty_derived:
            expected_root_entries = {"project.ro.json", *_PROJECT_DIRECTORIES}
            if self.incomplete_marker:
                expected_root_entries.add(_RECOVERY_INCOMPLETE_MARKER)
            if set(path.name for path in self.root.iterdir()) != expected_root_entries:
                raise RecoveryVerificationProblem("source-inventory-changed")
            for name in set(_PROJECT_DIRECTORIES) - _RECOVERY_PORTABLE_ROOTS:
                directory = self.root / name
                if _stable_directory_identity(directory) is None or any(directory.iterdir()):
                    raise RecoveryVerificationProblem("source-inventory-changed")
        directories, paths = _recovery_paths(self.root, cancel, incomplete_marker=self.incomplete_marker)
        immutable_paths = tuple(path for path in paths if path not in self.writable_files)
        if (directories, immutable_paths) != (self.directories, tuple(sorted(self.files))):
            raise RecoveryVerificationProblem("source-inventory-changed")
        for path, (stream, expected, digest) in self.files.items():
            _recovery_check_cancel(cancel)
            status = path.stat(follow_symlinks=False)
            if (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns) != expected:
                raise RecoveryVerificationProblem("source-inventory-changed")
            stream.seek(0)
            if _recovery_stream_hash(stream, cancel) != digest:
                raise RecoveryVerificationProblem("source-inventory-changed")
            stream.seek(0)

    def binding(self) -> tuple:
        return (
            tuple((path.relative_to(self.root).as_posix(), _path_identity(path)) for path in self.directories),
            tuple(
                (path.relative_to(self.root).as_posix(), value[1], value[2])
                for path, value in sorted(self.files.items())
            ),
        )


def _recovery_stream_hash(stream: BinaryIO, cancel: Callable[[], bool]) -> str:
    digest = hashlib.sha256()
    while True:
        _recovery_check_cancel(cancel)
        material = stream.read(_RECOVERY_CHUNK_BYTES)
        if not material:
            break
        digest.update(material)
    return digest.hexdigest()


def _recovery_paths(
    root: Path, cancel: Callable[[], bool], *, incomplete_marker: bool = False
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    directories, files = [], [root / "project.ro.json"]
    if incomplete_marker:
        files.append(root / _RECOVERY_INCOMPLETE_MARKER)
    pending = [root / name for name in sorted(_RECOVERY_PORTABLE_ROOTS)]
    while pending:
        _recovery_check_cancel(cancel)
        directory = pending.pop()
        if _stable_directory_identity(directory) is None:
            raise RecoveryVerificationProblem("source-directory-unsafe")
        directories.append(directory)
        for entry in sorted(directory.iterdir(), key=lambda path: str(path).casefold()):
            _recovery_check_cancel(cancel)
            status = entry.stat(follow_symlinks=False)
            if _redirect(entry):
                raise RecoveryVerificationProblem("source-file-unsafe")
            if stat.S_ISDIR(status.st_mode):
                pending.append(entry)
            elif stat.S_ISREG(status.st_mode) and status.st_nlink == 1:
                files.append(entry)
            else:
                raise RecoveryVerificationProblem("source-file-unsafe")
            if len(files) + len(directories) + len(pending) > _RECOVERY_FILE_LIMIT:
                raise RecoveryVerificationProblem("source-inventory-limit")
    return tuple(sorted(directories)), tuple(sorted(files))


@contextmanager
def _recovery_inventory(
    root: Path,
    cancel: Callable[[], bool],
    *,
    existing_root_hold: bool = False,
    require_empty_derived: bool = False,
    writable_files: frozenset[Path] = frozenset(),
    incomplete_marker: bool = False,
) -> Iterator[_RecoveryInventory]:
    directories, paths = _recovery_paths(root, cancel, incomplete_marker=incomplete_marker)
    with ExitStack() as stack:
        # The publication owner already retains a DELETE-capable root handle.
        # Every child directory and file still receives strict guards.
        files: dict[Path, tuple[BinaryIO, tuple[int, int, int, int], str]] = {}
        inventory = _RecoveryInventory(
            root, directories, files, "", writable_files, require_empty_derived, incomplete_marker
        )
        if existing_root_hold:
            # Publication explicitly validates the complete held inventory.
            # After removing its completion marker, release handles only;
            # a late content-check failure must not reopen an incomplete copy.
            stack.enter_context(_windows_directory_locks(list(directories)))
        else:
            stack.enter_context(_stable_directories([root, *directories]))
        fingerprint = hashlib.sha256()
        for directory in (root, *directories):
            _recovery_check_cancel(cancel)
            status = directory.stat(follow_symlinks=False)
            fingerprint.update(
                json.dumps(
                    [directory.relative_to(root).as_posix(), "directory", status.st_dev, status.st_ino],
                    separators=(",", ":"),
                ).encode()
            )
        for path in paths:
            if path in writable_files:
                continue
            _recovery_check_cancel(cancel)
            removable_marker = existing_root_hold and path == root / _RECOVERY_INCOMPLETE_MARKER
            stream = stack.enter_context(
                _recovery_held_file(
                    path,
                    stable_name=not removable_marker,
                    allow_owned_rename=removable_marker,
                    validate_after=lambda: not inventory.publication_finalized,
                )
            )
            status = os.fstat(stream.fileno())
            identity = (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns)
            digest = _recovery_stream_hash(stream, cancel)
            stream.seek(0)
            files[path] = (stream, identity, digest)
            fingerprint.update(
                json.dumps(
                    [path.relative_to(root).as_posix(), "file", *identity, digest], separators=(",", ":")
                ).encode()
            )
        inventory.signature = fingerprint.hexdigest()
        if _recovery_paths(root, cancel, incomplete_marker=incomplete_marker) != (directories, paths):
            raise RecoveryVerificationProblem("source-inventory-changed")
        yield inventory
        # Staging's caller explicitly checks while later operational holds
        # are live. Published/source inventories recheck on context exit.
        if not inventory.publication_finalized and (not require_empty_derived or existing_root_hold):
            inventory.recheck(cancel)


def _recovery_check_cancel(cancel: Callable[[], bool]) -> None:
    try:
        if cancel() is False:
            return
    except Exception:
        pass
    raise RecoveryVerificationProblem("cancelled")


@contextmanager
def _recovery_held_file(
    path: Path,
    *,
    stable_name: bool = True,
    delete_access: bool = False,
    allow_owned_rename: bool = False,
    validate_after: Callable[[], bool] | None = None,
) -> Iterator[BinaryIO]:
    """Pin a regular single-link source against writers/delete on Windows."""

    if os.name == "nt":
        import msvcrt

        create_file, close_handle, invalid = _windows_directory_lock_api()
        handle = create_file(
            str(path),
            0x80000000 | (0x10000 if delete_access else 0),
            1 | (4 if allow_owned_rename else 0),
            None,
            3,
            0x00200000,
            None,
        )
        if handle in (None, invalid):
            raise RecoveryVerificationProblem("source-read-unavailable")
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            close_handle(handle)
            raise
        stream = os.fdopen(descriptor, "rb")
    else:
        stream = path.open("rb")
    try:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or getattr(before, "st_file_attributes", 0) & 0x400
            or _redirect(path)
            or (before.st_dev, before.st_ino) != _path_identity(path)
        ):
            raise RecoveryVerificationProblem("source-file-unsafe")
        yield stream
        if validate_after is None or validate_after():
            after = os.fstat(stream.fileno())
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) or (stable_name and _path_identity(path) != (before.st_dev, before.st_ino)):
                raise RecoveryVerificationProblem("source-file-changed")
    finally:
        stream.close()


def _recovery_read(path: Path, limit: int) -> bytes:
    with _recovery_held_file(path) as stream:
        material = stream.read(limit + 1)
        if len(material) > limit:
            raise RecoveryVerificationProblem("source-file-oversize")
        return material


def _recovery_lock(path: Path) -> tuple[dict[str, Any], bytes]:
    material = _recovery_read(path, 4096)
    return _recovery_parse_lock(material), material


def _recovery_parse_lock(material: bytes) -> dict[str, Any]:
    try:

        def unique(pairs):
            data = {}
            for key, value in pairs:
                if key in data:
                    raise ValueError("duplicate lock field")
                data[key] = value
            return data

        data = json.loads(material, object_pairs_hook=unique)
        if (
            not isinstance(data, dict)
            or set(data) != _LOCK_KEYS
            or data["schemaVersion"] != "1.0"
            or data["documentType"] != "research-observatory-project-lock"
            or any(
                not isinstance(data[key], str) or _PROJECT_ID.fullmatch(data[key]) is None
                for key in ("projectId", "instanceId")
            )
            or type(data["processId"]) is not int
            or not 1 <= data["processId"] <= 0xFFFFFFFF
            or not isinstance(data["heartbeatAt"], str)
            or not isinstance(data["recoveryToken"], str)
            or re.fullmatch(r"[0-9a-f]{64}", data["recoveryToken"]) is None
        ):
            raise ValueError("invalid lock")
        if _utc_datetime(data["heartbeatAt"]) is None:
            raise ValueError("invalid heartbeat")
        return data
    except ValueError, UnicodeError, RecursionError:
        raise RecoveryVerificationProblem("source-lock-invalid") from None


def _recovery_file_identity(path: Path) -> str:
    if os.name != "nt":
        raise RecoveryVerificationProblem("ownership-platform-unavailable")
    import ctypes
    from ctypes import wintypes

    class Information(ctypes.Structure):
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

    create, close, invalid = _windows_directory_lock_api()
    handle = create(str(path), 0x80, 3, None, 3, 0x00200000 | 0x02000000, None)
    if handle in (None, invalid):
        raise RecoveryVerificationProblem("source-identity-unavailable")
    try:
        function = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandle
        function.argtypes, function.restype = (wintypes.HANDLE, ctypes.c_void_p), wintypes.BOOL
        info = Information()
        if not function(handle, ctypes.byref(info)) or info.attributes & 0x400:
            raise RecoveryVerificationProblem("source-identity-unavailable")
        return f"{info.volume:08x}:{info.index_high << 32 | info.index_low:016x}"
    finally:
        close(handle)


def _refresh_owned_heartbeat(path: Path, owner: _OwnedProjectSession) -> None:
    """Publish exactly seven lock fields through the owned Windows handle."""

    if os.name != "nt":
        raise RecoveryVerificationProblem("ownership-platform-unavailable")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    lock = path / ".locks/session.lock"
    owner.exclusion.validate()
    # Only the owner metadata refresh allows rename sharing. The stable private
    # exclusion remains held, writers are denied, and the exact acquisition FID
    # is checked before publishing through the owned staging handle. Original
    # recovery-copy inputs and close deletion retain their stricter sharing.
    with _recovery_held_file(lock, stable_name=False, allow_owned_rename=True) as old:
        material = old.read(4097)
        actual, exact = _recovery_lock(lock)
        if (
            material != exact
            or (os.fstat(old.fileno()).st_dev, os.fstat(old.fileno()).st_ino) != owner.lock_identity
            or any(actual[key] != owner.record[key] for key in _LOCK_KEYS - {"heartbeatAt"})
            or _utc_datetime(owner.record["heartbeatAt"]) is None
            or actual["heartbeatAt"] < owner.record["heartbeatAt"]
        ):
            raise RecoveryVerificationProblem("owned-lock-changed")
        record = {**actual, "heartbeatAt": _timestamp()}
        if _utc_datetime(record["heartbeatAt"]) is None or record["heartbeatAt"] < actual["heartbeatAt"]:
            raise RecoveryVerificationProblem("owned-clock-regressed")
        encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        stage = lock.parent / (".session-heartbeat-" + secrets.token_hex(16))
        create, close, invalid = _windows_directory_lock_api()
        handle = create(str(stage), 0xC0010000, 1, None, 1, 0x00200000, None)
        if handle in (None, invalid):
            raise RecoveryVerificationProblem("heartbeat-write-unavailable")
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except BaseException:
            close(handle)
            raise
        with os.fdopen(descriptor, "w+b") as stream:
            stage_identity = _path_identity(stage)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            if stream.read(4097) != encoded or owner.stop.is_set():
                raise RecoveryVerificationProblem("heartbeat-publication-unavailable")

            class Rename(ctypes.Structure):
                _fields_ = (
                    ("flags", wintypes.DWORD),
                    ("root", wintypes.HANDLE),
                    ("length", wintypes.DWORD),
                    ("name", wintypes.WCHAR * 1),
                )

            name = str(lock).encode("utf-16-le")
            buffer = ctypes.create_string_buffer(
                max(ctypes.sizeof(Rename), Rename.name.offset + len(name) + ctypes.sizeof(wintypes.WCHAR))
            )
            info = Rename.from_buffer(buffer)
            info.flags, info.root, info.length = 3, None, len(name)
            ctypes.memmove(ctypes.addressof(buffer) + Rename.name.offset, name, len(name))
            function = ctypes.WinDLL("kernel32", use_last_error=True).SetFileInformationByHandle
            function.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
            function.restype = wintypes.BOOL
            # Recheck the current name immediately before owned POSIX replacement.
            # Cooperating writers also hold the same stable project exclusion.
            if _path_identity(lock) != (os.fstat(old.fileno()).st_dev, os.fstat(old.fileno()).st_ino):
                raise RecoveryVerificationProblem("owned-lock-changed")
            if not function(handle, 22, buffer, len(buffer)):
                raise RecoveryVerificationProblem("heartbeat-publication-unavailable")
            if _path_identity(lock) != stage_identity:
                raise RecoveryVerificationProblem("heartbeat-publication-unavailable")
            stream.seek(0)
            if stream.read(4097) != encoded:
                raise RecoveryVerificationProblem("heartbeat-publication-unavailable")
            owner.record = record
            owner.lock_identity = stage_identity


def _path_identity(path: Path) -> tuple[int, int]:
    status = path.stat(follow_symlinks=False)
    return (status.st_dev, status.st_ino)


def _stable_directory_identity(path: Path) -> tuple[int, int] | None:
    """Return one non-following directory identity snapshot, rejecting redirects."""

    status = path.stat(follow_symlinks=False)
    reparse_point = bool(getattr(status, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    if not stat.S_ISDIR(status.st_mode) or reparse_point:
        return None
    return (status.st_dev, status.st_ino)


def _inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(root)))) == os.path.normcase(
            str(root)
        )
    except ValueError:
        return False


def _installation_roots() -> tuple[Path, ...]:
    roots = {
        Path(value)
        for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "SystemRoot")
        if (value := os.environ.get(name))
    }
    if getattr(sys, "frozen", False):
        roots.add(Path(sys.executable).parent)
    return tuple(roots)


@cache
def _windows_directory_lock_api() -> tuple[Any, Any, int]:
    """Bind the immutable Windows directory-lock API once per Core process."""

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    invalid_handle = wintypes.HANDLE(-1).value
    if invalid_handle is None:
        raise RuntimeError("Windows returned an invalid null handle sentinel")
    return create_file, close_handle, invalid_handle


@contextmanager
def _windows_directory_locks(paths: list[Path]) -> Iterator[None]:
    """Deny directory rename/delete for the duration of a path-based operation."""

    if os.name != "nt":
        yield
        return
    import ctypes

    create_file, close_handle, invalid_handle = _windows_directory_lock_api()
    file_read_attributes = 0x00000080
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_backup_semantics = 0x02000000
    handles: list[int] = []
    try:
        for path in sorted(set(paths), key=lambda item: str(item).casefold()):
            handle = create_file(
                str(path),
                file_read_attributes,
                file_share_read | file_share_write,
                None,
                open_existing,
                file_flag_open_reparse_point | file_flag_backup_semantics,
                None,
            )
            if handle == invalid_handle:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
        yield
    finally:
        for handle in reversed(handles):
            close_handle(handle)


@contextmanager
def _held_directory_renamer(source: Path) -> Iterator[Callable[[Path], None]]:
    """Hold a Windows directory against replacement and rename through that handle."""

    identity = _path_identity(source)
    if os.name != "nt":

        def rename_portable(destination: Path) -> None:
            if _path_identity(source) != identity:
                raise ProjectLifecycleProblem.invalid_path()
            os.rename(source, destination)

        yield rename_portable
        return
    import ctypes
    from ctypes import wintypes

    class FileRenameInfo(ctypes.Structure):
        _fields_ = (
            ("ReplaceIfExists", wintypes.BOOLEAN),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", wintypes.WCHAR * 1),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    set_file_information = kernel32.SetFileInformationByHandle
    set_file_information.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    set_file_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    delete_access = 0x00010000
    file_read_attributes = 0x00000080
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    file_rename_info = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_backup_semantics = 0x02000000
    invalid_handle = wintypes.HANDLE(-1).value
    handle = create_file(
        str(source),
        delete_access | file_read_attributes,
        file_share_read | file_share_write,
        None,
        open_existing,
        file_flag_open_reparse_point | file_flag_backup_semantics,
        None,
    )
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if _redirect(source) or _path_identity(source) != identity:
        close_handle(handle)
        raise ProjectLifecycleProblem.invalid_path()

    def rename(destination: Path) -> None:
        encoded = str(destination).encode("utf-16-le")
        size = FileRenameInfo.FileName.offset + len(encoded) + ctypes.sizeof(wintypes.WCHAR)
        buffer = ctypes.create_string_buffer(size)
        info = ctypes.cast(buffer, ctypes.POINTER(FileRenameInfo)).contents
        info.ReplaceIfExists = False
        info.RootDirectory = None
        info.FileNameLength = len(encoded)
        ctypes.memmove(ctypes.addressof(buffer) + FileRenameInfo.FileName.offset, encoded, len(encoded))
        if not set_file_information(handle, file_rename_info, buffer, size):
            raise ctypes.WinError(ctypes.get_last_error())

    try:
        yield rename
    finally:
        close_handle(handle)


@contextmanager
def _stable_directories(paths: list[Path]) -> Iterator[None]:
    try:
        identities = {path: _stable_directory_identity(path) for path in paths}
        if any(identity is None for identity in identities.values()):
            raise ProjectLifecycleProblem.invalid_path()
        with _windows_directory_locks(paths):
            if any(_stable_directory_identity(path) != identity for path, identity in identities.items()):
                raise ProjectLifecycleProblem.invalid_path()
            try:
                yield
            finally:
                if any(_stable_directory_identity(path) != identity for path, identity in identities.items()):
                    raise ProjectLifecycleProblem.invalid_path()
    except ProjectLifecycleProblem:
        raise
    except OSError as error:
        raise ProjectLifecycleProblem.invalid_path() from error


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _redirect(path: Path) -> bool:
    try:
        return path.is_symlink() or path.is_junction()
    except OSError as error:
        raise ProjectLifecycleProblem(
            status=422,
            code="RO-CORE-PROJECT-PATH-INVALID",
            title="Project path cannot be inspected",
            detail="The selected local path could not be verified without following a redirect.",
            remediation="Choose a present local directory that is not a symbolic link or junction.",
        ) from error


def _canonical_directory(value: str) -> Path:
    windows_value = value.replace("/", "\\").casefold()
    if (
        not value
        or len(value) > 4096
        or "\x00" in value
        or windows_value.startswith(("\\\\?\\", "\\\\.\\", "\\??\\", "\\device\\"))
    ):
        raise ProjectLifecycleProblem.invalid_path()
    path = Path(value)
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise ProjectLifecycleProblem.invalid_path()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if _redirect(current):
            raise ProjectLifecycleProblem.invalid_path()
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ProjectLifecycleProblem(
            status=404,
            code="RO-CORE-PROJECT-NOT-FOUND",
            title="Project location was not found",
            detail="The selected local project directory is unavailable.",
            remediation="Locate the project directory or choose another local location.",
        ) from error
    if (
        resolved != path
        or not path.is_dir()
        or _redirect(path)
        or (os.name == "nt" and any(_inside(resolved, root) for root in _installation_roots()))
    ):
        raise ProjectLifecycleProblem.invalid_path()
    return path


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise ProjectLifecycleProblem(
            status=500,
            code="RO-CORE-PROJECT-WRITE-FAILED",
            title="Project update could not be published",
            detail="The local project remained unchanged or recoverable after a filesystem write failed.",
            remediation="Check local storage availability and retry once.",
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _read_project_document(path: Path) -> Any:
    descriptor: int | None = None
    try:
        before = path.stat(follow_symlinks=False)
        if (
            _redirect(path)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > _MAX_PROJECT_DOCUMENT_BYTES
        ):
            raise OSError("project document is redirected, linked, non-regular, or oversized")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise OSError("project document changed before open")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = None
            payload = stream.read(_MAX_PROJECT_DOCUMENT_BYTES + 1)
            after_read = os.fstat(stream.fileno())
        after_path = path.stat(follow_symlinks=False)
        if (
            len(payload) > _MAX_PROJECT_DOCUMENT_BYTES
            or (after_read.st_dev, after_read.st_ino) != (before.st_dev, before.st_ino)
            or (after_path.st_dev, after_path.st_ino) != (before.st_dev, before.st_ino)
            or after_path.st_nlink != 1
        ):
            raise OSError("project document changed during snapshot")
        return json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectLifecycleProblem(
            status=422,
            code="RO-CORE-PROJECT-DAMAGED",
            title="Project metadata is damaged",
            detail="The project manifest or profile is unavailable, unsafe, oversized, or malformed.",
            remediation=(
                "Keep the original unchanged. First make and verify a complete backup; repair only a working copy."
            ),
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _atomic_audit_append(path: Path, record: dict[str, Any]) -> bytes:
    existing = b""
    if path.exists() or _redirect(path):
        try:
            status = path.stat(follow_symlinks=False)
            identity = (status.st_dev, status.st_ino)
            if _redirect(path) or not path.is_file() or status.st_nlink != 1 or status.st_size > _MAX_AUDIT_BYTES:
                raise OSError("audit target is redirected, linked, non-regular, or oversized")
            existing = path.read_bytes()
            after = path.stat(follow_symlinks=False)
            if (after.st_dev, after.st_ino) != identity or after.st_nlink != 1:
                raise OSError("audit target changed during snapshot")
            existing.decode("utf-8")
            if existing and not existing.endswith(b"\n"):
                raise OSError("audit target is not a complete JSON-lines document")
        except (OSError, UnicodeError) as error:
            raise ProjectLifecycleProblem(
                status=500,
                code="RO-CORE-PROJECT-AUDIT-FAILED",
                title="Project audit record could not be written",
                detail="The lifecycle action did not complete without its required local audit record.",
                remediation="Check local storage availability and retry.",
            ) from error
    line = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(existing) + len(line) > _MAX_AUDIT_BYTES:
        raise ProjectLifecycleProblem(
            status=500,
            code="RO-CORE-PROJECT-AUDIT-FAILED",
            title="Project audit record could not be written",
            detail="The bounded lifecycle audit reached its current local size limit.",
            remediation="Preserve the project and request a reviewed audit rollover before retrying.",
        )
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(existing + line)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise ProjectLifecycleProblem(
            status=500,
            code="RO-CORE-PROJECT-AUDIT-FAILED",
            title="Project audit record could not be written",
            detail="The lifecycle action did not complete without its required local audit record.",
            remediation="Check local storage availability and retry.",
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
    return line


def _release_version(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str) or not (match := _RELEASE_VERSION.fullmatch(value)):
        return None
    version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return version if all(part <= _MAX_SAFE_INTEGER for part in version) else None


def _utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(slots=True)
class ProjectLifecycleProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    remediation: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code

    @classmethod
    def invalid_path(cls) -> ProjectLifecycleProblem:
        return cls(
            status=422,
            code="RO-CORE-PROJECT-PATH-INVALID",
            title="Project path is not allowed",
            detail="Project locations must be absolute, canonical local directories without redirects or traversal.",
            remediation="Choose a direct local directory outside symbolic links and junctions.",
        )

    @classmethod
    def rollback_failed(cls) -> ProjectLifecycleProblem:
        return cls(
            status=500,
            code="RO-CORE-PROJECT-ROLLBACK-FAILED",
            title="Project operation requires recovery",
            detail="A failed lifecycle operation could not restore its exact prior local state.",
            remediation="Keep the application open and use the reviewed project recovery workflow.",
        )


@dataclass(frozen=True, slots=True)
class _ProjectActionScope:
    """Nested metadata assessment usable only inside its owning project action."""

    _run: Callable[[str, bool, Callable[[Path, str], Any]], Any]

    def perform(
        self, *, root: str, require_write: bool, action: Callable[[Path, str], _PROJECT_ACTION_RESULT]
    ) -> _PROJECT_ACTION_RESULT:
        return cast(_PROJECT_ACTION_RESULT, self._run(root, require_write, action))


class ProjectLifecycleService:
    """Serialize package lifecycle operations for one supervised Core process."""

    def __init__(
        self,
        *,
        object_upgrade: Callable[[Path, str], object] | None = None,
        recovery_witness_store: RecoveryWitnessStore | None = None,
        recovery_native_authority: RecoveryNativeAuthority | None = None,
        require_recovery_exclusion: bool = False,
    ) -> None:
        if object_upgrade is not None and not callable(object_upgrade):
            raise TypeError("object upgrade must be a callable composition boundary")
        self._instance_id = str(uuid.uuid4())
        self._opened: dict[Path, ProjectAccessMode] = {}
        self._owned_locks: dict[Path, tuple[dict[str, Any], tuple[int, int]]] = {}
        self._mutex = FairProjectActionMutex()
        self._object_upgrade = object_upgrade
        self._recovery_store = recovery_witness_store
        self._recovery_native = recovery_native_authority
        self._require_recovery_exclusion = require_recovery_exclusion
        self._owned_sessions: dict[Path, _OwnedProjectSession] = {}
        self._recovery_mutex = threading.RLock()
        self._recovery_previews: dict[str, _RecoveryPreview] = {}
        self._recovery_verifier: (
            Callable[[Path, str, _ProjectActionScope, Callable[[], bool]], RecoveryCopyVerifiedFacts] | None
        ) = None
        self._recovery_key_access: Callable[[str], None] | None = None
        self._shutting_down = False

    def configure_recovery_verifier(
        self,
        verifier: Callable[[Path, str, _ProjectActionScope, Callable[[], bool]], RecoveryCopyVerifiedFacts],
        *,
        key_access: Callable[[str], None],
    ) -> None:
        if not callable(verifier) or not callable(key_access) or self._recovery_verifier is not None:
            raise ValueError("recovery verification composition is invalid")
        self._recovery_verifier = verifier
        self._recovery_key_access = key_access

    @staticmethod
    def _recovery_problem() -> ProjectLifecycleProblem:
        return ProjectLifecycleProblem(
            status=409,
            code="RO-CORE-PROJECT-RECOVERY-UNAVAILABLE",
            title="Project ownership is unavailable",
            detail="The current local project ownership could not be established safely.",
            remediation="Keep the original unchanged and retry after restoring the local ownership prerequisite.",
            retryable=True,
        )

    def _session_witness(
        self,
        path: Path,
        record: dict[str, Any],
        session: RecoveryNativeSession,
        disposition: str,
    ) -> RecoveryOwnershipWitness:
        audit = _recovery_read(path / "logs/project-lifecycle.jsonl", _MAX_AUDIT_BYTES)
        return RecoveryOwnershipWitness(
            "1.0",
            "project-session-recovery",
            secrets.token_hex(32),
            record["projectId"],
            str(path),
            _recovery_file_identity(path),
            self._instance_id,
            hashlib.sha256(record["recoveryToken"].encode()).hexdigest(),
            record["heartbeatAt"],
            hashlib.sha256(_recovery_read(path / "project.ro.json", _MAX_PROJECT_DOCUMENT_BYTES)).hexdigest(),
            session,
            cast(Any, disposition),
            len(audit),
            hashlib.sha256(audit).hexdigest(),
        )

    def _start_heartbeat(self, path: Path, owner: _OwnedProjectSession) -> None:
        def refresh() -> None:
            while not owner.stop.wait(timeout=10):
                try:
                    with self._mutex:
                        if (
                            self._shutting_down
                            or self._owned_sessions.get(path) is not owner
                            or self._opened.get(path) is not ProjectAccessMode.READ_WRITE
                            or owner.stop.is_set()
                        ):
                            return
                        with _stable_directories(self._project_guard_paths(path)):
                            _refresh_owned_heartbeat(path, owner)
                            self._owned_locks[path] = (dict(owner.record), _path_identity(path / ".locks/session.lock"))
                except OSError, ValueError, RecoveryVerificationProblem, ProjectLifecycleProblem:
                    owner.stop.set()
                    emit_log_record(
                        "project.heartbeat-unavailable",
                        level="WARNING",
                        fields={"reasonCode": "owned-heartbeat-unavailable"},
                    )
                    return

        owner.heartbeat = threading.Thread(target=refresh, name="project-owned-heartbeat", daemon=True)
        owner.heartbeat.start()

    @staticmethod
    def _recovery_destination(root: Path, value: str) -> Path:
        destination = Path(value)
        parent = _canonical_directory(str(destination.parent))
        if (
            not destination.is_absolute()
            or destination != parent / destination.name
            or _DIRECTORY_NAME.fullmatch(destination.name) is None
            or destination.exists()
            or _redirect(destination)
            or _inside(parent, root)
            or _inside(root, destination)
            or os.name != "nt"
            or not re.match(r"^[A-Za-z]:[\\/]", str(destination))
        ):
            raise RecoveryVerificationProblem("destination-unavailable")
        return destination

    def _fresh_recovery_proof(self, root: Path, destination: Path) -> RecoveryOwnershipWitness:
        if (
            self._shutting_down
            or self._recovery_store is None
            or self._recovery_native is None
            or self._recovery_verifier is None
            or self._recovery_key_access is None
        ):
            raise RecoveryVerificationProblem("ownership-proof-unavailable")
        self._recovery_destination(root, str(destination))
        self._validate_layout(root)
        manifest, _profile, compatibility = self._assess_documents(root)
        if compatibility is not ProjectCompatibilityState.COMPATIBLE or manifest["lifecycleState"] != "active":
            raise RecoveryVerificationProblem("source-incompatible")
        record, _material = _recovery_lock(root / ".locks/session.lock")
        identity = str(manifest["projectId"])
        if record["projectId"] != identity:
            raise RecoveryVerificationProblem("ownership-record-mismatch")
        token_sha256 = hashlib.sha256(record["recoveryToken"].encode()).hexdigest()
        created = self._recovery_store.read(identity, record["instanceId"], "created", token_sha256=token_sha256)
        witness = self._recovery_store.read(identity, record["instanceId"], "opened", token_sha256=token_sha256)
        self._recovery_store.check_nonterminal(identity, record["instanceId"], token_sha256=token_sha256)
        heartbeat = _utc_datetime(record["heartbeatAt"])
        initial_heartbeat = _utc_datetime(witness.initial_heartbeat)
        if heartbeat is None or initial_heartbeat is None:
            raise RecoveryVerificationProblem("ownership-record-mismatch")
        common = (
            "project_id",
            "canonical_root",
            "root_file_identity",
            "core_instance_id",
            "recovery_token_sha256",
            "initial_heartbeat",
            "manifest_sha256",
            "native_session",
        )
        if (
            any(getattr(created, name) != getattr(witness, name) for name in common)
            or witness.project_id != identity
            or witness.canonical_root != str(root)
            or witness.root_file_identity != _recovery_file_identity(root)
            or witness.native_session.core.process_id != record["processId"]
            or hashlib.sha256(record["recoveryToken"].encode()).hexdigest() != witness.recovery_token_sha256
            or heartbeat < initial_heartbeat
            or hashlib.sha256(_recovery_read(root / "project.ro.json", _MAX_PROJECT_DOCUMENT_BYTES)).hexdigest()
            != witness.manifest_sha256
        ):
            raise RecoveryVerificationProblem("ownership-record-mismatch")
        audit = _recovery_read(root / "logs/project-lifecycle.jsonl", _MAX_AUDIT_BYTES)
        for proof in (created, witness):
            if (
                proof.audit_byte_count > len(audit)
                or hashlib.sha256(audit[: proof.audit_byte_count]).hexdigest() != proof.audit_sha256
            ):
                raise RecoveryVerificationProblem("source-audit-changed")
        if created.audit_byte_count >= witness.audit_byte_count:
            raise RecoveryVerificationProblem("source-audit-unavailable")
        try:
            records = [json.loads(line) for line in audit[created.audit_byte_count :].splitlines()]
            if (
                not records
                or records[0].get("event") != "project.opened"
                or any(
                    not isinstance(item, dict)
                    or set(item)
                    != {
                        "schemaVersion",
                        "event",
                        "state",
                        "recordedAt",
                        "traceId",
                    }
                    or item["schemaVersion"] != "1.0"
                    or item["event"] == "project.closed"
                    for item in records
                )
            ):
                raise ValueError("invalid operational audit linkage")
        except ValueError, UnicodeError, RecursionError, AttributeError:
            raise RecoveryVerificationProblem("source-audit-unavailable") from None
        inspection = self._recovery_native.inspect(witness, root, destination)
        if inspection.native_owner_state != "dead" or inspection.core_owner_state != "dead":
            raise RecoveryVerificationProblem("owner-death-unproven")
        if (
            inspection.source_file_identity != witness.root_file_identity
            or inspection.destination_parent_identity != _recovery_file_identity(destination.parent)
            or inspection.principal_reference != witness.native_session.principal_reference
        ):
            raise RecoveryVerificationProblem("native-proof-mismatch")
        try:
            self._recovery_key_access(identity)
        except Exception:
            raise RecoveryVerificationProblem("retained-key-unavailable") from None
        return witness

    def _recovery_projection(self, preview: _RecoveryPreview) -> ProjectRecoveryProjection:
        with self._recovery_mutex:
            return ProjectRecoveryProjection(
                preview_id=preview.preview_id,
                state=cast(Any, preview.state),
                reason_codes=preview.reason_codes,
                requires_confirmation=preview.state == "preview-ready",
                source_display_label=preview.source_display_label,
                destination_display_label=preview.destination.name[:120] or "New working copy",
                verified_fact_summary=preview.verified_fact_summary,
            )

    def _selected_recovery(self, root: str, preview_id: str) -> _RecoveryPreview:
        with self._recovery_mutex:
            preview = self._recovery_previews.get(preview_id)
            if preview is None or os.path.normcase(str(preview.root)) != os.path.normcase(root.replace("/", "\\")):
                raise self._recovery_problem()
            return preview

    def preview_recovery(self, *, root: str, destination_root: str, trace_id: str) -> ProjectRecoveryProjection:
        preview = _RecoveryPreview(secrets.token_hex(16), Path(root), Path(destination_root))
        with self._recovery_mutex:
            if len(self._recovery_previews) >= 64:
                for previous_id, previous in tuple(self._recovery_previews.items()):
                    if (
                        not previous.validating
                        and previous.state
                        in ("denied", "unavailable-proof", "cancelled", "verification-failed", "recovered")
                        and (previous.worker is None or not previous.worker.is_alive())
                    ):
                        del self._recovery_previews[previous_id]
                        if len(self._recovery_previews) < 64:
                            break
            if self._shutting_down or len(self._recovery_previews) >= 64:
                raise self._recovery_problem()
            self._recovery_previews[preview.preview_id] = preview
        try:
            if os.name != "nt" or not re.match(r"^[A-Za-z]:[\\/]", root):
                raise RecoveryVerificationProblem("source-path-unavailable")
            path = _canonical_directory(root)
            destination = self._recovery_destination(path, destination_root)
            with _stable_directories([path, destination.parent, *self._project_guard_paths(path)]):
                witness = self._fresh_recovery_proof(path, destination)
                _manifest, profile, _compatibility = self._assess_documents(path)
                with _recovery_inventory(path, preview.cancel.is_set) as inventory:
                    preview.root, preview.destination = path, destination
                    preview.witness, preview.source_signature = witness, inventory.signature
                    preview.source_display_label = str(profile["displayName"])
                preview.state = "preview-ready"
        except RecoveryVerificationProblem as error:
            preview.reason_codes = (error.reason_code,)
            preview.state = "unavailable-proof" if "unavailable" in error.reason_code else "denied"
        except OSError, ValueError, ProjectLifecycleProblem:
            preview.state, preview.reason_codes = "denied", ("source-or-destination-unavailable",)
        finally:
            with self._recovery_mutex:
                preview.validating = False
        return self._recovery_projection(preview)

    def confirm_recovery(
        self,
        *,
        root: str,
        preview_id: str,
        confirmation: str,
        trace_id: str,
    ) -> ProjectRecoveryProjection:
        preview = self._selected_recovery(root, preview_id)
        with self._recovery_mutex:
            if (
                self._shutting_down
                or confirmation != "recover-working-copy"
                or preview.state != "preview-ready"
                or preview.cancel.is_set()
            ):
                raise self._recovery_problem()
            preview.state = "copying"
            preview.worker = threading.Thread(
                target=self._create_recovery_copy,
                args=(preview, trace_id),
                name="project-recovery-copy",
                daemon=True,
            )
            preview.worker.start()
        return self._recovery_projection(preview)

    def recovery_status(self, *, root: str, preview_id: str) -> ProjectRecoveryProjection:
        return self._recovery_projection(self._selected_recovery(root, preview_id))

    def cancel_recovery(self, *, root: str, preview_id: str) -> ProjectRecoveryProjection:
        preview = self._selected_recovery(root, preview_id)
        with preview.publication_mutex, self._recovery_mutex:
            if preview.state in ("preview-ready", "copying") and not preview.published:
                preview.cancel.set()
                if preview.state == "preview-ready":
                    preview.state, preview.reason_codes = "cancelled", ("cancelled",)
        return self._recovery_projection(preview)

    def _create_recovery_copy(self, preview: _RecoveryPreview, trace_id: str) -> None:
        stage: Path | None = None
        stage_identity: tuple[int, int] | None = None
        exclusion: RecoveryExclusion | None = None
        failure: str | None = None
        facts: RecoveryCopyVerifiedFacts | None = None
        verification_holds = ExitStack()
        verified_inventory: _RecoveryInventory | None = None
        published_inventory: _RecoveryInventory | None = None
        try:
            _recovery_check_cancel(preview.cancel.is_set)
            if self._recovery_store is None or preview.witness is None or self._recovery_verifier is None:
                raise RecoveryVerificationProblem("ownership-proof-unavailable")
            exclusion = self._recovery_store.acquire_project(preview.witness.project_id)
            path, destination = preview.root, preview.destination
            with _stable_directories([path, destination.parent, *self._project_guard_paths(path)]):
                witness = self._fresh_recovery_proof(path, destination)
                if witness != preview.witness:
                    raise RecoveryVerificationProblem("ownership-record-changed")
                with _recovery_inventory(path, preview.cancel.is_set) as inventory:
                    if inventory.signature != preview.source_signature:
                        raise RecoveryVerificationProblem("source-inventory-changed")
                    stage = destination.parent / (f".{destination.name}.ro-recovery-{preview.preview_id}")
                    stage.mkdir(mode=0o700)
                    stage_identity = _path_identity(stage)
                    with _stable_directories([stage]):
                        # Persist a restart-safe deny before copying or removing
                        # the copied active lock. Ordinary layout validation
                        # rejects this entry, including if quarantine fails.
                        with (stage / _RECOVERY_INCOMPLETE_MARKER).open("xb") as marker:
                            marker.write(b"Recovery copy verification is incomplete.\n")
                            marker.flush()
                            os.fsync(marker.fileno())
                        for name in _PROJECT_DIRECTORIES:
                            (stage / name).mkdir(mode=0o700)
                        for directory in inventory.directories:
                            (stage / directory.relative_to(path)).mkdir(mode=0o700, parents=True, exist_ok=True)
                        expected_copy = {}
                        for source, (stream, identity, digest) in inventory.files.items():
                            _recovery_check_cancel(preview.cancel.is_set)
                            relative = source.relative_to(path)
                            copied = stage / relative
                            stream.seek(0)
                            with copied.open("xb") as target:
                                while True:
                                    _recovery_check_cancel(preview.cancel.is_set)
                                    material = stream.read(_RECOVERY_CHUNK_BYTES)
                                    if not material:
                                        break
                                    target.write(material)
                                target.flush()
                                os.fsync(target.fileno())
                            expected_copy[relative] = (identity[2], digest)
                        # This complete raw DB/WAL/object/config/export/audit barrier
                        # precedes any SQLite access to the privately owned copy.
                        with _recovery_inventory(stage, preview.cancel.is_set) as copied_inventory:
                            actual_copy = {
                                p.relative_to(stage): (value[1][2], value[2])
                                for p, value in copied_inventory.files.items()
                            }
                            if actual_copy != expected_copy:
                                raise RecoveryVerificationProblem("raw-copy-mismatch")
                        inventory.recheck(preview.cancel.is_set)
                        old_lock = stage / ".locks/session.lock"
                        archived_lock = stage / "logs" / (f"recovery-original-session-{preview.preview_id}.json")
                        # Only this owned raw copy loses its active lock name.
                        # The exact old bytes remain in private local lineage.
                        os.rename(old_lock, archived_lock)
                        audit_path = stage / "logs/project-lifecycle.jsonl"
                        audit_before = _recovery_read(audit_path, _MAX_AUDIT_BYTES)
                        shared_memory = stage / "state/project.sqlite3-shm"
                        wal = stage / "state/project.sqlite3-wal"
                        # DB and any committed copied WAL are held against
                        # writes. SQLite's derived shared-memory index and an
                        # absent, newly created empty WAL are operational only.
                        new_wal = not wal.exists()
                        operational_files = {audit_path, shared_memory}
                        if new_wal:
                            operational_files.add(wal)
                        verified_inventory = verification_holds.enter_context(
                            _recovery_inventory(
                                stage,
                                preview.cancel.is_set,
                                require_empty_derived=True,
                                writable_files=frozenset(operational_files),
                                incomplete_marker=True,
                            )
                        )
                        active = True
                        thread_id = threading.get_ident()

                        def staging_action(selected_root, require_write, action):
                            if (
                                not active
                                or threading.get_ident() != thread_id
                                or require_write
                                or Path(selected_root) != stage
                                or _path_identity(stage) != stage_identity
                            ):
                                raise RecoveryVerificationProblem("staging-authority-unavailable")
                            return action(stage, witness.project_id)

                        try:
                            facts = self._recovery_verifier(
                                stage,
                                witness.project_id,
                                _ProjectActionScope(staging_action),
                                preview.cancel.is_set,
                            )
                        finally:
                            active = False
                        if not isinstance(facts, RecoveryCopyVerifiedFacts):
                            raise RecoveryVerificationProblem("copy-verification-unavailable")
                        verified_inventory.recheck(preview.cancel.is_set)
                        if _recovery_read(audit_path, _MAX_AUDIT_BYTES) != audit_before:
                            raise RecoveryVerificationProblem("staging-audit-changed")
                        owned_line = self._audit(stage, "project.recovery-copy-verified", "active", trace_id)
                        audit_after = _recovery_read(audit_path, _MAX_AUDIT_BYTES)
                        if not isinstance(owned_line, bytes) or audit_after != audit_before + owned_line:
                            raise RecoveryVerificationProblem("staging-audit-changed")
                        for operational in sorted(operational_files):
                            if not operational.exists():
                                continue
                            stream = verification_holds.enter_context(_recovery_held_file(operational))
                            status = os.fstat(stream.fileno())
                            if operational == wal and new_wal and status.st_size != 0:
                                raise RecoveryVerificationProblem("staging-state-changed")
                            verified_inventory.files[operational] = (
                                stream,
                                (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns),
                                _recovery_stream_hash(stream, preview.cancel.is_set),
                            )
                            if operational == audit_path:
                                stream.seek(0)
                                if stream.read(_MAX_AUDIT_BYTES + 1) != audit_after:
                                    raise RecoveryVerificationProblem("staging-audit-changed")
                        verified_inventory.writable_files = frozenset()
                    inventory.recheck(preview.cancel.is_set)
                    if self._fresh_recovery_proof(path, destination) != witness:
                        raise RecoveryVerificationProblem("ownership-record-changed")
                    verified_inventory.recheck(preview.cancel.is_set)
                    verified_binding = verified_inventory.binding()
                    # Windows cannot rename a directory with open descendants.
                    # Reacquire strict holds and compare all verified bytes at
                    # the destination before granting ready/open authority.
                    verification_holds.close()
                    publish = verification_holds.enter_context(_held_directory_renamer(stage))
                    if _path_identity(stage) != stage_identity:
                        raise RecoveryVerificationProblem("staging-authority-changed")
                    with preview.publication_mutex:
                        _recovery_check_cancel(preview.cancel.is_set)
                        exclusion.validate()
                        self._recovery_destination(path, str(destination))
                        publish(destination)  # Held no-replace publication.
                        stage = destination  # Cleanup owns this name before any fallible probe.
                        preview.published = True
                        preview.target_identity = stage_identity
                        if _path_identity(destination) != stage_identity:
                            raise RecoveryVerificationProblem("published-copy-changed")
                        published_inventory = verification_holds.enter_context(
                            _recovery_inventory(
                                destination,
                                preview.cancel.is_set,
                                existing_root_hold=True,
                                require_empty_derived=True,
                                incomplete_marker=True,
                            )
                        )
                        if published_inventory.binding() != verified_binding:
                            raise RecoveryVerificationProblem("published-content-changed")
                        published_inventory.recheck(preview.cancel.is_set)
        except RecoveryVerificationProblem as error:
            failure = error.reason_code
        except OSError, ValueError, ProjectLifecycleProblem:
            failure = "copy-verification-unavailable"
        except Exception:
            # An unavailable composed policy/key adapter cannot strand copying
            # or turn an incomplete operation into a successful projection.
            failure = "copy-verification-unavailable"
        finally:
            if failure is None and published_inventory is not None and facts is not None:
                try:
                    with preview.publication_mutex:
                        _recovery_check_cancel(preview.cancel.is_set)
                        assert exclusion is not None
                        exclusion.validate()
                        published_inventory.recheck(preview.cancel.is_set)
                        # Source checks have finished. Keep all verified copy
                        # bytes held through the last incomplete-marker removal;
                        # remaining contexts release handles without new checks.
                        published_inventory.publication_finalized = True
                        (preview.destination / _RECOVERY_INCOMPLETE_MARKER).unlink()
                except RecoveryVerificationProblem as error:
                    failure = error.reason_code
                except OSError, ValueError, ProjectLifecycleProblem:
                    failure = "copy-verification-unavailable"
            try:
                verification_holds.close()
            except RecoveryVerificationProblem as error:
                failure = failure or error.reason_code
            except OSError, ValueError:
                failure = failure or "staging-authority-changed"
            if failure is not None and stage is not None and stage_identity is not None:
                # Retain only this operation's exact partial/published root. Never
                # replace, delete or repair an original or pre-existing target.
                with suppress(OSError, ProjectLifecycleProblem):
                    if _path_identity(stage) == stage_identity:
                        with _held_directory_renamer(stage) as quarantine:
                            if _path_identity(stage) == stage_identity:
                                quarantine(
                                    stage.parent
                                    / (f".{preview.destination.name}.ro-recovery-failed-{preview.preview_id}")
                                )
            if exclusion is not None:
                exclusion.close()
            with self._recovery_mutex:
                if failure is not None:
                    preview.state = "cancelled" if failure == "cancelled" else "verification-failed"
                    preview.reason_codes = (failure,)
                    preview.verified_fact_summary = None
                elif facts is not None:
                    preview.state = "verified-copy-ready"
                    preview.reason_codes = ()
                    preview.verified_fact_summary = (
                        f"Verified {facts.canonical_row_count} canonical rows "
                        f"and {facts.available_object_count} encrypted objects."
                    )

    def _record_recovery_open(self, path: Path, *, succeeded: bool) -> None:
        with self._recovery_mutex:
            for preview in self._recovery_previews.values():
                if preview.destination == path and preview.state in ("verified-copy-ready", "open-failed"):
                    preview.state = "recovered" if succeeded else "open-failed"
                    preview.reason_codes = () if succeeded else ("normal-open-unavailable",)

    def record_recovery_open(self, *, root: str, succeeded: bool) -> None:
        """Called only by normal open/worker attachment composition."""

        path = Path(root)
        if succeeded:
            with self._mutex:
                if self._opened.get(path) is not ProjectAccessMode.READ_WRITE:
                    raise self._recovery_problem()
                with _stable_directories(self._project_guard_paths(path)):
                    self._check_recovery_open_target(path)
        self._record_recovery_open(path, succeeded=succeeded)

    def _check_recovery_open_target(self, path: Path) -> None:
        with self._recovery_mutex:
            for preview in self._recovery_previews.values():
                if preview.destination == path and (
                    preview.state == "copying"
                    or (preview.published and preview.state in ("verification-failed", "cancelled"))
                ):
                    raise self._recovery_problem()
                if (
                    preview.destination == path
                    and preview.state in ("verified-copy-ready", "open-failed")
                    and (not preview.published or preview.target_identity != _path_identity(path))
                ):
                    preview.state = "open-failed"
                    preview.reason_codes = ("published-copy-changed",)
                    raise self._recovery_problem()

    @staticmethod
    def _project_guard_paths(path: Path) -> list[Path]:
        return [path, path / ".locks", path / "config", path / "logs", path / "state"]

    @staticmethod
    def _validate_database(path: Path, project_id: str) -> None:
        try:
            validate_canonical_database(path / "state" / "project.sqlite3", expected_project_id=project_id)
        except StorageProblem as error:
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-DAMAGED",
                title="Project database is damaged or incompatible",
                detail="The canonical local database did not satisfy its versioned identity and integrity contract.",
                remediation=(
                    "Keep the original unchanged. First make and verify a complete backup; repair only a working copy."
                ),
            ) from error

    @staticmethod
    def _write_lock(lock: Path, record: dict[str, Any]) -> None:
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(record, stream, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-ALREADY-OPEN",
                title="Project is already open",
                detail="A concurrent local open acquired the project lock first.",
                remediation="Return to the existing project window or close its verified session first.",
            ) from error
        except OSError as error:
            raise ProjectLifecycleProblem(
                status=500,
                code="RO-CORE-PROJECT-LOCK-FAILED",
                title="Project lock could not be acquired",
                detail="The project was not opened because exclusive access could not be established.",
                remediation="Check local filesystem permissions and retry.",
                retryable=True,
            ) from error

    def create(
        self,
        *,
        parent_directory: str,
        directory_name: str,
        display_name: str,
        template_id: str,
        trace_id: str,
        initialize_authority: Callable[[Path, str], None] | None = None,
    ) -> ProjectProjection:
        if initialize_authority is not None and not callable(initialize_authority):
            raise TypeError("project authority initializer must be callable")
        parent = _canonical_directory(parent_directory)
        if not _DIRECTORY_NAME.fullmatch(directory_name):
            raise ProjectLifecycleProblem.invalid_path()
        clean_name = display_name.strip()
        if not 1 <= len(clean_name) <= 120 or any(ord(character) < 32 for character in clean_name):
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-NAME-INVALID",
                title="Project name is invalid",
                detail="The project name must contain 1 to 120 visible characters.",
                remediation="Enter a concise project name without control characters.",
            )
        if not _TEMPLATE_ID.fullmatch(template_id) or template_id not in _IMPLEMENTED_TEMPLATES:
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-TEMPLATE-INVALID",
                title="Project template is invalid",
                detail="The selected project template is not a canonical local template identifier.",
                remediation="Choose an implemented project template.",
            )
        with _stable_directories([parent]):
            return self._create_at(
                parent=parent,
                directory_name=directory_name,
                display_name=clean_name,
                template_id=template_id,
                trace_id=trace_id,
                initialize_authority=initialize_authority,
            )

    def _create_at(
        self,
        *,
        parent: Path,
        directory_name: str,
        display_name: str,
        template_id: str,
        trace_id: str,
        initialize_authority: Callable[[Path, str], None] | None,
    ) -> ProjectProjection:
        target = parent / directory_name
        if target.exists() or _redirect(target):
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-ALREADY-EXISTS",
                title="Project location already exists",
                detail="Creation will not replace an existing filesystem entry.",
                remediation="Choose another directory name or open the existing project.",
            )
        project_id = str(uuid.uuid4())
        now = _timestamp()
        staging = parent / f".{directory_name}.ro-staging-{secrets.token_hex(8)}"
        try:
            staging.mkdir(mode=0o700)
            for relative in _PROJECT_DIRECTORIES:
                (staging / relative).mkdir(mode=0o700)
            manifest = {
                "schemaVersion": "1.0",
                "documentType": "research-observatory-project-manifest",
                "projectId": project_id,
                "projectRevision": 0,
                "packageFormatVersion": "1.0.0",
                "layoutVersion": "1.0",
                "lifecycleState": "active",
                "applicationCompatibility": {"minimum": "0.1.0", "maximumExclusive": "1.0.0"},
                "databaseProfile": "sqlite-wal-v1",
                "objectFormat": "encrypted-content-addressed-v1",
                "createdAt": now,
                "modifiedAt": now,
            }
            profile = {
                "schemaVersion": "1.0",
                "documentType": "research-observatory-project-profile",
                "displayName": display_name,
                "templateId": template_id,
            }
            with _held_directory_renamer(staging) as rename_staging:
                with _stable_directories([staging / ".locks", staging / "config", staging / "logs", staging / "state"]):
                    _atomic_json(staging / "project.ro.json", manifest)
                    _atomic_json(staging / "config" / "project-profile.json", profile)
                    initialize_database(
                        staging / "state" / "project.sqlite3",
                        project_id=project_id,
                        project_created_at=now,
                    )
                    if initialize_authority is not None:
                        try:
                            initialize_authority(staging, project_id)
                        except ProjectLifecycleProblem:
                            raise
                        except Exception as error:
                            raise ProjectLifecycleProblem(
                                status=500,
                                code="RO-CORE-PROJECT-CREATE-FAILED",
                                title="Project creation did not complete",
                                detail="Creation stopped before workflow and Research Intent authority were published.",
                                remediation="Inspect and retry after restoring the local project authority boundary.",
                                retryable=True,
                            ) from error
                    self._audit(staging, "project.created", "active", trace_id)
                rename_staging(target)
        except ProjectLifecycleProblem:
            self._remove_staging(staging)
            raise
        except StorageProblem as error:
            self._remove_staging(staging)
            raise ProjectLifecycleProblem(
                status=500,
                code="RO-CORE-PROJECT-CREATE-FAILED",
                title="Project creation did not complete",
                detail="Creation stopped before the staged project and canonical database were published.",
                remediation="Remove any named staging directory after inspection, then retry.",
                retryable=True,
            ) from error
        except OSError as error:
            self._remove_staging(staging)
            raise ProjectLifecycleProblem(
                status=500,
                code="RO-CORE-PROJECT-CREATE-FAILED",
                title="Project creation did not complete",
                detail="Creation stopped before the staged project was published.",
                remediation="Remove any named staging directory after inspection, then retry.",
                retryable=True,
            ) from error
        return self._projection(target, manifest=manifest, profile=profile)

    def shutdown(self) -> None:
        """Release only locks owned by this supervised Core instance."""

        with self._recovery_mutex:
            self._shutting_down = True
            previews = tuple(self._recovery_previews.values())
        for preview in previews:
            with preview.publication_mutex:
                if not preview.published:
                    preview.cancel.set()
        with self._mutex:
            owners = tuple(self._owned_sessions.values())
            for owner in owners:
                owner.stop.set()
            for path in set(self._opened) | set(self._owned_sessions) | set(self._owned_locks):
                if self._opened.get(path) is ProjectAccessMode.READ_ONLY:
                    self._opened.pop(path, None)
                    continue
                try:
                    with _stable_directories(self._project_guard_paths(path)):
                        self._remove_owned_lock(path)
                except OSError, UnicodeError, json.JSONDecodeError, ProjectLifecycleProblem:
                    continue
                finally:
                    self._opened.pop(path, None)
            self._owned_sessions.clear()
            self._owned_locks.clear()
        # Never join or wait for protected issuance while holding the lifecycle
        # mutex. Native retains the bounded owned-Job stop deadline.
        for owner in owners:
            if owner.heartbeat is not None:
                owner.heartbeat.join(timeout=1)
            owner.exclusion.close()

    def perform_open_project_action(
        self,
        *,
        root: str,
        require_write: bool,
        action: Callable[[Path, str], _PROJECT_ACTION_RESULT],
        scope_consumer: Callable[[_ProjectActionScope], None] | None = None,
    ) -> _PROJECT_ACTION_RESULT:
        """Run one bounded project action while retaining lifecycle authority.

        Privacy, retention, and later project-scoped modules use this seam instead
        of reconstructing path, compatibility, or session-lock authority.
        """

        if not callable(action):
            raise TypeError("project action must be callable")
        with self._mutex:
            path = _canonical_directory(root)
            with _stable_directories(self._project_guard_paths(path)):
                project_id = self._assess_open_project_authority(path, require_write=require_write)
                self._validate_database(path, project_id)
                if scope_consumer is None:
                    return action(path, project_id)
                active = True
                owner_thread = threading.get_ident()

                def nested(
                    selected_root: str, selected_write: bool, selected_action: Callable[[Path, str], Any]
                ) -> Any:
                    if (
                        not active
                        or threading.get_ident() != owner_thread
                        or not callable(selected_action)
                        or _canonical_directory(selected_root) != path
                    ):
                        raise ProjectLifecycleProblem(
                            status=409,
                            code="RO-CORE-PROJECT-ACTION-SCOPE-INVALID",
                            title="Project action scope is unavailable",
                            detail="Nested project authority must stay within its owning current action.",
                            remediation="Retry through the current project action.",
                        )
                    current_id = self._assess_open_project_authority(path, require_write=selected_write)
                    if current_id != project_id:
                        raise ProjectLifecycleProblem.invalid_path()
                    return selected_action(path, current_id)

                try:
                    scope_consumer(_ProjectActionScope(nested))
                    return action(path, project_id)
                finally:
                    active = False

    def _assess_open_project_authority(self, path: Path, *, require_write: bool) -> str:
        self._validate_layout(path)
        manifest, _profile, compatibility = self._assess_documents(path)
        access = self._opened.get(path)
        if access is None:
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-NOT-OPEN",
                title="Project is not open",
                detail="Project-scoped settings require an open local project session.",
                remediation="Open the compatible project locally and retry.",
            )
        if require_write and (
            access is not ProjectAccessMode.READ_WRITE or compatibility is not ProjectCompatibilityState.COMPATIBLE
        ):
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-READ-ONLY",
                title="Project is read-only",
                detail="Privacy settings and cache cleanup cannot mutate a read-only project.",
                remediation="Use a compatible writable project copy and retry.",
            )
        return str(manifest["projectId"])

    def open(self, *, root: str, trace_id: str) -> ProjectProjection:
        path = _canonical_directory(root)
        if self._recovery_store is None:
            if self._require_recovery_exclusion:
                raise self._recovery_problem()
            return self._open_existing(root=root, trace_id=trace_id)
        owner: _OwnedProjectSession | None = None
        with _stable_directories(self._project_guard_paths(path)):
            self._check_recovery_open_target(path)
            self._validate_layout(path)
            manifest, _profile, compatibility = self._assess_documents(path)
            if compatibility is not ProjectCompatibilityState.COMPATIBLE:
                return self._open_existing(root=root, trace_id=trace_id)
            lock = path / ".locks/session.lock"
            if lock.exists() or _redirect(lock):
                # Preserve the ordinary foreign/old lock denial before sealing.
                return self._open_existing(root=root, trace_id=trace_id)
            try:
                exclusion = self._recovery_store.acquire_project(str(manifest["projectId"]))
            except RecoveryVerificationProblem:
                raise self._recovery_problem() from None
            record = {
                "schemaVersion": "1.0",
                "documentType": "research-observatory-project-lock",
                "projectId": manifest["projectId"],
                "instanceId": self._instance_id,
                "processId": os.getpid(),
                "heartbeatAt": _timestamp(),
                "recoveryToken": secrets.token_hex(32),
            }
            owner = _OwnedProjectSession(exclusion, record)
            try:
                # Native/DPAPI work is outside the shared lifecycle mutex.
                try:
                    if self._recovery_native is not None:
                        session = self._recovery_native.current_session()
                        created = self._session_witness(path, record, session, "created")
                        self._recovery_store.issue(created)
                        owner.witness = created
                except OSError, ValueError, RecoveryVerificationProblem:
                    # A protected exclusion still owns this ordinary session.
                    # Missing durable proof truthfully denies later recovery.
                    owner.witness = None
                projection = self._open_existing(root=root, trace_id=trace_id, owner=owner)
                try:
                    if owner.witness is not None:
                        opened = self._session_witness(path, record, owner.witness.native_session, "opened")
                        self._recovery_store.issue(opened)
                        owner.witness = opened
                except OSError, ValueError, RecoveryVerificationProblem:
                    owner.witness = None
                with self._mutex:
                    owner.ready = True
                self._start_heartbeat(path, owner)
                return projection
            except BaseException:
                # Failure before authoritative open may release this resource.
                # A rollback failure retains ownership until Core terminates.
                with self._mutex:
                    retained = path in self._opened or path in self._owned_locks
                    if not retained and lock.exists():
                        try:
                            actual, _bytes = _recovery_lock(lock)
                            retained = actual == record
                        except OSError, RecoveryVerificationProblem:
                            retained = True
                    if not retained:
                        self._owned_sessions.pop(path, None)
                    else:
                        owner.ready = True
                        owner.stop.set()
                        self._owned_sessions[path] = owner
                if not retained:
                    exclusion.close()
                self._record_recovery_open(path, succeeded=False)
                raise

    def _open_existing(
        self,
        *,
        root: str,
        trace_id: str,
        owner: _OwnedProjectSession | None = None,
    ) -> ProjectProjection:
        with self._mutex:
            if self._shutting_down:
                raise self._recovery_problem()
            path = _canonical_directory(root)
            with _stable_directories(self._project_guard_paths(path)):
                self._check_recovery_open_target(path)
                self._validate_layout(path)
                manifest, profile, compatibility = self._assess_documents(path)
                if manifest["lifecycleState"] != "active":
                    raise ProjectLifecycleProblem(
                        status=409,
                        code="RO-CORE-PROJECT-NOT-ACTIVE",
                        title="Project is not active",
                        detail="Archived or trashed projects cannot open for mutation.",
                        remediation="Restore an archived project before opening it.",
                    )
                lock = path / ".locks" / "session.lock"
                if path in self._opened or lock.exists() or _redirect(lock):
                    raise ProjectLifecycleProblem(
                        status=409,
                        code="RO-CORE-PROJECT-ALREADY-OPEN",
                        title="Project is already open",
                        detail="A concurrent local open was detected and no project bytes were changed.",
                        remediation="Return to the existing project window or close its verified session first.",
                    )
                if compatibility is not ProjectCompatibilityState.COMPATIBLE:
                    emit_log_record(
                        "project.compatibility",
                        level="WARNING",
                        fields={
                            "state": compatibility.value,
                            "reasonCode": "read-only-safe-open",
                            "traceId": trace_id,
                        },
                    )
                    self._opened[path] = ProjectAccessMode.READ_ONLY
                    return self._projection(
                        path,
                        manifest=manifest,
                        profile=profile,
                        compatibility=compatibility,
                    )
                record = (
                    owner.record
                    if owner is not None
                    else {
                        "schemaVersion": "1.0",
                        "documentType": "research-observatory-project-lock",
                        "projectId": manifest["projectId"],
                        "instanceId": self._instance_id,
                        "processId": os.getpid(),
                        "heartbeatAt": _timestamp(),
                        "recoveryToken": secrets.token_hex(32),
                    }
                )
                self._write_lock(lock, record)
                self._owned_locks[path] = (dict(record), _path_identity(lock))
                if owner is not None:
                    owner.lock_identity = self._owned_locks[path][1]
                try:
                    if self._object_upgrade is not None:
                        try:
                            self._object_upgrade(path, str(manifest["projectId"]))
                        except ObjectKeyUnavailable as error:
                            raise ProjectLifecycleProblem(
                                status=409,
                                code="RO-CORE-PROJECT-UPGRADE-KEY-UNAVAILABLE",
                                title="Project encryption key is unavailable",
                                detail=(
                                    "The project remained closed because its supported prior objects "
                                    "could not be upgraded without the retained project key."
                                ),
                                remediation="Restore the required local project key and retry open.",
                                retryable=True,
                            ) from error
                        except ObjectStoreProblem as error:
                            raise ProjectLifecycleProblem(
                                status=500,
                                code="RO-CORE-PROJECT-UPGRADE-FAILED",
                                title="Project object upgrade did not complete",
                                detail=("The project remained closed with its verified recovery authority retained."),
                                remediation="Keep the project unchanged, restore the prerequisite, and retry open.",
                                retryable=True,
                            ) from error
                    self._validate_database(path, str(manifest["projectId"]))
                    self._opened[path] = ProjectAccessMode.READ_WRITE
                    self._audit(path, "project.opened", "active", trace_id)
                    if owner is not None:
                        self._owned_sessions[path] = owner
                except ProjectLifecycleProblem as error:
                    self._opened.pop(path, None)
                    try:
                        self._remove_owned_lock(path)
                    except (OSError, ProjectLifecycleProblem) as rollback_error:
                        raise ProjectLifecycleProblem.rollback_failed() from rollback_error
                    raise error
                return self._projection(
                    path,
                    manifest=manifest,
                    profile=profile,
                    compatibility=compatibility,
                )

    def _remove_owned_lock(self, path: Path) -> dict[str, Any]:
        """Delete only the exact held file and complete current owned record."""

        lock = path / ".locks/session.lock"
        expected = self._owned_locks.get(path)
        try:
            if expected is None:
                raise RecoveryVerificationProblem("owned-lock-unavailable")
            owner = self._owned_sessions.get(path)
            if owner is not None:
                owner.exclusion.validate()
            with _recovery_held_file(lock, stable_name=False, delete_access=True) as stream:
                record = _recovery_parse_lock(stream.read(4097))
                status = os.fstat(stream.fileno())
                if record != expected[0] or (status.st_dev, status.st_ino) != expected[1]:
                    raise RecoveryVerificationProblem("owned-lock-changed")
                if os.name == "nt":
                    import ctypes
                    import msvcrt
                    from ctypes import wintypes

                    function = ctypes.WinDLL("kernel32", use_last_error=True).SetFileInformationByHandle
                    function.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
                    function.restype = wintypes.BOOL
                    flags = wintypes.DWORD(3)  # DELETE | POSIX_SEMANTICS: exact file, no path unlink.
                    if not function(
                        msvcrt.get_osfhandle(stream.fileno()), 21, ctypes.byref(flags), ctypes.sizeof(flags)
                    ):
                        raise OSError("owned lock removal unavailable")
                else:
                    if _path_identity(lock) != expected[1]:
                        raise RecoveryVerificationProblem("owned-lock-changed")
                    lock.unlink()
            self._owned_locks.pop(path, None)
            return record
        except RecoveryVerificationProblem:
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-LOCK-CHANGED",
                title="Project lock identity changed",
                detail="The complete current lock no longer matches this supervised Core's owned record.",
                remediation="Keep the lock unchanged and use the safe recovery workflow.",
            ) from None

    def close(self, *, root: str, trace_id: str) -> ProjectProjection:
        path = _canonical_directory(root)
        owner: _OwnedProjectSession | None = None
        error: BaseException | None = None
        with self._mutex:
            owner = self._owned_sessions.get(path)
            if owner is not None and not owner.ready:
                raise self._recovery_problem()
            if owner is not None:
                owner.stop.set()
            try:
                projection = self._close_existing(root=root, trace_id=trace_id)
            except BaseException as failure:
                # The original lock/audit rollback remains authoritative.
                # Retain its exclusion; a stopped refresh grants no takeover.
                error = failure
            if error is None and owner is not None:
                self._owned_sessions.pop(path, None)
        if error is not None:
            if owner is not None:
                if owner.heartbeat is not None:
                    owner.heartbeat.join(timeout=1)
                with self._mutex:
                    if (
                        not self._shutting_down
                        and self._owned_sessions.get(path) is owner
                        and self._opened.get(path) is ProjectAccessMode.READ_WRITE
                        and (owner.heartbeat is None or not owner.heartbeat.is_alive())
                    ):
                        owner.stop = threading.Event()
                        self._start_heartbeat(path, owner)
            raise error
        if owner is not None:
            if owner.heartbeat is not None:
                owner.heartbeat.join(timeout=1)
            try:
                if owner.witness is not None and self._recovery_store is not None:
                    closed = self._session_witness(path, owner.record, owner.witness.native_session, "closed")
                    self._recovery_store.issue(closed)
            except OSError, ValueError, RecoveryVerificationProblem:
                # The completed close removed its exact lock and audited it.
                # Old witness bytes remain immutable and cannot grant recovery.
                pass
            finally:
                owner.exclusion.close()
        return projection

    def _close_existing(self, *, root: str, trace_id: str) -> ProjectProjection:
        with self._mutex:
            path = _canonical_directory(root)
            with _stable_directories(self._project_guard_paths(path)):
                self._validate_layout(path)
                manifest, profile, compatibility = self._assess_documents(path)
                lock = path / ".locks" / "session.lock"
                if self._opened.get(path) is ProjectAccessMode.READ_ONLY:
                    self._opened.pop(path, None)
                    return self._projection(
                        path,
                        manifest=manifest,
                        profile=profile,
                        compatibility=compatibility,
                    )
                if self._opened.get(path) is ProjectAccessMode.READ_WRITE:
                    try:
                        record = self._remove_owned_lock(path)
                    except ProjectLifecycleProblem:
                        raise
                    except (OSError, UnicodeError, json.JSONDecodeError) as error:
                        raise ProjectLifecycleProblem(
                            status=500,
                            code="RO-CORE-PROJECT-CLOSE-FAILED",
                            title="Project close did not complete",
                            detail="The verified project lock could not be removed.",
                            remediation="Keep the application open and retry close before using recovery.",
                            retryable=True,
                        ) from error
                    self._opened.pop(path, None)
                    try:
                        self._audit(path, "project.closed", str(manifest["lifecycleState"]), trace_id)
                    except ProjectLifecycleProblem as error:
                        try:
                            self._write_lock(lock, record)
                            self._owned_locks[path] = (dict(record), _path_identity(lock))
                            owner = self._owned_sessions.get(path)
                            if owner is not None:
                                owner.lock_identity = self._owned_locks[path][1]
                            self._opened[path] = ProjectAccessMode.READ_WRITE
                        except ProjectLifecycleProblem as rollback_error:
                            raise ProjectLifecycleProblem.rollback_failed() from rollback_error
                        raise error
                elif lock.exists() or _redirect(lock):
                    raise ProjectLifecycleProblem(
                        status=409,
                        code="RO-CORE-PROJECT-OPEN-ELSEWHERE",
                        title="Project is owned by another session",
                        detail="This Core instance will not remove an unverified project lock.",
                        remediation="Return to the owning session or use the reviewed stale-lock recovery workflow.",
                    )
                return self._projection(
                    path,
                    manifest=manifest,
                    profile=profile,
                    compatibility=compatibility,
                )

    def archive(self, *, root: str, trace_id: str) -> ProjectProjection:
        return self._transition(
            root=root, expected="active", target="archived", event="project.archived", trace_id=trace_id
        )

    def restore(self, *, root: str, trace_id: str) -> ProjectProjection:
        return self._transition(
            root=root, expected="archived", target="active", event="project.restored", trace_id=trace_id
        )

    def delete(self, *, root: str, confirmation: str, trace_id: str) -> ProjectProjection:
        with self._mutex:
            path = _canonical_directory(root)
            parent = _canonical_directory(str(path.parent))
            with _stable_directories([parent]):
                trash = parent / ".research-observatory-trash"
                if trash.exists():
                    if not trash.is_dir() or _redirect(trash):
                        raise ProjectLifecycleProblem.invalid_path()
                else:
                    trash.mkdir(mode=0o700)
                trash = _canonical_directory(str(trash))
                with _held_directory_renamer(path) as rename_project:
                    with _stable_directories([path / ".locks", path / "config", path / "logs", path / "state"]):
                        self._validate_layout(path)
                        manifest, profile = self._documents(path)
                        self._require_closed(path)
                        expected = f"delete:{manifest['projectId']}"
                        if not secrets.compare_digest(confirmation, expected):
                            raise ProjectLifecycleProblem(
                                status=422,
                                code="RO-CORE-PROJECT-DELETE-CONFIRMATION-INVALID",
                                title="Project deletion was not confirmed",
                                detail=(
                                    "Deletion requires the exact project-specific confirmation "
                                    "shown by the application."
                                ),
                                remediation="Review the consequences and enter the exact confirmation phrase.",
                            )
                        original_manifest = manifest
                        manifest = self._updated_manifest(manifest, "trash")
                        _atomic_json(path / "project.ro.json", manifest)
                        try:
                            self._audit(path, "project.trashed", "trash", trace_id)
                        except ProjectLifecycleProblem as error:
                            try:
                                _atomic_json(path / "project.ro.json", original_manifest)
                            except ProjectLifecycleProblem as rollback_error:
                                raise ProjectLifecycleProblem.rollback_failed() from rollback_error
                            raise error
                        destination = trash / f"{manifest['projectId']}-{secrets.token_hex(6)}"
                        if destination.exists() or _redirect(destination):
                            raise ProjectLifecycleProblem.invalid_path()
                    try:
                        rename_project(destination)
                    except OSError as error:
                        try:
                            with _stable_directories([path / ".locks", path / "config", path / "logs", path / "state"]):
                                _atomic_json(path / "project.ro.json", original_manifest)
                                self._audit(
                                    path,
                                    "project.trash-rollback",
                                    str(original_manifest["lifecycleState"]),
                                    trace_id,
                                )
                        except ProjectLifecycleProblem as rollback_error:
                            raise ProjectLifecycleProblem.rollback_failed() from rollback_error
                        raise ProjectLifecycleProblem(
                            status=500,
                            code="RO-CORE-PROJECT-DELETE-FAILED",
                            title="Project was not moved to recoverable trash",
                            detail="The lifecycle state was rolled back because the recoverable move failed.",
                            remediation="Check local storage permissions and retry.",
                            retryable=True,
                        ) from error
                return self._projection(destination, manifest=manifest, profile=profile)

    def _transition(self, *, root: str, expected: str, target: str, event: str, trace_id: str) -> ProjectProjection:
        with self._mutex:
            path = _canonical_directory(root)
            with _stable_directories(self._project_guard_paths(path)):
                self._validate_layout(path)
                manifest, profile = self._documents(path)
                self._require_closed(path)
                if manifest["lifecycleState"] != expected:
                    raise ProjectLifecycleProblem(
                        status=409,
                        code="RO-CORE-PROJECT-STATE-CONFLICT",
                        title="Project lifecycle state changed",
                        detail=f"This action requires a project in the {expected} state.",
                        remediation="Refresh project state before choosing another lifecycle action.",
                        retryable=True,
                    )
                original_manifest = manifest
                manifest = self._updated_manifest(original_manifest, target)
                _atomic_json(path / "project.ro.json", manifest)
                try:
                    self._audit(path, event, target, trace_id)
                except ProjectLifecycleProblem as error:
                    try:
                        _atomic_json(path / "project.ro.json", original_manifest)
                    except ProjectLifecycleProblem as rollback_error:
                        raise ProjectLifecycleProblem.rollback_failed() from rollback_error
                    raise error
                return self._projection(path, manifest=manifest, profile=profile)

    def _require_closed(self, path: Path) -> None:
        lock = path / ".locks" / "session.lock"
        if path in self._opened or lock.exists() or _redirect(lock):
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-MUST-CLOSE",
                title="Project must be closed first",
                detail="Lifecycle changes are denied while any project lock is present.",
                remediation="Close the verified project session, then retry the lifecycle action.",
            )

    def _documents(self, path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        manifest, profile, compatibility = self._assess_documents(path)
        if compatibility is not ProjectCompatibilityState.COMPATIBLE:
            raise self._compatibility_problem(compatibility)
        self._validate_database(path, str(manifest["projectId"]))
        return manifest, profile

    @staticmethod
    def _compatibility_problem(compatibility: ProjectCompatibilityState) -> ProjectLifecycleProblem:
        if compatibility is ProjectCompatibilityState.NEWER_UNSUPPORTED:
            return ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-NEWER-UNSUPPORTED",
                title="Project requires a newer compatible application",
                detail="This project is available only for read-only inspection in the current application.",
                remediation=(
                    "First create and verify a complete backup, then reopen it with a compatible application version."
                ),
            )
        return ProjectLifecycleProblem(
            status=409,
            code="RO-CORE-PROJECT-MIGRATION-REQUIRED",
            title="Project migration is required",
            detail="This older project is available only for read-only inspection until a reviewed migration is run.",
            remediation=(
                "First create and verify a complete backup, then run the reviewed project migration against a copy."
            ),
        )

    def _assess_documents(
        self,
        path: Path,
    ) -> tuple[dict[str, Any], dict[str, Any], ProjectCompatibilityState]:
        manifest = _read_project_document(path / "project.ro.json")
        profile = _read_project_document(path / "config" / "project-profile.json")
        compatibility = manifest.get("applicationCompatibility") if isinstance(manifest, dict) else None
        package_format = _release_version(manifest.get("packageFormatVersion")) if isinstance(manifest, dict) else None
        minimum = _release_version(compatibility.get("minimum")) if isinstance(compatibility, dict) else None
        maximum = _release_version(compatibility.get("maximumExclusive")) if isinstance(compatibility, dict) else None
        created = _utc_datetime(manifest.get("createdAt")) if isinstance(manifest, dict) else None
        modified = _utc_datetime(manifest.get("modifiedAt")) if isinstance(manifest, dict) else None
        if (
            not isinstance(manifest, dict)
            or set(manifest) != _MANIFEST_KEYS
            or manifest.get("schemaVersion") != "1.0"
            or manifest.get("documentType") != "research-observatory-project-manifest"
            or not isinstance(manifest.get("projectId"), str)
            or not _PROJECT_ID.fullmatch(str(manifest["projectId"]))
            or manifest.get("lifecycleState") not in {"active", "archived", "trash"}
            or not isinstance(manifest.get("projectRevision"), int)
            or isinstance(manifest.get("projectRevision"), bool)
            or not 0 <= manifest.get("projectRevision", -1) <= _MAX_SAFE_INTEGER
            or package_format is None
            or not isinstance(manifest.get("layoutVersion"), str)
            or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", str(manifest.get("layoutVersion")))
            or not isinstance(manifest.get("databaseProfile"), str)
            or not _TEMPLATE_ID.fullmatch(str(manifest.get("databaseProfile")))
            or not isinstance(manifest.get("objectFormat"), str)
            or not _TEMPLATE_ID.fullmatch(str(manifest.get("objectFormat")))
            or not isinstance(compatibility, dict)
            or set(compatibility) != {"minimum", "maximumExclusive"}
            or minimum is None
            or maximum is None
            or minimum >= maximum
            or created is None
            or modified is None
            or created > modified
        ):
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-DAMAGED",
                title="Project manifest is damaged",
                detail="The project root does not match the implemented versioned manifest contract.",
                remediation=(
                    "Keep the original unchanged. First make and verify a complete backup; repair only a working copy."
                ),
            )
        if (
            not isinstance(profile, dict)
            or set(profile) != _PROFILE_KEYS
            or profile.get("schemaVersion") != "1.0"
            or profile.get("documentType") != "research-observatory-project-profile"
            or not isinstance(profile.get("displayName"), str)
            or not 1 <= len(profile["displayName"]) <= 120
            or any(ord(character) < 32 or ord(character) == 127 for character in profile["displayName"])
            or not isinstance(profile.get("templateId"), str)
            or not _TEMPLATE_ID.fullmatch(profile["templateId"])
            or profile["templateId"] not in _IMPLEMENTED_TEMPLATES
        ):
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-DAMAGED",
                title="Project profile is damaged",
                detail="The local project profile does not match its exact versioned contract.",
                remediation=(
                    "Keep the original unchanged. First make and verify a complete backup; repair only a working copy."
                ),
            )
        if package_format > _CURRENT_PACKAGE_FORMAT or minimum > _CURRENT_APPLICATION_VERSION:
            state = ProjectCompatibilityState.NEWER_UNSUPPORTED
        elif package_format < _CURRENT_PACKAGE_FORMAT or maximum <= _CURRENT_APPLICATION_VERSION:
            state = ProjectCompatibilityState.MIGRATION_REQUIRED
        elif (
            manifest["layoutVersion"] != "1.0"
            or manifest["databaseProfile"] != "sqlite-wal-v1"
            or manifest["objectFormat"] != "encrypted-content-addressed-v1"
        ):
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-DAMAGED",
                title="Current project format is internally inconsistent",
                detail="Current-format storage metadata does not match the implemented project contract.",
                remediation=(
                    "Keep the original unchanged. First make and verify a complete backup; repair only a working copy."
                ),
            )
        else:
            state = ProjectCompatibilityState.COMPATIBLE
        return manifest, profile, state

    @staticmethod
    def _validate_layout(path: Path) -> None:
        expected = {*_PROJECT_DIRECTORIES, "project.ro.json"}
        try:
            present = {entry.name for entry in path.iterdir()}
            if expected - present:
                raise ProjectLifecycleProblem(
                    status=422,
                    code="RO-CORE-PROJECT-INCOMPLETE",
                    title="Project package is incomplete",
                    detail="One or more required project package entries are missing.",
                    remediation=(
                        "Keep the original unchanged. First make and verify a complete backup, "
                        "then restore missing entries."
                    ),
                )
            if present != expected:
                raise ProjectLifecycleProblem.invalid_path()
            for relative in _PROJECT_DIRECTORIES:
                directory = path / relative
                if _redirect(directory):
                    raise ProjectLifecycleProblem.invalid_path()
                if not directory.is_dir():
                    raise ProjectLifecycleProblem(
                        status=422,
                        code="RO-CORE-PROJECT-INCOMPLETE",
                        title="Project package is incomplete",
                        detail="A required project package directory is unavailable.",
                        remediation=(
                            "Keep the original unchanged. First make and verify a complete backup, "
                            "then restore the directory."
                        ),
                    )
            for document in (path / "project.ro.json", path / "config" / "project-profile.json"):
                if _redirect(document):
                    raise ProjectLifecycleProblem.invalid_path()
                if not document.is_file():
                    raise ProjectLifecycleProblem(
                        status=422,
                        code="RO-CORE-PROJECT-INCOMPLETE",
                        title="Project package is incomplete",
                        detail="A required project metadata document is unavailable.",
                        remediation=(
                            "Keep the original unchanged. First make and verify a complete backup, "
                            "then restore the document."
                        ),
                    )
        except ProjectLifecycleProblem:
            raise
        except OSError as error:
            raise ProjectLifecycleProblem.invalid_path() from error

    def _projection(
        self,
        path: Path,
        *,
        manifest: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
        compatibility: ProjectCompatibilityState | None = None,
    ) -> ProjectProjection:
        if manifest is None or profile is None or compatibility is None:
            manifest, profile, compatibility = self._assess_documents(path)
        access_mode = self._opened.get(path, ProjectAccessMode.CLOSED)
        if compatibility is ProjectCompatibilityState.COMPATIBLE:
            recovery_action = ProjectRecoveryAction.NONE
        elif compatibility is ProjectCompatibilityState.MIGRATION_REQUIRED:
            recovery_action = ProjectRecoveryAction.BACKUP_THEN_MIGRATE
        else:
            recovery_action = ProjectRecoveryAction.BACKUP_THEN_USE_COMPATIBLE_APPLICATION
        return ProjectProjection(
            project_id=str(manifest["projectId"]),
            display_name=str(profile["displayName"]),
            template_id=str(profile["templateId"]),
            lifecycle_state=ProjectLifecycleState(str(manifest["lifecycleState"])),
            root=str(path),
            open=access_mode is not ProjectAccessMode.CLOSED,
            access_mode=access_mode,
            compatibility_state=compatibility,
            package_format_version=str(manifest["packageFormatVersion"]),
            backup_required_before_repair=compatibility is not ProjectCompatibilityState.COMPATIBLE,
            recovery_action=recovery_action,
            revision=int(manifest["projectRevision"]),
            delete_confirmation=f"delete:{manifest['projectId']}",
        )

    def _updated_manifest(self, manifest: dict[str, Any], state: str) -> dict[str, Any]:
        if int(manifest["projectRevision"]) >= _MAX_SAFE_INTEGER:
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-REVISION-EXHAUSTED",
                title="Project revision cannot advance",
                detail="The project reached the maximum supported manifest revision.",
                remediation="Keep the project closed and request a reviewed format migration.",
            )
        return {
            **manifest,
            "projectRevision": int(manifest["projectRevision"]) + 1,
            "lifecycleState": state,
            "modifiedAt": _timestamp(),
        }

    def _audit(self, root: Path, event: str, state: str, trace_id: str) -> bytes:
        if not _TRACE_ID.fullmatch(trace_id):
            raise ProjectLifecycleProblem(
                status=500,
                code="RO-CORE-PROJECT-AUDIT-FAILED",
                title="Project audit identity is invalid",
                detail="The lifecycle action was denied because its correlation identity was invalid.",
                remediation="Retry through the generated desktop client.",
            )
        record = {
            "schemaVersion": "1.0",
            "event": event,
            "state": state,
            "recordedAt": _timestamp(),
            "traceId": trace_id,
        }
        return _atomic_audit_append(root / "logs" / "project-lifecycle.jsonl", record)

    @staticmethod
    def _remove_staging(staging: Path) -> None:
        if staging.exists() and not _redirect(staging):
            with suppress(OSError):
                shutil.rmtree(staging)
