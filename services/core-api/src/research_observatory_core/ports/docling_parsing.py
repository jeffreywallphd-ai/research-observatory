"""Parent-owned raw receipt for the pinned isolated Docling worker."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..parsing.contracts import ParserDescriptor, RawParserArtifact
from ..parsing.requests import ParseRequest
from .parsing import ReadOnlyDocumentSource


@dataclass(frozen=True, slots=True)
class AuthenticatedDoclingDelivery:
    wire: bytes
    producer: ParserDescriptor
    job_id: str
    attempt_id: str
    artifact_receipt: RawParserArtifact


class DoclingWorkerPort(Protocol):
    def parse_source(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedDoclingDelivery: ...
