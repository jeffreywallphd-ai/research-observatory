"""Portable exact-revision anchor/reader port; no paths or database connections."""

from typing import Protocol

from ..anchors.contracts import (
    AnchorSelection,
    CitationLinkResolution,
    DocumentReaderOutline,
    DocumentReaderRevisions,
    SourceAnchorReceipt,
    SourceAnchorResolution,
)


class SourceAnchorRepository(Protocol):
    def reader_revisions(self, attachment_id: str) -> DocumentReaderRevisions: ...

    def create(self, command_id: str, selection: AnchorSelection) -> SourceAnchorReceipt: ...

    def read(self, anchor_id: str) -> SourceAnchorReceipt: ...

    def resolve(self, anchor_id: str, *, expected_revision_id: str) -> SourceAnchorResolution: ...

    def citation_links(
        self, revision_id: str, citation_id: str, *, after_reference_id: str | None = None, limit: int = 2
    ) -> CitationLinkResolution: ...

    def list(self, revision_id: str, *, limit: int = 100, after_id: str | None = None) -> tuple[str, ...]: ...

    def outline(
        self, revision_id: str, *, after_node_id: str | None = None, limit: int = 50
    ) -> DocumentReaderOutline: ...
