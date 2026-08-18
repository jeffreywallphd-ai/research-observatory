"""Project-scoped local adapter for the content-addressed object-store port."""

from __future__ import annotations

import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
import stat
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from .ports.object_store import (
    ObjectAccessDenied,
    ObjectConflict,
    ObjectCorrupt,
    ObjectIntegrityMismatch,
    ObjectNotFound,
    ObjectPutCommand,
    ObjectReferenced,
    ObjectStore,
    ObjectStoreProblem,
    RetentionClass,
    RightsStatus,
    StorageState,
    StoredObject,
    VerifiedObjectStream,
)
from .projects import ProjectLifecycleProblem, _stable_directories
from .storage import MAX_SAFE_INTEGER, CanonicalConnection, StorageProblem, open_canonical_database

_CHUNK_BYTES = 1024 * 1024
_MAX_SOURCE_CHUNK_BYTES = 4 * _CHUNK_BYTES
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9._-]{0,119}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")
_RIGHTS: frozenset[str] = frozenset(("allowed", "denied", "unknown", "not-applicable"))
_RETENTION: frozenset[str] = frozenset(("project-lifetime", "derived-rebuildable", "export-retained"))
_READABLE_RIGHTS: frozenset[str] = frozenset(("allowed", "not-applicable"))


def _bounded(exception: type[ObjectStoreProblem], message: str) -> ObjectStoreProblem:
    problem = exception(message)
    problem.__cause__ = None
    problem.__context__ = None
    problem.__suppress_context__ = True
    return problem


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _identity(path: Path) -> tuple[int, int]:
    status = path.stat(follow_symlinks=False)
    return (status.st_dev, status.st_ino)


def _redirect(path: Path) -> bool:
    try:
        return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())
    except OSError:
        return True


def _canonical_directory(path: Path, *, create: bool = False) -> Path:
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    candidate = path.resolve(strict=True)
    status = candidate.stat(follow_symlinks=False)
    if candidate != path or not stat.S_ISDIR(status.st_mode) or _redirect(path):
        raise _bounded(ObjectStoreProblem, "object-store directory is unavailable")
    return candidate


def _canonical_root(project_root: Path) -> tuple[Path, Path, Path, Path]:
    raw = Path(project_root)
    if not raw.is_absolute():
        raise _bounded(ObjectStoreProblem, "project object-store authority is invalid")
    root = _canonical_directory(raw)
    state = _canonical_directory(root / "state")
    objects = _canonical_directory(root / "objects")
    temporary = _canonical_directory(root / ".tmp")
    database = state / "project.sqlite3"
    if not database.is_file() or _redirect(database):
        raise _bounded(ObjectStoreProblem, "project object-store authority is unavailable")
    return root, state, objects, temporary


