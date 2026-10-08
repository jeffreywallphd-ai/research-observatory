"""Inspect-only originals over existing canonical source and revision records."""

from collections.abc import Callable

from .document_revisions import DocumentRevisionProblem
from .domain_contracts import is_uuid_v7
from .ports.document_viewer import ViewerSourceMetadata, ViewerSourceSelector, ViewerTextChunk
from .ports.object_store import ObjectReadCancelled


class LocalDocumentViewerRepository:
    def __init__(self, revisions) -> None:
        self.revisions = revisions

    def describe(
        self, selector: ViewerSourceSelector, *, cancellation_requested: Callable[[], bool] = lambda: False
    ) -> ViewerSourceMetadata:
        selector = ViewerSourceSelector.model_validate(selector)

        def describe():
            source = self.revisions.source(selector.attachment_id)
            if source.document_revision_id != selector.document_revision_id:
                raise DocumentRevisionProblem("viewer-original-revision-mismatch")
            actor = self.revisions.actor()

            def current(connection):
                self.revisions._authority(connection, actor)
                if selector.normalized_revision_id is not None:
                    row = connection.execute(
                        "SELECT result_id,document_id FROM document_normalized_revisions "
                        "WHERE project_id=? AND revision_id=?",
                        (source.project_id, selector.normalized_revision_id),
                    ).fetchone()
                    if (
                        row is None
                        or row[1] != source.document_id
                        or self.revisions._receipt(connection, row[0]).binding.source != source
                    ):
                        raise DocumentRevisionProblem("viewer-normalized-source-mismatch")
                return ViewerSourceMetadata(source=source, normalized_revision_id=selector.normalized_revision_id)

            return self.revisions.objects._read_inspected_document_context(
                source, actor=actor, action=current, cancellation_requested=cancellation_requested
            )

        return self.revisions._bounded(describe)

    def read_range(
        self,
        selector: ViewerSourceSelector,
        *,
        start: int,
        end: int,
        cancellation_requested: Callable[[], bool] = lambda: False,
    ) -> bytes:
        def read():
            before = self.describe(selector, cancellation_requested=cancellation_requested)
            value = self.revisions.objects._read_inspected_document_range(
                before.source,
                start=start,
                end=end,
                actor=self.revisions.actor(),
                cancellation_requested=cancellation_requested,
            )
            # The source stream and transaction are closed. Never deliver a
            # successful old read after the exact current copy/rights changed.
            if self.describe(selector, cancellation_requested=cancellation_requested) != before:
                raise DocumentRevisionProblem("viewer-source-changed")
            if cancellation_requested() is not False:
                raise ObjectReadCancelled()
            return value

        return self.revisions._bounded(read)

    def _read_owned_range(
        self,
        selector: ViewerSourceSelector,
        expected: ViewerSourceMetadata,
        *,
        start: int,
        end: int,
        cancellation_requested: Callable[[], bool] = lambda: False,
    ) -> bytes:
        """Physical read for the service's mandatory fresh delivery fence.

        Expected metadata is request-local identity, never authorization. The
        owning service supplies a fresh actor/Intent/privacy scope, and the
        encrypted adapter verifies exact canonical source and current inspect
        rights inside its writer. Every waiter must separately validate current
        authority and full metadata after this stream/transaction has closed.
        Ordinary repository callers retain read_range's pre/post validation.
        """

        def read():
            selected = ViewerSourceSelector.model_validate(selector)
            metadata = ViewerSourceMetadata.model_validate(expected)
            if (
                metadata.source.project_id != self.revisions.project
                or metadata.source.attachment_id != selected.attachment_id
                or metadata.source.document_revision_id != selected.document_revision_id
                or metadata.normalized_revision_id != selected.normalized_revision_id
            ):
                raise DocumentRevisionProblem("viewer-source-changed")
            value = self.revisions.objects._read_inspected_document_range(
                metadata.source,
                start=start,
                end=end,
                actor=self.revisions.actor(),
                cancellation_requested=cancellation_requested,
            )
            if cancellation_requested() is not False:
                raise ObjectReadCancelled()
            return value

        return self.revisions._bounded(read)

    def text_chunk(self, selector: ViewerSourceSelector, *, node_id: str, offset: int) -> ViewerTextChunk:
        if not is_uuid_v7(node_id) or type(offset) is not int or not 0 <= offset <= 64 * 1024 * 1024:
            raise DocumentRevisionProblem("viewer-text-selection-invalid")

        def read():
            metadata = self.describe(selector)
            if metadata.normalized_revision_id is None:
                raise DocumentRevisionProblem("viewer-structured-revision-required")
            actor = self.revisions.actor()

            def current(connection):
                self.revisions._authority(connection, actor)
                accepted = self.revisions._accepted(connection, metadata.normalized_revision_id)
                if (
                    accepted.document_id != metadata.source.document_id
                    or accepted.result.binding.source != metadata.source
                ):
                    raise DocumentRevisionProblem("viewer-normalized-source-mismatch")
                nodes = [item for item in accepted.structure.nodes if item.node_id == node_id]
                if len(nodes) != 1:
                    raise DocumentRevisionProblem("viewer-text-selection-invalid")
                node = nodes[0]
                text = ""
                if node.text is not None:
                    projection = next(
                        item
                        for item in accepted.structure.text_projections
                        if item.projection_id == node.text.projection_id
                    )
                    span = node.text.normalized_range
                    if offset > span.end - span.start:
                        raise DocumentRevisionProblem("viewer-text-selection-invalid")
                    text = projection.normalized_text[span.start + offset : min(span.end, span.start + offset + 4096)]
                    next_offset = offset + len(text) if span.start + offset + len(text) < span.end else None
                elif offset != 0:
                    raise DocumentRevisionProblem("viewer-text-selection-invalid")
                else:
                    next_offset = None
                self.revisions._authority(connection, self.revisions.actor())
                return ViewerTextChunk(
                    metadata=metadata,
                    node_id=node.node_id,
                    node_kind=node.kind,
                    page_number=node.locator.page_index + 1 if node.locator.kind == "page-region" else None,
                    offset=offset,
                    text=text,
                    next_offset=next_offset,
                )

            result = self.revisions.objects._read_authorized_document_context(
                metadata.source, actor=actor, action=current
            )
            if self.describe(selector) != metadata:
                raise DocumentRevisionProblem("viewer-source-changed")
            # The artifact read has closed. Original metadata checks only
            # inspect permission; derivative delivery also needs fresh derive
            # permission and current human/Intent/privacy authority.
            current_actor = self.revisions.actor()
            self.revisions.objects._read_authorized_document_context(
                metadata.source,
                actor=current_actor,
                action=lambda connection: self.revisions._authority(connection, current_actor),
            )
            return result

        return self.revisions._bounded(read)
