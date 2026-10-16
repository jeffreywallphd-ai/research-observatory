"""Current canonical source projection; real protected DB, synthetic Native/parser."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.lexical_source_repository import CanonicalIndexSources, IndexSourceProblem  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402

from tests.documents import test_document_revision_repository as fixtures  # noqa: E402


class IndexSourceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.attachments = self.f.f.fixture
        self.corpus = self.attachments.corpus

        def build():
            item, path = self.corpus._build_item()
            return item.model_copy(update={"work_revision_id": self.attachments.work_revision_id}), path

        self.item = self.corpus._create(build=build)
        self.sources = CanonicalIndexSources(self.f.repository, resolve=lambda _address: self.corpus.source)

    def permit(self, subject, *, previous=None, index="permitted", corpus_membership=False, expires_at=None):
        return self.attachments.rights.publish_draft(
            subject,
            tuple(
                RightsPermissionDraft(
                    use=RightsUse(action=action, purpose=purpose, destination_kind="local-project"),
                    value=index if action == "index" else "permitted",
                    basis="researcher-confirmed",
                    confidence="confirmed",
                    evidence_revision_ids=(subject.source_assertion_revision_id,),
                    license_observation_revision_id=None,
                    entitlement_revision_id=None,
                    expires_at=expires_at,
                )
                for purpose in (("local-search", "corpus-membership") if corpus_membership else ("local-search",))
                for action in (
                    ("store", "inspect", "derive", "index") if purpose == "corpus-membership" else ("inspect", "index")
                )
            ),
            previous,
            command_id=new_uuid_v7(),
            command_sha256="c" * 64,
            actor=self.f.actor,
        )

    def test_exact_search_permission_required_and_revocation_excludes_retained_metadata(self):
        denied = self.sources.capture(self.item.item_id)
        self.assertEqual((), denied.rows)
        subject = self.sources.metadata_subject(self.corpus.source)
        grant = self.permit(subject)
        allowed = self.sources.capture(self.item.item_id)
        self.assertTrue(allowed.rows)
        self.assertIn("10.99999/synthetic-a", " ".join(row.identifiers for row in allowed.rows))
        self.assertTrue(all(row.item_id == self.item.item_id for row in allowed.rows))
        self.permit(subject, previous=grant.revision_id, index="denied")
        revoked = self.sources.capture(self.item.item_id)
        self.assertEqual((), revoked.rows)
        self.assertNotEqual(allowed.authority_sha256, revoked.authority_sha256)

    def test_accepted_text_retains_canonical_node_projection_and_codepoint_span(self):
        parsed = self.f.parse("Synthetic café search passage")
        accepted = self.f.repository.accept(self.f.command(parsed))
        self.permit(self.f.f.candidate.rights_subject, previous=self.f.f.policy.revision_id)
        captured = self.sources.capture(self.item.item_id)
        text = tuple(row for row in captured.rows if row.full_text)
        self.assertTrue(text)
        projections = {value.projection_id: value for value in accepted.structure.text_projections}
        for row in text:
            self.assertEqual(accepted.revision_id, row.document_revision_id)
            self.assertEqual(row.projection_id, row.element_id)
            self.assertIn(row.projection_id, projections)
            self.assertEqual(
                projections[row.projection_id].normalized_text[row.normalized_start : row.normalized_end], row.full_text
            )
        substituted = replace(
            captured,
            rows=tuple(
                replace(row, full_text="X" * len(row.full_text)) if row.full_text else row for row in captured.rows
            ),
        )
        with (
            self.corpus.repository._transaction(write=True) as (db, _aggregates),
            self.assertRaises(IndexSourceProblem),
        ):
            self.sources.revalidate(db, substituted)


if __name__ == "__main__":
    unittest.main()
