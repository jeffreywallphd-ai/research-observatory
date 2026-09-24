"""Authenticated Core API and worker wiring, with synthetic external transport."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

# ruff: noqa: E402
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest

from tests.connectors import test_connector_workflow as fixtures
from tests.service import test_core_api as api


class ConnectorApiTests(unittest.TestCase):
    consent_service = fixtures.ConnectorWorkflowTests.consent_service
    worker_service = fixtures.ConnectorWorkflowTests.worker_service
    intent = fixtures.ConnectorWorkflowTests.intent
    policy = fixtures.ConnectorWorkflowTests.policy

    def setUp(self):
        fixtures.ConnectorWorkflowTests.setUp(self)
        self.app = create_app(
            projects=self.projects,
            privacy=self.privacy,
            intents=self.service,
            connectors=self.worker,
            capability_digest=capability_token_digest(api.TOKEN),
            expected_authority=api.AUTHORITY,
        )

    def tearDown(self):
        fixtures.ConnectorWorkflowTests.tearDown(self)

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


if __name__ == "__main__":
    unittest.main()
