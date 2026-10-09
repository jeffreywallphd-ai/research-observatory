"""Opaque source-viewer selections; never paths, credentials or claimed rights."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..models import ContractModel
from ..parsing.contracts import Identity, NodeKind, ProjectIdentity, SourceIdentity
from .object_store import MAX_VIEWER_SOURCE_BYTES


class ViewerSourceSelector(ContractModel):
    attachment_id: Identity
    document_revision_id: Identity
    normalized_revision_id: Identity | None = None


class ViewerDeepLink(ContractModel):
    """Portable selection, reauthorized after explicit project open/unlock."""

    schema_version: Literal["1.0"]
    project_id: ProjectIdentity
    selector: ViewerSourceSelector
    anchor_ids: Annotated[tuple[Identity, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def exact_selection(self) -> Self:
        if (
            self.selector.normalized_revision_id is None
            or self.selector.normalized_revision_id == self.selector.document_revision_id
            or len(set(self.anchor_ids)) != len(self.anchor_ids)
        ):
            raise ValueError("viewer-link-selection-invalid")
        return self


class ViewerSourceMetadata(ContractModel):
    source: SourceIdentity
    normalized_revision_id: Identity | None = None

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.source.byte_length > MAX_VIEWER_SOURCE_BYTES:
            raise ValueError("viewer-source-limit")
        if self.normalized_revision_id == self.source.document_revision_id:
            raise ValueError("viewer-normalized-revision-invalid")
        return self


class ViewerTextChunk(ContractModel):
    metadata: ViewerSourceMetadata
    node_id: Identity
    node_kind: NodeKind
    page_number: Annotated[int, Field(strict=True, ge=1, le=500)] | None
    offset: Annotated[int, Field(strict=True, ge=0)]
    text: Annotated[str, Field(max_length=4096, repr=False)]
    next_offset: Annotated[int, Field(strict=True, ge=0)] | None
