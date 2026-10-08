"""Opaque source-viewer selections; never paths, credentials or claimed rights."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from ..models import ContractModel
from ..parsing.contracts import Identity, NodeKind, SourceIdentity
from .object_store import MAX_VIEWER_SOURCE_BYTES


class ViewerSourceSelector(ContractModel):
    attachment_id: Identity
    document_revision_id: Identity
    normalized_revision_id: Identity | None = None


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
