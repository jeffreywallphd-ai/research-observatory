from __future__ import annotations

import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.model_registry_contracts import ModelManifest, canonical_hash  # noqa: E402
from research_observatory_core.model_registry_repository import SqliteModelCatalogRepository  # noqa: E402
from research_observatory_core.ports.repositories import (  # noqa: E402
    RepositoryConflict,
    RepositoryIdempotencyConflict,
    RepositoryTransactionFailed,
)
from research_observatory_core.storage import (  # noqa: E402
    configure_protected_database_provider,
    initialize_database,
    open_canonical_database,
)

from tests.ai.test_model_registry import (  # noqa: E402
    FixtureInventory,
    FixturePolicy,
    ModelRegistry,
    manifest_document,
    task,
)
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

PROJECT = "123e4567-e89b-42d3-a456-426614174000"
STAMP = "2026-09-06T12:00:00.000Z"
TRACE = "a" * 32


class ModelRegistryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-registry-fixture-")
        self.root = Path(self.temporary.name).resolve()
        (self.root / "state").mkdir()
        (self.root / ".tmp").mkdir()
        self.database = self.root / "state/project.sqlite3"
        self.keys = InMemoryDatabaseKeyProvider()
        configure_protected_database_provider(self.keys)
        report = initialize_database(self.database, project_id=PROJECT, project_created_at=STAMP)
        self.assertTrue(report.ok, report.errors)
        self.repo = SqliteModelCatalogRepository(self.database, PROJECT)
        self.actor = new_uuid_v7()
        self.manifest = ModelManifest.model_validate(manifest_document())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def append(
        self, *, expected: int = 0, key: str = "fixture-command-1", manifests: tuple[ModelManifest, ...] | None = None
    ):
        return self.repo.append(
            expected_revision=expected,
            manifests=(self.manifest,) if manifests is None else manifests,
            actor_id=self.actor,
            idempotency_key=key,
            trace_id=TRACE,
            occurred_at=STAMP,
        )

    def counts(self) -> tuple[int, int, int]:
        connection = open_canonical_database(self.database, expected_project_id=PROJECT)
        try:
            return tuple(
                connection.execute(query).fetchone()[0]
                for query in (
                    "SELECT COUNT(*) FROM settings WHERE setting_key='models.catalog'",
                    "SELECT COUNT(*) FROM provenance_events WHERE event_type='models.catalog.refreshed'",
                    "SELECT COUNT(*) FROM outbox_events WHERE event_type='models.catalog.refreshed'",
                )
            )
        finally:
            connection.close()

    def test_protected_restart_history_audit_and_idempotent_replay(self) -> None:
        self.assertIsNone(self.repo.read())
        self.assertEqual((0, 0, 0), self.counts())
        first = self.append()
        self.assertEqual(first, self.append())
        self.assertEqual((1, 1, 1), self.counts())
        second = self.append(expected=1, key="fixture-command-2", manifests=())
        reconstructed = SqliteModelCatalogRepository(self.database, PROJECT)
        self.assertEqual(second, reconstructed.read())
        self.assertEqual(first, reconstructed.read(revision=1))
        self.assertEqual((2, 1), tuple(item.revision for item in reconstructed.history()))
        self.assertEqual((1,), tuple(item.revision for item in reconstructed.history(before_revision=2)))
        self.assertEqual(first.record_hash, second.previous_hash)
        self.assertEqual((2, 2, 2), self.counts())
        self.assertNotEqual(self.database.read_bytes()[:16], b"SQLite format 3\x00")
        connection = open_canonical_database(self.database, expected_project_id=PROJECT)
        try:
            rows = connection.execute(
                "SELECT actor_type, actor_id FROM provenance_events WHERE event_type='models.catalog.refreshed'"
            ).fetchall()
            self.assertEqual([("human", self.actor), ("human", self.actor)], [tuple(row) for row in rows])
        finally:
            connection.close()

    def test_restart_does_not_persist_host_readiness(self) -> None:
        stored = self.append()
        reloaded = SqliteModelCatalogRepository(self.database, PROJECT).read()
        assert reloaded is not None
        catalog = reloaded.catalog
        self.assertEqual(stored.catalog, catalog)
        fresh_inventory = FixtureInventory(catalog.manifests)
        fresh_inventory.observations = ()
        registry = ModelRegistry(fresh_inventory, FixturePolicy(), clock_ms=lambda: 1500)
        result = registry.resolve(catalog, task())
        self.assertFalse(result.eligible)
        self.assertIn("availability-unknown", result.rejected[0].reason_codes)
        fresh_inventory.observations = FixtureInventory(catalog.manifests).observations
        self.assertEqual(1, len(registry.resolve(catalog, task()).eligible))

    def test_conflicts_changed_retries_and_regressing_manifest_preserve_history(self) -> None:
        first = self.append()
        with self.assertRaises(RepositoryIdempotencyConflict):
            self.append(manifests=())
        with self.assertRaises(RepositoryConflict):
            self.append(key="different-key")
        changed = manifest_document() | {"contextTokens": 16384}
        with self.assertRaises(RepositoryConflict):
            self.append(expected=1, key="different-key", manifests=(ModelManifest.model_validate(changed),))
        self.append(expected=1, key="removed", manifests=())
        with self.assertRaises(RepositoryConflict):
            self.append(expected=2, key="reintroduced", manifests=(ModelManifest.model_validate(changed),))
        self.assertEqual(first, self.repo.read(revision=1))
        self.assertEqual((2, 2, 2), self.counts())

    def test_injected_atomic_failure_preserves_all_three_durable_facts(self) -> None:
        with (
            patch.object(self.repo, "_append_events", side_effect=OSError("fixture interruption")),
            self.assertRaises(RepositoryTransactionFailed),
        ):
            self.append()
        self.assertEqual((0, 0, 0), self.counts())
        self.assertIsNone(self.repo.read())
        self.append()
        self.assertEqual((1, 1, 1), self.counts())

    def test_concurrent_expected_revision_has_one_winner(self) -> None:
        def attempt(key: str) -> str:
            try:
                self.append(key=key)
                return "committed"
            except RepositoryConflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = sorted(pool.map(attempt, ("writer-a", "writer-b")))
        self.assertEqual(["committed", "conflict"], results)
        self.assertEqual((1, 1, 1), self.counts())

    def test_wrong_project_and_missing_actor_do_not_mutate(self) -> None:
        with self.assertRaises(RepositoryTransactionFailed):
            SqliteModelCatalogRepository(self.database, new_uuid_v7()).read()
        with self.assertRaises((ValueError, RepositoryTransactionFailed)):
            self.repo.append(
                expected_revision=0,
                manifests=(self.manifest,),
                actor_id="spoofed-user",
                idempotency_key="bad-actor",
                trace_id=TRACE,
                occurred_at=STAMP,
            )
        self.assertEqual((0, 0, 0), self.counts())

    def test_corrupt_latest_record_never_falls_back_to_prior_revision(self) -> None:
        first = self.append()
        connection = open_canonical_database(self.database, expected_project_id=PROJECT)
        try:
            connection.execute(
                "INSERT INTO settings (setting_id, project_id, setting_key, revision, value_type, "
                "text_value, created_at, modified_at) VALUES (?, ?, 'models.catalog', 2, 'text', '{}', ?, ?)",
                (new_uuid_v7(), PROJECT, STAMP, STAMP),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(RepositoryTransactionFailed):
            self.repo.read()
        with self.assertRaises(RepositoryTransactionFailed):
            self.append(expected=2, key="after-corruption")
        self.assertEqual(first, self.repo.read(revision=1))

    def test_one_thousand_manifests_fit_typed_storage_without_a_large_setting_blob(self) -> None:
        manifests = tuple(
            ModelManifest.model_validate(manifest_document() | {"manifestId": f"fixture-{i:04}"}) for i in range(1000)
        )
        stored = self.append(manifests=manifests)
        reloaded = self.repo.read()
        assert reloaded is not None
        self.assertEqual(1000, len(reloaded.catalog.manifests))
        self.assertEqual(canonical_hash(stored.catalog), stored.catalog_hash)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT)
        try:
            maximum = connection.execute("SELECT MAX(length(text_value)) FROM settings").fetchone()[0]
            self.assertLessEqual(maximum, 65536)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
