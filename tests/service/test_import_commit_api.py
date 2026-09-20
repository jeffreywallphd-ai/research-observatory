"""Authenticated commit transport over actual local storage and durable workers."""

import unittest
from pathlib import Path

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.import_preview_repository import sqlite_import_preview_repository
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ports.import_previews import PreviewDraftChange

from tests.service.test_import_review_api import ImportReviewApiTests


class ImportCommitApiTests(unittest.TestCase):
    def setUp(self):
        self.api = ImportReviewApiTests(methodName="runTest")
        self.api.setUp()
        self.addCleanup(self.api.doCleanups)
        self.post = self.api.post
        self.request = new_uuid_v7()
        self.assertEqual(200, self.post("begin-review").status_code)

    def start(self, **values):
        return self.post("commit/start", requestId=self.request, revision=1, **values)

    def test_prepared_request_can_be_discovered_without_renderer_memory_or_automatic_execution(self):
        self.assertIsNone(self.post("commit/latest").json())
        prepared = self.post("commit/prepare", revision=1)
        self.assertEqual(200, prepared.status_code)
        self.assertIsNone(prepared.json()["jobId"])
        self.assertEqual(prepared.json(), self.post("commit/latest").json())
        self.assertEqual(prepared.json(), self.post("commit/prepare", revision=1).json())
        self.request = prepared.json()["requestId"]
        self.start()
        self.assertEqual("runnable", self.post("commit/latest").json()["jobState"])
        self.api.fixture.service.run_pending()
        self.assertEqual("succeeded", self.post("commit/latest").json()["jobState"])

    def test_commit_status_manifest_pages_and_request_replay(self):
        empty = self.post("commit/status", requestId=self.request)
        self.assertEqual(200, empty.status_code)
        self.assertIsNone(empty.json()["jobId"])
        self.assertIsNone(self.post("manifest").json())
        started = self.start()
        self.assertEqual(200, started.status_code)
        self.assertEqual("runnable", started.json()["jobState"])
        self.assertIsNone(started.json()["manifest"])
        self.api.fixture.service.run_pending()
        ready = self.post("commit/status", requestId=self.request)
        self.assertEqual(200, ready.status_code)
        self.assertEqual("succeeded", ready.json()["jobState"])
        manifest = ready.json()["manifest"]
        self.assertEqual(1, manifest["selectedCount"])
        self.assertEqual(1, manifest["createdCount"])
        self.assertEqual(manifest, self.post("manifest").json())
        self.assertEqual(manifest, self.start().json()["manifest"])
        first = self.post("manifest/members", revisionId=manifest["revisionId"], limit=1).json()
        self.assertFalse(first["complete"])
        self.assertFalse(first["records"][0]["included"])
        final = self.post("manifest/members", revisionId=manifest["revisionId"], after=first["nextAfter"]).json()
        self.assertTrue(final["complete"])
        self.assertTrue(final["records"][0]["included"])
        self.assertIsNotNone(final["records"][0]["sourceRecordRevisionId"])
        self.assertNotIn("Synthetic", str(final))
        self.assertEqual("no-store", ready.headers["Cache-Control"])

    def test_cancel_requires_exact_request_job_and_does_not_cancel_preview(self):
        started = self.start().json()
        self.assertEqual(409, self.post("commit/cancel", requestId=self.request, jobId=new_uuid_v7()).status_code)
        cancelled = self.post("commit/cancel", requestId=self.request, jobId=started["jobId"])
        self.assertEqual(200, cancelled.status_code)
        self.assertEqual("cancelled", cancelled.json()["jobState"])
        self.assertIsNone(cancelled.json()["manifest"])
        self.assertEqual(200, self.post("records", revision=1).status_code)
        self.assertIsNone(self.post("manifest").json())

    def test_strict_input_authentication_and_uncertain_outcome_disclosure(self):
        self.assertEqual(422, self.post("commit/start", requestId=self.request, revision=True).status_code)
        self.assertEqual(422, self.start(actorId=new_uuid_v7()).status_code)
        self.assertEqual(422, self.post("manifest/members", revisionId=new_uuid_v7(), limit=101).status_code)
        denied = self.api.client.post(
            "/projects/imports/commit/start",
            json={**self.api.address, "requestId": self.request, "revision": 1},
            headers={"Authorization": "Bearer " + "b" * 64},
        )
        self.assertEqual(401, denied.status_code)
        self.start()
        conflict = self.start(previousManifestRevisionId=new_uuid_v7())
        self.assertEqual(409, conflict.status_code)
        self.assertNotIn("No canonical import was published", conflict.text)
        self.assertIn("status", conflict.json()["detail"])
        self.assertNotIn(self.api.fixture.root, conflict.text)

    def test_manifest_and_completed_status_deny_later_rights_revocation(self):
        self.start()
        self.api.fixture.service.run_pending()
        manifest = self.post("manifest").json()
        f = self.api.fixture
        repository = sqlite_import_preview_repository(Path(f.root) / "state/project.sqlite3", f.project_id)
        row = repository.draft_page(self.api.preview, revision=1, after=1, limit=1)[0]
        denied = ImportRights(
            store=ImportPermission(value="permitted", basis="researcher-confirmed"),
            inspect=ImportPermission(value="denied", basis="researcher-confirmed"),
        )
        repository.revise_draft(
            self.api.preview,
            PreviewDraftChange(
                expected_revision=1,
                actor=f.service.actor("1" * 32),
                decisions=(row.decision.model_copy(update={"rights": denied}),),
            ),
        )
        for route, values in [
            ("manifest", {}),
            ("manifest/members", {"revisionId": manifest["revisionId"], "after": 0, "limit": 1}),
            ("commit/status", {"requestId": self.request}),
        ]:
            with self.subTest(route=route):
                response = self.post(route, **values)
                self.assertEqual(403, response.status_code)
                self.assertNotIn("Synthetic", response.text)

    def test_cross_preview_manifest_and_request_substitution_are_denied(self):
        self.start()
        self.api.fixture.service.run_pending()
        manifest = self.post("manifest").json()
        second = self.api.fixture.intake(b"title,doi\nOther,10.99999/other\n")
        self.api.fixture.service.schedule(self.api.fixture.root, second)
        self.api.fixture.service.run_pending()
        self.api.address["previewId"] = second
        self.post("begin-review")
        self.assertEqual(409, self.post("manifest", revisionId=manifest["revisionId"]).status_code)
        self.assertEqual(409, self.post("manifest/members", revisionId=manifest["revisionId"]).status_code)
        self.assertEqual(409, self.post("commit/status", requestId=self.request).status_code)
