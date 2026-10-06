"""Core-owned exact-copy acquisition values; none is a reusable egress grant."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from ..connectors.contracts import UtcInstant
from ..ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from ..reconciliation.contracts import SourceAddress
from ..rights_policy import RightsSubject


class AcquisitionProblem(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AcquisitionLocation(DraftValue):
    location_id: Identity
    project_id: ProjectIdentity
    source_assertion_revision_id: Identity
    source_revision_id: Identity
    address: SourceAddress
    source_sha256: Digest
    provider: Annotated[str, Field(max_length=64)]
    location_key: Annotated[str, Field(max_length=128)]
    url: Annotated[str, Field(max_length=8192)] = Field(repr=False)
    license: Annotated[str, Field(max_length=4096)] | None
    version: Annotated[str, Field(max_length=256)] | None
    location_sha256: Digest

    @property
    def rights_subject(self) -> RightsSubject:
        return RightsSubject(
            project_id=self.project_id,
            source_assertion_revision_id=self.source_assertion_revision_id,
            address=self.address,
            copy_id=self.location_id,
            copy_location="provider-hosted",
            resource_class="full-text",
        )


class AcquisitionSelection(DraftValue):
    location_id: Identity
    location_sha256: Digest
    source_assertion_revision_id: Identity
    work_id: Identity
    work_revision_id: Identity
    version_id: Identity
    version_revision_id: Identity
    expected_sha256: Digest | None = None
    redirect_hosts: tuple[Annotated[str, Field(strict=True, min_length=1, max_length=253)], ...] = Field(
        default=(), max_length=5
    )

    @property
    def association(self) -> tuple[str, str, str, str, str]:
        return (
            self.source_assertion_revision_id,
            self.work_id,
            self.work_revision_id,
            self.version_id,
            self.version_revision_id,
        )


class AcquisitionReceipt(DraftValue):
    location_id: Identity
    location_sha256: Digest
    provider_policy_revision_id: Identity
    retrieved_at: UtcInstant
    expected_sha256: Digest | None
    actual_sha256: Digest
    media_type: Annotated[str, Field(max_length=200)]
    wire_bytes: Annotated[int, Field(strict=True, ge=0, le=128 * 1024 * 1024)]
    expanded_bytes: Annotated[int, Field(strict=True, ge=0, le=128 * 1024 * 1024)]
    attempts: Annotated[int, Field(strict=True, ge=1, le=3)]
    redirect_hosts: tuple[Annotated[str, Field(max_length=253)], ...] = Field(max_length=5)
    elapsed_ms: Annotated[int, Field(strict=True, ge=0, le=120000)]
    confirmation_sha256: Digest


@dataclass(frozen=True, slots=True)
class AcquisitionStage:
    """Internal Core composition value; never a renderer or connector command."""

    expected_sha256: str | None
    receipt: Callable[[], AcquisitionReceipt]
