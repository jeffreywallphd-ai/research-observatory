"""Bounded read projections over existing protected operations and source pages."""

from typing import Annotated, Literal

from pydantic import Field

from ..ports.workflow_executor import WorkflowJobState
from .contracts import ConnectorModel, ConnectorRecord, InvocationId, Operation, ProviderId, RequestDigest, UtcInstant


class ConnectorRunSummary(ConnectorModel):
    preview_id: InvocationId
    invocation_id: InvocationId
    job_id: InvocationId
    workflow_run_id: InvocationId
    provider_id: ProviderId
    operation: Operation
    state: WorkflowJobState
    updated_at: UtcInstant
    diagnostic_code: str | None


class ConnectorRecentRuns(ConnectorModel):
    items: Annotated[tuple[ConnectorRunSummary, ...], Field(max_length=20)]
    scope: Literal["latest-20-source-jobs-within-100-workflows"] = "latest-20-source-jobs-within-100-workflows"


class ConnectorObservationSummary(ConnectorModel):
    observation_id: InvocationId
    observed_at: UtcInstant
    retrieved_at: UtcInstant | None
    outcome: Literal["complete", "partial", "failed"]
    continuation: Literal["exhausted", "next-page", "retry-current", "unavailable"]
    record_count: Annotated[int, Field(strict=True, ge=0, le=1000)]
    records: Annotated[tuple[ConnectorRecord, ...], Field(max_length=1)] = Field(repr=False)
    field_projection: Literal["title-oa-locations-discovery"] = "title-oa-locations-discovery"


class ConnectorInspection(ConnectorModel):
    job: ConnectorRunSummary
    query_json: Annotated[str, Field(strict=True, min_length=1, max_length=262144)] = Field(repr=False)
    scientific_request_sha256: RequestDigest
    observation: ConnectorObservationSummary | None
    record_offset: Annotated[int, Field(strict=True, ge=0, le=999)]
    next_record_offset: Annotated[int, Field(strict=True, ge=1, le=999)] | None
