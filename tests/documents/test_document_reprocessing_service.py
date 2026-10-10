"""Actual Windows Native-authorized Core/vault/SQLCipher; authored output only."""

import json
import sys
import unittest
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.document_attachment_repository import LocalParserArtifactStager  # noqa: E402
from research_observatory_core.document_parser_runtime import InstalledParser  # noqa: E402
from research_observatory_core.document_reprocessing import (  # noqa: E402
    REPROCESSING_MEDIA_TYPE,
    ReprocessingBatchView,
    ReprocessingPage,
)
from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.document_viewer_allocations import ViewerArtifactReads  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.main import create_runtime_app  # noqa: E402
from research_observatory_core.object_store import _LocalObjectStore  # noqa: E402
from research_observatory_core.parsing.contracts import DocumentIR  # noqa: E402
from research_observatory_core.parsing.requests import ParseSuccess  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402
from research_observatory_core.workflow_executor import WorkerCapacity  # noqa: E402

from tests.documents import correction_native_windows_fixture  # noqa: E402
from tests.parsing import contract_fixtures  # noqa: E402
from tests.service import test_import_preview_service as runtime_fixture  # noqa: E402
from tests.workflows.test_local_workflow_executor import WORKER_A  # noqa: E402


def complete_job(service, root, project, session, job_id, raw):
    """Complete exactly one admitted job with declared synthetic retained output."""
    repository, selected, _actor = service._repository(str(root), project, session, "1" * 32)
    with closing(open_canonical_database(selected._database, expected_project_id=project)) as connection:
        inputs = repository._input(connection, job_id)
    now = service.now()
    claim = repository.queue.claim_next(
        worker_id=WORKER_A,
        concurrency_classes=("document",),
        activity_types=("document-parse",),
        now=now,
        lease_duration_ms=30000,
    )
    assert claim is not None and claim.job_id == job_id
    repository.queue.start(claim, now=now)
    request = inputs.request(claim)
    stager = LocalParserArtifactStager(
        selected._database,
        selected._objects,
        claim=claim,
        request=request,
        actor=repository.actor,
        guard=repository.guard,
        now=service.now,
    )
    artifact = stager(
        request,
        b'{"synthetic-parser-output":true}',
        media_type="application/vnd.research-observatory.text-parser-output+json",
        cancelled=lambda: False,
    )
    wire = contract_fixtures.ir(request.binding, raw=raw).model_dump(mode="json", by_alias=True)
    wire["rawArtifacts"] = [artifact.model_dump(mode="json", by_alias=True)]
    return repository.retain(
        claim,
        request,
        ParseSuccess(schema_version="1.0", kind="success", binding=request.binding, ir=DocumentIR.model_validate(wire)),
        stopped=lambda: False,
    )[0]


