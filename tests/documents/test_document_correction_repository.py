"""Actual encrypted corrections and canonical atomic acceptance; synthetic parse."""

import sys
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_corrections import (  # noqa: E402
    CorrectionAcceptance,
    CorrectionDiscard,
    CorrectionPatch,
    CorrectionSave,
    ExcludeCorrection,
    RelabelCorrection,
    SplitCorrection,
    value_sha256,
)
from research_observatory_core.document_revision_repository import LocalDocumentCorrectionRepository  # noqa: E402
from research_observatory_core.document_revisions import DocumentRevisionProblem, protected_json  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.parsing.contracts import CodepointRange  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.documents import test_document_revision_repository as fixtures  # noqa: E402
from tests.parsing.contract_fixtures import rich_ir_wire  # noqa: E402


class DocumentCorrectionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        result = self.f.parse("Authored synthetic paragraph")
        self.base = self.f.repository.accept(self.f.command(result))
        self.original = protected_json(self.base)
        self.adapter = LocalDocumentCorrectionRepository(self.f.repository)

    def reopen(self):
        return LocalDocumentCorrectionRepository(self.f.reopen())

    def save(self, *, previous=None, label="Authored heading", command_id=None):
        node = self.base.structure.nodes[0]
        return CorrectionSave(
            command_id=command_id or new_uuid_v7(),
            draft_id=previous.draft_id if previous else None,
            expected_draft_revision_id=previous.revision_id if previous else None,
            patch=CorrectionPatch(
                base_revision_id=self.base.revision_id,
                expected_structure_sha256=self.base.structure_sha256,
                operations=(
                    RelabelCorrection(
                        op="relabel", node_id=node.node_id, expected_node_sha256=value_sha256(node), label=label
                    ),
                ),
            ),
            rationale="Authored synthetic rationale; retain the observed parser text.",
        )

    def acceptance(self, draft, **changes):
        return CorrectionAcceptance.model_validate(
            {
                "commandId": new_uuid_v7(),
                "draftRevisionId": draft.revision_id,
                "expectedCurrentRevisionId": self.base.revision_id,
                "confirmationSha256": value_sha256(draft),
                "decision": "accept-correction",
                **changes,
            }
        )

    def head(self):
        with (
            closing(open_canonical_database(self.f.database, expected_project_id=self.f.f.source.project_id)) as db,
            self.f.repository._aggregates(db) as aggregates,
        ):
            return aggregates.get(self.base.document_id).revision_id

    def test_saved_draft_is_encrypted_reopens_and_does_not_accept_or_change_source_head(self):
        before = self.f.counts()
        command = self.save()
        draft = self.adapter.save(command)
        with (
            closing(open_canonical_database(self.f.database, expected_project_id=self.f.f.source.project_id)) as db,
            self.f.repository._aggregates(db) as aggregates,
        ):
            self.assertEqual(0, aggregates.get_revision(draft.revision_id).revision)
        self.assertEqual(self.base.revision_id, self.head())
        self.assertEqual(before["document_normalized_revisions"], self.f.counts()["document_normalized_revisions"])
        self.assertEqual(self.f.actor.actor_id, draft.authored_by)
        self.assertEqual(command.rationale, draft.rationale)
        self.assertEqual(draft, self.reopen().read(draft.revision_id))
        self.assertEqual(self.original, protected_json(self.f.reopen().read(self.base.revision_id)))
        objects = self.f.f.fixture.project_root / "objects"
        for item in objects.rglob("*"):
            if item.is_file():
                raw = item.read_bytes()
                self.assertNotIn(command.rationale.encode(), raw)
                self.assertNotIn(b"Authored heading", raw)

    def test_preview_only_tail_has_a_second_page_without_advancing_accepted_head(self):
        def authored(value):
            first = value["nodes"][0]
            value["nodes"] = [{**first, "stagedId": f"node-{i}", "order": i} for i in range(20)]

        parsed = self.f.parse("Authored synthetic tail", change=authored)
        self.base = self.f.repository.accept(self.f.command(parsed, expected=self.base.revision_id))
        node = self.base.structure.nodes[-1]
        saving = self.save().model_copy(
            update={
                "patch": CorrectionPatch(
                    base_revision_id=self.base.revision_id,
                    expected_structure_sha256=self.base.structure_sha256,
                    operations=(
                        SplitCorrection(
                            op="split", node_id=node.node_id, expected_node_sha256=value_sha256(node), at=8
                        ),
                    ),
                )
            }
        )
        draft = self.adapter.save(saving)
        first = self.reopen().page(self.base.revision_id, draft_revision_id=draft.revision_id)
        self.assertEqual((20, 20, 20), (len(first.nodes), len(first.preview_nodes), first.next_offset))
        final = self.reopen().page(self.base.revision_id, draft_revision_id=draft.revision_id, offset=first.next_offset)
        self.assertEqual((), final.nodes)
        self.assertEqual(1, len(final.preview_nodes))
        self.assertEqual(" synthetic tail", final.preview_nodes[0].preview)
        self.assertIsNone(final.next_offset)
        self.assertEqual(self.base.revision_id, self.head())

    def test_explicit_acceptance_binds_rationale_result_new_ids_and_atomic_dependency_event(self):
        draft = self.adapter.save(self.save())
        command = self.acceptance(draft)
        accepted = self.adapter.accept(command)
        self.assertEqual(accepted.revision_id, self.head())
        self.assertEqual(self.base.revision_id, accepted.previous_revision_id)
        self.assertEqual(self.base.result, accepted.result)
        self.assertEqual(self.original, protected_json(self.f.reopen().read(self.base.revision_id)))
        self.assertTrue(
            {m.canonical_id for m in self.base.element_identities}.isdisjoint(
                {m.canonical_id for m in accepted.element_identities}
            )
        )
        self.assertEqual(accepted, self.f.reopen().read(accepted.revision_id))
        self.assertEqual(draft, self.reopen().accepted_draft(accepted.revision_id))
        with closing(open_canonical_database(self.f.database, expected_project_id=self.f.f.source.project_id)) as db:
            rows = db.execute(
                "SELECT previous_revision_id,replacement_revision_id FROM dependency_impact_runs "
                "WHERE project_id=? AND idempotency_key=?",
                (self.f.f.source.project_id, "document-correction-impact-" + command.command_id),
            ).fetchall()
            self.assertEqual([(self.base.revision_id, accepted.revision_id)], [tuple(r) for r in rows])
            events = db.execute(
                "SELECT actor_type,actor_id FROM provenance_events WHERE project_id=? AND revision_id IN (?,?)",
                (self.f.f.source.project_id, accepted.revision_id, accepted.decision_revision_id),
            ).fetchall()
            self.assertEqual([("human", self.f.actor.actor_id)] * 2, [tuple(r) for r in events])

    def test_exact_retry_does_not_duplicate_and_changed_commands_or_stale_drafts_refuse(self):
        saving = self.save()
        first = self.adapter.save(saving)
        before = self.f.counts()
        self.assertEqual(first, self.reopen().save(saving))
        self.assertEqual(before, self.f.counts())
        with self.assertRaises(DocumentRevisionProblem):
            self.reopen().save(saving.model_copy(update={"rationale": "Different private rationale"}))
        second = self.adapter.save(self.save(previous=first, label="Second proposal"))
        with self.assertRaises(DocumentRevisionProblem):
            self.adapter.accept(self.acceptance(first))
        command = self.acceptance(second)
        accepted = self.adapter.accept(command)
        before = self.f.counts()
        self.assertEqual(accepted, self.reopen().accept(command))
        self.assertEqual(before, self.f.counts())
        with self.assertRaises(DocumentRevisionProblem):
            self.reopen().accept(command.model_copy(update={"confirmation_sha256": "0" * 64}))
        self.assertEqual(before, self.f.counts())

    def test_acceptance_interruption_rolls_back_head_elements_decision_and_impact_and_can_retry(self):
        draft = self.adapter.save(self.save())
        command = self.acceptance(draft)
        before = self.f.counts()
        with (
            patch(
                "research_observatory_core.document_revision_repository._publication_step",
                side_effect=lambda step: (
                    (_ for _ in ()).throw(RuntimeError("synthetic interrupt"))
                    if step == "correction-acceptance-complete"
                    else None
                ),
            ),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.adapter.accept(command)
        self.assertEqual(self.base.revision_id, self.head())
        self.assertEqual(before, self.f.counts())
        with closing(open_canonical_database(self.f.database, expected_project_id=self.f.f.source.project_id)) as db:
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM dependency_impact_runs WHERE idempotency_key=?",
                    ("document-correction-impact-" + command.command_id,),
                ).fetchone()[0],
            )
        self.assertEqual(self.base.revision_id, self.reopen().accept(command).previous_revision_id)

    def test_competing_base_only_one_acceptance_and_stopped_or_changed_authority_leaves_no_publication(self):
        first = self.adapter.save(self.save())
        second = self.adapter.save(self.save(label="Competing proposal"))
        before = self.f.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.adapter.accept(self.acceptance(first), cancelled=lambda: True)
        self.assertEqual(before, self.f.counts())
        actor = self.f.actor
        self.f.actor = replace(actor, intent_sha256="0" * 64)
        with self.assertRaises(DocumentRevisionProblem):
            self.adapter.accept(self.acceptance(first))
        self.f.actor = actor
        self.assertEqual(before, self.f.counts())
        self.adapter.accept(self.acceptance(first))
        before = self.f.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.reopen().accept(self.acceptance(second))
        self.assertEqual(before, self.f.counts())

    def test_successive_correction_preserves_accepted_human_label_after_split_and_reopen(self):
        first_draft = self.adapter.save(self.save())
        first = self.adapter.accept(self.acceptance(first_draft))
        node = first.structure.nodes[0]
        command = CorrectionSave(
            command_id=new_uuid_v7(),
            draft_id=None,
            expected_draft_revision_id=None,
            patch=CorrectionPatch(
                base_revision_id=first.revision_id,
                expected_structure_sha256=first.structure_sha256,
                operations=(
                    SplitCorrection(op="split", node_id=node.node_id, expected_node_sha256=value_sha256(node), at=9),
                ),
            ),
            rationale="A second authored decision splits the block and keeps the accepted heading label.",
        )
        second_draft = self.reopen().save(command)
        second = self.reopen().accept(
            CorrectionAcceptance(
                command_id=new_uuid_v7(),
                draft_revision_id=second_draft.revision_id,
                expected_current_revision_id=first.revision_id,
                confirmation_sha256=value_sha256(second_draft),
                decision="accept-correction",
            )
        )
        metadata = self.reopen().metadata(second.revision_id)
        self.assertEqual(second.revision_id, metadata.base_revision_id)
        self.assertEqual(second.structure_sha256, metadata.expected_structure_sha256)
        self.assertEqual("Authored heading", metadata.labels[0].label)
        self.assertIn(metadata.labels[0].node_id, {n.node_id for n in second.structure.nodes})
        self.assertEqual(second, self.f.reopen().read(second.revision_id))
        self.assertEqual(self.original, protected_json(self.f.reopen().read(self.base.revision_id)))

    def test_saved_undo_and_explicit_discard_reopen_without_acceptance_and_cannot_be_accepted(self):
        first = self.adapter.save(self.save())
        command = self.save(previous=first).model_dump(mode="json", by_alias=True)
        command["patch"]["operations"] = []
        command["rationale"] = "Undo the authored proposal before acceptance."
        undone = self.reopen().save(CorrectionSave.model_validate(command))
        self.assertEqual((), self.reopen().read(undone.revision_id).patch.operations)
        self.assertEqual(self.base.revision_id, self.head())
        with self.assertRaises(DocumentRevisionProblem):
            self.adapter.accept(self.acceptance(undone))
        discard = CorrectionDiscard(
            command_id=new_uuid_v7(),
            draft_revision_id=undone.revision_id,
            confirmation_sha256=value_sha256(undone),
            rationale="Discard this saved proposal deliberately.",
        )
        discarded = self.reopen().discard(discard)
        self.assertEqual("discarded", self.reopen().read(discarded.revision_id).state)
        self.assertEqual(undone, self.reopen().read(undone.revision_id))
        self.assertEqual(self.base.revision_id, self.head())
        counts = self.f.counts()
        self.assertEqual(discarded, self.reopen().discard(discard))
        self.assertEqual(counts, self.f.counts())
        with self.assertRaises(DocumentRevisionProblem):
            self.adapter.accept(self.acceptance(discarded))

    def test_excluded_child_cannot_supply_new_ancestor_quote_but_prior_anchor_is_immutable(self):
        from research_observatory_core.anchors.contracts import AnchorSelection
        from research_observatory_core.source_anchor_repository import LocalSourceAnchorRepository

        def authored(value):
            value.update({k: v for k, v in rich_ir_wire().items() if k not in {"binding", "rawArtifacts"}})
            value["figures"][0]["previewStageId"] = None

        parsed = self.f.parse(change=authored)
        self.base = self.f.repository.accept(self.f.command(parsed, expected=self.base.revision_id))
        paragraph = next(n for n in self.base.structure.nodes if n.kind == "paragraph")
        marker = next(n for n in self.base.structure.nodes if n.kind == "citation-marker")
        anchors = LocalSourceAnchorRepository(self.f.reopen())
        selection = AnchorSelection(
            revision_id=self.base.revision_id,
            node_id=paragraph.node_id,
            normalized_range=CodepointRange(start=6, end=10),
        )
        old = anchors.create(new_uuid_v7(), selection)
        save = self.save().model_copy(
            update={
                "patch": CorrectionPatch(
                    base_revision_id=self.base.revision_id,
                    expected_structure_sha256=self.base.structure_sha256,
                    operations=(
                        ExcludeCorrection(
                            op="exclude", node_id=marker.node_id, expected_node_sha256=value_sha256(marker)
                        ),
                    ),
                )
            }
        )
        draft = self.adapter.save(save)
        accepted = self.adapter.accept(self.acceptance(draft))
        current = next(n for n in accepted.structure.nodes if n.kind == "paragraph")
        before = self.f.counts()
        observed = []
        build = anchors._build_target

        def inspect_guard(*args):
            try:
                return build(*args)
            except DocumentRevisionProblem as error:
                observed.append(str(error))
                raise

        with (
            patch.object(anchors, "_build_target", inspect_guard),
            self.assertRaisesRegex(DocumentRevisionProblem, "source-anchor-denied"),
        ):
            anchors.create(
                new_uuid_v7(),
                selection.model_copy(
                    update={
                        "revision_id": accepted.revision_id,
                        "node_id": current.node_id,
                    }
                ),
            )
        self.assertEqual(["source-anchor-excluded-region"], observed)
        self.assertEqual(before, self.f.counts())
        self.assertEqual(old, LocalSourceAnchorRepository(self.f.reopen()).read(old.anchor_id))


if __name__ == "__main__":
    unittest.main()