def _validate_sha256(value: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise _bounded(ObjectStoreProblem, "object identity is invalid")
    return value


def _validate_command(command: ObjectPutCommand) -> ObjectPutCommand:
    if not isinstance(command, ObjectPutCommand):
        raise _bounded(ObjectStoreProblem, "object metadata is invalid")
    if _MEDIA_TYPE.fullmatch(command.media_type) is None or len(command.media_type) > 200:
        raise _bounded(ObjectStoreProblem, "object media type is invalid")
    if command.rights_status not in _RIGHTS:
        raise _bounded(ObjectStoreProblem, "object rights state is invalid")
    if _IDENTIFIER.fullmatch(command.protection_profile) is None:
        raise _bounded(ObjectStoreProblem, "object protection profile is invalid")
    if command.retention_class not in _RETENTION:
        raise _bounded(ObjectStoreProblem, "object retention class is invalid")
    if command.expected_sha256 is not None:
        _validate_sha256(command.expected_sha256)
    # The canonical SQLite boundary performs exact UTC calendar validation.
    if not isinstance(command.created_at, str) or len(command.created_at) != 24:
        raise _bounded(ObjectStoreProblem, "object creation time is invalid")
    return command


def _validate_purpose(purpose: str) -> None:
    if not isinstance(purpose, str) or _IDENTIFIER.fullmatch(purpose) is None:
        raise _bounded(ObjectStoreProblem, "object access purpose is invalid")


def _opaque_name(project_id: str, object_sha256: str) -> str:
    return hmac.new(project_id.encode("ascii"), object_sha256.encode("ascii"), hashlib.sha256).hexdigest()


def _object_path(
    objects: Path,
    project_id: str,
    object_sha256: str,
    *,
    create: bool,
) -> tuple[Path, tuple[Path, Path]]:
    opaque = _opaque_name(project_id, object_sha256)
    first = _canonical_directory(objects / opaque[:2], create=create)
    second = _canonical_directory(first / opaque[2:4], create=create)
    return second / f"{opaque}.blob", (first, second)


def _staging_directory(temporary: Path) -> Path:
    return _canonical_directory(temporary / "object-store", create=True)


def _file_matches(path: Path, descriptor: int, identity: tuple[int, int]) -> bool:
    try:
        opened = os.fstat(descriptor)
        visible = path.stat(follow_symlinks=False)
        return (
            stat.S_ISREG(opened.st_mode)
            and stat.S_ISREG(visible.st_mode)
            and opened.st_nlink == 1
            and visible.st_nlink == 1
            and (opened.st_dev, opened.st_ino) == identity
            and (visible.st_dev, visible.st_ino) == identity
            and not _redirect(path)
        )
    except OSError:
        return False


def _open_read_locked(path: Path) -> io.FileIO:
    if os.name != "nt":
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        return os.fdopen(descriptor, "rb", buffering=0)

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
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    generic_read = 0x80000000
    file_share_read = 0x00000001
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_sequential_scan = 0x08000000
    invalid_handle = wintypes.HANDLE(-1).value
    handle = create_file(
        str(path),
        generic_read,
        file_share_read,
        None,
        open_existing,
        file_flag_open_reparse_point | file_flag_sequential_scan,
        None,
    )
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except BaseException:
        close_handle(handle)
        raise
    return os.fdopen(descriptor, "rb", buffering=0)


def _verified_reader(path: Path, expected_sha256: str, expected_length: int) -> io.FileIO:
    reader = _open_read_locked(path)
    try:
        status = os.fstat(reader.fileno())
        identity = (status.st_dev, status.st_ino)
        if not _file_matches(path, reader.fileno(), identity):
            raise OSError("object identity is not exclusive")
        digest = hashlib.sha256()
        length = 0
        while block := reader.read(_CHUNK_BYTES):
            digest.update(block)
            length += len(block)
        if digest.hexdigest() != expected_sha256 or length != expected_length:
            raise OSError("object integrity differs")
        if not _file_matches(path, reader.fileno(), identity):
            raise OSError("object identity changed")
        reader.seek(0)
        return reader
    except BaseException:
        reader.close()
        raise


@dataclass(slots=True)
class _ReaderEntry:
    reader: io.FileIO


class _ReaderRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._readers: dict[str, _ReaderEntry] = {}

    def register(self, reader: io.FileIO) -> str:
        with self._lock:
            while True:
                token = secrets.token_hex(32)
                if token not in self._readers:
                    self._readers[token] = _ReaderEntry(reader)
                    return token

    def read(self, token: str | None, size: int) -> bytes:
        with self._lock:
            entry = self._readers.get(token or "")
        if entry is None:
            raise ValueError("verified object stream is closed")
        return entry.reader.read(size)

    def close(self, token: str | None) -> None:
        if token is None:
            return
        with self._lock:
            entry = self._readers.pop(token, None)
        if entry is not None:
            entry.reader.close()


_READERS = _ReaderRegistry()


class _VerifiedObjectStream:
    __slots__ = ("__token",)

    def __init__(self, reader: io.FileIO) -> None:
        self.__token: str | None = _READERS.register(reader)

    def read(self, size: int = -1) -> bytes:
        if not isinstance(size, int) or size < -1:
            raise ValueError("size must be -1 or a non-negative integer")
        failure: ObjectStoreProblem | None = None
        result = b""
        try:
            result = _READERS.read(self.__token, size)
        except OSError:
            self.close()
            failure = _bounded(ObjectCorrupt, "verified object stream failed")
        if failure is not None:
            raise failure
        if result == b"":
            self.close()
        return result

    def close(self) -> None:
        token = self.__token
        self.__token = None
        _READERS.close(token)

    def __enter__(self) -> VerifiedObjectStream:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


@dataclass(slots=True)
class _StoreState:
    root: Path
    state: Path
    objects: Path
    temporary: Path
    database: Path
    project_id: str
    lock: threading.RLock


class _StoreRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, _StoreState] = {}
        self._project_locks: dict[str, threading.RLock] = {}

    def register(self, state: _StoreState) -> str:
        key = os.path.normcase(str(state.root))
        with self._lock:
            state.lock = self._project_locks.setdefault(key, threading.RLock())
            while True:
                token = secrets.token_hex(32)
                if token not in self._states:
                    self._states[token] = state
                    return token

    def state(self, token: str) -> _StoreState:
        with self._lock:
            state = self._states.get(token)
        if state is None:
            raise _bounded(ObjectStoreProblem, "object-store authority is unavailable")
        return state


