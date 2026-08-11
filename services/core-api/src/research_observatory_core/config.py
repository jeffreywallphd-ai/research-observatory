"""Fail-closed configuration for the local Core API process."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Validated settings for the local-only process profile.

    The current release has one profile. Hosted settings are intentionally not
    accepted early: adding them belongs to the later governed deployment wave.
    """

    model_config = SettingsConfigDict(
        env_prefix="RO_CORE_",
        case_sensitive=False,
        extra="forbid",
        frozen=True,
    )

    profile: Literal["local"] = "local"
    bind_host: str = "127.0.0.1"
    bind_port: int = Field(default=0, ge=0, le=65_535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @model_validator(mode="before")
    @classmethod
    def accept_contract_field_names(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        aliases = {"bindHost": "bind_host", "bindPort": "bind_port", "logLevel": "log_level"}
        for external, internal in aliases.items():
            if external in normalized:
                if internal in normalized:
                    raise ValueError(f"configuration supplies both {external} and {internal}")
                normalized[internal] = normalized.pop(external)
        return normalized

    @field_validator("bind_host")
    @classmethod
    def require_numeric_loopback(cls, value: str) -> str:
        if value != value.strip() or not value:
            raise ValueError("bind host must be a canonical numeric loopback address")
        try:
            address = ipaddress.ip_address(value)
        except ValueError as error:
            raise ValueError("bind host must be a canonical numeric loopback address") from error
        if not address.is_loopback or str(address) != value:
            raise ValueError("local profile may bind only to a canonical numeric loopback address")
        return value

    def public_projection(self) -> dict[str, str]:
        """Return the deliberately small, non-secret configuration projection."""

        return {
            "schemaVersion": "1.0",
            "profile": self.profile,
            "bindHost": "loopback",
            "bindPort": "ephemeral" if self.bind_port == 0 else "assigned",
        }
