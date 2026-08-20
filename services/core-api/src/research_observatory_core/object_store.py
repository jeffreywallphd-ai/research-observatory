"""Project-scoped local adapter for the content-addressed object-store port."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import re
import secrets
import shutil
import sqlite3
import stat
import struct
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from nacl import bindings as sodium
from nacl.exceptions import CryptoError

from .ports.object_store import (
    CleanupCategory,
    ObjectAccessDenied,
    ObjectBusy,
    ObjectConflict,
    ObjectCorrupt,
    ObjectIntegrityMismatch,
    ObjectKeyUnavailable,
    ObjectNotFound,
    ObjectPutCommand,
    ObjectReferenced,
    ObjectStoragePressure,
    ObjectStore,
    ObjectStoreProblem,
    RetentionClass,
    RightsStatus,
    StorageCategory,
    StorageCleanupPreview,
    StorageCleanupRequest,
    StorageCleanupResult,
    StoragePolicy,
    StoragePressure,
    StorageState,
    StorageUsage,
    StorageUsageCategory,
    StoredObject,
    VerifiedObjectStream,
)
from .ports.object_store_keys import ObjectMasterKey, ObjectMasterKeyProvider
from .projects import ProjectLifecycleProblem, _atomic_audit_append, _stable_directories
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
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_UTC_MILLISECONDS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_CLEANUP_PARTIAL = re.compile(r"^cleanup-[0-9a-f]{24}-(?P<identity>[A-Za-z0-9_-]{43})\.partial$")
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
_CLEANUP_CATEGORIES: tuple[CleanupCategory, ...] = (
    "derived-objects",
    "orphaned-objects",
    "indexes",
    "project-cache",
    "models",
    "shared-cache",
)
_STORAGE_CATEGORIES: tuple[StorageCategory, ...] = (
    "canonical-metadata",
    "durable-objects",
    "derived-objects",
    "orphaned-objects",
    "indexes",
    "project-cache",
    "models",
    "configuration",
    "exports",
    "operational",
    "shared-cache",
)
_CATEGORY_CONSEQUENCE = {
    "canonical-metadata": "retained",
    "durable-objects": "retained",
    "derived-objects": "recomputed",
    "orphaned-objects": "metadata-repair",
    "indexes": "recomputed",
    "project-cache": "recomputed",
    "models": "redownloaded",
    "configuration": "retained",
    "exports": "retained",
    "operational": "retained",
    "shared-cache": "redownloaded",
}


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


def _cleanup_staging_directory(temporary: Path) -> Path:
    return _canonical_directory(temporary / "storage-cleanup", create=True)


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
    except OSError, ProjectLifecycleProblem:
        return False


def _held_candidate_matches(candidate: _FileCandidate, descriptor: int, visible_path: Path) -> bool:
    try:
        opened = os.fstat(descriptor)
        visible = visible_path.stat(follow_symlinks=False)
        return (
            stat.S_ISREG(opened.st_mode)
            and stat.S_ISREG(visible.st_mode)
            and opened.st_nlink == 1
            and visible.st_nlink == 1
            and (opened.st_dev, opened.st_ino) == candidate.identity
            and (visible.st_dev, visible.st_ino) == candidate.identity
            and int(opened.st_size) == candidate.byte_count
            and int(visible.st_size) == candidate.byte_count
            and int(opened.st_mtime_ns) == candidate.modified_ns
            and int(visible.st_mtime_ns) == candidate.modified_ns
            and not _redirect(visible_path)
        )
    except OSError:
        return False


@contextmanager
def _held_cleanup_candidate(
    candidate: _FileCandidate,
) -> Iterator[tuple[Callable[[Path], None], Callable[[], None]]]:
    """Bind destructive cleanup to the verified Windows file handle."""

    if os.name != "nt":
        reader = _open_read_locked(candidate.path)
        try:
            if not _held_candidate_matches(candidate, reader.fileno(), candidate.path):
                raise OSError("cleanup candidate identity changed")

            def unsupported_rename(_destination: Path) -> None:
                raise OSError("identity-bound cleanup is unavailable on this platform")

            def unsupported_delete() -> None:
                raise OSError("identity-bound cleanup is unavailable on this platform")

            yield unsupported_rename, unsupported_delete
        finally:
            reader.close()
        return

    import ctypes
    import msvcrt
    from ctypes import wintypes

    class FileRenameInfo(ctypes.Structure):
        _fields_ = (
            ("ReplaceIfExists", wintypes.BOOLEAN),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", wintypes.WCHAR * 1),
        )

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = (("DeleteFile", wintypes.BOOLEAN),)

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
    generic_read = 0x80000000
    delete_access = 0x00010000
    file_share_read = 0x00000001
    open_existing = 3
    file_rename_info = 3
    file_disposition_info = 4
    file_flag_open_reparse_point = 0x00200000
    invalid_handle = wintypes.HANDLE(-1).value
    handle = create_file(
        str(candidate.path),
        generic_read | delete_access,
        file_share_read,
        None,
        open_existing,
        file_flag_open_reparse_point,
        None,
    )
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except BaseException:
        close_handle(handle)
        raise
    reader = os.fdopen(descriptor, "rb", buffering=0)
    current = candidate.path

    def require_held_match() -> None:
        if not _held_candidate_matches(candidate, reader.fileno(), current):
            raise OSError("cleanup candidate identity changed")

    def rename_held(destination: Path) -> None:
        nonlocal current
        require_held_match()
        encoded = str(destination).encode("utf-16-le")
        size = FileRenameInfo.FileName.offset + len(encoded) + ctypes.sizeof(wintypes.WCHAR)
        buffer = ctypes.create_string_buffer(size)
        info = ctypes.cast(buffer, ctypes.POINTER(FileRenameInfo)).contents
        info.ReplaceIfExists = False
        info.RootDirectory = None
        info.FileNameLength = len(encoded)
        ctypes.memmove(ctypes.addressof(buffer) + FileRenameInfo.FileName.offset, encoded, len(encoded))
        native_handle = wintypes.HANDLE(msvcrt.get_osfhandle(reader.fileno()))
        if not set_file_information(native_handle, file_rename_info, buffer, size):
            raise ctypes.WinError(ctypes.get_last_error())
        current = destination
        require_held_match()

    def delete_held() -> None:
        require_held_match()
        info = FileDispositionInfo(True)
        native_handle = wintypes.HANDLE(msvcrt.get_osfhandle(reader.fileno()))
        if not set_file_information(
            native_handle,
            file_disposition_info,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    try:
        require_held_match()
        yield rename_held, delete_held
    finally:
        reader.close()


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
    cancellation_requested: Callable[[str], bool] | None
    storage_policy: StoragePolicy
    shared_cache: Path | None
    cleanup_plan: _CleanupPlan | None
    lock: threading.RLock


@dataclass(frozen=True, slots=True)
class _FileCandidate:
    category: CleanupCategory
    path: Path
    authority_root: Path
    identity: tuple[int, int]
    byte_count: int
    modified_ns: int
    object_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class _FileFact:
    path: Path
    identity: tuple[int, int]
    byte_count: int
    modified_ns: int
    exclusive: bool


@dataclass(frozen=True, slots=True)
class _CleanupPlan:
    token: str
    request: StorageCleanupRequest
    candidates: tuple[_FileCandidate, ...]


@dataclass(frozen=True, slots=True)
class _Inventory:
    usage: StorageUsage
    candidates: tuple[_FileCandidate, ...]


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


def _validate_limit(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_SAFE_INTEGER:
        raise _bounded(ObjectStoreProblem, f"{name} is invalid")
    return value


def _validate_storage_policy(policy: StoragePolicy | None) -> StoragePolicy:
    if policy is None:
        return StoragePolicy()
    if not isinstance(policy, StoragePolicy):
        raise _bounded(ObjectStoreProblem, "storage policy is invalid")
    project_soft = _validate_limit(policy.project_soft_limit_bytes, "project soft storage limit")
    project_hard = _validate_limit(policy.project_hard_limit_bytes, "project hard storage limit")
    shared_soft = _validate_limit(policy.shared_cache_soft_limit_bytes, "shared-cache soft storage limit")
    shared_hard = _validate_limit(policy.shared_cache_hard_limit_bytes, "shared-cache hard storage limit")
    minimum_free = _validate_limit(policy.minimum_free_bytes, "minimum free storage reserve")
    if minimum_free is None:
        raise _bounded(ObjectStoreProblem, "minimum free storage reserve is invalid")
    if project_soft is not None and project_hard is not None and project_soft > project_hard:
        raise _bounded(ObjectStoreProblem, "project storage thresholds are invalid")
    if shared_soft is not None and shared_hard is not None and shared_soft > shared_hard:
        raise _bounded(ObjectStoreProblem, "shared-cache storage thresholds are invalid")
    return StoragePolicy(
        project_soft_limit_bytes=project_soft,
        project_hard_limit_bytes=project_hard,
        shared_cache_soft_limit_bytes=shared_soft,
        shared_cache_hard_limit_bytes=shared_hard,
        minimum_free_bytes=minimum_free,
    )


def _validate_cleanup_request(request: StorageCleanupRequest) -> StorageCleanupRequest:
    if not isinstance(request, StorageCleanupRequest):
        raise _bounded(ObjectStoreProblem, "storage cleanup request is invalid")
    if (
        not isinstance(request.categories, tuple)
        or not request.categories
        or len(request.categories) != len(set(request.categories))
        or any(category not in _CLEANUP_CATEGORIES for category in request.categories)
    ):
        raise _bounded(ObjectStoreProblem, "storage cleanup categories are invalid")
    if not isinstance(request.requested_at, str) or _UTC_MILLISECONDS.fullmatch(request.requested_at) is None:
        raise _bounded(ObjectStoreProblem, "storage cleanup time is invalid")
    try:
        datetime.fromisoformat(request.requested_at[:-1] + "+00:00")
    except ValueError:
        raise _bounded(ObjectStoreProblem, "storage cleanup time is invalid") from None
    if not isinstance(request.trace_id, str) or _TRACE_ID.fullmatch(request.trace_id) is None:
        raise _bounded(ObjectStoreProblem, "storage cleanup trace is invalid")
    if not isinstance(request.actor_id, str) or _IDENTIFIER.fullmatch(request.actor_id) is None:
        raise _bounded(ObjectStoreProblem, "storage cleanup actor is invalid")
    return request


def _directory_chain(root: Path, parent: Path) -> tuple[Path, ...]:
    chain: list[Path] = []
    current = parent
    while True:
        chain.append(current)
        if current == root:
            break
        if root not in current.parents:
            raise OSError("storage path escaped its authority")
        current = current.parent
    return tuple(reversed(chain))


def _scan_regular_files(root: Path) -> tuple[_FileFact, ...]:
    if not root.exists():
        return ()
    authority = _canonical_directory(root)
    pending = [authority]
    facts: list[_FileFact] = []
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                status = path.stat(follow_symlinks=False)
                if stat.S_ISDIR(status.st_mode):
                    if _redirect(path) or path.resolve(strict=True) != path:
                        raise OSError("storage inventory contains a redirected directory")
                    pending.append(path)
                elif stat.S_ISREG(status.st_mode):
                    facts.append(
                        _FileFact(
                            path=path,
                            identity=(status.st_dev, status.st_ino),
                            byte_count=int(status.st_size),
                            modified_ns=int(status.st_mtime_ns),
                            exclusive=status.st_nlink == 1 and not _redirect(path),
                        )
                    )
                else:
                    raise OSError("storage inventory contains an unsupported entry")
    return tuple(sorted(facts, key=lambda item: os.path.normcase(str(item.path))))


def _object_relative_path(project_id: str, object_sha256: str) -> Path:
    opaque = _opaque_name(project_id, object_sha256)
    return Path(opaque[:2]) / opaque[2:4] / f"{opaque}.blob"


def _pressure(
    byte_count: int,
    soft_limit: int | None,
    hard_limit: int | None,
    *,
    free_bytes: int | None = None,
    minimum_free_bytes: int = 0,
) -> StoragePressure:
    if free_bytes is not None and free_bytes < minimum_free_bytes:
        return "low-disk"
    if hard_limit is not None and byte_count >= hard_limit:
        return "hard-limit"
    if soft_limit is not None and byte_count >= soft_limit:
        return "soft-limit"
    return "normal"


def _inventory(state: _StoreState) -> _Inventory:
    counts: dict[StorageCategory, list[int]] = {category: [0, 0, 0, 0] for category in _STORAGE_CATEGORIES}
    candidates: list[_FileCandidate] = []

    def record(
        category: StorageCategory,
        fact: _FileFact,
        *,
        reclaimable: bool = False,
        object_sha256: str | None = None,
        authority_root: Path | None = None,
    ) -> None:
        values = counts[category]
        values[0] += fact.byte_count
        values[1] += 1
        if reclaimable and category in _CLEANUP_CATEGORIES:
            values[2] += fact.byte_count
            values[3] += 1
            candidates.append(
                _FileCandidate(
                    category=category,
                    path=fact.path,
                    authority_root=authority_root or state.root,
                    identity=fact.identity,
                    byte_count=fact.byte_count,
                    modified_ns=fact.modified_ns,
                    object_sha256=object_sha256,
                )
            )

    connection: CanonicalConnection | None = None
    try:
        connection = open_canonical_database(state.database, expected_project_id=state.project_id)
        connection.execute("BEGIN")
        rows = tuple(
            connection.execute(
                """
                SELECT object.object_sha256, object.byte_length, object.media_type,
                       object.rights_status, object.protection_profile, object.retention_class,
                       object.storage_state, object.created_at, object.verified_at,
                       (SELECT count(*) FROM documents AS document
                         WHERE document.project_id = object.project_id
                           AND document.object_sha256 = object.object_sha256) AS reference_count,
                       object.envelope_version, object.key_version, object.ciphertext_byte_length
                  FROM object_records AS object
                 WHERE object.project_id = ?
                """,
                (state.project_id,),
            ).fetchall()
        )
        metadata_by_path = {
            os.path.normcase(str(_object_relative_path(state.project_id, str(row[0])))): _row_metadata(row)
            for row in rows
        }
        for fact in _scan_regular_files(state.objects):
            relative = fact.path.relative_to(state.objects)
            metadata = metadata_by_path.get(os.path.normcase(str(relative)))
            if metadata is None or metadata.storage_state == "deleted":
                record(
                    "orphaned-objects",
                    fact,
                    reclaimable=fact.exclusive,
                    authority_root=state.objects,
                )
                continue
            category: StorageCategory = (
                "derived-objects" if metadata.retention_class == "derived-rebuildable" else "durable-objects"
            )
            record(
                category,
                fact,
                reclaimable=(
                    category == "derived-objects"
                    and metadata.storage_state == "available"
                    and metadata.reference_count == 0
                    and fact.exclusive
                    and not _READERS.in_use(state.project_id, metadata.object_sha256)
                ),
                object_sha256=metadata.object_sha256,
                authority_root=state.objects,
            )
        connection.execute("ROLLBACK")
    except OSError, sqlite3.Error, StorageProblem:
        if connection is not None and connection.in_transaction:
            with suppress(sqlite3.Error, StorageProblem):
                connection.execute("ROLLBACK")
        raise _bounded(ObjectStoreProblem, "storage inventory is unavailable") from None
    finally:
        if connection is not None:
            connection.close()

    category_directories: tuple[tuple[str, StorageCategory], ...] = (
        ("state", "canonical-metadata"),
        ("indexes", "indexes"),
        ("cache", "project-cache"),
        ("models", "models"),
        ("config", "configuration"),
        ("exports", "exports"),
        ("logs", "operational"),
        (".locks", "operational"),
        (".tmp", "operational"),
    )
    try:
        for relative_name, category in category_directories:
            directory = state.root / relative_name
            for fact in _scan_regular_files(directory):
                reclaimable = category in ("indexes", "project-cache", "models") and fact.exclusive
                record(category, fact, reclaimable=reclaimable, authority_root=directory)
        for child in state.root.iterdir():
            if child.is_file() and child.name not in {"state", "objects"}:
                status = child.stat(follow_symlinks=False)
                record(
                    "canonical-metadata",
                    _FileFact(
                        path=child,
                        identity=(status.st_dev, status.st_ino),
                        byte_count=int(status.st_size),
                        modified_ns=int(status.st_mtime_ns),
                        exclusive=status.st_nlink == 1 and not _redirect(child),
                    ),
                )
        if state.shared_cache is not None:
            for fact in _scan_regular_files(state.shared_cache):
                record(
                    "shared-cache",
                    fact,
                    reclaimable=fact.exclusive,
                    authority_root=state.shared_cache,
                )
        disk = shutil.disk_usage(state.root)
    except OSError:
        raise _bounded(ObjectStoreProblem, "storage inventory is unavailable") from None

    categories = tuple(
        StorageUsageCategory(
            category=category,
            byte_count=counts[category][0],
            item_count=counts[category][1],
            reclaimable_byte_count=counts[category][2],
            reclaimable_item_count=counts[category][3],
            cleanup_consequence=cast(Any, _CATEGORY_CONSEQUENCE[category]),
        )
        for category in _STORAGE_CATEGORIES
    )
    project_bytes = sum(entry.byte_count for entry in categories if entry.category != "shared-cache")
    shared_bytes = counts["shared-cache"][0]
    policy = state.storage_policy
    usage = StorageUsage(
        project_byte_count=project_bytes,
        shared_cache_byte_count=shared_bytes,
        free_byte_count=int(disk.free),
        project_soft_limit_bytes=policy.project_soft_limit_bytes,
        project_hard_limit_bytes=policy.project_hard_limit_bytes,
        shared_cache_soft_limit_bytes=policy.shared_cache_soft_limit_bytes,
        shared_cache_hard_limit_bytes=policy.shared_cache_hard_limit_bytes,
        project_pressure=_pressure(
            project_bytes,
            policy.project_soft_limit_bytes,
            policy.project_hard_limit_bytes,
            free_bytes=int(disk.free),
            minimum_free_bytes=policy.minimum_free_bytes,
        ),
        shared_cache_pressure=_pressure(
            shared_bytes,
            policy.shared_cache_soft_limit_bytes,
            policy.shared_cache_hard_limit_bytes,
        ),
        categories=categories,
    )
    return _Inventory(usage=usage, candidates=tuple(candidates))


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
    upgrade_boundary: Callable[[str], None] | None = None,
    admission_check: Callable[[int], None] | None = None,
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
        if admission_check is not None:
            admission_check(0)
        digest = hashlib.sha256()
        length = 0
        if encrypted:
            if master is None or data_key is None:
                raise ObjectKeyUnavailable("object encryption key is unavailable")
            stream_state = sodium.crypto_secretstream_xchacha20poly1305_state()
            header = sodium.crypto_secretstream_xchacha20poly1305_init_push(stream_state, data_key)
            if admission_check is not None:
                admission_check(len(_ENVELOPE_MAGIC) + len(header))
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
                if admission_check is not None:
                    admission_check(int(os.fstat(descriptor).st_size) + _FRAME_LENGTH.size + len(ciphertext))
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
                if admission_check is not None:
                    admission_check(int(os.fstat(descriptor).st_size) + len(block))
                _write_all(descriptor, block)
        if upgrade_boundary is not None:
            upgrade_boundary("before-replacement-fsync")
        os.fsync(descriptor)
        if upgrade_boundary is not None:
            upgrade_boundary("after-replacement-fsync")
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
            if upgrade_boundary is not None:
                upgrade_boundary("before-partial-cleanup")
            with suppress(OSError):
                destination.unlink()
            if upgrade_boundary is not None:
                upgrade_boundary("after-partial-cleanup")


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


@dataclass(frozen=True, slots=True)
class _UpgradeRecord:
    object_sha256: str
    phase: str
    source_identity: tuple[int, int] | None
    replacement_identity: tuple[int, int] | None
    rollback_identity: tuple[int, int] | None
    envelope: _EnvelopeMetadata | None


def _upgrade_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for restart/recovery proof."""


