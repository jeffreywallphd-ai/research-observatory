"""Purpose-bound protected derivative keys, separate from project database keys."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, TypeVar, runtime_checkable

from .credential_store import SecretLease, SecretUnavailable
from .database_keys import validate_database_key_identity

_VERSION = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
T = TypeVar("T")


class DerivativeKeyProblem(RuntimeError):
    """Content-free unavailable, stale or mismatched index key authority."""


class DerivativePurpose(StrEnum):
    LEXICAL = "lexical-fts5-v1"


@dataclass(frozen=True, slots=True)
class DerivativeKeyScope:
    project_id: str
    generation_id: str
    purpose: DerivativePurpose
    canonical_key_version: str
    lifecycle_sha256: str

    def __post_init__(self) -> None:
        validate_database_key_identity(self.project_id)
        validate_database_key_identity(self.generation_id)
        if (
            not isinstance(self.purpose, DerivativePurpose)
            or not isinstance(self.canonical_key_version, str)
            or _VERSION.fullmatch(self.canonical_key_version) is None
            or not isinstance(self.lifecycle_sha256, str)
            or _SHA256.fullmatch(self.lifecycle_sha256) is None
        ):
            raise ValueError("derivative key scope is invalid")


@dataclass(frozen=True, slots=True)
class DerivativeKeyLease:
    scope: DerivativeKeyScope
    version: str
    _secret: SecretLease = field(repr=False, compare=False)
    _current: Callable[[], None] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scope, DerivativeKeyScope)
            or not isinstance(self.version, str)
            or _VERSION.fullmatch(self.version) is None
            or not isinstance(self._secret, SecretLease)
            or not callable(self._current)
        ):
            raise ValueError("derivative key lease is invalid")

    def assert_current(self, expected: DerivativeKeyScope) -> None:
        if not isinstance(expected, DerivativeKeyScope) or expected != self.scope:
            raise DerivativeKeyProblem("derivative key scope is unavailable")
        try:
            if self._secret.use(len) != 32:
                raise DerivativeKeyProblem("derivative key is unavailable")
            self._current()
        except SecretUnavailable:
            raise DerivativeKeyProblem("derivative key is unavailable") from None

    def use(self, expected: DerivativeKeyScope, consumer: Callable[[memoryview], T]) -> T:
        self.assert_current(expected)
        return self._secret.use(consumer)

    def close(self) -> None:
        self._secret.close()

    def __enter__(self) -> DerivativeKeyLease:
        self.assert_current(self.scope)
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


@runtime_checkable
class DerivativeKeyProvider(Protocol):
    def lease(self, scope: DerivativeKeyScope, *, create: bool) -> DerivativeKeyLease: ...

    def lease_for_retirement(
        self, scope: DerivativeKeyScope, *, expected_version: str, authorize: Callable[[], None]
    ) -> DerivativeKeyLease:
        """Recovery only: exact retired scope/version, live Core authorization.

        This cannot create keys or grant ordinary index/query eligibility.
        The owning recovery operation must hold and authenticate its file
        before requesting the lease and recheck retirement on every use.
        """
        ...

    def revoke(self, scope: DerivativeKeyScope, *, expected_version: str) -> None: ...


__all__ = [
    "DerivativeKeyLease",
    "DerivativeKeyProblem",
    "DerivativeKeyProvider",
    "DerivativeKeyScope",
    "DerivativePurpose",
]