_STORES = _StoreRegistry()


def _row_metadata(row: Any) -> StoredObject:
    return StoredObject(
        object_sha256=str(row[0]),
        byte_length=int(row[1]),
        media_type=str(row[2]),
        rights_status=cast(RightsStatus, str(row[3])),
        protection_profile=str(row[4]),
        retention_class=cast(RetentionClass, str(row[5])),
        storage_state=cast(StorageState, str(row[6])),
        created_at=str(row[7]),
        verified_at=None if row[8] is None else str(row[8]),
        reference_count=int(row[9]),
    )


_METADATA_SQL = """
    SELECT object.object_sha256, object.byte_length, object.media_type,
           object.rights_status, object.protection_profile, object.retention_class,
           object.storage_state, object.created_at, object.verified_at,
           (SELECT count(*) FROM documents AS document
             WHERE document.project_id = object.project_id
               AND document.object_sha256 = object.object_sha256) AS reference_count
    FROM object_records AS object
    WHERE object.project_id = ? AND object.object_sha256 = ?
"""


def _metadata(connection: CanonicalConnection, project_id: str, object_sha256: str) -> StoredObject | None:
    row = connection.execute(_METADATA_SQL, (project_id, object_sha256)).fetchone()
    return None if row is None else _row_metadata(row)


