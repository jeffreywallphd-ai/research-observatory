"""Portable exact-revision anchor/reader port; no paths or database connections."""

from typing import Protocol

from ..anchors.contracts import AnchorSelection, DocumentReaderOutline, DocumentReaderRevisions, SourceAnchorReceipt


class SourceAnchorRepository(Protocol):
    def reader_revisions(self, attachment_id: str) -> DocumentReaderRevisions: ...

    def create(self, command_id: str, selection: AnchorSelection) -> SourceAnchorReceipt: ...

    def read(self, anchor_id: str) -> SourceAnchorReceipt: ...

    def list(self, revision_id: str, *, limit: int = 100, after_id: str | None = None) -> tuple[str, ...]: ...

    def outline(
        self, revision_id: str, *, after_node_id: str | None = None, limit: int = 50
    ) -> DocumentReaderOutline: ...
