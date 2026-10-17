"""Strict lexical observations and requests, separate from executor job state.

These protected values grant no read, source-opening or publication authority.
Draft edits do not create these records. Full hybrid replay remains separate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..ingestion.import_drafts import DraftValue
from ..ingestion.preview_workflow import PreviewIntentContext, fingerprint
from ..parsing.contracts import Count, Digest, Identity, ProjectIdentity
from .contracts import MAX_WIRE_BYTES, load_query_document
from .ranking import FIELD_WEIGHTS, RANKING_VERSION, LexicalFilters

type Session = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")]
type QueryWire = Annotated[str, Field(strict=True, min_length=2, max_length=MAX_WIRE_BYTES)]
type KeyVersion = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")]
type Instant = Annotated[str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")]


class SearchValue(DraftValue):
    model_config = ConfigDict(
        strict=True, revalidate_instances="always", hide_input_in_errors=True, validate_default=True
    )


def content_sha256(value: SearchValue) -> str:
    encoded = json.dumps(
        value.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    if len(encoded) > 1024 * 1024:
        raise ValueError("search-record-byte-limit")
    return hashlib.sha256(encoded).hexdigest()


class SearchFilters(SearchValue):
    year_from: Annotated[int, Field(strict=True, ge=1, le=9999)] | None = None
    year_to: Annotated[int, Field(strict=True, ge=1, le=9999)] | None = None

    def kernel(self) -> LexicalFilters:
        return LexicalFilters(self.year_from, self.year_to)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        self.kernel()
        return self


class SearchRequestInput(SearchValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    command_id: Identity
    actor_id: Identity
    session_id: Session = Field(repr=False)
    intent: PreviewIntentContext
    policy_sha256: Digest
    query_document: QueryWire = Field(repr=False)
    filters: SearchFilters
    ranking_version: Literal["ro-lexical-best-row-per-leaf-bm25-1"] = RANKING_VERSION
    field_weights: Annotated[tuple[float, ...], Field(min_length=8, max_length=8)] = FIELD_WEIGHTS

    @field_validator("query_document")
    @classmethod
    def exact_query(cls, value: str) -> str:
        if load_query_document(value).to_json() != value:
            raise ValueError("search-query-record-invalid")
        return value

    @model_validator(mode="after")
    def authority(self) -> Self:
        if (
            self.intent.project_id != self.project_id
            or self.intent.status != "accepted"
            or self.field_weights != FIELD_WEIGHTS
        ):
            raise ValueError("search-request-authority-invalid")
        return self

    @property
    def configuration_id(self) -> str:
        return "lexical-search." + self.command_id

    @property
    def configuration_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_hash(self) -> str:
        return fingerprint(self.model_dump(mode="json", by_alias=True))

    @property
    def idempotency_key(self) -> str:
        return fingerprint(["lexical-search/1", self.command_id])

    def policy_reference(self) -> dict[str, str]:
        return {
            "policyId": "local-lexical-search-policy",
            "policyVersion": "1.0.0",
            "policyHash": "sha256:" + self.policy_sha256,
        }


class SearchInputIdentity(SearchValue):
    project_id: ProjectIdentity
    generation_id: Identity
    selection_id: Identity
    generation_event_id: Identity
    generation_configuration_sha256: Digest
    projection_sha256: Digest
    source_watermark: Count
    source_authority_epoch: Count
    rights_time_partition: Count
    validated_at: Instant
    authority_sha256: Digest
    actor_sha256: Digest
    lifecycle_sha256: Digest
    canonical_key_version: KeyVersion
    derivative_key_version: KeyVersion
    earliest_rights_expiry: Instant | None
    input_sha256: Digest
    source_set_sha256: Digest

    @field_validator("earliest_rights_expiry", "validated_at")
    @classmethod
    def real_instant(cls, value: str | None) -> str | None:
        if value is not None:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.isoformat(timespec="milliseconds").replace("+00:00", "Z") != value:
                raise ValueError("search-instant-invalid")
        return value


class SearchInputManifest(SearchValue):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["lexical-input-manifest"] = "lexical-input-manifest"
    project_id: ProjectIdentity
    job_id: Identity
    input_sha256: Digest
    level: Annotated[int, Field(strict=True, ge=0, le=32)]
    ordinal: Count
    source_revision_ids: Annotated[tuple[Identity, ...], Field(min_length=1, max_length=60)]

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if self.source_revision_ids != tuple(sorted(set(self.source_revision_ids))):
            raise ValueError("search-input-manifest-invalid")
        return self


class SearchRunContent(SearchValue):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["lexical-search-run"] = "lexical-search-run"
    search_run_id: Identity
    project_id: ProjectIdentity
    job_id: Identity
    attempt_id: Identity
    request_sha256: Digest
    request: SearchRequestInput = Field(repr=False)
    inputs: SearchInputIdentity
    source_roots: Annotated[tuple[Identity, ...], Field(max_length=60)]
    result_count: Count
    result_sha256: Digest
    executed_at: Instant
    semantic_state: Literal["unqualified"] = "unqualified"
    rerank_state: Literal["not-run"] = "not-run"

    @model_validator(mode="after")
    def exact_observation(self) -> Self:
        if (
            self.project_id != self.request.project_id
            or self.project_id != self.inputs.project_id
            or self.request_sha256 != self.request.configuration_hash.removeprefix("sha256:")
            or self.source_roots != tuple(sorted(set(self.source_roots)))
            or self.search_run_id in (self.job_id, self.attempt_id, self.request.command_id)
        ):
            raise ValueError("search-run-authority-invalid")
        SearchInputIdentity.real_instant(self.executed_at)
        content_sha256(self)
        return self


class SearchRunRecord(SearchValue):
    revision_id: Identity
    payload_sha256: Digest
    content: SearchRunContent = Field(repr=False)

    @model_validator(mode="after")
    def exact_payload(self) -> Self:
        if self.payload_sha256 != content_sha256(self.content):
            raise ValueError("search-run-payload-invalid")
        return self
