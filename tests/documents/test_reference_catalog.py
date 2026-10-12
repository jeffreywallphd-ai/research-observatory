"""Real canonical database; declared synthetic source-resolver fixture only."""

import sqlite3
import sys
import unittest
from contextlib import closing, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]
from research_observatory_core.document_references import extract_references, match_reference_entries  # noqa: E402
from research_observatory_core.reconciliation.contracts import ReconciliationProblem  # noqa: E402
from research_observatory_core.reference_matching_repository import ReferenceMatchingRepository  # noqa: E402
from research_observatory_core.repositories import _UNIT_OF_WORKS, _SqliteAggregateRepository  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.corpus import test_repository as fixtures  # noqa: E402
from tests.documents.reference_catalog_fixture import import_works  # noqa: E402
from tests.documents.test_reference_entries import JATS, accepted_native  # noqa: E402


class ReferenceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.CorpusRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.repository = ReferenceMatchingRepository(self.f.database, self.f.project)
        self.entries = extract_references(accepted_native(JATS))
        self.resolve = lambda _address: self.f.source

    @contextmanager
    def transaction(self):
        with closing(open_canonical_database(self.f.database, expected_project_id=self.f.project)) as connection:
            connection.execute("BEGIN")
            token = _UNIT_OF_WORKS.register(connection, self.f.project)
            try:
                yield connection, _SqliteAggregateRepository(token)
            finally:
                _UNIT_OF_WORKS.unregister(token)
                connection.rollback()

    def test_complete_current_catalog_uses_sealed_work_and_indexed_exact_assessment(self):
        with self.transaction() as (connection, aggregates):
            before = connection.execute("SELECT total_changes()").fetchone()[0]
            snapshot = self.repository.snapshot(connection, aggregates, self.entries, resolve=self.resolve)
            self.assertEqual(before, connection.execute("SELECT total_changes()").fetchone()[0])
        matched = match_reference_entries(self.entries, snapshot.works, snapshot.assessments)
        assert matched[0].target is not None
        self.assertEqual(self.f.work_id, matched[0].target.work_id)
        self.assertEqual(self.f.work_revision_id, matched[0].target.revision_id)
        self.assertEqual("exact-linked", matched[0].link_state)
        self.assertIn(self.f.work_revision_id, snapshot.input_revision_ids)
        self.assertIn(self.f.source.source_revision_id, snapshot.input_revision_ids)
        self.assertIn(self.f.address.revision_id, snapshot.input_revision_ids)

    def test_current_source_change_cannot_be_omitted_to_prove_unique_match(self):
        changed = self.f.source.model_copy(update={"source_sha256": "e" * 64})
        with self.transaction() as (connection, aggregates), self.assertRaises(ReconciliationProblem):
            self.repository.snapshot(connection, aggregates, self.entries, resolve=lambda _address: changed)

    def test_catalog_digest_binds_complete_match_assessment_and_current_heads(self):
        with self.transaction() as (connection, aggregates):
            a = self.repository.snapshot(connection, aggregates, self.entries, resolve=self.resolve)
            b = self.repository.snapshot(connection, aggregates, (), resolve=self.resolve)
            self.assertNotEqual(a.sha256, b.sha256)
            self.assertEqual(a.works, b.works)

    def test_cancellation_does_not_expose_partial_catalog(self):
        with (
            self.transaction() as (connection, aggregates),
            self.assertRaisesRegex(ValueError, "reference-operation-cancelled"),
        ):
            self.repository.snapshot(connection, aggregates, self.entries, resolve=self.resolve, cancelled=lambda: True)

    def test_imported_fields_use_existing_ranking_projection_and_composed_author_list(self):
        resolve, _ = import_works(self.f, 1)
        with self.transaction() as (connection, aggregates):
            snapshot = self.repository.snapshot(connection, aggregates, self.entries, resolve=resolve)
        record = next(work.record for work in snapshot.works if work.target.work_id != self.f.work_id)
        self.assertNotIn("doi", dict(record.fields))
        self.assertEqual(("Synthetic One; Synthetic Two",), dict(record.fields)["authors"])
        self.assertEqual(
            "exact-linked", match_reference_entries(self.entries, snapshot.works, snapshot.assessments)[0].link_state
        )

    def test_missing_identifier_projection_cannot_hide_competing_sealed_work(self):
        # Deliberately damage only the non-authoritative lookup projection to
        # create a second sealed Work, then expose only the first index hit.
        with closing(sqlite3.connect(self.f.database)) as connection, connection:
            rows = connection.execute("SELECT * FROM reconciliation_identifier_links").fetchall()
            trigger = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name='reconciliation_identifier_links_no_delete'"
            ).fetchone()[0]
            connection.execute("DROP TRIGGER reconciliation_identifier_links_no_delete")
            connection.execute("DELETE FROM reconciliation_identifier_links")
            connection.execute(trigger)
        resolve, results = import_works(self.f, 1, duplicate=True)
        self.assertNotEqual(self.f.work_id, results[0].work_id)
        with closing(sqlite3.connect(self.f.database)) as connection, connection:
            connection.execute("DROP TRIGGER reconciliation_identifier_links_no_delete")
            connection.execute("DELETE FROM reconciliation_identifier_links")
            connection.executemany(
                "INSERT INTO reconciliation_identifier_links VALUES (" + ",".join("?" for _ in rows[0]) + ")", rows
            )
            connection.execute(trigger)
        with self.transaction() as (connection, aggregates):
            snapshot = self.repository.snapshot(connection, aggregates, self.entries, resolve=resolve)
        matched = match_reference_entries(self.entries, snapshot.works, snapshot.assessments)[0]
        self.assertEqual("ambiguous", matched.link_state)
        self.assertIsNone(matched.target)
        self.assertEqual(2, len(matched.candidates))
        self.assertIn("multiple-work-matches", matched.match_flags)


if __name__ == "__main__":
    unittest.main(verbosity=2)
