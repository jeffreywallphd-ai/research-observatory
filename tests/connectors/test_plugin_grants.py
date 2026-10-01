"""Core-owned signed-plugin grant history and denial audit on protected SQLite."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from nacl.signing import SigningKey  # noqa: E402
from research_observatory_core.connectors.plugin_grants import (  # noqa: E402
    PluginEnableConfirmation,
    PluginGrantActor,
    PluginGrantProblem,
)
from research_observatory_core.connectors.plugin_manifest import (  # noqa: E402
    VerifiedPluginPackage,
    verify_plugin_package,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.plugin_grant_repository import SqlitePluginGrantRepository  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    _DATABASE_ERRORS,
    configure_protected_database_provider,
    initialize_database,
    open_canonical_database,
)

from tests.connectors.test_plugin_manifest_contract import (  # noqa: E402
    PACKAGE_FILE,
    PATH,
    PROJECT_ID,
    PUBLISHER_ID,
    _manifest_bytes,
    _manifest_document,
)
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

NOW = "2026-10-01T12:00:00.000Z"


class PluginGrantRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-plugin-grant-synthetic-")
        self.addCleanup(self._cleanup)
        root = Path(self.temporary.name).resolve()
        (root / "state").mkdir()
        self.database = root / "state/project.sqlite3"
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        initialized = initialize_database(self.database, project_id=PROJECT_ID, project_created_at=NOW)
        self.assertTrue(initialized.ok, initialized.errors)
        self.repo = SqlitePluginGrantRepository(self.database, PROJECT_ID)
        self.key = SigningKey(b"\x05" * 32)
        self.package = self._package()
        self.actor = PluginGrantActor(actor_id=new_uuid_v7(), trace_id="a" * 32, occurred_at=NOW)

    def _cleanup(self) -> None:
        if os.name == "nt":
            subprocess.run(
                [
                    str(Path(os.environ["SYSTEMROOT"]) / "System32/icacls.exe"),
                    self.temporary.name,
                    "/reset",
                    "/t",
                    "/c",
                    "/q",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        self.temporary.cleanup()

    def _package(self, document: dict | None = None, *, package_file: bytes = PACKAGE_FILE):
        raw = _manifest_bytes(document or _manifest_document(package_file=package_file))
        return verify_plugin_package(
            raw,
            self.key.sign(raw).signature,
            {PATH: package_file},
            {PUBLISHER_ID: bytes(self.key.verify_key)},
        )

    def _confirmation(self, package=None, **changes):
        package = package or self.package
        manifest = package.manifest
        values = dict(
            action_id=new_uuid_v7(),
            project_id=PROJECT_ID,
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            publisher_key_id=manifest.publisher_key_id,
            trusted_key_sha256="sha256:" + hashlib.sha256(bytes(self.key.verify_key)).hexdigest(),
            trusted_key_revision=1,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            permissions=manifest.permissions,
            destinations=manifest.destinations,
            operations=manifest.operations,
            data_classes=manifest.data_classes,
            credential_scopes=manifest.credential_scopes,
            expected_revision=None,
        )
        values.update(changes)
        return PluginEnableConfirmation(**values)

    def _enable(self, package, confirmation, *, actor):
        return self.repo.enable(
            package, confirmation, actor=actor,
            trusted_key_sha256=confirmation.trusted_key_sha256,
            trusted_key_revision=confirmation.trusted_key_revision,
        )

    def test_explicit_exact_enable_restarts_and_revoke_preserves_history(self) -> None:
        confirmation = self._confirmation()
        grant = self._enable(self.package, confirmation, actor=self.actor)
        self.assertEqual(1, grant.revision)
        self.assertEqual(grant, SqlitePluginGrantRepository(self.database, PROJECT_ID).current_grant(grant.plugin_id))
        self.assertEqual(grant, self._enable(self.package, confirmation, actor=self.actor))
        revoke_action = new_uuid_v7()
        self.repo.revoke(grant.plugin_id, expected_revision=1, action_id=revoke_action, actor=self.actor)
        self.repo.revoke(grant.plugin_id, expected_revision=1, action_id=revoke_action, actor=self.actor)
        self.assertIsNone(SqlitePluginGrantRepository(self.database, PROJECT_ID).current_grant(grant.plugin_id))
        history = self.repo.audit_history(grant.plugin_id)
        self.assertEqual(["enabled", "revoked"], [entry.event_kind for entry in history])
        self.assertTrue(all(entry.provenance_event_id for entry in history))

    def test_revoked_action_replay_cannot_resurrect_historical_grant(self) -> None:
        confirmation = self._confirmation()
        grant = self._enable(self.package, confirmation, actor=self.actor)
        self.repo.revoke(grant.plugin_id, expected_revision=1, action_id=new_uuid_v7(), actor=self.actor)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-action-stale"):
            self._enable(self.package, confirmation, actor=self.actor)
        self.assertIsNone(self.repo.current_grant(grant.plugin_id))
        self.assertEqual(
            ["enabled", "revoked", "denied"],
            [event.event_kind for event in self.repo.audit_history(grant.plugin_id)],
        )

    def test_changed_package_and_permissions_require_fresh_exact_action(self) -> None:
        original = self._enable(self.package, self._confirmation(), actor=self.actor)
        changed = self._package(package_file=b"# changed synthetic package bytes\n")
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-confirmation-mismatch"):
            self._enable(changed, self._confirmation(self.package, expected_revision=1), actor=self.actor)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-confirmation-mismatch"):
            self._enable(
                self.package,
                self._confirmation(expected_revision=1, permissions=()),
                actor=self.actor,
            )
        for changes in (
            {"operations": ("lookup",)},
            {"data_classes": ()},
            {"credential_scopes": ("unreviewed-scope",)},
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                PluginGrantProblem, "plugin-grant-confirmation-mismatch"
            ):
                self._enable(self.package, self._confirmation(expected_revision=1, **changes), actor=self.actor)
        self.assertEqual(original, self.repo.current_grant(original.plugin_id))
        authority = self.repo.current_grant_authority(original.plugin_id)
        assert authority is not None
        self.assertEqual(self.package.manifest.operations, authority.operations)
        self.assertEqual(self.package.manifest.data_classes, authority.data_classes)
        self.assertEqual(self.package.manifest.credential_scopes, authority.credential_scopes)
        denials = [event for event in self.repo.audit_history(original.plugin_id) if event.event_kind == "denied"]
        self.assertEqual(5, len(denials))
        self.assertEqual(
            2, self._enable(changed, self._confirmation(changed, expected_revision=1), actor=self.actor).revision
        )

    def test_changed_package_replay_cannot_return_old_grant_as_new_authority(self) -> None:
        confirmation = self._confirmation()
        original = self._enable(self.package, confirmation, actor=self.actor)
        changed = self._package(package_file=b"# different signed package\n")
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-confirmation-mismatch"):
            self._enable(changed, confirmation, actor=self.actor)
        self.assertEqual(original, self.repo.current_grant(original.plugin_id))
        self.assertEqual(
            ["enabled", "denied"],
            [event.event_kind for event in self.repo.audit_history(original.plugin_id)],
        )

    def test_project_publisher_collision_and_stale_revision_deny_without_new_grant(self) -> None:
        original = self._enable(self.package, self._confirmation(), actor=self.actor)
        other_key = SigningKey(b"\x06" * 32)
        document = _manifest_document()
        document["publisherKeyId"] = "other-publisher"
        raw = _manifest_bytes(document)
        other = verify_plugin_package(
            raw,
            other_key.sign(raw).signature,
            {PATH: PACKAGE_FILE},
            {"other-publisher": bytes(other_key.verify_key)},
        )
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-publisher-collision"):
            self._enable(other, self._confirmation(other, expected_revision=1), actor=self.actor)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-stale-revision"):
            self._enable(self.package, self._confirmation(expected_revision=None), actor=self.actor)
        self.assertEqual(original, self.repo.current_grant(original.plugin_id))
        self.assertEqual(3, len(self.repo.audit_history(original.plugin_id)))

    def test_forged_package_and_system_runtime_denial_do_not_mint_consent(self) -> None:
        forged = VerifiedPluginPackage(
            manifest=self.package.manifest,
            manifest_sha256=self.package.manifest_sha256,
            package_sha256=self.package.package_sha256,
            signature_sha256=self.package.signature_sha256,
            _seal=object(),
        )
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-package-unverified"):
            self._enable(forged, self._confirmation(), actor=self.actor)
        self.assertIsNone(self.repo.current_grant(self.package.manifest.plugin_id))
        system = PluginGrantActor(actor_id=new_uuid_v7(), trace_id="b" * 32, occurred_at=NOW, actor_type="system")
        self.repo.record_denial(
            plugin_id=self.package.manifest.plugin_id,
            reason_code="plugin-broker-destination-denied",
            actor=system,
            invocation_id=new_uuid_v7(),
            package_sha256=self.package.package_sha256,
        )
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-actor-invalid"):
            self._enable(self.package, self._confirmation(), actor=system)
        self.assertEqual(
            ["denied"], [event.event_kind for event in self.repo.audit_history(self.package.manifest.plugin_id)]
        )

    def test_denial_audit_is_content_free_append_only_and_cross_project_scope_denies(self) -> None:
        self.repo.record_denial(
            plugin_id="fixture.repository",
            reason_code="plugin-broker-destination-denied",
            actor=self.actor,
            invocation_id=new_uuid_v7(),
            package_sha256=self.package.package_sha256,
        )
        audit = self.repo.audit_history("fixture.repository")
        self.assertEqual("plugin-broker-destination-denied", audit[0].reason_code)
        with open_canonical_database(self.database, expected_project_id=PROJECT_ID) as db:
            with self.assertRaises(_DATABASE_ERRORS):
                db.execute("UPDATE plugin_grant_events SET reason_code='changed'")
            with self.assertRaises(_DATABASE_ERRORS):
                db.execute("DELETE FROM plugin_grant_events")
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-project-mismatch"):
            self._enable(
                self.package,
                self._confirmation(project_id="0190a000-0000-7000-8000-000000000041"),
                actor=self.actor,
            )


if __name__ == "__main__":
    unittest.main()
