"""Human review publishes reversible identity, history, and dependency intent atomically."""

import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportRights
from research_observatory_core.ports.repositories import RepositoryConflict
from research_observatory_core.reconciliation.contracts import ReconciliationProblem
from research_observatory_core.reconciliation.decisions import AliasPlan, ReviewCommand, ReviewPlan, SourcePartition
from research_observatory_core.reconciliation.exact import IdentifierAssertion
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
)
from research_observatory_core.storage import _DATABASE_ERRORS, open_canonical_database

from tests.reconciliation import test_repository as fixture_module


class ReviewRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.ReconciliationRepositoryTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.repo, self.actor, self.resolve = f.repository, f.actor, f.resolve
        self.a_command = new_uuid_v7()
        self.a = self.repo.reconcile(f.address, command_id=self.a_command, actor=self.actor, resolve=self.resolve)
        self.b_address = f.another_source(
            identifiers=(IdentifierAssertion(scheme="doi", observed="10.99999/synthetic-b"),)
        )
        self.b = self.repo.reconcile(self.b_address, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve)

    def context(self, works, unassigned=()):
        return self.repo.review_context(tuple(works), unassigned=tuple(unassigned), resolve=self.resolve)

    def merge_plan(self):
        assert self.a.work_id is not None and self.b.work_id is not None
        context = self.context((self.a.work_id, self.b.work_id))
        works = {work.work_id: work for work in context.works}
        return ReviewPlan(
            action="merge",
            works=context.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(
                    group="survivor",
                    existing_work_id=self.a.work_id,
                    assertion_revision_ids=tuple(sorted((self.a.assertion_revision_id, self.b.assertion_revision_id))),
                ),
            ),
            aliases=(
                AliasPlan(
                    work_id=self.b.work_id, revision_id=works[self.b.work_id].revision_id, target_group="survivor"
                ),
            ),
            conflict_disposition="retain-all",
            evidence_sha256=context.fingerprint,
            rationale="Synthetic explicit human merge",
        )

    def command(self, plan):
        preview = self.repo.preview_review(plan, actor=self.actor, resolve=self.resolve)
        return ReviewCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256)

    def commit(self, command):
        return self.repo.review(command, actor=self.actor, resolve=self.resolve)

    def counts(self):
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.project) as db:
            return tuple(
                (row[0], db.execute('SELECT COUNT(*) FROM "' + row[0] + '"').fetchone()[0])
                for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")
            )

    def test_merge_split_restart_alias_routing_exact_and_original_receipt(self):
        assert self.b.work_id is not None
        command = self.command(self.merge_plan())
        merged = self.commit(command)
        self.assertEqual(2, len(merged.work_states))
        self.assertEqual(2, len(merged.dependency_run_ids))
        after = self.counts()
        self.assertEqual(merged, self.commit(command))
        self.assertEqual(after, self.counts())
        context = self.context((self.a.work_id,))
        self.assertEqual((self.b.work_id,), tuple(item.work_id for item in context.inbound_aliases))
        split = ReviewPlan(
            action="split",
            works=context.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(
                    group="retained",
                    existing_work_id=self.a.work_id,
                    assertion_revision_ids=(self.a.assertion_revision_id,),
                ),
                SourcePartition(
                    group="separated", existing_work_id=None, assertion_revision_ids=(self.b.assertion_revision_id,)
                ),
            ),
            aliases=(
                AliasPlan(
                    work_id=self.b.work_id, revision_id=context.inbound_aliases[0].revision_id, target_group="separated"
                ),
            ),
            conflict_disposition="retain-all",
            evidence_sha256=context.fingerprint,
            rationale="Synthetic explicit reversal of merge",
        )
        separated = self.commit(self.command(split))
        new_work = next(
            item for item in separated.work_states if item.disposition == "active" and item.work_id != self.a.work_id
        )
        self.repo = SqliteReconciliationRepository(self.fixture.database, self.fixture.project)
        inspected = self.repo.inspect(self.b.assertion_revision_id, resolve=self.resolve)
        self.assertEqual(self.b, inspected.result)
        assert inspected.canonical_work is not None
        self.assertEqual(new_work.work_id, inspected.canonical_work.work_id)
        alias = next(item for item in separated.work_states if item.work_id == self.b.work_id)
        self.assertEqual(new_work.work_id, alias.alias_target)
        third = self.fixture.another_source(
            identifiers=(IdentifierAssertion(scheme="doi", observed="10.99999/synthetic-b"),)
        )
        exact = self.repo.reconcile(third, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve)
        self.assertEqual(new_work.work_id, exact.work_id)
        self.assertEqual("exact-linked", exact.disposition)

    def test_stale_preview_changed_command_actor_and_current_rights_deny_without_new_facts(self):
        command = self.command(self.merge_plan())
        self.commit(command)
        before = self.counts()
        with self.assertRaises(ReconciliationProblem):
            self.commit(command.model_copy(update={"command_id": new_uuid_v7()}))
        with self.assertRaises(ReconciliationProblem):
            self.repo.review(command, actor=replace(self.actor, actor_id=new_uuid_v7()), resolve=self.resolve)
        altered = command.plan.model_copy(update={"rationale": "Different human decision"})
        with self.assertRaises(ReconciliationProblem):
            self.commit(command.model_copy(update={"plan": altered}))
        self.fixture.resolved[self.b_address.revision_id] = self.fixture.resolved[
            self.b_address.revision_id
        ].model_copy(update={"rights": ImportRights()})
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-rights-denied"):
            self.commit(command)
        self.assertEqual(before, self.counts())

    def test_inbound_alias_cannot_be_omitted_or_substituted_when_splitting(self):
        self.commit(self.command(self.merge_plan()))
        context = self.context((self.a.work_id,))
        plan = ReviewPlan(
            action="split",
            works=context.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(
                    group="a", existing_work_id=self.a.work_id, assertion_revision_ids=(self.a.assertion_revision_id,)
                ),
                SourcePartition(
                    group="b", existing_work_id=None, assertion_revision_ids=(self.b.assertion_revision_id,)
                ),
            ),
            aliases=(),
            conflict_disposition="retain-all",
            evidence_sha256=context.fingerprint,
            rationale="Synthetic explicit split",
        )
        before = self.counts()
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-review-alias-plan-incomplete"):
            self.command(plan)
        alias = context.inbound_aliases[0]
        altered = plan.model_copy(
            update={"aliases": (AliasPlan(work_id=alias.work_id, revision_id=new_uuid_v7(), target_group="b"),)}
        )
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-review-alias-plan-incomplete"):
            self.command(altered)
        self.assertEqual(before, self.counts())

    def test_concurrent_decisions_have_one_winner(self):
        first = self.command(self.merge_plan())
        second = first.model_copy(update={"command_id": new_uuid_v7()})

        def submit(command):
            try:
                return self.commit(command)
            except ReconciliationProblem as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(submit, (first, second)))
        self.assertEqual(1, sum(isinstance(item, ReconciliationProblem) for item in results))
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.project) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM reconciliation_review_decisions").fetchone()[0])
            self.assertEqual(4, db.execute("SELECT COUNT(*) FROM reconciliation_work_states").fetchone()[0])

    def test_previously_affected_inputs_block_new_outputs_but_keep_history_inspectable(self):
        with self.repo._transaction(write=True) as (connection, aggregates):
            old = aggregates.get_revision(self.fixture.source.source_revision_id)
            replacement = self.repo._append(
                aggregates,
                sources=(),
                current=old,
                actor=self.actor,
                digest="7" * 64,
                label="Synthetic corrected source",
            )
            self.repo._publish_impacts(connection, (self.repo._change(old, replacement, self.actor, human=False),))
        replay = self.repo.reconcile(
            self.fixture.address, command_id=self.a_command, actor=self.actor, resolve=self.resolve
        )
        self.assertEqual(self.a, replay)
        plan = self.merge_plan()
        before = self.counts()
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-input-requires-review"):
            self.command(plan)
        self.assertEqual(before, self.counts())
        third = self.fixture.another_source()
        before = self.counts()
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-input-requires-review"):
            self.repo.reconcile(third, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve)
        self.assertEqual(before, self.counts())
        inspected = self.repo.inspect(self.a.assertion_revision_id, resolve=self.resolve)
        self.assertEqual(self.a, inspected.result)
        self.assertEqual("requires-review", inspected.dependency_state)

    def test_recorded_changed_root_blocks_later_derivation_but_equal_fingerprint_does_not(self):
        for changed in (False, True):
            with self.subTest(changed=changed):
                with self.repo._transaction(write=True) as (connection, aggregates):
                    old = self.repo._append(
                        aggregates, sources=(), actor=self.actor, digest="1" * 64, label="Synthetic independent input"
                    )
                    replacement = self.repo._append(
                        aggregates,
                        sources=(),
                        current=old,
                        actor=self.actor,
                        digest="2" * 64,
                        label="Synthetic updated input",
                    )
                    change = self.repo._change(old, replacement, self.actor)
                    if not changed:
                        change = replace(change, replacement_fingerprint=change.previous_fingerprint)
                    runs = self.repo._publish_impacts(connection, (change,))
                    self.assertEqual(
                        0,
                        connection.execute(
                            "SELECT COUNT(*) FROM dependency_impact_items WHERE run_id=?", (runs[0],)
                        ).fetchone()[0],
                    )
                before = self.counts()
                if changed:
                    with (
                        self.assertRaisesRegex(ReconciliationProblem, "reconciliation-input-requires-review"),
                        self.repo._transaction(write=True) as (_, aggregates),
                    ):
                        self.repo._append(
                            aggregates,
                            sources=(old,),
                            actor=self.actor,
                            digest="3" * 64,
                            label="Synthetic new derivation",
                        )
                    self.assertEqual(before, self.counts())
                else:
                    with self.repo._transaction(write=True) as (_, aggregates):
                        self.repo._append(
                            aggregates,
                            sources=(old,),
                            actor=self.actor,
                            digest="3" * 64,
                            label="Synthetic permitted derivation",
                        )

    def test_changed_prior_human_decision_denies_new_exact_output_and_preserves_replay(self):
        # Use compatible identifier namespaces so this path would append a Work
        # revision; a disputed DOI pair only creates a review-required assertion.
        compatible = self.fixture.another_source(identifiers=(IdentifierAssertion(scheme="pmid", observed="12345678"),))
        self.b = self.repo.reconcile(compatible, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve)
        command = self.command(self.merge_plan())
        outcome = self.commit(command)
        with self.repo._transaction(write=True) as (connection, aggregates):
            previous = aggregates.get_revision(outcome.decision_revision_id)
            revised = self.repo._append(
                aggregates,
                sources=(),
                current=previous,
                actor=self.actor,
                kind="decision",
                adjudicated=True,
                digest="d" * 64,
                label="Synthetic revised human judgment",
            )
            self.repo._publish_impacts(connection, (self.repo._change(previous, revised, self.actor),))
        self.assertEqual(outcome, self.commit(command))
        source = self.fixture.another_source()
        before = self.counts()
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-input-requires-review"):
            self.repo.reconcile(source, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve)
        self.assertEqual(before, self.counts())
        self.assertEqual(
            "requires-review", self.repo.inspect(self.a.assertion_revision_id, resolve=self.resolve).dependency_state
        )

    def test_affected_leaf_is_rejected_before_large_input_manifest_can_hide_it(self):
        with self.repo._transaction(write=True) as (connection, aggregates):
            inputs = tuple(
                self.repo._append(
                    aggregates,
                    sources=(),
                    actor=self.actor,
                    digest=str(index % 10) * 64,
                    label="Synthetic bounded source",
                )
                for index in range(65)
            )
            revised = self.repo._append(
                aggregates,
                sources=(),
                current=inputs[-1],
                actor=self.actor,
                digest="a" * 64,
                label="Synthetic changed final leaf",
            )
            self.repo._publish_impacts(connection, (self.repo._change(inputs[-1], revised, self.actor),))
        before = self.counts()
        with (
            self.assertRaisesRegex(ReconciliationProblem, "reconciliation-input-requires-review"),
            self.repo._transaction(write=True) as (_, aggregates),
        ):
            self.repo._append(
                aggregates, sources=inputs, actor=self.actor, digest="b" * 64, label="Synthetic denied derivation"
            )
        self.assertEqual(before, self.counts())

    def test_every_review_publication_failure_rolls_back_all_facts_and_can_retry(self):
        command = self.command(self.merge_plan())
        for step in (
            "review-decision-created",
            "review-work-created",
            "review-membership-created",
            "review-impacts-created",
            "review-command-created",
        ):
            with self.subTest(step=step):
                before = self.counts()

                def fail(observed, expected=step):
                    if observed == expected:
                        raise ReconciliationProblem("synthetic-review-interruption")

                with (
                    patch(
                        "research_observatory_core.reconciliation_repository._publication_step", side_effect=fail
                    ) as injected,
                    self.assertRaises(ReconciliationProblem),
                ):
                    self.commit(command)
                injected.assert_any_call(step)
                self.assertEqual(before, self.counts())
        self.commit(command)

    def test_unsealed_current_head_denies_inspection_and_identical_retry(self):
        assert self.a.work_id is not None
        with self.repo._transaction(write=True) as (_, aggregates):
            current = aggregates.get(self.a.work_id)
            self.repo._append(
                aggregates,
                sources=(current,),
                current=current,
                actor=self.actor,
                digest="a" * 64,
                label="Synthetic unsupported Work revision",
            )
        before = self.counts()
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-integrity-invalid"):
            self.repo.inspect(self.a.assertion_revision_id, resolve=self.resolve)
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-integrity-invalid"):
            self.repo.reconcile(self.fixture.address, command_id=self.a_command, actor=self.actor, resolve=self.resolve)
        self.assertEqual(before, self.counts())

    def test_old_dependents_are_blocked_atomically_while_new_decision_and_work_stay_fresh(self):
        assert self.a.work_id is not None
        with self.repo._transaction(write=True) as (_, aggregates):
            consumer = self.repo._append(
                aggregates,
                sources=(aggregates.get(self.a.work_id),),
                actor=self.actor,
                digest="1" * 64,
                kind="evidence",
                label="Synthetic dependent",
            )
        plan = self.merge_plan()
        preview = self.repo.preview_review(plan, actor=self.actor, resolve=self.resolve)
        self.assertIn(consumer.revision_id, preview.affected_output_revision_ids)
        outcome = self.commit(self.command(plan))
        factory = create_sqlite_unit_of_work_factory(self.fixture.database, self.fixture.project)
        with factory() as unit, self.assertRaises(RepositoryConflict):
            unit.require_fresh_revision(consumer.revision_id)
        with factory() as unit:
            unit.require_fresh_revision(outcome.decision_revision_id)
            for state in outcome.work_states:
                unit.require_fresh_revision(state.revision_id)
        impacts = sqlite_dependency_impact_repository(self.fixture.database.parent.parent, self.fixture.project)
        for run_id in outcome.dependency_run_ids:
            run = impacts.run(run_id)
            while run.state == "running":
                run = impacts.advance(run_id, expected_checkpoint_sha256=run.checkpoint_sha256)
        self.assertIn(consumer.revision_id, {item.output_revision_id for item in impacts.stale_states()})

    def test_large_input_manifest_keeps_actual_source_and_prior_judgment_material(self):
        with self.repo._transaction(write=True) as (connection, aggregates):
            inputs = tuple(
                self.repo._append(
                    aggregates, sources=(), actor=self.actor, digest=str(index % 10) * 64, label="Synthetic input"
                )
                for index in range(65)
            )
            judgment = self.repo._append(
                aggregates,
                sources=(),
                actor=self.actor,
                kind="decision",
                digest="a" * 64,
                label="Synthetic prior judgment",
                adjudicated=True,
            )
            derived = self.repo._append(
                aggregates,
                sources=(*inputs, judgment),
                actor=self.actor,
                digest="b" * 64,
                label="Synthetic large derivation",
            )
            changed = self.repo._append(
                aggregates,
                sources=(),
                current=inputs[0],
                actor=self.actor,
                digest="c" * 64,
                label="Synthetic corrected input",
            )
            self.repo._publish_impacts(connection, (self.repo._change(inputs[0], changed, self.actor),))
        factory = create_sqlite_unit_of_work_factory(self.fixture.database, self.fixture.project)
        with factory() as unit, self.assertRaises(RepositoryConflict):
            unit.require_fresh_revision(derived.revision_id)

        with self.repo._transaction(write=True) as (connection, aggregates):
            revised = self.repo._append(
                aggregates,
                sources=(),
                current=judgment,
                actor=self.actor,
                kind="decision",
                adjudicated=True,
                digest="d" * 64,
                label="Synthetic revised judgment",
            )
            run_ids = self.repo._publish_impacts(connection, (self.repo._change(judgment, revised, self.actor),))
            affected = connection.execute(
                "SELECT output_revision_id FROM dependency_impact_items WHERE run_id=?", (run_ids[0],)
            ).fetchall()
            self.assertIn(derived.revision_id, {row[0] for row in affected})

    def test_review_impacts_recover_from_unrelated_graph_growth_without_releasing_stale_outputs(self):
        assert self.a.work_id is not None
        with self.repo._transaction(write=True) as (_, aggregates):
            consumer = self.repo._append(
                aggregates,
                sources=(aggregates.get(self.a.work_id),),
                actor=self.actor,
                digest="1" * 64,
                kind="evidence",
                label="Synthetic dependent",
            ).revision_id
        outcome = self.commit(self.command(self.merge_plan()))
        with self.repo._transaction(write=True) as (_, aggregates):
            self.repo._append(
                aggregates,
                sources=(),
                actor=self.actor,
                digest="2" * 64,
                kind="evidence",
                label="Synthetic independent append",
            )
        self.repo = SqliteReconciliationRepository(self.fixture.database, self.fixture.project)
        factory = create_sqlite_unit_of_work_factory(self.fixture.database, self.fixture.project)
        for _ in range(4):
            with factory() as unit, self.assertRaises(RepositoryConflict):
                unit.require_fresh_revision(consumer)
            self.repo.advance_review_impacts()
        impacts = sqlite_dependency_impact_repository(self.fixture.database.parent.parent, self.fixture.project)
        self.assertIn(consumer, {item.output_revision_id for item in impacts.stale_states()})
        self.assertTrue(all(impacts.run(run_id).state != "running" for run_id in outcome.dependency_run_ids))

    def test_partial_impact_continuation_rolls_back_at_every_seam_and_recovers_after_lost_ack(self):
        assert self.a.work_id is not None
        with self.repo._transaction(write=True) as (_, aggregates):
            consumers = tuple(
                self.repo._append(
                    aggregates,
                    sources=(aggregates.get(self.a.work_id),),
                    actor=self.actor,
                    digest="1" * 64,
                    kind="evidence",
                    label="Synthetic dependent",
                ).revision_id
                for _ in range(102)
            )
        outcome = self.commit(self.command(self.merge_plan()))
        impacts = sqlite_dependency_impact_repository(self.fixture.database.parent.parent, self.fixture.project)
        root_id = next(run_id for run_id in outcome.dependency_run_ids if impacts.run(run_id).total_items >= 102)
        root = impacts.run(root_id)
        partial = impacts.advance(root_id, expected_checkpoint_sha256=root.checkpoint_sha256)
        self.assertEqual(100, partial.processed_items)
        with self.repo._transaction(write=True) as (_, aggregates):
            self.repo._append(
                aggregates,
                sources=(),
                actor=self.actor,
                digest="2" * 64,
                kind="evidence",
                label="Synthetic independent append",
            )
        factory = create_sqlite_unit_of_work_factory(self.fixture.database, self.fixture.project)
        for step in ("impact-continuation-created", "impact-continuation-linked", "impact-predecessor-cancelled"):
            with self.subTest(step=step):
                before = self.counts()

                def fail(observed, expected=step):
                    if observed == expected:
                        raise ReconciliationProblem("synthetic-continuation-interruption")

                with (
                    patch("research_observatory_core.reconciliation_repository._publication_step", side_effect=fail),
                    self.assertRaises(ReconciliationProblem),
                ):
                    self.repo.advance_review_impacts()
                self.assertEqual(before, self.counts())
                self.assertEqual(partial, impacts.run(root_id))
                with factory() as unit, self.assertRaises(RepositoryConflict):
                    unit.require_fresh_revision(consumers[-1])
        self.repo.advance_review_impacts()  # Committed continuation; caller loses acknowledgement.
        self.repo = SqliteReconciliationRepository(self.fixture.database, self.fixture.project)
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.project) as db:
            links = db.execute(
                "SELECT run_id,previous_checkpoint_sha256 FROM reconciliation_impact_continuations"
            ).fetchall()
        self.assertEqual(1, len(links))
        self.assertEqual(partial.checkpoint_sha256, links[0][1])
        self.assertEqual("cancelled", impacts.run(root_id).state)
        for _ in range(4):
            self.repo.advance_review_impacts()
        self.assertEqual("completed", impacts.run(links[0][0]).state)
        self.assertTrue(set(consumers) <= {item.output_revision_id for item in impacts.stale_states()})
        self.assertFalse(self.repo.advance_review_impacts())
        with factory() as unit, self.assertRaises(RepositoryConflict):
            unit.require_fresh_revision(consumers[-1])

    def test_continuation_rejects_substituted_semantics_checkpoint_owner_and_forks(self):
        assert self.a.work_id is not None
        with self.repo._transaction(write=True) as (_, aggregates):
            self.repo._append(
                aggregates,
                sources=(aggregates.get(self.a.work_id),),
                actor=self.actor,
                digest="1" * 64,
                kind="evidence",
                label="Synthetic dependent",
            )
        outcome = self.commit(self.command(self.merge_plan()))
        impacts = sqlite_dependency_impact_repository(self.fixture.database.parent.parent, self.fixture.project)
        root_id = next(run_id for run_id in outcome.dependency_run_ids if impacts.run(run_id).state == "running")
        root = impacts.run(root_id)
        change = impacts.change(root.change_id)
        from research_observatory_core.repositories import _SqliteDependencyImpactRepository

        adapter = _SqliteDependencyImpactRepository(self.fixture.database, self.fixture.project)
        for substituted in (
            change,
            replace(change, actor_id=new_uuid_v7()),
            replace(change, propagation_policy_version="2.0.0"),
            replace(change, reason="SOURCE_VERSION"),
        ):
            with self.subTest(change=substituted):
                change_id, child_id = new_uuid_v7(), new_uuid_v7()
                fresh = replace(substituted, change_id=change_id, idempotency_key="reconciliation-impact-" + change_id)
                with self.repo._transaction(write=True) as (db, _):
                    from research_observatory_core.ports.repositories import DEFAULT_DEPENDENCY_IMPACT_LIMITS

                    preview = adapter._preview_with_connection(
                        db, fresh, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
                    )
                    adapter._begin_with_connection(
                        db, fresh, preview_sha256=preview.preview_sha256, run_id=child_id, batch_size=100
                    )
                    checkpoint = "sha256:" + "0" * 64 if substituted == change else root.checkpoint_sha256
                    with self.assertRaises(_DATABASE_ERRORS):
                        db.execute(
                            "INSERT INTO reconciliation_impact_continuations VALUES (?,?,?,?,?,?)",
                            (root_id, self.fixture.project, 1, root_id, child_id, checkpoint),
                        )
        # Manual cancellation stays terminal and does not acquire an automatic child.
        impacts.cancel(root_id, expected_checkpoint_sha256=root.checkpoint_sha256, occurred_at=self.actor.occurred_at)
        self.assertFalse(self.repo.advance_review_impacts())
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.project) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM reconciliation_impact_continuations").fetchone()[0])

    def test_repeated_graph_growth_follows_saved_chain_without_forking_or_reviving_terminal_roots(self):
        assert self.a.work_id is not None
        with self.repo._transaction(write=True) as (_, aggregates):
            self.repo._append(
                aggregates,
                sources=(aggregates.get(self.a.work_id),),
                actor=self.actor,
                digest="1" * 64,
                kind="evidence",
                label="Synthetic dependent",
            )
        outcome = self.commit(self.command(self.merge_plan()))
        impacts = sqlite_dependency_impact_repository(self.fixture.database.parent.parent, self.fixture.project)
        root_id = next(run_id for run_id in outcome.dependency_run_ids if impacts.run(run_id).state == "running")
        previous = root_id
        for sequence in range(1, 4):
            with self.repo._transaction(write=True) as (_, aggregates):
                self.repo._append(
                    aggregates,
                    sources=(),
                    actor=self.actor,
                    digest="2" * 64,
                    kind="evidence",
                    label="Synthetic independent append",
                )
            self.assertTrue(self.repo.advance_review_impacts())
            with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.project) as db:
                links = db.execute(
                    "SELECT sequence,previous_run_id,run_id FROM reconciliation_impact_continuations "
                    "WHERE root_run_id=? ORDER BY sequence",
                    (root_id,),
                ).fetchall()
                self.assertEqual(sequence, len(links))
                self.assertEqual((sequence, previous), tuple(links[-1])[:2])
                with self.assertRaises(_DATABASE_ERRORS):
                    db.execute(
                        "INSERT INTO reconciliation_impact_continuations VALUES (?,?,?,?,?,?)",
                        (
                            root_id,
                            self.fixture.project,
                            sequence + 1,
                            previous,
                            root_id,
                            impacts.run(previous).checkpoint_sha256,
                        ),
                    )
            previous = links[-1][2]
            self.repo = SqliteReconciliationRepository(self.fixture.database, self.fixture.project)
        self.assertTrue(self.repo.advance_review_impacts())
        self.assertFalse(self.repo.advance_review_impacts())
        self.assertEqual("completed", impacts.run(previous).state)

    def test_real_graph_growth_does_not_turn_corrupted_saved_authority_into_a_continuation(self):
        assert self.a.work_id is not None
        with self.repo._transaction(write=True) as (_, aggregates):
            self.repo._append(
                aggregates,
                sources=(aggregates.get(self.a.work_id),),
                actor=self.actor,
                digest="1" * 64,
                kind="evidence",
                label="Synthetic dependent",
            )
        outcome = self.commit(self.command(self.merge_plan()))
        impacts = sqlite_dependency_impact_repository(self.fixture.database.parent.parent, self.fixture.project)
        root_id = next(run_id for run_id in outcome.dependency_run_ids if impacts.run(run_id).state == "running")
        for table, column, value in (
            ("dependency_impact_runs", "graph_sha256", "sha256:" + "0" * 64),
            ("dependency_impact_runs", "preview_sha256", "sha256:" + "0" * 64),
            ("dependency_impact_runs", "authority_sha256", "sha256:" + "0" * 64),
            ("dependency_impact_items", "path_sha256", "sha256:" + "0" * 64),
            ("dependency_impact_audit_events", "checkpoint_sha256", "sha256:" + "0" * 64),
        ):
            with self.subTest(table=table, column=column):

                def substitute(new_value, table=table, column=column):
                    with closing(sqlite3.connect(self.fixture.database)) as db, db:
                        trigger = table + "_no_update"
                        ddl = db.execute("SELECT sql FROM sqlite_schema WHERE name=?", (trigger,)).fetchone()[0]
                        prior = db.execute(f"SELECT {column} FROM {table} WHERE run_id=?", (root_id,)).fetchone()[0]
                        db.execute(f"DROP TRIGGER {trigger}")
                        db.execute(f"UPDATE {table} SET {column}=? WHERE run_id=?", (new_value, root_id))
                        db.execute(ddl)
                        return prior

                original = substitute(value)
                try:
                    before = self.counts()
                    with self.assertRaises(ReconciliationProblem):
                        self.repo.advance_review_impacts()
                    self.assertEqual(before, self.counts())
                finally:
                    substitute(original)
                if column == "graph_sha256":
                    with self.repo._transaction(write=True) as (_, aggregates):
                        self.repo._append(
                            aggregates,
                            sources=(),
                            actor=self.actor,
                            digest="2" * 64,
                            kind="evidence",
                            label="Synthetic independent append",
                        )

    def _assert_graph_effect_corruption_denies_continuation(self, *, delete: bool):
        assert self.a.work_id is not None
        with self.repo._transaction(write=True) as (_, aggregates):
            consumer = self.repo._append(
                aggregates,
                sources=(aggregates.get(self.a.work_id),),
                actor=self.actor,
                digest="1" * 64,
                kind="evidence",
                label="Synthetic dependent",
            ).revision_id
        outcome = self.commit(self.command(self.merge_plan()))
        impacts = sqlite_dependency_impact_repository(self.fixture.database.parent.parent, self.fixture.project)
        root_id = next(run_id for run_id in outcome.dependency_run_ids if impacts.run(run_id).state == "running")
        before_run = impacts.run(root_id)
        with closing(sqlite3.connect(self.fixture.database)) as db, db:
            trigger = "material_dependencies_no_delete" if delete else "material_dependencies_no_update"
            ddl = db.execute("SELECT sql FROM sqlite_schema WHERE name=?", (trigger,)).fetchone()[0]
            db.execute("DROP TRIGGER " + trigger)
            sql = (
                "DELETE FROM material_dependencies"
                if delete
                else "UPDATE material_dependencies SET relation_type='non-material'"
            )
            changed = db.execute(
                sql + " WHERE dependency_revision_id=? AND output_revision_id=?", (self.a.work_revision_id, consumer)
            )
            self.assertEqual(1, changed.rowcount)
            db.execute(ddl)
        before = self.counts()
        with self.assertRaises(ReconciliationProblem):
            self.repo.advance_review_impacts()
        self.assertEqual(before, self.counts())
        self.assertEqual(before_run, impacts.run(root_id))
        factory = create_sqlite_unit_of_work_factory(self.fixture.database, self.fixture.project)
        with factory() as unit, self.assertRaises(RepositoryConflict):
            unit.require_fresh_revision(consumer)

    def test_removed_material_edge_cannot_discard_pending_effect_in_a_continuation(self):
        self._assert_graph_effect_corruption_denies_continuation(delete=True)

    def test_weakened_material_edge_cannot_discard_pending_effect_in_a_continuation(self):
        self._assert_graph_effect_corruption_denies_continuation(delete=False)
