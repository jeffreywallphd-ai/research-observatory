"""Actual protected canonical publication with authored citation IR, no models."""

import copy
import sys
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_citation_repository import LocalDocumentCitationRepository  # noqa: E402
from research_observatory_core.document_citations import CitationEnrichmentCommand  # noqa: E402
from research_observatory_core.document_reference_repository import LocalDocumentReferenceRepository  # noqa: E402
from research_observatory_core.document_references import ReferenceEnrichmentCommand  # noqa: E402
from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.repositories import _material_registration_with_connection  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.documents import test_document_revision_repository as fixtures  # noqa: E402

BODY = "Synthetic [1]. Missing [9].\n"
RAW = BODY + "[1] Synthetic Author (2024). Synthetic reference alpha. doi:10.99999/synthetic-a"


def citation_ir(value, *, raw=RAW, identifier="10.99999/synthetic-a"):
    body = value["nodes"][0]
    reference = copy.deepcopy(body)
    projection = body["text"]["projectionId"]

    def span(start, end):
        return dict(
            projectionId=projection, normalizedRange=dict(start=start, end=end), rawRanges=[dict(start=start, end=end)]
        )

    body["text"] = span(0, len(BODY))
    body["locator"]["rawRanges"] = body["text"]["rawRanges"]
    marker = copy.deepcopy(body)
    marker.update(
        stagedId="citation-node", order=1, kind="citation-marker", parentId=body["stagedId"], text=span(10, 13)
    )
    marker["locator"]["rawRanges"] = marker["text"]["rawRanges"]
    reference.update(stagedId="reference-node", order=2, kind="reference", text=span(len(BODY), len(raw)))
    reference["locator"]["rawRanges"] = reference["text"]["rawRanges"]
    value["nodes"].extend([marker, reference])
    value["references"] = [
        dict(
            stagedId="reference-1",
            nodeId="reference-node",
            order=0,
            rawText=reference["text"],
            identifiers=[dict(scheme="doi", observed=identifier)],
        )
    ]
    value["citations"] = [
        dict(
            stagedId="citation-1",
            nodeId="citation-node",
            marker=span(10, 13),
            referenceCandidates=["reference-1"],
            resolution="candidate",
        )
    ]


class CitationRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        parsed = self.f.parse(RAW, change=citation_ir)
        self.accepted = self.f.repository.accept(self.f.command(parsed))
        self.resolve = lambda _address: self.f.f.fixture.corpus.source
        self.references = LocalDocumentReferenceRepository(self.f.reopen(), resolve=self.resolve)
        self.ref = self.references.enrich(self.reference_command())
        self.repository = self.reopen()

    def reopen(self):
        return LocalDocumentCitationRepository(self.f.reopen(), resolve=self.resolve)

    def reference_command(self, expected=None):
        return ReferenceEnrichmentCommand(
            command_id=new_uuid_v7(), revision_id=self.accepted.revision_id, expected_collection_revision_id=expected
        )

    def command(self, expected=None, reference=None, command_id=None):
        return CitationEnrichmentCommand(
            command_id=command_id or new_uuid_v7(),
            revision_id=self.accepted.revision_id,
            reference_collection_revision_id=reference or self.ref.collection_revision_id,
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

    def test_encrypted_publication_exact_retry_restart_and_source_identity(self):
        before = self.f.repository.read(self.accepted.revision_id)
        command = self.command()
        collection = self.repository.enrich(command)
        counts = self.counts()
        self.assertEqual(collection, self.repository.enrich(command))
        self.assertEqual(collection, self.reopen().read(self.accepted.revision_id))
        self.assertEqual(counts, self.counts())
        self.assertEqual(["candidate", "unresolved"], [c.resolution for c in collection.entries])
        self.assertEqual("[1]", collection.entries[0].anchor.quote.exact)
        self.assertEqual(self.accepted.structure.citations[0].citation_id, collection.entries[0].canonical_citation_id)
        self.assertIsNone(collection.entries[1].canonical_citation_id)
        self.assertEqual(self.ref.collection_revision_id, collection.reference_collection_revision_id)
        self.assertEqual(before, self.f.repository.read(self.accepted.revision_id))
        self.assertNotIn(BODY.encode(), self.f.database.read_bytes())
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            reg = _material_registration_with_connection(
                db, self.accepted.project_id, collection.collection_revision_id
            )
            self.assertIn(self.ref.collection_revision_id, {d.revision_id for d in reg.dependencies})
            rows = db.execute(
                "SELECT element_id,element_order FROM document_enrichment_elements WHERE collection_revision_id=?",
                (collection.collection_revision_id,),
            ).fetchall()
        self.assertEqual([(self.accepted.structure.citations[0].citation_id, 0)], [tuple(r) for r in rows])

    def test_reference_refresh_blocks_saved_context_read_and_retry_then_explicit_refresh_appends(self):
        command = self.command()
        first = self.repository.enrich(command)
        self.ref = self.references.enrich(self.reference_command(self.ref.collection_revision_id))
        before = self.counts()
        for operation in (
            lambda: self.repository.read(self.accepted.revision_id),
            lambda: self.repository.enrich(command),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                operation()
        self.assertEqual(before, self.counts())
        second = self.repository.enrich(self.command(first.collection_revision_id))
        self.assertEqual(first.collection_id, second.collection_id)
        self.assertEqual(first.collection_revision_id, second.previous_collection_revision_id)
        self.assertEqual(self.ref.collection_revision_id, second.reference_collection_revision_id)
        self.assertEqual(second, self.reopen().read(self.accepted.revision_id))

    def test_current_rights_principal_and_target_authority_are_required(self):
        command = self.command()
        self.repository.enrich(command)
        self.f.actor = replace(self.f.actor, actor_type="worker")
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.read(self.accepted.revision_id)
        self.f.actor = replace(self.f.actor, actor_type="human")
        self.f.f.permit(derive="denied")
        before = self.counts()
        for operation in (
            lambda: self.repository.read(self.accepted.revision_id),
            lambda: self.repository.enrich(command),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                operation()
        self.assertEqual(before, self.counts())

    def test_missing_reference_predecessor_and_command_reuse_are_content_free_conflicts(self):
        before = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.enrich(self.command(reference=new_uuid_v7()))
        self.assertEqual(before, self.counts())
        command = self.command()
        first = self.repository.enrich(command)
        before = self.counts()
        for invalid in (self.command(), self.command(first.collection_revision_id, command_id=command.command_id)):
            with self.assertRaises(DocumentRevisionProblem):
                self.repository.enrich(invalid)
        self.assertEqual(before, self.counts())

    def test_cancel_and_fault_before_commit_preserve_prior_durable_state(self):
        before = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.enrich(self.command(), cancelled=lambda: True)
        self.assertEqual(before, self.counts())

        def fail(step):
            if step == "citation-before-commit":
                raise RuntimeError("synthetic-citation-interruption")

        with (
            patch("research_observatory_core.document_citation_repository._publication_step", side_effect=fail),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.repository.enrich(self.command())
        self.assertEqual(before, self.counts())
        self.assertIsNotNone(self.repository.enrich(self.command()))

    def test_concurrent_reference_refresh_cannot_publish_stale_target_context(self):
        fired = []

        def refresh(step):
            if step == "citation-prepared" and not fired:
                fired.append(True)
                self.ref = self.references.enrich(self.reference_command(self.ref.collection_revision_id))

        with (
            patch("research_observatory_core.document_citation_repository._publication_step", side_effect=refresh),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.repository.enrich(self.command())
        self.assertEqual([True], fired)
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM document_enrichments WHERE enrichment_kind='citation-contexts'"
                ).fetchone()[0],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
