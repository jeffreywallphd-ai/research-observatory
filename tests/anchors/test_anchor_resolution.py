"""Exact-revision resolution/staleness over real SQLCipher and protected objects.

The parser output and downstream evidence graphs are declared synthetic fixtures.
"""

import sys
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.object_store import _object_relative_path  # noqa: E402
from research_observatory_core.ports.repositories import AggregateRevisionDraft  # noqa: E402
from research_observatory_core.repositories import (  # noqa: E402
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
)
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.anchors import test_anchor_repository as predecessor  # noqa: E402
from tests.parsing import contract_fixtures  # noqa: E402


class AnchorResolutionTests(unittest.TestCase):
    def setUp(self):
        self.f = predecessor.AnchorRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.repository = self.f.repository
        self.anchor = self.repository.create(self.f.command, self.f.selection)
        self.revision = self.f.accepted.revision_id

    def resolve(self, repository=None):
        return (repository or self.repository).resolve(self.anchor.anchor_id, expected_revision_id=self.revision)

    def damage(self):
        fixture = self.f.f
        with closing(
            open_canonical_database(fixture.database, expected_project_id=self.anchor.target.project_id)
        ) as db:
            digest = db.execute(
                "SELECT object_sha256 FROM documents WHERE revision_id=?", (self.anchor.anchor_revision_id,)
            ).fetchone()[0]
        path = fixture.f.fixture.project_root / "objects" / _object_relative_path(self.anchor.target.project_id, digest)
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)

    def dependent(self, source_revision=None):
        fixture = self.f.f
        factory = create_sqlite_unit_of_work_factory(fixture.database, self.anchor.target.project_id)
        with factory() as unit:
            source = unit.aggregates.get_revision(source_revision or self.anchor.anchor_revision_id)
            evidence = unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=new_uuid_v7(),
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="evidence",
                    created_at=fixture.now,
                    modified_at=fixture.now,
                    display_label_observed="Synthetic anchor-dependent evidence",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                    provenance_inputs=(source,),
                    dependency_coverage="complete",
                    material_dependencies=fixture.repository._dependencies((source,)),
                ),
                fixture.repository._event(fixture.actor, fixture.now, "evidence.created", "fixture." + new_uuid_v7()),
                expected_revision=None,
            )
            unit.commit()
        return evidence

    def impact_counts(self):
        fixture = self.f.f
        with closing(
            open_canonical_database(fixture.database, expected_project_id=self.anchor.target.project_id)
        ) as db:
            return {
                table: db.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]
                for table in ("dependency_impact_runs", "dependency_stale_causes", "provenance_events", "outbox_events")
            }

    def test_exact_context_metadata_and_old_revision_survive_reopen_without_pdf_or_ir(self):
        with patch(
            "research_observatory_core.document_revision_repository.LocalDocumentRevisionRepository._accepted",
            side_effect=AssertionError("common retained context must not load the full IR"),
        ):
            result = self.resolve(self.f.reopen())
        self.assertEqual("fallback", result.status)
        self.assertEqual("structural-text", result.selector_used)
        self.assertEqual(self.anchor.target, result.target)
        self.assertEqual(self.revision, result.metadata.revision_id)
        self.assertEqual(self.anchor.target.source, result.source)
        self.assertEqual("unverified", result.scholarly_verification)
        later = self.f.f.parse("Later accepted synthetic source text.")
        self.f.f.repository.accept(self.f.f.command(later, expected=self.revision))
        self.assertEqual(result, self.resolve(self.f.reopen()))

    def test_authenticated_broken_context_commits_exact_stale_dependents_once_after_reopen(self):
        direct = self.dependent()
        transitive = self.dependent(direct.revision_id)
        unrelated = self.dependent(self.revision)
        self.damage()
        broken = self.resolve()
        self.assertEqual("broken", broken.status)
        self.assertIsNone(broken.target)
        self.assertEqual("completed", broken.propagation.state)
        self.assertEqual(2, broken.propagation.stale_count)
        impacts = sqlite_dependency_impact_repository(self.f.f.f.fixture.project_root, self.anchor.target.project_id)
        for evidence in (direct, transitive):
            self.assertEqual(1, len(impacts.stale_states(output_revision_id=evidence.revision_id)))
        self.assertEqual((), impacts.stale_states(output_revision_id=unrelated.revision_id))
        before = self.impact_counts()
        self.assertEqual(broken, self.resolve(self.f.reopen()))
        self.assertEqual(before, self.impact_counts())

    def test_denied_or_substituted_context_never_publishes_a_broken_anchor(self):
        self.dependent()
        self.damage()
        before = self.impact_counts()
        for anchor_id, expected in ((new_uuid_v7(), self.revision), (self.anchor.anchor_id, new_uuid_v7())):
            with self.assertRaises(DocumentRevisionProblem):
                self.repository.resolve(anchor_id, expected_revision_id=expected)
            self.assertEqual(before, self.impact_counts())
        self.f.f.f.permit(derive="denied")
        after_rights = self.impact_counts()

        def derive_denials():
            with closing(
                open_canonical_database(self.f.f.database, expected_project_id=self.anchor.target.project_id)
            ) as db:
                return db.execute(
                    "SELECT count(*) FROM rights_use_decisions WHERE use_action='derive' AND decision_code<>'allow'"
                ).fetchone()[0]

        before_denials = derive_denials()
        with self.assertRaises(DocumentRevisionProblem):
            self.resolve()
        self.assertEqual(after_rights, self.impact_counts())
        self.assertEqual(before_denials + 1, derive_denials())

    def test_missing_canonical_outbox_is_denied_and_does_not_invalidate(self):
        self.damage()
        fixture = self.f.f
        with closing(
            open_canonical_database(fixture.database, expected_project_id=self.anchor.target.project_id)
        ) as db:
            db.execute("DELETE FROM outbox_events WHERE idempotency_key=?", ("document.anchor." + self.f.command,))
        before = self.impact_counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.resolve()
        self.assertEqual(before, self.impact_counts())

    def test_interruption_rolls_back_invalidation_stale_rows_and_run_then_retry_succeeds(self):
        self.dependent()
        self.damage()
        before = self.impact_counts()
        with (
            patch(
                "research_observatory_core.source_anchor_repository._publication_step",
                side_effect=RuntimeError("synthetic resolution interruption"),
            ),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.resolve()
        self.assertEqual(before, self.impact_counts())
        self.assertEqual("completed", self.resolve().propagation.state)

    def test_citation_links_preserve_exact_canonical_candidates_and_uncertainty(self):
        for resolution, candidate_ids in (
            ("unresolved", []),
            ("candidate", ["ref-entry-1"]),
            ("ambiguous", ["ref-entry-1", "ref-entry-2"]),
        ):

            def rich(value, resolution=resolution, candidate_ids=candidate_ids):
                binding, receipts = value["binding"], value["rawArtifacts"]
                value.update(contract_fixtures.rich_ir_wire())
                value["binding"], value["rawArtifacts"] = binding, receipts
                value["figures"][0]["previewStageId"] = None
                value["citations"][0]["resolution"] = resolution
                value["citations"][0]["referenceCandidates"] = candidate_ids

            retained = self.f.f.parse(change=rich)
            expected = self.f.f.repository.history(self.f.accepted.document_id)[-1]
            accepted = self.f.f.repository.accept(self.f.f.command(retained, expected=expected))
            citation = accepted.structure.citations[0]
            links = self.f.reopen().citation_links(accepted.revision_id, citation.citation_id, limit=1)
            self.assertEqual(resolution, links.resolution)
            self.assertEqual("unverified", links.scholarly_verification)
            self.assertEqual("[1]", links.marker.quote.exact)
            self.assertEqual(citation.reference_candidates[:1], tuple(row.reference_id for row in links.targets))
            if links.next_reference_id is not None:
                second = self.repository.citation_links(
                    accepted.revision_id, citation.citation_id, after_reference_id=links.next_reference_id, limit=1
                )
                self.assertEqual(citation.reference_candidates[1:], tuple(row.reference_id for row in second.targets))
            with self.assertRaises(DocumentRevisionProblem):
                self.repository.citation_links(self.revision, citation.citation_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
