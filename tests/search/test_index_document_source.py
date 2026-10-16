"""Real protected document storage; synthetic parser and Native inspector fixture."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402

from tests.documents import test_document_revision_repository as document_fixtures  # noqa: E402


class IndexDocumentSourceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = document_fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        parsed = self.fixture.parse("Clearly synthetic search-only normalized source")
        self.accepted = self.fixture.repository.accept(self.fixture.command(parsed))

    def permit_search_only(self, index="permitted"):
        parsed_fixture = self.fixture.f
        parsed_fixture.policy = parsed_fixture.fixture.rights.publish_draft(
            parsed_fixture.candidate.rights_subject,
            tuple(
                RightsPermissionDraft(
                    use=RightsUse(action=action, purpose="local-search", destination_kind="local-project"),
                    value=index if action == "index" else "permitted",
                    basis="researcher-confirmed",
                    confidence="confirmed",
                    evidence_revision_ids=(parsed_fixture.source.source_assertion_revision_id,),
                    license_observation_revision_id=None,
                    entitlement_revision_id=None,
                    expires_at=None,
                )
                for action in ("inspect", "index")
            ),
            parsed_fixture.policy.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="e" * 64,
            actor=self.fixture.actor,
        )

    def test_search_only_grant_reads_current_accepted_ir_without_analysis_grant(self):
        self.permit_search_only()
        actual = self.fixture.repository.read_for_index(self.accepted.revision_id)
        self.assertEqual(self.accepted, actual)
        self.assertEqual(self.accepted.content_sha256, actual.content_sha256)
        with self.assertRaises(DocumentRevisionProblem):
            self.fixture.repository.read(self.accepted.revision_id)

    def test_analysis_grant_is_not_index_authority(self):
        with self.assertRaises(DocumentRevisionProblem):
            self.fixture.repository.read_for_index(self.accepted.revision_id)

    def test_index_revocation_blocks_read_of_retained_accepted_ir(self):
        self.permit_search_only()
        self.fixture.repository.read_for_index(self.accepted.revision_id)
        self.permit_search_only(index="denied")
        with self.assertRaises(DocumentRevisionProblem):
            self.fixture.repository.read_for_index(self.accepted.revision_id)


if __name__ == "__main__":
    unittest.main()
