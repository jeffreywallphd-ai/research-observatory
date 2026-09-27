"""Frozen local request authority survives restart without mutable command reuse."""

import unittest

from research_observatory_core.reconciliation.contracts import ReconciliationProblem
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository

from tests.reconciliation import test_batch_publication as fixtures


class BatchRequestTests(unittest.TestCase):
    def test_request_round_trip_exact_replay_and_changed_authority_denial(self):
        f = fixtures.BatchPublicationTests(methodName="runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        repository = f.f.repository
        self.assertIsNone(repository.batch_request(f.inputs.request_id))
        self.assertEqual(f.inputs, repository.save_batch_request(f.inputs, actor=f.f.actor))
        reopened = SqliteReconciliationRepository(f.f.database, f.f.project)
        self.assertEqual(f.inputs, reopened.batch_request(f.inputs.request_id))
        self.assertEqual(f.inputs, reopened.save_batch_request(f.inputs, actor=f.f.actor))
        for changed in (
            f.inputs.model_copy(update={"session_epoch": "d" * 32}),
            f.inputs.model_copy(update={"policy_sha256": "sha256:" + "e" * 64}),
        ):
            with self.subTest(fields=changed.session_epoch), self.assertRaises(ReconciliationProblem):
                reopened.save_batch_request(changed, actor=f.f.actor)
        self.assertEqual(f.inputs, reopened.batch_request(f.inputs.request_id))
