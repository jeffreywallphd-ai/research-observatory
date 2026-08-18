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
import struct
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from nacl import bindings as sodium
from nacl.exceptions import CryptoError

from .ports.object_store import (
    ObjectAccessDenied,
    ObjectBusy,
    ObjectConflict,
    ObjectCorrupt,
    ObjectIntegrityMismatch,
    ObjectKeyUnavailable,
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
from .ports.object_store_keys import ObjectMasterKey, ObjectMasterKeyProvider
from .projects import ProjectLifecycleProblem, _stable_directories
from .storage import (
    MAX_SAFE_INTEGER,
    CanonicalConnection,
    StorageProblem,
    _open_thread_transferable_canonical_database,
    open_canonical_database,
)

_CHUNK_BYTES = 1024 * 1024
_MAX_SOURCE_CHUNK_BYTES = 4 * _CHUNK_BYTES
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9._-]{0,119}$")
_KEY_VERSION = re.compile(r"^[a-z][a-z0-9.-]{0,119}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")
_RIGHTS: frozenset[str] = frozenset(("allowed", "denied", "unknown", "not-applicable"))
_RETENTION: frozenset[str] = frozenset(("project-lifetime", "derived-rebuildable", "export-retained"))
_READABLE_RIGHTS: frozenset[str] = frozenset(("allowed", "not-applicable"))
_PLAINTEXT_FIXTURE = "plaintext-fixture-v1"
_ENCRYPTED_ENVELOPE = "secretstream-xchacha20poly1305-v1"
_ENCRYPTED_PROFILE = "project-encrypted-v1"
_ENVELOPE_MAGIC = b"ROO1"
_FRAME_LENGTH = struct.Struct(">I")
_STREAM_AAD_PREFIX = b"research-observatory-object-stream-v1\0"
_WRAP_AAD_PREFIX = b"research-observatory-object-key-v1\0"


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
    if (
        not isinstance(command.media_type, str)
        or _MEDIA_TYPE.fullmatch(command.media_type) is None
        or len(command.media_type) > 200
    ):
        raise _bounded(ObjectStoreProblem, "object media type is invalid")
    if command.rights_status not in _RIGHTS:
        raise _bounded(ObjectStoreProblem, "object rights state is invalid")
    if not isinstance(command.protection_profile, str) or _IDENTIFIER.fullmatch(command.protection_profile) is None:
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


def _validate_key_version(value: str) -> str:
    if (
        not isinstance(value, str)
        or _KEY_VERSION.fullmatch(value) is None
        or ".." in value
        or "--" in value
        or value.endswith((".", "-"))
    ):
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    return value


def _master_key(
    provider: ObjectMasterKeyProvider | None,
    *,
    key_version: str | None = None,
) -> ObjectMasterKey:
    if provider is None:
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    try:
        candidate = (
            provider.active_object_master_key() if key_version is None else provider.object_master_key(key_version)
        )
    except Exception:
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable") from None
    if candidate is None or not isinstance(candidate, ObjectMasterKey):
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    version = _validate_key_version(candidate.key_version)
    if key_version is not None and version != key_version:
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    if (
        not isinstance(candidate.key_bytes, bytes)
        or len(candidate.key_bytes) != sodium.crypto_secretstream_xchacha20poly1305_KEYBYTES
    ):
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    return candidate


def _frame_aad(project_id: str, frame_index: int) -> bytes:
    return _STREAM_AAD_PREFIX + project_id.encode("ascii") + frame_index.to_bytes(8, "big")


def _wrap_aad(project_id: str, object_sha256: str, key_version: str) -> bytes:
    return (
        _WRAP_AAD_PREFIX
        + project_id.encode("ascii")
        + b"\0"
        + object_sha256.encode("ascii")
        + b"\0"
        + key_version.encode("ascii")
    )


@dataclass(frozen=True, slots=True)
class _EnvelopeMetadata:
    envelope_version: str
    key_version: str | None
    wrapped_key: str | None
    wrap_nonce: str | None
    ciphertext_byte_length: int


def _read_source_block(source: BinaryIO) -> bytes:
    block = source.read(_CHUNK_BYTES)
    if not isinstance(block, bytes) or len(block) > _MAX_SOURCE_CHUNK_BYTES:
        raise ValueError("object source returned an invalid chunk")
    return block


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("staging write failed")
        view = view[written:]


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


def _read_exact(reader: io.FileIO, size: int) -> bytes:
    payload = bytearray()
    while len(payload) < size:
        block = reader.read(size - len(payload))
        if block == b"":
            raise OSError("encrypted object is truncated")
        payload.extend(block)
    return bytes(payload)


