"""Actual canonical queue/run/provenance transactions; synthetic Native fixture."""

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.lexical_index_repository import IndexServiceProblem  # noqa: E402
from research_observatory_core.lexical_input_repository import rights_time_partition  # noqa: E402
from research_observatory_core.lexical_search_repository import SqliteLexicalSearchRepository  # noqa: E402
from research_observatory_core.ports.workflow_executor import WorkflowActor  # noqa: E402
from research_observatory_core.repositories import _SqliteIntentRevisionRepository  # noqa: E402
from research_observatory_core.rights_policy import RightsPolicyRevision  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402

from tests.connectors.test_connector_authority import ConnectorAuthorityFixture  # noqa: E402
from tests.search.fixture_support import SearchRunFixture  # noqa: E402


class SearchRunRepositoryTests(SearchRunFixture):
    def test_each_search_intent_read_is_fresh_and_coherent_in_one_connection(self):
        preview = self.document_fixture.f.preview
        adapter = SqliteLexicalSearchRepository(
            SimpleNamespace(imports=preview.service, now=lambda: self.document_fixture.now),
            derivative_keys=self.service.keys,
            database_keys=self.service.canonical_keys,
        )
        opened = []
        original = _SqliteIntentRevisionRepository._open

        def tracked_open(repository):
            connection = original(repository)
            opened.append(connection)
            return connection

        def read():
            with patch.object(_SqliteIntentRevisionRepository, "_open", tracked_open):
                return adapter._using(
                    self.document_fixture.repository,
                    preview.root,
                    self.document_fixture.f.session,
                    lambda runs: runs.intent(),
                )

        first = read()
        authority = ConnectorAuthorityFixture(methodName="runTest")
        authority.root, authority.service = preview.root, preview.intents
        changed = authority.intent("local-only")
        second = read()
        self.assertEqual(self.document_fixture.intent, first)
        self.assertEqual(changed.revision_id, second.revision_id)
        self.assertNotEqual(first.revision_id, second.revision_id)
        self.assertEqual(2, len(opened), "each fresh coherent read must use one canonical connection")

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


def stamp(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class CommitTimeBoundaryReproduction(SearchRunFixture):
    def _accepted_counts(self):
        with self.f.corpus.repository._transaction(write=False) as (db, _aggregates):
            return {
                name: db.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                for name in (
                    "aggregate_revisions",
                    "search_lexical_runs",
                    "search_input_manifests",
                    "search_observation_events",
                    "workflow_attempt_artifacts",
                    "workflow_committed_outputs",
                    "provenance_events",
                    "outbox_events",
                )
            }

    def _reject_transition_after_terminal_write(self, transition, *, expected_expiry=None):
        inputs = self.inputs()
        job = self.repo.submit(inputs)
        claim = self.claim(job)
        original = self.repo.queue._complete_with_connection
        completed = []
        before = {}

        def terminal_then_transition(*args, **kwargs):
            value = original(*args, **kwargs)
            completed.append(True)
            transition()
            return value

        def consume(snapshot, _store):
            nonlocal before
            self.assertTrue(snapshot.ranked)
            self.assertEqual(expected_expiry, snapshot.validation.expires_at)
            before = self._accepted_counts()
            return self.repo.complete(claim, snapshot, cancelled=lambda: False)

        with (
            patch.object(self.repo.queue, "_complete_with_connection", side_effect=terminal_then_transition),
            self.assertRaises(IndexServiceProblem),
        ):
            self.reader.read(parse_query("identifiers:synthetic"), consume=consume)
        self.assertEqual([True], completed, "the real terminal writer must execute before the transition")
        self.assertTrue(before)
        self.assertIsNone(self.repo.queue.accepted_output(job.job_id), "expired acceptance must roll back")
        self.assertEqual("running", self.repo.queue.get(job.job_id).state)
        self.assertEqual(before, self._accepted_counts(), "all accepted history must roll back atomically")

    def test_expiry_after_terminal_write_rolls_back_canonical_acceptance(self):
        baseline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=1)
        boundary = baseline + timedelta(minutes=1)
        instant = baseline
        self.f.permit(self.subject, previous=self.grant.revision_id, corpus_membership=True, expires_at=stamp(boundary))
        self.service.catalog.now = lambda: stamp(instant)

        def expire():
            nonlocal instant
            instant = boundary

        with patch("research_observatory_core.rights_repository._utcnow", side_effect=lambda: instant):
            self.service.rebuild()
            self._reject_transition_after_terminal_write(expire, expected_expiry=stamp(boundary))

    def test_clock_rollback_after_terminal_write_rolls_back_canonical_acceptance(self):
        baseline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=1)
        earlier = baseline - timedelta(milliseconds=1)
        instant = baseline
        self.service.catalog.now = lambda: stamp(instant)
        with self.f.corpus.repository._transaction(write=False) as (db, _aggregates):
            self.assertEqual(
                rights_time_partition(db, self.service.project, stamp(baseline)),
                rights_time_partition(db, self.service.project, stamp(earlier)),
            )

        def roll_back():
            nonlocal instant
            instant = earlier

        with patch("research_observatory_core.rights_repository._utcnow", side_effect=lambda: instant):
            self.service.rebuild()
            self._reject_transition_after_terminal_write(roll_back)

    def test_nonmatching_activation_after_terminal_write_rolls_back_canonical_acceptance(self):
        parsed = self.document_fixture.parse("Entirely unrelated final commit activation passage")
        self.document_fixture.repository.accept(self.document_fixture.command(parsed))
        subject = self.document_fixture.f.candidate.rights_subject
        grant = self.f.permit(subject, previous=self.document_fixture.f.policy.revision_id)
        baseline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=1)
        boundary = baseline + timedelta(minutes=1)
        instant = baseline
        policy = RightsPolicyRevision(
            revision_id=new_uuid_v7(),
            predecessor_revision_id=grant.revision_id,
            subject=subject,
            permissions=tuple(
                permission.model_copy(
                    update={"assertion_id": new_uuid_v7(), "recorded_at": stamp(boundary), "expires_at": None}
                )
                for permission in grant.permissions
            ),
        )
        self.f.attachments.rights.publish(
            policy, command_id=new_uuid_v7(), command_sha256="c" * 64, actor=self.document_fixture.actor
        )
        self.service.catalog.now = lambda: stamp(instant)

        def activate():
            nonlocal instant
            instant = boundary

        with patch("research_observatory_core.rights_repository._utcnow", side_effect=lambda: instant):
            self.service.rebuild()
            captured = self.f.sources.capture(self.f.item.item_id)
            self.assertTrue(captured.rows)
            self.assertFalse(any(row.full_text for row in captured.rows))
            self._reject_transition_after_terminal_write(activate)


if __name__ == "__main__":
    unittest.main()