def _mark_quarantined(state: _StoreState, object_sha256: str) -> None:
    connection: CanonicalConnection | None = None
    try:
        connection = open_canonical_database(state.database, expected_project_id=state.project_id)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE object_records
               SET storage_state='quarantined', verified_at=NULL
             WHERE project_id=? AND object_sha256=? AND storage_state <> 'deleted'
            """,
            (state.project_id, object_sha256),
        )
        connection.execute("COMMIT")
    except OSError, sqlite3.Error, StorageProblem:
        if connection is not None and connection.in_transaction:
            with suppress(sqlite3.Error, StorageProblem):
                connection.execute("ROLLBACK")
    finally:
        if connection is not None:
            connection.close()


def _stream_to_staging(source: BinaryIO, staging: Path) -> tuple[Path, str, int]:
    destination = staging / f"{secrets.token_hex(24)}.partial"
    descriptor = -1
    succeeded = False
    try:
        descriptor = os.open(
            destination,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        identity = _identity(destination)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != identity
            or _redirect(destination)
        ):
            raise OSError("staging identity is invalid")
        digest = hashlib.sha256()
        length = 0
        while True:
            block = source.read(_CHUNK_BYTES)
            if block == b"":
                break
            if not isinstance(block, bytes) or len(block) > _MAX_SOURCE_CHUNK_BYTES:
                raise ValueError("object source returned an invalid chunk")
            length += len(block)
            if length > MAX_SAFE_INTEGER:
                raise ValueError("object exceeds the supported length")
            digest.update(block)
            view = memoryview(block)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("staging write failed")
                view = view[written:]
        os.fsync(descriptor)
        if not _file_matches(destination, descriptor, identity):
            raise OSError("staging identity changed")
        succeeded = True
        return destination, digest.hexdigest(), length
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not succeeded:
            with suppress(OSError):
                destination.unlink()


def _publish(staging: Path, destination: Path) -> bool:
    try:
        os.link(staging, destination, follow_symlinks=False)
        created = True
    except FileExistsError:
        created = False
    finally:
        with suppress(OSError):
            staging.unlink()
    return created


def _cleanup_staging(directory: Path) -> None:
    failure: ObjectStoreProblem | None = None
    try:
        candidates = tuple(directory.iterdir())
    except OSError:
        candidates = ()
        failure = _bounded(ObjectStoreProblem, "object staging inventory is unavailable")
    if failure is not None:
        raise failure
    for candidate in candidates:
        try:
            status = candidate.stat(follow_symlinks=False)
            if not (
                candidate.name.endswith(".partial")
                and stat.S_ISREG(status.st_mode)
                and status.st_nlink == 1
                and not _redirect(candidate)
            ):
                raise OSError("unexpected object staging entry")
            candidate.unlink()
        except OSError:
            failure = _bounded(ObjectStoreProblem, "abandoned object staging cannot be reconciled")
        if failure is not None:
            raise failure


class _LocalObjectStore:
    __slots__ = ("__token",)

    def __init__(self, state: _StoreState) -> None:
        self.__token = _STORES.register(state)

    def _state(self) -> _StoreState:
        return _STORES.state(self.__token)

    def metadata(self, object_sha256: str) -> StoredObject:
        digest = _validate_sha256(object_sha256)
        state = self._state()
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            connection: CanonicalConnection | None = None
            metadata_failure: ObjectStoreProblem | None = None
            try:
                connection = open_canonical_database(state.database, expected_project_id=state.project_id)
                result = _metadata(connection, state.project_id, digest)
            except sqlite3.Error, StorageProblem:
                result = None
                metadata_failure = _bounded(ObjectStoreProblem, "object metadata lookup failed")
            finally:
                if connection is not None:
                    connection.close()
        if metadata_failure is not None:
            raise metadata_failure
        if result is None:
            raise _bounded(ObjectNotFound, "object metadata is unavailable")
        return result

    def put(self, source: BinaryIO, command: ObjectPutCommand) -> StoredObject:
        command = _validate_command(command)
        if not hasattr(source, "read"):
            raise _bounded(ObjectStoreProblem, "object source is invalid")
        state = self._state()
        created_file = False
        destination: Path | None = None
        connection: CanonicalConnection | None = None
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            staging_directory = _staging_directory(state.temporary)
            with _stable_directories([state.root, state.state, state.objects, state.temporary, staging_directory]):
                staging_failure: ObjectStoreProblem | None = None
                staging: Path | None = None
                digest = ""
                length = 0
                try:
                    staging, digest, length = _stream_to_staging(source, staging_directory)
                except Exception:
                    staging_failure = _bounded(ObjectStoreProblem, "object source could not be staged")
                if staging_failure is not None or staging is None:
                    raise staging_failure or _bounded(ObjectStoreProblem, "object source could not be staged")
                if command.expected_sha256 is not None and digest != command.expected_sha256:
                    with suppress(OSError):
                        staging.unlink()
                    raise _bounded(ObjectIntegrityMismatch, "object content hash did not match")
                destination, buckets = _object_path(state.objects, state.project_id, digest, create=True)
                publication_failure: ObjectStoreProblem | None = None
                try:
                    with _stable_directories(
                        [state.root, state.state, state.objects, state.temporary, staging_directory, *buckets]
                    ):
                        created_file = _publish(staging, destination)
                        reader = _verified_reader(destination, digest, length)
                        reader.close()
                        connection = open_canonical_database(state.database, expected_project_id=state.project_id)
                        connection.execute("BEGIN IMMEDIATE")
                        existing = _metadata(connection, state.project_id, digest)
                        verified_at = max(command.created_at, _now())
                        if existing is None:
                            connection.execute(
                                """
                                INSERT INTO object_records (
                                    object_sha256, project_id, byte_length, media_type, rights_status,
                                    protection_profile, retention_class, storage_state, created_at, verified_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'available', ?, ?)
                                """,
                                (
                                    digest,
                                    state.project_id,
                                    length,
                                    command.media_type,
                                    command.rights_status,
                                    command.protection_profile,
                                    command.retention_class,
                                    command.created_at,
                                    verified_at,
                                ),
                            )
                        else:
                            immutable = (
                                existing.byte_length,
                                existing.media_type,
                                existing.rights_status,
                                existing.protection_profile,
                                existing.retention_class,
                            )
                            requested = (
                                length,
                                command.media_type,
                                command.rights_status,
                                command.protection_profile,
                                command.retention_class,
                            )
                            if immutable != requested:
                                raise ObjectConflict("object metadata conflicts with its content identity")
                            if existing.storage_state == "quarantined":
                                raise ObjectCorrupt("quarantined object requires explicit repair")
                            connection.execute(
                                """
                                UPDATE object_records
                                   SET storage_state='available', verified_at=?
                                 WHERE project_id=? AND object_sha256=?
                                """,
                                (verified_at, state.project_id, digest),
                            )
                        result = _metadata(connection, state.project_id, digest)
                        if result is None:
                            raise ObjectStoreProblem("object metadata publication failed")
                        connection.execute("COMMIT")
                        return result
                except ObjectStoreProblem:
                    if connection is not None and connection.in_transaction:
                        with suppress(sqlite3.Error, StorageProblem):
                            connection.execute("ROLLBACK")
                    if created_file and destination is not None:
                        with suppress(OSError):
                            destination.unlink()
                    raise
                except OSError, ProjectLifecycleProblem, sqlite3.Error, StorageProblem, ValueError:
                    if connection is not None and connection.in_transaction:
                        with suppress(sqlite3.Error, StorageProblem):
                            connection.execute("ROLLBACK")
                    if created_file and destination is not None:
                        with suppress(OSError):
                            destination.unlink()
                    publication_failure = _bounded(ObjectStoreProblem, "object publication failed")
                finally:
                    if connection is not None:
                        connection.close()
                if publication_failure is not None:
                    raise publication_failure

    def open(self, object_sha256: str, *, purpose: str) -> VerifiedObjectStream:
        digest = _validate_sha256(object_sha256)
        _validate_purpose(purpose)
        state = self._state()
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            metadata = self.metadata(digest)
            if metadata.storage_state == "quarantined":
                raise _bounded(ObjectCorrupt, "object is quarantined")
            if metadata.storage_state != "available":
                raise _bounded(ObjectNotFound, "object is unavailable")
            if metadata.rights_status not in _READABLE_RIGHTS:
                raise _bounded(ObjectAccessDenied, "object access is not authorized")
            path_failure: ObjectStoreProblem | None = None
            destination: Path | None = None
            buckets: tuple[Path, ...] = ()
            try:
                destination, buckets = _object_path(state.objects, state.project_id, digest, create=False)
            except OSError:
                _mark_quarantined(state, digest)
                path_failure = _bounded(ObjectCorrupt, "object integrity verification failed")
            if path_failure is not None or destination is None:
                raise path_failure or _bounded(ObjectCorrupt, "object integrity verification failed")
            integrity_failure: ObjectStoreProblem | None = None
            reader: io.FileIO | None = None
            try:
                with _stable_directories([state.root, state.objects, *buckets]):
                    reader = _verified_reader(destination, digest, metadata.byte_length)
            except OSError, ProjectLifecycleProblem:
                _mark_quarantined(state, digest)
                integrity_failure = _bounded(ObjectCorrupt, "object integrity verification failed")
            if integrity_failure is not None or reader is None:
                raise integrity_failure or _bounded(ObjectCorrupt, "object integrity verification failed")
            connection: CanonicalConnection | None = None
            state_failure: ObjectStoreProblem | None = None
            try:
                connection = open_canonical_database(state.database, expected_project_id=state.project_id)
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE object_records SET verified_at=?
                     WHERE project_id=? AND object_sha256=? AND storage_state='available'
                    """,
                    (max(metadata.created_at, _now()), state.project_id, digest),
                )
                connection.execute("COMMIT")
            except sqlite3.Error, StorageProblem:
                reader.close()
                if connection is not None and connection.in_transaction:
                    with suppress(sqlite3.Error, StorageProblem):
                        connection.execute("ROLLBACK")
                state_failure = _bounded(ObjectStoreProblem, "object verification state could not be recorded")
            finally:
                if connection is not None:
                    connection.close()
            if state_failure is not None:
                raise state_failure
            return _VerifiedObjectStream(reader)

    def delete(self, object_sha256: str) -> None:
        digest = _validate_sha256(object_sha256)
        state = self._state()
        connection: CanonicalConnection | None = None
        moved: Path | None = None
        destination: Path | None = None
        failure: ObjectStoreProblem | None = None
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            staging = _staging_directory(state.temporary)
            try:
                connection = open_canonical_database(state.database, expected_project_id=state.project_id)
                connection.execute("BEGIN IMMEDIATE")
                metadata = _metadata(connection, state.project_id, digest)
                if metadata is None:
                    raise ObjectNotFound("object is unavailable")
                if metadata.reference_count:
                    raise ObjectReferenced("referenced object cannot be deleted")
                if metadata.storage_state == "deleted":
                    connection.execute("ROLLBACK")
                    return
                destination, buckets = _object_path(state.objects, state.project_id, digest, create=False)
                with _stable_directories([state.root, state.state, state.objects, state.temporary, staging, *buckets]):
                    reader = _verified_reader(destination, digest, metadata.byte_length)
                    reader.close()
                    moved = staging / f"delete-{secrets.token_hex(24)}.partial"
                    os.rename(destination, moved)
                    connection.execute(
                        """
                        UPDATE object_records SET storage_state='deleted', verified_at=NULL
                         WHERE project_id=? AND object_sha256=?
                        """,
                        (state.project_id, digest),
                    )
                    connection.execute("COMMIT")
                    # Metadata no longer exposes the object after COMMIT. A cleanup
                    # failure can safely leave only an operation-scoped staging file,
                    # which the next adapter construction reconciles.
                    with suppress(OSError):
                        moved.unlink()
                    moved = None
            except ObjectStoreProblem:
                if connection is not None and connection.in_transaction:
                    with suppress(sqlite3.Error, StorageProblem):
                        connection.execute("ROLLBACK")
                raise
            except OSError, ProjectLifecycleProblem:
                if connection is not None and connection.in_transaction:
                    with suppress(sqlite3.Error, StorageProblem):
                        connection.execute("ROLLBACK")
                if moved is not None and destination is not None:
                    with suppress(OSError):
                        os.rename(moved, destination)
                _mark_quarantined(state, digest)
                failure = _bounded(ObjectCorrupt, "object delete verification failed")
            except sqlite3.Error, StorageProblem:
                if connection is not None and connection.in_transaction:
                    with suppress(sqlite3.Error, StorageProblem):
                        connection.execute("ROLLBACK")
                if moved is not None and destination is not None:
                    with suppress(OSError):
                        os.rename(moved, destination)
                failure = _bounded(ObjectStoreProblem, "object delete failed")
            finally:
                if connection is not None:
                    connection.close()
            if failure is not None:
                raise failure


