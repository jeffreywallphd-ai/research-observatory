"""Native-only intake protocol over actual authenticated Core/project/object ports."""

from __future__ import annotations

import base64
import hashlib
import unittest
import uuid

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest

from tests.service import test_import_preview_service as fixture


class ImportIntakeApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportPreviewServiceTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
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
        self.project = {"root": self.fixture.root, "projectId": self.fixture.project_id}

    def session(self):
        response = self.client.post("/native/imports/context", json=self.project)
        self.assertEqual(200, response.status_code)
        return {**self.project, "sessionId": response.json()["sessionId"]}

    def post(self, route, context, **values):
        return self.client.post("/native/imports/" + route, json={**context, **values})

    def create(self, context, **override):
        return self.post(
            "create",
            context,
            **{
                "sourceName": "synthetic.csv",
                "formatName": "csv",
                "encoding": "utf-8",
                "rights": fixture.fixture.RIGHTS.model_dump(mode="json", by_alias=True),
                **override,
            },
        )

    def test_native_intake_roundtrip_uses_encrypted_chunks_and_real_worker(self):
        context = self.session()
        created = self.create(context)
        self.assertEqual(200, created.status_code)
        preview = created.json()["previewId"]
        address = {**context, "previewId": preview}
        raw = b"title,doi\nSynthetic intake,10.99999/EXAMPLE\n"
        self.assertEqual(
            200, self.post("chunk", address, ordinal=1, data=base64.b64encode(raw).decode("ascii")).status_code
        )
        sealed = self.post(
            "seal", address, sourceSha256=hashlib.sha256(raw).hexdigest(), byteLength=len(raw), chunkCount=1
        )
        self.assertEqual(200, sealed.status_code)
        self.assertEqual("source-sealed", sealed.json()["state"])
        self.assertEqual(200, self.post("schedule", address).status_code)
        self.fixture.service.run_pending()
        status = self.post("status", address)
        self.assertEqual(200, status.status_code)
        self.assertEqual("succeeded", status.json()["jobState"])
        self.assertEqual("parse-completed", status.json()["state"])
        self.assertNotIn("Synthetic intake", status.text)
        self.assertNotIn(self.fixture.root, status.text)
        review = self.client.post(
            "/projects/imports/begin-review", json={"root": self.fixture.root, "previewId": preview}
        )
        self.assertEqual(200, review.status_code)
        self.assertEqual(2, review.json()["recordCount"])

    def test_project_identity_and_closed_reopened_session_cannot_be_substituted(self):
        context = self.session()
        preview = self.create(context).json()["previewId"]
        wrong = {**context, "projectId": str(uuid.uuid4())}
        self.assertEqual(409, self.create(wrong).status_code)
        self.assertEqual(409, self.create({**context, "sessionId": "f" * 32}).status_code)
        self.fixture.service.detach(self.fixture.root)
        self.fixture.projects.close(root=self.fixture.root, trace_id="1" * 32)
        self.fixture.projects.open(root=self.fixture.root, trace_id="1" * 32)
        renewed = self.session()
        self.assertNotEqual(context["sessionId"], renewed["sessionId"])
        self.assertEqual(409, self.post("chunk", {**context, "previewId": preview}, ordinal=1, data="WA==").status_code)
        self.assertEqual(200, self.post("cancel", {**renewed, "previewId": preview}).status_code)
        self.assertEqual("cancelled", self.post("status", {**renewed, "previewId": preview}).json()["state"])

    def test_claimed_seal_digest_is_not_accepted_as_verified_source(self):
        context = self.session()
        address = {**context, "previewId": self.create(context).json()["previewId"]}
        raw = b"title\nSynthetic mismatch\n"
        self.assertEqual(200, self.post("chunk", address, ordinal=1, data=base64.b64encode(raw).decode()).status_code)
        self.assertEqual(
            200, self.post("seal", address, sourceSha256="0" * 64, byteLength=len(raw), chunkCount=1).status_code
        )
        self.assertEqual(200, self.post("schedule", address).status_code)
        self.fixture.service.run_pending()
        status = self.post("status", address)
        self.assertEqual(200, status.status_code)
        self.assertNotEqual("succeeded", status.json()["jobState"])
        self.assertNotEqual("parse-completed", status.json()["state"])
        review = self.client.post(
            "/projects/imports/begin-review", json={"root": self.fixture.root, "previewId": address["previewId"]}
        )
        self.assertEqual(409, review.status_code)

    def test_cancellation_before_worker_claim_leaves_no_reviewable_import(self):
        context = self.session()
        address = {**context, "previewId": self.create(context).json()["previewId"]}
        raw = b"title\nSynthetic cancellation\n"
        self.assertEqual(200, self.post("chunk", address, ordinal=1, data=base64.b64encode(raw).decode()).status_code)
        self.assertEqual(
            200,
            self.post(
                "seal", address, sourceSha256=hashlib.sha256(raw).hexdigest(), byteLength=len(raw), chunkCount=1
            ).status_code,
        )
        self.assertEqual(200, self.post("schedule", address).status_code)
        self.assertEqual(200, self.post("cancel", address).status_code)
        self.fixture.service.run_pending()
        self.assertEqual("cancelled", self.post("status", address).json()["state"])
        review = self.client.post(
            "/projects/imports/begin-review", json={"root": self.fixture.root, "previewId": address["previewId"]}
        )
        self.assertEqual(409, review.status_code)

    def test_intake_denies_unknown_rights_actor_path_and_malformed_or_oversized_chunks(self):
        context = self.session()
        self.assertEqual(403, self.create(context, rights={}).status_code)
        self.assertEqual(422, self.create(context, sourceName="../synthetic.csv").status_code)
        self.assertEqual(422, self.create(context, actor={"actorId": "synthetic"}).status_code)
        address = {**context, "previewId": self.create(context).json()["previewId"]}
        for data in ["not base64!", "", base64.b64encode(b"X" * (128 * 1024 + 1)).decode("ascii")]:
            self.assertEqual(422, self.post("chunk", address, ordinal=1, data=data).status_code)
        self.assertEqual(409, self.post("chunk", address, ordinal=2, data="WA==").status_code)
        self.assertEqual(200, self.post("cancel", address).status_code)
        self.assertEqual(409, self.post("chunk", address, ordinal=1, data="WA==").status_code)
        self.assertEqual(409, self.post("schedule", address).status_code)

    def test_native_routes_keep_existing_authentication_and_transport_bounds(self):
        response = self.client.post(
            "/native/imports/context", json=self.project, headers={"Authorization": "Bearer " + "b" * 64}
        )
        self.assertEqual(401, response.status_code)
        response = self.client.post(
            "/native/imports/create", content=iter([b" " * 500000] * 2), headers={"Content-Type": "application/json"}
        )
        self.assertEqual(413, response.status_code)
        self.assertNotIn(self.fixture.root, response.text)
        # Private native commands are not generated into the renderer API contract.
        self.assertFalse(any(path.startswith("/native/") for path in self.client.get("/openapi.json").json()["paths"]))


if __name__ == "__main__":
    unittest.main()
