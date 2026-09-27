"""Portable source addresses and bounded, protected reconciliation values."""

from typing import Annotated, Literal, Self

from pydantic import Field, computed_field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity, ImportRights, ProjectIdentity
from .exact import IdentifierAssertion, MatchFlag, SourceOrigin
from .identifiers import NormalizedIdentifier


class SourceAddress(DraftValue):
    kind: Literal["import-member", "connector-record"]
    context_id: Identity
    revision_id: Identity
    ordinal: Annotated[int, Field(strict=True, ge=0, le=200000)]
    record_key: Digest | None

    @model_validator(mode="after")
    def complete_address(self) -> Self:
        if self.kind == "import-member":
            if self.ordinal < 1 or self.record_key is None:
                raise ValueError("reconciliation-source-address-invalid")
        elif self.ordinal > 999 or self.record_key is not None:
            raise ValueError("reconciliation-source-address-invalid")
        return self


class ScholarlyField(DraftValue):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    observed: Annotated[str, Field(min_length=1, max_length=65536)] = Field(repr=False)
    origin: SourceOrigin
    source_selector: Annotated[str, Field(min_length=1, max_length=128)]


class SourceAssertion(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    address: SourceAddress
    source_revision_id: Identity
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    identifiers: Annotated[tuple[IdentifierAssertion, ...], Field(max_length=128)] = Field(repr=False)
    fields: Annotated[tuple[ScholarlyField, ...], Field(max_length=256)] = Field(repr=False)
    rights: ImportRights
    source_sha256: Digest

    @model_validator(mode="after")
    def bounded_source(self) -> Self:
        if len(self.model_dump_json(by_alias=True).encode("utf-8")) > 1024 * 1024:
            raise ValueError("reconciliation-source-limit")
        return self


class ReconciliationResult(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    assertion_revision_id: Identity
    source: SourceAddress
    work_id: Identity | None
    work_revision_id: Identity | None
    disposition: Literal["new-work", "exact-linked", "review-required"]
    candidates: Annotated[tuple[Identity, ...], Field(max_length=256)]
    flags: Annotated[tuple[MatchFlag, ...], Field(max_length=16)]
    knowledge_status: Literal["inferred", "disputed"]
    matching_reason: Literal["no-exact-match", "unique-compatible-exact-identifiers", "human-review-required"]

    @model_validator(mode="after")
    def consistent_disposition(self) -> Self:
        review = self.disposition == "review-required"
        if review != (self.work_id is None) or review != (self.work_revision_id is None):
            raise ValueError("reconciliation-result-invalid")
        if review != bool(self.flags) or review != (self.knowledge_status == "disputed"):
            raise ValueError("reconciliation-result-invalid")
        return self


class FieldObservation(DraftValue):
    assertion_revision_id: Identity
    value: Annotated[str, Field(min_length=1, max_length=65536)] = Field(repr=False)
    origin: SourceOrigin


class CanonicalFieldSelection(DraftValue):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    selected: Annotated[str, Field(min_length=1, max_length=65536)] | None = Field(repr=False)
    status: Literal["observed", "adjudicated", "disputed", "not-reported"]
    reason: Literal["consistent-source-values", "accepted-correction", "competing-assertions", "no-assertion"]
    observations: Annotated[tuple[FieldObservation, ...], Field(max_length=32768)] = Field(repr=False)


class CanonicalWorkReference(DraftValue):
    work_id: Identity
    revision_id: Identity


class ReconciliationInspection(DraftValue):
    result: ReconciliationResult
    assertion: SourceAssertion = Field(repr=False)
    canonical_work: CanonicalWorkReference | None = None
    canonical_fields: Annotated[tuple[CanonicalFieldSelection, ...], Field(max_length=256)] = Field(
        default=(), repr=False
    )

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def normalized_identifiers(self) -> tuple[NormalizedIdentifier, ...]:
        return tuple(item.normalized for item in self.assertion.identifiers)


class ReconciliationProblem(RuntimeError):
    """Content-free domain failures mapped to bounded API diagnostics."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
