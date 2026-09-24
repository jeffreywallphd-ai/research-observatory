"""Broker-private, atomic provider configuration in the existing profile vault.

Only native configuration code supplies values; projections contain presence and
CAS versions, never values. Missing records differ from inaccessible protection.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field

from ..ports.credential_store import (
    CredentialStore,
    CredentialStoreProblem,
    SecretAccessContext,
    SecretConflict,
    SecretKind,
    SecretNotFound,
    SecretPurpose,
    SecretReference,
)
from .contracts import ConnectorCapabilities, ConnectorModel, ProviderId
from .providers import HOSTS, ProviderProblem, capabilities
from .transport import bounded_json


class ConnectorConnectionStatus(ConnectorModel):
    provider_id: ProviderId
    configuration: Literal["ready", "not-configured", "unavailable"]
    key_configured: bool
    contact_configured: bool
    version: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None


@dataclass(slots=True)
class _Connection:
    key: str | None = field(repr=False)
    contact: str | None = field(repr=False)
    version: str | None

    def clear(self) -> None:
        # Release transient string references; the backing mutable lease is
        # zeroed by CredentialStore. Python does not guarantee string erasure.
        self.key = self.contact = None


def _reference(provider: str) -> SecretReference:
    if provider not in HOSTS:
        raise ProviderProblem("unsupported-operation")
    return SecretReference("local-default", SecretKind.CONNECTOR_TOKEN, provider, "connection-v1")


def _validate(provider: str, key: object, contact: object) -> tuple[str | None, str | None]:
    _reference(provider)
    for value in (key, contact):
        if value is not None and (
            not isinstance(value, str)
            or not 3 <= len(value) <= 1024
            or any(not 33 <= ord(char) <= 126 for char in value)
        ):
            raise ProviderProblem("invalid-query")
    if key is not None and provider not in {"openalex", "semantic-scholar"}:
        raise ProviderProblem("invalid-query")
    if contact is not None and (
        provider == "semantic-scholar" or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(contact)) is None
    ):
        raise ProviderProblem("invalid-query")
    assert key is None or isinstance(key, str)
    assert contact is None or isinstance(contact, str)
    return key, contact


def _projection(provider: str, connection: _Connection) -> ConnectorConnectionStatus:
    return ConnectorConnectionStatus(
        provider_id=provider,
        configuration="not-configured" if provider == "unpaywall" and connection.contact is None else "ready",
        key_configured=connection.key is not None,
        contact_configured=connection.contact is not None,
        version=connection.version,
    )


class ConnectorSettings:
    def __init__(self, store: CredentialStore | None):
        self._store = store

    @contextmanager
    def _read(self, provider: str, context: SecretAccessContext) -> Iterator[_Connection]:
        reference = _reference(provider)
        if self._store is None:
            raise ProviderProblem("provider-unavailable")
        try:
            record, lease = self._store.lease_record(reference, context)
        except SecretNotFound:
            yield _Connection(None, None, None)
            return
        except CredentialStoreProblem:
            raise ProviderProblem("provider-unavailable") from None
        with lease:
            try:

                def parse(view: memoryview) -> tuple[str | None, str | None]:
                    if len(view) > 8192:
                        raise ProviderProblem("incompatible-response")
                    document = bounded_json(bytes(view))
                    if (
                        not isinstance(document, dict)
                        or set(document) != {"version", "provider", "key", "contact"}
                        or document["version"] != "1.0"
                        or document["provider"] != provider
                    ):
                        raise ProviderProblem("incompatible-response")
                    return _validate(provider, document["key"], document["contact"])

                key, contact = lease.use(parse)
                connection = _Connection(key, contact, record.version)
                del key, contact
            except ProviderProblem, CredentialStoreProblem:
                raise ProviderProblem("provider-unavailable") from None
            try:
                yield connection
            finally:
                connection.clear()

    @contextmanager
    def lease(self, provider: str, context: SecretAccessContext) -> Iterator[_Connection]:
        """Caller must hold current operation authority before entering this lease."""
        with self._read(provider, context) as connection:
            if _projection(provider, connection).configuration != "ready":
                raise ProviderProblem("not-configured")
            yield connection

    def status(self, provider: str) -> ConnectorConnectionStatus:
        _reference(provider)
        context = SecretAccessContext("CAP-04.S02", SecretPurpose.CONNECTOR_AUTHENTICATION, secrets.token_hex(16))
        try:
            with self._read(provider, context) as connection:
                return _projection(provider, connection)
        except ProviderProblem:
            return ConnectorConnectionStatus(
                provider_id=provider,
                configuration="unavailable",
                key_configured=False,
                contact_configured=False,
                version=None,
            )

    def describe(self, provider: str) -> ConnectorCapabilities:
        return ConnectorCapabilities.model_validate(
            capabilities(provider).model_dump() | {"configuration": self.status(provider).configuration}
        )

    def replace(
        self,
        provider: str,
        *,
        key: str | None,
        contact: str | None,
        expected_version: str | None,
        context: SecretAccessContext,
        preserve_key: bool = False,
        preserve_contact: bool = False,
    ) -> ConnectorConnectionStatus:
        """Complete CAS replacement; explicit null clears without deleting history."""
        key, contact = _validate(provider, key, contact)
        if preserve_key or preserve_contact:
            if (
                expected_version is None
                or (preserve_key and key is not None)
                or (preserve_contact and contact is not None)
            ):
                raise ProviderProblem("invalid-query")
            with self._read(provider, context) as previous:
                if previous.version != expected_version:
                    raise SecretConflict("connector-configuration-conflict")
                return self.replace(
                    provider,
                    key=previous.key if preserve_key else key,
                    contact=previous.contact if preserve_contact else contact,
                    expected_version=expected_version,
                    context=context,
                )
        if self._store is None:
            raise ProviderProblem("provider-unavailable")
        material = bytearray(
            json.dumps(
                {"version": "1.0", "provider": provider, "key": key, "contact": contact},
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")
        )
        try:
            record = self._store.put(_reference(provider), material, context, expected_version=expected_version)
            return _projection(provider, _Connection(key, contact, record.version))
        finally:
            material[:] = b"\0" * len(material)
