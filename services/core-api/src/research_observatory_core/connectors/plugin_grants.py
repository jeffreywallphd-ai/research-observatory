"""Core-only researcher decisions and content-free connector grant audit types.

The API/native caller must authenticate the actor and capture an explicit
researcher action for the exact package and permissions before constructing a
confirmation. These values are never accepted from a plugin or worker frame.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..domain_contracts import is_uuid_v7
from .contracts import _utc
from .plugin_manifest import PluginDestination, PluginProjectGrant

_TRACE = re.compile(r"[0-9a-f]{32}\Z")


class PluginGrantProblem(ValueError):
    """Bounded denial without a package path, credential, or research query."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PluginGrantActor:
    """Authenticated Core actor facts supplied by the native command boundary."""

    actor_id: str
    trace_id: str
    occurred_at: str
    actor_type: str = "human"


def _actor(actor: PluginGrantActor, *, allow_system: bool = False) -> None:
    """Validate authenticated actor facts without depending on storage code."""

    if (
        not isinstance(actor, PluginGrantActor)
        or actor.actor_type not in ({"human", "system"} if allow_system else {"human"})
        or not is_uuid_v7(actor.actor_id)
        or not isinstance(actor.trace_id, str)
        or _TRACE.fullmatch(actor.trace_id) is None
    ):
        raise PluginGrantProblem("plugin-grant-actor-invalid")
    try:
        _utc(actor.occurred_at)
    except ValueError:
        raise PluginGrantProblem("plugin-grant-actor-invalid") from None


@dataclass(frozen=True, slots=True)
class PluginEnableConfirmation:
    """Exact visible permission review; a package cannot approve itself."""

    action_id: str
    project_id: str
    plugin_id: str
    plugin_version: str
    publisher_key_id: str
    trusted_key_sha256: str
    trusted_key_revision: int
    package_sha256: str
    manifest_sha256: str
    permissions: tuple[str, ...]
    destinations: tuple[PluginDestination, ...]
    operations: tuple[str, ...]
    data_classes: tuple[str, ...]
    credential_scopes: tuple[str, ...]
    expected_revision: int | None


@dataclass(frozen=True, slots=True)
class PluginGrantAuditEvent:
    event_id: str
    project_id: str
    plugin_id: str
    event_kind: str
    reason_code: str
    revision: int | None
    publisher_key_id: str | None
    package_sha256: str | None
    invocation_id: str | None
    provenance_event_id: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class PluginCurrentGrant:
    """Current project grant plus the local key authority it approved."""

    grant: PluginProjectGrant
    trusted_key_sha256: str
    trusted_key_revision: int
    operations: tuple[str, ...]
    data_classes: tuple[str, ...]
    credential_scopes: tuple[str, ...]
