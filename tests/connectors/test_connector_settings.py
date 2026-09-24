"""Synthetic provider configuration in an isolated real Windows DPAPI vault."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.providers import ProviderProblem  # noqa: E402
from research_observatory_core.connectors.settings import ConnectorSettings  # noqa: E402
from research_observatory_core.ports.credential_store import (  # noqa: E402
    SecretAccessContext,
    SecretAuditEvent,
    SecretConflict,
    SecretKind,
    SecretPurpose,
    SecretReference,
)
from research_observatory_core.windows_credentials import WindowsCredentialStore  # noqa: E402

CONTACT = "synthetic@example.invalid"
KEY = "synthetic-graph-fixture-material"
CONTEXT = SecretAccessContext("CAP-04.S02", SecretPurpose.CONNECTOR_AUTHENTICATION, "a" * 32)


@unittest.skipUnless(os.name == "nt", "Windows DPAPI credential boundary")
class ConnectorSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ro-connector-private-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "vault"
        self.events: list[SecretAuditEvent] = []
        self.store = WindowsCredentialStore(self.root, audit_sink=self.events.append)
        self.settings = ConnectorSettings(self.store)

    def test_absent_required_contact_is_distinct_from_optional_keyless(self):
        self.assertEqual("not-configured", self.settings.status("unpaywall").configuration)
        for provider in ("openalex", "crossref", "semantic-scholar"):
            status = self.settings.status(provider)
            self.assertEqual("ready", status.configuration)
            self.assertFalse(status.key_configured)
            self.assertIsNone(status.version)
        with self.assertRaises(ProviderProblem) as error, self.settings.lease("unpaywall", CONTEXT):
            self.fail("Missing required contact cannot produce a connection")
        self.assertEqual("not-configured", error.exception.code)

    def test_complete_cas_rotation_clear_restart_and_no_secret_projection(self):
        first = self.settings.replace("unpaywall", key=None, contact=CONTACT, expected_version=None, context=CONTEXT)
        restarted = ConnectorSettings(WindowsCredentialStore(self.root, audit_sink=self.events.append))
        status = restarted.status("unpaywall")
        self.assertEqual(first.version, status.version)
        self.assertEqual("ready", status.configuration)
        with restarted.lease("unpaywall", CONTEXT) as connection:
            self.assertEqual(CONTACT, connection.contact)
            self.assertNotIn(CONTACT, repr(connection))
        self.assertIsNone(connection.contact)
        with self.assertRaises(SecretConflict):
            self.settings.replace("unpaywall", key=None, contact=None, expected_version=None, context=CONTEXT)
        cleared = self.settings.replace(
            "unpaywall",
            key=None,
            contact=None,
            expected_version=first.version,
            context=CONTEXT,
        )
        self.assertNotEqual(first.version, cleared.version)
        self.assertEqual("not-configured", cleared.configuration)
        graph = self.settings.replace("semantic-scholar", key=KEY, contact=None, expected_version=None, context=CONTEXT)
        self.assertTrue(graph.key_configured)
        self.assertNotIn(KEY, graph.model_dump_json())
        self.assertNotIn(CONTACT, status.model_dump_json())
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(CONTACT.encode(), path.read_bytes())
                self.assertNotIn(KEY.encode(), path.read_bytes())
        self.assertNotIn(CONTACT, repr(self.events))
        self.assertNotIn(KEY, repr(self.events))

    def test_corrupt_unavailable_or_lost_root_never_degrades_to_keyless(self):
        self.settings.replace("semantic-scholar", key=KEY, contact=None, expected_version=None, context=CONTEXT)
        sealed = next(self.root.rglob("*.sealed"))
        original = sealed.read_bytes()
        sealed.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        damaged = sealed.read_bytes()
        self.assertEqual("unavailable", self.settings.status("semantic-scholar").configuration)
        self.assertEqual(damaged, sealed.read_bytes())
        sealed.write_bytes(original)
        root = next(self.root.glob("*.dpapi"))
        root.unlink()
        self.assertEqual("unavailable", self.settings.status("semantic-scholar").configuration)
        self.assertFalse(root.exists())
        self.assertEqual(original, sealed.read_bytes())

    def test_malformed_or_wrong_provider_record_is_unavailable(self):
        ref = SecretReference("local-default", SecretKind.CONNECTOR_TOKEN, "unpaywall", "connection-v1")
        self.store.put(
            ref,
            json.dumps({"version": "1.0", "provider": "crossref", "key": None, "contact": CONTACT}).encode(),
            CONTEXT,
        )
        self.assertEqual("unavailable", self.settings.status("unpaywall").configuration)

    def test_preserve_existing_value_is_bound_to_exact_cas_predecessor(self):
        first = self.settings.replace("openalex", key=KEY, contact=CONTACT, expected_version=None, context=CONTEXT)
        second = self.settings.replace(
            "openalex",
            key=None,
            contact=None,
            preserve_key=True,
            expected_version=first.version,
            context=CONTEXT,
        )
        with self.settings.lease("openalex", CONTEXT) as value:
            self.assertEqual(KEY, value.key)
            self.assertIsNone(value.contact)
        self.assertNotEqual(first.version, second.version)
        with self.assertRaises(SecretConflict):
            self.settings.replace(
                "openalex",
                key=None,
                contact=CONTACT,
                preserve_key=True,
                expected_version=first.version,
                context=CONTEXT,
            )

    def test_invalid_values_and_unsupported_private_settings_are_rejected_before_write(self):
        for provider, key, contact in (
            ("unpaywall", KEY, CONTACT),
            ("crossref", KEY, None),
            ("semantic-scholar", None, CONTACT),
            ("unpaywall", None, "not-an-address"),
            ("semantic-scholar", "x\r\ny", None),
            ("unpaywall", None, " x@example.invalid"),
        ):
            with self.subTest(provider=provider), self.assertRaises(ProviderProblem):
                self.settings.replace(provider, key=key, contact=contact, expected_version=None, context=CONTEXT)
        self.assertEqual([], self.events)


if __name__ == "__main__":
    unittest.main()