class _UpgradeCancelled(ObjectStoreProblem):
    """A caller requested cancellation at a journaled recovery boundary."""


def _upgrade_boundary(boundary: str) -> None:
    _upgrade_step_completed(boundary)


def _check_upgrade_cancellation(state: _StoreState, phase: str) -> None:
    requested = state.cancellation_requested
    if requested is None:
        return
    try:
        cancelled = requested(phase)
    except Exception:
        raise _bounded(ObjectStoreProblem, "object upgrade cancellation check failed") from None
    if not isinstance(cancelled, bool):
        raise _bounded(ObjectStoreProblem, "object upgrade cancellation check failed")
    if cancelled:
        raise _bounded(_UpgradeCancelled, "object upgrade was cancelled")


def _optional_identity(device: Any, inode: Any) -> tuple[int, int] | None:
    if device is None and inode is None:
        return None
    if not isinstance(device, str) or not isinstance(inode, str):
        raise _bounded(ObjectStoreProblem, "object upgrade identity is invalid")
    try:
        identity = (int(device), int(inode))
    except ValueError:
        raise _bounded(ObjectStoreProblem, "object upgrade identity is invalid") from None
    if identity[0] < 0 or identity[1] < 0:
        raise _bounded(ObjectStoreProblem, "object upgrade identity is invalid")
    return identity


