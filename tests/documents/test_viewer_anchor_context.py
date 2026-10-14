"""Viewer context over real encrypted canonical anchors; authored synthetic IR."""

import unittest
from contextlib import closing
from unittest.mock import patch

from research_observatory_core.document_revisions import DocumentRevisionProblem
from research_observatory_core.document_viewer_repository import LocalDocumentViewerRepository
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.object_store import _object_relative_path
from research_observatory_core.parsing.contracts import CodepointRange
from research_observatory_core.ports.document_viewer import ViewerSourceSelector
from research_observatory_core.storage import open_canonical_database

from tests.anchors import test_anchor_repository as anchors


class ViewerAnchorContextTests(unittest.TestCase):
    def setUp(self):
        self.f = anchors.AnchorRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.anchor = self.f.repository.create(self.f.command, self.f.selection)
        self.selector = ViewerSourceSelector(
            attachment_id=self.anchor.target.source.attachment_id,
            document_revision_id=self.anchor.target.source.document_revision_id,
            normalized_revision_id=self.anchor.target.revision_id,
        )

    def viewer(self):
        return LocalDocumentViewerRepository(self.f.f.reopen())

    def test_two_retained_anchors_resolve_their_distinct_exact_context_without_full_ir(self):
        second = self.f.repository.create(
            new_uuid_v7(),
            self.f.selection.model_copy(update={"normalized_range": CodepointRange(start=0, end=23)}),
        )
        with patch(
            "research_observatory_core.document_revision_repository.LocalDocumentRevisionRepository._accepted",
            side_effect=AssertionError("retained anchor resolution cannot load the full IR"),
        ):
            left = self.viewer().resolve_anchor(self.selector, anchor_id=self.anchor.anchor_id)
            right = self.viewer().resolve_anchor(self.selector, anchor_id=second.anchor_id)
        self.assertEqual(self.anchor.target, left.target)
        self.assertEqual(second.target, right.target)
        self.assertNotEqual(left.target.quote.exact, right.target.quote.exact)
        self.assertEqual(self.selector.normalized_revision_id, left.metadata.revision_id)
        self.assertEqual(left.source, right.source)

    def test_later_accepted_head_does_not_move_a_viewer_link(self):
        later = self.f.f.parse("Changed later synthetic source representation.")
        base = self.f.f.repository.read(self.selector.normalized_revision_id)
        accepted = self.f.f.reprocess_uncorrected_fixture(later, base)
        self.assertNotEqual(self.selector.normalized_revision_id, accepted.revision_id)
        result = self.viewer().resolve_anchor(self.selector, anchor_id=self.anchor.anchor_id)
        self.assertEqual(self.anchor.target, result.target)

    def test_substituted_original_revision_anchor_or_normalized_revision_delivers_no_context(self):
        for field in ("attachment_id", "document_revision_id", "normalized_revision_id"):
            with self.subTest(field=field), self.assertRaises(DocumentRevisionProblem):
                self.viewer().resolve_anchor(
                    self.selector.model_copy(update={field: new_uuid_v7()}), anchor_id=self.anchor.anchor_id
                )
        with self.assertRaises(DocumentRevisionProblem):
            self.viewer().resolve_anchor(self.selector, anchor_id=new_uuid_v7())

    def test_derive_denial_retains_original_inspection_without_returning_anchor_text(self):
        self.f.f.f.permit(derive="denied")
        viewer = self.viewer()
        with self.assertRaises(DocumentRevisionProblem):
            viewer.resolve_anchor(self.selector, anchor_id=self.anchor.anchor_id)
        self.assertEqual(self.anchor.target.source, viewer.describe(self.selector).source)

    def test_broken_protected_context_returns_canonical_revision_and_no_substitute_passage(self):
        source = self.anchor.target.source
        with closing(open_canonical_database(self.f.f.database, expected_project_id=source.project_id)) as db:
            digest = db.execute(
                "SELECT object_sha256 FROM documents WHERE revision_id=?", (self.anchor.anchor_revision_id,)
            ).fetchone()[0]
        path = self.f.f.f.fixture.project_root / "objects" / _object_relative_path(source.project_id, digest)
        damaged = bytearray(path.read_bytes())
        damaged[-1] ^= 1
        path.write_bytes(damaged)
        result = self.viewer().resolve_anchor(self.selector, anchor_id=self.anchor.anchor_id)
        self.assertEqual("broken", result.status)
        self.assertIsNone(result.target)
        self.assertEqual(source, result.source)
        self.assertEqual(self.selector.normalized_revision_id, result.metadata.revision_id)
        self.assertEqual("completed", result.propagation.state)

    def test_resource_denial_precedes_context_decryption_and_is_not_a_broken_anchor(self):
        with (
            patch(
                "research_observatory_core.document_viewer_allocations.viewer_core_allowance", return_value=24 * 1024**2
            ),
            patch(
                "research_observatory_core.object_store._verified_stored_reader",
                side_effect=AssertionError("over-budget retained context cannot be decrypted"),
            ),
            self.assertRaisesRegex(DocumentRevisionProblem, "viewer-resource-limit"),
        ):
            self.viewer().resolve_anchor(self.selector, anchor_id=self.anchor.anchor_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
