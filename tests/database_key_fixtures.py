"""Explicit in-memory database-key authority for deterministic protected-storage tests."""

from __future__ import annotations

import secrets

from research_observatory_core.ports.credential_store import SecretLease
from research_observatory_core.ports.database_keys import (
    DatabaseKeyConflict,
    DatabaseKeyLease,
    DatabaseKeyUnavailable,
    validate_database_key_identity,
)


class InMemoryDatabaseKeyProvider:
    """Restart-stable test double that never writes key material to project files."""

    def __init__(self) -> None:
        self._active: dict[str, tuple[str, bytes]] = {}
        self._staged: dict[tuple[str, str], tuple[str, bytes]] = {}

    @staticmethod
    def _new() -> tuple[str, bytes]:
        return secrets.token_hex(16), secrets.token_bytes(32)

    @staticmethod
    def _lease(record: tuple[str, bytes]) -> DatabaseKeyLease:
        version, material = record
        return DatabaseKeyLease(version, SecretLease(bytearray(material)))

    def active_key(self, project_id: str, *, create: bool) -> DatabaseKeyLease:
        validate_database_key_identity(project_id)
        record = self._active.get(project_id)
        if record is None:
            if not create:
                raise DatabaseKeyUnavailable("test database key is unavailable")
            record = self._active.setdefault(project_id, self._new())
        return self._lease(record)

    def staged_rekey(self, project_id: str, operation_id: str, *, create: bool) -> DatabaseKeyLease:
        validate_database_key_identity(project_id, operation_id)
        identity = (project_id, operation_id)
        record = self._staged.get(identity)
        if record is None:
            if not create:
                raise DatabaseKeyUnavailable("staged test database key is unavailable")
            record = self._staged.setdefault(identity, self._new())
        return self._lease(record)

    def activate_rekey(
        self,
        project_id: str,
        operation_id: str,
        *,
        expected_active_version: str,
    ) -> str:
        validate_database_key_identity(project_id, operation_id)
        active = self._active.get(project_id)
        staged = self._staged.get((project_id, operation_id))
        if active is None or staged is None:
            raise DatabaseKeyUnavailable("test database rekey material is unavailable")
        if active[0] != expected_active_version:
            raise DatabaseKeyConflict("test database key activation conflicted")
        version = secrets.token_hex(16)
        self._active[project_id] = (version, staged[1])
        return version

    def forget_active(self, project_id: str) -> None:
        self._active.pop(project_id, None)

    def forget_staged(self, project_id: str, operation_id: str) -> None:
        self._staged.pop((project_id, operation_id), None)

    def active_version(self, project_id: str) -> str:
        record = self._active.get(project_id)
        if record is None:
            raise DatabaseKeyUnavailable("test database key is unavailable")
        return record[0]

    def active_material_for_test(self, project_id: str) -> bytes:
        """Return a test-only copy for ciphertext and disclosure assertions."""

        record = self._active.get(project_id)
        if record is None:
            raise DatabaseKeyUnavailable("test database key is unavailable")
        return bytes(record[1])


__all__ = ["InMemoryDatabaseKeyProvider"]