def _unwrap_data_key(
    provider: ObjectMasterKeyProvider | None,
    *,
    project_id: str,
    object_sha256: str,
    key_version: str | None,
    wrapped_key: str | None,
    wrap_nonce: str | None,
) -> bytes:
    if key_version is None or wrapped_key is None or wrap_nonce is None:
        raise _bounded(ObjectCorrupt, "object encryption metadata is invalid")
    version = _validate_key_version(key_version)
    try:
        wrapped = bytes.fromhex(wrapped_key)
        nonce = bytes.fromhex(wrap_nonce)
    except ValueError:
        raise _bounded(ObjectCorrupt, "object encryption metadata is invalid") from None
    if (
        len(wrapped)
        != sodium.crypto_secretstream_xchacha20poly1305_KEYBYTES + sodium.crypto_aead_xchacha20poly1305_ietf_ABYTES
        or len(nonce) != sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES
    ):
        raise _bounded(ObjectCorrupt, "object encryption metadata is invalid")
    master = _master_key(provider, key_version=version)
    try:
        data_key = sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
            wrapped,
            _wrap_aad(project_id, object_sha256, version),
            nonce,
            master.key_bytes,
        )
    except CryptoError:
        # A present key version with unusable bytes is operationally equivalent
        # to key loss. Preserve the object for recovery instead of quarantining it.
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable") from None
    if len(data_key) != sodium.crypto_secretstream_xchacha20poly1305_KEYBYTES:
        raise _bounded(ObjectCorrupt, "object encryption metadata is invalid")
    return data_key


def _start_pull(reader: io.FileIO, data_key: bytes) -> sodium.crypto_secretstream_xchacha20poly1305_state:
    if _read_exact(reader, len(_ENVELOPE_MAGIC)) != _ENVELOPE_MAGIC:
        raise OSError("encrypted object header is invalid")
    header = _read_exact(reader, sodium.crypto_secretstream_xchacha20poly1305_HEADERBYTES)
    stream_state = sodium.crypto_secretstream_xchacha20poly1305_state()
    try:
        sodium.crypto_secretstream_xchacha20poly1305_init_pull(stream_state, header, data_key)
    except CryptoError:
        raise OSError("encrypted object header is invalid") from None
    return stream_state


def _pull_frame(
    reader: io.FileIO,
    stream_state: sodium.crypto_secretstream_xchacha20poly1305_state,
    *,
    project_id: str,
    frame_index: int,
) -> tuple[bytes, bool]:
    frame_size = _FRAME_LENGTH.unpack(_read_exact(reader, _FRAME_LENGTH.size))[0]
    if not (
        sodium.crypto_secretstream_xchacha20poly1305_ABYTES
        <= frame_size
        <= _MAX_SOURCE_CHUNK_BYTES + sodium.crypto_secretstream_xchacha20poly1305_ABYTES
    ):
        raise OSError("encrypted object frame is invalid")
    ciphertext = _read_exact(reader, frame_size)
    try:
        message, tag = sodium.crypto_secretstream_xchacha20poly1305_pull(
            stream_state,
            ciphertext,
            ad=_frame_aad(project_id, frame_index),
        )
    except CryptoError:
        raise OSError("encrypted object authentication failed") from None
    if tag == sodium.crypto_secretstream_xchacha20poly1305_TAG_FINAL:
        if reader.read(1) != b"":
            raise OSError("encrypted object has trailing content")
        return message, True
    if tag != sodium.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE or not message:
        raise OSError("encrypted object frame tag is invalid")
    return message, False


def _verify_encrypted_payload(
    reader: io.FileIO,
    data_key: bytes,
    *,
    project_id: str,
    expected_sha256: str,
    expected_length: int,
) -> None:
    stream_state = _start_pull(reader, data_key)
    digest = hashlib.sha256()
    length = 0
    frame_index = 0
    while True:
        message, final = _pull_frame(
            reader,
            stream_state,
            project_id=project_id,
            frame_index=frame_index,
        )
        digest.update(message)
        length += len(message)
        if length > MAX_SAFE_INTEGER:
            raise OSError("encrypted object plaintext is too large")
        if final:
            break
        frame_index += 1
    if digest.hexdigest() != expected_sha256 or length != expected_length:
        raise OSError("encrypted object plaintext identity differs")


