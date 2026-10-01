"""Protected append-only project grant decisions for signed connector plugins.

Only an authenticated Core command may call enable/revoke. This repository
checks the exact researcher-confirmed package and project-local publisher pin;
the launcher rechecks current grant, package bytes and policy at dispatch.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .connectors.plugin_grants import (
    PluginCurrentGrant,
    PluginEnableConfirmation,
    PluginGrantActor,
    PluginGrantAuditEvent,
    PluginGrantProblem,
)
from .connectors.plugin_manifest import (
    _VERIFIED_SEAL,
    PluginProjectGrant,
    VerifiedPluginPackage,
)
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .storage import (
    _DATABASE_ERRORS,
    CanonicalConnection,
    StorageProblem,
    _normalize_utc_millisecond,
    _project_identity,
    open_canonical_database,
)

_TRACE = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CODE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_PLUGIN = re.compile(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*\Z")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _actor(actor: PluginGrantActor, *, allow_system: bool = False) -> None:
    if (
        not isinstance(actor, PluginGrantActor)
        or actor.actor_type not in ({"human", "system"} if allow_system else {"human"})
        or not is_uuid_v7(actor.actor_id)
        or _TRACE.fullmatch(actor.trace_id) is None
    ):
        raise PluginGrantProblem("plugin-grant-actor-invalid")
    try:
        if _normalize_utc_millisecond(actor.occurred_at) != actor.occurred_at:
            raise ValueError
    except ValueError, StorageProblem:
        raise PluginGrantProblem("plugin-grant-actor-invalid") from None


def _package(package: VerifiedPluginPackage) -> None:
    if not isinstance(package, VerifiedPluginPackage) or package._seal is not _VERIFIED_SEAL:
        raise PluginGrantProblem("plugin-package-unverified")


def _confirmation_digest(confirmation: PluginEnableConfirmation, actor: PluginGrantActor) -> str:
    return _digest(
        {
            "actionId": confirmation.action_id,
            "actorId": actor.actor_id,
            "projectId": confirmation.project_id,
            "pluginId": confirmation.plugin_id,
            "pluginVersion": confirmation.plugin_version,
            "publisherKeyId": confirmation.publisher_key_id,
            "trustedKeySha256": confirmation.trusted_key_sha256,
            "trustedKeyRevision": confirmation.trusted_key_revision,
            "packageSha256": confirmation.package_sha256,
            "manifestSha256": confirmation.manifest_sha256,
            "permissions": list(confirmation.permissions),
            "destinations": [item.model_dump(mode="json", by_alias=True) for item in confirmation.destinations],
            "operations": list(confirmation.operations),
            "dataClasses": list(confirmation.data_classes),
            "credentialScopes": list(confirmation.credential_scopes),
            "expectedRevision": confirmation.expected_revision,
        }
    )


class SqlitePluginGrantRepository:
    """Project-local canonical grant history; no profile-wide installed registry."""

    def __init__(self, database: Path, project_id: str) -> None:
        try:
            canonical_project, _ = _project_identity(project_id)
        except StorageProblem:
            raise PluginGrantProblem("plugin-grant-project-invalid") from None
        if not Path(database).is_absolute():
            raise PluginGrantProblem("plugin-grant-storage-invalid")
        self._database = Path(database)
        self._project = canonical_project

    @contextmanager
    def _transaction(self) -> Iterator[CanonicalConnection]:
        connection: CanonicalConnection | None = None
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project)
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except PluginGrantProblem:
            raise
        except (*_DATABASE_ERRORS, StorageProblem, OSError, sqlite3.Error):
            raise PluginGrantProblem("plugin-grant-storage-invalid") from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def _latest(self, connection: CanonicalConnection, plugin_id: str):
        return connection.execute(
            "SELECT event_id,revision,event_kind,publisher_key_id,grant_json,package_sha256,"
            "trusted_key_sha256,trusted_key_revision,review_json "
            "FROM plugin_grant_events WHERE project_id=? AND plugin_id=? AND revision IS NOT NULL "
            "ORDER BY revision DESC LIMIT 1",
            (self._project, plugin_id),
        ).fetchone()

    def _append(
        self,
        connection: CanonicalConnection,
        *,
        plugin_id: str,
        event_kind: str,
        reason_code: str,
        actor: PluginGrantActor,
        revision: int | None = None,
        predecessor_event_id: str | None = None,
        action_id: str | None = None,
        action_sha256: str | None = None,
        publisher_key_id: str | None = None,
        package_sha256: str | None = None,
        manifest_sha256: str | None = None,
        trusted_key_sha256: str | None = None,
        trusted_key_revision: int | None = None,
        review_json: str | None = None,
        grant_json: str | None = None,
        invocation_id: str | None = None,
    ) -> str:
        event_id = new_uuid_v7()
        event_type = "connector.plugin-" + event_kind
        record_sha256 = _digest(
            {
                "projectId": self._project,
                "pluginId": plugin_id,
                "eventKind": event_kind,
                "reasonCode": reason_code,
                "revision": revision,
                "packageSha256": package_sha256,
                "manifestSha256": manifest_sha256,
                "trustedKeySha256": trusted_key_sha256,
                "trustedKeyRevision": trusted_key_revision,
                "reviewSha256": hashlib.sha256(review_json.encode("utf-8")).hexdigest() if review_json else None,
                "invocationId": invocation_id,
                "grantSha256": hashlib.sha256(grant_json.encode("utf-8")).hexdigest() if grant_json else None,
            }
        )
        connection.execute(
            "INSERT INTO provenance_events (event_id,project_id,revision_id,event_type,occurred_at,"
            "trace_id,actor_type,actor_id,record_sha256) VALUES (?,?,NULL,?,?,?,?,?,?)",
            (
                event_id,
                self._project,
                event_type,
                actor.occurred_at,
                actor.trace_id,
                actor.actor_type,
                actor.actor_id,
                record_sha256,
            ),
        )
        outbox_id: str | None = None
        if event_kind in {"enabled", "revoked"}:
            outbox_id = new_uuid_v7()
            assert action_id is not None
            connection.execute(
                "INSERT INTO outbox_events (outbox_id,project_id,revision_id,event_type,occurred_at,"
                "available_at,state,idempotency_key,record_sha256) VALUES (?,?,NULL,?,?,?,'pending',?,?)",
                (
                    outbox_id,
                    self._project,
                    event_type,
                    actor.occurred_at,
                    actor.occurred_at,
                    "plugin-grant-" + action_id,
                    record_sha256,
                ),
            )
        connection.execute(
            "INSERT INTO plugin_grant_events (event_id,project_id,plugin_id,event_kind,reason_code,revision,"
            "predecessor_event_id,action_id,action_sha256,publisher_key_id,package_sha256,manifest_sha256,"
            "trusted_key_sha256,trusted_key_revision,review_json,"
            "grant_json,invocation_id,record_sha256,provenance_event_id,outbox_id,actor_id,trace_id,occurred_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                self._project,
                plugin_id,
                event_kind,
                reason_code,
                revision,
                predecessor_event_id,
                action_id,
                action_sha256,
                publisher_key_id,
                package_sha256,
                manifest_sha256,
                trusted_key_sha256,
                trusted_key_revision,
                review_json,
                grant_json,
                invocation_id,
                record_sha256,
                event_id,
                outbox_id,
                actor.actor_id,
                actor.trace_id,
                actor.occurred_at,
            ),
        )
        return event_id

    def enable(
        self,
        package: VerifiedPluginPackage,
        confirmation: PluginEnableConfirmation,
        *,
        actor: PluginGrantActor,
        trusted_key_sha256: str,
        trusted_key_revision: int,
    ) -> PluginProjectGrant:
        """Append an exact researcher-confirmed grant, or an audited denial."""

        _actor(actor)
        _package(package)
        if not isinstance(confirmation, PluginEnableConfirmation) or confirmation.project_id != self._project:
            raise PluginGrantProblem("plugin-grant-project-mismatch")
        if not is_uuid_v7(confirmation.action_id) or (
            confirmation.expected_revision is not None
            and (type(confirmation.expected_revision) is not int or confirmation.expected_revision < 1)
        ):
            raise PluginGrantProblem("plugin-grant-confirmation-invalid")
        if (
            not isinstance(trusted_key_sha256, str)
            or _SHA.fullmatch(trusted_key_sha256) is None
            or type(trusted_key_revision) is not int
            or not 1 <= trusted_key_revision <= 2**53 - 1
        ):
            raise PluginGrantProblem("plugin-grant-trust-invalid")
        manifest = package.manifest
        plugin_id = manifest.plugin_id
        try:
            action_sha256 = _confirmation_digest(confirmation, actor)
        except AttributeError, TypeError, ValueError:
            raise PluginGrantProblem("plugin-grant-confirmation-invalid") from None
        exact = (
            confirmation.plugin_id == plugin_id
            and confirmation.plugin_version == manifest.plugin_version
            and confirmation.publisher_key_id == manifest.publisher_key_id
            and confirmation.trusted_key_sha256 == trusted_key_sha256
            and confirmation.trusted_key_revision == trusted_key_revision
            and confirmation.package_sha256 == package.package_sha256
            and confirmation.manifest_sha256 == package.manifest_sha256
            and confirmation.permissions == manifest.permissions
            and confirmation.destinations == manifest.destinations
            and confirmation.operations == manifest.operations
            and confirmation.data_classes == manifest.data_classes
            and confirmation.credential_scopes == manifest.credential_scopes
        )
        with self._transaction() as connection:
            replay = connection.execute(
                "SELECT event_id,action_sha256,grant_json FROM plugin_grant_events WHERE project_id=? AND action_id=?",
                (self._project, confirmation.action_id),
            ).fetchone()
            if not exact:
                reason = "plugin-grant-confirmation-mismatch"
            elif replay is not None:
                if replay[1] != action_sha256 or replay[2] is None:
                    reason = "plugin-grant-action-conflict"
                else:
                    latest = self._latest(connection, plugin_id)
                    if latest is not None and latest[0] == replay[0] and latest[2] == "enabled":
                        return PluginProjectGrant.model_validate_json(replay[2])
                    reason = "plugin-grant-action-stale"
            else:
                latest = self._latest(connection, plugin_id)
                if latest is not None and latest[3] != manifest.publisher_key_id:
                    reason = "plugin-grant-publisher-collision"
                elif (latest[1] if latest else None) != confirmation.expected_revision:
                    reason = "plugin-grant-stale-revision"
                else:
                    revision = (latest[1] if latest else 0) + 1
                    grant = PluginProjectGrant.model_validate(
                        {
                            "projectId": self._project,
                            "pluginId": plugin_id,
                            "pluginVersion": manifest.plugin_version,
                            "packageSha256": package.package_sha256,
                            "manifestSha256": package.manifest_sha256,
                            "publisherKeyId": manifest.publisher_key_id,
                            "permissions": manifest.permissions,
                            "destinations": manifest.destinations,
                            "revision": revision,
                        }
                    )
                    self._append(
                        connection,
                        plugin_id=plugin_id,
                        event_kind="enabled",
                        reason_code="plugin-grant-confirmed",
                        actor=actor,
                        revision=revision,
                        predecessor_event_id=latest[0] if latest else None,
                        action_id=confirmation.action_id,
                        action_sha256=action_sha256,
                        publisher_key_id=manifest.publisher_key_id,
                        package_sha256=package.package_sha256,
                        manifest_sha256=package.manifest_sha256,
                        trusted_key_sha256=trusted_key_sha256,
                        trusted_key_revision=trusted_key_revision,
                        review_json=_canonical(
                            {
                                "operations": list(confirmation.operations),
                                "dataClasses": list(confirmation.data_classes),
                                "credentialScopes": list(confirmation.credential_scopes),
                            }
                        ),
                        grant_json=grant.model_dump_json(by_alias=True),
                    )
                    return grant
            self._append(
                connection,
                plugin_id=plugin_id,
                event_kind="denied",
                reason_code=reason,
                actor=actor,
                publisher_key_id=manifest.publisher_key_id,
                package_sha256=package.package_sha256,
                manifest_sha256=package.manifest_sha256,
            )
        raise PluginGrantProblem(reason)

    def revoke(self, plugin_id: str, *, expected_revision: int, action_id: str, actor: PluginGrantActor) -> None:
        _actor(actor)
        if not _PLUGIN.fullmatch(plugin_id) or len(plugin_id) > 121 or not is_uuid_v7(action_id):
            raise PluginGrantProblem("plugin-grant-command-invalid")
        if type(expected_revision) is not int or expected_revision < 1:
            raise PluginGrantProblem("plugin-grant-command-invalid")
        action_sha256 = _digest(
            {
                "actionId": action_id,
                "actorId": actor.actor_id,
                "projectId": self._project,
                "pluginId": plugin_id,
                "expectedRevision": expected_revision,
                "action": "revoke",
            }
        )
        with self._transaction() as connection:
            replay = connection.execute(
                "SELECT event_id,action_sha256,event_kind FROM plugin_grant_events WHERE project_id=? AND action_id=?",
                (self._project, action_id),
            ).fetchone()
            if replay is not None:
                if (replay[1], replay[2]) != (action_sha256, "revoked"):
                    reason = "plugin-grant-action-conflict"
                else:
                    latest = self._latest(connection, plugin_id)
                    if latest is not None and latest[0] == replay[0] and latest[2] == "revoked":
                        return
                    reason = "plugin-grant-action-stale"
            else:
                latest = self._latest(connection, plugin_id)
                if latest is None or latest[2] != "enabled":
                    reason = "plugin-grant-not-active"
                elif latest[1] != expected_revision:
                    reason = "plugin-grant-stale-revision"
                else:
                    self._append(
                        connection,
                        plugin_id=plugin_id,
                        event_kind="revoked",
                        reason_code="plugin-grant-revoked",
                        actor=actor,
                        revision=expected_revision + 1,
                        predecessor_event_id=latest[0],
                        action_id=action_id,
                        action_sha256=action_sha256,
                        publisher_key_id=latest[3],
                        package_sha256=latest[5],
                    )
                    return
            self._append(connection, plugin_id=plugin_id, event_kind="denied", reason_code=reason, actor=actor)
        raise PluginGrantProblem(reason)

    def current_grant_authority(self, plugin_id: str) -> PluginCurrentGrant | None:
        if not _PLUGIN.fullmatch(plugin_id) or len(plugin_id) > 121:
            raise PluginGrantProblem("plugin-grant-command-invalid")
        connection = open_canonical_database(self._database, expected_project_id=self._project)
        try:
            latest = self._latest(connection, plugin_id)
            if latest is None or latest[2] != "enabled":
                return None
            grant = PluginProjectGrant.model_validate_json(latest[4])
            if (
                grant.project_id != self._project
                or grant.plugin_id != plugin_id
                or grant.revision != latest[1]
                or grant.publisher_key_id != latest[3]
                or grant.package_sha256 != latest[5]
                or latest[6] is None
                or latest[7] is None
                or latest[8] is None
            ):
                raise PluginGrantProblem("plugin-grant-integrity-invalid")
            try:
                review = json.loads(latest[8])
                if (
                    not isinstance(review, dict)
                    or set(review) != {"operations", "dataClasses", "credentialScopes"}
                    or any(not isinstance(review[field], list) for field in review)
                    or any(not all(isinstance(value, str) for value in review[field]) for field in review)
                ):
                    raise ValueError
            except (ValueError, TypeError):
                raise PluginGrantProblem("plugin-grant-integrity-invalid") from None
            return PluginCurrentGrant(
                grant, latest[6], latest[7],
                tuple(review["operations"]), tuple(review["dataClasses"]), tuple(review["credentialScopes"]),
            )
        finally:
            connection.close()

    def current_grant(self, plugin_id: str) -> PluginProjectGrant | None:
        authority = self.current_grant_authority(plugin_id)
        return authority.grant if authority is not None else None

    def record_denial(
        self,
        *,
        plugin_id: str,
        reason_code: str,
        actor: PluginGrantActor,
        invocation_id: str | None = None,
        package_sha256: str | None = None,
    ) -> None:
        """Persist only stable bounded denial facts; never a URL or exception text."""

        _actor(actor, allow_system=True)
        if (
            not _PLUGIN.fullmatch(plugin_id)
            or len(plugin_id) > 121
            or _CODE.fullmatch(reason_code) is None
            or (invocation_id is not None and not is_uuid_v7(invocation_id))
            or (package_sha256 is not None and _SHA.fullmatch(package_sha256) is None)
        ):
            raise PluginGrantProblem("plugin-grant-audit-invalid")
        with self._transaction() as connection:
            self._append(
                connection,
                plugin_id=plugin_id,
                event_kind="denied",
                reason_code=reason_code,
                actor=actor,
                invocation_id=invocation_id,
                package_sha256=package_sha256,
            )

    def audit_history(self, plugin_id: str) -> tuple[PluginGrantAuditEvent, ...]:
        if not _PLUGIN.fullmatch(plugin_id) or len(plugin_id) > 121:
            raise PluginGrantProblem("plugin-grant-command-invalid")
        connection = open_canonical_database(self._database, expected_project_id=self._project)
        try:
            rows = connection.execute(
                "SELECT event_id,project_id,plugin_id,event_kind,reason_code,revision,publisher_key_id,"
                "package_sha256,invocation_id,provenance_event_id,occurred_at "
                "FROM plugin_grant_events WHERE project_id=? AND plugin_id=? ORDER BY audit_sequence",
                (self._project, plugin_id),
            ).fetchall()
            return tuple(PluginGrantAuditEvent(*row) for row in rows)
        finally:
            connection.close()
