"""Dependency-neutral content-addressed object-store port."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO, Literal, Protocol, runtime_checkable

from .corpus import CorpusActor

MAX_VIEWER_SOURCE_BYTES = 128 * 1024 * 1024
MAX_VIEWER_RANGE_BYTES = 1024 * 1024

RightsStatus = Literal["allowed", "denied", "unknown", "not-applicable"]
ObjectCreationSource = Literal[
    "local-import",
    "connector-acquisition",
    "local-derivation",
    "test-fixture",
    "legacy-unreported",
]
ObjectAccessPurpose = Literal[
    "reference-import",
    "document-analysis",
    "connector-plugin-execution",
    "test-verification",
    "storage-performance",
    "project-backup",
    "project-export",
    "provider-egress",
]
ObjectAccessClass = Literal["local-read", "controlled-egress"]
ObjectAccessOutcome = Literal["allow", "deny", "require-confirmation"]
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


class ObjectSourceTooLarge(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-SOURCE-TOO-LARGE"


class ObjectStagingCancelled(ObjectStoreProblem):
    code = "RO-CORE-OBJECT-STAGING-CANCELLED"


class ObjectReadCancelled(ObjectStoreProblem):
    """A trusted read stop signal denied access; ciphertext remains recoverable."""

    code = "RO-CORE-OBJECT-READ-CANCELLED"


class ObjectStagingCleanupRequired(ObjectStoreProblem):
    """An owned encrypted partial remains; intake cannot claim safe cleanup."""

    code = "RO-CORE-OBJECT-STAGING-CLEANUP-REQUIRED"


@dataclass(frozen=True, slots=True)
class ObjectPutCommand:
    """Caller-owned metadata for one immutable plaintext content identity."""

    media_type: str
    rights_status: RightsStatus
    protection_profile: str
    retention_class: RetentionClass
    creation_source: ObjectCreationSource
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
    creation_source: ObjectCreationSource
    storage_state: StorageState
    created_at: str
    verified_at: str | None
    reference_count: int
    envelope_version: str
    key_version: str | None
    ciphertext_byte_length: int


@dataclass(frozen=True, slots=True)
class ObjectAccessRequest:
    """Detached policy input; it contains no bytes or filesystem capability."""

    project_id: str
    object_metadata: StoredObject
    purpose: ObjectAccessPurpose
    access_class: ObjectAccessClass
    destination_id: str | None


@dataclass(frozen=True, slots=True)
class ObjectAccessDecision:
    """Bounded policy result. Only an exact ``allow`` may expose a stream."""

    outcome: ObjectAccessOutcome
    reason_code: str


@runtime_checkable
class ObjectAccessPolicy(Protocol):
    def authorize(self, request: ObjectAccessRequest) -> ObjectAccessDecision: ...


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
    def ensure_intake_ready(self) -> None:
        """Reject intake while earlier encrypted staging needs reconciliation."""
        ...

    def put(self, source: BinaryIO, command: ObjectPutCommand) -> StoredObject: ...

    def put_inspected(
        self,
        source: BinaryIO,
        command: ObjectPutCommand,
        inspector: Callable[[BinaryIO, str, int], str],
        *,
        max_plaintext_bytes: int,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> StoredObject: ...

    def open(
        self,
        object_sha256: str,
        *,
        purpose: str,
        access_class: ObjectAccessClass = "local-read",
        destination_id: str | None = None,
    ) -> VerifiedObjectStream: ...

    def open_document_attachment(
        self,
        attachment_id: str,
        document_revision_id: str,
        *,
        actor: CorpusActor,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> VerifiedObjectStream:
        """Read an exact inspected copy; an optional trusted stop applies until close.

        Authentication completes before the first byte. Cancellation closes and
        rolls back the owned reader without classifying healthy bytes as corrupt.
        The signal performs no I/O, permission checks or database operations.
        """
        ...

    def read_document_attachment_range(
        self,
        attachment_id: str,
        document_revision_id: str,
        *,
        start: int,
        end: int,
        actor: CorpusActor,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> bytes:
        """Authenticate an inspected original and return one bounded half-open range.

        The adapter discards any prefix in bounded chunks and closes its stream
        and transaction before return. This is sequential access, not O(1) seek.
        The caller still owns request admission and current-authority delivery.
        """
        ...

    def metadata(self, object_sha256: str) -> StoredObject: ...

    def delete(self, object_sha256: str) -> None: ...

    def usage(self) -> StorageUsage: ...

    def preview_cleanup(self, request: StorageCleanupRequest) -> StorageCleanupPreview: ...

    def cleanup(self, preview_token: str) -> StorageCleanupResult: ...


__all__ = [
    "MAX_VIEWER_RANGE_BYTES",
    "MAX_VIEWER_SOURCE_BYTES",
    "CleanupCategory",
    "ObjectAccessClass",
    "ObjectAccessDecision",
    "ObjectAccessDenied",
    "ObjectAccessOutcome",
    "ObjectAccessPolicy",
    "ObjectAccessPurpose",
    "ObjectAccessRequest",
    "ObjectBusy",
    "ObjectConflict",
    "ObjectCorrupt",
    "ObjectCreationSource",
    "ObjectIntegrityMismatch",
    "ObjectKeyUnavailable",
    "ObjectNotFound",
    "ObjectPutCommand",
    "ObjectReadCancelled",
    "ObjectReferenced",
    "ObjectSourceTooLarge",
    "ObjectStagingCancelled",
    "ObjectStagingCleanupRequired",
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
