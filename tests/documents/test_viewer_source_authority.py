"""Real SQLCipher/current native session and encrypted original viewer authority."""

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

from research_observatory_core.document_revisions import DocumentRevisionProblem
from research_observatory_core.document_viewer_repository import LocalDocumentViewerRepository
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.document_viewer import ViewerSourceSelector
from research_observatory_core.ports.object_store import ObjectAccessDenied
from research_observatory_core.storage import open_canonical_database

from tests.documents import test_document_revision_repository as revisions


class ViewerSourceAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.f = revisions.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.viewer = LocalDocumentViewerRepository(self.f.repository)
        self.selector = ViewerSourceSelector(
            attachment_id=self.f.f.source.attachment_id,
            document_revision_id=self.f.f.source.document_revision_id,
        )

    def test_inspect_only_original_remains_readable_but_derivative_still_requires_derive(self):
        self.f.f.permit(derive="denied")
        metadata = self.viewer.describe(self.selector)
        self.assertEqual(self.f.f.source, metadata.source)
        self.assertEqual(b"Synthetic", self.viewer.read_range(self.selector, start=0, end=9))
        with self.assertRaises(ObjectAccessDenied):
            self.f.f.fixture.store.open_parse_source(self.f.f.source, actor=self.f.actor)

    def test_normalized_revision_resolves_exact_original_and_substitutions_deny(self):
        parsed = self.f.parse()
        normalized = self.f.repository.accept(self.f.command(parsed))
        selector = self.selector.model_copy(update={"normalized_revision_id": normalized.revision_id})
        metadata = self.viewer.describe(selector)
        self.assertEqual(normalized.revision_id, metadata.normalized_revision_id)
        self.assertNotEqual(normalized.revision_id, metadata.source.document_revision_id)
        self.assertEqual(b"Synthetic", self.viewer.read_range(selector, start=0, end=9))
        for field in ("attachment_id", "document_revision_id", "normalized_revision_id"):
            with self.subTest(field=field), self.assertRaises(DocumentRevisionProblem):
                self.viewer.read_range(selector.model_copy(update={field: new_uuid_v7()}), start=0, end=9)

    def test_current_inspect_denial_applies_to_metadata_and_every_range(self):
        self.f.f.fixture.publish_right(
            self.f.f.candidate, value="denied", predecessor=self.f.f.policy.revision_id, inspect=True
        )
        for action in (
            lambda: self.viewer.describe(self.selector),
            lambda: self.viewer.read_range(self.selector, start=0, end=9),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                action()

    def test_owned_expected_identity_is_not_an_authorization_grant(self):
        self.f.f.permit(derive="denied")
        expected = self.viewer.describe(self.selector)
        self.assertEqual(
            b"Synthetic", self.viewer._read_owned_range(self.selector, expected, start=0, end=9)
        )
        self.f.f.fixture.publish_right(
            self.f.f.candidate, value="denied", predecessor=self.f.f.policy.revision_id, inspect=True
        )
        with self.assertRaises(DocumentRevisionProblem):
            self.viewer._read_owned_range(self.selector, expected, start=0, end=9)

    def test_owned_expected_identity_substitutions_deny_before_plaintext_read(self):
        from research_observatory_core import object_store

        expected = self.viewer.describe(self.selector)
        replacements = [
            expected.model_copy(update={"source": expected.source.model_copy(update={field: new_uuid_v7()})})
            for field in ("project_id", "attachment_id", "document_revision_id", "work_revision_id")
        ]
        replacements.append(expected.model_copy(update={"normalized_revision_id": new_uuid_v7()}))
        with patch.object(object_store, "_pull_frame", wraps=object_store._pull_frame) as authenticated_frame:
            for substituted in replacements:
                with self.subTest(source=substituted), self.assertRaises(DocumentRevisionProblem):
                    self.viewer._read_owned_range(self.selector, substituted, start=0, end=9)
            authenticated_frame.assert_not_called()

    def test_structured_text_is_bounded_exact_revision_and_does_not_create_anchors(self):
        parsed = self.f.parse()
        normalized = self.f.repository.accept(self.f.command(parsed))
        selector = self.selector.model_copy(update={"normalized_revision_id": normalized.revision_id})
        node = next(item for item in normalized.structure.nodes if item.text is not None)
        value = self.viewer.text_chunk(selector, node_id=node.node_id, offset=0)
        self.assertEqual(selector.normalized_revision_id, value.metadata.normalized_revision_id)
        self.assertEqual(node.node_id, value.node_id)
        self.assertLessEqual(len(value.text), 4096)
        self.assertEqual((), self.f.repository.source_anchors().list(normalized.revision_id))
        for offset in (-1, True, 1.5, 2**30):
            with self.subTest(offset=offset), self.assertRaises(DocumentRevisionProblem):
                self.viewer.text_chunk(selector, node_id=node.node_id, offset=offset)
        with self.assertRaises(DocumentRevisionProblem):
            self.viewer.text_chunk(selector, node_id=new_uuid_v7(), offset=0)

    def test_derive_revocation_denies_structured_text_but_preserves_original_inspection(self):
        parsed = self.f.parse()
        normalized = self.f.repository.accept(self.f.command(parsed))
        selector = self.selector.model_copy(update={"normalized_revision_id": normalized.revision_id})
        node = next(item for item in normalized.structure.nodes if item.text is not None)
        self.f.f.permit(derive="denied")
        with self.assertRaises(DocumentRevisionProblem):
            self.viewer.text_chunk(selector, node_id=node.node_id, offset=0)
        self.assertEqual(b"Synthetic", self.viewer.read_range(selector, start=0, end=9))

    def test_derive_revoked_after_artifact_context_closes_denies_text_delivery(self):
        parsed = self.f.parse()
        normalized = self.f.repository.accept(self.f.command(parsed))
        selector = self.selector.model_copy(update={"normalized_revision_id": normalized.revision_id})
        node = next(item for item in normalized.structure.nodes if item.text is not None)
        store_type = type(self.f.f.fixture.store)
        read_context = store_type._read_authorized_document_context

        def revoke_after_close(store, *args, **kwargs):
            result = read_context(store, *args, **kwargs)
            self.f.f.permit(derive="denied")
            return result

        with (
            patch.object(store_type, "_read_authorized_document_context", revoke_after_close),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.viewer.text_chunk(selector, node_id=node.node_id, offset=0)

    def test_source_history_is_immutable_and_substituted_source_field_denies(self):
        with (
            closing(open_canonical_database(self.f.database, expected_project_id=self.f.f.source.project_id)) as db,
            self.assertRaises(sqlite3.DatabaseError),
        ):
            db.execute(
                "UPDATE document_attachment_candidates SET work_revision_id=? WHERE candidate_id=?",
                (new_uuid_v7(), self.f.f.source.candidate_id),
            )
        with self.assertRaises(ObjectAccessDenied):
            self.f.f.fixture.store._read_inspected_document_range(
                self.f.f.source.model_copy(update={"work_revision_id": new_uuid_v7()}),
                start=0,
                end=9,
                actor=self.f.actor,
            )
        self.assertEqual(b"Synthetic", self.viewer.read_range(self.selector, start=0, end=9))

    def test_rights_changed_after_reader_close_deny_delivery_of_successful_old_bytes(self):
        store = self.f.f.fixture.store
        original = store._read_inspected_document_range

        def revoke_after_close(_store, *args, **kwargs):
            value = original(*args, **kwargs)
            self.f.f.fixture.publish_right(
                self.f.f.candidate, value="denied", predecessor=self.f.f.policy.revision_id, inspect=True
            )
            return value

        with (
            patch.object(type(store), "_read_inspected_document_range", revoke_after_close),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.viewer.read_range(self.selector, start=0, end=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
