"""Project grant persistence required by Core plugin authority services."""

from __future__ import annotations

from typing import Protocol

from ..connectors.plugin_grants import (
    PluginCurrentGrant,
    PluginEnableConfirmation,
    PluginGrantActor,
    PluginGrantAuditEvent,
)
from ..connectors.plugin_manifest import PluginProjectGrant, VerifiedPluginPackage


class PluginGrantRepository(Protocol):
    def enable(
        self,
        package: VerifiedPluginPackage,
        confirmation: PluginEnableConfirmation,
        *,
        actor: PluginGrantActor,
        trusted_key_sha256: str,
        trusted_key_revision: int,
    ) -> PluginProjectGrant: ...

    def revoke(self, plugin_id: str, *, expected_revision: int, action_id: str, actor: PluginGrantActor) -> None: ...

    def current_grant_authority(self, plugin_id: str) -> PluginCurrentGrant | None: ...

    def current_grant(self, plugin_id: str) -> PluginProjectGrant | None: ...

    def record_denial(
        self,
        *,
        plugin_id: str,
        reason_code: str,
        actor: PluginGrantActor,
        invocation_id: str | None = None,
        package_sha256: str | None = None,
    ) -> None: ...

    def audit_history(self, plugin_id: str) -> tuple[PluginGrantAuditEvent, ...]: ...
