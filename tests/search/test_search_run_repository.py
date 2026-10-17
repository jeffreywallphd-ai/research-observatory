"""Actual canonical queue/run/provenance transactions; synthetic Native fixture."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.lexical_index_repository import IndexServiceProblem  # noqa: E402
from research_observatory_core.ports.workflow_executor import WorkflowActor  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402

from tests.search.fixture_support import SearchRunFixture  # noqa: E402


class SearchRunRepositoryTests(SearchRunFixture):
    def test_submission_replay_conflict_and_canonical_run_do_not_invalidate_inputs(self):
        self.service.rebuild()
        inputs = self.inputs()
        initial = self.reader.read(parse_query("identifiers:synthetic"))
        job, claim, (record, completion) = self.execute(inputs)
        self.assertEqual("succeeded", self.repo.queue.get(job.job_id).state)
        replay = self.repo.submit(inputs)
        self.assertEqual(job.job_id, replay.job_id)
        self.assertEqual("succeeded", replay.state)
        self.assertEqual(record, self.repo.result(job.job_id))
        self.assertEqual(1, len(completion.outputs))
        self.assertEqual(record.content.search_run_id, completion.outputs[0].artifact_id)
        self.assertEqual(initial, self.reader.read(parse_query("identifiers:synthetic")))
        repeated = self.reader.read(
            parse_query("identifiers:synthetic"),
            consume=lambda snapshot, _store: self.repo.complete(claim, snapshot, cancelled=lambda: False),
        )
        self.assertEqual(record, repeated[0])
        with self.assertRaises(IndexServiceProblem):
            self.repo.submit(self.inputs(command=inputs.command_id, query="different"))
        # A second independently persisted run and actual generic workflow
        # completion cannot invalidate the first run's unchanged input identity.
        self.execute(self.inputs())
        self.assertEqual(initial, self.reader.read(parse_query("identifiers:synthetic")))
        self.assertEqual(record, self.repo.result(job.job_id))

    def test_result_disclosure_requires_current_inputs_after_canonical_success(self):
        self.service.rebuild()
        job, _claim, (record, _completion) = self.execute(self.inputs())
        self.assertEqual(record, self.repo.result(job.job_id))
        self.f.permit(self.subject, previous=self.grant.revision_id, corpus_membership=True, index="denied")
        with self.assertRaises(IndexServiceProblem):
            self.repo.result(job.job_id)
        self.assertEqual("succeeded", self.repo.queue.get(job.job_id).state)
        with self.f.corpus.repository._transaction(write=False) as (db, _aggregates):
            self.assertEqual(1, db.execute("SELECT count(*) FROM search_lexical_runs").fetchone()[0])

    def test_cancellation_before_commit_creates_no_accepted_node_or_partial_history(self):
        self.service.rebuild()
        inputs = self.inputs()
        job = self.repo.submit(inputs)
        claim = self.claim(job)
        self.repo.queue.request_cancellation(
            job.job_id,
            actor=WorkflowActor(inputs.actor_id, "human", "researcher"),
            now=self.document_fixture.now,
            reason_code="user-cancel",
            interruption_kind="user-cancel",
        )
        with self.assertRaises(IndexServiceProblem):
            self.reader.read(
                parse_query("identifiers:synthetic"),
                consume=lambda snapshot, _store: self.repo.complete(claim, snapshot, cancelled=lambda: False),
            )
        self.assertIsNone(self.repo.queue.accepted_output(job.job_id))
        with self.f.corpus.repository._transaction(write=False) as (db, _aggregates):
            self.assertEqual(0, db.execute("SELECT count(*) FROM search_lexical_runs").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT count(*) FROM search_observation_events").fetchone()[0])

    def test_known_object_quarantine_without_outbox_denies_old_result(self):
        self.service.rebuild()
        job, _claim, (_record, _completion) = self.execute(self.inputs())
        head = self.service.catalog.watermark()
        with self.f.corpus.repository._transaction(write=True) as (db, _aggregates):
            from research_observatory_core.lexical_input_repository import source_authority_epoch

            epoch = source_authority_epoch(db, self.service.project)
            db.execute("UPDATE object_records SET verified_at=created_at WHERE storage_state='available'")
            self.assertEqual(epoch, source_authority_epoch(db, self.service.project))
            self.assertGreater(
                db.execute("SELECT count(*) FROM object_records WHERE storage_state='available'").fetchone()[0], 0
            )
            db.execute(
                "UPDATE object_records SET storage_state='quarantined',verified_at=NULL WHERE storage_state='available'"
            )
            self.assertGreater(source_authority_epoch(db, self.service.project), epoch)
        self.assertEqual(head, self.service.catalog.watermark())
        with self.assertRaises(IndexServiceProblem):
            self.repo.result(job.job_id)


if __name__ == "__main__":
    unittest.main()
