"""Local project package lifecycle authority.

The project package is authoritative. This module owns the versioned manifest,
classified directories, lock, and audit seam and delegates canonical database
creation and validation to the storage adapter. Domain repositories remain
outside this lifecycle boundary.
"""

from __future__ import annotations

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
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, TypeVar, cast

from .logging import emit_log_record
from .models import (
    ProjectAccessMode,
    ProjectCompatibilityState,
    ProjectLifecycleState,
    ProjectProjection,
    ProjectRecoveryAction,
)
from .ports.object_store import ObjectKeyUnavailable, ObjectStoreProblem
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


def _atomic_audit_append(path: Path, record: dict[str, Any]) -> None:
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


class ProjectLifecycleService:
    """Serialize package lifecycle operations for one supervised Core process."""

    def __init__(self, *, object_upgrade: Callable[[Path, str], object] | None = None) -> None:
        if object_upgrade is not None and not callable(object_upgrade):
            raise TypeError("object upgrade must be a callable composition boundary")
        self._instance_id = str(uuid.uuid4())
        self._opened: dict[Path, ProjectAccessMode] = {}
        self._mutex = threading.RLock()
        self._object_upgrade = object_upgrade

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

        with self._mutex:
            for path in tuple(self._opened):
                if self._opened.get(path) is ProjectAccessMode.READ_ONLY:
                    self._opened.pop(path, None)
                    continue
                lock = path / ".locks" / "session.lock"
                try:
                    with _stable_directories(self._project_guard_paths(path)):
                        record = json.loads(lock.read_text(encoding="utf-8"))
                        status = lock.stat(follow_symlinks=False)
                        if (
                            isinstance(record, dict)
                            and record.get("instanceId") == self._instance_id
                            and not _redirect(lock)
                            and status.st_nlink == 1
                        ):
                            lock.unlink()
                except OSError, UnicodeError, json.JSONDecodeError, ProjectLifecycleProblem:
                    continue
                finally:
                    self._opened.pop(path, None)

    def perform_open_project_action(
        self,
        *,
        root: str,
        require_write: bool,
        action: Callable[[Path, str], _PROJECT_ACTION_RESULT],
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
                    access is not ProjectAccessMode.READ_WRITE
                    or compatibility is not ProjectCompatibilityState.COMPATIBLE
                ):
                    raise ProjectLifecycleProblem(
                        status=409,
                        code="RO-CORE-PROJECT-READ-ONLY",
                        title="Project is read-only",
                        detail="Privacy settings and cache cleanup cannot mutate a read-only project.",
                        remediation="Use a compatible writable project copy and retry.",
                    )
                project_id = str(manifest["projectId"])
                self._validate_database(path, project_id)
                return action(path, project_id)

    def open(self, *, root: str, trace_id: str) -> ProjectProjection:
        with self._mutex:
            path = _canonical_directory(root)
            with _stable_directories(self._project_guard_paths(path)):
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
                record = {
                    "schemaVersion": "1.0",
                    "documentType": "research-observatory-project-lock",
                    "projectId": manifest["projectId"],
                    "instanceId": self._instance_id,
                    "processId": os.getpid(),
                    "heartbeatAt": _timestamp(),
                    "recoveryToken": secrets.token_hex(32),
                }
                self._write_lock(lock, record)
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
                except ProjectLifecycleProblem as error:
                    self._opened.pop(path, None)
                    try:
                        lock.unlink()
                    except OSError as rollback_error:
                        raise ProjectLifecycleProblem.rollback_failed() from rollback_error
                    raise error
                return self._projection(
                    path,
                    manifest=manifest,
                    profile=profile,
                    compatibility=compatibility,
                )

    def close(self, *, root: str, trace_id: str) -> ProjectProjection:
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
                        record = json.loads(lock.read_text(encoding="utf-8"))
                        status = lock.stat(follow_symlinks=False)
                        if (
                            not isinstance(record, dict)
                            or record.get("instanceId") != self._instance_id
                            or _redirect(lock)
                            or status.st_nlink != 1
                        ):
                            raise ProjectLifecycleProblem(
                                status=409,
                                code="RO-CORE-PROJECT-LOCK-CHANGED",
                                title="Project lock identity changed",
                                detail="The lock no longer belongs to this supervised Core instance.",
                                remediation="Do not break the lock; use the safe-open recovery workflow.",
                            )
                        lock.unlink()
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

    def _audit(self, root: Path, event: str, state: str, trace_id: str) -> None:
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
        _atomic_audit_append(root / "logs" / "project-lifecycle.jsonl", record)

    @staticmethod
    def _remove_staging(staging: Path) -> None:
        if staging.exists() and not _redirect(staging):
            with suppress(OSError):
                shutil.rmtree(staging)
