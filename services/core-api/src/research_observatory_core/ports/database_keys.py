"""Dependency-neutral leases for project-database encryption keys."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

from .credential_store import SecretLease

_PROJECT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_OPERATION_ID = re.compile(r"^[0-9a-f]{32}$")
_VERSION = re.compile(r"^[0-9a-f]{32}$")
T = TypeVar("T")


class DatabaseKeyProblem(RuntimeError):
    """Bounded database-key failure without key material or project paths."""


class DatabaseKeyUnavailable(DatabaseKeyProblem):
    """The required key does not exist or cannot be recovered."""


class DatabaseKeyConflict(DatabaseKeyProblem):
    """A key creation or activation precondition did not match."""


@dataclass(slots=True)
class DatabaseKeyLease:
    """Versioned mutable key lease cleared at the trust-boundary return."""

    version: str
    _secret: SecretLease

    def __post_init__(self) -> None:
        if _VERSION.fullmatch(self.version) is None or not isinstance(self._secret, SecretLease):
            raise ValueError("database key lease is invalid")

    def use(self, consumer: Callable[[memoryview], T]) -> T:
        return self._secret.use(consumer)

    def close(self) -> None:
        self._secret.close()

    def __enter__(self) -> DatabaseKeyLease:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


def validate_database_key_identity(project_id: str, operation_id: str | None = None) -> None:
    if not isinstance(project_id, str) or _PROJECT_ID.fullmatch(project_id) is None:
        raise ValueError("database key project identity is invalid")
    if operation_id is not None and (
        not isinstance(operation_id, str) or _OPERATION_ID.fullmatch(operation_id) is None
    ):
        raise ValueError("database key operation identity is invalid")


@runtime_checkable
class DatabaseKeyProvider(Protocol):
    def active_key(self, project_id: str, *, create: bool) -> DatabaseKeyLease: ...

    def staged_rekey(self, project_id: str, operation_id: str, *, create: bool) -> DatabaseKeyLease: ...

    def activate_rekey(
        self,
        project_id: str,
        operation_id: str,
        *,
        expected_active_version: str,
    ) -> str: ...


__all__ = [
    "DatabaseKeyConflict",
    "DatabaseKeyLease",
    "DatabaseKeyProblem",
    "DatabaseKeyProvider",
    "DatabaseKeyUnavailable",
    "validate_database_key_identity",
]
