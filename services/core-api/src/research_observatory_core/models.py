"""Portable response models for the runtime service surface."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

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
        else:
            if self.access_mode is ProjectAccessMode.READ_WRITE:
                raise ValueError("incompatible projects cannot open for write")
            if not self.backup_required_before_repair or self.recovery_action is ProjectRecoveryAction.NONE:
                raise ValueError("incompatible projects require a backup-first recovery action")
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
