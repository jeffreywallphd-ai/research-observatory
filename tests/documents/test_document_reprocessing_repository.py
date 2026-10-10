"""Actual encrypted reparse authority and publication; authored parser output."""

import sys
import unittest
from contextlib import closing
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_corrections import (  # noqa: E402
    CorrectionAcceptance,
    CorrectionPatch,
    CorrectionSave,
    RelabelCorrection,
    value_sha256,
)
from research_observatory_core.document_reprocessing import (  # noqa: E402
    ReprocessingAcceptance,
    ReprocessingCancel,
    ReprocessingContinue,
    ReprocessingCreate,
    ReprocessingMapping,
    ReprocessingReconcile,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.ports.repositories import AggregateRevisionDraft, MaterialDependency  # noqa: E402
from research_observatory_core.repositories import _projection_content_sha256  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.documents import test_document_revision_repository as fixtures  # noqa: E402


class DocumentReprocessingRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_ordinary_new_replacement_is_denied_but_initial_accept_and_historical_replay_work(self):
        f = self.f
        initial = f.parse()
        command = f.command(initial)
        base = f.repository.accept(command)
        replacement = f.parse("New authored reparse")
        before = f.counts()
        with self.assertRaises(fixtures.DocumentRevisionProblem):
            f.repository.accept(f.command(replacement, expected=base.revision_id))
        self.assertEqual(before, f.counts())
        self.assertEqual(base, f.reopen().accept(command))
        self.assertEqual(base, f.reopen().read(base.revision_id))

    def batch(self, base, receipt):
        f = self.f
        with closing(open_canonical_database(f.database, expected_project_id=f.f.source.project_id)) as db:
            inputs = f.repository._input(db, receipt.binding.attempt.job_id)
        command = ReprocessingCreate(command_id=new_uuid_v7(), base_revision_ids=(base.revision_id,))
        return f.repository.reprocessing().create(command, input_factory=lambda _base: inputs)

    def test_preview_leaves_head_unchanged_and_explicit_accept_reopens_with_fresh_ids(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        receipt = f.parse("Different authored reparse")
        repo = f.repository.reprocessing()
        batch = self.batch(base, receipt)
        before = f.counts()["document_normalized_revisions"]
        page = repo.compare(batch.batch_revision_id, batch.items[0].item_id)
        self.assertEqual(before, f.counts()["document_normalized_revisions"])
        self.assertEqual(base, f.reopen().read(base.revision_id))
        page = repo.reconcile(
            ReprocessingReconcile(
                command_id=new_uuid_v7(),
                comparison_revision_id=page.comparison_revision_id,
                expected_plan_revision_id=None,
                rationale="Explicitly reviewed this uncorrected reparse",
                mappings=(),
            )
        )
        accepted = repo.accept(
            ReprocessingAcceptance(
                command_id=new_uuid_v7(),
                plan_revision_id=page.plan_revision_id,
                expected_current_revision_id=base.revision_id,
                confirmation_sha256=page.confirmation_sha256,
                expected_graph_sha256=page.impact.graph_sha256,
                decision="accept-reparse",
            )
        )
        new = f.reopen().read(accepted.revision_id)
        self.assertEqual(base.revision_id, new.previous_revision_id)
        self.assertTrue(
            {m.canonical_id for m in base.element_identities}.isdisjoint(m.canonical_id for m in new.element_identities)
        )
        self.assertEqual(base, f.reopen().read(base.revision_id))

    def corrected(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        node = base.structure.nodes[0]
        correction = f.repository.corrections()
        draft = correction.save(
            CorrectionSave(
                command_id=new_uuid_v7(),
                draft_id=None,
                expected_draft_revision_id=None,
                patch=CorrectionPatch(
                    base_revision_id=base.revision_id,
                    expected_structure_sha256=base.structure_sha256,
                    operations=(
                        RelabelCorrection(
                            op="relabel",
                            node_id=node.node_id,
                            expected_node_sha256=value_sha256(node),
                            label="Retained human label",
                        ),
                    ),
                ),
                rationale="Original researcher's retained rationale",
            )
        )
        corrected = correction.accept(
            CorrectionAcceptance(
                command_id=new_uuid_v7(),
                draft_revision_id=draft.revision_id,
                expected_current_revision_id=base.revision_id,
                confirmation_sha256=value_sha256(draft),
                decision="accept-correction",
            )
        )
        return base, draft, corrected

    def ready(self, base, receipt):
        repo = self.f.repository.reprocessing()
        batch = self.batch(base, receipt)
        page = repo.compare(batch.batch_revision_id, batch.items[0].item_id)
        mappings = [
            {
                "obligationId": o.obligation_id,
                "nodeId": page.candidate_nodes[o.operation_index].node_id,
                "relatedNodeId": None,
                "referenceId": None,
            }
            for o in page.obligations
        ]
        page = repo.reconcile(
            ReprocessingReconcile.model_validate(
                {
                    "commandId": new_uuid_v7(),
                    "comparisonRevisionId": page.comparison_revision_id,
                    "expectedPlanRevisionId": None,
                    "rationale": "Current human explicitly maps retained decisions to the new receipt",
                    "mappings": mappings,
                }
            )
        )
        command = ReprocessingAcceptance(
            command_id=new_uuid_v7(),
            plan_revision_id=page.plan_revision_id,
            expected_current_revision_id=base.revision_id,
            confirmation_sha256=page.confirmation_sha256,
            expected_graph_sha256=page.impact.graph_sha256,
            decision="accept-reparse",
        )
        return repo, batch, page, command

    def test_corrected_reparse_preserves_original_author_history_and_literal_verifier(self):
        f = self.f
        _machine, old_draft, base = self.corrected()
        original = base.model_dump_json()
        receipt = f.parse("New authored corrected reparse")
        repo, batch, _page, command = self.ready(base, receipt)
        accepted = repo.accept(command)
        final = f.reopen().read(accepted.revision_id)
        self.assertEqual(accepted.machine_revision_id, final.previous_revision_id)
        metadata = f.reopen().corrections().metadata(final.revision_id)
        self.assertEqual("Retained human label", metadata.labels[0].label)
        self.assertEqual(original, f.reopen().read(base.revision_id).model_dump_json())
        self.assertEqual(old_draft, f.reopen().corrections().read(old_draft.revision_id))
        before = f.counts()
        self.assertEqual(accepted, f.reopen().reprocessing().accept(command))
        self.assertEqual(before, f.counts())
        self.assertEqual(
            accepted, f.reopen().reprocessing().read_impact(batch.batch_revision_id, batch.items[0].item_id)
        )

    def test_each_inner_publication_interruption_rolls_back_all_canonical_facts(self):
        f = self.f
        _machine, _draft, base = self.corrected()
        repo, _batch, _page, command = self.ready(base, f.parse("Atomic interruption witness"))
        before = f.counts()
        for boundary in (
            "reprocessing-outer-complete",
            "reprocessing-decision-complete",
            "reprocessing-accepted-complete",
            "reprocessing-draft-complete",
            "reprocessing-impact-complete",
        ):

            def fail(observed, boundary=boundary):
                if observed == boundary:
                    raise RuntimeError("authored precommit interruption")

            with (
                self.subTest(boundary=boundary),
                patch("research_observatory_core.document_revision_repository._publication_step", side_effect=fail),
                self.assertRaises(fixtures.DocumentRevisionProblem),
            ):
                repo.accept(command)
            self.assertEqual(before, f.counts())
            self.assertEqual(base, f.reopen().read(base.revision_id))
        self.assertIsNotNone(repo.accept(command))

    def test_authentic_same_source_other_job_output_cannot_substitute_comparison(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        a, b = f.parse("Same authored output"), f.parse("Same authored output")
        batch = self.batch(base, a)
        before = f.counts()
        queue_type = type(f.repository.queue)
        observed = queue_type._accepted_status_with_connection

        def substitute(queue, connection, job_id):
            job, output = observed(queue, connection, job_id)
            if job_id == a.binding.attempt.job_id:
                output = observed(queue, connection, b.binding.attempt.job_id)[1]
            return job, output

        with (
            patch.object(queue_type, "_accepted_status_with_connection", substitute),
            self.assertRaises(fixtures.DocumentRevisionProblem),
        ):
            f.repository.reprocessing().compare(batch.batch_revision_id, batch.items[0].item_id)
        self.assertEqual(before, f.counts())

    def test_cancellation_retains_acceptance_and_historical_impact_from_successor(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        repo, batch, _page, command = self.ready(base, f.parse("Accepted before batch cancellation"))
        accepted = repo.accept(command)
        cancellation = ReprocessingCancel(command_id=new_uuid_v7(), batch_revision_id=batch.batch_revision_id)
        cancelled = repo.cancel(cancellation)
        self.assertEqual("cancelled", cancelled.state)
        self.assertEqual("accepted", cancelled.items[0].state)
        self.assertEqual(accepted.revision_id, cancelled.items[0].accepted_revision_id)
        before = f.counts()
        self.assertEqual(cancelled, f.reopen().reprocessing().cancel(cancellation))
        self.assertEqual(before, f.counts())
        self.assertEqual(
            accepted, f.reopen().reprocessing().read_impact(cancelled.batch_revision_id, cancelled.items[0].item_id)
        )
        historical = f.reopen().reprocessing().read(batch.batch_revision_id)
        self.assertEqual(batch.batch_revision_id, historical.batch_revision_id)
        self.assertEqual("active", historical.state)
        self.assertEqual("accepted", historical.items[0].state)

    def test_omission_changed_confirmation_and_current_head_cas_refuse(self):
        f = self.f
        _machine, _draft, base = self.corrected()
        receipt = f.parse("Exact obligations witness")
        batch = self.batch(base, receipt)
        repo = f.repository.reprocessing()
        page = repo.compare(batch.batch_revision_id, batch.items[0].item_id, offset=100_000)
        self.assertEqual(1, page.unresolved_count)
        self.assertEqual(1, len(page.obligations))
        before = f.counts()
        with self.assertRaises(fixtures.DocumentRevisionProblem):
            repo.reconcile(
                ReprocessingReconcile(
                    command_id=new_uuid_v7(),
                    comparison_revision_id=page.comparison_revision_id,
                    expected_plan_revision_id=None,
                    rationale="Omission refuses",
                    mappings=(),
                )
            )
        self.assertEqual(before, f.counts())
        from research_observatory_core.document_reprocessing import ReprocessingMapping

        full = repo.compare(batch.batch_revision_id, batch.items[0].item_id)
        mapping = ReprocessingMapping(
            obligation_id=full.obligations[0].obligation_id,
            node_id=full.candidate_nodes[0].node_id,
            related_node_id=None,
            reference_id=None,
        )
        reconciled = repo.reconcile(
            ReprocessingReconcile(
                command_id=new_uuid_v7(),
                comparison_revision_id=page.comparison_revision_id,
                expected_plan_revision_id=None,
                rationale="Explicit full retained obligation",
                mappings=(mapping,),
            )
        )
        command = ReprocessingAcceptance(
            command_id=new_uuid_v7(),
            plan_revision_id=reconciled.plan_revision_id,
            expected_current_revision_id=base.revision_id,
            confirmation_sha256=reconciled.confirmation_sha256,
            expected_graph_sha256=reconciled.impact.graph_sha256,
            decision="accept-reparse",
        )
        before = f.counts()
        for changed in (
            command.model_copy(update={"confirmation_sha256": "0" * 64}),
            command.model_copy(update={"expected_current_revision_id": new_uuid_v7()}),
            command.model_copy(update={"expected_graph_sha256": "0" * 64}),
        ):
            with self.assertRaises(fixtures.DocumentRevisionProblem):
                repo.accept(changed)
            self.assertEqual(before, f.counts())
        self.assertIsNotNone(repo.accept(command))

    def append_output(self, label, source=None, *, relation="direct", coverage="complete"):
        f = self.f
        with closing(open_canonical_database(f.database, expected_project_id=f.f.source.project_id)) as db:
            db.execute("BEGIN IMMEDIATE")
            with f.repository._aggregates(db) as aggregates:
                prior = None if source is None else aggregates.get_revision(source)
                dependencies = (
                    ()
                    if prior is None
                    else (
                        MaterialDependency(
                            dependency_id=new_uuid_v7(),
                            dependency_kind="source-revision",
                            relation_type=relation,
                            revision_id=prior.revision_id,
                            configuration_id=None,
                            configuration_version=None,
                            fingerprint=_projection_content_sha256(prior),
                            governing_policy_id="dependency.material.v1",
                            governing_policy_version="1.0.0",
                        ),
                    )
                )
                output = aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=new_uuid_v7(),
                        aggregate_id=new_uuid_v7(),
                        aggregate_kind="evidence",
                        created_at=f.now,
                        modified_at=f.now,
                        display_label_observed=label,
                        display_label_normalized=None,
                        knowledge_status="observed",
                        rights_status="allowed",
                        dependency_coverage=coverage,
                        material_dependencies=dependencies,
                    ),
                    f.repository._event(f.actor, f.now, "evidence.created", "authored-reparse-output-" + new_uuid_v7()),
                    expected_revision=None,
                )
            db.commit()
            return output.revision_id

    def test_selective_material_impact_is_immediate_and_new_history_does_not_stale_itself(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        direct = self.append_output("Authored direct consumer", base.revision_id)
        transitive = self.append_output("Authored transitive consumer", direct)
        conditional = self.append_output("Authored undecided conditional", base.revision_id, relation="conditional")
        informational = self.append_output(
            "Authored non-material observation", base.revision_id, relation="non-material"
        )
        unrelated = self.append_output("Authored unrelated branch", coverage="not-applicable")

        # Declare the already-migrated legacy representation. New public writes
        # correctly reject unreported coverage; this fixture supplies no edges
        # or registration authority, matching the existing migration contract.
        def migrated_legacy(connection, **values):
            connection.execute(
                "INSERT INTO material_dependency_outputs VALUES (?,?,?,NULL,NULL)",
                (values["revision"].revision_id, values["project_id"], "legacy-unreported"),
            )

        with patch("research_observatory_core.repositories._record_material_dependencies", migrated_legacy):
            legacy = self.append_output("Authored migrated legacy unknown coverage", coverage="not-applicable")
        repo, _batch, page, command = self.ready(base, f.parse("Material graph change"))
        # The batch and comparison also retain historical non-material links.
        self.assertEqual(
            (3, 3, 1),
            (page.impact.affected_count, page.impact.informational_count, page.impact.legacy_unreported_count),
        )
        accepted = repo.accept(command)
        self.assertEqual("completed", accepted.impact_state)
        states = {s.output_revision_id: s.disposition for s in f.reopen().reprocessing().impacts.stale_states()}
        self.assertEqual("stale", states[direct])
        self.assertEqual("stale", states[transitive])
        self.assertEqual("unknown-impact", states[conditional])
        for retained in (informational, unrelated, legacy, accepted.machine_revision_id, accepted.revision_id):
            self.assertNotIn(retained, states)
        self.assertEqual(base, f.reopen().read(base.revision_id))
        self.assertEqual(accepted.revision_id, f.reopen().read(accepted.revision_id).revision_id)

    def test_pending_impact_restart_exact_old_checkpoint_retry_cannot_consume_another_chunk(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        outputs = tuple(self.append_output("Authored bounded consumer", base.revision_id) for _ in range(101))
        repo, batch, _page, command = self.ready(base, f.parse("Pending material graph change"))
        accepted = repo.accept(command)
        self.assertEqual(("running", 0, 101), (accepted.impact_state, accepted.processed_items, accepted.total_items))
        reopened = f.reopen().reprocessing()
        self.assertEqual(accepted, reopened.read_impact(batch.batch_revision_id, batch.items[0].item_id))
        first = reopened.resume_impact(
            batch.batch_revision_id, batch.items[0].item_id, accepted.impact_checkpoint_sha256
        )
        self.assertEqual(("running", 100), (first.impact_state, first.processed_items))
        self.assertEqual(
            first,
            f.reopen()
            .reprocessing()
            .resume_impact(batch.batch_revision_id, batch.items[0].item_id, accepted.impact_checkpoint_sha256),
        )
        with self.assertRaises(fixtures.DocumentRevisionProblem):
            reopened.resume_impact(batch.batch_revision_id, batch.items[0].item_id, "0" * 64)
        final = (
            f.reopen()
            .reprocessing()
            .resume_impact(batch.batch_revision_id, batch.items[0].item_id, first.impact_checkpoint_sha256)
        )
        self.assertEqual(("completed", 101), (final.impact_state, final.processed_items))
        self.assertEqual(
            final,
            reopened.resume_impact(batch.batch_revision_id, batch.items[0].item_id, first.impact_checkpoint_sha256),
        )
        self.assertEqual(
            set(outputs),
            {s.output_revision_id for s in reopened.impacts.stale_states() if s.run_id == accepted.impact_run_id},
        )
        self.assertEqual(
            ["started", "checkpoint", "completed"],
            [a.event_type for a in reopened.impacts.audit(run_id=accepted.impact_run_id)],
        )

    def second_source(self):
        f, source_fixture = self.f, self.f.f
        attachments = source_fixture.fixture
        candidate = attachments.service.stage(
            BytesIO(b"Second SYNTHETIC source copy for a two-document batch"),
            source_name="paper.txt",
            declared_media_type="text/plain",
            source_assertion_revision_id=attachments._assertion_id(),
            work_id=attachments.corpus.work_id,
            work_revision_id=attachments.work_revision_id,
            version_id=attachments.version.version_id,
            version_revision_id=attachments.version.revision_id,
            actor=attachments.corpus.actor,
        )
        policy = attachments.publish_right(candidate, inspect=True)
        attachment = attachments.service.commit(
            candidate.candidate_id,
            confirmation_sha256=candidate.candidate_sha256,
            command_id=new_uuid_v7(),
            actor=attachments.corpus.actor,
        )
        from research_observatory_core.parsing.contracts import LocalOrigin
        from research_observatory_core.parsing.selection import (
            ParserRegistry,
            RegisteredParser,
            SelectionSource,
            select_parser,
        )
        from research_observatory_core.parsing.source import source_identity

        source_fixture.source = source_identity(attachment, candidate, LocalOrigin(kind="local-import"))
        source_fixture.candidate, source_fixture.policy = candidate, policy
        source_fixture.permit()
        producer = source_fixture.request.binding.producer
        selection = select_parser(
            (SelectionSource(source_fixture.source, "available", "primary"),),
            ParserRegistry((RegisteredParser(producer, "available"),)),
            primary_attachment_id=source_fixture.source.attachment_id,
        )
        source_fixture.request = source_fixture.request.model_copy(update={"selection": selection})
        return f.repository.accept(f.command(f.parse("Second authored initial parse")))

    def test_two_document_cancel_reopen_preserves_committed_item_and_stops_unaccepted_job(self):
        f = self.f
        first = f.repository.accept(f.command(f.parse()))
        receipt = f.parse("First item new parse")
        second = self.second_source()
        with closing(open_canonical_database(f.database, expected_project_id=f.f.source.project_id)) as db:
            first_input = f.repository._input(db, receipt.binding.attempt.job_id)
            second_input = f.repository._input(db, second.result.binding.attempt.job_id).model_copy(
                update={"command_id": new_uuid_v7()}
            )
        by_base = {first.revision_id: first_input, second.revision_id: second_input}
        repo = f.repository.reprocessing()
        batch = repo.create(
            ReprocessingCreate(command_id=new_uuid_v7(), base_revision_ids=(first.revision_id, second.revision_id)),
            input_factory=lambda base: by_base[base.revision_id],
        )
        self.assertEqual(("ready", "processing"), tuple(item.state for item in batch.items))
        item = batch.items[0]
        page = repo.compare(batch.batch_revision_id, item.item_id)
        page = repo.reconcile(
            ReprocessingReconcile(
                command_id=new_uuid_v7(),
                comparison_revision_id=page.comparison_revision_id,
                expected_plan_revision_id=None,
                rationale="Only the first item was explicitly accepted",
                mappings=(),
            )
        )
        command = ReprocessingAcceptance(
            command_id=new_uuid_v7(),
            plan_revision_id=page.plan_revision_id,
            expected_current_revision_id=first.revision_id,
            confirmation_sha256=page.confirmation_sha256,
            expected_graph_sha256=page.impact.graph_sha256,
            decision="accept-reparse",
        )
        accepted = repo.accept(command)
        cancelled = repo.cancel(ReprocessingCancel(command_id=new_uuid_v7(), batch_revision_id=batch.batch_revision_id))
        self.assertEqual(("accepted", "cancelled"), tuple(item.state for item in cancelled.items))
        self.assertEqual("cancelled", f.queue.get(batch.items[1].job_id).state)
        self.assertEqual(second, f.reopen().read(second.revision_id))
        self.assertEqual(accepted.revision_id, f.reopen().read(accepted.revision_id).revision_id)
        before = f.counts()
        self.assertEqual(accepted, f.reopen().reprocessing().accept(command))
        self.assertEqual(before, f.counts())
        self.assertEqual(accepted, f.reopen().reprocessing().read_impact(cancelled.batch_revision_id, item.item_id))
        with self.assertRaises(fixtures.DocumentRevisionProblem):
            f.reopen().reprocessing().compare(cancelled.batch_revision_id, cancelled.items[1].item_id)
        self.assertEqual(before, f.counts())

    def test_all_active_generations_must_reconcile_and_inherited_label_survives_split(self):
        f = self.f
        _machine, first_draft, first = self.corrected()
        node = first.structure.nodes[0]
        second_draft = f.repository.corrections().save(
            CorrectionSave.model_validate(
                {
                    "commandId": new_uuid_v7(),
                    "draftId": None,
                    "expectedDraftRevisionId": None,
                    "patch": {
                        "baseRevisionId": first.revision_id,
                        "expectedStructureSha256": first.structure_sha256,
                        "operations": [
                            {"op": "split", "nodeId": node.node_id, "expectedNodeSha256": value_sha256(node), "at": 12}
                        ],
                    },
                    "rationale": "Original second human split decision",
                }
            )
        )
        base = f.repository.corrections().accept(
            CorrectionAcceptance(
                command_id=new_uuid_v7(),
                draft_revision_id=second_draft.revision_id,
                expected_current_revision_id=first.revision_id,
                confirmation_sha256=value_sha256(second_draft),
                decision="accept-correction",
            )
        )
        receipt = f.parse("New authored corrected reparse")
        repo = f.repository.reprocessing()
        batch = self.batch(base, receipt)
        page = repo.compare(batch.batch_revision_id, batch.items[0].item_id)
        self.assertEqual((2, 2, 2), (page.generation_count, page.total_obligations, page.unresolved_count))
        for remaining in (1, 0):
            page = repo.reconcile(
                ReprocessingReconcile(
                    command_id=new_uuid_v7(),
                    comparison_revision_id=page.comparison_revision_id,
                    expected_plan_revision_id=page.plan_revision_id,
                    rationale="Current human reconciles every original generation",
                    mappings=(
                        ReprocessingMapping(
                            obligation_id=page.obligations[0].obligation_id,
                            node_id=page.candidate_nodes[0].node_id,
                            related_node_id=None,
                            reference_id=None,
                        ),
                    ),
                )
            )
            self.assertEqual(remaining, page.unresolved_count)
            command = ReprocessingAcceptance(
                command_id=new_uuid_v7(),
                plan_revision_id=page.plan_revision_id,
                expected_current_revision_id=base.revision_id,
                confirmation_sha256=page.confirmation_sha256,
                expected_graph_sha256=page.impact.graph_sha256,
                decision="accept-reparse",
            )
            if remaining:
                before = f.counts()
                with self.assertRaises(fixtures.DocumentRevisionProblem):
                    repo.accept(command)
                self.assertEqual(before, f.counts())
        accepted = repo.accept(command)
        final = f.reopen().read(accepted.revision_id)
        self.assertEqual(2, len(final.structure.nodes))
        metadata = f.reopen().corrections().metadata(final.revision_id)
        self.assertEqual(
            [label.label for label in f.reopen().corrections().metadata(base.revision_id).labels],
            [label.label for label in metadata.labels],
        )
        self.assertIn("Retained human label", [label.label for label in metadata.labels])
        self.assertEqual(first_draft, f.reopen().corrections().read(first_draft.revision_id))
        self.assertEqual(second_draft, f.reopen().corrections().read(second_draft.revision_id))
        before = f.counts()
        self.assertEqual(accepted, f.reopen().reprocessing().accept(command))
        self.assertEqual(before, f.counts())

    def test_saved_plan_same_text_target_substitution_after_confirmation_refuses(self):
        f = self.f
        _machine, _draft, base = self.corrected()

        def duplicate(wire):
            wire["nodes"].append({**wire["nodes"][0], "stagedId": "second-authored-node", "order": 1})

        receipt = f.parse("Identical same-text target candidates", change=duplicate)
        repo, _batch, page, command = self.ready(base, receipt)
        observed = repo._record

        def substitute(connection, revision_id, expected=None):
            record = observed(connection, revision_id, expected)
            if revision_id == page.plan_revision_id:
                step = record.steps[0]
                target = page.candidate_nodes[1]
                mapping = step.mappings[0].model_copy(update={"node_id": target.node_id})
                operation = step.mapped_patch.operations[0].model_copy(
                    update={"node_id": target.node_id, "expected_node_sha256": target.node_sha256}
                )
                changed = step.model_copy(
                    update={
                        "mappings": (mapping,),
                        "mapped_patch": step.mapped_patch.model_copy(update={"operations": (operation,)}),
                    }
                )
                return record.model_copy(update={"steps": (changed,)})
            return record

        before = f.counts()
        with patch.object(repo, "_record", substitute), self.assertRaises(fixtures.DocumentRevisionProblem):
            repo.accept(command)
        self.assertEqual(before, f.counts())
        self.assertEqual(base, f.reopen().read(base.revision_id))

    def test_persisted_batch_without_enqueue_reopens_and_exact_retry_submits_once(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        with closing(open_canonical_database(f.database, expected_project_id=f.f.source.project_id)) as db:
            inputs = f.repository._input(db, base.result.binding.attempt.job_id).model_copy(
                update={"command_id": new_uuid_v7()}
            )
        command = ReprocessingCreate(command_id=new_uuid_v7(), base_revision_ids=(base.revision_id,))
        repo = f.repository.reprocessing()
        with (
            patch.object(
                f.repository, "submit", side_effect=fixtures.DocumentRevisionProblem("authored-before-enqueue")
            ),
            self.assertRaises(fixtures.DocumentRevisionProblem),
        ):
            repo.create(command, input_factory=lambda _base: inputs)
        retained = f.reopen().reprocessing().queue().items[0]
        self.assertEqual(("not-submitted", None), (retained.items[0].state, retained.items[0].job_id))
        before = f.counts()
        with self.assertRaises(fixtures.DocumentRevisionProblem):
            repo.compare(retained.batch_revision_id, retained.items[0].item_id)
        self.assertEqual(before, f.counts())
        factory = unittest.mock.Mock(side_effect=AssertionError("exact retry must retain immutable inputs"))
        admitted = repo.create(command, input_factory=factory)
        factory.assert_not_called()
        self.assertEqual(
            ("processing", retained.batch_revision_id), (admitted.items[0].state, admitted.batch_revision_id)
        )
        before = f.counts()
        self.assertEqual(admitted, f.reopen().reprocessing().create(command, input_factory=factory))
        self.assertEqual(before, f.counts())
        self.assertEqual(base, f.reopen().read(base.revision_id))

    def missing_input(self, base):
        with closing(open_canonical_database(self.f.database, expected_project_id=base.project_id)) as db:
            return self.f.repository._input(db, base.result.binding.attempt.job_id).model_copy(
                update={"command_id": new_uuid_v7()}
            )

    def assert_no_job(self, inputs):
        with closing(open_canonical_database(self.f.database, expected_project_id=inputs.project_id)) as db:
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM document_parse_jobs WHERE project_id=? AND command_id=?",
                    (inputs.project_id, inputs.command_id),
                ).fetchone()[0],
            )

    def test_cancelled_unsubmitted_batch_exact_create_retry_returns_current_without_job(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        inputs = self.missing_input(base)
        command = ReprocessingCreate(command_id=new_uuid_v7(), base_revision_ids=(base.revision_id,))
        repo = f.repository.reprocessing()
        with (
            patch.object(f.repository, "submit", side_effect=RuntimeError("authored-before-enqueue")),
            self.assertRaises(fixtures.DocumentRevisionProblem),
        ):
            repo.create(command, input_factory=lambda _base: inputs)
        retained = f.reopen().reprocessing().queue().items[0]
        cancelled = repo.cancel(
            ReprocessingCancel(command_id=new_uuid_v7(), batch_revision_id=retained.batch_revision_id)
        )
        before = f.counts()
        factory = unittest.mock.Mock(side_effect=AssertionError("historical retry must retain its inputs"))
        self.assertEqual(cancelled, f.reopen().reprocessing().create(command, input_factory=factory))
        factory.assert_not_called()
        self.assert_no_job(inputs)
        self.assertEqual(before, f.counts())
        self.assertEqual(base, f.reopen().read(base.revision_id))

    def test_cancellation_winning_new_job_admission_writer_prevents_future_submission(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        inputs = self.missing_input(base)
        command = ReprocessingCreate(command_id=new_uuid_v7(), base_revision_ids=(base.revision_id,))
        repo = f.repository.reprocessing()
        submit = f.repository.submit
        observed = []

        def cancel_before_writer(inputs, **kwargs):
            retained = f.reopen().reprocessing().queue().items[0]
            observed.append(
                f.reopen()
                .reprocessing()
                .cancel(ReprocessingCancel(command_id=new_uuid_v7(), batch_revision_id=retained.batch_revision_id))
            )
            return submit(inputs, **kwargs)

        with patch.object(f.repository, "submit", side_effect=cancel_before_writer):
            current = repo.create(command, input_factory=lambda _base: inputs)
        self.assertEqual(observed[0], current)
        self.assert_no_job(inputs)
        self.assertEqual(base, f.reopen().read(base.revision_id))

    def test_superseded_continuation_retry_never_submits_its_old_unsubmitted_input(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))
        original_input = self.missing_input(base)
        repo = f.repository.reprocessing()
        batch = repo.create(
            ReprocessingCreate(command_id=new_uuid_v7(), base_revision_ids=(base.revision_id,)),
            input_factory=lambda _base: original_input,
        )
        first_input = self.missing_input(base)
        first_command = ReprocessingContinue(
            command_id=new_uuid_v7(),
            batch_revision_id=batch.batch_revision_id,
            item_id=batch.items[0].item_id,
            expected_job_id=batch.items[0].job_id,
        )
        with (
            patch.object(
                f.repository,
                "submit",
                side_effect=fixtures.DocumentRevisionProblem("authored-before-continued-enqueue"),
            ),
            self.assertRaises(fixtures.DocumentRevisionProblem),
        ):
            repo.continue_item(first_command, input_factory=lambda _base: first_input)
        successor = f.reopen().reprocessing().queue().items[0]
        second_input = self.missing_input(base)
        current = repo.continue_item(
            ReprocessingContinue(
                command_id=new_uuid_v7(),
                batch_revision_id=successor.batch_revision_id,
                item_id=successor.items[0].item_id,
                expected_job_id=None,
            ),
            input_factory=lambda _base: second_input,
        )
        before = f.counts()
        factory = unittest.mock.Mock(side_effect=AssertionError("historical continuation must retain its inputs"))
        self.assertEqual(current, f.reopen().reprocessing().continue_item(first_command, input_factory=factory))
        factory.assert_not_called()
        self.assert_no_job(first_input)
        self.assertEqual(before, f.counts())
        cancelled = repo.cancel(
            ReprocessingCancel(command_id=new_uuid_v7(), batch_revision_id=current.batch_revision_id)
        )
        self.assertEqual(cancelled, repo.continue_item(first_command, input_factory=factory))
        self.assert_no_job(first_input)

    def test_retained_partial_result_quality_is_visible_but_no_complete_comparison_is_invented(self):
        f = self.f
        base = f.repository.accept(f.command(f.parse()))

        def partial(wire):
            wire["quality"]["warnings"] = [
                {"code": "parser-partial-output", "severity": "warning", "nodeId": None, "detail": None}
            ]

        receipt = f.parse("Retained partial reparse", change=partial)
        repo = f.repository.reprocessing()
        batch = self.batch(base, receipt)
        quality = f.repository.quality(batch.items[0].job_id)
        self.assertEqual("available", quality.assessment.availability)
        self.assertIn("parser-partial-output", quality.assessment.review_reasons)
        before = f.counts()
        with self.assertRaises(fixtures.DocumentRevisionProblem):
            repo.compare(batch.batch_revision_id, batch.items[0].item_id)
        self.assertEqual(before, f.counts())
        self.assertEqual(base, f.reopen().read(base.revision_id))
        self.assertEqual(batch.items[0].job_id, quality.job_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
