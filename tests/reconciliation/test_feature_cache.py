"""A derived feature cache never grants rights or substitutes source authority."""

import unittest
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.candidates import prepare_record
from research_observatory_core.reconciliation.contracts import ReconciliationProblem
from research_observatory_core.reconciliation.feature_cache import FeatureSnapshot, candidate_record
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.storage import open_canonical_database

from tests.reconciliation import test_repository as fixture_module


class FeatureCacheTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.ReconciliationRepositoryTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.result = f.repository.reconcile(f.address, command_id=new_uuid_v7(), actor=f.actor, resolve=f.resolve)

    def test_cache_reopens_without_recomputing_and_reauthorizes_every_read(self):
        f = self.fixture
        expected = prepare_record(candidate_record(self.result.assertion_revision_id, f.source))
        with patch(
            "research_observatory_core.reconciliation.feature_cache.prepare_record", wraps=prepare_record
        ) as compute:
            first = f.repository.prepared_record(self.result.assertion_revision_id, resolve=f.resolve)
            reopened = SqliteReconciliationRepository(f.database, f.project)
            self.assertEqual(expected, first)
            self.assertEqual(first, reopened.prepared_record(self.result.assertion_revision_id, resolve=f.resolve))
            self.assertEqual(1, compute.call_count)
        denied = []

        def no_rights(address):
            denied.append(address)
            raise ReconciliationProblem("reconciliation-rights-denied")

        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-rights-denied"):
            reopened.prepared_record(self.result.assertion_revision_id, resolve=no_rights)
        self.assertEqual([f.address], denied)
        with open_canonical_database(f.database, expected_project_id=f.project) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM reconciliation_feature_cache").fetchone()[0])

    def test_snapshot_binds_exact_source_revision_and_rejects_substitution(self):
        f = self.fixture
        item = FeatureSnapshot.create(self.result.assertion_revision_id, f.source)
        self.assertEqual(
            prepare_record(candidate_record(self.result.assertion_revision_id, f.source)),
            item.restore(self.result.assertion_revision_id, f.source),
        )
        changed = f.source.model_copy(update={"source_revision_id": new_uuid_v7()})
        with self.assertRaisesRegex(ReconciliationProblem, "duplicate-feature-cache-mismatch"):
            item.restore(self.result.assertion_revision_id, changed)
        with self.assertRaisesRegex(ReconciliationProblem, "duplicate-feature-cache-mismatch"):
            item.restore(new_uuid_v7(), f.source)
        raw = item.model_dump(mode="json", by_alias=True)
        raw["unexpected"] = True
        with self.assertRaises(ValueError):
            FeatureSnapshot.model_validate(raw)
