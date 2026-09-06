"""Owned provider-neutral registry values; persistence and runtime authority are separate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from .model_gateway_contracts import ModelTaskKind
from .models import ContractModel

type RegistryCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$", max_length=128)]
type RegistryHash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
type RegistryVersion = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$", max_length=128)]
type RegistryRevision = Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]
type RegistryTime = Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]
type RegistryDataClass = Literal["public", "internal", "confidential", "restricted"]
type ModelModality = Literal["text", "image", "audio", "video"]
type ModelDeployment = Literal["local", "remote", "institutional"]
type ModelPlatform = Literal["windows-x64", "macos-arm64", "linux-x64", "linux-arm64"]
type ModelAvailability = Literal["ready", "unavailable", "unknown"]
type ModelAccelerator = Literal["none", "gpu"]
type ModelCost = Annotated[int, Field(strict=True, ge=0, le=10**12)]


class RegistryModel(ContractModel):
    model_config = ConfigDict(revalidate_instances="always")


class ModelExecutionIdentity(RegistryModel):
    provider_id: RegistryCode
    provider_version: RegistryVersion
    model_id: RegistryCode
    model_version: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")]
    runtime_id: RegistryCode
    runtime_version: RegistryVersion
    configuration_hash: RegistryHash
    evaluation_id: RegistryCode | None
    evaluation_version: RegistryVersion | None

    @model_validator(mode="after")
    def evaluation_pair(self) -> Self:
        if (self.evaluation_id is None) != (self.evaluation_version is None):
            raise ValueError("evaluation identity must be complete or unreported")
        return self


class ModelManifest(RegistryModel):
    schema_version: Literal["1.0"] = "1.0"
    manifest_id: RegistryCode
    revision: Annotated[int, Field(strict=True, ge=1, le=2**31 - 1)]
    identity: ModelExecutionIdentity
    deployment: ModelDeployment
    license_id: RegistryCode
    capabilities: Annotated[tuple[ModelTaskKind, ...], Field(min_length=1, max_length=8)]
    features: Annotated[tuple[RegistryCode, ...], Field(max_length=32)]
    modalities: Annotated[tuple[ModelModality, ...], Field(min_length=1, max_length=4)]
    context_tokens: Annotated[int, Field(strict=True, ge=1, le=11_000_000)]
    max_output_tokens: Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
    supports_citations: Annotated[bool, Field(strict=True)]
    platforms: Annotated[tuple[ModelPlatform, ...], Field(min_length=1, max_length=4)]
    minimum_memory_mib: Annotated[int, Field(strict=True, ge=0, le=10_000_000, alias="minimumMemoryMiB")]
    accelerator: ModelAccelerator
    quality_tier: Literal["unrated", "economy", "balanced", "quality"]
    allowed_data_classes: Annotated[tuple[RegistryDataClass, ...], Field(max_length=4)]
    cost_microunits_per_thousand_tokens: ModelCost | None
    declared_availability: Literal["available", "unavailable", "unknown"]
    retired: Annotated[bool, Field(strict=True)]

    @field_validator("capabilities", "features", "modalities", "platforms", "allowed_data_classes")
    @classmethod
    def canonical_set(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("registry sets must be sorted and unique")
        return value


class ModelRegistryCatalog(RegistryModel):
    project_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9-]+$")]
    revision: RegistryRevision
    manifests: Annotated[tuple[ModelManifest, ...], Field(max_length=1000)]

    @model_validator(mode="after")
    def ordered_manifests(self) -> Self:
        keys = tuple(item.manifest_id for item in self.manifests)
        if keys != tuple(sorted(set(keys))) or (self.revision == 0 and self.manifests):
            raise ValueError("catalog identity or revision is invalid")
        return self


class HostModelObservation(RegistryModel):
    """Trusted adapter's ephemeral observation of one exact immutable manifest."""

    manifest_hash: RegistryHash
    observed_at_ms: RegistryTime
    expires_at_ms: RegistryTime
    availability: ModelAvailability
    platform: ModelPlatform
    memory_mib: Annotated[int, Field(strict=True, ge=0, le=10_000_000)]
    accelerator: ModelAccelerator
    qualified_task_kinds: Annotated[tuple[ModelTaskKind, ...], Field(max_length=8)]
    modalities: Annotated[tuple[ModelModality, ...], Field(max_length=4)]

    @model_validator(mode="after")
    def bounded_observation(self) -> Self:
        if not 0 < self.expires_at_ms - self.observed_at_ms <= 60_000:
            raise ValueError("runtime observation lifetime must be positive and at most one minute")
        for values in (self.qualified_task_kinds, self.modalities):
            if tuple(sorted(set(values))) != values:
                raise ValueError("observation sets must be sorted and unique")
        return self


