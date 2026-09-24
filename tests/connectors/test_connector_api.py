"""Authenticated Core API and worker wiring, with synthetic external transport."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

# ruff: noqa: E402
from research_observatory_core.app import create_app
from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.connectors import test_connector_workflow as fixtures
from tests.connectors.test_connector_transport import BytesStream
from tests.connectors.test_scholarly_mapping import fixture, request
from tests.service import test_core_api as api
from tests.service import test_import_preview_service as runtime_fixture


class ConnectorApiTests(fixtures.ConnectorWorkflowFixture):
    def setUp(self):
        super().setUp()
        self.app = create_app(
            projects=self.projects,
            privacy=self.privacy,
            intents=self.service,
            connectors=self.worker,
            capability_digest=capability_token_digest(api.TOKEN),
            expected_authority=api.AUTHORITY,
        )

    def test_authenticated_preview_confirmation_durable_status_and_session_fence(self):
        with api.authenticated_client(self.app) as client:
            payload = {
                "root": self.root,
                "request": self.request.model_dump(mode="json", by_alias=True),
                "retention": self.rights.model_dump(mode="json", by_alias=True),
            }
            denied = client.post("/projects/connectors/previews", json=payload, headers={"Authorization": ""})
            self.assertEqual(401, denied.status_code)
            injected = client.post("/projects/connectors/previews", json=payload | {"authorityStamp": {"allow": True}})
            self.assertEqual(422, injected.status_code)
            preview = client.post("/projects/connectors/previews", json=payload)
            self.assertEqual(200, preview.status_code, preview.text)
            self.assertEqual("no-store", preview.headers["cache-control"])
            self.assertEqual([], self.calls)
            body = preview.json()
            confirmed = client.post(
                "/projects/connectors/confirmations",
                json={"root": self.root, "previewId": body["previewId"], "confirmation": body["confirmation"]},
            )
            self.assertEqual(200, confirmed.status_code, confirmed.text)
            address = {"root": self.root, "jobId": confirmed.json()["jobId"]}
            deadline = time.monotonic() + 10
            while True:
                status = client.post("/projects/connectors/jobs/status", json=address)
                self.assertEqual(200, status.status_code, status.text)
                if status.json()["state"] in {"succeeded", "failed", "cancelled"} or time.monotonic() > deadline:
                    break
                time.sleep(0.05)
            self.assertEqual("succeeded", status.json()["state"], status.text)
            self.assertEqual(1, len(self.calls))
            self.assertIsNotNone(self.repository.checkpoint(self.request))
            self.assertEqual(200, client.post("/projects/close", json={"root": self.root}).status_code)
            self.assertEqual(200, client.post("/projects/open", json={"root": self.root}).status_code)
            old = client.post(
                "/projects/connectors/confirmations",
                json={"root": self.root, "previewId": body["previewId"], "confirmation": body["confirmation"]},
            )
            self.assertEqual(403, old.status_code)
            self.assertEqual(1, len(self.calls))

    def test_unavailable_runtime_and_bounded_request_do_not_disclose_queries(self):
        with api.authenticated_client() as client:
            unavailable = client.get("/projects/connectors/capabilities")
            self.assertEqual(503, unavailable.status_code)
            oversized = client.post(
                "/projects/connectors/previews",
                content=b"q" * (256 * 1024 + 1),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(413, oversized.status_code)
            self.assertNotIn("qqqqq", oversized.text)
            self.assertEqual([], self.calls)


class ConnectorRuntimeCompositionTests(unittest.TestCase):
    def test_runtime_factory_uses_protected_repositories_and_real_worker(self):
        helper = runtime_fixture.ImportRuntimeCompositionTests()
        app = helper.application(NativeWorkflowContext("b" * 32, "c" * 32))
        calls = []

        async def respond(wire):
            calls.append(wire)
            response = httpx2.Response(200, json=fixture("openalex"))
            return httpx2.Response(200, headers=response.headers, stream=BytesStream(response.content))

        with (
            tempfile.TemporaryDirectory(prefix="ro-connector-runtime-") as temporary,
            patch(
                "research_observatory_core.repositories._windows_worker_capacity",
                return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
            ),
            helper.client(app) as client,
        ):
            runtime = app.state.runtime
            self.worker, self.service, self.privacy = runtime.connectors, runtime.intents, runtime.privacy
            self.assertIsNotNone(self.worker)
            self.worker._transport_factory = lambda: httpx2.MockTransport(respond)
            created = client.post(
                "/projects",
                json={
                    "parentDirectory": temporary,
                    "directoryName": "synthetic-connector",
                    "displayName": "Synthetic connector",
                    "primaryUseCase": "theory-synthesis",
                    "researchObjective": "Synthetic scholarly metadata",
                },
            )
            self.assertEqual(200, created.status_code, created.text)
            self.root = created.json()["root"]
            self.assertEqual(200, client.post("/projects/open", json={"root": self.root}).status_code)
            self.request = request("openalex", projectId=created.json()["projectId"])
            authority = fixtures.authority_fixtures.ConnectorAuthorityFixture()
            authority.root, authority.service, authority.privacy = self.root, self.service, self.privacy
            authority.intent()
            authority.policy()
            payload = {
                "root": self.root,
                "request": self.request.model_dump(mode="json", by_alias=True),
                "retention": {
                    "rights": {
                        name: {"value": "permitted", "basis": "researcher-confirmed"} for name in ("store", "inspect")
                    },
                    "retainBody": True,
                },
            }
            preview = client.post("/projects/connectors/previews", json=payload)
            self.assertEqual(200, preview.status_code, preview.text)
            confirmed = client.post(
                "/projects/connectors/confirmations",
                json={
                    "root": self.root,
                    "previewId": preview.json()["previewId"],
                    "confirmation": preview.json()["confirmation"],
                },
            )
            self.assertEqual(200, confirmed.status_code, confirmed.text)
            address = {"root": self.root, "jobId": confirmed.json()["jobId"]}
            deadline = time.monotonic() + 10
            while True:
                status = client.post("/projects/connectors/jobs/status", json=address)
                self.assertEqual(200, status.status_code, status.text)
                if status.json()["state"] in {"succeeded", "failed", "cancelled"} or time.monotonic() > deadline:
                    break
                time.sleep(0.05)
            self.assertEqual("succeeded", status.json()["state"], status.text)
            self.assertEqual(1, len(calls))
            database = Path(self.root) / "state/project.sqlite3"
            self.assertNotEqual(b"SQLite format 3\x00", database.read_bytes()[:16])
            self.assertEqual(200, client.post("/projects/close", json={"root": self.root}).status_code)
            self.assertEqual(200, client.post("/projects/open", json={"root": self.root}).status_code)
            self.assertEqual("succeeded", client.post("/projects/connectors/jobs/status", json=address).json()["state"])
            self.assertEqual(1, len(calls))


if __name__ == "__main__":
    unittest.main()
