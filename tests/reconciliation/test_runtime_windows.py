"""Production Core/DPAPI/SQLCipher/import/connector handoff; synthetic HTTP only."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2
from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.main import create_runtime_app
from research_observatory_core.ports.import_previews import PreviewCreate, PreviewDraftChange
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.connectors import test_connector_authority as authority_fixture
from tests.connectors import test_source_slice_runtime as source_fixture
from tests.connectors.test_connector_transport import BytesStream
from tests.service import test_import_preview_service as runtime_fixture

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "nt", "Windows DPAPI and SQLCipher required")
class ReconciliationRuntimeTests(unittest.TestCase):
    def test_actual_sources_converge_and_restart_rechecks_current_rights(self):
        directory = Path(tempfile.mkdtemp(prefix="reconciliation-runtime-", dir=REPO / "artifacts/tmp"))
        calls = []
        helper = runtime_fixture.ImportRuntimeCompositionTests()
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
        document = source_fixture.documents(1)["crossref"]

        async def respond(wire):
            calls.append(wire.url.host)
            self.assertEqual("api.crossref.org", wire.url.host)
            response = httpx2.Response(200, json=document)
            return httpx2.Response(200, headers=response.headers, stream=BytesStream(response.content))

        def application(epoch):
            return create_runtime_app(
                settings=CoreSettings(),
                profile_vault_root=directory / "vault",
                workflow_context=NativeWorkflowContext(epoch * 32, "c" * 32),
                capability_digest=capability_token_digest("a" * 64),
                expected_authority="127.0.0.1:49152",
            )

        def post(client, route, body, expected=200):
            response = client.post(route, json=body)
            self.assertEqual(expected, response.status_code, response.text)
            return response.json()

        with patch(
            "research_observatory_core.repositories._windows_worker_capacity",
            return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
        ):
            app = application("b")
            with helper.client(app) as client:
                runtime = app.state.runtime
                runtime.connectors._transport_factory = lambda: httpx2.MockTransport(respond)
                project = post(
                    client,
                    "/projects",
                    {
                        "parentDirectory": str(directory),
                        "directoryName": "project",
                        "displayName": "Synthetic reconciliation",
                        "primaryUseCase": "theory-synthesis",
                        "researchObjective": "Synthetic source identity test",
                    },
                )
                root, identity = project["root"], project["projectId"]
                post(client, "/projects/open", {"root": root})
                authority = authority_fixture.ConnectorAuthorityFixture()
                authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
                authority.intent(providers=("crossref",))
                authority.policy()
                preview = new_uuid_v7()
                imports = runtime.imports
                raw = b"title,doi\nSynthetic imported title,https://doi.org/10.99999/SYNTHETIC-0\n"
                imports.create(
                    root,
                    PreviewCreate(
                        preview_id=preview,
                        source_name="synthetic.csv",
                        format_name="csv",
                        rights=rights,
                        actor=imports.actor("1" * 32),
                    ),
                )
                imports.append_chunk(root, preview, ordinal=1, data=raw)
                imports.seal(
                    root,
                    preview,
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                    byte_length=len(raw),
                    chunk_count=1,
                    trace_id="1" * 32,
                )
                imports.schedule(root, preview)
                imports.run_pending()
                repository = imports._adapters(Path(root), identity).previews
                draft = repository.revise_draft(
                    preview, PreviewDraftChange(expected_revision=0, actor=imports.actor("2" * 32))
                )
                imports.schedule_commit(root, preview, revision=draft.revision, request_id=new_uuid_v7())
                imports.run_pending()
                manifest = imports.import_manifest(root, preview)
                self.assertIsNotNone(manifest)
                member = next(
                    item
                    for item in imports.import_manifest_members(
                        root, preview, revision_id=manifest.revision_id, after=0, limit=10
                    )
                    if item.decision.included
                )
                original = member.model_dump_json()
                address = {
                    "kind": "import-member",
                    "contextId": preview,
                    "revisionId": manifest.revision_id,
                    "ordinal": member.ordinal,
                    "recordKey": member.record_key,
                }
                command = {"root": root, "commandId": new_uuid_v7(), "source": address}
                post(
                    client, "/projects/reconciliation/exact", command | {"rights": rights.model_dump(mode="json")}, 422
                )
                post(client, "/projects/reconciliation/exact", command | {"ignored": "x" * 32768}, 413)
                post(
                    client,
                    "/projects/reconciliation/exact",
                    command | {"source": address | {"contextId": new_uuid_v7()}},
                    409,
                )
                first = post(client, "/projects/reconciliation/exact", command)
                self.assertEqual("new-work", first["disposition"])
                self.assertEqual(first, post(client, "/projects/reconciliation/exact", command))
                request = source_fixture.source_request("crossref", identity, 1)
                confirmed = post(
                    client,
                    "/projects/connectors/previews",
                    {
                        "root": root,
                        "request": request.model_dump(mode="json", by_alias=True),
                        "retention": {"rights": rights.model_dump(mode="json", by_alias=True), "retainBody": True},
                    },
                )
                job = post(
                    client,
                    "/projects/connectors/confirmations",
                    {"root": root, "previewId": confirmed["previewId"], "confirmation": confirmed["confirmation"]},
                )
                runtime.connectors.run_pending()
                status = post(client, "/projects/connectors/jobs/status", {"root": root, "jobId": job["jobId"]})
                self.assertEqual("succeeded", status["state"])
                connector_address = post(
                    client,
                    "/projects/reconciliation/connector-address",
                    {"root": root, "previewId": confirmed["previewId"], "ordinal": 0},
                )
                connector_command = {"root": root, "commandId": new_uuid_v7(), "source": connector_address}
                second = post(client, "/projects/reconciliation/exact", connector_command)
                self.assertEqual("exact-linked", second["disposition"])
                self.assertEqual(first["workId"], second["workId"])
                self.assertNotEqual(first["workRevisionId"], second["workRevisionId"])
                self.assertEqual("inferred", second["knowledgeStatus"])
                current_member = next(
                    item
                    for item in repository.manifest_members(manifest.revision_id, after=0, limit=10)
                    if item.decision.included
                )
                self.assertEqual(original, current_member.model_dump_json())
                self.assertEqual(["api.crossref.org"], calls)
                post(client, "/projects/reconciliation/exact", command | {"source": connector_address}, 409)
                forged = connector_command | {
                    "commandId": new_uuid_v7(),
                    "source": connector_address | {"revisionId": new_uuid_v7()},
                }
                post(client, "/projects/reconciliation/exact", forged, 409)
                authority.policy(False)
                self.assertEqual(second, post(client, "/projects/reconciliation/exact", connector_command))
                post(client, "/projects/close", {"root": root})
                response = client.post("/projects/reconciliation/exact", json=command)
                self.assertNotEqual(200, response.status_code)
            restarted = application("d")
            with helper.client(restarted) as client:
                post(client, "/projects/open", {"root": root})
                self.assertEqual(second, post(client, "/projects/reconciliation/exact", connector_command))
                inspection = post(
                    client,
                    "/projects/reconciliation/inspect",
                    {"root": root, "assertionRevisionId": second["assertionRevisionId"]},
                )
                self.assertEqual("unverified", inspection["assertion"]["identifiers"][0]["verificationState"])
                doi = next(item for item in inspection["normalizedIdentifiers"] if item["scheme"] == "doi")
                self.assertEqual("10.99999/synthetic-0", doi["canonical"])
                self.assertFalse(doi["registryVerified"])
                title = next(item for item in inspection["canonicalFields"] if item["name"] == "title")
                self.assertEqual("disputed", title["status"])
                self.assertIsNone(title["selected"])
                self.assertEqual(2, len(title["observations"]))
                authority.service = restarted.state.runtime.intents
                current_intent = authority.service.workspace(root).current
                assert current_intent is not None
                intent_request = authority_fixture.fixtures.draft_request(
                    root, expected_revision=current_intent.revision
                )
                impact = authority.service.preview(intent_request.to_impact_request())
                intent_request = intent_request.model_copy(
                    update={"impact_acknowledgement": impact.acknowledgement_token}
                )
                pending_intent = authority.service.save_draft(
                    intent_request, trace_id="4" * 32, idempotency_key="6" * 32
                )
                post(client, "/projects/reconciliation/exact", connector_command, 403)
                post(
                    client,
                    "/projects/reconciliation/inspect",
                    {"root": root, "assertionRevisionId": second["assertionRevisionId"]},
                    403,
                )
                authority.accept(pending_intent)
                self.assertEqual(second, post(client, "/projects/reconciliation/exact", connector_command))
                service = restarted.state.runtime.imports
                repository = service._adapters(Path(root), identity).previews
                repository.revise_draft(
                    preview,
                    PreviewDraftChange(
                        expected_revision=1,
                        actor=service.actor("2" * 32),
                        rights=rights.model_copy(
                            update={"index": ImportPermission(value="denied", basis="researcher-confirmed")}
                        ),
                    ),
                )
                post(client, "/projects/reconciliation/exact", connector_command, 403)
                post(
                    client,
                    "/projects/reconciliation/inspect",
                    {"root": root, "assertionRevisionId": second["assertionRevisionId"]},
                    403,
                )
                self.assertEqual(["api.crossref.org"], calls)
                self.assertNotEqual(b"SQLite format 3\x00", (Path(root) / "state/project.sqlite3").read_bytes()[:16])
                post(client, "/projects/close", {"root": root})
        report = {
            "fixtureKind": "synthetic-import-and-crossref-production-core",
            "realWindowsPrincipal": True,
            "dpapiAndSqlcipher": True,
            "exactSourcesConverged": True,
            "restartPreserved": True,
            "currentRightsDenial": True,
            "sourceUnchanged": True,
            "networkRequests": len(calls),
            "networkDuringReconciliation": 0,
        }
        (directory / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"report": (directory / "result.json").relative_to(REPO).as_posix()}), flush=True)
