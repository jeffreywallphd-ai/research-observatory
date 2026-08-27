"""Windows current-user DPAPI adapter for the local profile credential port."""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import struct
import threading
import uuid
from contextlib import contextmanager, suppress
from ctypes import wintypes
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from nacl import bindings as sodium
from nacl.exceptions import CryptoError

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
_LOCAL_APP_DATA = uuid.UUID("f1b32785-6fba-4fcf-9d55-7b8e7f157091")


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
        root_file, _records = self._ensure_root()
        if not root_file.exists():
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


__all__ = [
    "WindowsCredentialStore",
    "WindowsCurrentUserDataProtector",
    "WindowsDatabaseKeyProvider",
    "WindowsObjectMasterKeyProvider",
    "create_windows_database_key_provider",
    "create_windows_object_key_provider",
    "default_windows_profile_vault_path",
]
