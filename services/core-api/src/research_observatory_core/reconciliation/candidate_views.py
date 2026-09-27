"""Bounded historical evidence pages with explicit current-state warnings."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from .candidate_sets import CandidateExplanation
from .candidates import DEFAULT_CONFIG
from .identifiers import NORMALIZER_VERSION


class CandidatePage(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    set_revision_id: Identity
    request_id: Identity
    inventory_sha256: Digest
    current_inventory_sha256: Digest
    inventory_state: Literal["unchanged", "changed"]
    record_count: Annotated[int, Field(strict=True, ge=0, le=10000)]
    candidate_count: Annotated[int, Field(strict=True, ge=0, le=20000)]
    compared_pairs: Annotated[int, Field(strict=True, ge=0, le=250000)]
    membership_state: Literal["unchanged", "changed"]
    dependency_state: Literal["unaffected", "requires-review"]
    algorithm: Literal["scholarly-duplicate-ranking/1.0.0"] = "scholarly-duplicate-ranking/1.0.0"
    feature_version: Literal["scholarly-duplicate-features/1.0.0"] = "scholarly-duplicate-features/1.0.0"
    configuration_sha256: Digest = DEFAULT_CONFIG.fingerprint
    identifier_normalizer: str = NORMALIZER_VERSION
    after: Annotated[int, Field(strict=True, ge=0, le=20000)]
    next_after: Annotated[int, Field(strict=True, ge=1, le=20000)] | None
    items: Annotated[tuple[CandidateExplanation, ...], Field(max_length=100)]

    @model_validator(mode="after")
    def complete_page(self) -> Self:
        end = self.after + len(self.items)
        if (
            not 0 <= self.after <= end <= self.candidate_count <= self.compared_pairs
            or self.compared_pairs > self.record_count * (self.record_count - 1) // 2
            or self.next_after != (end if end < self.candidate_count else None)
            or (self.next_after is not None and not self.items)
            or self.configuration_sha256 != DEFAULT_CONFIG.fingerprint
            or self.identifier_normalizer != NORMALIZER_VERSION
            or self.inventory_state
            != ("unchanged" if self.inventory_sha256 == self.current_inventory_sha256 else "changed")
        ):
            raise ValueError("duplicate-page-invalid")
        return self
