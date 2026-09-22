"""Bounded repeated manifest reads must retain complete current rights checks."""

import unittest
from unittest.mock import patch

from research_observatory_core.import_commit_repository import SqliteImportCommitRepository
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ports.import_previews import PreviewDraftChange, PreviewProblem

from tests.data import test_import_commit_publication as fixture


class ImportManifestAccessTests(unittest.TestCase):
    def setUp(self):
        self.publication = fixture.ImportCommitPublicationTests(methodName="runTest")
        self.publication.setUp()
        self.addCleanup(self.publication.doCleanups)
        self.output = self.publication.publish()
        self.fixture = self.publication.fixture
        self.repository = self.fixture.repository

    def test_unchanged_pages_reuse_only_complete_current_authorization_and_cold_adapter_rescans(self):
        repository = self.repository
        with patch.object(repository, "_page_decision_revisions", wraps=repository._page_decision_revisions) as scans:
            repository.manifest(self.output.revision_id)
            first = scans.call_count
            self.assertGreater(first, 0)
            repository.manifest_members(self.output.revision_id, after=0, limit=1)
            repository.manifest_members(self.output.revision_id, after=1, limit=1)
            self.assertEqual(first, scans.call_count)
        cold = SqliteImportCommitRepository(self.fixture.database, self.fixture.inputs.project_id)
        with patch.object(cold, "_page_decision_revisions", wraps=cold._page_decision_revisions) as scans:
            cold.manifest_members(self.output.revision_id, after=0, limit=1)
            self.assertGreater(scans.call_count, 0)

    def test_off_page_revocation_invalidates_warm_authority_and_failed_checks_are_never_memoized(self):
        f = self.fixture
        self.repository.manifest(self.output.revision_id)
        item = self.repository.draft_page(f.inputs.preview.preview_id, revision=1, after=1, limit=1)[0]
        denied = ImportRights(
            store=ImportPermission(value="permitted", basis="researcher-confirmed"),
            inspect=ImportPermission(value="denied", basis="researcher-confirmed"),
        )
        self.repository.revise_draft(
            f.inputs.preview.preview_id,
            PreviewDraftChange(
                expected_revision=1,
                actor=f.fixture.fixture.actor,
                decisions=(item.decision.model_copy(update={"rights": denied}),),
            ),
        )
        with patch.object(
            self.repository, "_page_decision_revisions", wraps=self.repository._page_decision_revisions
        ) as scans:
            for _ in range(2):
                previous = scans.call_count
                with self.assertRaisesRegex(PreviewProblem, "rights-denied"):
                    self.repository.manifest_members(self.output.revision_id, after=0, limit=1)
                self.assertGreater(scans.call_count, previous)

    def test_new_draft_requires_complete_recheck_even_when_rights_stay_permitted(self):
        f = self.fixture
        self.repository.manifest(self.output.revision_id)
        self.repository.revise_draft(
            f.inputs.preview.preview_id,
            PreviewDraftChange(
                expected_revision=1,
                actor=f.fixture.fixture.actor,
            ),
        )
        with patch.object(
            self.repository, "_page_decision_revisions", wraps=self.repository._page_decision_revisions
        ) as scans:
            self.repository.manifest_members(self.output.revision_id, after=0, limit=1)
            self.assertGreater(scans.call_count, 0)

    def test_default_revocation_denies_warmed_read(self):
        f = self.fixture
        preview = f.inputs.preview.preview_id
        self.repository.manifest(self.output.revision_id)
        denied = ImportRights(
            store=ImportPermission(value="permitted", basis="researcher-confirmed"),
            inspect=ImportPermission(value="denied", basis="researcher-confirmed"),
        )
        self.repository.revise_draft(
            preview, PreviewDraftChange(expected_revision=1, actor=f.fixture.fixture.actor, rights=denied)
        )
        with self.assertRaisesRegex(PreviewProblem, "rights-denied"):
            self.repository.manifest(self.output.revision_id)

    def test_undo_of_permitted_edit_rechecks_new_revision(self):
        f = self.fixture
        preview = f.inputs.preview.preview_id
        self.repository.revise_draft(preview, PreviewDraftChange(expected_revision=1, actor=f.fixture.fixture.actor))
        self.repository.manifest(self.output.revision_id)
        self.repository.revise_draft(
            preview, PreviewDraftChange(expected_revision=2, actor=f.fixture.fixture.actor, restore_revision=1)
        )
        with patch.object(
            self.repository, "_page_decision_revisions", wraps=self.repository._page_decision_revisions
        ) as scans:
            self.repository.manifest(self.output.revision_id)
            self.assertGreater(scans.call_count, 0)

    def test_warmed_scan_does_not_bypass_cancelled_preview(self):
        self.repository.manifest(self.output.revision_id)
        self.repository.cancel(self.fixture.inputs.preview.preview_id, actor=self.fixture.actor)
        with self.assertRaisesRegex(PreviewProblem, "closed"):
            self.repository.manifest_members(self.output.revision_id, after=0, limit=1)

    def test_publication_replay_rechecks_rights_even_after_warmed_read(self):
        self.repository.manifest(self.output.revision_id)
        with patch.object(
            self.repository, "_page_decision_revisions", wraps=self.repository._page_decision_revisions
        ) as scans:
            with self.repository._transaction(None) as connection:
                self.repository._manifest_access(connection, self.output.revision_id)
            self.assertGreater(scans.call_count, 0)
