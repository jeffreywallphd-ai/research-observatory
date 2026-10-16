"""Purpose/lifecycle key contracts; deterministic memory doubles, not DPAPI proof."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.derivative_keys import VaultDerivativeKeyProvider  # noqa: E402
from research_observatory_core.ports.credential_store import (  # noqa: E402
    SecretConflict,
    SecretLease,
    SecretNotFound,
    SecretPurpose,
    SecretRecord,
)
from research_observatory_core.ports.derivative_keys import (  # noqa: E402
    DerivativeKeyProblem,
    DerivativeKeyScope,
    DerivativePurpose,
)

from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

PROJECT = "0199e895-0000-7000-8000-000000000001"
OTHER = "0199e895-0000-7000-8000-000000000002"
GENERATION = "0199e895-0000-7000-8000-000000000003"


class MemoryVault:
    def __init__(self):
        self.values = {}
        self.contexts = []
        self.counter = 0

    def put(self, reference, material, context, *, expected_version=None):
        self.contexts.append(context)
        old = self.values.get(reference)
        if (old is None and expected_version is not None) or (old and old[0].version != expected_version):
            raise SecretConflict("fixture conflict")
        self.counter += 1
        record = SecretRecord(f"{self.counter:032x}", reference.kind)
        self.values[reference] = (record, bytes(material))
        return record

    def lease_record(self, reference, context):
        self.contexts.append(context)
        if reference not in self.values:
            raise SecretNotFound("fixture absent")
        record, material = self.values[reference]
        return record, SecretLease(bytearray(material))

    def lease(self, reference, context):
        return self.lease_record(reference, context)[1]


class DerivativeKeyTests(unittest.TestCase):
    def setUp(self):
        self.canonical = InMemoryDatabaseKeyProvider()
        with self.canonical.active_key(PROJECT, create=True) as key:
            version = key.version
        self.vault = MemoryVault()
        self.provider = VaultDerivativeKeyProvider(self.vault, profile_id="fixture", database_keys=self.canonical)
        self.scope = DerivativeKeyScope(PROJECT, GENERATION, DerivativePurpose.LEXICAL, version, "a" * 64)

    def test_reopen_distinct_from_database_key_and_separate_purpose(self):
        with self.provider.lease(self.scope, create=True) as lease:
            first = lease.use(self.scope, bytes)
            version = lease.version
        with self.provider.lease(self.scope, create=False) as lease:
            self.assertEqual(first, lease.use(self.scope, bytes))
            self.assertEqual(version, lease.version)
        self.assertNotEqual(first, self.canonical.active_material_for_test(PROJECT))
        self.assertEqual({SecretPurpose.DERIVATIVE_INDEX_ENCRYPTION}, {c.purpose for c in self.vault.contexts})
        self.assertEqual({"CAP-06.S01"}, {c.calling_capability for c in self.vault.contexts})

    def test_exact_binding_is_immutable_and_cannot_be_substituted(self):
        with self.provider.lease(self.scope, create=True) as lease:
            for changed in (
                replace(self.scope, project_id=OTHER),
                replace(self.scope, generation_id=OTHER),
                replace(self.scope, lifecycle_sha256="b" * 64),
                replace(self.scope, canonical_key_version="b" * 32),
            ):
                with self.subTest(changed=changed), self.assertRaises(DerivativeKeyProblem):
                    lease.use(changed, bytes)
            with self.assertRaises(FrozenInstanceError):
                cast(Any, lease).scope = replace(self.scope, project_id=OTHER)
            self.assertNotIn(lease.use(self.scope, bytes).hex(), repr(lease))

    def test_missing_or_stale_scope_cannot_create_or_recover_key(self):
        for changed in (
            replace(self.scope, project_id=OTHER),
            replace(self.scope, canonical_key_version="b" * 32),
        ):
            for create in (False, True):
                with self.assertRaises(DerivativeKeyProblem):
                    self.provider.lease(changed, create=create)
        self.assertEqual({}, self.vault.values)
        with self.assertRaises(DerivativeKeyProblem):
            self.provider.lease(self.scope, create=False)

    def test_retirement_lease_requires_exact_old_version_and_live_retirement_authority(self):
        with self.provider.lease(self.scope, create=True) as original:
            version = original.version
            material = original.use(self.scope, bytes)
        with self.canonical.staged_rekey(PROJECT, "1" * 32, create=True):
            pass
        self.canonical.activate_rekey(PROJECT, "1" * 32, expected_active_version=self.scope.canonical_key_version)
        permitted = True

        def authorize():
            if not permitted:
                raise DerivativeKeyProblem("synthetic retired authority denied")

        before = dict(self.vault.values)
        with self.assertRaises(DerivativeKeyProblem):
            self.provider.lease(self.scope, create=False)
        with self.assertRaises(DerivativeKeyProblem):
            self.provider.lease_for_retirement(self.scope, expected_version="0" * 32, authorize=authorize)
        with self.provider.lease_for_retirement(self.scope, expected_version=version, authorize=authorize) as retired:
            self.assertEqual(material, retired.use(self.scope, bytes))
            permitted = False
            with self.assertRaises(DerivativeKeyProblem):
                retired.use(self.scope, bytes)
        with self.assertRaises(DerivativeKeyProblem):
            self.provider.lease_for_retirement(self.scope, expected_version=version, authorize=authorize)
        self.assertEqual(before, self.vault.values)

    def test_rotation_invalidates_old_scope_and_live_lease(self):
        lease = self.provider.lease(self.scope, create=True)
        with self.canonical.staged_rekey(PROJECT, "1" * 32, create=True):
            pass
        self.canonical.activate_rekey(PROJECT, "1" * 32, expected_active_version=self.scope.canonical_key_version)
        with self.assertRaises(DerivativeKeyProblem):
            lease.use(self.scope, bytes)
        with self.assertRaises(DerivativeKeyProblem):
            self.provider.lease(self.scope, create=False)
        lease.close()

    def test_generation_and_relocation_require_fresh_material(self):
        with self.provider.lease(self.scope, create=True) as lease:
            original = lease.use(self.scope, bytes)
        for changed in (replace(self.scope, generation_id=OTHER), replace(self.scope, lifecycle_sha256="b" * 64)):
            with self.assertRaises(DerivativeKeyProblem):
                self.provider.lease(changed, create=False)
            with self.provider.lease(changed, create=True) as lease:
                self.assertNotEqual(original, lease.use(changed, bytes))

    def test_invalid_scope_and_closed_lease_are_bounded(self):
        for changes in ({"purpose": "lexical-fts5-v1"}, {"project_id": "private-path"}, {"lifecycle_sha256": "x"}):
            with self.assertRaises(ValueError):
                replace(self.scope, **cast(Any, changes))
        lease = self.provider.lease(self.scope, create=True)
        lease.close()
        with self.assertRaises(DerivativeKeyProblem):
            lease.use(self.scope, bytes)

    def test_retirement_invalidates_live_and_persisted_generation_key_version(self):
        lease = self.provider.lease(self.scope, create=True)
        self.addCleanup(lease.close)
        material = lease.use(self.scope, bytes)
        version = lease.version
        self.provider.revoke(self.scope, expected_version=version)
        with self.assertRaises(DerivativeKeyProblem):
            lease.use(self.scope, bytes)
        with self.provider.lease(self.scope, create=False) as current:
            self.assertNotEqual(version, current.version)
            self.assertNotEqual(material, current.use(self.scope, bytes))
            replacement = current.version
        self.provider.revoke(self.scope, expected_version=version)
        with self.provider.lease(self.scope, create=False) as current:
            self.assertEqual(replacement, current.version)


if __name__ == "__main__":
    unittest.main()