def _upgrade_record(connection: CanonicalConnection, project_id: str, digest: str) -> _UpgradeRecord:
    row = connection.execute(
        """
        SELECT phase, source_device, source_inode, replacement_device, replacement_inode,
               rollback_device, rollback_inode, key_version, wrapped_key, wrap_nonce,
               ciphertext_byte_length
          FROM object_envelope_upgrades
         WHERE project_id=? AND object_sha256=?
        """,
        (project_id, digest),
    ).fetchone()
    if row is None:
        raise _bounded(ObjectStoreProblem, "object upgrade state is unavailable")
    key_version = None if row[7] is None else str(row[7])
    wrapped_key = None if row[8] is None else str(row[8])
    wrap_nonce = None if row[9] is None else str(row[9])
    ciphertext_length = None if row[10] is None else int(row[10])
    envelope: _EnvelopeMetadata | None = None
    if any(value is not None for value in (key_version, wrapped_key, wrap_nonce, ciphertext_length)):
        if None in (key_version, wrapped_key, wrap_nonce, ciphertext_length):
            raise _bounded(ObjectStoreProblem, "object upgrade encryption state is invalid")
        envelope = _EnvelopeMetadata(
            envelope_version=_ENCRYPTED_ENVELOPE,
            key_version=key_version,
            wrapped_key=wrapped_key,
            wrap_nonce=wrap_nonce,
            ciphertext_byte_length=cast(int, ciphertext_length),
        )
    return _UpgradeRecord(
        object_sha256=digest,
        phase=str(row[0]),
        source_identity=_optional_identity(row[1], row[2]),
        replacement_identity=_optional_identity(row[3], row[4]),
        rollback_identity=_optional_identity(row[5], row[6]),
        envelope=envelope,
    )


