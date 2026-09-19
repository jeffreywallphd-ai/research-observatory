"""Native-only intake protocol over actual authenticated Core/project/object ports."""

from __future__ import annotations

import base64
import hashlib
import unittest
import uuid
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.import_preview_repository import sqlite_import_preview_repository
from research_observatory_core.ingestion.import_drafts import ImportPermission
from research_observatory_core.ingestion.preview_workflow import fingerprint
from research_observatory_core.ingestion.reference_imports import PARSER_VERSION, ImportLimits
from research_observatory_core.ports.import_previews import PreviewDraftChange
from research_observatory_core.storage import open_canonical_database

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

    def test_explicit_delimiters_survive_project_reopen_and_reach_real_worker(self):
        for delimiter in ("\t", ";"):
            with self.subTest(delimiter=repr(delimiter)):
                context = self.session()
                created = self.create(context, delimiter=delimiter)
                self.assertEqual(200, created.status_code)
                preview = created.json()["previewId"]
                address = {**context, "previewId": preview}
                raw = f'title{delimiter}doi\n"Synthetic{delimiter} title"{delimiter}10.99999/EXAMPLE\n'.encode()
                self.assertEqual(
                    200, self.post("chunk", address, ordinal=1, data=base64.b64encode(raw).decode()).status_code
                )
                self.assertEqual(
                    200,
                    self.post(
                        "seal", address, sourceSha256=hashlib.sha256(raw).hexdigest(), byteLength=len(raw), chunkCount=1
                    ).status_code,
                )
                self.assertEqual(200, self.post("schedule", address).status_code)
                self.fixture.service.detach(self.fixture.root)
                self.fixture.projects.close(root=self.fixture.root, trace_id="1" * 32)
                self.fixture.projects.open(root=self.fixture.root, trace_id="1" * 32)
                renewed = {**self.session(), "previewId": preview}
                self.fixture.service.run_pending()
                self.assertEqual("succeeded", self.post("status", renewed).json()["jobState"])
                repository = sqlite_import_preview_repository(
                    Path(self.fixture.root) / "state/project.sqlite3", self.fixture.project_id
                )
                self.assertEqual(delimiter, repository.read(preview).delimiter)
                rows = repository.records_page(preview, after=0, limit=25)
                self.assertEqual(2, len(rows))
                self.assertEqual(f"Synthetic{delimiter} title", rows[1].fields[0].raw_value)
                self.assertEqual("10.99999/example", rows[1].candidates[1].value)
                review = self.client.post(
                    "/projects/imports/begin-review", json={"root": self.fixture.root, "previewId": preview}
                )
                self.assertEqual(200, review.status_code)
                self.assertEqual(delimiter, review.json()["delimiter"])
                self.assertEqual(delimiter, repository.draft(preview).authority.delimiter)
                with closing(
                    open_canonical_database(
                        Path(self.fixture.root) / "state/project.sqlite3", expected_project_id=self.fixture.project_id
                    )
                ) as connection:
                    recorded = connection.execute(
                        "SELECT d.fingerprint FROM material_dependencies d JOIN import_parse_completions c "
                        "ON c.project_id=d.project_id AND c.receipt_revision_id=d.output_revision_id "
                        "WHERE c.preview_id=? AND d.configuration_id='import.parser-configuration'",
                        (preview,),
                    ).fetchall()
                expected = fingerprint(
                    {
                        "parserVersion": PARSER_VERSION,
                        "format": "csv",
                        "encoding": "utf-8",
                        "delimiter": delimiter,
                        "limits": asdict(ImportLimits()),
                    }
                )
                self.assertEqual([expected], [row[0] for row in recorded])
        for invalid in ({"delimiter": "|"}, {"formatName": "ris", "delimiter": ";"}):
            self.assertEqual(422, self.create(self.session(), **invalid).status_code)

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

    def test_library_discovery_is_bounded_and_reopens_persisted_previews(self):
        context = self.session()
        ids = [self.create(context, sourceName=f"synthetic-{index}.csv").json()["previewId"] for index in range(3)]
        first = self.client.post("/projects/imports/list", json={"root": self.fixture.root, "after": None, "limit": 2})
        self.assertEqual(200, first.status_code)
        self.assertEqual(ids[:2], [item["previewId"] for item in first.json()["items"]])
        self.assertFalse(first.json()["complete"])
        second = self.client.post(
            "/projects/imports/list", json={"root": self.fixture.root, "after": first.json()["nextAfter"], "limit": 2}
        )
        self.assertEqual([ids[2]], [item["previewId"] for item in second.json()["items"]])
        self.assertTrue(second.json()["complete"])
        for item in first.json()["items"]:
            self.assertNotIn("root", item)
            self.assertNotIn("rights", item)
            self.assertNotIn("sessionId", item)
            self.assertEqual("created", item["state"])
        self.fixture.service.detach(self.fixture.root)
        self.fixture.projects.close(root=self.fixture.root, trace_id="1" * 32)
        self.assertEqual(
            409,
            self.client.post(
                "/projects/imports/status", json={"root": self.fixture.root, "previewId": ids[0]}
            ).status_code,
        )
        self.fixture.projects.open(root=self.fixture.root, trace_id="1" * 32)
        status = self.client.post("/projects/imports/status", json={"root": self.fixture.root, "previewId": ids[0]})
        self.assertEqual(200, status.status_code)
        self.assertEqual("synthetic-0.csv", status.json()["sourceName"])
        cancelled = self.client.post("/projects/imports/cancel", json={"root": self.fixture.root, "previewId": ids[0]})
        self.assertEqual(200, cancelled.status_code)
        self.assertEqual("cancelled", cancelled.json()["state"])
        for invalid in [{"after": "bogus", "limit": 2}, {"after": None, "limit": 26}, {"after": None, "limit": True}]:
            self.assertEqual(
                422, self.client.post("/projects/imports/list", json={"root": self.fixture.root, **invalid}).status_code
            )

    def test_discovery_status_and_cancel_recheck_inspection_rights(self):
        preview = self.fixture.intake()
        self.fixture.service.schedule(self.fixture.root, preview)
        self.fixture.service.run_pending()
        repository = sqlite_import_preview_repository(
            Path(self.fixture.root) / "state/project.sqlite3", self.fixture.project_id
        )
        actor = self.fixture.service.actor("2" * 32)
        draft = repository.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=actor))
        denied = draft.authority.rights.model_copy(
            update={"inspect": ImportPermission(value="denied", basis="researcher-confirmed")}
        )
        repository.revise_draft(preview, PreviewDraftChange(expected_revision=1, actor=actor, rights=denied))
        for route in ("status", "cancel"):
            response = self.client.post(
                "/projects/imports/" + route, json={"root": self.fixture.root, "previewId": preview}
            )
            self.assertEqual(403, response.status_code)
            self.assertNotIn("synthetic.csv", response.text)
        discovery = self.client.post(
            "/projects/imports/list", json={"root": self.fixture.root, "after": None, "limit": 1}
        )
        self.assertEqual(200, discovery.status_code)
        self.assertEqual([], discovery.json()["items"])
        self.assertEqual(preview, discovery.json()["nextAfter"])
        self.assertFalse(discovery.json()["complete"])
        self.assertNotIn("synthetic.csv", discovery.text)

    def test_native_report_pages_bind_session_revision_and_complete_diagnostics(self):
        preview = self.fixture.intake()
        self.fixture.service.schedule(self.fixture.root, preview)
        self.fixture.service.run_pending()
        public = {"root": self.fixture.root, "previewId": preview}
        self.assertEqual(200, self.client.post("/projects/imports/begin-review", json=public).status_code)
        address = {**self.session(), "previewId": preview}
        first = self.post("report", address, revision=1, after=0, limit=1)
        self.assertEqual(200, first.status_code)
        self.assertEqual(preview, first.json()["previewId"])
        self.assertEqual(2, first.json()["recordCount"])
        self.assertEqual(1, first.json()["nextAfter"])
        self.assertFalse(first.json()["complete"])
        second = self.post("report", address, revision=1, after=1, limit=1)
        self.assertTrue(second.json()["complete"])
        self.assertEqual(2, second.json()["nextAfter"])
        self.assertTrue(second.json()["csv"].startswith("2,"))
        self.assertNotIn("Synthetic", first.text + second.text)
        self.assertNotIn("synthetic.csv", first.text + second.text)
        self.assertEqual(409, self.post("report", address, revision=2, after=0, limit=1).status_code)
        self.assertEqual(422, self.post("report", address, revision=1, after=0, limit=1, path="report.csv").status_code)
        final = self.post("report", address, revision=1, after=2, limit=1)
        self.assertEqual("", final.json()["csv"])
        self.assertTrue(final.json()["complete"])
        repository = sqlite_import_preview_repository(
            Path(self.fixture.root) / "state/project.sqlite3", self.fixture.project_id
        )
        repository.revise_draft(
            preview, PreviewDraftChange(expected_revision=1, actor=self.fixture.service.actor("2" * 32))
        )
        self.assertEqual(409, self.post("report", address, revision=1, after=2, limit=1).status_code)

    def test_report_final_authorization_rejects_earlier_record_rights_revocation(self):
        preview = self.fixture.intake()
        self.fixture.service.schedule(self.fixture.root, preview)
        self.fixture.service.run_pending()
        repository = sqlite_import_preview_repository(
            Path(self.fixture.root) / "state/project.sqlite3", self.fixture.project_id
        )
        actor = self.fixture.service.actor("2" * 32)
        draft = repository.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=actor))
        address = {**self.session(), "previewId": preview}
        self.assertEqual(200, self.post("report", address, revision=1, after=0, limit=25).status_code)
        row = repository.draft_page(preview, revision=1, after=1, limit=1)[0]
        denied = draft.authority.rights.model_copy(
            update={"inspect": ImportPermission(value="denied", basis="researcher-confirmed")}
        )
        decision = row.decision.model_copy(update={"rights": denied})
        repository.revise_draft(preview, PreviewDraftChange(expected_revision=1, actor=actor, decisions=(decision,)))
        # A historical terminal page alone would not inspect any rows. Native
        # publication requires this distinct current-head authorization instead.
        self.assertEqual(409, self.post("report", address, revision=1, after=2, limit=25).status_code)
        self.fixture.service.detach(self.fixture.root)
        self.fixture.projects.close(root=self.fixture.root, trace_id="1" * 32)
        self.fixture.projects.open(root=self.fixture.root, trace_id="1" * 32)
        self.assertEqual(409, self.post("report", address, revision=1, after=2, limit=1).status_code)


if __name__ == "__main__":
    unittest.main()
