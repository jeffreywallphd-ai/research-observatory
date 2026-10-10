"""Closed bounded correction projections; no persistence or authority."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .document_corrections import CorrectionDraft, CorrectionLabel, HumanReferenceMatch
from .document_revisions import Instant
from .parsing.contracts import Digest, Identity, IRValue, ProjectIdentity, SourceIdentity, SourceLocator, Token

type Offset = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
type Preview = Annotated[str, Field(strict=True, max_length=160)]


class CorrectionNodeView(IRValue):
    node_id: Token
    parent_id: Token | None
    order: Offset
    kind: Token
    expected_node_sha256: Digest | None
    preview: Preview = Field(repr=False)
    label: Preview | None = Field(repr=False)
    text_start: Offset | None
    text_end: Offset | None
    locator: SourceLocator
    reference_id: Identity | None
    expected_reference_sha256: Digest | None
    state: Literal["accepted", "proposed"]

    @model_validator(mode="after")
    def authority(self):
        if (self.state == "accepted") != (self.expected_node_sha256 is not None) or (
            (self.reference_id is None) != (self.expected_reference_sha256 is None)
            or (self.text_start is None) != (self.text_end is None)
        ):
            raise ValueError("document-correction-view-invalid")
        return self


class CorrectionDraftView(IRValue):
    record: CorrectionDraft = Field(repr=False)
    confirmation_sha256: Digest


class CorrectionDraftSelector(IRValue):
    draft_revision_id: Identity
    base_revision_id: Identity


class CorrectionQueueItem(IRValue):
    job_id: Identity
    attachment_id: Identity
    revision_id: Identity | None


class CorrectionQueue(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    items: tuple[CorrectionQueueItem, ...] = Field(max_length=10)
    next_after_job_id: Identity | None


class CorrectionPage(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    source: SourceIdentity
    document_id: Identity
    revision_id: Identity
    current_revision_id: Identity
    accepted_by: Identity
    accepted_at: Instant
    machine_revision_id: Identity
    attachment_id: Identity
    job_id: Identity
    structure_sha256: Digest
    nodes: tuple[CorrectionNodeView, ...] = Field(max_length=20)
    preview_nodes: tuple[CorrectionNodeView, ...] = Field(max_length=20)
    next_offset: Offset | None
    draft: CorrectionDraftView | None = Field(repr=False)
    drafts: tuple[CorrectionDraftSelector, ...] = Field(max_length=10)
    accepted_labels: tuple[CorrectionLabel, ...] = Field(max_length=20)
    accepted_reference_matches: tuple[HumanReferenceMatch, ...] = Field(max_length=20)
    accepted_decision: CorrectionDraftView | None = Field(repr=False)
    scholarly_verification: Literal["unverified"] = "unverified"


class CorrectionAcceptedView(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    document_id: Identity
    revision_id: Identity
    previous_revision_id: Identity
    structure_sha256: Digest
    content_sha256: Digest
    decision_revision_id: Identity
    accepted_by: Identity
    accepted_at: Instant
    scholarly_verification: Literal["unverified"] = "unverified"


class CorrectionImpactItem(IRValue):
    revision_id: Identity
    kind: Token
    disposition: Literal["stale", "unknown-impact", "informational"]


class CorrectionImpactView(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    base_revision_id: Identity
    draft_revision_id: Identity
    graph_sha256: Digest
    affected_count: Offset
    informational_count: Offset
    legacy_unreported_count: Offset
    items: tuple[CorrectionImpactItem, ...] = Field(max_length=20)
    truncated: bool
    state: Literal["prospective-rechecked-at-acceptance"] = "prospective-rechecked-at-acceptance"


class CorrectionWorkTarget(IRValue):
    work_id: Identity
    work_revision_id: Identity
    title: Preview = Field(repr=False)
    scholarly_verification: Literal["unverified"] = "unverified"


class CorrectionWorkTargets(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    items: tuple[CorrectionWorkTarget, ...] = Field(max_length=10)
    next_after_work_id: Identity | None