def _upgrade_paths(destination: Path) -> tuple[Path, Path]:
    return (
        destination.with_name(f".{destination.name}.upgrade-replacement"),
        destination.with_name(f".{destination.name}.upgrade-rollback"),
    )


def _exclusive_identity(path: Path) -> tuple[int, int]:
    status = path.stat(follow_symlinks=False)
    identity = (status.st_dev, status.st_ino)
    if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1 or _redirect(path):
        raise OSError("object upgrade file identity is invalid")
    return identity


def _matches_identity(path: Path, expected: tuple[int, int] | None) -> bool:
    if expected is None:
        return False
    try:
        return _exclusive_identity(path) == expected
    except OSError:
        return False


def _verify_legacy_source(
    path: Path,
    *,
    digest: str,
    byte_length: int,
    expected_identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    try:
        identity = _exclusive_identity(path)
        if expected_identity is not None and identity != expected_identity:
            raise OSError("legacy object identity changed")
        reader = _verified_reader(path, digest, byte_length)
        reader.close()
        if _exclusive_identity(path) != identity:
            raise OSError("legacy object identity changed")
        return identity
    except OSError:
        raise _bounded(ObjectCorrupt, "legacy object source is corrupt") from None


def _verify_upgrade_replacement(
    state: _StoreState,
    path: Path,
    metadata: StoredObject,
    envelope: _EnvelopeMetadata,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    try:
        identity = _exclusive_identity(path)
        if expected_identity is not None and identity != expected_identity:
            raise OSError("encrypted replacement identity changed")
        reader = _verified_encrypted_reader(
            path,
            project_id=state.project_id,
            object_sha256=metadata.object_sha256,
            byte_length=metadata.byte_length,
            ciphertext_byte_length=envelope.ciphertext_byte_length,
            key_version=envelope.key_version,
            wrapped_key=envelope.wrapped_key,
            wrap_nonce=envelope.wrap_nonce,
            key_provider=state.key_provider,
        )
        reader.close()
        if _exclusive_identity(path) != identity:
            raise OSError("encrypted replacement identity changed")
        return identity
    except ObjectKeyUnavailable:
        raise
    except OSError:
        raise _bounded(ObjectCorrupt, "encrypted object replacement is corrupt") from None


def _record_upgrade_failure(state: _StoreState, digest: str, code: str) -> None:
    connection: CanonicalConnection | None = None
    try:
        connection = open_canonical_database(state.database, expected_project_id=state.project_id)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE object_envelope_upgrades
               SET failure_code=?, updated_at=?
             WHERE project_id=? AND object_sha256=? AND phase <> 'complete'
            """,
            (code, _now(), state.project_id, digest),
        )
        connection.execute("COMMIT")
    except sqlite3.Error, StorageProblem:
        if connection is not None and connection.in_transaction:
            with suppress(sqlite3.Error, StorageProblem):
                connection.execute("ROLLBACK")
    finally:
        if connection is not None:
            connection.close()


def _set_upgrade_phase(
    state: _StoreState,
    digest: str,
    *,
    expected_phase: str,
    phase: str,
    source_identity: tuple[int, int] | None = None,
    replacement_identity: tuple[int, int] | None = None,
    rollback_identity: tuple[int, int] | None = None,
    envelope: _EnvelopeMetadata | None = None,
) -> None:
    connection = open_canonical_database(state.database, expected_project_id=state.project_id)
    try:
        connection.execute("BEGIN IMMEDIATE")
        updated = connection.execute(
            """
            UPDATE object_envelope_upgrades
               SET phase=?, source_device=?, source_inode=?,
                   replacement_device=?, replacement_inode=?,
                   rollback_device=?, rollback_inode=?, key_version=?, wrapped_key=?,
                   wrap_nonce=?, ciphertext_byte_length=?, failure_code=NULL, updated_at=?
             WHERE project_id=? AND object_sha256=? AND phase=?
            """,
            (
                phase,
                None if source_identity is None else str(source_identity[0]),
                None if source_identity is None else str(source_identity[1]),
                None if replacement_identity is None else str(replacement_identity[0]),
                None if replacement_identity is None else str(replacement_identity[1]),
                None if rollback_identity is None else str(rollback_identity[0]),
                None if rollback_identity is None else str(rollback_identity[1]),
                None if envelope is None else envelope.key_version,
                None if envelope is None else envelope.wrapped_key,
                None if envelope is None else envelope.wrap_nonce,
                None if envelope is None else envelope.ciphertext_byte_length,
                _now(),
                state.project_id,
                digest,
                expected_phase,
            ),
        )
        if updated.rowcount != 1:
            raise _bounded(ObjectStoreProblem, "object upgrade state changed")
        _upgrade_boundary(f"before-journal-{phase}-commit")
        connection.execute("COMMIT")
        _upgrade_boundary(f"after-journal-{phase}-commit")
    except BaseException:
        if connection.in_transaction:
            with suppress(sqlite3.Error, StorageProblem):
                connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def _commit_upgrade_metadata(
    state: _StoreState,
    metadata: StoredObject,
    record: _UpgradeRecord,
    rollback_identity: tuple[int, int],
) -> None:
    if record.envelope is None or record.source_identity is None or record.replacement_identity is None:
        raise _bounded(ObjectStoreProblem, "object upgrade state is incomplete")
    connection = open_canonical_database(state.database, expected_project_id=state.project_id)
    try:
        connection.execute("BEGIN IMMEDIATE")
        object_updated = connection.execute(
            """
            UPDATE object_records
               SET protection_profile=?, envelope_version=?, key_version=?, wrapped_key=?,
                   wrap_nonce=?, ciphertext_byte_length=?, verified_at=NULL
             WHERE project_id=? AND object_sha256=?
               AND envelope_version=? AND protection_profile=?
            """,
            (
                _ENCRYPTED_PROFILE,
                _ENCRYPTED_ENVELOPE,
                record.envelope.key_version,
                record.envelope.wrapped_key,
                record.envelope.wrap_nonce,
                record.envelope.ciphertext_byte_length,
                state.project_id,
                metadata.object_sha256,
                _PLAINTEXT_FIXTURE,
                _PLAINTEXT_FIXTURE,
            ),
        )
        journal_updated = connection.execute(
            """
            UPDATE object_envelope_upgrades
               SET phase='metadata-committed', rollback_device=?, rollback_inode=?,
                   failure_code=NULL, updated_at=?
             WHERE project_id=? AND object_sha256=? AND phase='swap-intent'
            """,
            (
                str(rollback_identity[0]),
                str(rollback_identity[1]),
                _now(),
                state.project_id,
                metadata.object_sha256,
            ),
        )
        if object_updated.rowcount != 1 or journal_updated.rowcount != 1:
            raise _bounded(ObjectStoreProblem, "object upgrade metadata changed")
        _upgrade_boundary("before-metadata-and-journal-commit")
        connection.execute("COMMIT")
        _upgrade_boundary("after-metadata-and-journal-commit")
    except BaseException:
        if connection.in_transaction:
            with suppress(sqlite3.Error, StorageProblem):
                connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def _load_upgrade(
    state: _StoreState,
    digest: str,
) -> tuple[_UpgradeRecord, StoredObject]:
    connection = open_canonical_database(state.database, expected_project_id=state.project_id)
    try:
        record = _upgrade_record(connection, state.project_id, digest)
        metadata = _metadata(connection, state.project_id, digest)
        if metadata is None:
            raise _bounded(ObjectStoreProblem, "object upgrade metadata is unavailable")
        return record, metadata
    finally:
        connection.close()


def _complete_metadata_upgrade(
    state: _StoreState,
    metadata: StoredObject,
    record: _UpgradeRecord,
    destination: Path,
    replacement: Path,
    rollback: Path,
) -> None:
    connection = open_canonical_database(state.database, expected_project_id=state.project_id)
    try:
        current = _metadata(connection, state.project_id, metadata.object_sha256)
        if current is None or current.envelope_version != _ENCRYPTED_ENVELOPE:
            raise _bounded(ObjectStoreProblem, "object upgrade metadata is incomplete")
        _upgrade_boundary("before-production-reader-verification")
        reader = _verified_stored_reader(state, connection, destination, current)
        reader.close()
        _upgrade_boundary("after-production-reader-verification")
    finally:
        connection.close()
    if replacement.exists() or _redirect(replacement):
        raise _bounded(ObjectStoreProblem, "object upgrade replacement conflicts")
    if rollback.exists():
        _upgrade_boundary("before-rollback-cleanup-verification")
        _verify_legacy_source(
            rollback,
            digest=metadata.object_sha256,
            byte_length=metadata.byte_length,
            expected_identity=record.rollback_identity or record.source_identity,
        )
        _upgrade_boundary("after-rollback-cleanup-verification")
        _upgrade_boundary("before-rollback-cleanup")
        rollback.unlink()
        if os.name != "nt":
            _sync_directory(rollback.parent)
        _upgrade_boundary("after-rollback-cleanup")
    elif record.phase == "metadata-committed" and record.rollback_identity is not None:
        # Cleanup may have completed immediately before interruption.
        pass
    _upgrade_step_completed("rollback-removed")
    _set_upgrade_phase(
        state,
        metadata.object_sha256,
        expected_phase="metadata-committed",
        phase="complete",
    )
    _upgrade_step_completed("complete")


def _reconcile_one_upgrade(state: _StoreState, staging: Path, digest: str) -> None:
    while True:
        record, metadata = _load_upgrade(state, digest)
        _check_upgrade_cancellation(state, record.phase)
        destination, buckets = _object_path(state.objects, state.project_id, digest, create=False)
        replacement, rollback = _upgrade_paths(destination)
        with _stable_directories([state.root, state.state, state.objects, state.temporary, staging, *buckets]):
            if record.phase == "complete":
                if replacement.exists() or rollback.exists() or _redirect(replacement) or _redirect(rollback):
                    raise _bounded(ObjectStoreProblem, "completed object upgrade has residual files")
                connection = open_canonical_database(state.database, expected_project_id=state.project_id)
                try:
                    current = _metadata(connection, state.project_id, digest)
                    if current is None:
                        raise _bounded(ObjectStoreProblem, "completed object upgrade metadata is unavailable")
                    _upgrade_boundary("before-completed-reader-verification")
                    reader = _verified_stored_reader(state, connection, destination, current)
                    reader.close()
                    _upgrade_boundary("after-completed-reader-verification")
                finally:
                    connection.close()
                return

            if record.phase == "legacy-detected":
                _upgrade_boundary("before-legacy-source-verification")
                source_identity = _verify_legacy_source(
                    destination,
                    digest=digest,
                    byte_length=metadata.byte_length,
                )
                _upgrade_boundary("after-legacy-source-verification")
                if replacement.exists() or rollback.exists() or _redirect(replacement) or _redirect(rollback):
                    raise _bounded(ObjectStoreProblem, "legacy object upgrade files conflict")
                _set_upgrade_phase(
                    state,
                    digest,
                    expected_phase="legacy-detected",
                    phase="replacement-writing",
                    source_identity=source_identity,
                )
                _upgrade_step_completed("legacy-detected")
                continue

            if record.phase == "replacement-writing":
                if record.source_identity is None:
                    raise _bounded(ObjectStoreProblem, "legacy object identity is unavailable")
                _upgrade_boundary("before-writing-source-verification")
                _verify_legacy_source(
                    destination,
                    digest=digest,
                    byte_length=metadata.byte_length,
                    expected_identity=record.source_identity,
                )
                _upgrade_boundary("after-writing-source-verification")
                if rollback.exists() or _redirect(rollback):
                    raise _bounded(ObjectStoreProblem, "object upgrade rollback conflicts")
                if replacement.exists():
                    if _redirect(replacement):
                        raise _bounded(ObjectStoreProblem, "object upgrade replacement conflicts")
                    _exclusive_identity(replacement)
                    _upgrade_boundary("before-stale-replacement-cleanup")
                    replacement.unlink()
                    if os.name != "nt":
                        _sync_directory(replacement.parent)
                    _upgrade_boundary("after-stale-replacement-cleanup")
                _upgrade_step_completed("replacement-writing")
                source = _open_read_locked(destination)
                staged: Path | None = None
                try:
                    staged, staged_digest, staged_length, envelope = _stream_to_staging(
                        source,
                        staging,
                        project_id=state.project_id,
                        protection_profile=_ENCRYPTED_PROFILE,
                        key_provider=state.key_provider,
                        allow_plaintext_fixture=False,
                        upgrade_boundary=_upgrade_boundary,
                    )
                finally:
                    source.close()
                if staged_digest != digest or staged_length != metadata.byte_length:
                    if staged is not None:
                        with suppress(OSError):
                            staged.unlink()
                    raise _bounded(ObjectCorrupt, "legacy object source is corrupt")
                _upgrade_boundary("before-staged-to-replacement-rename")
                _move_no_replace(staged, replacement)
                _upgrade_boundary("after-staged-to-replacement-rename")
                _upgrade_boundary("before-replacement-verification")
                replacement_identity = _verify_upgrade_replacement(state, replacement, metadata, envelope)
                _upgrade_boundary("after-replacement-verification")
                _set_upgrade_phase(
                    state,
                    digest,
                    expected_phase="replacement-writing",
                    phase="replacement-verified",
                    source_identity=record.source_identity,
                    replacement_identity=replacement_identity,
                    envelope=envelope,
                )
                _upgrade_step_completed("replacement-verified")
                continue

            if record.phase == "replacement-verified":
                if record.source_identity is None or record.replacement_identity is None or record.envelope is None:
                    raise _bounded(ObjectStoreProblem, "verified object replacement state is incomplete")
                _upgrade_boundary("before-pre-swap-source-verification")
                _verify_legacy_source(
                    destination,
                    digest=digest,
                    byte_length=metadata.byte_length,
                    expected_identity=record.source_identity,
                )
                _upgrade_boundary("after-pre-swap-source-verification")
                _upgrade_boundary("before-pre-swap-replacement-verification")
                _verify_upgrade_replacement(
                    state,
                    replacement,
                    metadata,
                    record.envelope,
                    expected_identity=record.replacement_identity,
                )
                _upgrade_boundary("after-pre-swap-replacement-verification")
                if rollback.exists() or _redirect(rollback):
                    raise _bounded(ObjectStoreProblem, "object upgrade rollback conflicts")
                _set_upgrade_phase(
                    state,
                    digest,
                    expected_phase="replacement-verified",
                    phase="swap-intent",
                    source_identity=record.source_identity,
                    replacement_identity=record.replacement_identity,
                    envelope=record.envelope,
                )
                _upgrade_step_completed("swap-intent")
                continue

            if record.phase == "swap-intent":
                if record.source_identity is None or record.replacement_identity is None or record.envelope is None:
                    raise _bounded(ObjectStoreProblem, "object swap intent is incomplete")
                canonical_is_source = _matches_identity(destination, record.source_identity)
                canonical_is_replacement = _matches_identity(destination, record.replacement_identity)
                rollback_is_source = _matches_identity(rollback, record.source_identity)
                replacement_is_expected = _matches_identity(replacement, record.replacement_identity)
                if canonical_is_source:
                    if rollback.exists() or _redirect(rollback):
                        raise _bounded(ObjectStoreProblem, "object upgrade rollback conflicts")
                    _upgrade_boundary("before-original-to-rollback-rename")
                    _move_no_replace(destination, rollback)
                    _upgrade_boundary("after-original-to-rollback-rename")
                    rollback_is_source = True
                    canonical_is_source = False
                    _upgrade_step_completed("original-moved-to-rollback")
                if not rollback_is_source:
                    raise _bounded(ObjectCorrupt, "object upgrade rollback authority is unavailable")
                if not destination.exists():
                    if not replacement_is_expected:
                        raise _bounded(ObjectCorrupt, "object upgrade replacement authority is unavailable")
                    _upgrade_boundary("before-replacement-to-canonical-rename")
                    _move_no_replace(replacement, destination)
                    _upgrade_boundary("after-replacement-to-canonical-rename")
                    canonical_is_replacement = True
                    replacement_is_expected = False
                    _upgrade_step_completed("replacement-moved-to-canonical")
                if not canonical_is_replacement or replacement_is_expected:
                    raise _bounded(ObjectCorrupt, "object upgrade canonical identity is invalid")
                _upgrade_boundary("before-rollback-authority-verification")
                rollback_identity = _verify_legacy_source(
                    rollback,
                    digest=digest,
                    byte_length=metadata.byte_length,
                    expected_identity=record.source_identity,
                )
                _upgrade_boundary("after-rollback-authority-verification")
                _upgrade_boundary("before-canonical-replacement-verification")
                _verify_upgrade_replacement(
                    state,
                    destination,
                    metadata,
                    record.envelope,
                    expected_identity=record.replacement_identity,
                )
                _upgrade_boundary("after-canonical-replacement-verification")
                _commit_upgrade_metadata(state, metadata, record, rollback_identity)
                _upgrade_step_completed("metadata-committed")
                continue

            if record.phase == "metadata-committed":
                _complete_metadata_upgrade(state, metadata, record, destination, replacement, rollback)
                continue

            raise _bounded(ObjectStoreProblem, "object upgrade phase is invalid")


def _reconcile_envelope_upgrades(directory: Path, state: _StoreState) -> None:
    connection = open_canonical_database(state.database, expected_project_id=state.project_id)
    try:
        rows = tuple(
            str(row[0])
            for row in connection.execute(
                """
                SELECT object_sha256
                  FROM object_envelope_upgrades
                 WHERE project_id=?
                 ORDER BY object_sha256
                """,
                (state.project_id,),
            ).fetchall()
        )
    finally:
        connection.close()
    for digest in rows:
        try:
            _reconcile_one_upgrade(state, directory, digest)
        except _UpgradeCancelled:
            _record_upgrade_failure(state, digest, "cancelled")
            raise _bounded(ObjectStoreProblem, "object upgrade was cancelled") from None
        except ObjectKeyUnavailable:
            _record_upgrade_failure(state, digest, "key-unavailable")
            raise
        except ObjectCorrupt as error:
            code = "source-corrupt"
            try:
                phase = _load_upgrade(state, digest)[0].phase
                if phase not in ("legacy-detected", "replacement-writing"):
                    code = "upgrade-corrupt"
            except ObjectStoreProblem:
                code = "upgrade-state-unavailable"
            _record_upgrade_failure(state, digest, code)
            raise _bounded(ObjectCorrupt, str(error)) from None
        except ObjectStoreProblem as error:
            _record_upgrade_failure(state, digest, "interrupted")
            raise _bounded(type(error), str(error)) from None
        except OSError, sqlite3.Error, StorageProblem:
            _record_upgrade_failure(state, digest, "io-failure")
            raise _bounded(ObjectStoreProblem, "object envelope upgrade did not complete") from None


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


def _reconcile_cleanup_staging(directory: Path) -> None:
    try:
        for path in tuple(directory.iterdir()):
            match = _CLEANUP_PARTIAL.fullmatch(path.name)
            if match is None:
                raise OSError("unexpected cleanup staging entry")
            status = path.stat(follow_symlinks=False)
            candidate = _FileCandidate(
                category="project-cache",
                path=path,
                authority_root=directory,
                identity=(status.st_dev, status.st_ino),
                byte_count=int(status.st_size),
                modified_ns=int(status.st_mtime_ns),
            )
            if not hmac.compare_digest(_cleanup_candidate_commitment(candidate), match.group("identity")):
                raise OSError("cleanup staging identity commitment changed")
            with _held_cleanup_candidate(candidate) as (_, delete_held):
                delete_held()
    except OSError, ValueError:
        raise _bounded(ObjectStoreProblem, "storage cleanup staging cannot be reconciled") from None


def _cleanup_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for partial-GC restart proof."""


def _storage_audit(
    state: _StoreState,
    event: str,
    request: StorageCleanupRequest,
    *,
    preview_token: str,
    byte_count: int,
    item_count: int,
    skipped_item_count: int = 0,
) -> None:
    try:
        logs = _canonical_directory(state.root / "logs", create=True)
        with _stable_directories([state.root, logs]):
            _atomic_audit_append(
                logs / "storage-maintenance.jsonl",
                {
                    "actorId": request.actor_id,
                    "byteCount": byte_count,
                    "categories": list(request.categories),
                    "event": event,
                    "itemCount": item_count,
                    "occurredAt": _now(),
                    "previewId": hashlib.sha256(preview_token.encode("ascii")).hexdigest()[:24],
                    "projectId": state.project_id,
                    "schemaVersion": "1.0",
                    "skippedItemCount": skipped_item_count,
                    "traceId": request.trace_id,
                },
            )
    except OSError, ProjectLifecycleProblem:
        raise _bounded(ObjectStoreProblem, "storage maintenance audit could not be written") from None


def _candidate_matches(candidate: _FileCandidate) -> bool:
    try:
        status = candidate.path.stat(follow_symlinks=False)
        return (
            stat.S_ISREG(status.st_mode)
            and status.st_nlink == 1
            and not _redirect(candidate.path)
            and (status.st_dev, status.st_ino) == candidate.identity
            and int(status.st_size) == candidate.byte_count
            and int(status.st_mtime_ns) == candidate.modified_ns
        )
    except OSError:
        return False


def _cleanup_partial_path(directory: Path, candidate: _FileCandidate) -> Path:
    return directory / f"cleanup-{secrets.token_hex(12)}-{_cleanup_candidate_commitment(candidate)}.partial"


def _cleanup_candidate_commitment(candidate: _FileCandidate) -> str:
    identity = ":".join(
        str(value) for value in (*candidate.identity, candidate.byte_count, candidate.modified_ns)
    ).encode("ascii")
    return base64.urlsafe_b64encode(hashlib.sha256(identity).digest()).rstrip(b"=").decode("ascii")


def _remove_rebuildable_candidate(state: _StoreState, candidate: _FileCandidate) -> bool:
    if not _candidate_matches(candidate):
        return False
    try:
        chain = _directory_chain(candidate.authority_root, candidate.path.parent)
        with _stable_directories(list(chain)):
            if not _candidate_matches(candidate):
                return False
            with _held_cleanup_candidate(candidate) as (rename_held, delete_held):
                if candidate.category == "shared-cache":
                    delete_held()
                    return True
                staging = _cleanup_staging_directory(state.temporary)
                with _stable_directories([state.root, state.temporary, staging]):
                    rename_held(_cleanup_partial_path(staging, candidate))
                    _cleanup_step_completed("after-rebuildable-move")
                    delete_held()
                    return True
    except OSError, ProjectLifecycleProblem:
        return False


class _LocalObjectStore:
    __slots__ = ("__token",)

    def __init__(self, state: _StoreState) -> None:
        self.__token = _STORES.register(state)

    def _state(self) -> _StoreState:
        return _STORES.state(self.__token)

    def usage(self) -> StorageUsage:
        state = self._state()
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            return _inventory(state).usage

    def preview_cleanup(self, request: StorageCleanupRequest) -> StorageCleanupPreview:
        request = _validate_cleanup_request(request)
        state = self._state()
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            inventory = _inventory(state)
            selected = frozenset(request.categories)
            token = secrets.token_hex(32)
            candidates = tuple(candidate for candidate in inventory.candidates if candidate.category in selected)
            state.cleanup_plan = _CleanupPlan(token=token, request=request, candidates=candidates)
            categories = tuple(entry for entry in inventory.usage.categories if entry.category in selected)
            return StorageCleanupPreview(
                preview_token=token,
                categories=categories,
                reclaimable_byte_count=sum(entry.reclaimable_byte_count for entry in categories),
                reclaimable_item_count=sum(entry.reclaimable_item_count for entry in categories),
            )

    def cleanup(self, preview_token: str) -> StorageCleanupResult:
        if not isinstance(preview_token, str) or re.fullmatch(r"[0-9a-f]{64}", preview_token) is None:
            raise _bounded(ObjectConflict, "storage cleanup preview is no longer current")
        state = self._state()
        with state.lock, _stable_directories([state.root, state.state, state.objects, state.temporary]):
            plan = state.cleanup_plan
            if plan is None or not hmac.compare_digest(plan.token, preview_token):
                raise _bounded(ObjectConflict, "storage cleanup preview is no longer current")
            state.cleanup_plan = None
            planned_bytes = sum(candidate.byte_count for candidate in plan.candidates)
            _storage_audit(
                state,
                "storage.cleanup.started",
                plan.request,
                preview_token=preview_token,
                byte_count=planned_bytes,
                item_count=len(plan.candidates),
            )
            reclaimed_bytes = 0
            reclaimed_items = 0
            skipped_items = 0
            try:
                for candidate in plan.candidates:
                    _cleanup_step_completed("before-candidate")
                    reclaimed = False
                    if candidate.object_sha256 is not None:
                        try:
                            self.delete(candidate.object_sha256)
                            reclaimed = True
                        except ObjectReferenced, ObjectBusy, ObjectNotFound, ObjectCorrupt:
                            reclaimed = False
                    else:
                        reclaimed = _remove_rebuildable_candidate(state, candidate)
                    if reclaimed:
                        reclaimed_bytes += candidate.byte_count
                        reclaimed_items += 1
                    else:
                        skipped_items += 1
                    _cleanup_step_completed("after-candidate")
            except ObjectStoreProblem:
                raise
            except Exception:
                raise _bounded(ObjectStoreProblem, "storage cleanup was interrupted and can be retried") from None
            _storage_audit(
                state,
                "storage.cleanup.completed",
                plan.request,
                preview_token=preview_token,
                byte_count=reclaimed_bytes,
                item_count=reclaimed_items,
                skipped_item_count=skipped_items,
            )
            usage_after = _inventory(state).usage
            return StorageCleanupResult(
                reclaimed_byte_count=reclaimed_bytes,
                reclaimed_item_count=reclaimed_items,
                skipped_item_count=skipped_items,
                usage_after=usage_after,
            )

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
            baseline_bytes = _inventory(state).usage.project_byte_count
            last_staged_bytes = 0

            def admit(prospective_staged_bytes: int) -> None:
                nonlocal last_staged_bytes
                policy = state.storage_policy
                projected = baseline_bytes + prospective_staged_bytes
                if policy.project_hard_limit_bytes is not None and projected > policy.project_hard_limit_bytes:
                    raise _bounded(ObjectStoragePressure, "project storage hard limit would be exceeded")
                disk = shutil.disk_usage(state.root)
                additional = max(0, prospective_staged_bytes - last_staged_bytes)
                if int(disk.free) - additional < policy.minimum_free_bytes:
                    raise _bounded(ObjectStoragePressure, "local disk reserve is unavailable")
                last_staged_bytes = prospective_staged_bytes

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
                        admission_check=admit,
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
                    UPDATE object_records SET verified_at=COALESCE(verified_at, ?)
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


def _prepare_store_state(
    project_root: Path,
    project_id: str,
    *,
    key_provider: ObjectMasterKeyProvider | None,
    allow_plaintext_fixture: bool,
    cancellation_requested: Callable[[str], bool] | None,
    storage_policy: StoragePolicy | None,
    shared_cache_root: Path | None,
) -> _StoreState:
    policy = _validate_storage_policy(storage_policy)
    path_failure: ObjectStoreProblem | None = None
    try:
        root, state_directory, objects, temporary = _canonical_root(Path(project_root))
    except OSError:
        path_failure = _bounded(ObjectStoreProblem, "project object-store authority is invalid")
        root = state_directory = objects = temporary = Path()
    if path_failure is not None:
        raise path_failure
    shared_cache: Path | None = None
    if shared_cache_root is not None:
        raw_shared = Path(shared_cache_root)
        try:
            if not raw_shared.is_absolute():
                raise OSError("shared-cache authority is relative")
            shared_cache = _canonical_directory(raw_shared)
            if shared_cache == root or shared_cache.is_relative_to(root) or root.is_relative_to(shared_cache):
                raise OSError("shared-cache authority overlaps project authority")
        except OSError:
            raise _bounded(ObjectStoreProblem, "shared-cache authority is invalid") from None
    database = state_directory / "project.sqlite3"
    migration_failure: ObjectStoreProblem | None = None
    try:
        from .migrations.runner import migrate_database

        with _stable_directories([root, state_directory, objects, temporary]):
            migrate_database(database, expected_project_id=project_id)
    except OSError, StorageProblem, ProjectLifecycleProblem:
        migration_failure = _bounded(
            ObjectStoreProblem,
            "project object-store schema upgrade did not complete",
        )
    if migration_failure is not None:
        raise migration_failure
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
    return _StoreState(
        root=root,
        state=state_directory,
        objects=objects,
        temporary=temporary,
        database=database,
        project_id=project_id,
        key_provider=key_provider,
        allow_plaintext_fixture=allow_plaintext_fixture,
        cancellation_requested=cancellation_requested,
        storage_policy=policy,
        shared_cache=shared_cache,
        cleanup_plan=None,
        lock=threading.RLock(),
    )


def _reconcile_store_state(store_state: _StoreState) -> None:
    staging_failure: ObjectStoreProblem | None = None
    try:
        staging = _staging_directory(store_state.temporary)
        with _stable_directories(
            [
                store_state.root,
                store_state.state,
                store_state.objects,
                store_state.temporary,
                staging,
            ]
        ):
            _reconcile_envelope_upgrades(staging, store_state)
            _reconcile_staging(staging, store_state)
            cleanup_staging = _cleanup_staging_directory(store_state.temporary)
            with _stable_directories([store_state.root, store_state.temporary, cleanup_staging]):
                _reconcile_cleanup_staging(cleanup_staging)
    except ObjectStoreProblem as problem:
        staging_failure = _bounded(type(problem), "object staging reconciliation failed")
    except OSError, ProjectLifecycleProblem:
        staging_failure = _bounded(ObjectStoreProblem, "object staging reconciliation failed")
    if staging_failure is not None:
        raise staging_failure


def upgrade_local_object_envelopes(
    project_root: Path,
    project_id: str,
    *,
    key_provider: ObjectMasterKeyProvider | None = None,
    cancellation_requested: Callable[[str], bool] | None = None,
) -> None:
    """Finish supported prior-envelope upgrades before ordinary project open."""

    if key_provider is not None and not isinstance(key_provider, ObjectMasterKeyProvider):
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    if cancellation_requested is not None and not callable(cancellation_requested):
        raise _bounded(ObjectStoreProblem, "object upgrade cancellation boundary is invalid")
    state = _prepare_store_state(
        project_root,
        project_id,
        key_provider=key_provider,
        allow_plaintext_fixture=False,
        cancellation_requested=cancellation_requested,
        storage_policy=None,
        shared_cache_root=None,
    )
    _reconcile_store_state(state)


def create_local_object_store(
    project_root: Path,
    project_id: str,
    *,
    key_provider: ObjectMasterKeyProvider | None = None,
    allow_plaintext_fixture: bool = False,
    storage_policy: StoragePolicy | None = None,
    shared_cache_root: Path | None = None,
) -> ObjectStore:
    """Create the project-local adapter behind the dependency-neutral port."""

    if not isinstance(allow_plaintext_fixture, bool):
        raise _bounded(ObjectStoreProblem, "plaintext fixture policy is invalid")
    if key_provider is None and not allow_plaintext_fixture:
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    if key_provider is not None and not isinstance(key_provider, ObjectMasterKeyProvider):
        raise _bounded(ObjectKeyUnavailable, "object encryption key is unavailable")
    store_state = _prepare_store_state(
        project_root,
        project_id,
        key_provider=key_provider,
        allow_plaintext_fixture=allow_plaintext_fixture,
        cancellation_requested=None,
        storage_policy=storage_policy,
        shared_cache_root=shared_cache_root,
    )
    _reconcile_store_state(store_state)
    return _LocalObjectStore(store_state)


__all__ = ["create_local_object_store", "upgrade_local_object_envelopes"]
