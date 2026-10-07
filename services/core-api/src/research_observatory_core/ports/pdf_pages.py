"""One protected PDF page derivative, without paths or whole-document surfaces."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from ..parsing.contracts import ParseBinding, ParserDescriptor, RawParserArtifact
from ..parsing.pdf_geometry import PdfPageGeometry
from ..parsing.requests import ParseRequest
from .parsing import ReadOnlyDocumentSource


@dataclass(frozen=True, slots=True)
class AuthenticatedPageDelivery:
    wire: bytes = field(repr=False)
    producer: ParserDescriptor
    job_id: str
    attempt_id: str
    page_index: int
    artifact_receipt: RawParserArtifact


@dataclass(frozen=True, slots=True)
class PagePreview:
    binding: ParseBinding
    page_index: int
    width_pixels: int
    height_pixels: int
    geometry: PdfPageGeometry
    artifact: RawParserArtifact
    png: bytes = field(repr=False)


class PdfPageWorkerPort(Protocol):
    def render_page(
        self, request: ParseRequest, source: ReadOnlyDocumentSource, page_index: int, *, cancelled: Callable[[], bool]
    ) -> AuthenticatedPageDelivery: ...
