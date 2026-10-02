"""Exact encrypted-object pointer persists independently of a native token."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.plugin_package_repository import (  # noqa: E402
    PluginPackagePointer,
    PluginPackagePointerProblem,
    SqlitePluginPackageRepository,
)
from research_observatory_core.storage import configure_protected_database_provider, initialize_database  # noqa: E402

from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

PROJECT = "0190a000-0000-7000-8000-000000000040"


@unittest.skipUnless(os.name == "nt", "Windows protected project database")
class PluginPackageRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-plugin-package-pointer-")
        self.addCleanup(self.temporary.cleanup)
        database = Path(self.temporary.name).resolve() / "state/project.sqlite3"
        self.database = database
        database.parent.mkdir()
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        assert initialize_database(database, project_id=PROJECT, project_created_at="2026-10-01T12:00:00.000Z").ok
        self.repository = SqlitePluginPackageRepository(database, PROJECT)
        self.pointer = PluginPackagePointer(
            PROJECT,
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            "sha256:" + "3" * 64,
            "4" * 64,
        )

    def test_exact_signature_reopens_and_conflicting_archive_denies(self):
        self.assertIsNone(
            self.repository.read(
                self.pointer.package_sha256, self.pointer.manifest_sha256, self.pointer.signature_sha256
            )
        )
        self.assertEqual(
            self.pointer,
            self.repository.record(self.pointer, now="2026-10-01T12:00:00.000Z"),
        )
        reopened = SqlitePluginPackageRepository(self.database, PROJECT)
        self.assertEqual(
            self.pointer,
            reopened.read(self.pointer.package_sha256, self.pointer.manifest_sha256, self.pointer.signature_sha256),
        )
        self.assertEqual(
            self.pointer,
            reopened.record(self.pointer, now="2026-10-01T12:01:00.000Z"),
        )
        with self.assertRaisesRegex(PluginPackagePointerProblem, "plugin-package-identity-conflict"):
            reopened.record(
                PluginPackagePointer(
                    PROJECT,
                    self.pointer.package_sha256,
                    self.pointer.manifest_sha256,
                    self.pointer.signature_sha256,
                    "5" * 64,
                ),
                now="2026-10-01T12:02:00.000Z",
            )
        rotated = PluginPackagePointer(
            PROJECT,
            self.pointer.package_sha256,
            self.pointer.manifest_sha256,
            "sha256:" + "6" * 64,
            "7" * 64,
        )
        self.assertEqual(rotated, reopened.record(rotated, now="2026-10-01T12:03:00.000Z"))
        self.assertEqual(
            self.pointer,
            reopened.read(self.pointer.package_sha256, self.pointer.manifest_sha256, self.pointer.signature_sha256),
        )
        self.assertEqual(
            rotated, reopened.read(rotated.package_sha256, rotated.manifest_sha256, rotated.signature_sha256)
        )


if __name__ == "__main__":
    unittest.main()
