"""Dependency-neutral scoped secret storage and short-lived access leases."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, TypeVar, runtime_checkable

_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,118}[a-z0-9])?$")
_CAPABILITY = re.compile(r"^CAP-[0-9]{2}(?:\.S[0-9]{2})?$")
_AUDIT_CONTEXT = re.compile(r"^[0-9a-f]{32}$")
_VERSION = re.compile(r"^[0-9a-f]{32}$")
_REFERENCE_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_REASON = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

T = TypeVar("T")


class CredentialStoreProblem(RuntimeError):
    """Bounded credential-store failure that never includes secret material."""


class SecretUnavailable(CredentialStoreProblem):
    """The requested secret or its OS protection authority is unavailable."""


class SecretNotFound(SecretUnavailable):
    """No encrypted record exists for the exact scoped secret reference."""


class SecretConflict(CredentialStoreProblem):
    """A create or compare-and-swap precondition did not match."""


class SecretCorrupt(CredentialStoreProblem):
    """Protected material failed the exact application envelope contract."""


class SecretAccessDenied(CredentialStoreProblem):
    """The scoped request or its required audit publication was denied."""


class SecretKind(StrEnum):
    PROVIDER_KEY = "provider-key"
    CONNECTOR_TOKEN = "connector-token"
    SIGNING_TRUST = "signing-trust"
    ENCRYPTION_KEY_MATERIAL = "encryption-key-material"


def _require_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None or ".." in value or "--" in value:
        raise ValueError(f"{field} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class SecretReference:
    profile_id: str
    kind: SecretKind
    subject_id: str
    name: str

    def __post_init__(self) -> None:
        _require_identifier(self.profile_id, "secret profile identity")
        if not isinstance(self.kind, SecretKind):
            raise ValueError("secret kind is invalid")
        _require_identifier(self.subject_id, "secret subject identity")
        _require_identifier(self.name, "secret name")


@dataclass(frozen=True, slots=True)
class SecretAccessContext:
    calling_capability: str
    purpose: str
    audit_context: str

    def __post_init__(self) -> None:
        if not isinstance(self.calling_capability, str) or _CAPABILITY.fullmatch(self.calling_capability) is None:
            raise ValueError("calling capability is invalid")
        _require_identifier(self.purpose, "secret access purpose")
        if not isinstance(self.audit_context, str) or _AUDIT_CONTEXT.fullmatch(self.audit_context) is None:
            raise ValueError("secret audit context is invalid")


@dataclass(frozen=True, slots=True)
class SecretRecord:
    version: str
    kind: SecretKind

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or _VERSION.fullmatch(self.version) is None:
            raise ValueError("secret version is invalid")
        if not isinstance(self.kind, SecretKind):
            raise ValueError("secret kind is invalid")


@dataclass(frozen=True, slots=True)
class SecretAuditEvent:
    operation: Literal["put", "lease"]
    outcome: Literal["authorized"]
    reason_code: str
    reference_token: str
    audit_context: str

    def __post_init__(self) -> None:
        if self.operation not in ("put", "lease") or self.outcome != "authorized":
            raise ValueError("secret audit event is invalid")
        if not isinstance(self.reason_code, str) or _REASON.fullmatch(self.reason_code) is None:
            raise ValueError("secret audit reason is invalid")
        if not isinstance(self.reference_token, str) or _REFERENCE_TOKEN.fullmatch(self.reference_token) is None:
            raise ValueError("secret audit reference is invalid")
        if not isinstance(self.audit_context, str) or _AUDIT_CONTEXT.fullmatch(self.audit_context) is None:
            raise ValueError("secret audit context is invalid")


class SecretLease:
    """Mutable in-process secret buffer cleared when its bounded lease closes."""

    __slots__ = ("__material",)

    def __init__(self, material: bytearray) -> None:
        if not isinstance(material, bytearray) or not material:
            raise ValueError("secret lease material is invalid")
        self.__material: bytearray | None = material

    def use(self, consumer: Callable[[memoryview], T]) -> T:
        material = self.__material
        if material is None:
            raise SecretUnavailable("secret lease is unavailable")
        if not callable(consumer):
            raise ValueError("secret consumer is invalid")
        return consumer(memoryview(material).toreadonly())

    def close(self) -> None:
        material = self.__material
        self.__material = None
        if material is not None:
            material[:] = b"\0" * len(material)

    def __enter__(self) -> SecretLease:
        if self.__material is None:
            raise SecretUnavailable("secret lease is unavailable")
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


@runtime_checkable
class CredentialStore(Protocol):
    def put(
        self,
        reference: SecretReference,
        material: bytes | bytearray,
        context: SecretAccessContext,
        *,
        expected_version: str | None = None,
    ) -> SecretRecord: ...

    def lease(self, reference: SecretReference, context: SecretAccessContext) -> SecretLease: ...


SecretAuditSink = Callable[[SecretAuditEvent], None]


__all__ = [
    "CredentialStore",
    "CredentialStoreProblem",
    "SecretAccessContext",
    "SecretAccessDenied",
    "SecretAuditEvent",
    "SecretAuditSink",
    "SecretConflict",
    "SecretCorrupt",
    "SecretKind",
    "SecretLease",
    "SecretNotFound",
    "SecretRecord",
    "SecretReference",
    "SecretUnavailable",
]
