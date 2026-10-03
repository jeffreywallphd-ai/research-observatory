"""Encrypted invocation state and workflow-fenced plugin page publication."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_dispatch import (  # noqa: E402
    PluginBrokerResponseRef,
    PluginStagedOutput,
)
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
    PluginPublishedPage,
)
from research_observatory_core.ports.object_store import ObjectPutCommand  # noqa: E402
from research_observatory_core.ports.workflow_executor import WorkflowActor  # noqa: E402
from research_observatory_core.repositories import _SqliteWorkflowQueueRepository  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    development_plaintext_database_fixture,
    initialize_database,
    open_canonical_database,
)

from tests.connectors.test_plugin_manifest_contract import _manifest_bytes, _manifest_document  # noqa: E402
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

    def _search(self, *, query="approved", cursor=None, previous_invocation_id=None, package_override=None):
        manifest_document = _manifest_document()
        manifest_document["operations"].append("search")
        raw, key = archive(manifest=_manifest_bytes(manifest_document))
        inspected = inspect_plugin_archive(raw)
        package = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {inspected.manifest.publisher_key_id: key},
        )
        document = {"query": query, "pageSize": 2}
        if cursor is not None:
            document["cursor"] = cursor
            document["previousInvocationId"] = previous_invocation_id
        self.input_data = json.dumps(document, separators=(",", ":")).encode()
        digest = hashlib.sha256(self.input_data).hexdigest()
        self.objects.put(
            io.BytesIO(self.input_data),
            ObjectPutCommand(
                media_type="application/octet-stream",
                rights_status="allowed",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="local-derivation",
                created_at=NOW,
                expected_sha256=digest,
            ),
        )
        request = PluginInvocationRequest(
            project_id=PROJECT,
            invocation_id=new_uuid_v7(),
            scientific_request_sha256="sha256:" + digest,
            operation="search",
            destination=package.manifest.destinations[0],
        )
        grant = PluginProjectGrant(
            project_id=PROJECT,
            plugin_id=package.manifest.plugin_id,
            plugin_version=package.manifest.plugin_version,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            publisher_key_id=package.manifest.publisher_key_id,
            permissions=package.manifest.permissions,
            destinations=package.manifest.destinations,
            revision=1,
        )
        self.plan = authorize_plugin_invocation(package, grant, request)
        if package_override is not None:
            self.plan = self.plan.model_copy(update={"package_sha256": package_override})
        self.inputs = self.inputs.model_copy(
            update={
                "request": request,
                "package_sha256": self.plan.package_sha256,
                "manifest_sha256": self.plan.manifest_sha256,
                "signature_sha256": self.plan.signature_sha256,
                "authorization_request_sha256": self.plan.request_sha256,
                "input_object_sha256": digest,
                "input_byte_length": len(self.input_data),
            }
        )
        return self.inputs, self.plan

    def _staged(self, next_cursor=None, *, redacted=False):
        response = json.dumps(
            {"records": [], "nextCursor": next_cursor} if self.plan.operation == "search" else {"id": "synthetic-1"},
            separators=(",", ":"),
        ).encode()
        response_digest = hashlib.sha256(response).hexdigest()
        self.objects.put(
            io.BytesIO(response),
            ObjectPutCommand(
                media_type="application/json",
                rights_status="allowed",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="connector-acquisition",
                created_at=NOW,
                expected_sha256=response_digest,
            ),
        )
        document = {
            "schemaVersion": "1.0",
            "invocationId": self.inputs.invocation_id,
            "operation": self.plan.operation,
            "records": [],
            "continuation": "next-page" if next_cursor is not None else "exhausted",
        }
        if next_cursor is not None:
            document["nextCursor"] = next_cursor
        body = json.dumps(document, separators=(",", ":")).encode()
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
        return PluginStagedOutput(
            digest,
            len(body),
            1,
            NOW,
            validate_plugin_output(self.plan, body, retrieved_at=NOW),
            (PluginBrokerResponseRef(object_sha256=response_digest, byte_length=len(response), redacted=redacted),),
        )

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
    def test_page_two_reopens_predecessor_and_records_exact_provenance(self):
        self._search()
        first_inputs = self.inputs
        first_claim = self._claim()
        first_output = self.repository.publish(
            self.inputs,
            self.plan,
            self._staged("page-2"),
            first_claim,
            actor_id=self.actor.actor_id,
            now=lambda: LATER,
            recheck_current=lambda: None,
            interrupted=lambda: False,
        )
        self._search(cursor="page-2", previous_invocation_id=first_inputs.invocation_id)
        second_claim = self._claim()
        reopened = PluginJobRepository(
            self.database, PROJECT, create_local_object_store(self.root, PROJECT, key_provider=self.keys)
        )
        second_output = reopened.publish(
            self.inputs,
            self.plan,
            self._staged(),
            second_claim,
            actor_id=self.actor.actor_id,
            now=lambda: LATER,
            recheck_current=lambda: None,
            interrupted=lambda: False,
        )
        second = reopened.result(self.inputs)
        assert second is not None
        self.assertEqual(second_output.revision_id, second.revision_id)
        self.assertEqual("exhausted", second.continuation)
        with open_canonical_database(self.database, expected_project_id=PROJECT) as connection:
            linked = connection.execute(
                "SELECT related_revision_id FROM provenance_ledger_relations "
                "WHERE project_id=? AND relation_type='wasDerivedFrom' AND entity_revision_id=?",
                (PROJECT, second_output.revision_id),
            ).fetchall()
        self.assertEqual({self.inputs.invocation_id, first_output.revision_id}, {row[0] for row in linked})

    def test_uncommitted_predecessor_cannot_publish_page_two(self):
        self._search(cursor="page-2", previous_invocation_id=new_uuid_v7())
        claim = self._claim()
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "predecessor"):
            self.repository.publish(
                self.inputs,
                self.plan,
                self._staged(),
                claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: False,
            )
        self.assertIsNone(self.repository.result(self.inputs))

    def test_changed_search_query_cannot_replay_prior_cursor_after_restart(self):
        self._search()
        first_inputs = self.inputs
        first_claim = self._claim()
        self.repository.publish(
            self.inputs,
            self.plan,
            self._staged("page-2"),
            first_claim,
            actor_id=self.actor.actor_id,
            now=lambda: LATER,
            recheck_current=lambda: None,
            interrupted=lambda: False,
        )
        self._search(query="changed", cursor="page-2", previous_invocation_id=first_inputs.invocation_id)
        second_claim = self._claim()
        reopened = PluginJobRepository(
            self.database, PROJECT, create_local_object_store(self.root, PROJECT, key_provider=self.keys)
        )
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "predecessor"):
            reopened.publish(
                self.inputs,
                self.plan,
                self._staged(),
                second_claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: False,
            )
        self.assertIsNone(reopened.result(self.inputs))

    def test_wrong_cursor_cannot_publish_against_committed_page(self):
        self._search()
        first_inputs = self.inputs
        first_claim = self._claim()
        first_output = self.repository.publish(
            self.inputs,
            self.plan,
            self._staged("page-2"),
            first_claim,
            actor_id=self.actor.actor_id,
            now=lambda: LATER,
            recheck_current=lambda: None,
            interrupted=lambda: False,
        )
        self._search(cursor="page-3", previous_invocation_id=first_inputs.invocation_id)
        second_claim = self._claim()
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "predecessor"):
            self.repository.publish(
                self.inputs,
                self.plan,
                self._staged(),
                second_claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: False,
            )
        self.assertIsNone(self.repository.result(self.inputs))
        prior = self.repository.result(first_inputs)
        assert prior is not None
        self.assertEqual(first_output.revision_id, prior.revision_id)

    def test_changed_package_cannot_replay_committed_cursor(self):
        self._search()
        first_inputs = self.inputs
        first_claim = self._claim()
        self.repository.publish(
            self.inputs,
            self.plan,
            self._staged("page-2"),
            first_claim,
            actor_id=self.actor.actor_id,
            now=lambda: LATER,
            recheck_current=lambda: None,
            interrupted=lambda: False,
        )
        self._search(
            cursor="page-2",
            previous_invocation_id=first_inputs.invocation_id,
            package_override="sha256:" + "9" * 64,
        )
        second_claim = self._claim()
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "predecessor"):
            self.repository.publish(
                self.inputs,
                self.plan,
                self._staged(),
                second_claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: False,
            )
        self.assertIsNone(self.repository.result(self.inputs))

    def test_exhausted_page_cannot_be_used_as_predecessor(self):
        self._search()
        first_inputs = self.inputs
        first_claim = self._claim()
        self.repository.publish(
            self.inputs,
            self.plan,
            self._staged(),
            first_claim,
            actor_id=self.actor.actor_id,
            now=lambda: LATER,
            recheck_current=lambda: None,
            interrupted=lambda: False,
        )
        self._search(cursor="page-2", previous_invocation_id=first_inputs.invocation_id)
        second_claim = self._claim()
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "predecessor"):
            self.repository.publish(
                self.inputs,
                self.plan,
                self._staged(),
                second_claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: False,
            )
        self.assertIsNone(self.repository.result(self.inputs))

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
        self.assertEqual(1, len(page.broker_responses))
        self.assertEqual(1, page.broker_calls)
        self.assertIs(page.broker_responses[0].redacted, False)
        with self.objects.open(page.broker_responses[0].object_sha256, purpose="document-analysis") as stream:
            sanitized_response = stream.read()
        self.assertEqual(b'{"id":"synthetic-1"}', sanitized_response)
        object_files = tuple(path for path in (self.root / "objects").rglob("*") if path.is_file())
        self.assertFalse(any(sanitized_response in path.read_bytes() for path in object_files))
        with open_canonical_database(self.database, expected_project_id=PROJECT) as connection:
            dependencies = connection.execute(
                "SELECT configuration_id,fingerprint FROM material_dependencies "
                "WHERE project_id=? AND output_revision_id=? "
                "AND configuration_id IN ('plugin.broker-response.1','plugin.broker-response-redacted.1')",
                (PROJECT, page.revision_id),
            ).fetchall()
        self.assertEqual(
            {
                "plugin.broker-response.1": "sha256:" + page.broker_responses[0].object_sha256,
                "plugin.broker-response-redacted.1": "sha256:"
                + hashlib.sha256(b"plugin.broker-response-redacted.v1:false").hexdigest(),
            },
            dict(dependencies),
        )
        legacy_page = PluginPublishedPage.model_validate(page.model_dump(exclude={"broker_responses"}))
        self.assertEqual((), legacy_page.broker_responses)
        historical = page.model_dump()
        del historical["broker_responses"][0]["redacted"]
        historical_page = PluginPublishedPage.model_validate(historical)
        self.assertIsNone(historical_page.broker_responses[0].redacted)

    def test_redacted_broker_response_reopens_with_explicit_provenance(self):
        claim = self._claim()
        staged = self._staged(redacted=True)
        self.assertIs(staged.broker_responses[0].redacted, True)
        output = self.repository.publish(
            self.inputs,
            self.plan,
            staged,
            claim,
            actor_id=self.actor.actor_id,
            now=lambda: LATER,
            recheck_current=lambda: None,
            interrupted=lambda: False,
        )
        reopened = PluginJobRepository(
            self.database, PROJECT, create_local_object_store(self.root, PROJECT, key_provider=self.keys)
        )
        page = reopened.result(self.inputs)
        assert page is not None
        self.assertEqual(output.revision_id, page.revision_id)
        self.assertIs(page.broker_responses[0].redacted, True)
        with open_canonical_database(self.database, expected_project_id=PROJECT) as connection:
            dependency = connection.execute(
                "SELECT fingerprint FROM material_dependencies WHERE project_id=? AND output_revision_id=? "
                "AND configuration_id='plugin.broker-response-redacted.1'",
                (PROJECT, page.revision_id),
            ).fetchone()
        self.assertIsNotNone(dependency)
        self.assertEqual(
            "sha256:" + hashlib.sha256(b"plugin.broker-response-redacted.v1:true").hexdigest(),
            dependency[0],
        )

    def test_no_broker_response_reference_cannot_publish_result(self):
        claim = self._claim()
        staged = replace(self._staged(), broker_responses=())
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "broker-response"):
            self.repository.publish(
                self.inputs,
                self.plan,
                staged,
                claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: False,
            )
        self.assertIsNone(self.repository.result(self.inputs))

    def test_unknown_historical_redaction_marker_cannot_publish_new_result(self):
        claim = self._claim()
        staged = self._staged()
        historical = PluginBrokerResponseRef.model_validate(staged.broker_responses[0].model_dump(exclude={"redacted"}))
        self.assertIsNone(historical.redacted)
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "broker-response"):
            self.repository.publish(
                self.inputs,
                self.plan,
                replace(staged, broker_responses=(historical,)),
                claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: False,
            )
        self.assertIsNone(self.repository.result(self.inputs))

    def test_missing_or_changed_broker_response_object_denies_publication(self):
        claim = self._claim()
        staged = self._staged()
        reference = staged.broker_responses[0]
        for changed in (
            reference.model_copy(update={"object_sha256": "f" * 64}),
            reference.model_copy(update={"byte_length": reference.byte_length + 1}),
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(PluginJobRepositoryProblem, "broker-response"):
                self.repository.publish(
                    self.inputs,
                    self.plan,
                    replace(staged, broker_responses=(changed,)),
                    claim,
                    actor_id=self.actor.actor_id,
                    now=lambda: LATER,
                    recheck_current=lambda: None,
                    interrupted=lambda: False,
                )
        self.assertIsNone(self.repository.result(self.inputs))

    def test_search_page_cannot_publish_cursor_absent_from_stored_broker_response(self):
        self._search()
        claim = self._claim()
        staged = self._staged("page-2")
        response = b'{"records":[],"nextCursor":"different-page"}'
        digest = hashlib.sha256(response).hexdigest()
        self.objects.put(
            io.BytesIO(response),
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
        forged = replace(
            staged,
            broker_responses=(PluginBrokerResponseRef(object_sha256=digest, byte_length=len(response)),),
        )
        with self.assertRaisesRegex(PluginJobRepositoryProblem, "broker-response"):
            self.repository.publish(
                self.inputs,
                self.plan,
                forged,
                claim,
                actor_id=self.actor.actor_id,
                now=lambda: LATER,
                recheck_current=lambda: None,
                interrupted=lambda: False,
            )
        self.assertIsNone(self.repository.result(self.inputs))

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
