"""Version choices and sourced warnings preserve history and atomic stale intent."""

import hashlib
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportRights
from research_observatory_core.ports.repositories import RepositoryConflict
from research_observatory_core.reconciliation.contracts import ReconciliationProblem
from research_observatory_core.reconciliation.decisions import AliasPlan, ReviewPlan, SourcePartition
from research_observatory_core.reconciliation.versions import (
    UpdateRelationDraft,
    VersionCommand,
    VersionDate,
    VersionDefinition,
    VersionEvidence,
    VersionPlan,
    VersionReference,
)
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
)
from research_observatory_core.storage import open_canonical_database

from tests.reconciliation import test_review_repository as fixtures


class VersionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ReviewRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.repo, self.actor, self.resolve = self.f.repo, self.f.actor, self.f.resolve
        assert self.f.a.work_id is not None and self.f.b.work_id is not None
        self.work_ids = tuple(sorted((self.f.a.work_id, self.f.b.work_id)))

    def context(self):
        return self.repo.version_context(self.work_ids, resolve=self.resolve)

    def plan(self, action, **values):
        work_ids = values.pop("work_ids", self.work_ids)
        context = self.repo.version_context(work_ids, resolve=self.resolve)
        return VersionPlan(
            action=action,
            work_ids=work_ids,
            context_sha256=context.fingerprint,
            rationale="Synthetic human version decision",
            **values,
        )

    def command(self, plan):
        preview = self.repo.preview_versions(plan, actor=self.actor, resolve=self.resolve)
        return VersionCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256)

    def commit(self, command):
        return self.repo.decide_versions(command, actor=self.actor, resolve=self.resolve)

    def register(self, assertion, kind):
        outcome = self.commit(
            self.command(
                self.plan(
                    "register",
                    definition=VersionDefinition(
                        kind=kind,
                        assertion_revision_ids=(assertion,),
                        date=VersionDate(precision="not-reported", value=None),
                    ),
                )
            )
        )
        return outcome.version_revisions[0]

    def relation(self, source, target, *, kind="corrects"):
        assertion = self.repo.inspect(self.f.b.assertion_revision_id, resolve=self.resolve).assertion
        identifier = assertion.identifiers[0]
        evidence = VersionEvidence(
            assertion_revision_id=self.f.b.assertion_revision_id,
            category="identifier",
            selector=identifier.source_selector,
            value_sha256=hashlib.sha256(identifier.observed.encode()).hexdigest(),
        )
        return UpdateRelationDraft(
            kind=kind,
            source=source,
            target=target,
            evidence=(evidence,),
            date=VersionDate(precision="year", value="2026"),
            knowledge_status="adjudicated",
        )

    def test_concurrent_version_decisions_have_one_winner_and_preserve_the_losing_draft(self):
        version = self.register(self.f.a.assertion_revision_id, "version-of-record")
        first = self.command(self.plan("prefer", work_ids=(self.f.a.work_id,), version=version))
        second = first.model_copy(update={"command_id": new_uuid_v7()})

        def submit(command):
            try:
                return self.commit(command)
            except ReconciliationProblem as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(submit, (first, second)))
        self.assertEqual(1, sum(isinstance(item, ReconciliationProblem) for item in results))
        self.assertEqual(1, len(self.context().preferences))
        winner = next(
            command
            for command, result in zip((first, second), results, strict=True)
            if not isinstance(result, ReconciliationProblem)
        )
        self.assertEqual(
            next(result for result in results if not isinstance(result, ReconciliationProblem)), self.commit(winner)
        )

    def test_all_sourced_notice_kinds_and_version_cycles_preserve_exact_history(self):
        target = self.register(self.f.a.assertion_revision_id, "preprint")
        accepted = self.register(self.f.b.assertion_revision_id, "accepted-manuscript")
        self.commit(self.command(self.plan("relate", relation=self.relation(accepted, target, kind="supersedes"))))
        versions = {
            item.version_id: VersionReference(version_id=item.version_id, revision_id=item.revision_id)
            for item in self.context().versions
        }
        before = self.f.counts()
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-version-cycle"):
            self.command(
                self.plan(
                    "relate",
                    relation=self.relation(
                        versions[target.version_id], versions[accepted.version_id], kind="is-version-of"
                    ),
                )
            )
        self.assertEqual(before, self.f.counts())
        for notice_kind, relation_kind in (
            ("erratum", "erratum-for"),
            ("correction", "corrects"),
            ("expression-of-concern", "expresses-concern"),
            ("retraction", "retracts"),
        ):
            with self.subTest(kind=notice_kind):
                notice = self.register(self.f.b.assertion_revision_id, notice_kind)
                current = next(item for item in self.context().versions if item.version_id == target.version_id)
                relation = self.relation(
                    notice,
                    VersionReference(version_id=current.version_id, revision_id=current.revision_id),
                    kind=relation_kind,
                )
                self.commit(
                    self.command(
                        self.plan("relate", relation=relation.model_copy(update={"knowledge_status": "disputed"}))
                    )
                )
                self.assertEqual(
                    "preprint", self.repo.inspect_version(target.revision_id, resolve=self.resolve).definition.kind
                )
        context = self.context()
        self.assertEqual(
            {"supersedes", "erratum-for", "corrects", "expresses-concern", "retracts"},
            {item.assertion.kind for item in context.relations},
        )
        self.assertEqual(4, sum(item.assertion.knowledge_status == "disputed" for item in context.relations))
        before = self.f.counts()
        versions = {
            item.version_id: VersionReference(version_id=item.version_id, revision_id=item.revision_id)
            for item in context.versions
        }
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-version-notice-kind-invalid"):
            self.command(
                self.plan(
                    "relate",
                    relation=self.relation(versions[accepted.version_id], versions[target.version_id], kind="retracts"),
                )
            )
        self.assertEqual(before, self.f.counts())

    def test_version_owned_partial_impacts_recover_after_growth_and_cancellation_stays_terminal(self):
        target = self.register(self.f.a.assertion_revision_id, "version-of-record")
        source = self.register(self.f.b.assertion_revision_id, "correction")
        # Drain earlier unrelated version registration intents before this boundary.
        for _ in range(8):
            if not self.repo.advance_review_impacts():
                break
        with self.repo._transaction(write=True) as (_, aggregates):
            consumers = tuple(
                self.repo._append(
                    aggregates,
                    sources=(aggregates.get_revision(target.revision_id),),
                    actor=self.actor,
                    digest="3" * 64,
                    kind="evidence",
                    label="Synthetic version consumer",
                ).revision_id
                for _ in range(102)
            )
        outcome = self.commit(self.command(self.plan("relate", relation=self.relation(source, target))))
        impacts = sqlite_dependency_impact_repository(self.f.fixture.database.parent.parent, self.f.fixture.project)
        root_id = next(run_id for run_id in outcome.dependency_run_ids if impacts.run(run_id).total_items >= 102)
        root = impacts.run(root_id)
        partial = impacts.advance(root_id, expected_checkpoint_sha256=root.checkpoint_sha256)
        self.assertEqual(100, partial.processed_items)
        with self.repo._transaction(write=True) as (_, aggregates):
            self.repo._append(
                aggregates,
                sources=(),
                actor=self.actor,
                digest="4" * 64,
                kind="evidence",
                label="Synthetic independent graph growth",
            )
        factory = create_sqlite_unit_of_work_factory(self.f.fixture.database, self.f.fixture.project)
        for step in ("impact-continuation-created", "impact-continuation-linked", "impact-predecessor-cancelled"):
            with self.subTest(step=step):
                before = self.f.counts()

                def fail(observed, expected=step):
                    if observed == expected:
                        raise ReconciliationProblem("synthetic-version-impact-interruption")

                with (
                    patch("research_observatory_core.reconciliation_repository._publication_step", side_effect=fail),
                    self.assertRaises(ReconciliationProblem),
                ):
                    self.repo.advance_review_impacts()
                self.assertEqual(before, self.f.counts())
                self.assertEqual(partial, impacts.run(root_id))
                with factory() as unit, self.assertRaises(RepositoryConflict):
                    unit.require_fresh_revision(consumers[-1])
        self.repo.advance_review_impacts()
        self.repo = SqliteReconciliationRepository(self.f.fixture.database, self.f.fixture.project)
        for _ in range(12):
            if not self.repo.advance_review_impacts():
                break
        self.assertTrue(set(consumers) <= {item.output_revision_id for item in impacts.stale_states()})
        with open_canonical_database(self.f.fixture.database, expected_project_id=self.f.fixture.project) as db:
            child = db.execute(
                "SELECT run_id FROM reconciliation_impact_continuations WHERE root_run_id=?", (root_id,)
            ).fetchone()[0]
        self.assertEqual("completed", impacts.run(child).state)
        self.assertEqual("cancelled", impacts.run(root_id).state)
        current = next(item for item in self.context().versions if item.version_id == target.version_id)
        with self.repo._transaction(write=True) as (_, aggregates):
            consumer = self.repo._append(
                aggregates,
                sources=(aggregates.get_revision(current.revision_id),),
                actor=self.actor,
                digest="5" * 64,
                kind="evidence",
                label="Synthetic cancelled consumer",
            ).revision_id
        revised = self.commit(
            self.command(
                self.plan(
                    "revise",
                    version=VersionReference(version_id=current.version_id, revision_id=current.revision_id),
                    definition=current.definition.model_copy(
                        update={"date": VersionDate(precision="year", value="2025")}
                    ),
                )
            )
        )
        for run_id in revised.dependency_run_ids:
            run = impacts.run(run_id)
            if run.state == "running":
                impacts.cancel(
                    run_id, expected_checkpoint_sha256=run.checkpoint_sha256, occurred_at=self.actor.occurred_at
                )
        self.assertFalse(self.repo.advance_review_impacts())
        with factory() as unit, self.assertRaises(RepositoryConflict):
            unit.require_fresh_revision(consumer)

    def test_correction_keeps_historical_preference_and_immediately_denies_dependent_reuse(self):
        original = self.register(self.f.a.assertion_revision_id, "preprint")
        notice = self.register(self.f.b.assertion_revision_id, "correction")
        preferred = self.commit(self.command(self.plan("prefer", work_ids=(self.f.a.work_id,), version=original)))
        with self.repo._transaction(write=True) as (_, aggregates):
            consumer = self.repo._append(
                aggregates,
                sources=(aggregates.get_revision(original.revision_id),),
                actor=self.actor,
                digest="1" * 64,
                kind="evidence",
                label="Synthetic version consumer",
            )
            unaffected = self.repo._append(
                aggregates,
                sources=(),
                actor=self.actor,
                digest="2" * 64,
                kind="evidence",
                label="Synthetic unrelated output",
            )
        command = self.command(self.plan("relate", relation=self.relation(notice, original)))
        outcome = self.commit(command)
        self.assertEqual(outcome, self.commit(command))
        factory = create_sqlite_unit_of_work_factory(self.f.fixture.database, self.f.fixture.project)
        with factory() as unit, self.assertRaises(RepositoryConflict):
            unit.require_fresh_revision(consumer.revision_id)
        with factory() as unit:
            unit.require_fresh_revision(unaffected.revision_id)
        context = self.context()
        self.assertEqual(1, len(context.relations))
        self.assertEqual("corrects", context.relations[0].assertion.kind)
        self.assertEqual(original, context.relations[0].assertion.target)
        current = next(item for item in context.versions if item.version_id == original.version_id)
        self.assertNotEqual(original.revision_id, current.revision_id)
        self.assertEqual(original.revision_id, current.previous_revision_id)
        self.assertEqual(preferred.preference_revision_id, context.preferences[0].revision_id)
        self.assertEqual(original, context.preferences[0].selected)
        historical = self.repo.inspect_version(original.revision_id, resolve=self.resolve)
        self.assertEqual("preprint", historical.definition.kind)
        self.repo = SqliteReconciliationRepository(self.f.fixture.database, self.f.fixture.project)
        for _ in range(12):
            if not self.repo.advance_review_impacts():
                break
        self.assertFalse(self.repo.advance_review_impacts())
        impacts = sqlite_dependency_impact_repository(self.f.fixture.database.parent.parent, self.f.fixture.project)
        self.assertIn(consumer.revision_id, {item.output_revision_id for item in impacts.stale_states()})
        self.assertEqual(context, self.context())

    def test_changed_command_actor_context_source_and_rights_deny_without_publication(self):
        version = self.register(self.f.a.assertion_revision_id, "version-of-record")
        command = self.command(self.plan("prefer", work_ids=(self.f.a.work_id,), version=version))
        self.commit(command)
        before = self.f.counts()
        with self.assertRaises(ReconciliationProblem):
            self.commit(command.model_copy(update={"command_id": new_uuid_v7()}))
        with self.assertRaises(ReconciliationProblem):
            self.repo.decide_versions(command, actor=replace(self.actor, actor_id=new_uuid_v7()), resolve=self.resolve)
        with self.assertRaises(ReconciliationProblem):
            self.commit(
                command.model_copy(update={"plan": command.plan.model_copy(update={"rationale": "Changed decision"})})
            )
        self.f.fixture.resolved[self.f.fixture.address.revision_id] = self.f.fixture.source.model_copy(
            update={"rights": ImportRights()}
        )
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-rights-denied"):
            self.commit(command)
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-rights-denied"):
            self.repo.inspect_version(version.revision_id, resolve=self.resolve)
        self.assertEqual(before, self.f.counts())

    def test_sourced_relation_rejects_substituted_field_digest_and_revision(self):
        target = self.register(self.f.a.assertion_revision_id, "version-of-record")
        source = self.register(self.f.b.assertion_revision_id, "retraction")
        relation = self.relation(source, target, kind="retracts")
        before = self.f.counts()
        for forged in (
            relation.model_copy(
                update={"target": VersionReference(version_id=target.version_id, revision_id=new_uuid_v7())}
            ),
            relation.model_copy(
                update={"evidence": (relation.evidence[0].model_copy(update={"value_sha256": "0" * 64}),)}
            ),
            relation.model_copy(
                update={"evidence": (relation.evidence[0].model_copy(update={"selector": "foreign-selector"}),)}
            ),
        ):
            with self.subTest(), self.assertRaises(ReconciliationProblem):
                self.command(self.plan("relate", relation=forged))
        self.assertEqual(before, self.f.counts())

    def test_every_publication_seam_rolls_back_then_identical_command_can_commit(self):
        target = self.register(self.f.a.assertion_revision_id, "version-of-record")
        source = self.register(self.f.b.assertion_revision_id, "retraction")
        command = self.command(self.plan("relate", relation=self.relation(source, target, kind="retracts")))
        for step in (
            "version-decision-created",
            "version-facts-created",
            "version-work-created",
            "version-preference-created",
            "version-impacts-created",
            "version-command-created",
        ):
            with self.subTest(step=step):
                before = self.f.counts()

                def fail(observed, expected=step):
                    if observed == expected:
                        raise ReconciliationProblem("synthetic-version-interruption")

                with (
                    patch("research_observatory_core.reconciliation_repository._publication_step", side_effect=fail),
                    self.assertRaises(ReconciliationProblem),
                ):
                    self.commit(command)
                self.assertEqual(before, self.f.counts())
        outcome = self.commit(command)
        self.assertEqual(outcome, self.commit(command))

    def test_preference_state_stays_explicit_and_reselecting_retracted_version_keeps_warning(self):
        target = self.register(self.f.a.assertion_revision_id, "version-of-record")
        source = self.register(self.f.b.assertion_revision_id, "retraction")
        initial = self.context()
        self.assertTrue(all(item.state == "not-reported" for item in initial.preference_states))
        preferred = self.commit(self.command(self.plan("prefer", work_ids=(self.f.a.work_id,), version=target)))
        self.assertEqual(
            "current", next(item for item in self.context().preference_states if item.work_id == self.f.a.work_id).state
        )
        self.commit(self.command(self.plan("relate", relation=self.relation(source, target, kind="retracts"))))
        context = self.context()
        self.assertEqual(
            "requires-review",
            next(item for item in context.preference_states if item.work_id == self.f.a.work_id).state,
        )
        current = next(item for item in context.versions if item.version_id == target.version_id)
        refreshed = self.commit(
            self.command(
                self.plan(
                    "prefer",
                    work_ids=(self.f.a.work_id,),
                    version=VersionReference(version_id=current.version_id, revision_id=current.revision_id),
                    previous_preference_revision_id=preferred.preference_revision_id,
                )
            )
        )
        context = self.context()
        self.assertEqual(
            "current", next(item for item in context.preference_states if item.work_id == self.f.a.work_id).state
        )
        self.assertEqual("retracts", context.relations[0].assertion.kind)
        self.assertEqual(2, len(context.preferences))
        self.assertEqual(preferred.preference_revision_id, context.preferences[-1].previous_revision_id)
        self.assertEqual(refreshed.preference_revision_id, context.preferences[-1].revision_id)

    def test_current_version_inspection_rechecks_rights_of_supporting_notice(self):
        target = self.register(self.f.a.assertion_revision_id, "version-of-record")
        source = self.register(self.f.b.assertion_revision_id, "retraction")
        self.commit(self.command(self.plan("relate", relation=self.relation(source, target, kind="retracts"))))
        current = next(item for item in self.context().versions if item.version_id == target.version_id)
        self.f.fixture.resolved[self.f.b_address.revision_id] = self.f.fixture.resolved[
            self.f.b_address.revision_id
        ].model_copy(update={"rights": ImportRights()})
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-rights-denied"):
            self.repo.inspect_version(current.revision_id, resolve=self.resolve)

    def test_identical_retry_rechecks_all_original_decision_support(self):
        command = self.command(
            self.plan(
                "register",
                definition=VersionDefinition(
                    kind="preprint",
                    assertion_revision_ids=(self.f.a.assertion_revision_id,),
                    date=VersionDate(precision="unknown", value=None),
                ),
            )
        )
        self.commit(command)
        before = self.f.counts()
        self.f.fixture.resolved[self.f.b_address.revision_id] = self.f.fixture.resolved[
            self.f.b_address.revision_id
        ].model_copy(update={"rights": ImportRights()})
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-rights-denied"):
            self.commit(command)
        self.assertEqual(before, self.f.counts())

    def test_merge_then_split_retains_competing_preferences_and_unresolved_manifestation(self):
        assert self.f.a.work_id is not None and self.f.b.work_id is not None
        first = self.register(self.f.a.assertion_revision_id, "preprint")
        second = self.register(self.f.b.assertion_revision_id, "version-of-record")
        preferences = []
        for work_id, version in ((self.f.a.work_id, first), (self.f.b.work_id, second)):
            preferences.append(
                self.commit(
                    self.command(self.plan("prefer", work_ids=(work_id,), version=version))
                ).preference_revision_id
            )
        self.f.commit(self.f.command(self.f.merge_plan()))
        self.work_ids = (self.f.a.work_id,)
        context = self.context()
        self.assertEqual(set(preferences), {item.revision_id for item in context.preferences})
        self.assertEqual("requires-review", context.preference_states[0].state)
        combined = self.commit(
            self.command(
                self.plan(
                    "register",
                    definition=VersionDefinition(
                        kind="accepted-manuscript",
                        assertion_revision_ids=tuple(
                            sorted((self.f.a.assertion_revision_id, self.f.b.assertion_revision_id))
                        ),
                        date=VersionDate(precision="unknown", value=None),
                    ),
                )
            )
        ).version_revisions[0]
        review = self.f.context(self.work_ids)
        split = ReviewPlan(
            action="split",
            works=review.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(
                    group="retained",
                    existing_work_id=self.f.a.work_id,
                    assertion_revision_ids=(self.f.a.assertion_revision_id,),
                ),
                SourcePartition(
                    group="separated", existing_work_id=None, assertion_revision_ids=(self.f.b.assertion_revision_id,)
                ),
            ),
            aliases=(
                AliasPlan(
                    work_id=self.f.b.work_id,
                    revision_id=review.inbound_aliases[0].revision_id,
                    target_group="separated",
                ),
            ),
            conflict_disposition="retain-all",
            evidence_sha256=review.fingerprint,
            rationale="Synthetic split of source membership",
        )
        separated = self.f.commit(self.f.command(split))
        self.work_ids = tuple(sorted(item.work_id for item in separated.work_states if item.disposition == "active"))
        self.repo = SqliteReconciliationRepository(self.f.fixture.database, self.f.fixture.project)
        context = self.context()
        placement = next(item for item in context.placements if item.version_id == combined.version_id)
        self.assertEqual("requires-review", placement.state)
        self.assertEqual(self.work_ids, placement.work_ids)
        self.assertEqual(set(preferences), {item.revision_id for item in context.preferences})
        self.assertEqual(3, len(context.versions))
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-version-membership-invalid"):
            self.command(
                self.plan(
                    "prefer",
                    work_ids=(self.f.a.work_id,),
                    version=combined,
                    previous_preference_revision_id=preferences[0],
                )
            )
        self.assertEqual(
            "accepted-manuscript", self.repo.inspect_version(combined.revision_id, resolve=self.resolve).definition.kind
        )

    def test_restoring_original_partition_does_not_reactivate_old_preference(self):
        assert self.f.a.work_id is not None and self.f.b.work_id is not None
        version = self.register(self.f.a.assertion_revision_id, "version-of-record")
        preferred = self.commit(self.command(self.plan("prefer", work_ids=(self.f.a.work_id,), version=version)))
        self.f.commit(self.f.command(self.f.merge_plan()))
        review = self.f.context((self.f.a.work_id,))
        split = ReviewPlan(
            action="split",
            works=review.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(
                    group="retained",
                    existing_work_id=self.f.a.work_id,
                    assertion_revision_ids=(self.f.a.assertion_revision_id,),
                ),
                SourcePartition(
                    group="separated", existing_work_id=None, assertion_revision_ids=(self.f.b.assertion_revision_id,)
                ),
            ),
            aliases=(
                AliasPlan(
                    work_id=self.f.b.work_id,
                    revision_id=review.inbound_aliases[0].revision_id,
                    target_group="separated",
                ),
            ),
            conflict_disposition="retain-all",
            evidence_sha256=review.fingerprint,
            rationale="Restore original membership without changing scholarly preference",
        )
        self.f.commit(self.f.command(split))
        self.repo = SqliteReconciliationRepository(self.f.fixture.database, self.f.fixture.project)
        self.work_ids = (self.f.a.work_id,)
        context = self.context()
        self.assertEqual("requires-review", context.preference_states[0].state)
        self.assertEqual(preferred.preference_revision_id, context.preference_states[0].preference_revision_id)
        self.commit(
            self.command(
                self.plan("prefer", version=version, previous_preference_revision_id=preferred.preference_revision_id)
            )
        )
        self.assertEqual("current", self.context().preference_states[0].state)

    def test_preference_consumer_is_denied_atomically_when_work_membership_changes(self):
        version = self.register(self.f.a.assertion_revision_id, "version-of-record")
        preferred = self.commit(self.command(self.plan("prefer", work_ids=(self.f.a.work_id,), version=version)))
        with self.repo._transaction(write=True) as (_, aggregates):
            consumer = self.repo._append(
                aggregates,
                sources=(aggregates.get_revision(preferred.preference_revision_id),),
                actor=self.actor,
                digest="8" * 64,
                kind="evidence",
                label="Synthetic citable preference consumer",
            )
        self.f.commit(self.f.command(self.f.merge_plan()))
        factory = create_sqlite_unit_of_work_factory(self.f.fixture.database, self.f.fixture.project)
        with factory() as unit, self.assertRaises(RepositoryConflict):
            unit.require_fresh_revision(consumer.revision_id)
        self.repo = SqliteReconciliationRepository(self.f.fixture.database, self.f.fixture.project)
        for _ in range(20):
            if not self.repo.advance_review_impacts():
                break
        impacts = sqlite_dependency_impact_repository(self.f.fixture.database.parent.parent, self.f.fixture.project)
        self.assertIn(consumer.revision_id, {item.output_revision_id for item in impacts.stale_states()})

    def test_preference_reselection_rollback_preserves_fresh_consumer_then_retry_recovers_impacts(self):
        assert self.f.a.work_id is not None
        version = self.register(self.f.a.assertion_revision_id, "preprint")
        self.work_ids = (self.f.a.work_id,)
        first = self.commit(self.command(self.plan("prefer", version=version)))
        with self.repo._transaction(write=True) as (_, aggregates):
            consumer = self.repo._append(
                aggregates,
                sources=(aggregates.get_revision(first.preference_revision_id),),
                actor=self.actor,
                digest="9" * 64,
                kind="evidence",
                label="Synthetic preference-only consumer",
            )
        command = self.command(
            self.plan("prefer", version=version, previous_preference_revision_id=first.preference_revision_id)
        )
        factory = create_sqlite_unit_of_work_factory(self.f.fixture.database, self.f.fixture.project)
        for step in (
            "version-work-created",
            "version-preference-created",
            "version-impacts-created",
            "version-command-created",
        ):
            before = self.f.counts()

            def fail(observed, expected=step):
                if observed == expected:
                    raise ReconciliationProblem("synthetic-preference-interruption")

            with (
                self.subTest(step=step),
                patch(
                    "research_observatory_core.reconciliation_repository._publication_step", side_effect=fail
                ) as injected,
                self.assertRaises(ReconciliationProblem),
            ):
                self.commit(command)
            injected.assert_any_call(step)
            self.assertEqual(before, self.f.counts())
            with factory() as unit:
                unit.require_fresh_revision(consumer.revision_id)
        result = self.commit(command)
        self.assertEqual(result, self.commit(command))
        self.repo = SqliteReconciliationRepository(self.f.fixture.database, self.f.fixture.project)
        for _ in range(20):
            if not self.repo.advance_review_impacts():
                break
        self.assertFalse(self.repo.advance_review_impacts())
        impacts = sqlite_dependency_impact_repository(self.f.fixture.database.parent.parent, self.f.fixture.project)
        self.assertIn(consumer.revision_id, {item.output_revision_id for item in impacts.stale_states()})
