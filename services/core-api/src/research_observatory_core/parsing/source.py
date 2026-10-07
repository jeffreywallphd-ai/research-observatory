"""Core-owned protected source read and delivery; downstream sees only ports.

Read/verify under current session and writer authority, close the transaction,
then run parsing against bounded private memory. Recheck current source/rights
and the same trusted session before exposing a usable staged IR. No disk cache.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import suppress
from typing import cast

from ..ports.corpus import CorpusActor
from ..ports.document_attachments import AttachmentCandidate, DocumentAttachment, DocumentPublicationGuard
from ..ports.object_store import ObjectStore
from ..ports.parsing import ParseProblem, ParseSourceObjectStore
from .contracts import AcquisitionOrigin, LocalOrigin, SourceIdentity


def source_identity(
    attachment: DocumentAttachment,
    candidate: AttachmentCandidate,
    provenance: LocalOrigin | AcquisitionOrigin,
) -> SourceIdentity:
    paired = (
        "candidate_id",
        "source_assertion_revision_id",
        "work_id",
        "work_revision_id",
        "version_id",
        "version_revision_id",
        "object_sha256",
    )
    if any(getattr(attachment, field) != getattr(candidate, field) for field in paired):
        raise ParseProblem("parse-source-denied")
    result = None
    with suppress(ValueError):
        result = SourceIdentity.model_validate(
            {
                "project_id": candidate.project_id,
                "attachment_id": attachment.attachment_id,
                "document_id": attachment.document_id,
                "document_revision_id": attachment.document_revision_id,
                "candidate_id": candidate.candidate_id,
                "source_assertion_revision_id": candidate.source_assertion_revision_id,
                "work_id": candidate.work_id,
                "work_revision_id": candidate.work_revision_id,
                "version_id": candidate.version_id,
                "version_revision_id": candidate.version_revision_id,
                "object_sha256": candidate.object_sha256,
                "byte_length": candidate.byte_length,
                "format": candidate.format,
                "provenance": provenance,
            }
        )
    if result is None:
        raise ParseProblem("parse-source-denied")
    return result


class _ReadOnlyMemory:
    __slots__ = ("__data", "__offset")

    def __init__(self, data: bytes) -> None:
        self.__data = data
        self.__offset = 0

    def read(self, size: int = -1) -> bytes:
        if type(size) is not int or size < -1:
            raise ParseProblem("parse-source-denied")
        end = len(self.__data) if size == -1 else min(len(self.__data), self.__offset + size)
        result = self.__data[self.__offset : end]
        self.__offset = end
        return result

    def close(self) -> None:
        self.__data = b""
        self.__offset = 0

    def __enter__(self) -> _ReadOnlyMemory:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


class LocalProtectedParseSource:
    def __init__(self, objects: ObjectStore, *, guard: DocumentPublicationGuard) -> None:
        if not isinstance(objects, ParseSourceObjectStore) or not callable(guard):
            raise ParseProblem("parse-source-denied")
        self._objects = cast(ParseSourceObjectStore, objects)
        self._guard = guard

    def read_source(
        self,
        source: SourceIdentity,
        *,
        actor: CorpusActor,
        cancelled: Callable[[], bool],
    ) -> _ReadOnlyMemory:
        value = None
        try:
            source = SourceIdentity.model_validate(source)

            def read() -> bytes:
                if cancelled():
                    raise ParseProblem("parse-source-denied")
                data = bytearray()
                digest = hashlib.sha256()
                with self._objects.open_parse_source(source, actor=actor) as stream:
                    while True:
                        if cancelled():
                            raise ParseProblem("parse-source-denied")
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        if len(data) + len(chunk) > source.byte_length:
                            raise ParseProblem("parse-source-denied")
                        data.extend(chunk)
                        digest.update(chunk)
                if len(data) != source.byte_length or digest.hexdigest() != source.object_sha256:
                    raise ParseProblem("parse-source-denied")
                return bytes(data)

            value = self._guard(read)
        except Exception:
            pass
        if value is None:
            raise ParseProblem("parse-source-denied")
        return _ReadOnlyMemory(value)

    def deliver[Result](self, source: SourceIdentity, *, actor: CorpusActor, action: Callable[[], Result]) -> Result:
        # Validation/output formatting happens before this short delivery fence.
        # A full protected-source authentication is repeated here, without
        # copying source bytes or retaining a writer during parser execution.
        def current() -> Result:
            source_current = SourceIdentity.model_validate(source)
            with self._objects.open_parse_source(source_current, actor=actor):
                return action()

        return self._guard(current)
