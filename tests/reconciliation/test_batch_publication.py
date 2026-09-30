"""One real queue/SQLite commit for exact reconciliation and candidate publication."""

import json
import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
from typing import cast
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.workflow_executor import WorkflowActor
from research_observatory_core.reconciliation.batch import (
    BATCH_ACTIVITY,
    SOURCE_ACTIVITIES,
    BatchInput,
    InventorySnapshot,
)
from research_observatory_core.reconciliation.candidate_sets import REVIEW_PRIORITY_FINGERPRINT, content_digest
from research_observatory_core.reconciliation.candidates import generate_prepared_candidates
from research_observatory_core.reconciliation.contracts import ReconciliationProblem, ScholarlyField
from research_observatory_core.reconciliation.exact import IdentifierAssertion
from research_observatory_core.reconciliation.workflow import build_batch_job
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.repositories import _SqliteAggregateRepository
from research_observatory_core.storage import open_canonical_database

from tests.reconciliation.test_repository import ReconciliationRepositoryTests


class BatchPublicationTests(unittest.TestCase):
    def setUp(self):
        self.f = ReconciliationRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.addresses = (self.f.address, self.f.another_source())
        upstream = self.f.fixture.fixture
        self.queue = upstream.queue
        self.inputs = BatchInput(
            request_id=new_uuid_v7(),
            project_id=self.f.project,
            actor_id=self.f.actor.actor_id,
            intent=upstream.inputs.intent.model_copy(
                update={"status": "accepted", "content_hash": "sha256:" + self.f.actor.intent_sha256}
            ),
            policy_sha256="sha256:" + self.f.actor.policy_sha256,
            session_epoch="c" * 32,
            inventory=InventorySnapshot.from_queue(self.queue.accepted_snapshot(activity_types=SOURCE_ACTIVITIES)),
        )
        actor = WorkflowActor(self.f.actor.actor_id, "human", "researcher")
        self.job = self.queue.enqueue(
            build_batch_job(self.inputs, actor=actor, now=self.f.actor.occurred_at), actor=actor
        )
        self.claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.f.actor.occurred_at,
            lease_duration_ms=30000,
            activity_types=(BATCH_ACTIVITY,),
        )
        self.queue.start(self.claim, now=self.f.actor.occurred_at)

    def publish(self, **kwargs):
        return self.f.repository.publish_batch(
            self.inputs,
            self.addresses,
            claim=self.claim,
            actor=self.f.actor,
            resolve=self.f.resolve,
            now=lambda: self.f.actor.occurred_at,
            **kwargs,
        )

    def test_atomic_publication_and_reopened_replay_bind_final_membership(self):
        output = self.publish()
        self.assertEqual("succeeded", self.queue.get(self.job.job_id).state)
        content = self.f.repository.candidate_set(output.revision_id, resolve=self.f.resolve)
        self.assertEqual(2, len(content.members))
        heads = set()
        for item in content.members:
            assert item.canonical_work is not None
            heads.add(item.canonical_work.revision_id)
        self.assertEqual(1, len(heads))
        self.assertEqual(1, len(content.pair_sha256))
        before = self.f.counts()
        self.f.repository = SqliteReconciliationRepository(self.f.database, self.f.project)
        self.assertEqual(output, self.publish())
        self.assertEqual(before, self.f.counts())
        self.assertEqual(content, self.f.repository.candidate_set(output.revision_id, resolve=self.f.resolve))

    def test_new_candidate_set_binds_review_priority_as_atomic_material_configuration(self):
        output = self.publish()
        with open_canonical_database(self.f.database, expected_project_id=self.f.project) as db:
            rows = db.execute(
                "SELECT dependency_kind,relation_type,configuration_version,fingerprint FROM material_dependencies "
                "WHERE project_id=? AND output_revision_id=? AND configuration_id='scholarly.review-priority'",
                (self.f.project, output.revision_id),
            ).fetchall()
        self.assertEqual(
            [("parameter-set", "direct", "1.0.0", "sha256:" + REVIEW_PRIORITY_FINGERPRINT)],
            [tuple(row) for row in rows],
        )

    def test_legacy_publication_without_priority_marker_replays_original_accepted_output(self):
        # Reproduce the pre-correction publication shape through the real queue,
        # aggregate and candidate tables, then read/retry it with current code.
        append = SqliteReconciliationRepository._append

        def legacy_append(repository, *args, **kwargs):
            if kwargs.get("payload_configuration") == "duplicate-candidate-set":
                kwargs.pop("extra_parameter")
            return append(repository, *args, **kwargs)

        with (
            patch(
                "research_observatory_core.reconciliation_repository.prioritize_candidates",
                side_effect=lambda pairs, _: pairs,
            ),
            patch.object(SqliteReconciliationRepository, "_append", legacy_append),
        ):
            output = self.publish()
        original_content = self.f.repository.candidate_set(output.revision_id, resolve=self.f.resolve)
        original_page = self.f.repository.inspect_candidates(
            output.revision_id, after=0, limit=1, resolve=self.f.resolve
        )
        with open_canonical_database(self.f.database, expected_project_id=self.f.project) as db:
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM material_dependencies "
                    "WHERE project_id=? AND output_revision_id=? AND configuration_id='scholarly.review-priority'",
                    (self.f.project, output.revision_id),
                ).fetchone()[0],
            )
        counts = self.f.counts()
        self.f.repository = SqliteReconciliationRepository(self.f.database, self.f.project)
        self.assertEqual(output, self.publish())
        self.assertEqual(counts, self.f.counts())
        self.assertEqual(original_content, self.f.repository.candidate_set(output.revision_id, resolve=self.f.resolve))
        self.assertEqual(
            original_page,
            self.f.repository.inspect_candidates(output.revision_id, after=0, limit=1, resolve=self.f.resolve),
        )

    def publish_prioritized_batch(self):
        # Establish one Work with two real source assertions. The next batch
        # requests only its first source, so the second must still affect priority.
        for address in self.addresses:
            source = self.f.resolved[address.revision_id]
            self.f.resolved[address.revision_id] = source.model_copy(
                update={
                    "fields": (
                        ScholarlyField(
                            name="title",
                            observed="Synthetic marine cells study",
                            origin="observed",
                            source_selector="title",
                        ),
                    )
                }
            )
        first = self.publish()
        original_set = self.f.repository.candidate_set(first.revision_id, resolve=self.f.resolve)
        self.assertEqual(2, len(original_set.members))
        original_second_assertion = original_set.members[1].assertion_revision_id

        new_addresses = tuple(self.f.another_source() for _ in range(2))
        for address in new_addresses:
            source = self.f.resolved[address.revision_id]
            self.f.resolved[address.revision_id] = source.model_copy(
                update={
                    "identifiers": (),
                    "fields": (
                        ScholarlyField(
                            name="title",
                            observed="Synthetic marine cell study",
                            origin="observed",
                            source_selector="title",
                        ),
                    ),
                }
            )
        self.addresses = (self.addresses[0], *new_addresses)
        self.inputs = self.inputs.model_copy(
            update={
                "request_id": new_uuid_v7(),
                "inventory": InventorySnapshot.from_queue(
                    self.queue.accepted_snapshot(activity_types=SOURCE_ACTIVITIES)
                ),
            }
        )
        actor = WorkflowActor(self.f.actor.actor_id, "human", "researcher")
        self.job = self.queue.enqueue(
            build_batch_job(self.inputs, actor=actor, now=self.f.actor.occurred_at), actor=actor
        )
        self.claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.f.actor.occurred_at,
            lease_duration_ms=30000,
            activity_types=(BATCH_ACTIVITY,),
        )
        self.queue.start(self.claim, now=self.f.actor.occurred_at)

        output = self.publish()
        content = self.f.repository.candidate_set(output.revision_id, resolve=self.f.resolve)
        pairs = self.f.repository.candidate_pairs(output.revision_id, after=0, limit=100, resolve=self.f.resolve)
        self.assertEqual(3, len(content.members))
        self.assertEqual(3, len(pairs))
        first_work = original_set.members[0].canonical_work
        assert first_work is not None
        context = self.f.repository.review_context((first_work.work_id,), resolve=self.f.resolve)
        self.assertEqual(2, len(context.works[0].assertion_revision_ids))
        self.assertEqual(
            1,
            sum(
                member.canonical_work is not None and member.canonical_work.work_id == first_work.work_id
                for member in content.members
            ),
        )
        self.assertNotIn(original_second_assertion, {member.assertion_revision_id for member in content.members})
        other_assertions = {
            member.assertion_revision_id
            for member in content.members
            if member.canonical_work is None or member.canonical_work.work_id != first_work.work_id
        }
        self.assertEqual(2, len(other_assertions))
        within_other = next(pair for pair in pairs if {pair.left, pair.right} == other_assertions)
        self.assertTrue(any(pair.score < within_other.score for pair in pairs[: pairs.index(within_other)]))
        self.assertEqual(
            tuple(content.pair_sha256),
            tuple(content_digest(pair) for pair in pairs),
        )
        pages = list(pairs[:0])
        after = 0
        while True:
            page = self.f.repository.inspect_candidates(
                output.revision_id, after=after, limit=1, resolve=self.f.resolve
            )
            pages.extend(page.items)
            if page.next_after is None:
                break
            after = page.next_after
        self.assertEqual(pairs, tuple(pages))
        counts = self.f.counts()
        self.f.repository = SqliteReconciliationRepository(self.f.database, self.f.project)
        self.assertEqual(output, self.publish())
        self.assertEqual(counts, self.f.counts())
        self.assertEqual(
            pairs, self.f.repository.candidate_pairs(output.revision_id, after=0, limit=100, resolve=self.f.resolve)
        )
        self.assertEqual(
            pairs[1:2], self.f.repository.candidate_pairs(output.revision_id, after=1, limit=1, resolve=self.f.resolve)
        )
        return output, pairs

    def test_priority_uses_complete_sealed_work_membership_and_preserves_exact_replay(self):
        self.publish_prioritized_batch()

    def test_storage_checks_reject_untyped_feature_set_and_explanation_documents(self):
        self.publish()
        # Exercise each actual table's CHECK authority directly, independently
        # of adapter decoding. Real publication above supplies valid domain rows;
        # other tests exercise parent foreign keys and immutable publication.
        for table, collection, maximum in (
            ("reconciliation_feature_cache", "fields", 6),
            ("reconciliation_candidate_sets", "members", 10000),
            ("reconciliation_candidate_pairs", "features", 7),
        ):
            with open_canonical_database(self.f.database, expected_project_id=self.f.project) as source:
                ddl = source.execute("SELECT sql FROM sqlite_schema WHERE name=?", (table,)).fetchone()[0]
                columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]
                original = list(source.execute(f'SELECT * FROM "{table}" LIMIT 1').fetchone())
            position = next(index for index, name in enumerate(columns) if name.endswith("_json"))
            document = json.loads(original[position])
            missing = {key: value for key, value in document.items() if key != "algorithm"}
            malformed: tuple[dict[str, object], ...] = (
                {**document, "unexpectedContent": "untyped"},
                missing,
                {**document, "algorithm": "unrecognized"},
                {**document, collection: {}},
                {**document, collection: [{}] * (maximum + 1)},
            )
            if table == "reconciliation_candidate_pairs":
                malformed += ({**document, "score": True}, {**document, "score": 10001})
            with closing(sqlite3.connect(":memory:")) as isolated:
                isolated.execute(ddl)
                insert = f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in columns)})'
                isolated.execute(insert, original)
                self.assertEqual(1, isolated.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
                isolated.execute(f'DELETE FROM "{table}"')
                for value in malformed:
                    isolated.execute(f'DELETE FROM "{table}"')
                    changed = original.copy()
                    changed[position] = json.dumps(value)
                    with (
                        self.subTest(table=table, fields=tuple(value)),
                        self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK constraint failed"),
                    ):
                        isolated.execute(insert, changed)

    def test_large_dependency_manifest_preserves_all_material_and_historical_leaves(self):
        with self.f.repository._transaction(write=False) as (_, repository):
            template = repository.get_revision(self.f.source.source_revision_id)
        sources = tuple(replace(template, revision_id=new_uuid_v7(), aggregate_id=new_uuid_v7()) for _ in range(4097))
        historical = tuple(replace(template, revision_id=new_uuid_v7(), aggregate_id=new_uuid_v7()) for _ in range(65))
        drafts = {}
        test = self

        class AggregateProbe:
            def _require_fresh_revision(self, *_args, **_kwargs):
                pass

            def append(self, draft, _event, **_kwargs):
                test.assertLessEqual(len(draft.provenance_inputs), 64)
                drafts[draft.revision_id] = draft
                return replace(
                    template,
                    revision_id=draft.revision_id,
                    aggregate_id=draft.aggregate_id,
                    aggregate_kind=draft.aggregate_kind,
                )

        output = self.f.repository._append(
            cast(_SqliteAggregateRepository, AggregateProbe()),
            sources=sources,
            historical_sources=historical,
            actor=self.f.actor,
            digest="a" * 64,
            label="Synthetic bounded manifest",
            kind="workflow",
        )
        material: set[str] = set()
        retained: set[str] = set()

        def visit(revision, historical=False):
            if revision not in drafts:
                (retained if historical else material).add(revision)
                return
            for dependency in drafts[revision].material_dependencies:
                if dependency.revision_id:
                    visit(dependency.revision_id, historical or dependency.relation_type == "non-material")

        visit(output.revision_id)
        self.assertEqual({item.revision_id for item in sources}, material)
        self.assertEqual({item.revision_id for item in historical}, retained)

    def test_preparation_renews_a_live_lease_and_failed_job_continues_explicitly(self):
        self.queue.fail(self.claim, now=self.f.actor.occurred_at, error_code="invalid-input")
        previous = next(item for item in self.queue.task_center() if item.workflow_run_id == self.job.workflow_run_id)
        continued = self.queue.retry_as_continuation(
            self.job.job_id,
            expected_snapshot_revision=previous.snapshot_revision,
            expected_history_sequence=previous.revision,
            idempotency_key="d" * 32,
            actor=WorkflowActor(self.f.actor.actor_id, "human", "researcher"),
            now=self.f.actor.occurred_at,
        )
        self.claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.f.actor.occurred_at,
            lease_duration_ms=30000,
            activity_types=(BATCH_ACTIVITY,),
        )
        self.queue.start(self.claim, now=self.f.actor.occurred_at)
        elapsed = 0

        def now():
            return (
                (datetime.fromisoformat(self.f.actor.occurred_at) + timedelta(seconds=elapsed))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )

        def resolve(address):
            nonlocal elapsed
            elapsed += 20
            return self.f.resolve(address)

        output = self.f.repository.publish_batch(
            self.inputs, self.addresses, claim=self.claim, actor=self.f.actor, resolve=resolve, now=now
        )
        self.assertGreater(elapsed, 30)
        self.assertEqual("failed", self.queue.get(self.job.job_id).state)
        self.assertEqual("succeeded", self.queue.get(continued.jobs[0].job_id).state)
        self.assertEqual(output, self.queue.accepted_output(continued.jobs[0].job_id).outputs[0])

    def test_failure_and_stop_roll_back_exact_facts_and_queue_acceptance(self):
        before = self.f.counts()
        for seam in ("batch-exact-complete", "batch-candidates-created", "batch-before-completion"):

            def fail(step, seam=seam):
                if step == seam:
                    raise RuntimeError("injected-batch-failure")

            with (
                self.subTest(seam=seam),
                patch("research_observatory_core.reconciliation_repository._publication_step", fail),
                self.assertRaisesRegex(RuntimeError, "injected-batch-failure"),
            ):
                self.publish()
            self.assertEqual(before, self.f.counts())
            self.assertEqual("running", self.queue.get(self.job.job_id).state)
            with open_canonical_database(self.f.database, expected_project_id=self.f.project) as db:
                self.assertEqual(
                    0,
                    db.execute(
                        "SELECT COUNT(*) FROM material_dependencies "
                        "WHERE project_id=? AND configuration_id='scholarly.review-priority'",
                        (self.f.project,),
                    ).fetchone()[0],
                )
        polls = 0

        def interrupted():
            nonlocal polls
            polls += 1
            return polls >= 5

        with self.assertRaisesRegex(RuntimeError, "reconciliation-batch-interrupted"):
            self.publish(interrupted=interrupted)
        self.assertEqual(before, self.f.counts())
        self.publish()

    def test_fuzzy_similarity_never_merges_and_inspection_rechecks_rights(self):
        for index, address in enumerate(self.addresses):
            self.f.resolved[address.revision_id] = self.f.resolved[address.revision_id].model_copy(
                update={
                    "identifiers": (IdentifierAssertion(scheme="doi", observed=f"10.99999/unique-{index}"),),
                    "fields": (
                        ScholarlyField(
                            name="title",
                            observed="Synthetic identical scholarly title",
                            origin="observed",
                            source_selector="title",
                        ),
                        ScholarlyField(
                            name="authors", observed="Synthetic Author", origin="observed", source_selector="authors"
                        ),
                        ScholarlyField(name="year", observed="2024", origin="observed", source_selector="year"),
                    ),
                }
            )
        output = self.publish()
        content = self.f.repository.candidate_set(output.revision_id, resolve=self.f.resolve)
        works = set()
        for member in content.members:
            assert member.canonical_work is not None
            works.add(member.canonical_work.work_id)
        self.assertEqual(2, len(works))
        pairs = self.f.repository.candidate_pairs(output.revision_id, after=0, limit=100, resolve=self.f.resolve)
        self.assertEqual(1, len(pairs))
        self.assertIn("conflicting-identifiers", pairs[0].flags)
        self.assertEqual("human-review-required", pairs[0].disposition)
        address = self.addresses[0]
        source = self.f.resolved[address.revision_id]
        self.f.resolved[address.revision_id] = source.model_copy(
            update={
                "rights": source.rights.model_copy(
                    update={"inspect": source.rights.inspect.model_copy(update={"value": "denied"})}
                )
            }
        )
        with self.assertRaises(ReconciliationProblem):
            self.f.repository.candidate_pairs(output.revision_id, after=0, limit=100, resolve=self.f.resolve)
        with self.assertRaises(ReconciliationProblem):
            self.f.repository.inspect_candidates(output.revision_id, after=0, limit=1, resolve=self.f.resolve)
        with self.assertRaises(ReconciliationProblem):
            self.publish()

    def test_stop_during_scoring_and_before_acceptance_is_atomic(self):
        before = self.f.counts()
        stopped = False

        def score(*args, **kwargs):
            nonlocal stopped
            stopped = True
            return generate_prepared_candidates(*args, **kwargs)

        with (
            patch("research_observatory_core.reconciliation_repository.generate_prepared_candidates", score),
            self.assertRaisesRegex(ReconciliationProblem, "reconciliation-batch-interrupted"),
        ):
            self.publish(interrupted=lambda: stopped)
        self.assertEqual(before, self.f.counts())
        stopped = False

        def stop(step):
            nonlocal stopped
            if step == "batch-before-completion":
                stopped = True

        with (
            patch("research_observatory_core.reconciliation_repository._publication_step", stop),
            self.assertRaisesRegex(ReconciliationProblem, "reconciliation-batch-interrupted"),
        ):
            self.publish(interrupted=lambda: stopped)
        self.assertEqual(before, self.f.counts())
        self.assertIsNone(self.queue.accepted_output(self.job.job_id))

    def test_stop_interrupts_a_long_sql_statement_and_rolls_back(self):
        before = self.f.counts()
        inside_sql = False
        polls = 0
        original = self.f.repository._append

        def interrupted():
            nonlocal polls
            if inside_sql:
                polls += 1
            return inside_sql and polls >= 2

        def append(repository, **kwargs):
            nonlocal inside_sql
            result = original(repository, **kwargs)
            inside_sql = True
            repository._state().connection.execute(
                "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000) SELECT SUM(x) FROM n"
            ).fetchone()
            self.fail("stop signal did not interrupt the SQL boundary")
            return result

        with (
            patch.object(self.f.repository, "_append", append),
            self.assertRaisesRegex(ReconciliationProblem, "reconciliation-batch-interrupted"),
        ):
            self.publish(interrupted=interrupted)
        self.assertEqual(before, self.f.counts())
        self.assertIsNone(self.queue.accepted_output(self.job.job_id))

    def test_substituted_claim_and_current_authority_deny_without_facts(self):
        before = self.f.counts()
        original = self.claim
        self.claim = replace(original, lease_token="0" * 64)
        with self.assertRaises(RuntimeError):
            self.publish()
        self.claim = original
        self.f.actor = replace(self.f.actor, policy_sha256="0" * 64)
        with self.assertRaises(ReconciliationProblem):
            self.publish()
        self.assertEqual(before, self.f.counts())

    def test_pair_payload_substitution_cannot_rebind_itself_to_root_manifest(self):
        output = self.publish()
        # Corrupt only a disposable fixture, preserving its exact trigger DDL.
        import sqlite3

        with closing(sqlite3.connect(self.f.database)) as db, db:
            ddl = db.execute(
                "SELECT sql FROM sqlite_schema WHERE type='trigger' AND name='reconciliation_candidate_pairs_no_update'"
            ).fetchone()[0]
            db.execute("DROP TRIGGER reconciliation_candidate_pairs_no_update")
            db.execute(
                "UPDATE reconciliation_candidate_pairs "
                "SET explanation_json=json_set(explanation_json,'$.leftFingerprint',?) "
                "WHERE set_revision_id=?",
                ("f" * 64, output.revision_id),
            )
            db.execute(ddl)
        with self.assertRaises(ReconciliationProblem):
            self.f.repository.candidate_pairs(output.revision_id, after=0, limit=1, resolve=self.f.resolve)
        with open_canonical_database(self.f.database, expected_project_id=self.f.project) as canonical:
            self.assertEqual(1, canonical.execute("SELECT COUNT(*) FROM reconciliation_candidate_sets").fetchone()[0])