def create_local_object_store(project_root: Path, project_id: str) -> ObjectStore:
    """Create the project-local adapter behind the dependency-neutral port."""

    path_failure: ObjectStoreProblem | None = None
    try:
        root, state_directory, objects, temporary = _canonical_root(Path(project_root))
    except OSError:
        path_failure = _bounded(ObjectStoreProblem, "project object-store authority is invalid")
        root = state_directory = objects = temporary = Path()
    if path_failure is not None:
        raise path_failure
    database = state_directory / "project.sqlite3"
    connection: CanonicalConnection | None = None
    authority_failure: ObjectStoreProblem | None = None
    try:
        connection = open_canonical_database(database, expected_project_id=project_id)
    except sqlite3.Error, StorageProblem:
        authority_failure = _bounded(ObjectStoreProblem, "project object-store authority is incompatible")
    finally:
        if connection is not None:
            connection.close()
    if authority_failure is not None:
        raise authority_failure
    staging = _staging_directory(temporary)
    with _stable_directories([root, state_directory, objects, temporary, staging]):
        _cleanup_staging(staging)
    return _LocalObjectStore(
        _StoreState(
            root=root,
            state=state_directory,
            objects=objects,
            temporary=temporary,
            database=database,
            project_id=project_id,
            lock=threading.RLock(),
        )
    )


__all__ = ["create_local_object_store"]
