"""Connector tokens remain vault-scoped to publisher, plugin, scope and origin."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_credentials import (  # noqa: E402
    PluginCredentialProblem,
    PluginCredentialSettings,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.ports.credential_store import (  # noqa: E402
    SecretLease,
    SecretNotFound,
    SecretRecord,
)

from tests.connectors.test_plugin_job_repository import PluginJobFixture  # noqa: E402


class MemoryVault:
    def __init__(self):
        self.values = {}

    def put(self, reference, material, context, *, expected_version=None):
        old = self.values.get(reference)
        if (None if old is None else old[0]) != expected_version:
            raise ValueError("version conflict")
        version = "a" * 32 if old is None else "b" * 32
        self.values[reference] = (version, bytes(material))
        return SecretRecord(version, reference.kind)

    def lease_record(self, reference, context):
        if reference not in self.values:
            raise SecretNotFound()
        version, material = self.values[reference]
        return SecretRecord(version, reference.kind), SecretLease(bytearray(material))

    def lease(self, reference, context):
        return self.lease_record(reference, context)[1]


class PluginCredentialTests(PluginJobFixture):
    def setUp(self):
        super().setUp()
        self.plan = self.plan.model_copy(update={"permissions": ("provider-network", "credential-broker")})
        self.vault = MemoryVault()
        self.settings = PluginCredentialSettings(self.vault)

    def test_positive_scoped_lease_and_changed_origin_denial(self):
        scope = "repository-token"
        self.assertFalse(self.settings.status(scope, self.plan).configured)
        configured = self.settings.configure(self.plan, scope, "secret-token", expected_version=None)
        self.assertEqual("a" * 32, configured.version)
        self.assertEqual(
            (self.plan.destination.scheme, self.plan.destination.host, self.plan.destination.port),
            self.settings.origin(scope, self.plan),
        )
        with self.settings.lease(scope, self.plan) as secret:
            self.assertEqual("secret-token", secret)
        with self.assertRaises(PluginCredentialProblem), self.settings.lease("other-scope", self.plan):
            self.fail("other scope cannot receive this token")
        changed_destination = self.plan.destination.model_copy(update={"host": "other.example.org"})
        changed = self.plan.model_copy(update={"destination": changed_destination})
        with self.assertRaisesRegex(PluginCredentialProblem, "stale"):
            self.settings.status(scope, changed)
        other_project = self.plan.model_copy(update={"project_id": new_uuid_v7()})
        self.assertFalse(self.settings.status(scope, other_project).configured)
        self.assertNotIn(b"secret-token", repr(configured).encode())

    def test_permission_and_invalid_scope_deny_before_vault_lookup(self):
        without_permission = self.plan.model_copy(update={"permissions": ("provider-network",)})
        with self.assertRaisesRegex(PluginCredentialProblem, "permission-denied"):
            self.settings.status("repository-token", without_permission)
        with self.assertRaisesRegex(PluginCredentialProblem, "scope-invalid"):
            self.settings.configure(self.plan, "../outside", "secret-token", expected_version=None)
        self.assertEqual({}, self.vault.values)


if __name__ == "__main__":
    unittest.main()