class RegistryPermission(RegistryModel):
    """Internal current policy/rights witness; never accepted from a renderer."""

    project_id: Annotated[str, Field(min_length=1, max_length=128)]
    catalog_revision: RegistryRevision
    task_hash: RegistryHash
    manifest_hash: RegistryHash
    policy_revision: RegistryCode
    rights_revision: RegistryCode
    observed_at_ms: RegistryTime
    expires_at_ms: RegistryTime
    data_class: RegistryDataClass
    required_modalities: Annotated[tuple[ModelModality, ...], Field(min_length=1, max_length=4)]
    permitted_deployments: Annotated[tuple[ModelDeployment, ...], Field(max_length=3)]
    maximum_cost_microunits: ModelCost | None
    reason_codes: Annotated[tuple[RegistryCode, ...], Field(max_length=32)]

    @model_validator(mode="after")
    def bounded_permission(self) -> Self:
        if not 0 < self.expires_at_ms - self.observed_at_ms <= 60_000:
            raise ValueError("policy observation lifetime must be positive and at most one minute")
        for values in (self.required_modalities, self.permitted_deployments, self.reason_codes):
            if tuple(sorted(set(values))) != values:
                raise ValueError("policy sets must be sorted and unique")
        return self


class ModelEligibilityCandidate(RegistryModel):
    manifest_id: RegistryCode
    manifest_revision: RegistryRevision
    manifest_hash: RegistryHash
    policy_revision: RegistryCode
    rights_revision: RegistryCode
    observation_expires_at_ms: RegistryTime


class ModelRegistryRejection(RegistryModel):
    manifest_id: RegistryCode
    manifest_revision: RegistryRevision
    manifest_hash: RegistryHash
    # Keep all 32 bounded policy denials plus the matcher's local failures.
    reason_codes: Annotated[tuple[RegistryCode, ...], Field(min_length=1, max_length=64)]


class ModelRegistryResolution(RegistryModel):
    project_id: str
    catalog_revision: RegistryRevision
    task_hash: RegistryHash | None
    eligible: Annotated[tuple[ModelEligibilityCandidate, ...], Field(max_length=1000)]
    rejected: Annotated[tuple[ModelRegistryRejection, ...], Field(max_length=1000)]
    reason_codes: Annotated[tuple[RegistryCode, ...], Field(max_length=32)]
    execution_authorized: Literal[False] = False


type RegistryUuid = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
]
type RegistryTimestamp = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")]


class ModelCatalogRecord(ModelRegistryCatalog):
    """Internal immutable record; public projections omit actor and command identities."""

    catalog_hash: RegistryHash
    previous_hash: RegistryHash | None
    record_hash: RegistryHash
    actor_id: RegistryUuid
    event_id: RegistryUuid
    outbox_id: RegistryUuid
    occurred_at: RegistryTimestamp
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    command_hash: RegistryHash
    request_key_hash: RegistryHash

    @property
    def catalog(self) -> ModelRegistryCatalog:
        return ModelRegistryCatalog(project_id=self.project_id, revision=self.revision, manifests=self.manifests)

    @model_validator(mode="after")
    def verify_binding(self) -> Self:
        if self.revision < 1 or (self.revision == 1) != (self.previous_hash is None):
            raise ValueError("catalog predecessor is invalid")
        if self.catalog_hash != canonical_hash(self.catalog):
            raise ValueError("catalog hash is invalid")
        if self.record_hash != canonical_hash(self.model_dump(by_alias=True, exclude={"record_hash", "manifests"})):
            raise ValueError("catalog record hash is invalid")
        return self


class ModelCatalogSummary(RegistryModel):
    revision: RegistryRevision
    catalog_hash: RegistryHash
    record_hash: RegistryHash
    previous_hash: RegistryHash | None
    occurred_at: RegistryTimestamp
    model_count: Annotated[int, Field(strict=True, ge=0, le=1000)]


class ModelCatalogReadRequest(RegistryModel):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    revision: Annotated[int, Field(strict=True, ge=1, le=2**31 - 1)] | None = None
    after_manifest_id: RegistryCode | None = None
    before_history_revision: Annotated[int, Field(strict=True, ge=1, le=2**31 - 1)] | None = None


class ModelCatalogRefreshRequest(RegistryModel):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    expected_revision: Annotated[int, Field(strict=True, ge=0, le=2**31 - 2)]


class ModelCatalogEntry(RegistryModel):
    manifest: ModelManifest
    manifest_hash: RegistryHash
    availability: Literal["ready", "unavailable", "unknown", "stale"]
    qualified_task_kinds: Annotated[tuple[ModelTaskKind, ...], Field(max_length=8)]
    reason_codes: Annotated[tuple[RegistryCode, ...], Field(max_length=32)]
    eligibility: Literal["not-evaluated"] = "not-evaluated"


class ModelCatalogProjection(RegistryModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: Annotated[str, Field(pattern=r"^[0-9a-f-]{36}$")]
    revision: RegistryRevision
    latest_revision: RegistryRevision
    catalog_hash: RegistryHash | None
    model_count: Annotated[int, Field(strict=True, ge=0, le=1000)]
    inventory_state: Literal["not-configured", "available", "unavailable"]
    entries: Annotated[tuple[ModelCatalogEntry, ...], Field(max_length=50)]
    next_manifest_id: RegistryCode | None
    history: Annotated[tuple[ModelCatalogSummary, ...], Field(max_length=20)]
    next_history_revision: RegistryRevision | None
    execution_available: Literal[False] = False


def canonical_document(value: object) -> object:
    """Normalize only owned contract values and JSON-shaped task snapshots."""
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, RegistryModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, Mapping):
        return {key: canonical_document(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [canonical_document(item) for item in value]
    return value


def canonical_bytes(value: object) -> bytes:
    return json.dumps(canonical_document(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()
