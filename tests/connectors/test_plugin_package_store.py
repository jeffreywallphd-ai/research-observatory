"""Selected plugin ZIPs remain encrypted and reopen by exact content identity."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_package_intake import inspect_plugin_archive  # noqa: E402
from research_observatory_core.connectors.plugin_package_store import (  # noqa: E402
    PluginPackageStore,
    PluginPackageStoreProblem,
)
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store_keys import ObjectMasterKey  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture, initialize_database  # noqa: E402

from tests.connectors.test_plugin_manifest_contract import (  # noqa: E402
    PACKAGE_FILE,
    PATH,
    _manifest_bytes,
    _manifest_document,
)
from tests.connectors.test_plugin_package_intake import archive  # noqa: E402

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-7f3f36b60210"
CREATED_AT = "2026-08-18T12:00:00.000Z"


class MemoryKeyProvider:
    def active_object_master_key(self) -> ObjectMasterKey:
        return ObjectMasterKey("plugin-object-key-v1", bytes.fromhex("11" * 32))

    def object_master_key(self, key_version: str) -> ObjectMasterKey | None:
        return self.active_object_master_key() if key_version == "plugin-object-key-v1" else None


class PluginPackageStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.addCleanup(lambda: self.database_profile.__exit__(None, None, None))
        self.scratch = tempfile.TemporaryDirectory(prefix="ro-plugin-store-")
        self.addCleanup(self.scratch.cleanup)
        self.project = Path(self.scratch.name).resolve() / "project"
        for directory in ("state", "objects", ".tmp"):
            (self.project / directory).mkdir(parents=True)
        initialize_database(
            self.project / "state" / "project.sqlite3", project_id=PROJECT_ID, project_created_at=CREATED_AT
        )
        self.keys = MemoryKeyProvider()
        self.store = PluginPackageStore(create_local_object_store(self.project, PROJECT_ID, key_provider=self.keys))
        self.raw, _ = archive()
        self.inspected = inspect_plugin_archive(self.raw)

    def _save(self, raw: bytes | None = None) -> str:
        return self.store.save(
            self.raw if raw is None else raw, self.inspected.package_sha256, self.inspected.manifest_sha256
        )

    def test_exact_archive_encrypted_and_reopened_after_store_restart(self) -> None:
        archive_sha = self._save()
        self.assertEqual(archive_sha, hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(archive_sha, self._save())
        physical = tuple(path for path in (self.project / "objects").rglob("*") if path.is_file())
        self.assertEqual(len(physical), 1)
        self.assertNotEqual(physical[0].read_bytes(), self.raw)
        self.assertNotIn(self.inspected.manifest_bytes, physical[0].read_bytes())
        reopened = PluginPackageStore(create_local_object_store(self.project, PROJECT_ID, key_provider=self.keys))
        package = reopened.load(archive_sha, self.inspected.package_sha256, self.inspected.manifest_sha256)
        self.assertEqual(package.manifest_bytes, self.inspected.manifest_bytes)
        self.assertEqual(package.signature, self.inspected.signature)
        self.assertEqual(package.files, self.inspected.files)

    def test_manifest_change_cannot_alias_the_same_package_file_digest(self) -> None:
        archive_sha = self._save()
        changed = _manifest_document()
        changed["pluginVersion"] = "1.0.1"
        other_raw, _ = archive(
            files={"manifest.json": _manifest_bytes(changed), "manifest.sig": b"x" * 64, PATH: PACKAGE_FILE}
        )
        other = inspect_plugin_archive(other_raw)
        self.assertEqual(other.package_sha256, self.inspected.package_sha256)
        self.assertNotEqual(other.manifest_sha256, self.inspected.manifest_sha256)
        with self.assertRaisesRegex(PluginPackageStoreProblem, "digest-mismatch"):
            self.store.load(archive_sha, other.package_sha256, other.manifest_sha256)
        self.assertEqual(
            self.store.load(archive_sha, self.inspected.package_sha256, self.inspected.manifest_sha256).signature,
            self.inspected.signature,
        )

    def test_signature_change_has_distinct_archive_identity(self) -> None:
        archive_sha = self._save()
        altered_raw, _ = archive(
            files={"manifest.json": self.inspected.manifest_bytes, "manifest.sig": b"x" * 64, PATH: PACKAGE_FILE}
        )
        altered_sha = self._save(altered_raw)
        self.assertNotEqual(altered_sha, archive_sha)
        self.assertNotEqual(
            self.store.load(altered_sha, self.inspected.package_sha256, self.inspected.manifest_sha256).signature,
            self.inspected.signature,
        )
        physical = tuple(path for path in (self.project / "objects").rglob("*") if path.is_file())
        self.assertEqual(len(physical), 2)

    def test_physical_tamper_fails_closed(self) -> None:
        archive_sha = self._save()
        physical = tuple(path for path in (self.project / "objects").rglob("*") if path.is_file())
        self.assertEqual(len(physical), 1)
        physical[0].write_bytes(b"invalid encrypted envelope")
        with self.assertRaises(PluginPackageStoreProblem):
            self.store.load(archive_sha, self.inspected.package_sha256, self.inspected.manifest_sha256)

    def test_invalid_expected_digest_and_wrong_object_identity_deny(self) -> None:
        with self.assertRaises(PluginPackageStoreProblem):
            self.store.save(self.raw, "../outside", self.inspected.manifest_sha256)
        archive_sha = self._save()
        with self.assertRaises(PluginPackageStoreProblem):
            self.store.load("../outside", self.inspected.package_sha256, self.inspected.manifest_sha256)
        with self.assertRaises(PluginPackageStoreProblem):
            self.store.load("0" * 64, self.inspected.package_sha256, self.inspected.manifest_sha256)
        self.assertEqual(
            self.store.load(archive_sha, self.inspected.package_sha256, self.inspected.manifest_sha256).package_sha256,
            self.inspected.package_sha256,
        )


if __name__ == "__main__":
    unittest.main()