class _EncryptedReader:
    __slots__ = (
        "_buffer",
        "_finished",
        "_frame_index",
        "_identity",
        "_path",
        "_project_id",
        "_reader",
        "_state",
    )

    def __init__(
        self,
        reader: io.FileIO,
        data_key: bytes,
        *,
        project_id: str,
        path: Path,
        identity: tuple[int, int],
    ) -> None:
        self._reader = reader
        self._path = path
        self._identity = identity
        self._project_id = project_id
        self._state = _start_pull(reader, data_key)
        self._frame_index = 0
        self._buffer = bytearray()
        self._finished = False

    def _next(self) -> None:
        if self._finished:
            return
        message, final = _pull_frame(
            self._reader,
            self._state,
            project_id=self._project_id,
            frame_index=self._frame_index,
        )
        self._buffer.extend(message)
        self._finished = final
        if not final:
            self._frame_index += 1

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        while not self._finished and (size < 0 or len(self._buffer) < size):
            self._next()
        if size < 0:
            result = bytes(self._buffer)
            self._buffer.clear()
            return result
        result = bytes(self._buffer[:size])
        del self._buffer[:size]
        return result

    def close(self) -> None:
        self._buffer.clear()
        self._reader.close()

    def matches(self) -> bool:
        return _file_matches(self._path, self._reader.fileno(), self._identity)


def _verified_encrypted_reader(
    path: Path,
    *,
    project_id: str,
    object_sha256: str,
    byte_length: int,
    ciphertext_byte_length: int,
    key_version: str | None,
    wrapped_key: str | None,
    wrap_nonce: str | None,
    key_provider: ObjectMasterKeyProvider | None,
) -> _EncryptedReader:
    data_key = _unwrap_data_key(
        key_provider,
        project_id=project_id,
        object_sha256=object_sha256,
        key_version=key_version,
        wrapped_key=wrapped_key,
        wrap_nonce=wrap_nonce,
    )
    reader = _open_read_locked(path)
    try:
        status = os.fstat(reader.fileno())
        identity = (status.st_dev, status.st_ino)
        if status.st_size != ciphertext_byte_length or not _file_matches(path, reader.fileno(), identity):
            raise OSError("encrypted object identity differs")
        _verify_encrypted_payload(
            reader,
            data_key,
            project_id=project_id,
            expected_sha256=object_sha256,
            expected_length=byte_length,
        )
        if not _file_matches(path, reader.fileno(), identity):
            raise OSError("encrypted object identity changed")
        reader.seek(0)
        return _EncryptedReader(
            reader,
            data_key,
            project_id=project_id,
            path=path,
            identity=identity,
        )
    except BaseException:
        reader.close()
        raise


def _held_reader_matches(path: Path, reader: Any) -> bool:
    if isinstance(reader, _EncryptedReader):
        return reader.matches()
    status = os.fstat(reader.fileno())
    return _file_matches(path, reader.fileno(), (status.st_dev, status.st_ino))


@dataclass(slots=True)
class _ReaderEntry:
    reader: Any
    connection: CanonicalConnection
    project_id: str
    object_sha256: str


class _ReaderRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._readers: dict[str, _ReaderEntry] = {}

    def register(
        self,
        reader: Any,
        connection: CanonicalConnection,
        project_id: str,
        object_sha256: str,
    ) -> str:
        with self._lock:
            while True:
                token = secrets.token_hex(32)
                if token not in self._readers:
                    self._readers[token] = _ReaderEntry(reader, connection, project_id, object_sha256)
                    return token

    def in_use(self, project_id: str, object_sha256: str) -> bool:
        with self._lock:
            return any(
                entry.project_id == project_id and entry.object_sha256 == object_sha256
                for entry in self._readers.values()
            )

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
            try:
                if entry.connection.in_transaction:
                    entry.connection.execute("COMMIT")
            except sqlite3.Error, StorageProblem:
                if entry.connection.in_transaction:
                    with suppress(sqlite3.Error, StorageProblem):
                        entry.connection.execute("ROLLBACK")
            finally:
                entry.reader.close()
                entry.connection.close()


_READERS = _ReaderRegistry()


class _VerifiedObjectStream:
    __slots__ = ("__token",)

    def __init__(
        self,
        reader: Any,
        connection: CanonicalConnection,
        project_id: str,
        object_sha256: str,
    ) -> None:
        self.__token: str | None = _READERS.register(reader, connection, project_id, object_sha256)

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
    key_provider: ObjectMasterKeyProvider | None
    allow_plaintext_fixture: bool
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
        envelope_version=str(row[10]),
        key_version=None if row[11] is None else str(row[11]),
        ciphertext_byte_length=int(row[12]),
    )


_METADATA_SQL = """
    SELECT object.object_sha256, object.byte_length, object.media_type,
           object.rights_status, object.protection_profile, object.retention_class,
           object.storage_state, object.created_at, object.verified_at,
           (SELECT count(*) FROM documents AS document
             WHERE document.project_id = object.project_id
               AND document.object_sha256 = object.object_sha256) AS reference_count,
           object.envelope_version, object.key_version, object.ciphertext_byte_length
    FROM object_records AS object
    WHERE object.project_id = ? AND object.object_sha256 = ?
"""


