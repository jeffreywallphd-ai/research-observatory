"""Parent-authenticated native worker handoff; raw JSON confers no authority."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..parsing.contracts import ParserDescriptor, RawParserArtifact
from ..parsing.requests import ParseRequest
from .parsing import ReadOnlyDocumentSource


@dataclass(frozen=True, slots=True)
class AuthenticatedNativeDelivery:
    wire: bytes
    producer: ParserDescriptor
    job_id: str
    attempt_id: str
    artifact_receipt: RawParserArtifact


class NativeStructureWorkerPort(Protocol):
    def parse_source(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedNativeDelivery: ...