@unittest.skipUnless(sys.platform == "win32", "Actual Windows vault composition")
class DocumentReprocessingServiceTests(unittest.TestCase):
    @contextmanager
    def native_fixture(self):
        root = correction_native_windows_fixture.create()
        receipt = json.loads((root / "correction-receipt.json").read_text(encoding="utf-8"))
        project = Path(receipt["root"])
        app = create_runtime_app(
            settings=CoreSettings(),
            profile_vault_root=root / "vault",
            workflow_context=NativeWorkflowContext("b" * 32, "c" * 32),
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        helper = runtime_fixture.ImportRuntimeCompositionTests()
        with (
            patch(
                "research_observatory_core.repositories._windows_worker_capacity",
                return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
            ),
            helper.client(app) as client,
        ):
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            service = app.state.runtime.document_revisions
            service.shutdown()
            service.runtime = SimpleNamespace(
                load_text=lambda: InstalledParser(None, contract_fixtures.descriptor("ro-native-text", ("plain-text",)))
            )
            session = app.state.runtime.attachments.context(str(project), receipt["projectId"])
            address = {"root": str(project), "projectId": receipt["projectId"], "sessionId": session}

            def post(action, **fields):
                return client.post("/native/document-reprocessing/" + action, json={**address, **fields})

            yield service, project, receipt, address, post
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)

    def test_queue_charges_protected_reads_before_adapter_and_normal_page_succeeds(self):
        with self.native_fixture() as (_service, _project, receipt, _address, post):
            created = post(
                "create",
                batch={
                    "schemaVersion": "1.0",
                    "commandId": new_uuid_v7(),
                    "baseRevisionIds": [receipt["originalRevisionId"]],
                },
            )
            self.assertEqual(200, created.status_code, created.text)
            for _ in range(9):
                additional = post(
                    "create",
                    batch={
                        "schemaVersion": "1.0",
                        "commandId": new_uuid_v7(),
                        "baseRevisionIds": [receipt["originalRevisionId"]],
                    },
                )
                self.assertEqual(200, additional.status_code, additional.text)
            normal = post("queue", afterBatchId=None)
            self.assertEqual(200, normal.status_code, normal.text)
            self.assertEqual(10, len(normal.json()["items"]))
            self.assertIsNone(normal.json()["nextAfterBatchId"])
            self.assertEqual(created.json(), normal.json()["items"][0])
            original = _LocalObjectStore._read_protected_document_artifact
            with (
                patch.object(
                    ViewerArtifactReads, "admit_bytes", side_effect=DocumentRevisionProblem("viewer-resource-limit")
                ),
                patch.object(
                    _LocalObjectStore,
                    "_read_protected_document_artifact",
                    autospec=True,
                    side_effect=original,
                ) as adapter,
            ):
                denied = post("queue", afterBatchId=None)
            self.assertEqual(409, denied.status_code)
            self.assertNotIn("SYNTHETIC", denied.text)
            adapter.assert_not_called()

    def test_postdurable_reconcile_failure_is_unknown_and_exact_retry_has_one_plan(self):
        from research_observatory_core.document_revision_repository import LocalDocumentReprocessingRepository

        with self.native_fixture() as (service, project, receipt, address, post):
            created = post(
                "create",
                batch={
                    "schemaVersion": "1.0",
                    "commandId": new_uuid_v7(),
                    "baseRevisionIds": [receipt["originalRevisionId"]],
                },
            )
            self.assertEqual(200, created.status_code, created.text)
            batch = created.json()
            item = batch["items"][0]
            complete_job(
                service,
                project,
                receipt["projectId"],
                address["sessionId"],
                item["jobId"],
                "SYNTHETIC reparse recovery",
            )
            page = post("compare", batchRevisionId=batch["batchRevisionId"], itemId=item["itemId"], offset=0).json()
            command = {
                "schemaVersion": "1.0",
                "commandId": new_uuid_v7(),
                "comparisonRevisionId": page["comparisonRevisionId"],
                "expectedPlanRevisionId": None,
                "rationale": "Current human explicitly reviews this reparse",
                "mappings": [],
            }
            invalid = post("reconcile", reconciliation={**command, "rationale": "   "})
            self.assertEqual(409, invalid.status_code)
            with patch.object(
                LocalDocumentReprocessingRepository,
                "_page",
                side_effect=RuntimeError("authored-after-plan-publication"),
            ):
                unknown = post("reconcile", reconciliation=command)
            self.assertEqual(503, unknown.status_code)
            self.assertNotIn("SYNTHETIC", unknown.text)
            self.assertNotIn("authored-after", unknown.text)
            current = post("compare", batchRevisionId=batch["batchRevisionId"], itemId=item["itemId"], offset=0).json()
            self.assertIsNotNone(current["planRevisionId"])
            repository, _, _ = service._repository(str(project), receipt["projectId"], address["sessionId"], "1" * 32)

            def counts():
                with closing(
                    open_canonical_database(repository.database, expected_project_id=receipt["projectId"])
                ) as db:
                    return tuple(
                        db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                        for table in ("aggregate_revisions", "provenance_events", "outbox_events")
                    )

            before = counts()
            retried = post("reconcile", reconciliation=command)
            self.assertEqual(200, retried.status_code, retried.text)
            self.assertEqual(current["planRevisionId"], retried.json()["planRevisionId"])
            self.assertEqual(before, counts())

    def test_postdurable_commit_attach_serialization_and_delivery_faults_retain_exact_create(self):
        with self.native_fixture() as (service, project, receipt, address, post):
            repository, _, _ = service._repository(str(project), receipt["projectId"], address["sessionId"], "1" * 32)
            original_put = _LocalObjectStore.put_parser_artifact
            original_scope = service._scoped_repository

            def lost_commit(objects, raw, command, *args, **kwargs):
                result = original_put(objects, raw, command, *args, **kwargs)
                if command.media_type == REPROCESSING_MEDIA_TYPE:
                    raise RuntimeError("authored-after-durable-commit")
                return result

            def lost_delivery(*args, **kwargs):
                original_scope(*args, **kwargs)
                raise DocumentRevisionProblem("source-anchor-authority-scope-ended")

            faults = (
                ("commit", patch.object(_LocalObjectStore, "put_parser_artifact", new=lost_commit)),
                ("attach", patch.object(service, "attach", side_effect=RuntimeError("authored-post-create-attach"))),
                (
                    "serialize",
                    patch.object(
                        ReprocessingBatchView, "model_dump", side_effect=RuntimeError("authored-response-serialization")
                    ),
                ),
                ("delivery", patch.object(service, "_scoped_repository", side_effect=lost_delivery)),
            )
            for mode, fault in faults:
                with self.subTest(mode=mode):
                    command_id = new_uuid_v7()
                    command = {
                        "schemaVersion": "1.0",
                        "commandId": command_id,
                        "baseRevisionIds": [receipt["originalRevisionId"]],
                    }
                    with fault:
                        unknown = post("create", batch=command)
                    self.assertEqual(503, unknown.status_code, unknown.text)
                    self.assertNotIn("SYNTHETIC", unknown.text)
                    self.assertNotIn("authored-", unknown.text)
                    key = "document-reprocessing-document-reprocessing-batch-" + command_id
                    with closing(
                        open_canonical_database(repository.database, expected_project_id=receipt["projectId"])
                    ) as db:
                        records = db.execute(
                            "SELECT revision_id FROM outbox_events WHERE idempotency_key=?", (key,)
                        ).fetchall()
                    self.assertEqual(1, len(records))
                    retained = post("read", batchRevisionId=records[0][0])
                    self.assertEqual(200, retained.status_code, retained.text)
                    if mode == "commit":
                        self.assertEqual("not-submitted", retained.json()["items"][0]["state"])
                    retried = post("create", batch=command)
                    self.assertEqual(200, retried.status_code, retried.text)
                    self.assertEqual(records[0][0], retried.json()["batchRevisionId"])
                    self.assertEqual("processing", retried.json()["items"][0]["state"])
                    self.assertEqual(retried.json(), post("create", batch=command).json())
                    with closing(
                        open_canonical_database(repository.database, expected_project_id=receipt["projectId"])
                    ) as db:
                        self.assertEqual(
                            1,
                            db.execute("SELECT COUNT(*) FROM outbox_events WHERE idempotency_key=?", (key,)).fetchone()[
                                0
                            ],
                        )
                        batch = repository.reprocessing()._record(db, records[0][0])
                        self.assertEqual(
                            1,
                            db.execute(
                                "SELECT COUNT(*) FROM document_parse_jobs WHERE command_id=?",
                                (batch.items[0].inputs.command_id,),
                            ).fetchone()[0],
                        )

    def test_native_core_accept_restart_explicit_continuation_rights_actor_and_stopped_delivery(self):
        root = correction_native_windows_fixture.create()
        receipt = json.loads((root / "correction-receipt.json").read_text(encoding="utf-8"))
        project = Path(receipt["root"])
        app = create_runtime_app(
            settings=CoreSettings(),
            profile_vault_root=root / "vault",
            workflow_context=NativeWorkflowContext("b" * 32, "c" * 32),
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        helper = runtime_fixture.ImportRuntimeCompositionTests()
        with (
            patch(
                "research_observatory_core.repositories._windows_worker_capacity",
                return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
            ),
            helper.client(app) as client,
        ):
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            service = app.state.runtime.document_revisions
            service.shutdown()
            # The source-hosted app cannot claim packaged parser installation.
            # Only selection is an authored double; jobs/output below are
            # synthetic and current Native/vault/rights/persistence are real.
            service.runtime = SimpleNamespace(
                load_text=lambda: InstalledParser(None, contract_fixtures.descriptor("ro-native-text", ("plain-text",)))
            )
            attachments = app.state.runtime.attachments
            session = attachments.context(str(project), receipt["projectId"])
            address = {"root": str(project), "projectId": receipt["projectId"], "sessionId": session}

            def post(action, **fields):
                return client.post("/native/document-reprocessing/" + action, json={**address, **fields})

            created = post(
                "create",
                batch={
                    "schemaVersion": "1.0",
                    "commandId": new_uuid_v7(),
                    "baseRevisionIds": [receipt["originalRevisionId"]],
                },
            )
            self.assertEqual(200, created.status_code, created.text)
            batch = created.json()
            item = batch["items"][0]
            self.assertEqual("processing", item["state"])
            complete_job(
                service, project, receipt["projectId"], session, item["jobId"], "SYNTHETIC reparse changed text"
            )
            compared = post("compare", batchRevisionId=batch["batchRevisionId"], itemId=item["itemId"], offset=0)
            self.assertEqual(200, compared.status_code, compared.text)
            page = compared.json()
            self.assertEqual(item["jobId"], page["jobId"])
            self.assertEqual(0, page["unresolvedCount"])
            planned = post(
                "reconcile",
                reconciliation={
                    "schemaVersion": "1.0",
                    "commandId": new_uuid_v7(),
                    "comparisonRevisionId": page["comparisonRevisionId"],
                    "expectedPlanRevisionId": None,
                    "rationale": "Actual Native human explicitly reviewed this comparison",
                    "mappings": [],
                },
            )
            self.assertEqual(200, planned.status_code, planned.text)
            page = planned.json()
            command = {
                "schemaVersion": "1.0",
                "commandId": new_uuid_v7(),
                "planRevisionId": page["planRevisionId"],
                "expectedCurrentRevisionId": page["baseRevisionId"],
                "confirmationSha256": page["confirmationSha256"],
                "expectedGraphSha256": page["impact"]["graphSha256"],
                "decision": "accept-reparse",
            }
            accepted = post("accept", acceptance=command)
            self.assertEqual(200, accepted.status_code, accepted.text)
            accepted = accepted.json()
            self.assertEqual(accepted, post("accept", acceptance=command).json())
            self.assertEqual(
                accepted, post("read-impact", batchRevisionId=batch["batchRevisionId"], itemId=item["itemId"]).json()
            )
            self.assertEqual(
                422, post("read", batchRevisionId=batch["batchRevisionId"], actorId=new_uuid_v7()).status_code
            )
            factory = service.repository_factory
            for field, value in (("actor_type", "worker"), ("intent_sha256", "0" * 64), ("policy_sha256", "0" * 64)):

                def changed(*args, field=field, value=value, **kwargs):
                    actor = kwargs["actor"]
                    kwargs["actor"] = lambda: replace(actor(), **{field: value})
                    return factory(*args, **kwargs)

                with patch.object(service, "repository_factory", changed):
                    denied = post("read-impact", batchRevisionId=batch["batchRevisionId"], itemId=item["itemId"])
                    self.assertEqual(409, denied.status_code)
                    self.assertNotIn("SYNTHETIC", denied.text)

            def permissions(denied=None):
                def current(selected, actor):
                    from research_observatory_core.document_attachment_repository import LocalDocumentAttachmentService

                    with closing(
                        open_canonical_database(selected._database, expected_project_id=receipt["projectId"])
                    ) as connection:
                        local = LocalDocumentAttachmentService(
                            selected._database, receipt["projectId"], selected._objects
                        )
                        attached = local._attachment(connection, receipt["attachmentId"])
                        candidate = local._candidate(connection, attached.candidate_id)
                    prior = selected._rights.current(candidate.rights_subject, actor=actor)
                    values = tuple(
                        RightsPermissionDraft(
                            use=RightsUse(
                                action=right,
                                purpose="document-attachment" if right == "store" else "document-analysis",
                                destination_kind="local-project",
                            ),
                            value="denied" if right == denied else "permitted",
                            basis="researcher-confirmed",
                            confidence="confirmed",
                            grantee_actor_id=actor.actor_id,
                            evidence_revision_ids=(candidate.source_assertion_revision_id,),
                        )
                        for right in ("store", "inspect", "derive")
                    )
                    selected._rights.publish_draft(
                        candidate.rights_subject,
                        values,
                        prior.revision_id,
                        command_id=new_uuid_v7(),
                        command_sha256="6" * 64,
                        actor=actor,
                    )

                attachments._action(str(project), receipt["projectId"], session, "1" * 32, current)

            for right in ("inspect", "derive"):
                permissions(right)
                denied = post("read-impact", batchRevisionId=batch["batchRevisionId"], itemId=item["itemId"])
                self.assertEqual(409, denied.status_code)
                self.assertNotIn("SYNTHETIC", denied.text)
                permissions()
            queued = post(
                "create",
                batch={"schemaVersion": "1.0", "commandId": new_uuid_v7(), "baseRevisionIds": [accepted["revisionId"]]},
            )
            self.assertEqual(200, queued.status_code, queued.text)
            queued = queued.json()
            unfinished = queued["items"][0]
            old_session = session
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            service.shutdown()
            self.assertEqual(409, post("read", batchRevisionId=queued["batchRevisionId"]).status_code)
            session = attachments.context(str(project), receipt["projectId"])
            self.assertNotEqual(old_session, session)
            address["sessionId"] = session
            self.assertEqual(
                accepted, post("read-impact", batchRevisionId=batch["batchRevisionId"], itemId=item["itemId"]).json()
            )
            self.assertEqual(
                "needs-continuation",
                post("read", batchRevisionId=queued["batchRevisionId"]).json()["items"][0]["state"],
            )
            continued = post(
                "continue",
                continuation={
                    "schemaVersion": "1.0",
                    "commandId": new_uuid_v7(),
                    "batchRevisionId": queued["batchRevisionId"],
                    "itemId": unfinished["itemId"],
                    "expectedJobId": unfinished["jobId"],
                },
            )
            self.assertEqual(200, continued.status_code, continued.text)
            continued = continued.json()
            self.assertNotEqual(unfinished["jobId"], continued["items"][0]["jobId"])
            self.assertEqual(queued["batchId"], continued["batchId"])
            original_dump = ReprocessingPage.model_dump

            def stop(value, *args, **kwargs):
                result = original_dump(value, *args, **kwargs)
                if kwargs.get("mode") == "json":
                    service.imports.signal_stop(str(project))
                return result

            with patch.object(ReprocessingPage, "model_dump", stop):
                denied = post("compare", batchRevisionId=batch["batchRevisionId"], itemId=item["itemId"], offset=0)
                self.assertEqual(409, denied.status_code)
                self.assertNotIn("SYNTHETIC", denied.text)
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
        self.assertNotIn(b"SYNTHETIC", (project / "state/project.sqlite3").read_bytes())