def _metadata(connection: CanonicalConnection, project_id: str, object_sha256: str) -> StoredObject | None:
    row = connection.execute(_METADATA_SQL, (project_id, object_sha256)).fetchone()
    return None if row is None else _row_metadata(row)


def _encryption_material(
    connection: CanonicalConnection,
    project_id: str,
    object_sha256: str,
) -> tuple[str | None, str | None]:
    row = connection.execute(
        """
        SELECT wrapped_key, wrap_nonce FROM object_records
         WHERE project_id=? AND object_sha256=?
        """,
        (project_id, object_sha256),
    ).fetchone()
    if row is None:
        raise ObjectNotFound("object encryption metadata is unavailable")
    return (
        None if row[0] is None else str(row[0]),
        None if row[1] is None else str(row[1]),
    )


def _verified_stored_reader(
    state: _StoreState,
    connection: CanonicalConnection,
    path: Path,
    metadata: StoredObject,
) -> Any:
    if metadata.envelope_version == _PLAINTEXT_FIXTURE:
        if metadata.protection_profile != _PLAINTEXT_FIXTURE or not state.allow_plaintext_fixture:
            raise _bounded(ObjectAccessDenied, "plaintext object fixtures are disabled")
        return _verified_reader(path, metadata.object_sha256, metadata.byte_length)
    if metadata.envelope_version != _ENCRYPTED_ENVELOPE or metadata.protection_profile != _ENCRYPTED_PROFILE:
        raise _bounded(ObjectCorrupt, "object encryption profile is invalid")
    wrapped_key, wrap_nonce = _encryption_material(
        connection,
        state.project_id,
        metadata.object_sha256,
    )
    return _verified_encrypted_reader(
        path,
        project_id=state.project_id,
        object_sha256=metadata.object_sha256,
        byte_length=metadata.byte_length,
        ciphertext_byte_length=metadata.ciphertext_byte_length,
        key_version=metadata.key_version,
        wrapped_key=wrapped_key,
        wrap_nonce=wrap_nonce,
        key_provider=state.key_provider,
    )


def _publication_state(
    state: _StoreState,
    digest: str,
    length: int,
    command: ObjectPutCommand,
) -> tuple[str, StoredObject | None]:
    connection: CanonicalConnection | None = None
    try:
        connection = open_canonical_database(state.database, expected_project_id=state.project_id)
        result = _metadata(connection, state.project_id, digest)
    except sqlite3.Error, StorageProblem:
        return ("unknown", None)
    finally:
        if connection is not None:
            connection.close()
    if result is None:
        return ("absent", None)
    expected = (
        length,
        command.media_type,
        command.rights_status,
        command.protection_profile,
        command.retention_class,
        "available",
    )
    actual = (
        result.byte_length,
        result.media_type,
        result.rights_status,
        result.protection_profile,
        result.retention_class,
        result.storage_state,
    )
    return ("committed", result) if actual == expected else ("retained", result)


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


def _sqlite_busy(error: sqlite3.Error) -> bool:
    code = getattr(error, "sqlite_errorcode", None)
    return isinstance(code, int) and (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)


