"""Encrypted invocation state and workflow-fenced plugin page publication."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_dispatch import PluginStagedOutput  # noqa: E402
from research_observatory_core.connectors.plugin_manifest import (  # noqa: E402
    PluginInvocationRequest,
    PluginProjectGrant,
    authorize_plugin_invocation,
    verify_plugin_package,
)
from research_observatory_core.connectors.plugin_package_intake import inspect_plugin_archive  # noqa: E402
from research_observatory_core.connectors.plugin_result import validate_plugin_output  # noqa: E402
from research_observatory_core.connectors.plugin_workflow import PluginJobInput, build_plugin_job  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.ingestion.preview_workflow import PreviewIntentContext  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.plugin_job_repository import (  # noqa: E402
    PluginJobRepository,
    PluginJobRepositoryProblem,
)
from research_observatory_core.ports.object_store import ObjectPutCommand  # noqa: E402
from research_observatory_core.ports.workflow_executor import WorkflowActor  # noqa: E402
from research_observatory_core.repositories import _SqliteWorkflowQueueRepository  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture, initialize_database  # noqa: E402

from tests.connectors.test_plugin_package_intake import archive  # noqa: E402
from tests.connectors.test_plugin_package_store import MemoryKeyProvider  # noqa: E402

PROJECT = "0190a000-0000-7000-8000-000000000040"
NOW = "2026-10-01T12:00:00.000Z"
LATER = "2026-10-01T12:00:00.100Z"


class PluginJobFixture(unittest.TestCase):
    def setUp(self):
        profile = development_plaintext_database_fixture()
        profile.__enter__()
        self.addCleanup(lambda: profile.__exit__(None, None, None))
        scratch = tempfile.TemporaryDirectory(prefix="ro-plugin-job-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        for directory in ("state", "objects", ".tmp"):
            (self.root / directory).mkdir()
        self.database = self.root / "state/project.sqlite3"
        self.assertTrue(initialize_database(self.database, project_id=PROJECT, project_created_at=NOW).ok)
        self.keys = MemoryKeyProvider()
        self.objects = create_local_object_store(self.root, PROJECT, key_provider=self.keys)
        self.repository = PluginJobRepository(self.database, PROJECT, self.objects)
        self.queue = _SqliteWorkflowQueueRepository(self.database, PROJECT)
        raw, key = archive()
        inspected = inspect_plugin_archive(raw)
        package = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {inspected.manifest.publisher_key_id: key},
        )
        manifest = package.manifest
        self.input_data = b'{"identifier":"synthetic-1"}'
        request = PluginInvocationRequest(
            project_id=PROJECT,
            invocation_id=new_uuid_v7(),
            scientific_request_sha256="sha256:" + hashlib.sha256(self.input_data).hexdigest(),
            operation=manifest.operations[0],
            destination=manifest.destinations[0],
        )
        grant = PluginProjectGrant(
            project_id=PROJECT,
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            publisher_key_id=manifest.publisher_key_id,
            permissions=manifest.permissions,
            destinations=manifest.destinations,
            revision=1,
        )
        self.plan = authorize_plugin_invocation(package, grant, request)
        self.inputs = PluginJobInput(
            request=request,
            plugin_id=manifest.plugin_id,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            signature_sha256=package.signature_sha256,
            authorization_request_sha256=self.plan.request_sha256,
            consent_preview_id=new_uuid_v7(),
            consent_confirmation_sha256="sha256:" + "5" * 64,
            consent_retention_sha256="sha256:" + "6" * 64,
            input_object_sha256=hashlib.sha256(self.input_data).hexdigest(),
            input_byte_length=len(self.input_data),
            intent=PreviewIntentContext(
                project_id=PROJECT,
                domain_project_id=new_uuid_v7(),
                intent_id=new_uuid_v7(),
                revision_id=new_uuid_v7(),
                content_hash="sha256:" + "1" * 64,
                status="accepted",
            ),
            policy_hash="sha256:" + "2" * 64,
            job_epoch="3" * 32,
        )
        self.actor = WorkflowActor(new_uuid_v7(), "human", "local-researcher")

    def _staged(self):
        body = json.dumps(
            {
                "schemaVersion": "1.0",
                "invocationId": self.inputs.invocation_id,
                "operation": self.plan.operation,
                "records": [],
                "continuation": "exhausted",
            },
            separators=(",", ":"),
        ).encode()
        digest = hashlib.sha256(body).hexdigest()
        self.objects.put(
            io.BytesIO(body),
            ObjectPutCommand(
                media_type="application/json",
                rights_status="allowed",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="connector-acquisition",
                created_at=NOW,
                expected_sha256=digest,
            ),
        )
        return PluginStagedOutput(digest, len(body), 0, NOW, validate_plugin_output(self.plan, body, retrieved_at=NOW))

    def _claim(self):
        self.repository.save_input(self.inputs, actor_id=self.actor.actor_id, now=NOW)
        self.queue.enqueue(build_plugin_job(self.inputs, actor=self.actor, now=NOW), actor=self.actor)
        claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=NOW,
            lease_duration_ms=30_000,
            activity_types=("plugin-connector-invocation",),
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        self.queue.start(claim, now=NOW)
        return claim


class PluginJobRepositoryTests(PluginJobFixture):
    def test_encrypted_input_reopens_after_repository_restart(self):
        self.repository.save_input(self.inputs, actor_id=self.actor.actor_id, now=NOW)
        reopened = PluginJobRepository(
            self.database, PROJECT, create_local_object_store(self.root, PROJECT, key_provider=self.keys)
        )
        self.assertEqual(self.inputs, reopened.input(self.inputs.invocation_id))
        physical = tuple(path for path in (self.root / "objects").rglob("*") if path.is_file())
        self.assertEqual(1, len(physical))
        self.assertNotIn(self.inputs.invocation_id.encode(), physical[0].read_bytes())

    def test_fenced_publication_and_restart_replay(self):
        claim = self._claim()
        output = self.repository.publish(
            self.inputs,
            self.plan,
            self._staged(),
            claim,
            actor_id=self.actor.actor_id,
            now=lambda: LATER,
            recheck_current=lambda: None,
            interrupted=lambda: False,
        )
        self.assertEqual("succeeded", self.queue.get(claim.job_id).state)
        reopened = PluginJobRepository(
            self.database, PROJECT, create_local_object_store(self.root, PROJECT, key_provider=self.keys)
        )
        page = reopened.result(self.inputs)
        assert page is not None
        self.assertEqual(output.revision_id, page.revision_id)
        self.assertEqual((NOW, LATER), (page.retrieved_at, page.observed_at))
        self.assertEqual(self.plan.source_id, page.plan.source_id)

    def test_interrupted_claim_never_publishes(self):
        claim = self._claim()
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "interrupted"):
            self.repository.publish(
                self.inputs,
                self.plan,
                self._staged(),
                claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: True,
            )
        self.assertIsNone(self.repository.result(self.inputs))


if __name__ == "__main__":
    unittest.main()
