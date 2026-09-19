"""Authenticated JSON transport to real project/preview storage; no native UI claim."""

from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.import_preview_repository import sqlite_import_preview_repository
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights, review_record
from research_observatory_core.ports.import_previews import PreviewDraftChange

from tests.service import test_import_preview_service as fixture


class ImportReviewApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportPreviewServiceTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.preview = self.fixture.intake()
        self.fixture.service.schedule(self.fixture.root, self.preview)
        self.fixture.service.run_pending()
        app = create_app(
            projects=self.fixture.projects,
            privacy=self.fixture.privacy,
            intents=self.fixture.intents,
            imports=self.fixture.service,
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        self.client = self.enterContext(
            TestClient(
                app,
                base_url="http://127.0.0.1:49152",
                headers={"Authorization": "Bearer " + "a" * 64},
                client=("127.0.0.1", 50000),
            )
        )
        self.address = {"root": self.fixture.root, "previewId": self.preview}

    def post(self, route, **values):
        return self.client.post("/projects/imports/" + route, json={**self.address, **values})

    def test_authenticated_review_mapping_exclusion_and_report_round_trip(self):
        self.assertEqual(200, self.post("begin-review").status_code)
        page = self.post("records", revision=1, after=1).json()
        record = page["records"][0]
        mapped = self.post("mapping", expectedRevision=1, columns=[{"index": 0, "target": "title"}])
        self.assertEqual(200, mapped.status_code)
        edited = self.post(
            "edit", expectedRevision=2, records=[{"ordinal": 2, "recordKey": record["recordKey"]}], included=False
        )
        self.assertEqual(200, edited.status_code)
        self.assertEqual(3, edited.json()["revision"])
        report = self.post("report", revision=3).json()
        self.assertTrue(report["complete"])
        self.assertIn("excluded", report["csv"])
        self.assertNotIn("Synthetic", report["csv"])
        self.assertEqual(409, self.post("mapping", expectedRevision=1, columns=[]).status_code)
        current = self.post("review").json()
        self.assertEqual(3, current["revision"])

    def test_summary_is_explicit_revision_bound_and_never_an_unavailable_zero(self):
        self.post("begin-review")
        before = self.post("summary", revision=1)
        self.assertEqual(200, before.status_code)
        self.assertIsNone(before.json()["counts"])
        self.assertIsNone(before.json()["jobId"])
        self.assertEqual(409, self.post("summary/groups", revision=1, reason="doi").status_code)
        started = self.post("summary/start", revision=1)
        self.assertEqual(200, started.status_code)
        self.assertEqual("runnable", started.json()["jobState"])
        self.assertIsNone(started.json()["counts"])
        self.fixture.service.run_pending()
        ready = self.post("summary", revision=1)
        self.assertEqual(200, ready.status_code)
        self.assertEqual("succeeded", ready.json()["jobState"])
        self.assertEqual(1, ready.json()["counts"]["includedRecords"])
        self.assertEqual(1, ready.json()["counts"]["coverage"]["doi"])
        self.assertEqual("no-store", ready.headers["Cache-Control"])
        self.assertEqual([], self.post("summary/groups", revision=1, reason="doi").json()["groups"])
        self.post("mapping", expectedRevision=1, mode="automatic", columns=[])
        self.assertEqual(409, self.post("summary", revision=1).status_code)
        self.assertIsNone(self.post("summary", revision=2).json()["counts"])

    def test_summary_cancel_is_separate_from_preview_and_rejects_other_job(self):
        self.post("begin-review")
        started = self.post("summary/start", revision=1)
        self.assertEqual(200, started.status_code)
        job = started.json()["jobId"]
        cancelled = self.post("summary/cancel", revision=1, jobId=job)
        self.assertEqual(200, cancelled.status_code)
        self.assertEqual("cancelled", cancelled.json()["jobState"])
        self.assertIsNone(cancelled.json()["counts"])
        self.assertEqual(200, self.post("records", revision=1).status_code)
        parser_job = self.post("status").json()["jobId"]
        self.assertEqual(409, self.post("summary/cancel", revision=1, jobId=parser_job).status_code)
        self.assertEqual(422, self.post("summary/start", revision=True).status_code)
        self.assertEqual(422, self.post("summary/members", revision=1, reason="title", groupKey="a" * 64).status_code)

    def test_duplicate_groups_and_noncontiguous_members_are_complete_and_current(self):
        self.preview = self.fixture.intake(
            b"title,doi\nSynthetic A,10.99999/A\nSynthetic B,10.99999/B\n"
            b"Synthetic A,10.99999/A\nSynthetic B,10.99999/B\n"
        )
        self.address["previewId"] = self.preview
        self.fixture.service.schedule(self.fixture.root, self.preview)
        self.fixture.service.run_pending()
        self.post("begin-review")
        self.post("summary/start", revision=1)
        self.fixture.service.run_pending()
        self.assertEqual(4, self.post("summary", revision=1).json()["counts"]["candidateRecords"])
        for reason in ("raw", "doi"):
            first = self.post("summary/groups", revision=1, reason=reason, after=None, limit=1).json()
            self.assertFalse(first["complete"])
            group = first["groups"][0]
            self.assertEqual(2, group["memberCount"])
            last = self.post("summary/groups", revision=1, reason=reason, after=first["nextAfter"], limit=1).json()
            self.assertTrue(last["complete"])
            self.assertNotEqual(group["groupKey"], last["groups"][0]["groupKey"])
            members = self.post(
                "summary/members", revision=1, reason=reason, groupKey=group["groupKey"], after=0, limit=1
            ).json()
            self.assertFalse(members["complete"])
            remaining = self.post(
                "summary/members",
                revision=1,
                reason=reason,
                groupKey=group["groupKey"],
                after=members["nextAfter"],
                limit=1,
            ).json()
            self.assertTrue(remaining["complete"])
            self.assertEqual(members["nextAfter"] + 2, remaining["nextAfter"])
            self.assertEqual(group["firstOrdinal"], members["records"][0]["ordinal"])
        self.post("mapping", expectedRevision=1, mode="automatic", columns=[])
        self.assertEqual(409, self.post("summary/groups", revision=1, reason="doi").status_code)
        self.assertEqual(
            409, self.post("summary/members", revision=1, reason="doi", groupKey=group["groupKey"]).status_code
        )

    def test_undo_walks_effective_history_without_redo_or_automatic_stale_retry(self):
        self.assertEqual(200, self.post("begin-review").status_code)
        row = self.post("records", revision=1, after=1).json()["records"][0]
        records = [{"ordinal": row["ordinal"], "recordKey": row["recordKey"]}]
        self.assertEqual(200, self.post("edit", expectedRevision=1, records=records, included=False).status_code)
        self.assertEqual(200, self.post("mapping", expectedRevision=2, mode="automatic", columns=[]).status_code)
        restored = self.post("undo", expectedRevision=3)
        self.assertEqual(200, restored.status_code)
        self.assertEqual(4, restored.json()["revision"])
        self.assertEqual(1, restored.json()["undoTargetRevision"])
        self.assertFalse(self.post("records", revision=4, after=1).json()["records"][0]["included"])
        self.assertEqual(409, self.post("undo", expectedRevision=3).status_code)
        self.assertEqual(422, self.post("undo", expectedRevision=4, restoreRevision=3).status_code)
        self.assertEqual(200, self.post("undo", expectedRevision=4).status_code)
        self.assertTrue(self.post("records", revision=5, after=1).json()["records"][0]["included"])
        self.assertIsNone(self.post("review").json()["undoTargetRevision"])
        self.assertEqual(409, self.post("undo", expectedRevision=5).status_code)
        self.assertEqual(200, self.post("edit", expectedRevision=5, records=records, included=False).status_code)
        self.assertEqual(5, self.post("review").json()["undoTargetRevision"])
        self.assertEqual(200, self.post("undo", expectedRevision=6).status_code)
        self.assertIsNone(self.post("review").json()["undoTargetRevision"])
        self.assertTrue(self.post("records", revision=7, after=1).json()["records"][0]["included"])
        # Prior excluded revision remains readable, not overwritten by undo.
        self.assertFalse(self.post("records", revision=2, after=1).json()["records"][0]["included"])

    def test_validation_authentication_and_project_close_cannot_leak_records(self):
        self.post("begin-review")
        response = self.post("records", revision=True)
        self.assertEqual(422, response.status_code)
        denied = self.client.post(
            "/projects/imports/records",
            json={**self.address, "revision": 1},
            headers={"Authorization": "Bearer " + "b" * 64},
        )
        self.assertEqual(401, denied.status_code)
        self.fixture.service.detach(self.fixture.root)
        self.fixture.projects.close(root=self.fixture.root, trace_id="1" * 32)
        closed = self.post("records", revision=1)
        self.assertEqual(409, closed.status_code)
        self.assertNotIn("Synthetic", closed.text)
        self.assertNotIn(self.fixture.root, closed.text)

    def test_undo_cannot_reopen_restricted_source_via_authenticated_route(self):
        self.assertEqual(200, self.post("begin-review").status_code)
        repository = sqlite_import_preview_repository(
            Path(self.fixture.root) / "state/project.sqlite3", self.fixture.project_id
        )
        row = repository.draft_page(self.preview, revision=1, after=1, limit=1)[0]
        denied = ImportRights(inspect=ImportPermission(value="denied", basis="researcher-confirmed"))
        repository.revise_draft(
            self.preview,
            PreviewDraftChange(
                expected_revision=1,
                actor=self.fixture.service.actor("1" * 32),
                decisions=(review_record(row.record, included=False, fields=(), rights=denied),),
            ),
        )
        self.assertEqual(403, self.post("undo", expectedRevision=2).status_code)
        self.assertEqual(2, self.post("review").json()["revision"])
        self.assertEqual(403, self.post("records", revision=1, after=1).status_code)

    def test_automatic_column_targets_roundtrip_and_single_change_preserves_other_fields(self):
        self.assertEqual(200, self.post("begin-review").status_code)
        header = self.post("records", revision=1, after=0, limit=1).json()["records"][0]
        detail = self.post(
            "detail", revision=1, ordinal=header["ordinal"], recordKey=header["recordKey"], section="raw"
        ).json()
        columns = [{"index": field["index"], "target": field["target"]} for field in detail["fields"]]
        self.assertEqual([{"index": 0, "target": "title"}, {"index": 1, "target": "doi"}], columns)
        self.assertEqual(200, self.post("mapping", expectedRevision=1, columns=columns).status_code)
        record = self.post("records", revision=2, after=1, limit=1).json()["records"][0]
        self.assertEqual("Synthetic", record["title"]["text"])
        columns[0]["target"] = "container"
        self.assertEqual(200, self.post("mapping", expectedRevision=2, columns=columns).status_code)
        effective = self.post(
            "detail", revision=3, ordinal=record["ordinal"], recordKey=record["recordKey"], section="effective"
        ).json()["fields"]
        self.assertEqual(
            {"container": "Synthetic", "doi": "10.99999/example"}, {f["name"]: f["value"] for f in effective}
        )

    def test_actual_request_bytes_are_bounded_before_json_parsing(self):
        # A missing/false Content-Length must not bypass the body bound.
        response = self.client.post(
            "/projects/imports/review",
            content=iter([b" " * 500000, b" " * 500000]),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(413, response.status_code)
        self.assertNotIn("Synthetic", response.text)


if __name__ == "__main__":
    unittest.main()