def _stream_to_staging(
    source: BinaryIO,
    staging: Path,
    *,
    project_id: str,
    protection_profile: str,
    key_provider: ObjectMasterKeyProvider | None,
    allow_plaintext_fixture: bool,
) -> tuple[Path, str, int, _EnvelopeMetadata]:
    encrypted = protection_profile == _ENCRYPTED_PROFILE
    plaintext_fixture = protection_profile == _PLAINTEXT_FIXTURE and allow_plaintext_fixture
    if not encrypted and not plaintext_fixture:
        raise _bounded(ObjectStoreProblem, "object protection profile is unavailable")
    master = _master_key(key_provider) if encrypted else None
    data_key = sodium.crypto_secretstream_xchacha20poly1305_keygen() if encrypted else None
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
        if encrypted:
            if master is None or data_key is None:
                raise ObjectKeyUnavailable("object encryption key is unavailable")
            stream_state = sodium.crypto_secretstream_xchacha20poly1305_state()
            header = sodium.crypto_secretstream_xchacha20poly1305_init_push(stream_state, data_key)
            _write_all(descriptor, _ENVELOPE_MAGIC)
            _write_all(descriptor, header)
            frame_index = 0
            block = _read_source_block(source)
            while True:
                next_block = b"" if block == b"" else _read_source_block(source)
                final = next_block == b""
                length += len(block)
                if length > MAX_SAFE_INTEGER:
                    raise ValueError("object exceeds the supported length")
                digest.update(block)
                ciphertext = sodium.crypto_secretstream_xchacha20poly1305_push(
                    stream_state,
                    block,
                    ad=_frame_aad(project_id, frame_index),
                    tag=(
                        sodium.crypto_secretstream_xchacha20poly1305_TAG_FINAL
                        if final
                        else sodium.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE
                    ),
                )
                _write_all(descriptor, _FRAME_LENGTH.pack(len(ciphertext)))
                _write_all(descriptor, ciphertext)
                if final:
                    break
                block = next_block
                frame_index += 1
        else:
            while block := _read_source_block(source):
                length += len(block)
                if length > MAX_SAFE_INTEGER:
                    raise ValueError("object exceeds the supported length")
                digest.update(block)
                _write_all(descriptor, block)
        os.fsync(descriptor)
        if not _file_matches(destination, descriptor, identity):
            raise OSError("staging identity changed")
        object_sha256 = digest.hexdigest()
        ciphertext_byte_length = int(os.fstat(descriptor).st_size)
        if encrypted:
            if master is None or data_key is None:
                raise ObjectKeyUnavailable("object encryption key is unavailable")
            nonce = secrets.token_bytes(sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES)
            wrapped_key = sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
                data_key,
                _wrap_aad(project_id, object_sha256, master.key_version),
                nonce,
                master.key_bytes,
            )
            envelope = _EnvelopeMetadata(
                envelope_version=_ENCRYPTED_ENVELOPE,
                key_version=master.key_version,
                wrapped_key=wrapped_key.hex(),
                wrap_nonce=nonce.hex(),
                ciphertext_byte_length=ciphertext_byte_length,
            )
        else:
            envelope = _EnvelopeMetadata(
                envelope_version=_PLAINTEXT_FIXTURE,
                key_version=None,
                wrapped_key=None,
                wrap_nonce=None,
                ciphertext_byte_length=length,
            )
        succeeded = True
        return destination, object_sha256, length, envelope
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not succeeded:
            with suppress(OSError):
                destination.unlink()


def _publish(staging: Path, destination: Path) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move_file = kernel32.MoveFileExW
        move_file.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        move_file.restype = wintypes.BOOL
        move_file_write_through = 0x00000008
        if move_file(str(staging), str(destination), move_file_write_through):
            return True
        error = ctypes.get_last_error()
        if error in (80, 183):  # ERROR_FILE_EXISTS / ERROR_ALREADY_EXISTS
            with suppress(OSError):
                staging.unlink()
            return False
        with suppress(OSError):
            staging.unlink()
        raise ctypes.WinError(error)

    try:
        os.link(staging, destination, follow_symlinks=False)
        created = True
    except FileExistsError:
        created = False
    finally:
        with suppress(OSError):
            staging.unlink()
    _sync_directory(destination.parent)
    _sync_directory(staging.parent)
    return created


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _move_no_replace(source: Path, destination: Path) -> None:
    if os.name != "nt":
        os.rename(source, destination)
        _sync_directory(source.parent)
        if source.parent != destination.parent:
            _sync_directory(destination.parent)
        return

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file = kernel32.MoveFileExW
    move_file.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    move_file.restype = wintypes.BOOL
    move_file_write_through = 0x00000008
    if not move_file(str(source), str(destination), move_file_write_through):
        raise ctypes.WinError(ctypes.get_last_error())


_DELETE_STAGING = re.compile(r"^delete-([0-9a-f]{64})\.partial$")


