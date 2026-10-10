"""Actual encrypted publication/history; authored IR does not prove a parser."""

import copy
import sys
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.document_table_figure_repository import LocalDocumentTableFigureRepository  # noqa: E402
from research_observatory_core.document_table_figures import TableFigureCommand, TableFigureExcludeCommand  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.repositories import _material_registration_with_connection  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.documents import test_document_revision_repository as fixtures  # noqa: E402

RAW = "Synthetic table.\nA\nB\nSynthetic figure.\n"


def table_figure_ir(value):
    root = value["nodes"][0]
    projection = root["text"]["projectionId"]

    def span(start, end):
        return dict(
            projectionId=projection, normalizedRange=dict(start=start, end=end), rawRanges=[dict(start=start, end=end)]
        )

    def node(name, kind, start, end, parent=None):
        result = copy.deepcopy(root)
        result.update(stagedId=name, kind=kind, order=len(value["nodes"]), parentId=parent, text=span(start, end))
        result["locator"]["rawRanges"] = result["text"]["rawRanges"]
        value["nodes"].append(result)
        return result

    node("table", "table", 0, RAW.index("Synthetic figure."))
    cells = []
    for row, text in enumerate(("A", "B")):
        start = RAW.index(text + "\n")
        item = node("cell-" + text, "table-cell", start, start + 1, "table")
        cells.append(
            dict(
                nodeId=item["stagedId"],
                row=row,
                column=0,
                rowSpan=1,
                columnSpan=1,
                rawText=item["text"],
                confidence=dict(state="reported", value=0.5 + 0.4 * row),
            )
        )
    node("figure", "figure", RAW.index("Synthetic figure."), len(RAW))
    value["tables"] = [dict(nodeId="table", rows=2, columns=1, cells=cells, gridState="reported")]
    value["figures"] = [dict(nodeId="figure", caption=None, locator=value["nodes"][-1]["locator"], previewStageId=None)]


class TableFigureRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        parsed = self.f.parse(RAW, change=table_figure_ir)
        self.accepted = self.f.repository.accept(self.f.command(parsed))
        self.repository = self.reopen()

    def reopen(self):
        return LocalDocumentTableFigureRepository(self.f.reopen(), resolve=lambda _: self.f.f.fixture.corpus.source)

    def command(self, expected=None, command_id=None):
        return TableFigureCommand(
            command_id=command_id or new_uuid_v7(),
            revision_id=self.accepted.revision_id,
            expected_collection_revision_id=expected,
        )

    def exclude(self, collection, *, command_id=None, node_id=None):
        return TableFigureExcludeCommand(
            command_id=command_id or new_uuid_v7(),
            revision_id=self.accepted.revision_id,
            expected_collection_revision_id=collection.collection_revision_id,
            node_id=node_id or collection.entries[0].node_id,
            rationale="Synthetic human exclusion of unreliable extraction.",
        )

    def counts(self):
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            return tuple(
                db.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
                for table in (
                    "aggregate_revisions",
                    "document_enrichments",
                    "document_enrichment_elements",
                    "provenance_events",
                    "outbox_events",
                )
            )

    def test_encrypted_objects_exact_retry_reopen_and_material_inputs(self):
        original = self.f.repository.read(self.accepted.revision_id)
        command = self.command()
        first = self.repository.enrich(command)
        count = self.counts()
        self.assertEqual(first, self.repository.enrich(command))
        self.assertEqual(first, self.reopen().read(self.accepted.revision_id))
        self.assertEqual(count, self.counts())
        self.assertEqual(["table", "figure"], [e.kind for e in first.entries])
        self.assertEqual(["low-confidence", "reported-confidence"], [c.triage for c in first.entries[0].cells])
        self.assertTrue(all(c.scholarly_verification == "unverified" for c in first.entries[0].cells))
        self.assertEqual(original, self.f.repository.read(self.accepted.revision_id))
        self.assertNotIn(RAW.encode(), self.f.database.read_bytes())
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            registration = _material_registration_with_connection(
                db, self.accepted.project_id, first.collection_revision_id
            )
            self.assertEqual("complete", registration.coverage)
            self.assertIn(self.accepted.revision_id, {d.revision_id for d in registration.dependencies})
            rows = db.execute(
                "SELECT element_id,element_order FROM document_enrichment_elements WHERE collection_revision_id=?",
                (first.collection_revision_id,),
            ).fetchall()
        self.assertEqual({e.node_id for e in first.entries}, {r[0] for r in rows})
        self.assertEqual({(e.node_id, e.source_order) for e in first.entries}, {tuple(r) for r in rows})

    def test_exclusion_appends_history_exact_retry_and_survives_refresh(self):
        original = self.f.repository.read(self.accepted.revision_id)
        first = self.repository.enrich(self.command())
        command = self.exclude(first)
        second = self.repository.exclude(command)
        count = self.counts()
        self.assertEqual(second, self.repository.exclude(command))
        self.assertEqual(count, self.counts())
        self.assertEqual(first.collection_revision_id, second.previous_collection_revision_id)
        self.assertEqual(first.entries, second.entries)
        self.assertEqual(command.node_id, second.exclusions[0].node_id)
        self.assertEqual(self.f.actor.actor_id, second.exclusions[0].actor_id)
        self.assertEqual(command.rationale, second.exclusions[0].rationale)
        refreshed = self.reopen().enrich(self.command(second.collection_revision_id))
        self.assertEqual(second.exclusions, refreshed.exclusions)
        self.assertEqual(refreshed, self.reopen().read(self.accepted.revision_id))
        self.assertEqual(original, self.f.repository.read(self.accepted.revision_id))
        self.assertFalse(first.exclusions)

    def test_stale_head_command_reuse_unknown_object_and_duplicate_exclusion_are_refused(self):
        first = self.repository.enrich(self.command())
        command = self.exclude(first)
        second = self.repository.exclude(command)
        before = self.counts()
        for action in (
            lambda: self.repository.enrich(self.command()),
            lambda: self.repository.exclude(self.exclude(first)),
            lambda: self.repository.exclude(self.exclude(second)),
            lambda: self.repository.exclude(self.exclude(second, node_id=new_uuid_v7())),
            lambda: self.repository.enrich(self.command(second.collection_revision_id, command_id=command.command_id)),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                action()
            self.assertEqual(before, self.counts())

    def test_cancel_and_precommit_failure_leave_original_and_prior_collection_usable(self):
        first = self.repository.enrich(self.command())
        before = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.exclude(self.exclude(first), cancelled=lambda: True)
        self.assertEqual(before, self.counts())

        def fail(step):
            if step == "table-figures-before-commit":
                raise RuntimeError("synthetic interruption")

        with (
            patch("research_observatory_core.document_table_figure_repository._publication_step", side_effect=fail),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.repository.exclude(self.exclude(first))
        self.assertEqual(before, self.counts())
        self.assertEqual(first, self.reopen().read(self.accepted.revision_id))
        self.assertEqual(self.accepted, self.f.repository.read(self.accepted.revision_id))

    def test_current_human_rights_and_physical_admission_are_required(self):
        before = self.counts()

        def denied(_size):
            raise DocumentRevisionProblem("viewer-resource-limit")

        bounded = LocalDocumentTableFigureRepository(
            self.f.reopen(), resolve=lambda _: self.f.f.fixture.corpus.source, admit=denied
        )
        with self.assertRaisesRegex(DocumentRevisionProblem, "viewer-resource-limit"):
            bounded.enrich(self.command())
        self.assertEqual(before, self.counts())
        first = self.repository.enrich(self.command())
        before = self.counts()
        self.f.actor = replace(self.f.actor, actor_type="worker")
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.read(self.accepted.revision_id)
        self.assertEqual(before, self.counts())
        self.f.actor = replace(self.f.actor, actor_type="human")
        self.f.f.permit(derive="denied")
        # The explicit rights change itself appends its own canonical audit
        # event. Measure denied derivative actions from that new baseline.
        before = self.counts()
        for action in (
            lambda: self.repository.read(self.accepted.revision_id),
            lambda: self.repository.exclude(self.exclude(first)),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                action()
        self.assertEqual(before, self.counts())

    def test_human_authority_change_after_preparation_refuses_publication(self):
        first = self.repository.enrich(self.command())
        before = self.counts()
        original_actor = self.f.actor

        def revoke(step):
            if step == "table-figures-prepared":
                self.f.actor = replace(original_actor, actor_type="worker")

        try:
            with (
                patch(
                    "research_observatory_core.document_table_figure_repository._publication_step", side_effect=revoke
                ),
                self.assertRaises(DocumentRevisionProblem),
            ):
                self.repository.exclude(self.exclude(first))
        finally:
            self.f.actor = original_actor
        self.assertEqual(before, self.counts())
        self.assertEqual(first, self.reopen().read(self.accepted.revision_id))
        self.assertEqual(self.accepted, self.f.repository.read(self.accepted.revision_id))


if __name__ == "__main__":
    unittest.main(verbosity=2)
