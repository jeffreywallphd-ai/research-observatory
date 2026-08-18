"""Backup-first, forward-only migration authority for canonical SQLite databases."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import StaticPool

from research_observatory_core import storage
from research_observatory_core.migrations.versions import v0002_schema_history

_MANIFEST_DOCUMENT_TYPE = "research-observatory-sqlite-migration-recovery"
_FAILURE_DOCUMENT_TYPE = "research-observatory-sqlite-migration-failure"
_BACKUP_ROOT_NAME = "migration-backups"
_BACKUP_FILE_NAME = "project.sqlite3"
_MANIFEST_FILE_NAME = "recovery-manifest.json"
_FAILURE_FILE_NAME = "failure.json"


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """Detached dry-run result with no filesystem mutation."""

    source_schema_version: int
    target_schema_version: int
    migration_required: bool
    migration_ids: tuple[str, ...]
    source_schema_sha256: str
    target_schema_sha256: str


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Bounded successful migration result using project-relative paths only."""

    status: str
    source_schema_version: int
    target_schema_version: int
    migration_ids: tuple[str, ...]
    backup_relative_path: str | None
    recovery_manifest_relative_path: str | None
    backup_sha256: str | None
    recovery_manifest_sha256: str | None


class MigrationProblem(storage.StorageProblem):
    """Migration failed after a verified backup was retained when available."""

    def __init__(self, code: str, recovery_manifest_relative_path: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.recovery_manifest_relative_path = recovery_manifest_relative_path


def migration_framework_projection() -> dict[str, Any]:
    """Return the content-free migration authority advertised by Core diagnostics."""

    return {
        "backend": "alembic-1.18.5",
        "targetSchemaVersion": storage.DATABASE_SCHEMA_VERSION,
        "supportedSourceSchemaVersions": [storage.PREVIOUS_DATABASE_SCHEMA_VERSION],
        "revisions": list(_migration_ids(storage.PREVIOUS_DATABASE_SCHEMA_VERSION)),
        "backupRequired": True,
        "downgradeMode": "restore-verified-backup",
    }


@dataclass(frozen=True, slots=True)
class _SourceProfile:
    schema_version: int
    profile_sha256: str
    schema_sha256: str
    project_id: str


@dataclass(slots=True)
class _HeldFileAuthority:
    """One exclusively created file held without write/delete sharing."""

    path: Path
    descriptor: int
    identity: tuple[int, int]

    def validate(self) -> None:
        opened = os.fstat(self.descriptor)
        visible = self.path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or visible.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != self.identity
            or (visible.st_dev, visible.st_ino) != self.identity
            or storage._redirect(self.path)
        ):
            raise MigrationProblem("migration-backup-file-invalid")

    def read_bytes(self) -> bytes:
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        payload = bytearray()
        while block := os.read(self.descriptor, 1024 * 1024):
            payload.extend(block)
        return bytes(payload)

    def sha256(self) -> str:
        return _sha256_descriptor(self.descriptor)

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1


@dataclass(frozen=True, slots=True)
class _VerifiedBackup:
    directory: Path
    database: Path
    manifest: Path
    database_sha256: str
    manifest_sha256: str
    manifest_payload: dict[str, Any]
    database_authority: _HeldFileAuthority
    manifest_authority: _HeldFileAuthority

    def close(self) -> None:
        self.manifest_authority.close()
        self.database_authority.close()


_SUPPORTED_PROFILES = {
    storage.PREVIOUS_DATABASE_SCHEMA_VERSION: (
        storage.PREVIOUS_PROFILE_SHA256,
        storage.PREVIOUS_SCHEMA_SHA256,
    ),
    storage.DATABASE_SCHEMA_VERSION: (
        storage.EXPECTED_PROFILE_SHA256,
        storage.EXPECTED_SCHEMA_SHA256,
    ),
}


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while block := os.read(descriptor, 1024 * 1024):
        digest.update(block)
    return digest.hexdigest()


def _logical_database_sha256(connection: sqlite3.Connection) -> str:
    """Hash the complete deterministic logical database, not file layout."""

    digest = hashlib.sha256()
    for statement in connection.iterdump():
        payload = statement.encode("utf-8")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _relative_to_project(database: Path, path: Path) -> str:
    project_root = database.parent.parent if database.parent.name == "state" else database.parent
    return path.relative_to(project_root).as_posix()


