"""Owned, bounded scientific connector values; no network, secrets or persistence.

Queries, cursors, identifiers and source fields are protected research content.
Serialization is for the protected project/broker boundary, not diagnostics.
Provider observations and these models never authorize dispatch or grant rights.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import AfterValidator, ConfigDict, Field, field_validator, model_validator

from ..models import ContractModel

type ProviderId = Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$", max_length=128)]
type ApiVersion = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$", max_length=128)]
type Version = Annotated[
    str, Field(strict=True, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$", max_length=128)
]
type InvocationId = Annotated[
    str, Field(strict=True, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
]
type ProjectId = Annotated[
    str, Field(strict=True, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
]
type RequestDigest = Annotated[str, Field(strict=True, pattern=r"^sha256:[0-9a-f]{64}$")]
type ObjectDigest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
type BoundedText = Annotated[str, Field(strict=True, min_length=1, max_length=65536)]
type IdentifierValue = Annotated[str, Field(strict=True, min_length=1, max_length=4096)]
type Count = Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]
type RetryAfter = Annotated[int, Field(strict=True, ge=0, le=300000)]
type Operation = Literal["search", "lookup", "citations", "recommendations", "oa-resolution"]


def _utc(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        canonical = parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except ValueError:
        raise ValueError("connector-time-invalid") from None
    if canonical != value:
        raise ValueError("connector-time-invalid")
    return value


type UtcInstant = Annotated[
    str,
    Field(strict=True, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$"),
    AfterValidator(_utc),
]


class ConnectorModel(ContractModel):
    model_config = ConfigDict(revalidate_instances="always", hide_input_in_errors=True, validate_default=True)


def _json_default(value: object) -> object:
    if isinstance(value, ConnectorModel):
        return value.model_dump(mode="json", by_alias=True)
    raise ValueError("connector-json-invalid")


class BoundedDocument(ConnectorModel):
    maximum_document_bytes: ClassVar[int] = 10 * 1024 * 1024

    @model_validator(mode="before")
    @classmethod
    def bounded_document(cls, value: object) -> object:
        # Streaming size accounting rejects repeated large values before constructing
        # thousands of nested model snapshots. The broker separately caps wire bytes.
        length = 0
        try:
            encoder = json.JSONEncoder(
                ensure_ascii=False, allow_nan=False, default=_json_default, separators=(",", ":")
            )
            for fragment in encoder.iterencode(value):
                length += len(fragment.encode("utf-8"))
                if length > cls.maximum_document_bytes:
                    raise ValueError("connector-document-too-large")
        except TypeError, ValueError, RecursionError, UnicodeError:
            raise ValueError("connector-document-invalid-or-too-large") from None
        return value


class ProviderIdentifier(ConnectorModel):
    scheme: ProviderId
    value: IdentifierValue = Field(repr=False)


class SearchFilter(ConnectorModel):
    field: Literal["publication-year", "author-id", "source-id", "work-type", "language", "open-access"]
    operator: Literal["eq", "gte", "lte"]
    value: IdentifierValue = Field(repr=False)


class SearchSort(ConnectorModel):
    field: Literal["relevance", "publication-date", "citation-count"]
    direction: Literal["ascending", "descending"]


class SearchQuery(ConnectorModel):
    kind: Literal["search"]
    text: BoundedText = Field(repr=False)
    field: Literal["any", "title", "abstract"]
    filters: Annotated[tuple[SearchFilter, ...], Field(max_length=32)] = Field(repr=False)
    sort: Annotated[tuple[SearchSort, ...], Field(max_length=3)]
    fields: Annotated[
        tuple[Literal["title", "authors", "date", "venue", "identifiers", "abstract", "references", "rights"], ...],
        Field(max_length=8),
    ]

    @model_validator(mode="after")
    def unambiguous_projection(self) -> Self:
        if len(set(self.fields)) != len(self.fields) or len({item.field for item in self.sort}) != len(self.sort):
            raise ValueError("connector-projection-invalid")
        if not self.text.strip():
            raise ValueError("connector-query-empty")
        return self


class LookupQuery(ConnectorModel):
    kind: Literal["lookup"]
    identifiers: Annotated[tuple[ProviderIdentifier, ...], Field(min_length=1, max_length=100)] = Field(repr=False)


class CitationQuery(ConnectorModel):
    kind: Literal["citations"]
    seed: ProviderIdentifier = Field(repr=False)
    direction: Literal["citations", "references"]


class RecommendationQuery(ConnectorModel):
    kind: Literal["recommendations"]
    positive_seeds: Annotated[tuple[ProviderIdentifier, ...], Field(min_length=1, max_length=100)] = Field(repr=False)
    negative_seeds: Annotated[tuple[ProviderIdentifier, ...], Field(max_length=100)] = Field(repr=False)

    @model_validator(mode="after")
    def distinct_seeds(self) -> Self:
        positive = {(item.scheme, item.value) for item in self.positive_seeds}
        negative = {(item.scheme, item.value) for item in self.negative_seeds}
        if (
            positive & negative
            or len(positive) != len(self.positive_seeds)
            or len(negative) != len(self.negative_seeds)
        ):
            raise ValueError("connector-seeds-invalid")
        return self


class OaQuery(ConnectorModel):
    kind: Literal["oa-resolution"]
    identifier: ProviderIdentifier = Field(repr=False)


type ScientificQuery = Annotated[
    SearchQuery | LookupQuery | CitationQuery | RecommendationQuery | OaQuery, Field(discriminator="kind")
]


class ConnectorPolicy(ConnectorModel):
    """Ceilings and requested behavior, never a current policy/rights grant."""

    max_inflight: Annotated[int, Field(strict=True, ge=1, le=1)]
    minimum_interval_ms: Annotated[int, Field(strict=True, ge=1000, le=86400000)]
    maximum_attempts: Annotated[int, Field(strict=True, ge=1, le=3)]
    timeout_ms: Annotated[int, Field(strict=True, ge=1, le=30000)]
    maximum_response_bytes: Annotated[int, Field(strict=True, ge=1, le=10 * 1024 * 1024)]
    maximum_retry_after_ms: RetryAfter
    cache_mode: Literal["bypass", "revalidate", "allow-fresh"]
    maximum_fresh_age_ms: Annotated[int, Field(strict=True, ge=0, le=86400000)]
    raw_retention: Literal["if-permitted", "permitted-fields-only", "do-not-retain"]


class ConnectorCursor(ConnectorModel):
    provider_id: ProviderId
    project_id: ProjectId
    request_sha256: RequestDigest
    page_index: Annotated[int, Field(strict=True, ge=1, le=1000000)]
    value: IdentifierValue = Field(repr=False)
    expires_at: UtcInstant | None


class ConnectorRequest(BoundedDocument):
    maximum_document_bytes: ClassVar[int] = 256 * 1024
    schema_version: Literal["1.0"]
    project_id: ProjectId
    invocation_id: InvocationId
    provider_id: ProviderId
    adapter_version: Version
    source_api_version: ApiVersion | None
    query: ScientificQuery = Field(repr=False)
    page_size: Annotated[int, Field(strict=True, ge=1, le=1000)]
    cursor: ConnectorCursor | None = Field(repr=False)
    policy: ConnectorPolicy

    def scientific_sha256(self) -> str:
        scientific = self.model_dump(mode="json", by_alias=True, exclude={"invocation_id", "cursor", "policy"})
        raw = json.dumps(scientific, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode(
            "ascii"
        )
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    def page_sha256(self) -> str:
        """Cache identity includes the current cursor, unlike the pagination root."""
        page = {
            "scientificRequestSha256": self.scientific_sha256(),
            "cursor": self.cursor.model_dump(mode="json", by_alias=True) if self.cursor else None,
        }
        raw = json.dumps(page, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    def assert_cursor_binding(self, cursor: ConnectorCursor) -> None:
        if (cursor.provider_id, cursor.project_id, cursor.request_sha256) != (
            self.provider_id,
            self.project_id,
            self.scientific_sha256(),
        ):
            raise ValueError("connector-cursor-binding-invalid")

    @model_validator(mode="after")
    def cursor_binding(self) -> Self:
        if self.cursor is not None:
            self.assert_cursor_binding(self.cursor)
        return self

    def assert_resumable(self, now: str) -> None:
        _utc(now)
        if self.cursor is not None:
            self.assert_cursor_binding(self.cursor)
            if self.cursor.expires_at is not None and self.cursor.expires_at <= now:
                raise ValueError("connector-cursor-expired")


class ConnectorCapabilities(BoundedDocument):
    maximum_document_bytes: ClassVar[int] = 16384
    schema_version: Literal["1.0"]
    provider_id: ProviderId
    adapter_version: Version
    source_api_version: ApiVersion | None
    operations: Annotated[tuple[Operation, ...], Field(min_length=1, max_length=5)]
    identifier_schemes: Annotated[tuple[ProviderId, ...], Field(min_length=1, max_length=32)]
    maximum_page_size: Annotated[int, Field(strict=True, ge=1, le=1000)]
    configuration: Literal["ready", "not-configured", "unavailable"]
    required_settings: Annotated[tuple[Literal["contact", "provider-key"], ...], Field(max_length=2)]

    @field_validator("operations", "identifier_schemes", "required_settings")
    @classmethod
    def ordered_sets(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(values))) != values:
            raise ValueError("connector-capability-set-invalid")
        return values

    def assert_supported(self, request: ConnectorRequest) -> None:
        if self.configuration != "ready":
            raise ValueError("connector-not-configured-or-unavailable")
        if (self.provider_id, self.adapter_version, self.source_api_version) != (
            request.provider_id,
            request.adapter_version,
            request.source_api_version,
        ):
            raise ValueError("connector-provider-version-mismatch")
        if request.query.kind not in self.operations or request.page_size > self.maximum_page_size:
            raise ValueError("connector-unsupported-operation")
        query = request.query
        match query:
            case LookupQuery():
                identifiers = query.identifiers
            case CitationQuery():
                identifiers = (query.seed,)
            case RecommendationQuery():
                identifiers = query.positive_seeds + query.negative_seeds
            case OaQuery():
                identifiers = (query.identifier,)
            case SearchQuery():
                identifiers = ()
        if any(item.scheme not in self.identifier_schemes for item in identifiers):
            raise ValueError("connector-unsupported-identifier")


type ErrorCode = Literal[
    "authentication",
    "permission-denied",
    "rate-limit",
    "provider-unavailable",
    "timeout",
    "invalid-query",
    "incompatible-response",
    "policy-denied",
    "cancelled",
    "not-configured",
    "unsupported-operation",
    "invalid-cursor",
    "partial-response",
    "response-too-large",
]


class ConnectorError(ConnectorModel):
    code: ErrorCode
    retryable: Annotated[bool, Field(strict=True)]
    retry_after_ms: RetryAfter | None

    @model_validator(mode="after")
    def bounded_retry(self) -> Self:
        if self.retryable and self.code not in {"rate-limit", "provider-unavailable", "timeout"}:
            raise ValueError("connector-terminal-error")
        if self.retry_after_ms is not None and self.code not in {"rate-limit", "provider-unavailable"}:
            raise ValueError("connector-retry-after-invalid")
        return self


class SourceObservation(ConnectorModel):
    """A source-reported value or explicit absence; never a permission decision."""

    state: Literal["reported", "not-reported", "unknown", "not-applicable"]
    value: BoundedText | None = Field(repr=False)

    @model_validator(mode="after")
    def explicit_absence(self) -> Self:
        if (self.state == "reported") != (self.value is not None):
            raise ValueError("connector-observation-invalid")
        return self


class SourceTerms(ConnectorModel):
    license: SourceObservation
    terms: SourceObservation
    access: Literal["open", "closed", "unknown", "not-reported"]


class SourceField(ConnectorModel):
    namespace: ProviderId
    name: Annotated[str, Field(strict=True, pattern=r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")]
    encoding: Literal["text", "json"]
    value: Annotated[str, Field(strict=True, max_length=65536)] = Field(repr=False)

    @model_validator(mode="after")
    def json_is_data(self) -> Self:
        if self.encoding == "json":
            try:
                json.loads(self.value, parse_constant=_reject_json_constant)
            except ValueError, RecursionError:
                raise ValueError("connector-source-json-invalid") from None
        return self


def _reject_json_constant(_: str) -> Any:
    raise ValueError("connector-source-json-invalid")


class ConnectorRecord(ConnectorModel):
    provider_id: ProviderId
    raw_identifier: ProviderIdentifier = Field(repr=False)
    identifiers: Annotated[tuple[ProviderIdentifier, ...], Field(max_length=64)] = Field(repr=False)
    retrieved_at: UtcInstant
    fields: Annotated[tuple[SourceField, ...], Field(max_length=256)] = Field(repr=False)
    terms: SourceTerms = Field(repr=False)

    @model_validator(mode="after")
    def source_namespace(self) -> Self:
        if any(item.namespace != self.provider_id for item in self.fields):
            raise ValueError("connector-source-namespace-invalid")
        return self


class RateLimitState(ConnectorModel):
    provider_id: ProviderId
    observed_at: UtcInstant
    remaining: Count | None
    retry_after_ms: RetryAfter | None
    circuit: Literal["closed", "open", "half-open", "unknown"]


class ResponseRetention(ConnectorModel):
    """Sanitized scientific response identity, never the credential-bearing wire body."""

    body_state: Literal["retained", "permitted-fields-only", "unavailable"]
    object_sha256: ObjectDigest | None
    content_sha256: ObjectDigest | None
    byte_length: Annotated[int, Field(strict=True, ge=0, le=10 * 1024 * 1024)] | None
    redaction: Literal["applied", "not-required", "unavailable"]
    reason: Literal["permitted", "provider-terms", "policy", "not-retained", "not-received", "not-attempted"]

    @model_validator(mode="after")
    def retained_body(self) -> Self:
        if self.body_state == "retained":
            if (
                self.object_sha256 is None
                or self.content_sha256 != self.object_sha256
                or self.byte_length is None
                or self.redaction == "unavailable"
                or self.reason != "permitted"
            ):
                raise ValueError("connector-retained-body-invalid")
        elif self.object_sha256 is not None or self.reason == "permitted":
            raise ValueError("connector-unavailable-body-invalid")
        return self


class CacheObservation(ConnectorModel):
    state: Literal["disabled", "miss", "hit", "revalidated", "not-permitted"]
    age_ms: Count | None
    request_sha256: RequestDigest | None


class ConnectorResultPage(BoundedDocument):
    schema_version: Literal["1.0"]
    observation_id: InvocationId
    request: ConnectorRequest = Field(repr=False)
    observed_at: UtcInstant
    retrieved_at: UtcInstant | None
    outcome: Literal["complete", "partial", "failed"]
    continuation: Literal["exhausted", "next-page", "retry-current", "unavailable"]
    next_cursor: ConnectorCursor | None = Field(repr=False)
    records: Annotated[tuple[ConnectorRecord, ...], Field(max_length=1000)] = Field(repr=False)
    errors: Annotated[tuple[ConnectorError, ...], Field(max_length=16)]
    warnings: Annotated[tuple[ProviderId, ...], Field(max_length=32)]
    rate: RateLimitState
    response: ResponseRetention
    cache: CacheObservation

    @model_validator(mode="after")
    def coherent_page(self) -> Self:
        if len(self.records) > self.request.page_size or self.rate.provider_id != self.request.provider_id:
            raise ValueError("connector-page-provider-or-bound-invalid")
        if self.observation_id == self.request.invocation_id:
            raise ValueError("connector-observation-identity-invalid")
        if any(
            item.provider_id != self.request.provider_id or item.retrieved_at != self.retrieved_at
            for item in self.records
        ):
            raise ValueError("connector-record-provenance-invalid")
        if self.retrieved_at is not None and self.retrieved_at > self.observed_at:
            raise ValueError("connector-retrieval-time-invalid")
        if self.rate.observed_at > self.observed_at:
            raise ValueError("connector-rate-time-invalid")
        if self.outcome == "complete":
            if self.errors or self.retrieved_at is None or self.continuation not in {"exhausted", "next-page"}:
                raise ValueError("connector-complete-page-invalid")
        elif not self.errors or self.continuation not in {"retry-current", "unavailable"}:
            raise ValueError("connector-incomplete-page-invalid")
        if self.outcome == "failed" and self.records:
            raise ValueError("connector-failed-page-has-records")
        if self.continuation == "retry-current" and any(
            item.code
            in {
                "authentication",
                "permission-denied",
                "policy-denied",
                "cancelled",
                "not-configured",
                "unsupported-operation",
                "invalid-query",
                "invalid-cursor",
            }
            for item in self.errors
        ):
            raise ValueError("connector-terminal-continuation-invalid")
        if self.continuation == "next-page":
            if self.next_cursor is None:
                raise ValueError("connector-next-cursor-missing")
            self.request.assert_cursor_binding(self.next_cursor)
            current_index = self.request.cursor.page_index if self.request.cursor else 0
            if self.next_cursor.page_index != current_index + 1:
                raise ValueError("connector-next-cursor-not-advanced")
            if self.request.cursor is not None and self.next_cursor.value == self.request.cursor.value:
                raise ValueError("connector-next-cursor-repeated")
            if self.next_cursor.expires_at is not None and self.next_cursor.expires_at <= self.observed_at:
                raise ValueError("connector-next-cursor-expired")
        elif self.next_cursor is not None:
            raise ValueError("connector-unexpected-next-cursor")
        if self.cache.state in {"hit", "revalidated"}:
            if self.cache.request_sha256 != self.request.page_sha256() or self.cache.age_ms is None:
                raise ValueError("connector-cache-binding-invalid")
            if self.request.policy.cache_mode == "bypass":
                raise ValueError("connector-cache-policy-invalid")
            if self.cache.state == "hit" and (
                self.request.policy.cache_mode != "allow-fresh"
                or self.cache.age_ms > self.request.policy.maximum_fresh_age_ms
            ):
                raise ValueError("connector-cache-stale")
        elif self.cache.age_ms is not None or self.cache.request_sha256 is not None:
            raise ValueError("connector-cache-observation-invalid")
        if self.response.body_state == "retained" and self.request.policy.raw_retention != "if-permitted":
            raise ValueError("connector-retention-policy-invalid")
        if (
            self.response.byte_length is not None
            and self.response.byte_length > self.request.policy.maximum_response_bytes
        ):
            raise ValueError("connector-response-budget-exceeded")
        if any(
            item.retry_after_ms is not None and item.retry_after_ms > self.request.policy.maximum_retry_after_ms
            for item in self.errors
        ):
            raise ValueError("connector-retry-budget-exceeded")
        if (
            self.rate.retry_after_ms is not None
            and self.rate.retry_after_ms > self.request.policy.maximum_retry_after_ms
        ):
            raise ValueError("connector-rate-budget-exceeded")
        return self
