"""Authenticated delivery from the isolated inspection-only PDF operation."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..parsing.contracts import ParserDescriptor, RawParserArtifact
from ..parsing.requests import ParseRequest
from .parsing import ReadOnlyDocumentSource


@dataclass(frozen=True, slots=True)
class AuthenticatedInspectionDelivery:
    wire: bytes
    producer: ParserDescriptor
    job_id: str
    attempt_id: str
    artifact_receipt: RawParserArtifact


class PdfInspectionWorkerPort(Protocol):
    def parse_source(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedInspectionDelivery: ...