def _source_profile(connection: sqlite3.Connection, expected_project_id: str) -> _SourceProfile:
    try:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        expected = _SUPPORTED_PROFILES.get(schema_version)
        metadata = connection.execute(
            """
            SELECT schema_version, database_profile, application_id, profile_sha256, schema_sha256
            FROM schema_metadata WHERE singleton=1
            """
        ).fetchone()
        project_rows = connection.execute("SELECT project_id FROM projects ORDER BY project_id").fetchall()
        schema_sha256 = storage._schema_fingerprint(connection)
        quick_check = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        foreign_key_violations = tuple(connection.execute("PRAGMA foreign_key_check"))
        history_rows: tuple[tuple[Any, ...], ...] = ()
        if schema_version == storage.DATABASE_SCHEMA_VERSION:
            history_rows = tuple(
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT migration_id, from_schema_version, to_schema_version,
                           applied_at, backup_manifest_sha256, source_schema_sha256,
                           target_schema_sha256, migration_tool
                    FROM schema_migrations ORDER BY to_schema_version, migration_id
                    """
                )
            )
    except sqlite3.Error as error:
        raise MigrationProblem("migration-source-profile-invalid") from error
    if expected is None:
        raise MigrationProblem("migration-source-version-unsupported")
    profile_sha256, expected_schema_sha256 = expected
    if (
        application_id != storage.APPLICATION_ID
        or metadata is None
        or tuple(metadata)
        != (
            schema_version,
            storage.DATABASE_PROFILE,
            storage.APPLICATION_ID,
            profile_sha256,
            expected_schema_sha256,
        )
        or schema_sha256 != expected_schema_sha256
        or [str(row[0]) for row in project_rows] != [expected_project_id]
        or quick_check != ("ok",)
        or foreign_key_violations
        or not _valid_migration_history(schema_version, history_rows)
    ):
        raise MigrationProblem("migration-source-profile-invalid")
    return _SourceProfile(schema_version, profile_sha256, schema_sha256, expected_project_id)


def _valid_migration_history(schema_version: int, rows: tuple[tuple[Any, ...], ...]) -> bool:
    if schema_version == storage.PREVIOUS_DATABASE_SCHEMA_VERSION:
        return not rows
    if not rows:
        return True  # Fresh initialization at the current schema has no applied migration.
    if len(rows) != 1:
        return False
    row = rows[0]
    try:
        storage._normalize_utc_millisecond(str(row[3]))
    except storage.StorageProblem:
        return False
    return (
        row[0] == v0002_schema_history.revision
        and row[1] == v0002_schema_history.source_schema_version
        and row[2] == v0002_schema_history.target_schema_version
        and isinstance(row[4], str)
        and len(row[4]) == 64
        and all(character in "0123456789abcdef" for character in row[4])
        and row[5] == storage.PREVIOUS_SCHEMA_SHA256
        and row[6] == storage.EXPECTED_SCHEMA_SHA256
        and row[7] == "alembic-1.18.5"
    )


def _migration_ids(source_version: int) -> tuple[str, ...]:
    if source_version == storage.DATABASE_SCHEMA_VERSION:
        return ()
    if source_version == v0002_schema_history.source_schema_version:
        if (
            v0002_schema_history.down_revision is not None
            or v0002_schema_history.target_schema_version != storage.DATABASE_SCHEMA_VERSION
            or v0002_schema_history.TARGET_SCHEMA_SHA256 != storage.EXPECTED_SCHEMA_SHA256
            or v0002_schema_history.TARGET_PROFILE_SHA256 != storage.EXPECTED_PROFILE_SHA256
        ):
            raise MigrationProblem("migration-registry-invalid")
        return (v0002_schema_history.revision,)
    raise MigrationProblem("migration-source-version-unsupported")


def plan_database_migration(path: Path, *, expected_project_id: str) -> MigrationPlan:
    """Inspect an exact supported schema and return a mutation-free migration plan."""

    expected_project_id, _ = storage._project_identity(expected_project_id)
    database = storage._canonical_database_path(Path(path), must_exist=True)
    connection = storage._connect_held(database)
    try:
        storage._configure_connection(connection, initialize=False)
        source = _source_profile(connection, expected_project_id)
        migration_ids = _migration_ids(source.schema_version)
        return MigrationPlan(
            source_schema_version=source.schema_version,
            target_schema_version=storage.DATABASE_SCHEMA_VERSION,
            migration_required=bool(migration_ids),
            migration_ids=migration_ids,
            source_schema_sha256=source.schema_sha256,
            target_schema_sha256=storage.EXPECTED_SCHEMA_SHA256,
        )
    finally:
        connection.close()


def _ensure_canonical_directory(path: Path, *, create: bool) -> tuple[int, int]:
    if create:
        with suppress(FileExistsError):
            path.mkdir(mode=0o700)
    try:
        status = path.stat(follow_symlinks=False)
        if not stat.S_ISDIR(status.st_mode) or storage._redirect(path) or path.resolve(strict=True) != path:
            raise MigrationProblem("migration-backup-path-invalid")
        return (status.st_dev, status.st_ino)
    except OSError as error:
        raise MigrationProblem("migration-backup-path-invalid") from error


@contextmanager
def _held_windows_paths(paths: tuple[tuple[Path, bool], ...], *, deny_writes: bool = False) -> Iterator[None]:
    if os.name != "nt":
        descriptors: list[int] = []
        try:
            for path, directory in paths:
                if not directory:
                    descriptors.append(os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)))
            yield
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
        return
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
    generic_read = 0x80000000
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_backup_semantics = 0x02000000
    invalid_handle = wintypes.HANDLE(-1).value
    handles: list[int] = []
    try:
        for path, directory in paths:
            flags = file_flag_open_reparse_point | (file_flag_backup_semantics if directory else 0)
            share = file_share_read if deny_writes and not directory else file_share_read | file_share_write
            handle = create_file(str(path), generic_read, share, None, open_existing, flags, None)
            if handle == invalid_handle:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
        yield
    except OSError as error:
        raise MigrationProblem("migration-backup-path-invalid") from error
    finally:
        for handle in reversed(handles):
            close_handle(handle)


def _exclusive_descriptor(path: Path) -> int:
    if os.name != "nt":
        return os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    import ctypes
    import msvcrt
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
    generic_read = 0x80000000
    generic_write = 0x40000000
    write_dac = 0x00040000
    create_new = 1
    file_attribute_normal = 0x00000080
    file_flag_open_reparse_point = 0x00200000
    invalid_handle = wintypes.HANDLE(-1).value
    handle = create_file(
        str(path),
        generic_read | generic_write | write_dac,
        0,
        None,
        create_new,
        file_attribute_normal | file_flag_open_reparse_point,
        None,
    )
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDWR | getattr(os, "O_BINARY", 0))
    except Exception:
        kernel32.CloseHandle(handle)
        raise


def _lock_descriptor_writes(descriptor: int) -> None:
    """Bridge an untrusted SQLite working file into an immutable copy step."""

    if os.name != "nt":
        import importlib

        fcntl = importlib.import_module("fcntl")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = (
            ("internal", ctypes.c_void_p),
            ("internal_high", ctypes.c_void_p),
            ("offset", wintypes.DWORD),
            ("offset_high", wintypes.DWORD),
            ("event", wintypes.HANDLE),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    lock_file = kernel32.LockFileEx
    lock_file.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    )
    lock_file.restype = wintypes.BOOL
    overlapped = Overlapped()
    if not lock_file(
        msvcrt.get_osfhandle(descriptor),
        0x00000002 | 0x00000001,
        0,
        0xFFFFFFFF,
        0xFFFFFFFF,
        ctypes.byref(overlapped),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _deny_future_file_writes(authority: _HeldFileAuthority) -> None:
    """Persist a Windows deny-write ACE without releasing held file identity."""

    authority.validate()
    if os.name != "nt":
        return

    import ctypes
    import msvcrt
    from ctypes import wintypes

    class SidAndAttributes(ctypes.Structure):
        _fields_ = (("sid", ctypes.c_void_p), ("attributes", wintypes.DWORD))

    class TokenUser(ctypes.Structure):
        _fields_ = (("user", SidAndAttributes),)

    class Trustee(ctypes.Structure):
        _fields_ = (
            ("multiple_trustee", ctypes.c_void_p),
            ("multiple_trustee_operation", wintypes.DWORD),
            ("trustee_form", wintypes.DWORD),
            ("trustee_type", wintypes.DWORD),
            ("name", wintypes.LPWSTR),
        )

    class ExplicitAccess(ctypes.Structure):
        _fields_ = (
            ("permissions", wintypes.DWORD),
            ("access_mode", wintypes.DWORD),
            ("inheritance", wintypes.DWORD),
            ("trustee", Trustee),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    open_process_token = advapi32.OpenProcessToken
    open_process_token.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    open_process_token.restype = wintypes.BOOL
    get_token_information = advapi32.GetTokenInformation
    get_token_information.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    get_token_information.restype = wintypes.BOOL
    get_security_info = advapi32.GetSecurityInfo
    get_security_info.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    get_security_info.restype = wintypes.DWORD
    set_entries_in_acl = advapi32.SetEntriesInAclW
    set_entries_in_acl.argtypes = (
        wintypes.ULONG,
        ctypes.POINTER(ExplicitAccess),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    set_entries_in_acl.restype = wintypes.DWORD
    set_security_info = advapi32.SetSecurityInfo
    set_security_info.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )
    set_security_info.restype = wintypes.DWORD
    local_free = kernel32.LocalFree
    local_free.argtypes = (ctypes.c_void_p,)
    local_free.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    security_descriptor = ctypes.c_void_p()
    updated_acl = ctypes.c_void_p()
    try:
        if not open_process_token(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        required = wintypes.DWORD()
        get_token_information(token, 1, None, 0, ctypes.byref(required))
        if not required.value:
            raise ctypes.WinError(ctypes.get_last_error())
        token_buffer = ctypes.create_string_buffer(required.value)
        if not get_token_information(token, 1, token_buffer, required, ctypes.byref(required)):
            raise ctypes.WinError(ctypes.get_last_error())
        current_sid = ctypes.cast(token_buffer, ctypes.POINTER(TokenUser)).contents.user.sid

        existing_acl = ctypes.c_void_p()
        status = get_security_info(
            msvcrt.get_osfhandle(authority.descriptor),
            1,
            0x00000004,
            None,
            None,
            ctypes.byref(existing_acl),
            None,
            ctypes.byref(security_descriptor),
        )
        if status:
            raise OSError(status, "GetSecurityInfo failed")
        write_rights = 0x0002 | 0x0004 | 0x0010 | 0x0100 | 0x00010000
        entry = ExplicitAccess(
            write_rights,
            3,
            0,
            Trustee(None, 0, 0, 1, ctypes.cast(current_sid, wintypes.LPWSTR)),
        )
        status = set_entries_in_acl(1, ctypes.byref(entry), existing_acl, ctypes.byref(updated_acl))
        if status:
            raise OSError(status, "SetEntriesInAclW failed")
        status = set_security_info(
            msvcrt.get_osfhandle(authority.descriptor),
            1,
            0x00000004,
            None,
            None,
            updated_acl,
            None,
        )
        if status:
            raise OSError(status, "SetSecurityInfo failed")
        authority.validate()
    except (OSError, ValueError) as error:
        raise MigrationProblem("migration-backup-protection-failed") from error
    finally:
        if updated_acl.value:
            local_free(updated_acl)
        if security_descriptor.value:
            local_free(security_descriptor)
        if token.value:
            close_handle(token)


def _create_exclusive_file(path: Path, payload: bytes) -> _HeldFileAuthority:
    descriptor: int | None = None
    try:
        descriptor = _exclusive_descriptor(path)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        status = os.fstat(descriptor)
        path_status = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_nlink != 1
            or (status.st_dev, status.st_ino) != (path_status.st_dev, path_status.st_ino)
            or storage._redirect(path)
        ):
            raise MigrationProblem("migration-backup-file-invalid")
        authority = _HeldFileAuthority(path, descriptor, (status.st_dev, status.st_ino))
        authority.validate()
        descriptor = None
        return authority
    except (OSError, ValueError) as error:
        raise MigrationProblem("migration-backup-file-invalid") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _copy_to_exclusive_file(path: Path, source_descriptor: int) -> _HeldFileAuthority:
    authority = _create_exclusive_file(path, b"")
    try:
        os.lseek(source_descriptor, 0, os.SEEK_SET)
        while block := os.read(source_descriptor, 1024 * 1024):
            offset = 0
            while offset < len(block):
                offset += os.write(authority.descriptor, block[offset:])
        os.fsync(authority.descriptor)
        authority.validate()
        return authority
    except Exception:
        authority.close()
        raise


def _create_verified_backup(
    database: Path,
    source_profile: _SourceProfile,
    expected_project_id: str,
    migration_ids: tuple[str, ...],
    started_at: str,
) -> _VerifiedBackup:
    backup_root = database.parent / _BACKUP_ROOT_NAME
    backup_root_identity = _ensure_canonical_directory(backup_root, create=True)
    with _held_windows_paths(((database.parent, True), (backup_root, True))):
        if _ensure_canonical_directory(backup_root, create=False) != backup_root_identity:
            raise MigrationProblem("migration-backup-path-invalid")
        attempt_id = secrets.token_hex(16)
        attempt = backup_root / f"v{source_profile.schema_version}-to-v{storage.DATABASE_SCHEMA_VERSION}-{attempt_id}"
        try:
            attempt.mkdir(mode=0o700)
        except OSError as error:
            raise MigrationProblem("migration-backup-path-invalid") from error
        attempt_identity = _ensure_canonical_directory(attempt, create=False)
        with _held_windows_paths(((attempt, True),)):
            if _ensure_canonical_directory(attempt, create=False) != attempt_identity:
                raise MigrationProblem("migration-backup-path-invalid")
            working = attempt / f".working-{secrets.token_hex(16)}.sqlite3"
            working_descriptor = os.open(
                working,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
            backup_authority: _HeldFileAuthority | None = None
            manifest_authority: _HeldFileAuthority | None = None
            target: sqlite3.Connection | None = None
            backup_source: sqlite3.Connection | None = None
            try:
                created = os.fstat(working_descriptor)
                visible = working.stat(follow_symlinks=False)
                if (
                    not stat.S_ISREG(created.st_mode)
                    or created.st_nlink != 1
                    or (created.st_dev, created.st_ino) != (visible.st_dev, visible.st_ino)
                    or storage._redirect(working)
                ):
                    raise MigrationProblem("migration-backup-file-invalid")
                working_identity = (created.st_dev, created.st_ino)
                backup_source = storage._connect_held(database)
                target = sqlite3.connect(working.as_uri() + "?mode=rw", uri=True, autocommit=True)
                storage._configure_connection(backup_source, initialize=False)
                if _source_profile(backup_source, expected_project_id) != source_profile:
                    raise MigrationProblem("migration-source-changed-before-backup")
                backup_source.set_authorizer(storage._initialization_authorizer)
                passive = tuple(
                    int(value) for value in backup_source.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                )
                if passive[0] != 0 or passive[1] != passive[2]:
                    raise MigrationProblem("migration-checkpoint-incomplete")
                backup_source.backup(target, pages=256, sleep=0.01)
                target_checkpoint = tuple(
                    int(value) for value in target.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                )
                if target_checkpoint != (0, 0, 0):
                    raise MigrationProblem("migration-backup-verification-failed")
                os.fsync(working_descriptor)
                working_sha256_before = _sha256_descriptor(working_descriptor)
                if _logical_database_sha256(target) != _logical_database_sha256(backup_source):
                    raise MigrationProblem("migration-backup-verification-failed")
                # Keep the exclusive creation descriptor continuously open
                # while SQLite releases its writer handle, then lock that same
                # file identity. Raw hashes on both sides of the handoff detect
                # any compatible-content mutation in the lock transition.
                target.close()
                target = None
                _lock_descriptor_writes(working_descriptor)
                locked = os.fstat(working_descriptor)
                locked_visible = working.stat(follow_symlinks=False)
                if (
                    locked.st_nlink != 1
                    or locked_visible.st_nlink != 1
                    or (locked.st_dev, locked.st_ino) != working_identity
                    or (locked_visible.st_dev, locked_visible.st_ino) != working_identity
                    or storage._redirect(working)
                ):
                    raise MigrationProblem("migration-backup-file-invalid")
                if _sha256_descriptor(working_descriptor) != working_sha256_before:
                    raise MigrationProblem("migration-backup-changed-before-lock")
                backup = attempt / _BACKUP_FILE_NAME
                backup_authority = _copy_to_exclusive_file(backup, working_descriptor)
                if backup_authority.sha256() != working_sha256_before:
                    raise MigrationProblem("migration-backup-copy-invalid")
                backup_authority.validate()
                backup_sha256 = working_sha256_before
                backup_size = os.fstat(backup_authority.descriptor).st_size
                manifest_payload: dict[str, Any] = {
                    "schemaVersion": "1.0",
                    "documentType": _MANIFEST_DOCUMENT_TYPE,
                    "attemptId": attempt_id,
                    "createdAt": started_at,
                    "status": "backup-verified",
                    "databaseRelativePath": _relative_to_project(database, database),
                    "projectId": expected_project_id,
                    "sourceSchemaVersion": source_profile.schema_version,
                    "targetSchemaVersion": storage.DATABASE_SCHEMA_VERSION,
                    "migrationIds": list(migration_ids),
                    "sourceSchemaSha256": source_profile.schema_sha256,
                    "targetSchemaSha256": storage.EXPECTED_SCHEMA_SHA256,
                    "checkpoint": {
                        "mode": "passive-under-writer-reservation",
                        "logFrames": passive[1],
                        "checkpointedFrames": passive[2],
                    },
                    "backup": {
                        "relativePath": _relative_to_project(database, backup),
                        "sha256": backup_sha256,
                        "sizeBytes": backup_size,
                        "quickCheck": "ok",
                    },
                }
                manifest = attempt / _MANIFEST_FILE_NAME
                encoded = _json_bytes(manifest_payload)
                manifest_authority = _create_exclusive_file(manifest, encoded)
                manifest_authority.validate()
                if manifest_authority.read_bytes() != encoded:
                    raise MigrationProblem("migration-backup-manifest-invalid")
                manifest_sha256 = hashlib.sha256(encoded).hexdigest()
                # Persist deny-write/delete ACEs while each exclusive creation
                # handle is still open. The post-ACL identity/link validation
                # catches aliases created before protection; afterward Windows
                # denies new hardlinks and content changes even after return.
                _deny_future_file_writes(backup_authority)
                _deny_future_file_writes(manifest_authority)
                verified = _VerifiedBackup(
                    directory=attempt,
                    database=backup,
                    manifest=manifest,
                    database_sha256=backup_sha256,
                    manifest_sha256=manifest_sha256,
                    manifest_payload=manifest_payload,
                    database_authority=backup_authority,
                    manifest_authority=manifest_authority,
                )
                _assert_verified_backup(verified)
                backup_authority = None
                manifest_authority = None
                return verified
            except sqlite3.Error as error:
                raise MigrationProblem("migration-backup-failed") from error
            finally:
                if target is not None:
                    target.close()
                if backup_source is not None:
                    backup_source.close()
                os.close(working_descriptor)
                with suppress(OSError):
                    working.unlink()
                if manifest_authority is not None:
                    manifest_authority.close()
                if backup_authority is not None:
                    backup_authority.close()


def _assert_verified_backup(verified: _VerifiedBackup) -> None:
    verified.database_authority.validate()
    verified.manifest_authority.validate()
    if (
        verified.database_authority.sha256() != verified.database_sha256
        or verified.manifest_authority.sha256() != verified.manifest_sha256
        or verified.manifest_authority.read_bytes() != _json_bytes(verified.manifest_payload)
    ):
        raise MigrationProblem("migration-backup-changed-before-execution")


def _write_failure(verified: _VerifiedBackup, code: str) -> None:
    payload = {
        "schemaVersion": "1.0",
        "documentType": _FAILURE_DOCUMENT_TYPE,
        "attemptId": verified.manifest_payload["attemptId"],
        "status": "migration-failed",
        "failureCode": code,
        "recoveryManifestSha256": verified.manifest_sha256,
        "backupSha256": verified.database_sha256,
    }
    destination = verified.directory / _FAILURE_FILE_NAME
    # The immutable verified backup manifest remains the recovery authority if
    # publishing the optional bounded failure record is itself unavailable.
    with suppress(MigrationProblem):
        authority = _create_exclusive_file(destination, _json_bytes(payload))
        authority.close()


def _run_v1_to_v2(
    sqlalchemy_connection: Connection,
    *,
    applied_at: str,
    backup_manifest_sha256: str,
) -> None:
    context = MigrationContext.configure(sqlalchemy_connection, opts={"transactional_ddl": False})
    operations = Operations(context)
    v0002_schema_history.apply(
        operations,
        {
            "migration_id": v0002_schema_history.revision,
            "applied_at": applied_at,
            "backup_manifest_sha256": backup_manifest_sha256,
            "source_schema_sha256": storage.PREVIOUS_SCHEMA_SHA256,
            "target_schema_sha256": storage.EXPECTED_SCHEMA_SHA256,
            "targetSchemaSha256": storage.EXPECTED_SCHEMA_SHA256,
            "targetProfileSha256": storage.EXPECTED_PROFILE_SHA256,
        },
    )


def migrate_database(path: Path, *, expected_project_id: str) -> MigrationResult:
    """Migrate one supported database after retaining an exact verified backup."""

    expected_project_id, _ = storage._project_identity(expected_project_id)
    database = storage._canonical_database_path(Path(path), must_exist=True)
    if database.parent.name != "state":
        raise MigrationProblem("migration-database-location-invalid")
    initial_plan = plan_database_migration(database, expected_project_id=expected_project_id)
    if not initial_plan.migration_required:
        return MigrationResult(
            status="current",
            source_schema_version=initial_plan.source_schema_version,
            target_schema_version=initial_plan.target_schema_version,
            migration_ids=(),
            backup_relative_path=None,
            recovery_manifest_relative_path=None,
            backup_sha256=None,
            recovery_manifest_sha256=None,
        )

    started_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    connection = storage._connect_held(database)
    verified_backup: _VerifiedBackup | None = None
    engine = create_engine("sqlite://", creator=lambda: connection, poolclass=StaticPool)
    sqlalchemy_connection: Connection | None = None
    try:
        storage._configure_connection(connection, initialize=False)
        source = _source_profile(connection, expected_project_id)
        if source.schema_version != initial_plan.source_schema_version:
            raise MigrationProblem("migration-source-changed-before-lock")
        connection.set_authorizer(storage._initialization_authorizer)
        checkpoint = tuple(int(value) for value in connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise MigrationProblem("migration-checkpoint-incomplete")
        sqlalchemy_connection = engine.connect()
        connection.execute("BEGIN IMMEDIATE")
        verified_backup = _create_verified_backup(
            database,
            source,
            expected_project_id,
            initial_plan.migration_ids,
            started_at,
        )
        backup_relative_path = _relative_to_project(database, verified_backup.database)
        manifest_relative_path = _relative_to_project(database, verified_backup.manifest)
        _assert_verified_backup(verified_backup)
        _run_v1_to_v2(
            sqlalchemy_connection,
            applied_at=started_at,
            backup_manifest_sha256=verified_backup.manifest_sha256,
        )
        connection.set_authorizer(storage._canonical_authorizer)
        errors = storage._schema_profile_errors(connection, expected_project_id)
        integrity = storage.database_integrity_report(connection, expected_project_id=expected_project_id)
        if errors or not integrity.ok:
            raise MigrationProblem("migration-target-verification-failed")
        # The final backup/manifest identity check occurs immediately before
        # commit while both exclusive creation handles remain held.
        _assert_verified_backup(verified_backup)
        connection.execute("COMMIT")
        return MigrationResult(
            status="migrated",
            source_schema_version=source.schema_version,
            target_schema_version=storage.DATABASE_SCHEMA_VERSION,
            migration_ids=initial_plan.migration_ids,
            backup_relative_path=backup_relative_path,
            recovery_manifest_relative_path=manifest_relative_path,
            backup_sha256=verified_backup.database_sha256,
            recovery_manifest_sha256=verified_backup.manifest_sha256,
        )
    except MigrationProblem as error:
        if connection.in_transaction:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
        if verified_backup is not None:
            _write_failure(verified_backup, error.code)
            error.recovery_manifest_relative_path = _relative_to_project(database, verified_backup.manifest)
        raise
    except Exception as error:
        if connection.in_transaction:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
        problem = MigrationProblem("migration-execution-failed")
        if verified_backup is not None:
            _write_failure(verified_backup, problem.code)
            problem.recovery_manifest_relative_path = _relative_to_project(database, verified_backup.manifest)
        raise problem from error
    finally:
        if sqlalchemy_connection is not None:
            with suppress(Exception):
                sqlalchemy_connection.close()
        with suppress(Exception):
            engine.dispose()
        with suppress(Exception):
            connection.close()
        if verified_backup is not None:
            with suppress(Exception):
                verified_backup.close()
