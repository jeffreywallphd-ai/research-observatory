"""Portable response models for the runtime service surface."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import CORE_API_SCHEMA_VERSION, CORE_API_VERSION, CORE_SERVICE_ID


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True, extra="forbid", frozen=True)


class RuntimeState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    UNAVAILABLE = "unavailable"


class ProjectLifecycleState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    TRASH = "trash"


class ProjectAccessMode(StrEnum):
    CLOSED = "closed"
    READ_WRITE = "read-write"
    READ_ONLY = "read-only"


class ProjectCompatibilityState(StrEnum):
    COMPATIBLE = "compatible"
    MIGRATION_REQUIRED = "migration-required"
    NEWER_UNSUPPORTED = "newer-unsupported"


class ProjectRecoveryAction(StrEnum):
    NONE = "none"
    BACKUP_THEN_MIGRATE = "backup-then-migrate"
    BACKUP_THEN_USE_COMPATIBLE_APPLICATION = "backup-then-use-compatible-application"


class PrivacyNetworkPolicy(StrEnum):
    OFFLINE = "offline"
    METADATA_ONLY = "metadata-only"
    APPROVED_PROVIDERS = "approved-providers"


class RemoteModelApproval(StrEnum):
    PREVIEW_EVERY_TASK = "preview-every-task"


class TelemetryMode(StrEnum):
    OFF = "off"
    LOCAL_DIAGNOSTICS_ONLY = "local-diagnostics-only"


class DocumentRetentionPolicy(StrEnum):
    PROJECT_LIFETIME = "project-lifetime"
    REVIEW_AFTER_90_DAYS = "review-after-90-days"
    REVIEW_AFTER_365_DAYS = "review-after-365-days"


class EgressEnforcement(StrEnum):
    DENY = "deny"
    REQUIRE_TASK_PREVIEW = "require-task-preview"


class CacheClearState(StrEnum):
    CLEARED = "cleared"
    CLEARED_CLEANUP_PENDING = "cleared-cleanup-pending"


class RuntimeProjection(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    service: str = CORE_SERVICE_ID
    version: str = CORE_API_VERSION
    state: RuntimeState
    capabilities: tuple[str, ...]


class HealthResponse(RuntimeProjection):
    alive: bool = True


class ReadinessResponse(RuntimeProjection):
    ready: bool


class VersionResponse(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    service: str = CORE_SERVICE_ID
    version: str = CORE_API_VERSION
    api_version: str = "1.0.0"
    minimum_client_api_version: str = "1.0.0"
    maximum_client_api_version_exclusive: str = "2.0.0"


class ConfigurationResponse(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    profile: str
    bind_host: str
    bind_port: str


class ModuleResponse(ContractModel):
    module_id: str
    capabilities: tuple[str, ...]


class ModulesResponse(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    modules: tuple[ModuleResponse, ...]


class CapabilitiesResponse(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    capabilities: tuple[str, ...] = Field(min_length=1)


class ProblemDetail(ContractModel):
    type: str = Field(pattern=r"^urn:research-observatory:problem:[a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=120)
    status: int = Field(ge=400, le=599)
    detail: str = Field(min_length=1, max_length=500)
    code: str = Field(pattern=r"^RO-CORE-[A-Z0-9-]+$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    retryable: bool
    remediation: str = Field(min_length=1, max_length=240)


class ProjectCreateRequest(ContractModel):
    parent_directory: str = Field(min_length=1, max_length=4096)
    directory_name: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
    display_name: str = Field(min_length=1, max_length=120)
    template_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")


class ProjectRootRequest(ContractModel):
    root: str = Field(min_length=1, max_length=4096)


class ProjectDeleteRequest(ProjectRootRequest):
    confirmation: str = Field(min_length=1, max_length=80)


class ProjectProjection(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    display_name: str = Field(min_length=1, max_length=120)
    template_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
    lifecycle_state: ProjectLifecycleState
    root: str = Field(min_length=1, max_length=4096)
    open: bool
    access_mode: ProjectAccessMode
    compatibility_state: ProjectCompatibilityState
    package_format_version: str = Field(
        pattern=(
            r"^(?:0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])\."
            r"(?:0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])\."
            r"(?:0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])$"
        )
    )
    backup_required_before_repair: bool
    recovery_action: ProjectRecoveryAction
    revision: int = Field(ge=0, le=9_007_199_254_740_991)
    delete_confirmation: str = Field(pattern=r"^delete:[0-9a-f-]{36}$")

    @model_validator(mode="after")
    def validate_safe_open_state(self) -> ProjectProjection:
        if self.delete_confirmation != f"delete:{self.project_id}":
            raise ValueError("project deletion confirmation must match the project identity")
        if self.open != (self.access_mode is not ProjectAccessMode.CLOSED):
            raise ValueError("project open state must match its access mode")
        if (
            self.lifecycle_state is not ProjectLifecycleState.ACTIVE
            and self.access_mode is not ProjectAccessMode.CLOSED
        ):
            raise ValueError("only active projects may be open")
        if self.compatibility_state is ProjectCompatibilityState.COMPATIBLE:
            if self.package_format_version != "1.0.0":
                raise ValueError("compatible projects must use the current package format")
            if self.access_mode is ProjectAccessMode.READ_ONLY:
                raise ValueError("compatible projects do not use compatibility read-only mode")
            if self.backup_required_before_repair or self.recovery_action is not ProjectRecoveryAction.NONE:
                raise ValueError("compatible projects do not require compatibility repair")
        elif self.compatibility_state is ProjectCompatibilityState.MIGRATION_REQUIRED:
            if self.access_mode is ProjectAccessMode.READ_WRITE:
                raise ValueError("incompatible projects cannot open for write")
            if (
                not self.backup_required_before_repair
                or self.recovery_action is not ProjectRecoveryAction.BACKUP_THEN_MIGRATE
            ):
                raise ValueError("migration-required projects require the backup-then-migrate action")
        else:
            if self.access_mode is ProjectAccessMode.READ_WRITE:
                raise ValueError("incompatible projects cannot open for write")
            if (
                not self.backup_required_before_repair
                or self.recovery_action is not ProjectRecoveryAction.BACKUP_THEN_USE_COMPATIBLE_APPLICATION
            ):
                raise ValueError("newer-unsupported projects require the backup-then-use-compatible-application action")
        return self


class DeletionDisclosure(ContractModel):
    disclosure_version: Literal["secure-deletion-disclosure-v1"]
    scope: Literal["project-cache-only"]
    logical_removal: Literal[True]
    physical_erasure_guaranteed: Literal[False]
    canonical_project_data_excluded: Literal[True]
    limitations: tuple[str, ...] = Field(min_length=4, max_length=8)


class ProjectPrivacyRequest(ProjectRootRequest):
    pass


class PrivacyPolicyUpdateRequest(ProjectRootRequest):
    expected_revision: int = Field(ge=0, le=9_007_199_254_740_991)
    network_policy: PrivacyNetworkPolicy
    remote_model_approval: RemoteModelApproval
    telemetry_mode: TelemetryMode
    log_retention_days: int = Field(ge=1, le=90)
    document_retention: DocumentRetentionPolicy
    cache_retention_days: int = Field(ge=1, le=90)
    egress_consent_token: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_egress_consent(self) -> PrivacyPolicyUpdateRequest:
        expected = "acknowledge-egress-preview-v1"
        if self.network_policy is PrivacyNetworkPolicy.OFFLINE:
            if self.egress_consent_token is not None:
                raise ValueError("offline policy cannot record an egress consent token")
        elif self.egress_consent_token != expected:
            raise ValueError("non-offline policy requires the exact informed-consent token")
        return self


class PrivacyPolicyProjection(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    revision: int = Field(ge=0, le=9_007_199_254_740_991)
    defaults_applied: bool
    network_policy: PrivacyNetworkPolicy
    remote_model_approval: RemoteModelApproval
    telemetry_mode: TelemetryMode
    log_retention_days: int = Field(ge=1, le=90)
    document_retention: DocumentRetentionPolicy
    cache_retention_days: int = Field(ge=1, le=90)
    egress_consent_recorded: bool
    egress_enforcement: EgressEnforcement
    deletion_disclosure: DeletionDisclosure

    @model_validator(mode="after")
    def validate_policy_state(self) -> PrivacyPolicyProjection:
        if self.defaults_applied != (self.revision == 0):
            raise ValueError("privacy defaults state must match revision")
        if self.egress_consent_recorded != (self.network_policy is not PrivacyNetworkPolicy.OFFLINE):
            raise ValueError("egress consent state must match network policy")
        expected = (
            EgressEnforcement.REQUIRE_TASK_PREVIEW
            if self.network_policy is PrivacyNetworkPolicy.APPROVED_PROVIDERS
            else EgressEnforcement.DENY
        )
        if self.egress_enforcement is not expected:
            raise ValueError("egress enforcement must match network policy")
        return self


class CacheClearPreviewRequest(ProjectRootRequest):
    pass


class CacheClearPreview(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    policy_revision: int = Field(ge=0, le=9_007_199_254_740_991)
    preview_token: str = Field(pattern=r"^[0-9a-f]{32}$")
    confirmation: str = Field(pattern=r"^clear-cache:[0-9a-f]{32}$")
    expires_at: datetime
    item_count: int = Field(ge=0, le=100_000)
    byte_count: int = Field(ge=0, le=9_007_199_254_740_991)
    deletion_disclosure: DeletionDisclosure


class CacheClearRequest(ProjectRootRequest):
    preview_token: str = Field(pattern=r"^[0-9a-f]{32}$")
    confirmation: str = Field(pattern=r"^clear-cache:[0-9a-f]{32}$")

    @model_validator(mode="after")
    def validate_confirmation(self) -> CacheClearRequest:
        if self.confirmation != f"clear-cache:{self.preview_token}":
            raise ValueError("cache confirmation must match the preview token")
        return self


class CacheClearResult(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    state: CacheClearState
    item_count: int = Field(ge=0, le=100_000)
    byte_count: int = Field(ge=0, le=9_007_199_254_740_991)
    cleanup_pending: bool
    deletion_disclosure: DeletionDisclosure

    @model_validator(mode="after")
    def validate_cleanup_state(self) -> CacheClearResult:
        if self.cleanup_pending != (self.state is CacheClearState.CLEARED_CLEANUP_PENDING):
            raise ValueError("cache cleanup state must match cleanup_pending")
        return self


class OperationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperationStatus(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    operation_id: str = Field(pattern=r"^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    kind: str = Field(pattern=r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*$")
    state: OperationState
    sequence: int = Field(ge=0)
    progress_percent: int = Field(ge=0, le=100)
    cancellation_requested: bool
    created_at: datetime
    updated_at: datetime
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class OperationPage(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    items: tuple[OperationStatus, ...]
    next_cursor: str | None = None


class OperationProgressEvent(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    operation_id: str = Field(pattern=r"^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    sequence: int = Field(ge=1)
    state: OperationState
    progress_percent: int = Field(ge=0, le=100)
    terminal: bool
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
