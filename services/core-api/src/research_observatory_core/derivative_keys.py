"""Derivative key namespace over the existing approved profile vault adapter."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict

from .ports.credential_store import (
    CredentialStore,
    CredentialStoreProblem,
    SecretAccessContext,
    SecretConflict,
    SecretKind,
    SecretNotFound,
    SecretPurpose,
    SecretReference,
)
from .ports.database_keys import DatabaseKeyProblem, DatabaseKeyProvider
from .ports.derivative_keys import DerivativeKeyLease, DerivativeKeyProblem, DerivativeKeyScope


class VaultDerivativeKeyProvider:
    """Fresh random keys for each exact generation/lifecycle, never derived DB keys.

    Rotated project keys invalidate even live derivative leases. A missing or
    corrupt vault record is not replaced unless this exact new scope is being
    created. The caller must only request creation for a new canonical generation.
    """

    def __init__(self, store: CredentialStore, *, profile_id: str, database_keys: DatabaseKeyProvider) -> None:
        if not isinstance(store, CredentialStore) or not isinstance(database_keys, DatabaseKeyProvider):
            raise ValueError("derivative key authority is invalid")
        # Validate the profile with the same port used by the actual vault.
        SecretReference(profile_id, SecretKind.ENCRYPTION_KEY_MATERIAL, "derivative-index", "scope-v1")
        self._store = store
        self._profile_id = profile_id
        self._database_keys = database_keys

    @staticmethod
    def _context() -> SecretAccessContext:
        return SecretAccessContext(
            calling_capability="CAP-06.S01",
            purpose=SecretPurpose.DERIVATIVE_INDEX_ENCRYPTION,
            audit_context=secrets.token_hex(16),
        )

    def _reference(self, scope: DerivativeKeyScope) -> SecretReference:
        digest = hashlib.sha256(json.dumps(asdict(scope), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return SecretReference(
            self._profile_id, SecretKind.ENCRYPTION_KEY_MATERIAL, scope.project_id, "index-v1-" + digest
        )

    def _canonical_current(self, scope: DerivativeKeyScope) -> None:
        with self._database_keys.active_key(scope.project_id, create=False) as canonical:
            if canonical.version != scope.canonical_key_version:
                raise DerivativeKeyProblem("derivative key authority is stale")

    def _current(self, scope: DerivativeKeyScope, version: str) -> None:
        try:
            self._canonical_current(scope)
            record, secret = self._store.lease_record(self._reference(scope), self._context())
            with secret:
                if record.version != version or secret.use(len) != 32:
                    raise DerivativeKeyProblem("derivative key authority is stale")
        except DatabaseKeyProblem, CredentialStoreProblem:
            raise DerivativeKeyProblem("derivative key authority is unavailable") from None

    def lease(self, scope: DerivativeKeyScope, *, create: bool) -> DerivativeKeyLease:
        if not isinstance(scope, DerivativeKeyScope) or type(create) is not bool:
            raise DerivativeKeyProblem("derivative key request is invalid")
        try:
            self._canonical_current(scope)
            reference = self._reference(scope)
            try:
                record, secret = self._store.lease_record(reference, self._context())
            except SecretNotFound:
                if not create:
                    raise DerivativeKeyProblem("derivative key is unavailable") from None
                material = bytearray(secrets.token_bytes(32))
                try:
                    with suppress(SecretConflict):
                        self._store.put(reference, material, self._context())
                finally:
                    material[:] = b"\0" * len(material)
                record, secret = self._store.lease_record(reference, self._context())
            try:
                self._canonical_current(scope)
                if secret.use(len) != 32:
                    raise DerivativeKeyProblem("derivative key is unavailable")
                return DerivativeKeyLease(scope, record.version, secret, lambda: self._current(scope, record.version))
            except BaseException:
                secret.close()
                raise
        except DatabaseKeyProblem, CredentialStoreProblem:
            raise DerivativeKeyProblem("derivative key authority is unavailable") from None

    def revoke(self, scope: DerivativeKeyScope, *, expected_version: str) -> None:
        """Replace only the exact retired generation's vault material by CAS.

        Canonical manifests retain the old version, which can no longer be
        leased or decrypt its bytes. A retry never destroys a newer version.
        This also works after canonical-key rotation to retire its old scope.
        """
        if (
            not isinstance(scope, DerivativeKeyScope)
            or not isinstance(expected_version, str)
            or len(expected_version) != 32
            or any(c not in "0123456789abcdef" for c in expected_version)
        ):
            raise DerivativeKeyProblem("derivative retirement is invalid")
        material = bytearray(secrets.token_bytes(32))
        try:
            reference = self._reference(scope)
            try:
                record, old = self._store.lease_record(reference, self._context())
            except SecretNotFound:
                return
            old.close()
            if record.version == expected_version:
                with suppress(SecretConflict):
                    self._store.put(reference, material, self._context(), expected_version=expected_version)
        except CredentialStoreProblem:
            raise DerivativeKeyProblem("derivative retirement is unavailable") from None
        finally:
            material[:] = b"\0" * len(material)

    def lease_for_retirement(
        self, scope: DerivativeKeyScope, *, expected_version: str, authorize: Callable[[], None]
    ) -> DerivativeKeyLease:
        """No creation or current-search grant; only fenced retired recovery."""
        if (
            not isinstance(scope, DerivativeKeyScope)
            or not isinstance(expected_version, str)
            or len(expected_version) != 32
            or any(c not in "0123456789abcdef" for c in expected_version)
            or not callable(authorize)
        ):
            raise DerivativeKeyProblem("derivative retirement is invalid")

        def current() -> None:
            try:
                authorize()
                record, secret = self._store.lease_record(self._reference(scope), self._context())
                with secret:
                    if record.version != expected_version or secret.use(len) != 32:
                        raise DerivativeKeyProblem("retired derivative key is unavailable")
                authorize()
            except Exception:
                raise DerivativeKeyProblem("retired derivative authority is unavailable") from None

        current()
        try:
            record, secret = self._store.lease_record(self._reference(scope), self._context())
            try:
                if record.version != expected_version or secret.use(len) != 32:
                    raise DerivativeKeyProblem("retired derivative key is unavailable")
                current()
                return DerivativeKeyLease(scope, record.version, secret, current)
            except BaseException:
                secret.close()
                raise
        except CredentialStoreProblem:
            raise DerivativeKeyProblem("retired derivative key is unavailable") from None


__all__ = ["VaultDerivativeKeyProvider"]
