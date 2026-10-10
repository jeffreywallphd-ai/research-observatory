"""Source action values; permission review and Native execution remain distinct."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..anchors.contracts import MAX_QUOTE_CODEPOINTS, CoordinatesState, NormalizedPageRegion, SourceDocumentMetadata
from ..models import ContractModel
from ..parsing.contracts import CodepointRange, ConfidenceObservation, Digest, Identity, NodeKind, SourceIdentity
from ..rights_policy import Code, DecisionCode, RightsUse
from .document_viewer import ViewerSourceMetadata, ViewerSourceSelector

type ViewerAction = Literal[
    "copy-quotation", "print-quotation", "export-quotation", "export-annotation", "open-external-original"
]


class ViewerActionRequest(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    selector: ViewerSourceSelector
    action: ViewerAction
    anchor_id: Identity | None = None

    @model_validator(mode="after")
    def original_selection(self) -> Self:
        if self.action == "open-external-original" and self.anchor_id is not None:
            raise ValueError("viewer-action-selection-invalid")
        return self


class ViewerUseDecision(ContractModel):
    use: RightsUse
    code: DecisionCode
    reason_code: Code


class ViewerPolicyDecision(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    metadata: ViewerSourceMetadata
    action: ViewerAction
    anchor_id: Identity | None
    policy_revision_id: Identity | None
    state: Literal["ready", "review-required", "denied", "unavailable"]
    reason_code: Code
    can_review: bool
    requirements: Annotated[tuple[ViewerUseDecision, ...], Field(min_length=2, max_length=4)]
    selection_limit_codepoints: Literal[2048] = 2048


class ViewerRightsReviewReceipt(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    metadata: ViewerSourceMetadata
    action: ViewerAction
    policy_revision_id: Identity
    status: Literal["recorded"] = "recorded"


class ViewerOutputIdentity(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    source: SourceIdentity
    normalized_revision_id: Identity | None
    policy_revision_id: Identity
    scholarly_verification: Literal["unverified"] = "unverified"
    policy_basis: Annotated[tuple[ViewerUseDecision, ...], Field(min_length=2, max_length=4)]


class ViewerQuotationOutput(ViewerOutputIdentity):
    action: Literal["copy-quotation", "print-quotation", "export-quotation"]
    normalized_revision_id: Identity
    anchor_id: Identity
    anchor_revision_id: Identity
    text: Annotated[str, Field(strict=True, min_length=1, max_length=MAX_QUOTE_CODEPOINTS)] = Field(repr=False)
    text_position: CodepointRange
    citation_metadata: SourceDocumentMetadata

    @model_validator(mode="after")
    def exact_identity(self) -> Self:
        if (
            self.citation_metadata.project_id != self.source.project_id
            or self.citation_metadata.document_id != self.source.document_id
            or self.citation_metadata.revision_id != self.normalized_revision_id
            or self.text_position.end - self.text_position.start != len(self.text)
            or "\0" in self.text
        ):
            raise ValueError("viewer-quotation-identity-invalid")
        return self


class ViewerAnnotationOutput(ViewerOutputIdentity):
    action: Literal["export-annotation"]
    normalized_revision_id: Identity
    anchor_id: Identity
    anchor_revision_id: Identity
    node_id: Identity
    node_kind: NodeKind
    text_position: CodepointRange | None
    page_region: NormalizedPageRegion | None
    confidence: ConfidenceObservation
    coordinates_state: CoordinatesState


class ViewerOriginalHandoff(ViewerOutputIdentity):
    action: Literal["open-external-original"]


class ViewerActionPayload(ContractModel):
    """Private Native handoff, never a renderer response or reusable grant."""

    schema_version: Literal["1.0"] = "1.0"
    metadata: ViewerSourceMetadata
    action: ViewerAction
    anchor_id: Identity | None
    anchor_revision_id: Identity | None
    policy_revision_id: Identity
    authority_sha256: Digest
    content_sha256: Digest
    content_utf8: Annotated[str, Field(strict=True, max_length=65536)] = Field(repr=False)
