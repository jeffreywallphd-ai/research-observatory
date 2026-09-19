"""Bounded immutable source replay through the existing protected object port.

The repository owns ordered chunk membership, full-source identity, project and
preview state. No file path, database, new cipher or canonical import lives here.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Callable
from dataclasses import dataclass

from ..ports.object_store import ObjectPutCommand, ObjectStore
from .import_drafts import ImportRights

CHUNK_BYTES = 128 * 1024
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_CHUNKS = MAX_SOURCE_BYTES // CHUNK_BYTES


@dataclass(frozen=True, slots=True)
class SourceChunk:
    object_sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        if not isinstance(self.object_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", self.object_sha256) is None:
            raise ValueError("invalid-source-chunk-digest")
        if type(self.byte_length) is not int or not 0 < self.byte_length <= CHUNK_BYTES:
            raise ValueError("source-chunk-limit")


def put_source_chunk(store: ObjectStore, data: bytes, *, rights: ImportRights, created_at: str) -> SourceChunk:
    """Retain only an explicitly authorized, bounded native intake chunk.

    Object-level allowed is limited to this store/inspect decision. The repository
    retains all independent action permissions; it does not become export/model
    permission. A completed put alone is not source membership or parse success.
    """
    rights = ImportRights.model_validate(rights)
    if not rights.permits("store"):
        raise ValueError("import-store-denied")
    if not rights.permits("inspect"):
        raise ValueError("import-inspect-denied")
    if not isinstance(data, bytes) or not 0 < len(data) <= CHUNK_BYTES:
        raise ValueError("source-chunk-limit")
    digest = hashlib.sha256(data).hexdigest()
    stored = store.put(
        io.BytesIO(data),
        ObjectPutCommand(
            media_type="application/octet-stream",
            rights_status="allowed",
            protection_profile="project-encrypted-v1",
            retention_class="project-lifetime",
            creation_source="local-import",
            created_at=created_at,
            expected_sha256=digest,
        ),
    )
    if stored.object_sha256 != digest or stored.byte_length != len(data):
        raise ValueError("source-chunk-publication-mismatch")
    return SourceChunk(digest, stored.byte_length)


class ChunkedImportSource:
    """Close each verified object before returning bytes to the parser.

    The canonical object reader retains its rights/write barrier while decrypting
    at most one chunk. Record-page persistence, queue heartbeat and cancellation
    therefore do not inherit a long-lived SQLite writer reservation. Authorization
    is checked even for buffered bytes; denial permanently clears this reader.
    """

    def __init__(self, store: ObjectStore, chunks: tuple[SourceChunk, ...], *, authorize: Callable[[], ImportRights]):
        if (
            not isinstance(chunks, tuple)
            or len(chunks) > MAX_CHUNKS
            or any(not isinstance(c, SourceChunk) for c in chunks)
        ):
            raise ValueError("source-chunk-limit")
        if any(c.byte_length != CHUNK_BYTES for c in chunks[:-1]):
            raise ValueError("source-chunk-order")
        self._store, self._chunks, self._authorize = store, chunks, authorize
        self._ordinal = 0
        self._buffer = b""
        self._position = 0
        self._closed = False

    def close(self) -> None:
        self._closed = True
        self._buffer = b""
        self._position = 0

    def _check(self) -> None:
        if self._closed:
            raise ValueError("source-closed")
        rights = ImportRights.model_validate(self._authorize())
        if not rights.permits("inspect"):
            raise ValueError("import-inspect-denied")

    def read(self, size: int = -1) -> bytes:
        if type(size) is not int or not 0 <= size <= CHUNK_BYTES:
            raise ValueError("source-read-limit")
        try:
            self._check()
            if size == 0:
                return b""
            if self._position == len(self._buffer):
                self._buffer = b""
                self._position = 0
                if self._ordinal == len(self._chunks):
                    return b""
                chunk = self._chunks[self._ordinal]
                with self._store.open(chunk.object_sha256, purpose="reference-import") as stream:
                    data = stream.read(CHUNK_BYTES + 1)
                    if len(data) != chunk.byte_length or stream.read(1):
                        raise ValueError("source-chunk-length")
                    if hashlib.sha256(data).hexdigest() != chunk.object_sha256:
                        raise ValueError("source-chunk-digest")
                self._check()
                self._buffer = data
                self._ordinal += 1
            end = min(self._position + size, len(self._buffer))
            result = self._buffer[self._position : end]
            self._position = end
            return result
        except Exception:
            self.close()
            raise