def _reconcile_staging(
    directory: Path,
    state: _StoreState,
) -> None:
    failure: ObjectStoreProblem | None = None
    try:
        candidates = tuple(directory.iterdir())
    except OSError:
        candidates = ()
        failure = _bounded(ObjectStoreProblem, "object staging inventory is unavailable")
    if failure is not None:
        raise failure
    connection: CanonicalConnection | None = None
    try:
        connection = open_canonical_database(state.database, expected_project_id=state.project_id)
        rows = tuple(
            connection.execute(
                """
                SELECT object_sha256
                  FROM object_records WHERE project_id=?
                """,
                (state.project_id,),
            ).fetchall()
        )
    except sqlite3.Error, StorageProblem:
        rows = ()
        failure = _bounded(ObjectStoreProblem, "object staging metadata is unavailable")
    finally:
        if connection is not None:
            connection.close()
    if failure is not None:
        raise failure

    delete_rows = {_opaque_name(state.project_id, str(row[0])): str(row[0]) for row in rows}
    for candidate in candidates:
        record_connection: CanonicalConnection | None = None
        try:
            status = candidate.stat(follow_symlinks=False)
            if not (
                candidate.name.endswith(".partial")
                and stat.S_ISREG(status.st_mode)
                and status.st_nlink == 1
                and not _redirect(candidate)
            ):
                raise OSError("unexpected object staging entry")
            match = _DELETE_STAGING.fullmatch(candidate.name)
            if match is None:
                candidate.unlink()
                continue
            row = delete_rows.get(match.group(1))
            if row is None:
                raise OSError("delete recovery metadata is unavailable")
            digest = row
            record_connection = open_canonical_database(
                state.database,
                expected_project_id=state.project_id,
            )
            metadata = _metadata(record_connection, state.project_id, digest)
            if metadata is None:
                raise OSError("delete recovery metadata is unavailable")
            destination, buckets = _object_path(state.objects, state.project_id, digest, create=False)
            with _stable_directories([state.objects, *buckets]):
                reader = _verified_stored_reader(state, record_connection, candidate, metadata)
                reader.close()
                if metadata.storage_state == "deleted":
                    if destination.exists():
                        raise OSError("deleted object has conflicting bytes")
                    candidate.unlink()
                elif metadata.storage_state in ("available", "quarantined"):
                    if destination.exists():
                        raise OSError("object recovery destination already exists")
                    _move_no_replace(candidate, destination)
                    restored = _verified_stored_reader(state, record_connection, destination, metadata)
                    restored.close()
                else:
                    raise OSError("object recovery state is invalid")
        except OSError:
            failure = _bounded(ObjectStoreProblem, "abandoned object staging cannot be reconciled")
        finally:
            if record_connection is not None:
                record_connection.close()
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
        reader: Any | None = None
        publication_guard: io.FileIO | None = None
        publication_identity: tuple[int, int] | None = None
        remove_after_close = False
        quarantine_after_close = False
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            staging_directory = _staging_directory(state.temporary)
            with _stable_directories([state.root, state.state, state.objects, state.temporary, staging_directory]):
                staging_failure: ObjectStoreProblem | None = None
                staging: Path | None = None
                digest = ""
                length = 0
                envelope: _EnvelopeMetadata | None = None
                try:
                    staging, digest, length, envelope = _stream_to_staging(
                        source,
                        staging_directory,
                        project_id=state.project_id,
                        protection_profile=command.protection_profile,
                        key_provider=state.key_provider,
                        allow_plaintext_fixture=state.allow_plaintext_fixture,
                    )
                except ObjectStoreProblem as problem:
                    staging_failure = _bounded(type(problem), str(problem))
                except Exception:
                    staging_failure = _bounded(ObjectStoreProblem, "object source could not be staged")
                if staging_failure is not None or staging is None or envelope is None:
                    raise staging_failure or _bounded(ObjectStoreProblem, "object source could not be staged")
                if command.expected_sha256 is not None and digest != command.expected_sha256:
                    with suppress(OSError):
                        staging.unlink()
                    raise _bounded(ObjectIntegrityMismatch, "object content hash did not match")
                publication_failure: ObjectStoreProblem | None = None
                try:
                    destination, buckets = _object_path(state.objects, state.project_id, digest, create=True)
                    with _stable_directories(
                        [state.root, state.state, state.objects, state.temporary, staging_directory, *buckets]
                    ):
                        created_file = _publish(staging, destination)
                        publication_guard = _open_read_locked(destination)
                        guard_status = os.fstat(publication_guard.fileno())
                        publication_identity = (guard_status.st_dev, guard_status.st_ino)
                        if not _file_matches(destination, publication_guard.fileno(), publication_identity):
                            raise ObjectCorrupt("object identity changed before metadata reservation")
                        connection = open_canonical_database(state.database, expected_project_id=state.project_id)
                        connection.execute("BEGIN IMMEDIATE")
                        existing = _metadata(connection, state.project_id, digest)
                        verified_at = max(command.created_at, _now())
                        if existing is None:
                            if not created_file:
                                raise ObjectConflict("object bytes exist without canonical encryption metadata")
                            connection.execute(
                                """
                                INSERT INTO object_records (
                                    object_sha256, project_id, byte_length, media_type, rights_status,
                                    protection_profile, retention_class, storage_state, created_at, verified_at,
                                    envelope_version, key_version, wrapped_key, wrap_nonce, ciphertext_byte_length
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?, ?, ?, ?, ?)
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
                                    envelope.envelope_version,
                                    envelope.key_version,
                                    envelope.wrapped_key,
                                    envelope.wrap_nonce,
                                    envelope.ciphertext_byte_length,
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
                            if existing.storage_state == "deleted":
                                if not created_file:
                                    raise ObjectCorrupt("deleted object has unexpected visible bytes")
                                connection.execute(
                                    """
                                    UPDATE object_records
                                       SET storage_state='available', verified_at=?,
                                           envelope_version=?, key_version=?, wrapped_key=?,
                                           wrap_nonce=?, ciphertext_byte_length=?
                                     WHERE project_id=? AND object_sha256=?
                                    """,
                                    (
                                        verified_at,
                                        envelope.envelope_version,
                                        envelope.key_version,
                                        envelope.wrapped_key,
                                        envelope.wrap_nonce,
                                        envelope.ciphertext_byte_length,
                                        state.project_id,
                                        digest,
                                    ),
                                )
                            elif existing.storage_state == "available":
                                if created_file:
                                    quarantine_after_close = True
                                    raise ObjectCorrupt("available object bytes were unexpectedly absent")
                                connection.execute(
                                    """
                                    UPDATE object_records SET verified_at=?
                                     WHERE project_id=? AND object_sha256=?
                                    """,
                                    (verified_at, state.project_id, digest),
                                )
                            else:
                                raise ObjectConflict("object storage state cannot be published")
                        result = _metadata(connection, state.project_id, digest)
                        if result is None:
                            raise ObjectStoreProblem("object metadata publication failed")
                        reader = _verified_stored_reader(state, connection, destination, result)
                        if not _held_reader_matches(destination, reader) or not _file_matches(
                            destination,
                            publication_guard.fileno(),
                            publication_identity,
                        ):
                            raise ObjectCorrupt("object identity changed before metadata publication")
                        connection.execute("COMMIT")
                        if not _held_reader_matches(destination, reader) or not _file_matches(
                            destination,
                            publication_guard.fileno(),
                            publication_identity,
                        ):
                            quarantine_after_close = True
                            raise ObjectCorrupt("object identity changed during metadata publication")
                        return result
                except ObjectStoreProblem as problem:
                    if connection is not None and connection.in_transaction:
                        with suppress(sqlite3.Error, StorageProblem):
                            connection.execute("ROLLBACK")
                    publication_state, _result = _publication_state(state, digest, length, command)
                    if created_file and destination is not None and publication_state == "absent":
                        remove_after_close = True
                    raise _bounded(type(problem), str(problem)) from None
                except OSError, ProjectLifecycleProblem, sqlite3.Error, StorageProblem, ValueError:
                    if connection is not None and connection.in_transaction:
                        with suppress(sqlite3.Error, StorageProblem):
                            connection.execute("ROLLBACK")
                    publication_state, reconciled = _publication_state(state, digest, length, command)
                    if publication_state == "committed" and reconciled is not None:
                        if reader is not None and destination is not None and _held_reader_matches(destination, reader):
                            return reconciled
                        quarantine_after_close = True
                        publication_failure = _bounded(
                            ObjectCorrupt,
                            "object identity changed during metadata reconciliation",
                        )
                    if created_file and destination is not None and publication_state == "absent":
                        remove_after_close = True
                    if publication_failure is None:
                        publication_failure = _bounded(ObjectStoreProblem, "object publication failed")
                finally:
                    if reader is not None:
                        reader.close()
                    if publication_guard is not None:
                        publication_guard.close()
                    if remove_after_close and destination is not None:
                        with suppress(OSError):
                            destination.unlink()
                    if connection is not None:
                        connection.close()
                    if quarantine_after_close:
                        _mark_quarantined(state, digest)
                if publication_failure is not None:
                    raise publication_failure

    def open(self, object_sha256: str, *, purpose: str) -> VerifiedObjectStream:
        digest = _validate_sha256(object_sha256)
        _validate_purpose(purpose)
        state = self._state()
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            connection: CanonicalConnection | None = None
            reader: Any | None = None
            failure: ObjectStoreProblem | None = None
            destination: Path | None = None
            buckets: tuple[Path, ...] = ()
            try:
                connection = _open_thread_transferable_canonical_database(
                    state.database,
                    expected_project_id=state.project_id,
                )
                connection.execute("BEGIN IMMEDIATE")
                metadata = _metadata(connection, state.project_id, digest)
                if metadata is None:
                    raise ObjectNotFound("object is unavailable")
                if metadata.storage_state == "quarantined":
                    raise ObjectCorrupt("object is quarantined")
                if metadata.storage_state != "available":
                    raise ObjectNotFound("object is unavailable")
                if metadata.rights_status not in _READABLE_RIGHTS:
                    raise ObjectAccessDenied("object access is not authorized")
                destination, buckets = _object_path(state.objects, state.project_id, digest, create=False)
                with _stable_directories([state.root, state.objects, *buckets]):
                    reader = _verified_stored_reader(state, connection, destination, metadata)
                updated = connection.execute(
                    """
                    UPDATE object_records SET verified_at=?
                     WHERE project_id=? AND object_sha256=? AND storage_state='available'
                       AND rights_status IN ('allowed', 'not-applicable')
                    """,
                    (max(metadata.created_at, _now()), state.project_id, digest),
                )
                if updated.rowcount != 1:
                    raise ObjectAccessDenied("object access state changed")
                stream = _VerifiedObjectStream(reader, connection, state.project_id, digest)
                reader = None
                connection = None
                return stream
            except ObjectStoreProblem as problem:
                failure = _bounded(type(problem), str(problem))
            except OSError, ProjectLifecycleProblem:
                failure = _bounded(ObjectCorrupt, "object integrity verification failed")
            except sqlite3.Error, StorageProblem:
                failure = _bounded(ObjectStoreProblem, "object verification state could not be recorded")
            finally:
                if reader is not None:
                    reader.close()
                if connection is not None:
                    if connection.in_transaction:
                        with suppress(sqlite3.Error, StorageProblem):
                            connection.execute("ROLLBACK")
                    connection.close()
            if isinstance(failure, ObjectCorrupt):
                _mark_quarantined(state, digest)
            if failure is not None:
                raise failure
            raise _bounded(ObjectStoreProblem, "object verification failed")

    def delete(self, object_sha256: str) -> None:
        digest = _validate_sha256(object_sha256)
        state = self._state()
        connection: CanonicalConnection | None = None
        moved: Path | None = None
        destination: Path | None = None
        failure: ObjectStoreProblem | None = None
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            if _READERS.in_use(state.project_id, digest):
                raise _bounded(ObjectBusy, "object is in active use; retry after the reader closes")
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
                    reader = _verified_stored_reader(state, connection, destination, metadata)
                    reader.close()
                    moved = staging / f"delete-{_opaque_name(state.project_id, digest)}.partial"
                    _move_no_replace(destination, moved)
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
                        _move_no_replace(moved, destination)
                _mark_quarantined(state, digest)
                failure = _bounded(ObjectCorrupt, "object delete verification failed")
            except sqlite3.Error as error:
                if connection is not None and connection.in_transaction:
                    with suppress(sqlite3.Error, StorageProblem):
                        connection.execute("ROLLBACK")
                if moved is not None and destination is not None:
                    with suppress(OSError):
                        _move_no_replace(moved, destination)
                failure = (
                    _bounded(ObjectBusy, "object is busy; retry the delete")
                    if _sqlite_busy(error)
                    else _bounded(ObjectStoreProblem, "object delete failed")
                )
            except StorageProblem:
                if connection is not None and connection.in_transaction:
                    with suppress(sqlite3.Error, StorageProblem):
                        connection.execute("ROLLBACK")
                if moved is not None and destination is not None:
                    with suppress(OSError):
                        _move_no_replace(moved, destination)
                failure = _bounded(ObjectStoreProblem, "object delete failed")
            finally:
                if connection is not None:
                    connection.close()
            if failure is not None:
                raise failure


def create_local_object_store(
    project_root: Path,
    project_id: str,
    *,
    key_provider: ObjectMasterKeyProvider | None = None,
    allow_plaintext_fixture: bool = False,
) -> ObjectStore:
    """Create the project-local adapter behind the dependency-neutral port."""

    if not isinstance(allow_plaintext_fixture, bool):
        raise _bounded(ObjectStoreProblem, "plaintext fixture policy is invalid")
    if key_provider is None and not allow_plaintext_fixture:
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    if key_provider is not None and not isinstance(key_provider, ObjectMasterKeyProvider):
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")

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
    store_state = _StoreState(
        root=root,
        state=state_directory,
        objects=objects,
        temporary=temporary,
        database=database,
        project_id=project_id,
        key_provider=key_provider,
        allow_plaintext_fixture=allow_plaintext_fixture,
        lock=threading.RLock(),
    )
    staging_failure: ObjectStoreProblem | None = None
    try:
        staging = _staging_directory(temporary)
        with _stable_directories([root, state_directory, objects, temporary, staging]):
            _reconcile_staging(staging, store_state)
    except ObjectStoreProblem as problem:
        staging_failure = _bounded(type(problem), "object staging reconciliation failed")
    except OSError, ProjectLifecycleProblem:
        staging_failure = _bounded(ObjectStoreProblem, "object staging reconciliation failed")
    if staging_failure is not None:
        raise staging_failure
    return _LocalObjectStore(store_state)


__all__ = ["create_local_object_store"]
