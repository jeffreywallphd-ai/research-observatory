"""Actual SQLCipher and encrypted object store, with declared synthetic parse data."""

import sys
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]
from research_observatory_core.document_reference_repository import LocalDocumentReferenceRepository  # noqa: E402
from research_observatory_core.document_references import ReferenceEnrichmentCommand  # noqa: E402
from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.object_store import _object_relative_path  # noqa: E402
from research_observatory_core.ports.repositories import (  # noqa: E402
    DEFAULT_DEPENDENCY_IMPACT_LIMITS,
    DependencyChange,
)
from research_observatory_core.repositories import (  # noqa: E402
    _material_registration_with_connection,
    _projection_content_sha256,
    _SqliteDependencyImpactRepository,
)
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.documents import test_document_revision_repository as fixtures  # noqa: E402
from tests.documents.reference_catalog_fixture import import_works  # noqa: E402

RAW = "Synthetic Author (2024). Synthetic reference alpha. doi:10.99999/synthetic-a"


class ReferenceRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

        def reference(value):
            node = value["nodes"][0]
            node["kind"] = "reference"
            value["references"] = [
                {
                    "stagedId": "reference-1",
                    "nodeId": node["stagedId"],
                    "order": 0,
                    "rawText": node["text"],
                    "identifiers": [{"scheme": "doi", "observed": "10.99999/synthetic-a"}],
                }
            ]

        parsed = self.f.parse(RAW, change=reference)
        self.accepted = self.f.repository.accept(self.f.command(parsed))
        self.source = self.f.f.fixture.corpus.source
        self.resolve = lambda _address: self.source
        self.repository = self.reopen()

    def reopen(self):
        return LocalDocumentReferenceRepository(self.f.reopen(), resolve=self.resolve)

    def command(self, expected=None, command_id=None):
        return ReferenceEnrichmentCommand(
            command_id=command_id or new_uuid_v7(),
            revision_id=self.accepted.revision_id,
            expected_collection_revision_id=expected,
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

    def test_encrypted_publication_exact_retry_reopen_and_base_revision_preserved(self):
        before = self.f.repository.read(self.accepted.revision_id).model_dump_json(by_alias=True)
        command = self.command()
        collection = self.repository.enrich(command)
        counts = self.counts()
        self.assertEqual(collection, self.repository.enrich(command))
        self.assertEqual(counts, self.counts())
        self.assertEqual(collection, self.reopen().read(self.accepted.revision_id))
        self.assertEqual("exact-linked", collection.entries[0].link_state)
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            head = db.execute(
                (
                    "SELECT revision_id FROM aggregate_revisions WHERE project_id=? AND "
                    "aggregate_id=? ORDER BY revision DESC LIMIT 1"
                ),
                (self.accepted.project_id, self.f.f.fixture.corpus.work_id),
            ).fetchone()[0]
        # The fixture's Version registration already advanced this Work. A link
        # must use that current sealed head, not its original import revision.
        self.assertNotEqual(self.f.f.fixture.corpus.work_revision_id, head)
        self.assertEqual(head, collection.entries[0].target.revision_id)
        self.assertEqual(RAW, collection.entries[0].raw_text)
        self.assertEqual(before, self.f.repository.read(self.accepted.revision_id).model_dump_json(by_alias=True))
        self.assertNotIn(RAW.encode(), self.f.database.read_bytes())
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            accepted_inputs = _material_registration_with_connection(
                db, self.accepted.project_id, self.accepted.revision_id
            )
            collection_inputs = _material_registration_with_connection(
                db, self.accepted.project_id, collection.collection_revision_id
            )
        original = self.accepted.structure.binding.source.document_revision_id
        self.assertIn(original, {item.revision_id for item in accepted_inputs.dependencies})
        self.assertIn(self.accepted.revision_id, {item.revision_id for item in collection_inputs.dependencies})
        self.assertNotIn(original, {item.revision_id for item in collection_inputs.dependencies})

    def test_current_rights_and_human_principal_required_for_read_and_retry(self):
        command = self.command()
        self.repository.enrich(command)
        self.f.actor = replace(self.f.actor, actor_type="worker")
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.enrich(command)
        self.f.actor = replace(self.f.actor, actor_type="human")
        self.f.f.permit(derive="denied")
        before = self.counts()
        for operation in (
            lambda: self.repository.enrich(command),
            lambda: self.repository.read(self.accepted.revision_id),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                operation()
        self.assertEqual(before, self.counts())

    def test_actual_large_catalog_manifests_reopen_and_retry_without_losing_inputs(self):
        self.resolve, results = import_works(self.f.f.fixture.corpus, 22)
        self.assertEqual(22, len(results))
        self.repository = self.reopen()
        command = self.command()
        collection = self.repository.enrich(command)
        with (
            closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db,
            self.f.repository._aggregates(db) as aggregates,
        ):
            snapshot = self.repository.matching.snapshot(db, aggregates, collection.entries, resolve=self.resolve)
        self.assertGreater(len(snapshot.input_revision_ids), 64)
        counts = self.counts()
        self.assertEqual(collection, self.reopen().read(self.accepted.revision_id))
        self.assertEqual(collection, self.reopen().enrich(command))
        self.assertEqual(counts, self.counts())

    def test_cancellation_and_precommit_failure_leave_no_partial_collection(self):
        command = self.command()
        before = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.enrich(command, cancelled=lambda: True)
        self.assertEqual(before, self.counts())
        with (
            patch(
                "research_observatory_core.document_reference_repository._publication_step",
                side_effect=RuntimeError("synthetic-reference-interruption"),
            ),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.repository.enrich(command)
        self.assertEqual(before, self.counts())
        self.assertIsNotNone(self.repository.enrich(command))

    def test_expected_head_and_changed_command_reuse_conflict(self):
        command = self.command()
        first = self.repository.enrich(command)
        before = self.counts()
        for invalid in (self.command(), self.command(first.collection_revision_id, command.command_id)):
            with self.assertRaises(DocumentRevisionProblem):
                self.repository.enrich(invalid)
        self.assertEqual(before, self.counts())
        second = self.repository.enrich(self.command(first.collection_revision_id))
        self.assertEqual(first.collection_id, second.collection_id)
        self.assertEqual(first.collection_revision_id, second.previous_collection_revision_id)
        self.assertNotEqual(first.collection_revision_id, second.collection_revision_id)
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            self.assertEqual(
                1,
                db.execute(
                    (
                        "SELECT COUNT(*) FROM dependency_impact_runs WHERE project_id=? AND "
                        "previous_revision_id=? AND replacement_revision_id=?"
                    ),
                    (self.accepted.project_id, first.collection_revision_id, second.collection_revision_id),
                ).fetchone()[0],
            )

    def test_new_work_after_preparation_invalidates_complete_snapshot_without_partial_output(self):
        fired = []

        def change(step):
            if step == "reference-prepared" and not fired:
                fired.append(True)
                self.f.f.fixture.corpus._citing_work()

        with (
            patch("research_observatory_core.document_reference_repository._publication_step", side_effect=change),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.repository.enrich(self.command())
        self.assertEqual([True], fired)
        self.assertEqual(0, self.counts()[1])
        self.assertEqual(self.accepted, self.f.repository.read(self.accepted.revision_id))

    def test_affected_canonical_work_blocks_publication_even_with_valid_seal_and_rights(self):
        self.invalidate(self.f.f.fixture.corpus.work_revision_id, current_work=True)
        before = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.enrich(self.command())
        self.assertEqual(before, self.counts())

    def test_affected_accepted_semantic_input_blocks_read_and_publication(self):
        collection = self.repository.enrich(self.command())
        self.invalidate(self.accepted.revision_id)
        before = self.counts()
        for operation in (
            lambda: self.repository.read(self.accepted.revision_id),
            lambda: self.repository.enrich(self.command(collection.collection_revision_id)),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                operation()
        self.assertEqual(before, self.counts())

    def invalidate(self, revision_id, *, current_work=False):
        reconciler = self.repository.matching.reconciliation
        actor = self.f.actor
        with reconciler._transaction(write=True) as (connection, aggregates):
            work = (
                aggregates.get(self.f.f.fixture.corpus.work_id)
                if current_work
                else aggregates.get_revision(revision_id)
            )
            event = self.f.repository._event(
                actor,
                actor.occurred_at,
                "org.research-observatory.record.invalidated.v1",
                "synthetic-reference-work-invalidation-" + new_uuid_v7(),
            )
            aggregates.invalidate(work.revision_id, event)
            change = DependencyChange(
                change_id=event.event_id,
                idempotency_key=event.idempotency_key,
                reason="SOURCE_VERSION",
                dependency_kind="source-revision",
                previous_revision_id=work.revision_id,
                replacement_revision_id=None,
                configuration_id=None,
                previous_configuration_version=None,
                replacement_configuration_version=None,
                previous_fingerprint=_projection_content_sha256(work),
                replacement_fingerprint=None,
                propagation_policy_id="dependency.material.v1",
                propagation_policy_version="1.0.0",
                actor_id=actor.actor_id,
                trace_id=actor.trace_id,
                occurred_at=actor.occurred_at,
            )
            impacts = _SqliteDependencyImpactRepository(self.f.database, self.accepted.project_id)
            preview = impacts._preview_with_connection(
                connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
            )
            impacts._begin_with_connection(
                connection, change, preview_sha256=preview.preview_sha256, run_id=new_uuid_v7(), batch_size=100
            )

    def test_corrupt_encrypted_collection_is_denied_after_reopen(self):
        collection = self.repository.enrich(self.command())
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            row = db.execute(
                "SELECT payload_sha256 FROM document_enrichments WHERE revision_id=?",
                (collection.collection_revision_id,),
            ).fetchone()
        path = self.f.f.fixture.project_root / "objects" / _object_relative_path(self.accepted.project_id, row[0])
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        with self.assertRaises(DocumentRevisionProblem):
            self.reopen().read(self.accepted.revision_id)
        self.assertEqual(self.accepted, self.f.repository.read(self.accepted.revision_id))


if __name__ == "__main__":
    unittest.main(verbosity=2)
