from __future__ import annotations

import json
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.model_catalog import ModelCatalogService  # noqa: E402
from research_observatory_core.model_registry_contracts import HostModelObservation, ModelManifest  # noqa: E402
from research_observatory_core.model_registry_repository import sqlite_model_catalog_repository  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.storage import configure_protected_database_provider  # noqa: E402

from tests.ai.test_model_registry import FixtureInventory, manifest_document  # noqa: E402
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

TOKEN = secrets.token_hex(32)
AUTHORITY = "127.0.0.1:49152"


class ModelCatalogServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-model-service-fixture-")
        self.parent = Path(self.temporary.name).resolve()
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        self.lifecycle = ProjectLifecycleService()
        project = self.lifecycle.create(
            parent_directory=str(self.parent),
            directory_name="fixture-project",
            display_name="Fixture Project",
            template_id="theory-synthesis",
            trace_id="a" * 32,
        )
        self.project = project
        self.actor = new_uuid_v7()
        self.inventory = FixtureInventory((ModelManifest.model_validate(manifest_document()),))
        self.service = ModelCatalogService(
            self.lifecycle,
            repository_factory=sqlite_model_catalog_repository,
            local_actor_id=self.actor,
            inventory=self.inventory,
            clock_ms=lambda: 1500,
        )
        self.client = TestClient(
            create_app(
                projects=self.lifecycle,
                model_catalog=self.service,
                capability_digest=capability_token_digest(TOKEN),
                expected_authority=AUTHORITY,
            ),
            base_url=f"http://{AUTHORITY}",
            client=("127.0.0.1", 50000),
        )
        self.client.__enter__()
        self.client.headers.update({"Authorization": f"Bearer {TOKEN}"})

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temporary.cleanup()

    def read(self, **changes):
        return self.client.post(
            "/projects/models",
            json={
                "root": self.project.root,
                "revision": None,
                "afterManifestId": None,
                "beforeHistoryRevision": None,
            }
            | changes,
        )

    def refresh(self, **changes):
        return self.client.post(
            "/projects/models/refresh",
            json={"root": self.project.root, "expectedRevision": 0} | changes,
            headers={"Idempotency-Key": "b" * 32},
        )

    def open(self) -> None:
        self.lifecycle.open(root=self.project.root, trace_id="a" * 32)

    def test_closed_project_and_untrusted_metadata_cannot_discover_or_mutate(self) -> None:
        self.assertEqual(409, self.read().status_code)
        self.assertEqual(409, self.refresh().status_code)
        self.open()
        attempts: tuple[dict[str, object], ...] = (
            {"actorId": self.actor},
            {"available": True},
            {"manifests": []},
            {"allowed": True},
        )
        for extra in attempts:
            self.assertEqual(422, self.refresh(**extra).status_code)
        self.assertEqual(0, self.read().json()["revision"])

    def test_read_is_side_effect_free_refresh_is_versioned_and_history_is_visible(self) -> None:
        self.open()
        initial = self.read()
        self.assertEqual(200, initial.status_code)
        self.assertEqual([], initial.json()["entries"])
        self.assertEqual([], initial.json()["history"])
        self.assertEqual(0, initial.json()["revision"])
        refreshed = self.refresh()
        self.assertEqual(200, refreshed.status_code, refreshed.text)
        self.assertEqual(1, refreshed.json()["revision"])
        self.assertEqual("ready", refreshed.json()["entries"][0]["availability"])
        self.assertEqual("not-evaluated", refreshed.json()["entries"][0]["eligibility"])
        self.assertEqual([1], [item["revision"] for item in refreshed.json()["history"]])
        self.assertEqual(refreshed.json(), self.refresh().json())
        self.inventory.observations = ()
        reread = self.read(revision=1).json()
        self.assertEqual("unknown", reread["entries"][0]["availability"])
        self.assertEqual(1, reread["revision"])
        self.assertNotIn("actorId", refreshed.text)
        self.assertNotIn("fixture-command", refreshed.text)

    def test_transport_authentication_and_missing_core_actor_fail_closed(self) -> None:
        self.open()
        self.client.headers.pop("Authorization")
        self.assertIn(self.read().status_code, (401, 403))
        self.client.headers.update({"Authorization": f"Bearer {TOKEN}"})
        self.service._local_actor_id = None
        failed = self.refresh()
        self.assertEqual(503, failed.status_code)
        self.assertEqual("RO-CORE-MODEL-ACTOR-UNAVAILABLE", failed.json()["code"])
        self.assertEqual(0, self.read().json()["revision"])

    def test_read_only_compatibility_keeps_existing_catalog_inspectable_and_unchanged(self) -> None:
        self.open()
        self.assertEqual(200, self.refresh().status_code)
        self.lifecycle.close(root=self.project.root, trace_id="a" * 32)
        path = Path(self.project.root) / "project.ro.json"
        document = json.loads(path.read_text("utf-8"))
        document["applicationCompatibility"] = {"minimum": "0.2.0", "maximumExclusive": "1.0.0"}
        path.write_text(json.dumps(document), encoding="utf-8")
        opened = self.lifecycle.open(root=self.project.root, trace_id="a" * 32)
        self.assertEqual("read-only", opened.access_mode)
        before = self.read().json()
        denied = self.refresh(expectedRevision=1)
        self.assertEqual(409, denied.status_code)
        self.assertEqual("RO-CORE-PROJECT-READ-ONLY", denied.json()["code"])
        self.assertEqual(before, self.read().json())
        self.assertEqual([1], [row["revision"] for row in before["history"]])

    def test_manifest_and_history_pages_preserve_bounded_stable_identities(self) -> None:
        self.open()
        self.inventory.manifests = tuple(
            ModelManifest.model_validate(manifest_document() | {"manifestId": f"fixture-{index:03}"})
            for index in range(51)
        )
        self.assertEqual(200, self.refresh().status_code)
        first = self.read().json()
        self.assertEqual(50, len(first["entries"]))
        self.assertEqual("fixture-049", first["nextManifestId"])
        last = self.read(revision=1, afterManifestId=first["nextManifestId"]).json()
        self.assertEqual(["fixture-050"], [row["manifest"]["manifestId"] for row in last["entries"]])
        self.assertIsNone(last["nextManifestId"])
        self.assertEqual(first["catalogHash"], last["catalogHash"])
        for revision in range(1, 21):
            saved = self.client.post(
                "/projects/models/refresh",
                json={"root": self.project.root, "expectedRevision": revision},
                headers={"Idempotency-Key": f"{revision:032x}"},
            )
            self.assertEqual(200, saved.status_code, saved.text)
        history = self.read().json()
        self.assertEqual(list(range(21, 1, -1)), [row["revision"] for row in history["history"]])
        self.assertEqual(2, history["nextHistoryRevision"])
        older = self.read(revision=1, beforeHistoryRevision=2).json()
        self.assertEqual([1], [row["revision"] for row in older["history"]])
        self.assertIsNone(older["nextHistoryRevision"])
        self.assertEqual(first["catalogHash"], older["catalogHash"])
        self.assertEqual(404, self.read(revision=22).status_code)

    def test_current_qualification_never_claims_a_task_outside_the_manifest(self) -> None:
        self.open()
        observation = self.inventory.observations[0].model_dump()
        self.inventory.observations = (
            HostModelObservation(**(observation | {"qualified_task_kinds": ("embedding",)})),
        )
        saved = self.refresh()
        self.assertEqual(200, saved.status_code)
        self.assertEqual([], saved.json()["entries"][0]["qualifiedTaskKinds"])
        self.assertIn("evaluation-unqualified", saved.json()["entries"][0]["reasonCodes"])

    def test_generated_client_crosses_real_loopback_authentication_and_protected_storage(self) -> None:
        self.open()
        node = REPO / ".local/toolchains/node-v24.19.0-win-x64/node.exe"
        self.assertTrue(node.is_file(), "the pinned Node runtime is required for the actual generated-client boundary")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        host, port = listener.getsockname()
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(
                    projects=self.lifecycle,
                    model_catalog=self.service,
                    capability_digest=capability_token_digest(TOKEN),
                    expected_authority=f"{host}:{port}",
                ),
                host=host,
                port=port,
                log_config=None,
                access_log=False,
                proxy_headers=False,
            )
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        script = """
import { pathToFileURL } from 'node:url';
let input = ''; for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
const { createCoreApiClient } = await import(pathToFileURL(config.client).href);
const client = createCoreApiClient(async request => {
  const response = await fetch(config.origin + request.path, {
    method: request.method, body: request.body, signal: AbortSignal.timeout(10000),
    headers: { Authorization: 'Bearer ' + config.token, 'Content-Type': 'application/json',
      ...(request.idempotencyKey ? { 'Idempotency-Key': request.idempotencyKey } : {}) },
  });
  return { status: response.status, contentType: response.headers.get('content-type'),
    traceId: response.headers.get('x-trace-id'), etag: response.headers.get('etag'), body: await response.text() };
});
const read = { root: config.root, revision: null, afterManifestId: null, beforeHistoryRevision: null };
const before = await client.modelCatalog(read);
const saved = await client.refreshModelCatalog({ root: config.root, expectedRevision: 0 }, 'c'.repeat(32));
const replay = await client.refreshModelCatalog({ root: config.root, expectedRevision: 0 }, 'c'.repeat(32));
const after = await client.modelCatalog(read);
const denial = await fetch(config.origin + '/projects/models', {
  method: 'POST', body: JSON.stringify(read), headers: { 'Content-Type': 'application/json' },
});
const spoof = await fetch(config.origin + '/projects/models/refresh', {
  method: 'POST', body: JSON.stringify({ root: config.root, expectedRevision: 1 }),
  headers: { Authorization: 'Bearer ' + config.token, 'Content-Type': 'application/json',
    'Idempotency-Key': 'd'.repeat(32), 'X-Actor-Id': 'forged' },
});
if (before.revision !== 0 || saved.revision !== 1 || after.revision !== 1 || replay.revision !== 1
    || saved.entries[0].eligibility !== 'not-evaluated' || saved.executionAvailable !== false
    || denial.status !== 401 || spoof.status !== 403) throw new Error('model integration contract failed');
process.stdout.write(JSON.stringify({ revisions: [before.revision, saved.revision, replay.revision, after.revision],
  missingCredentialDenied: true, actorSpoofDenied: true, executionAuthorized: false }));
"""
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(server.started)
            completed = subprocess.run(
                [str(node), "--input-type=module", "-e", script],
                input=json.dumps(
                    {
                        "client": str(REPO / "packages/contracts/core-api/generated.ts"),
                        "origin": f"http://{host}:{port}",
                        "root": self.project.root,
                        "token": TOKEN,
                    }
                ),
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual([0, 1, 1, 1], json.loads(completed.stdout)["revisions"])
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
