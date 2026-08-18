"""Dependency-neutral content-addressed object-store port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Literal, Protocol, runtime_checkable

RightsStatus = Literal["allowed", "denied", "unknown", "not-applicable"]
RetentionClass = Literal["project-lifetime", "derived-rebuildable", "export-retained"]
StorageState = Literal["pending", "available", "quarantined", "deleted"]
CleanupCategory = Literal[
    "derived-objects",
    "orphaned-objects",
    "indexes",
    "project-cache",
    "models",
    "shared-cache",
]
StorageCategory = Literal[
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
]
StoragePressure = Literal["normal", "soft-limit", "hard-limit", "low-disk"]
CleanupConsequence = Literal["retained", "recomputed", "redownloaded", "metadata-repair"]


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


class ObjectStoragePressure(ObjectStoreProblem):
    """A hard quota, low-disk reserve, or stale cleanup lease denied mutation."""

    code = "RO-CORE-OBJECT-STORAGE-PRESSURE"


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


@dataclass(frozen=True, slots=True)
class StoragePolicy:
    """Deployment-supplied byte thresholds; ``None`` leaves a quota unbounded."""

    project_soft_limit_bytes: int | None = None
    project_hard_limit_bytes: int | None = None
    shared_cache_soft_limit_bytes: int | None = None
    shared_cache_hard_limit_bytes: int | None = None
    minimum_free_bytes: int = 512 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class StorageCleanupRequest:
    """Attributable selection for a non-destructive cleanup preview."""

    categories: tuple[CleanupCategory, ...]
    requested_at: str
    trace_id: str
    actor_id: str


@dataclass(frozen=True, slots=True)
class StorageUsageCategory:
    category: StorageCategory
    byte_count: int
    item_count: int
    reclaimable_byte_count: int
    reclaimable_item_count: int
    cleanup_consequence: CleanupConsequence


@dataclass(frozen=True, slots=True)
class StorageUsage:
    project_byte_count: int
    shared_cache_byte_count: int
    free_byte_count: int
    project_soft_limit_bytes: int | None
    project_hard_limit_bytes: int | None
    shared_cache_soft_limit_bytes: int | None
    shared_cache_hard_limit_bytes: int | None
    project_pressure: StoragePressure
    shared_cache_pressure: StoragePressure
    categories: tuple[StorageUsageCategory, ...]


@dataclass(frozen=True, slots=True)
class StorageCleanupPreview:
    preview_token: str
    categories: tuple[StorageUsageCategory, ...]
    reclaimable_byte_count: int
    reclaimable_item_count: int


@dataclass(frozen=True, slots=True)
class StorageCleanupResult:
    reclaimed_byte_count: int
    reclaimed_item_count: int
    skipped_item_count: int
    usage_after: StorageUsage


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

    def usage(self) -> StorageUsage: ...

    def preview_cleanup(self, request: StorageCleanupRequest) -> StorageCleanupPreview: ...

    def cleanup(self, preview_token: str) -> StorageCleanupResult: ...


__all__ = [
    "CleanupCategory",
    "ObjectAccessDenied",
    "ObjectBusy",
    "ObjectConflict",
    "ObjectCorrupt",
    "ObjectIntegrityMismatch",
    "ObjectKeyUnavailable",
    "ObjectNotFound",
    "ObjectPutCommand",
    "ObjectReferenced",
    "ObjectStoragePressure",
    "ObjectStore",
    "ObjectStoreProblem",
    "RetentionClass",
    "RightsStatus",
    "StorageCategory",
    "StorageCleanupPreview",
    "StorageCleanupRequest",
    "StorageCleanupResult",
    "StoragePolicy",
    "StoragePressure",
    "StorageState",
    "StorageUsage",
    "StorageUsageCategory",
    "StoredObject",
    "VerifiedObjectStream",
]
