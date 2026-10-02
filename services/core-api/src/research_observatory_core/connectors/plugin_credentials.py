"""Profile-vault connector tokens leased only to the exact brokered origin."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from ..ports.credential_store import (
    CredentialStore,
    CredentialStoreProblem,
    SecretAccessContext,
    SecretKind,
    SecretNotFound,
    SecretPurpose,
    SecretReference,
)
from .plugin_manifest import PluginInvocationPlan

_SCOPE = re.compile(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*\Z")


class PluginCredentialProblem(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PluginCredentialStatus:
    configured: bool
    version: str | None
    origin: tuple[str, str, int] | None


def _reference(plan: PluginInvocationPlan, scope: str, profile_id: str) -> SecretReference:
    plan = PluginInvocationPlan.model_validate(plan)
    if "credential-broker" not in plan.permissions:
        raise PluginCredentialProblem("plugin-credential-permission-denied")
    if not isinstance(scope, str) or len(scope) > 128 or _SCOPE.fullmatch(scope) is None:
        raise PluginCredentialProblem("plugin-credential-scope-invalid")
    publisher = hashlib.sha256(
        (plan.project_id + "\0" + plan.publisher_key_id + "\0" + plan.plugin_id).encode("utf-8")
    ).hexdigest()
    named = hashlib.sha256(scope.encode("utf-8")).hexdigest()
    return SecretReference(profile_id, SecretKind.CONNECTOR_TOKEN, "plugin." + publisher, "scope." + named)


def _origin(plan: PluginInvocationPlan) -> tuple[str, str, int]:
    return plan.destination.scheme, plan.destination.host, plan.destination.port


class PluginCredentialSettings:
    def __init__(self, store: CredentialStore | None, *, profile_id: str = "local-default") -> None:
        self._store, self._profile_id = store, profile_id

    @staticmethod
    def _context(plan: PluginInvocationPlan) -> SecretAccessContext:
        return SecretAccessContext(
            "CAP-04.S05",
            SecretPurpose.CONNECTOR_AUTHENTICATION,
            plan.invocation_id.replace("-", ""),
        )

    @staticmethod
    def _document(plan: PluginInvocationPlan, scope: str, secret: str) -> bytes:
        return json.dumps(
            {
                "schemaVersion": "1.0",
                "projectId": plan.project_id,
                "publisherKeyId": plan.publisher_key_id,
                "pluginId": plan.plugin_id,
                "scope": scope,
                "origin": list(_origin(plan)),
                "secret": secret,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")

    @staticmethod
    def _validated(plan: PluginInvocationPlan, scope: str, raw: bytes) -> str:
        try:
            document = json.loads(raw)
            if (
                not isinstance(document, dict)
                or set(document)
                != {"schemaVersion", "projectId", "publisherKeyId", "pluginId", "scope", "origin", "secret"}
                or document["schemaVersion"] != "1.0"
                or document["projectId"] != plan.project_id
                or document["publisherKeyId"] != plan.publisher_key_id
                or document["pluginId"] != plan.plugin_id
                or document["scope"] != scope
                or document["origin"] != list(_origin(plan))
                or not isinstance(document["secret"], str)
                or not 3 <= len(document["secret"]) <= 1024
                or any(ord(char) < 33 or ord(char) > 126 for char in document["secret"])
            ):
                raise ValueError
            return document["secret"]
        except ValueError, TypeError, KeyError, UnicodeError:
            raise PluginCredentialProblem("plugin-credential-corrupt-or-stale") from None

    def configure(
        self,
        plan: PluginInvocationPlan,
        scope: str,
        secret: str,
        *,
        expected_version: str | None,
    ) -> PluginCredentialStatus:
        reference = _reference(plan, scope, self._profile_id)
        if (
            self._store is None
            or not isinstance(secret, str)
            or not 3 <= len(secret) <= 1024
            or any(ord(char) < 33 or ord(char) > 126 for char in secret)
        ):
            raise PluginCredentialProblem("plugin-credential-invalid-or-unavailable")
        material = bytearray(self._document(plan, scope, secret))
        try:
            record = self._store.put(reference, material, self._context(plan), expected_version=expected_version)
            return PluginCredentialStatus(True, record.version, _origin(plan))
        except CredentialStoreProblem:
            raise PluginCredentialProblem("plugin-credential-store-unavailable") from None
        finally:
            material[:] = b"\0" * len(material)

    @contextmanager
    def lease(self, scope: str, plan: PluginInvocationPlan) -> Iterator[str]:
        reference = _reference(plan, scope, self._profile_id)
        if self._store is None:
            raise PluginCredentialProblem("plugin-credential-unavailable")
        try:
            lease = self._store.lease(reference, self._context(plan))
        except CredentialStoreProblem:
            raise PluginCredentialProblem("plugin-credential-unavailable") from None
        with lease:
            try:
                secret = lease.use(lambda view: self._validated(plan, scope, bytes(view)))
                yield secret
            finally:
                secret = ""

    def status(self, scope: str, plan: PluginInvocationPlan) -> PluginCredentialStatus:
        reference = _reference(plan, scope, self._profile_id)
        if self._store is None:
            return PluginCredentialStatus(False, None, None)
        try:
            record, lease = self._store.lease_record(reference, self._context(plan))
        except SecretNotFound:
            return PluginCredentialStatus(False, None, None)
        except CredentialStoreProblem:
            raise PluginCredentialProblem("plugin-credential-unavailable") from None
        with lease:
            lease.use(lambda view: self._validated(plan, scope, bytes(view)))
        return PluginCredentialStatus(True, record.version, _origin(plan))

    def origin(self, scope: str, plan: PluginInvocationPlan) -> tuple[str, str, int] | None:
        return self.status(scope, plan).origin
