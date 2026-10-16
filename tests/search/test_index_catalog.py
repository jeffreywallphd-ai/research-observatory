"""Actual protected canonical catalog; synthetic Native/source/key fixture."""

import hashlib
import sys
import unittest
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core import storage  # noqa: E402
from research_observatory_core.derivative_keys import VaultDerivativeKeyProvider  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.lexical_catalog_repository import (  # noqa: E402
    IndexCatalogProblem,
    IndexValidation,
    SqliteIndexCatalog,
    actor_context_sha256,
)
from research_observatory_core.lexical_index_store import ProtectedLexicalStore  # noqa: E402
from research_observatory_core.ports.derivative_keys import DerivativeKeyScope, DerivativePurpose  # noqa: E402

from tests.documents import test_document_revision_repository as document_fixtures  # noqa: E402
from tests.search.test_derivative_keys import MemoryVault  # noqa: E402


class IndexCatalogTests(unittest.TestCase):
    def setUp(self):
        self.fixture = document_fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.database.parent.parent
        self.project = self.fixture.f.source.project_id
        canonical = storage._database_protection_configuration().provider
        assert canonical is not None
        self.keys = VaultDerivativeKeyProvider(MemoryVault(), profile_id="fixture", database_keys=canonical)
        with canonical.active_key(self.project, create=False) as key:
            version = key.version
        self.scope = DerivativeKeyScope(self.project, new_uuid_v7(), DerivativePurpose.LEXICAL, version, "a" * 64)
        self.now = datetime.now(UTC)
        self.catalog = SqliteIndexCatalog(
            self.fixture.database,
            self.project,
            self.keys,
            actor=lambda: self.fixture.actor,
            guard=self.fixture.guard,
            now=lambda: self.now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        )

    @contextmanager
    def initialized_store(self, lease):
        with ProtectedLexicalStore(
            self.root,
            self.scope,
            self.keys,
            create=True,
            _bootstrap=lambda identities: self.catalog.bind_bootstrap(lease, identities),
        ) as store:
            self.catalog.acknowledge_initialization(lease, store.file_identities)
            yield store

    def test_source_progress_requires_durable_initialized_witness(self):
        lease = self.catalog.create(self.scope)
        self.addCleanup(lease.close)
        with self.assertRaises(IndexCatalogProblem):
            self.catalog.record_progress(lease, cursor_item_id=new_uuid_v7())
        self.assertIsNone(self.catalog.get(lease.generation_id).cursor_item_id)
        self.assertFalse(self.catalog.initialized(lease.generation_id))

    def test_shadow_creation_and_cancel_reacquire_fences_old_owner(self):
        first = self.catalog.create(self.scope)
        self.addCleanup(first.close)
        snapshot = self.catalog.get(self.scope.generation_id)
        self.assertEqual("Building", snapshot.stage)
        self.assertIsNone(self.catalog.selected())
        self.catalog.cancel(first)
        self.assertEqual("Incomplete", self.catalog.get(self.scope.generation_id).stage)
        with self.assertRaises(IndexCatalogProblem):
            self.catalog.assert_owner(first)
        with self.assertRaises(IndexCatalogProblem):
            self.catalog.renew(first)
        second = self.catalog.acquire(self.scope.generation_id)
        self.addCleanup(second.close)
        self.assertEqual(2, second.epoch)
        self.assertNotEqual(first.owner_sha256, second.owner_sha256)
        with self.assertRaises(IndexCatalogProblem):
            self.catalog.record_progress(first, cursor_item_id=new_uuid_v7())

    def test_expired_lease_cannot_renew_and_same_actor_gets_new_fence(self):
        first = self.catalog.create(self.scope)
        self.addCleanup(first.close)
        self.now += timedelta(seconds=31)
        with self.assertRaises(IndexCatalogProblem):
            self.catalog.renew(first)
        second = self.catalog.acquire(self.scope.generation_id)
        self.addCleanup(second.close)
        self.assertEqual(2, second.epoch)
        self.assertNotEqual(first.owner_sha256, second.owner_sha256)

    def test_ready_selection_binds_actual_projection_and_expected_pointer(self):
        lease = self.catalog.create(self.scope)
        self.addCleanup(lease.close)
        checkpoint = self.catalog.watermark()
        with self.initialized_store(lease) as store:
            store.apply((), (), expected_checkpoint=0, checkpoint=checkpoint)
            projection = store.projection()
            validation = IndexValidation(
                checkpoint,
                hashlib.sha256(b"synthetic empty-source validation").hexdigest(),
                actor_context_sha256(self.project, self.fixture.actor),
                None,
            )
            self.catalog.publish_ready(
                lease, projection, validation, expected_selection_id=None, revalidate=lambda _db: None
            )
        selected = self.catalog.selected()
        assert selected is not None
        self.assertEqual(self.scope.generation_id, selected.generation_id)
        self.assertEqual("Ready", selected.stage)
        self.assertEqual(projection.manifest_sha256, selected.projection_sha256)
        with self.assertRaises(IndexCatalogProblem):
            self.catalog.publish_ready(
                lease, projection, validation, expected_selection_id=None, revalidate=lambda _db: None
            )

    def test_projection_of_another_generation_cannot_promote_this_generation(self):
        first = self.catalog.create(self.scope)
        self.addCleanup(first.close)
        other_scope = replace(self.scope, generation_id=new_uuid_v7())
        other = self.catalog.create(other_scope)
        self.addCleanup(other.close)
        checkpoint = self.catalog.watermark()
        with self.initialized_store(first) as store:
            store.finish_build(checkpoint)
            projection = store.projection()
        validation = IndexValidation(checkpoint, "c" * 64, actor_context_sha256(self.project, self.fixture.actor), None)
        with self.assertRaises(IndexCatalogProblem):
            self.catalog.publish_ready(
                other, projection, validation, expected_selection_id=None, revalidate=lambda _db: None
            )
        self.assertIsNone(self.catalog.selected())
        self.assertEqual("Building", self.catalog.get(other_scope.generation_id).stage)

    def test_promotion_rechecks_clock_after_current_source_validation(self):
        lease = self.catalog.create(self.scope)
        self.addCleanup(lease.close)
        checkpoint = self.catalog.watermark()
        with self.initialized_store(lease) as store:
            store.finish_build(checkpoint)
            projection = store.projection()
        validation = IndexValidation(checkpoint, "c" * 64, actor_context_sha256(self.project, self.fixture.actor), None)

        def expire(_db):
            self.now += timedelta(seconds=31)

        with self.assertRaises(IndexCatalogProblem):
            self.catalog.publish_ready(lease, projection, validation, expected_selection_id=None, revalidate=expire)
        self.assertIsNone(self.catalog.selected())
        self.assertEqual("Building", self.catalog.get(self.scope.generation_id).stage)

    def test_validation_requires_exact_canonical_expiry(self):
        with self.assertRaises(ValueError):
            IndexValidation(1, "a" * 64, "b" * 64, "2026-10-16T18:00:00Z")

    def test_permission_expiry_during_final_key_check_rolls_back_promotion(self):
        lease = self.catalog.create(self.scope)
        self.addCleanup(lease.close)
        checkpoint = self.catalog.watermark()
        with self.initialized_store(lease) as store:
            store.finish_build(checkpoint)
            projection = store.projection()
        deadline = self.now + timedelta(seconds=10)
        expiry = deadline.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        validation = IndexValidation(
            checkpoint, "c" * 64, actor_context_sha256(self.project, self.fixture.actor), expiry
        )
        original = self.catalog._assert_key
        calls = 0

        def expire(snapshot):
            nonlocal calls
            original(snapshot)
            calls += 1
            if calls == 3:
                self.now = deadline

        with patch.object(self.catalog, "_assert_key", side_effect=expire), self.assertRaises(IndexCatalogProblem):
            self.catalog.publish_ready(
                lease, projection, validation, expected_selection_id=None, revalidate=lambda _db: None
            )
        self.assertEqual(3, calls)
        self.assertIsNone(self.catalog.selected())
        self.assertEqual("Building", self.catalog.get(self.scope.generation_id).stage)

    def test_cancellation_after_ready_event_rolls_back_event_pointer_and_audit_together(self):
        lease = self.catalog.create(self.scope)
        self.addCleanup(lease.close)
        checkpoint = self.catalog.watermark()
        with self.initialized_store(lease) as store:
            store.finish_build(checkpoint)
            projection = store.projection()
        validation = IndexValidation(checkpoint, "c" * 64, actor_context_sha256(self.project, self.fixture.actor), None)

        def counts():
            with self.catalog._transaction(write=False) as (db, _actor, _now):
                return tuple(
                    db.execute("SELECT count(*) FROM " + table).fetchone()[0]
                    for table in ("search_generation_events", "search_selections", "provenance_events", "outbox_events")
                )

        before = counts()
        stopped = False
        original = self.catalog._event

        def cancel_after_event(*args, **kwargs):
            nonlocal stopped
            result = original(*args, **kwargs)
            if kwargs.get("stage") == "Ready":
                stopped = True
            return result

        with (
            patch.object(self.catalog, "_event", side_effect=cancel_after_event),
            self.assertRaises(IndexCatalogProblem),
        ):
            self.catalog.publish_ready(
                lease,
                projection,
                validation,
                expected_selection_id=None,
                revalidate=lambda _db: None,
                cancelled=lambda: stopped,
            )
        self.assertTrue(stopped)
        self.assertEqual(before, counts())
        self.assertIsNone(self.catalog.selected())
        self.assertEqual("Building", self.catalog.get(self.scope.generation_id).stage)


if __name__ == "__main__":
    unittest.main()
