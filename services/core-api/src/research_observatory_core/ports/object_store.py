"""Dependency-neutral content-addressed object-store port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Literal, Protocol, runtime_checkable

RightsStatus = Literal["allowed", "denied", "unknown", "not-applicable"]
RetentionClass = Literal["project-lifetime", "derived-rebuildable", "export-retained"]
StorageState = Literal["pending", "available", "quarantined", "deleted"]


class ObjectStoreProblem(RuntimeError):
    """Bounded object-store failure without paths or research content."""

    code = "RO-CORE-OBJECT-STORE-FAILED"

    def __init__(self, message: str = "local object operation failed") -> None:
        super().__init__(message)


class ObjectNotFound(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-NOT-FOUND"


class ObjectConflict(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-CONFLICT"


class ObjectIntegrityMismatch(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-INTEGRITY-MISMATCH"


class ObjectCorrupt(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-CORRUPT"


class ObjectReferenced(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-REFERENCED"


class ObjectAccessDenied(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-ACCESS-DENIED"


class ObjectBusy(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-BUSY"


class ObjectKeyUnavailable(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-KEY-UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ObjectPutCommand:
    """Caller-owned metadata for one immutable plaintext content identity."""

    media_type: str
    rights_status: RightsStatus
    protection_profile: str
    retention_class: RetentionClass
    created_at: str
    expected_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Detached metadata projection; it never exposes a filesystem path."""

    object_sha256: str
    byte_length: int
    media_type: str
    rights_status: RightsStatus
    protection_profile: str
    retention_class: RetentionClass
    storage_state: StorageState
    created_at: str
    verified_at: str | None
    reference_count: int
    envelope_version: str
    key_version: str | None
    ciphertext_byte_length: int


@runtime_checkable
class VerifiedObjectStream(Protocol):
    """Controlled verified stream without a decrypted-path capability."""

    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...

    def __enter__(self) -> VerifiedObjectStream: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


@runtime_checkable
class ObjectStore(Protocol):
    def put(self, source: BinaryIO, command: ObjectPutCommand) -> StoredObject: ...

    def open(self, object_sha256: str, *, purpose: str) -> VerifiedObjectStream: ...

    def metadata(self, object_sha256: str) -> StoredObject: ...

    def delete(self, object_sha256: str) -> None: ...


__all__ = [
    "ObjectAccessDenied",
    "ObjectBusy",
    "ObjectConflict",
    "ObjectCorrupt",
    "ObjectIntegrityMismatch",
    "ObjectKeyUnavailable",
    "ObjectNotFound",
    "ObjectPutCommand",
    "ObjectReferenced",
    "ObjectStore",
    "ObjectStoreProblem",
    "RetentionClass",
    "RightsStatus",
    "StorageState",
    "StoredObject",
    "VerifiedObjectStream",
]
