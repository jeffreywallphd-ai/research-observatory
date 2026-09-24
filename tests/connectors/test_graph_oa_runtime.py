"""Normal Windows Core composition; synthetic provider bytes, no live query."""

from __future__ import annotations

import os
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
from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.main import create_runtime_app
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.connectors import test_connector_authority as authority_fixtures
from tests.connectors.test_connector_settings import CONTACT, KEY
from tests.connectors.test_connector_transport import BytesStream
from tests.connectors.test_graph_oa_mapping import PAPER, graph_request, oa_document, oa_request, paper
from tests.service import test_import_preview_service as runtime_fixture


@unittest.skipUnless(os.name == "nt", "Windows DPAPI and SQLCipher composition")
class GraphOaRuntimeTests(unittest.TestCase):
    def test_normal_core_worker_configuration_and_observations_survive_restart(self):
        with tempfile.TemporaryDirectory(prefix="ro-oa-graph-normal-runtime-") as directory:
            vault = Path(directory) / "vault"
            calls = []
            fail_graph = False

            async def respond(wire):
                calls.append(wire)
                if wire.url.host == "api.unpaywall.org":
                    self.assertEqual(CONTACT, wire.url.params["email"])
                    response = httpx2.Response(200, json=oa_document() | {"future": CONTACT})
                else:
                    self.assertEqual("api.semanticscholar.org", wire.url.host)
                    self.assertEqual(KEY, wire.headers["x-api-key"])
                    response = (
                        httpx2.Response(503)
                        if fail_graph
                        else httpx2.Response(200, json={"recommendedPapers": [paper() | {"future": KEY}]})
                    )
                return httpx2.Response(
                    response.status_code, headers=response.headers, stream=BytesStream(response.content)
                )

            def application(epoch):
                # This is the production factory and DPAPI adapter selection;
                # only the vault location, capacity and external HTTP are isolated.
                return create_runtime_app(
                    settings=CoreSettings(),
                    profile_vault_root=vault,
                    workflow_context=NativeWorkflowContext(epoch * 32, "c" * 32),
                    capability_digest=capability_token_digest("a" * 64),
                    expected_authority="127.0.0.1:49152",
                )

            helper = runtime_fixture.ImportRuntimeCompositionTests()
            with patch(
                "research_observatory_core.repositories._windows_worker_capacity",
                return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
            ):
                first = application("b")
                with helper.client(first) as client:
                    created = client.post(
                        "/projects",
                        json={
                            "parentDirectory": directory,
                            "directoryName": "synthetic-sources",
                            "displayName": "Synthetic sources",
                            "primaryUseCase": "theory-synthesis",
                            "researchObjective": "Synthetic source composition",
                        },
                    )
                    self.assertEqual(200, created.status_code, created.text)
                    root, identity = created.json()["root"], created.json()["projectId"]
                    self.assertEqual(200, client.post("/projects/open", json={"root": root}).status_code)
                    runtime = first.state.runtime
                    runtime.connectors._transport_factory = lambda: httpx2.MockTransport(respond)
                    authority = authority_fixtures.ConnectorAuthorityFixture()
                    authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
                    authority.intent(providers=("semantic-scholar", "unpaywall"))
                    authority.policy()
                    for provider, key, contact in (("unpaywall", None, CONTACT), ("semantic-scholar", KEY, None)):
                        configured = client.post(
                            "/native/connectors/configuration/replace",
                            json={
                                "root": root,
                                "projectId": identity,
                                "providerId": provider,
                                "key": key,
                                "contact": contact,
                                "expectedVersion": None,
                            },
                        )
                        self.assertEqual(200, configured.status_code, configured.text)
                        self.assertNotIn(CONTACT, configured.text)
                        self.assertNotIn(KEY, configured.text)
                    self.assertEqual([], calls)
                    value = oa_request(projectId=identity, invocationId=new_uuid_v7())
                    job = self.execute(client, root, value)
                    self.assertEqual("succeeded", job["state"])
                    saved = runtime.connectors._adapters(Path(root), identity).pages.replay(value)
                    self.assertIsNotNone(saved)
                    self.assertNotIn(CONTACT, saved.model_dump_json())
                    self.assertEqual("applied", saved.response.redaction)
                    self.assertEqual(200, client.post("/projects/close", json={"root": root}).status_code)
                second = application("d")
                with helper.client(second) as client:
                    self.assertEqual(200, client.post("/projects/open", json={"root": root}).status_code)
                    runtime = second.state.runtime
                    runtime.connectors._transport_factory = lambda: httpx2.MockTransport(respond)
                    states = client.get("/projects/connectors/capabilities")
                    self.assertEqual(200, states.status_code)
                    self.assertTrue(all(item["configuration"] == "ready" for item in states.json()["items"]))
                    prior = client.post("/projects/connectors/jobs/status", json={"root": root, "jobId": job["jobId"]})
                    self.assertEqual("succeeded", prior.json()["state"])
                    query = {
                        "kind": "recommendations",
                        "positiveSeeds": [{"scheme": "semantic-scholar", "value": PAPER}],
                        "negativeSeeds": [],
                    }
                    value2 = graph_request(query, projectId=identity, invocationId=new_uuid_v7())
                    self.assertEqual("succeeded", self.execute(client, root, value2)["state"])
                    saved = runtime.connectors._adapters(Path(root), identity).pages.replay(value2)
                    self.assertNotIn(KEY, saved.model_dump_json())
                    fail_graph = True
                    value3 = value2.model_copy(
                        update={
                            "invocation_id": new_uuid_v7(),
                            "policy": value2.policy.model_copy(update={"maximum_attempts": 1}),
                        }
                    )
                    failed = self.execute(client, root, value3)
                    self.assertEqual("failed", failed["state"])
                    self.assertIn("provider-unavailable", failed["diagnosticCode"])
                    preserved = runtime.connectors._adapters(Path(root), identity).pages.replay(value2)
                    self.assertEqual(saved, preserved)
                    self.assertEqual(3, len(calls))
                    self.assertNotEqual(
                        b"SQLite format 3\x00", (Path(root) / "state/project.sqlite3").read_bytes()[:16]
                    )
                    self.assertEqual(200, client.post("/projects/close", json={"root": root}).status_code)

    def execute(self, client, root, value):
        preview = client.post(
            "/projects/connectors/previews",
            json={
                "root": root,
                "request": value.model_dump(mode="json", by_alias=True),
                "retention": {
                    "rights": {
                        name: {"value": "permitted", "basis": "researcher-confirmed"} for name in ("store", "inspect")
                    },
                    "retainBody": True,
                },
            },
        )
        self.assertEqual(200, preview.status_code, preview.text)
        confirmed = client.post(
            "/projects/connectors/confirmations",
            json={
                "root": root,
                "previewId": preview.json()["previewId"],
                "confirmation": preview.json()["confirmation"],
            },
        )
        self.assertEqual(200, confirmed.status_code, confirmed.text)
        deadline = time.monotonic() + 10
        while True:
            status = client.post(
                "/projects/connectors/jobs/status", json={"root": root, "jobId": confirmed.json()["jobId"]}
            )
            self.assertEqual(200, status.status_code, status.text)
            if status.json()["state"] in {"succeeded", "failed", "cancelled"} or time.monotonic() > deadline:
                return status.json()
            time.sleep(0.05)
