"""Parser receives read-only data and values, never repositories or raw paths."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..parsing.contracts import ParserDescriptor, RawParserArtifact, SourceIdentity
from ..parsing.requests import ParseRequest
from ..ports.object_store import VerifiedObjectStream
from .corpus import CorpusActor


class ParseProblem(ValueError):
    """Only a content-free Core code may cross this boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReadOnlyDocumentSource(Protocol):
    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...

    def __enter__(self) -> ReadOnlyDocumentSource: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


@dataclass(frozen=True, slots=True)
class AuthenticatedParseDelivery:
    """Parent-owned receipt from the selected runtime, distinct from worker JSON.

    The real isolated launcher authenticates producer/job/attempt and hashes
    received artifacts. Worker-echoed fields cannot construct this authority.
    Synthetic parser doubles can exercise this port without qualifying a worker.
    """

    wire: bytes
    producer: ParserDescriptor
    job_id: str
    attempt_id: str
    artifact_receipts: tuple[RawParserArtifact, ...]


class DocumentParserPort(Protocol):
    def parse(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedParseDelivery: ...


class ProtectedParseSourcePort(Protocol):
    def read_source(
        self, source: SourceIdentity, *, actor: CorpusActor, cancelled: Callable[[], bool]
    ) -> AbstractContextManager[ReadOnlyDocumentSource]: ...

    def deliver[Result](
        self, source: SourceIdentity, *, actor: CorpusActor, action: Callable[[], Result]
    ) -> Result: ...


@runtime_checkable
class ParseSourceObjectStore(Protocol):
    """Additive protected-read facet, without changing legacy object-store consumers."""

    def open_parse_source(self, source: SourceIdentity, *, actor: CorpusActor) -> VerifiedObjectStream: ...
