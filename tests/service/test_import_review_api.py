"""Authenticated JSON transport to real project/preview storage; no native UI claim."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest

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
