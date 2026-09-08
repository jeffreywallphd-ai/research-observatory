from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

# ruff: noqa: E402
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.main import create_runtime_app
from research_observatory_core.model_gateway_contracts import decode_model_task
from research_observatory_core.model_registry_contracts import ModelManifest, canonical_hash
from research_observatory_core.model_registry_repository import SqliteModelRoutingRepository
from research_observatory_core.model_routing_contracts import CancellationToken, input_references
from research_observatory_core.model_routing_policy import CanonicalModelEligibilityPolicy
from research_observatory_core.object_store import create_local_object_store
from research_observatory_core.projects import ProjectLifecycleProblem
from research_observatory_core.repositories import create_sqlite_unit_of_work_factory

from tests.ai.test_model_registry import manifest_document, task
from tests.data.test_local_object_store import document_draft, event
from tests.data.test_object_envelope_upgrades import MemoryKeyProvider, command
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider


class ProjectModelGatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-gateway-core-fixture-")
        self.actor = new_uuid_v7()
        self.keys = MemoryKeyProvider({"fixture-key-v1": bytes.fromhex("41" * 32)}, "fixture-key-v1")
        self.application = create_runtime_app(
            settings=CoreSettings(),
            object_key_provider=self.keys,
            database_key_provider=InMemoryDatabaseKeyProvider(),
            local_actor_id=self.actor,
        )
        self.client = TestClient(self.application)
        self.client.__enter__()
        self.runtime = self.application.state.runtime
        self.project = self.runtime.projects.create(
            parent_directory=self.temporary.name,
            directory_name="fixture-project",
            display_name="Fixture project",
            template_id="theory-synthesis",
            trace_id="a" * 32,
        )
        self.root = Path(self.project.root)
        self.database = self.root / "state/project.sqlite3"

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temporary.cleanup()

    def open(self):
        return self.runtime.projects.open(root=self.project.root, trace_id="a" * 32)

    def policy(self):
        return CanonicalModelEligibilityPolicy(
            projects=self.runtime.projects,
            privacy=self.runtime.privacy,
            root=self.project.root,
            unit_of_work_factory=lambda path, identity: create_sqlite_unit_of_work_factory(
                path / "state/project.sqlite3", identity
            ),
            clock_ms=lambda: 1500,
        )

    def source_task(self):
        stored = create_local_object_store(self.root, self.project.project_id, key_provider=self.keys).put(
            io.BytesIO(b"synthetic local research fixture"), command()
        )
        factory = create_sqlite_unit_of_work_factory(self.database, self.project.project_id)
        with factory() as unit:
            revision = unit.aggregates.append(document_draft(1, stored.object_sha256), event(1), expected_revision=None)
            unit.commit()
        document = task()
        document["input"]["context"] = [
            {
                "aggregateId": revision.aggregate_id,
                "revisionId": revision.revision_id,
                "contentHash": "sha256:" + stored.object_sha256,
                "role": "source",
            }
        ]
        document["input"]["instruction"] = document["input"]["context"][0] | {"role": "instruction"}
        return document

    def assess(self, document, **changes):
        return self.policy().assess(
            project_id=changes.get("project_id", self.project.project_id),
            catalog_revision=1,
            task=decode_model_task(document),
            manifest=ModelManifest.model_validate(manifest_document()),
        )

    async def test_actual_core_composition_is_empty_denies_execution_and_persists_result(self):
        with self.assertRaises(ProjectLifecycleProblem):
            self.runtime.model_gateway.for_project(self.project.root)
        self.open()
        gateway, policy = self.runtime.model_gateway.for_project(self.project.root)
        request = task()
        result = await gateway.execute(request, input_references(request), policy, CancellationToken())
        self.assertEqual("denied", result["status"])
        self.assertIsNone(result["output"])
        self.assertEqual({}, gateway._adapters)
        self.assertEqual(("local",), policy.permitted_deployments)
        self.assertEqual(0, policy.maximum_cost_microunits)
        self.assertNotIn("model/execute", json.dumps(self.application.openapi()))
        restarted = SqliteModelRoutingRepository(self.database, self.project.project_id, self.actor)
        persisted = restarted.read(request["taskId"])
        assert persisted is not None
        self.assertTrue(persisted.terminal)
        self.assertNotEqual(b"SQLite format 3\0", self.database.read_bytes()[:16])
        self.runtime.projects.close(root=self.project.root, trace_id="a" * 32)
        with self.assertRaises(ProjectLifecycleProblem):
            await gateway.execute(request, input_references(request), policy, CancellationToken())

    async def test_missing_core_actor_cannot_bind_or_write(self):
        self.open()
        self.runtime.model_gateway._actor = None
        with self.assertRaisesRegex(ValueError, "authority is unavailable"):
            self.runtime.model_gateway.for_project(self.project.root)

    async def test_canonical_coarse_rights_do_not_grant_model_use_or_spend(self):
        self.open()
        request = self.source_task()
        before = copy.deepcopy(request)
        assessment = self.assess(request)
        self.assertIsNotNone(assessment)
        self.assertEqual(canonical_hash(request), assessment.task_hash)
        self.assertEqual(
            {"model-use-rights-unavailable", "source-classification-unavailable", "model-budget-authority-unavailable"},
            set(assessment.reason_codes),
        )
        self.assertEqual((), assessment.permitted_deployments)
        self.assertEqual(0, assessment.maximum_cost_microunits)
        self.assertEqual(before, request)
        self.runtime.projects.close(root=self.project.root, trace_id="a" * 32)
        self.open()
        self.assertEqual(assessment.rights_revision, self.assess(request).rights_revision)

    async def test_canonical_identity_hash_cross_project_and_latest_rights_are_checked(self):
        self.open()
        request = self.source_task()
        changed = copy.deepcopy(request)
        changed["input"]["context"][0]["contentHash"] = "sha256:" + "0" * 64
        self.assertIn("canonical-input-identity-mismatch", self.assess(changed).reason_codes)
        self.assertIsNone(self.assess(request, project_id=new_uuid_v7()))
        factory = create_sqlite_unit_of_work_factory(self.database, self.project.project_id)
        with factory() as unit:
            unit.aggregates.append(
                replace(document_draft(2, request["input"]["context"][0]["contentHash"][7:]), rights_status="denied"),
                event(2),
                expected_revision=0,
            )
            unit.commit()
        self.assertIn("canonical-input-rights-denied", self.assess(request).reason_codes)
        self.runtime.projects.close(root=self.project.root, trace_id="a" * 32)
        self.assertIsNone(self.assess(request))


if __name__ == "__main__":
    unittest.main()
