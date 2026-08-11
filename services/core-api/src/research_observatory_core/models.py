"""Portable response models for the runtime service surface."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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
    api_compatibility: str = "0.1"


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
