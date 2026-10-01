"""Core-owned, retry-safe rights drafts and protected rights repository port."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field

from ..ingestion.import_drafts import DraftValue, Identity
from ..rights_policy import (
    Confidence,
    PermissionValue,
    ProvenanceBasis,
    RightsDecision,
    RightsPolicyRevision,
    RightsRequest,
    RightsSubject,
    RightsUse,
    UtcMillis,
)
from .corpus import CorpusActor

RightsActor = CorpusActor


class RightsProblem(RuntimeError):
    """Content-free denial or integrity failure for the rights port."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RightsPermissionDraft(DraftValue):
    """Semantic request without repository-minted identity or recorded time."""

    use: RightsUse
    value: PermissionValue
    basis: ProvenanceBasis
    confidence: Confidence
    grantee_actor_id: Identity | None = None
    evidence_revision_ids: tuple[Identity, ...] = Field(max_length=16)
    license_observation_revision_id: Identity | None = None
    entitlement_revision_id: Identity | None = None
    expires_at: UtcMillis | None = None
    confirmation_required: bool = False


class RightsRecheckScope(DraftValue):
    """Durable propagation disposition for one exact source/copy policy revision."""

    rights_revision_id: Identity
    subject: RightsSubject
    exact_state: Literal["complete", "pending"]
    generic_state: Literal["complete", "pending"]
    disposition: Literal["complete", "pending"]
    pending_reason: Literal["exact-limit", "generic-limit", "exact-and-generic-limit"] | None
    reason: Literal["RIGHTS_POLICY"]
    occurred_at: UtcMillis


class RightsOutputRecheckMarker(DraftValue):
    """A source-rights review marker, without invented dependency-run authority."""

    marker_id: str = Field(
        min_length=36,
        max_length=71,
        pattern=r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|legacy:[0-9a-f]{64})$",
    )
    kind: Literal["exact", "generic", "legacy"]
    rights_revision_id: Identity | None
    source_assertion_revision_id: Identity | None
    path_id: Identity | None
    reason: Literal["RIGHTS_POLICY"]
    disposition: Literal["requires-review"]
    occurred_at: UtcMillis


class RightsOutputRecheckState(DraftValue):
    """Bounded protected inspection; unknown propagation must be treated as pending."""

    output_revision_id: Identity
    markers: tuple[RightsOutputRecheckMarker, ...] = Field(max_length=100)
    propagation_pending: bool
    propagation_unknown: bool
    truncated: bool


class RightsRepository(Protocol):
    def publish_draft(
        self,
        subject: RightsSubject,
        permissions: tuple[RightsPermissionDraft, ...],
        expected_predecessor_revision_id: str | None,
        *,
        command_id: str,
        command_sha256: str,
        actor: RightsActor,
    ) -> RightsPolicyRevision: ...

    def current(self, subject: RightsSubject, *, actor: RightsActor) -> RightsPolicyRevision | None: ...

    def evaluate(self, request: RightsRequest, *, actor: RightsActor) -> RightsDecision: ...

    def recheck_scope(self, subject: RightsSubject, *, actor: RightsActor) -> RightsRecheckScope | None: ...

    def advance_rechecks(
        self, subject: RightsSubject, *, actor: RightsActor, batch_size: int = 1_000
    ) -> RightsRecheckScope | None: ...

    def output_rechecks(self, output_revision_id: str, *, actor: RightsActor) -> RightsOutputRecheckState: ...


__all__ = [
    "RightsActor",
    "RightsOutputRecheckMarker",
    "RightsOutputRecheckState",
    "RightsPermissionDraft",
    "RightsRecheckScope",
    "RightsRepository",
]
