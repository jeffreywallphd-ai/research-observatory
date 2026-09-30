"""Production Core/DPAPI/SQLCipher/import/connector handoff; synthetic HTTP only."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
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
from tests.connectors.source_public_handoff import assert_source_handoff
from tests.connectors.test_connector_settings import CONTACT, KEY
from tests.connectors.test_connector_transport import BytesStream
from tests.service import test_import_preview_service as runtime_fixture

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "nt", "Windows DPAPI and SQLCipher required")
class ReconciliationRuntimeTests(unittest.TestCase):
    def test_import_and_four_retained_providers_batch_replays_after_core_reconstruction(self):
        directory = Path(tempfile.mkdtemp(prefix="reconciliation-batch-", dir=REPO / "artifacts/tmp"))
        helper = runtime_fixture.ImportRuntimeCompositionTests()
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
        rights_json = rights.model_dump(mode="json", by_alias=True)
        documents = source_fixture.documents(1)
        calls: list[str] = []
        retained: dict[str, Any] = {}
        addresses: dict[str, Any] = {}

        async def respond(wire):
            provider = {
                "api.openalex.org": "openalex",
                "api.crossref.org": "crossref",
                "api.unpaywall.org": "unpaywall",
                "api.semanticscholar.org": "semantic-scholar",
            }[wire.url.host]
            calls.append(provider)
            if provider == "unpaywall":
                self.assertEqual(CONTACT, wire.url.params["email"])
            if provider == "semantic-scholar":
                self.assertEqual(KEY, wire.headers["x-api-key"])
            response = httpx2.Response(200, json=documents[provider])
            return httpx2.Response(200, headers=response.headers, stream=BytesStream(response.content))

        def application(nonce):
            app = create_runtime_app(
                settings=CoreSettings(),
                profile_vault_root=directory / "vault",
                # A reconstructed Core keeps the authorized resume epoch. A new
                # epoch deliberately invalidates durable batch scheduling authority.
                workflow_context=NativeWorkflowContext("b" * 32, nonce * 32),
                capability_digest=capability_token_digest("a" * 64),
                expected_authority="127.0.0.1:49152",
            )
            return app

        def post(client, route, body, expected=200):
            response = client.post(route, json=body)
            self.assertEqual(expected, response.status_code, response.text)
            return response.json()

        def inspect_handoff(client):
            works = post(client, "/projects/reconciliation/versions/works", {"root": root, "after": None, "limit": 32})
            self.assertIsNone(works["nextAfter"])
            self.assertEqual(2, len(works["items"]))
            self.assertEqual([2, 3], sorted(len(work["assertionRevisionIds"]) for work in works["items"]))
            inspections: dict[str, Any] = {}
            for work in works["items"]:
                self.assertEqual("active", work["disposition"])
                for revision in work["assertionRevisionIds"]:
                    inspection = post(
                        client, "/projects/reconciliation/inspect", {"root": root, "assertionRevisionId": revision}
                    )
                    assertion = inspection["assertion"]
                    provider = assertion["provider"]
                    self.assertNotIn(provider, inspections)
                    inspections[provider] = inspection
                    self.assertEqual(identity, assertion["projectId"])
                    self.assertEqual(addresses[provider], assertion["address"])
                    self.assertEqual(rights_json, assertion["rights"])
                    self.assertEqual(
                        {"workId": work["workId"], "revisionId": work["revisionId"]}, inspection["canonicalWork"]
                    )
                    self.assertTrue(assertion["fields"])
                    for observation in (*assertion["fields"], *assertion["identifiers"]):
                        self.assertEqual("observed", observation["origin"])
                        self.assertTrue(observation["sourceSelector"])
                    self.assertTrue(all(item["verificationState"] == "unverified" for item in assertion["identifiers"]))
                    doi = next(item for item in inspection["normalizedIdentifiers"] if item["scheme"] == "doi")
                    expected_doi = (
                        "10.99999/synthetic-adapter"
                        if provider in {"unpaywall", "semantic-scholar"}
                        else "10.99999/synthetic-0"
                    )
                    self.assertEqual(expected_doi, doi["canonical"])
                    self.assertFalse(doi["registryVerified"])
                    if provider == "local-import":
                        self.assertEqual(member.source_record_revision_id, assertion["sourceRevisionId"])
                    else:
                        record = retained[provider]["page"].records[0]
                        self.assertEqual(addresses[provider]["revisionId"], assertion["sourceRevisionId"])
                        self.assertEqual(
                            hashlib.sha256(record.model_dump_json(by_alias=True).encode()).hexdigest(),
                            assertion["sourceSha256"],
                        )
            self.assertEqual({"local-import", *source_fixture.PROVIDERS}, set(inspections))
            for group in (("local-import", "openalex", "crossref"), ("unpaywall", "semantic-scholar")):
                self.assertEqual(1, len({inspections[provider]["canonicalWork"]["workId"] for provider in group}))
            return works, inspections

        def assert_sources_unchanged(runtime):
            imports = runtime.imports
            self.assertEqual(manifest.model_dump_json(), imports.import_manifest(root, preview).model_dump_json())
            members = imports.import_manifest_members(
                root, preview, revision_id=manifest.revision_id, after=0, limit=10
            )
            self.assertEqual(original_members, [item.model_dump_json() for item in members])
            pages = runtime.connectors._adapters(Path(root), identity).pages
            for saved in retained.values():
                self.assertEqual(saved["original"], pages.replay(saved["request"]).model_dump_json())

        with patch(
            "research_observatory_core.repositories._windows_worker_capacity",
            return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
        ):
            first = application("c")
            with helper.client(first) as client:
                runtime = first.state.runtime
                runtime.connectors._transport_factory = lambda: httpx2.MockTransport(respond)
                project = post(
                    client,
                    "/projects",
                    {
                        "parentDirectory": str(directory),
                        "directoryName": "project",
                        "displayName": "Synthetic five-source batch",
                        "primaryUseCase": "theory-synthesis",
                        "researchObjective": "Synthetic source-to-reconciliation handoff",
                    },
                )
                root, identity = project["root"], project["projectId"]
                post(client, "/projects/open", {"root": root})
                denied = client.post(
                    "/projects/reconciliation/batches/prepare", json={"root": root}, headers={"Authorization": ""}
                )
                self.assertEqual(401, denied.status_code, denied.text)
                authority = authority_fixture.ConnectorAuthorityFixture()
                authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
                authority.intent(providers=source_fixture.PROVIDERS)
                authority.policy()
                for provider, key, contact in (("unpaywall", None, CONTACT), ("semantic-scholar", KEY, None)):
                    post(
                        client,
                        "/native/connectors/configuration/replace",
                        {
                            "root": root,
                            "projectId": identity,
                            "providerId": provider,
                            "key": key,
                            "contact": contact,
                            "expectedVersion": None,
                        },
                    )
                self.assertEqual([], calls)
                imports = runtime.imports
                preview = new_uuid_v7()
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
                members = imports.import_manifest_members(
                    root, preview, revision_id=manifest.revision_id, after=0, limit=10
                )
                original_members = [item.model_dump_json() for item in members]
                included = [item for item in members if item.decision.included]
                self.assertEqual(1, len(included))
                member = included[0]
                addresses["local-import"] = {
                    "kind": "import-member",
                    "contextId": preview,
                    "revisionId": manifest.revision_id,
                    "ordinal": member.ordinal,
                    "recordKey": member.record_key,
                }
                handoff = []
                for provider in source_fixture.PROVIDERS:
                    request = source_fixture.source_request(provider, identity, 1)
                    confirmed = post(
                        client,
                        "/projects/connectors/previews",
                        {
                            "root": root,
                            "request": request.model_dump(mode="json", by_alias=True),
                            "retention": {"rights": rights_json, "retainBody": True},
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
                    page = runtime.connectors._adapters(Path(root), identity).pages.replay(request)
                    self.assertIsNotNone(page)
                    self.assertEqual(1, len(page.records))
                    self.assertEqual("disabled", page.cache.state)
                    self.assertNotIn(CONTACT, page.model_dump_json())
                    self.assertNotIn(KEY, page.model_dump_json())
                    retained[provider] = {"request": request, "page": page, "original": page.model_dump_json()}
                    handoff.append(
                        {"page": page.model_dump(mode="json", by_alias=True), "retention": confirmed["retention"]}
                    )
                    addresses[provider] = post(
                        client,
                        "/projects/reconciliation/connector-address",
                        {"root": root, "previewId": confirmed["previewId"], "ordinal": 0},
                    )
                assert_source_handoff(self, handoff, 1)
                self.assertCountEqual(source_fixture.PROVIDERS, calls)
                # Freeze the request under offline policy: reconciliation consumes
                # retained owner records, never a new provider response.
                authority.policy(False)
                request_id = post(client, "/projects/reconciliation/batches/prepare", {"root": root})["requestId"]
                batch_body = {"root": root, "requestId": request_id}
                scheduled = post(client, "/projects/reconciliation/batches/schedule", batch_body)
                runtime.reconciliation.run_pending()
                status_body = batch_body | {"jobId": scheduled["jobId"]}
                completed = post(client, "/projects/reconciliation/batches/status", status_body)
                self.assertEqual("succeeded", completed["state"])
                self.assertIsNotNone(completed["setRevisionId"])
                self.assertEqual(completed, post(client, "/projects/reconciliation/batches/schedule", batch_body))
                post(client, "/projects/reconciliation/batches/status", status_body | {"requestId": new_uuid_v7()}, 403)
                candidate_body = {"root": root, "setRevisionId": completed["setRevisionId"], "after": 0, "limit": 100}
                candidates = post(client, "/projects/reconciliation/candidates", candidate_body)
                self.assertEqual(request_id, candidates["requestId"])
                self.assertEqual(5, candidates["recordCount"])
                self.assertEqual("unchanged", candidates["inventoryState"])
                self.assertEqual("unchanged", candidates["membershipState"])
                self.assertIsNone(candidates["nextAfter"])
                works, inspections = inspect_handoff(client)
                assert_sources_unchanged(runtime)
                self.assertCountEqual(source_fixture.PROVIDERS, calls)
                post(client, "/projects/close", {"root": root})
            # This is a second production Core instance in the same test process,
            # not a native subprocess restart or an interrupted-worker recovery.
            restarted = application("d")
            with helper.client(restarted) as client:
                restarted.state.runtime.connectors._transport_factory = lambda: httpx2.MockTransport(respond)
                post(client, "/projects/open", {"root": root})
                self.assertEqual(completed, post(client, "/projects/reconciliation/batches/schedule", batch_body))
                self.assertEqual(completed, post(client, "/projects/reconciliation/batches/status", status_body))
                self.assertEqual(candidates, post(client, "/projects/reconciliation/candidates", candidate_body))
                self.assertEqual((works, inspections), inspect_handoff(client))
                assert_sources_unchanged(restarted.state.runtime)
                self.assertCountEqual(source_fixture.PROVIDERS, calls)
                self.assertNotEqual(b"SQLite format 3\x00", (Path(root) / "state/project.sqlite3").read_bytes()[:16])
                post(client, "/projects/close", {"root": root})
        report = {
            "fixtureKind": "synthetic-import-and-four-providers-production-core-batch",
            "dpapiAndSqlcipher": True,
            "restartScope": "same-process-core-reconstruction-same-resume-epoch",
            "nativeContext": "isolated",
            "sourceRecords": candidates["recordCount"],
            "activeWorks": len(works["items"]),
            "membershipSizes": sorted(len(work["assertionRevisionIds"]) for work in works["items"]),
            "sourceAddressesAndRightsBound": True,
            "immutableSourceObservations": True,
            "unauthenticatedAndForeignRequestDenied": True,
            "acceptedBatchReplayUnchanged": True,
            "networkRequests": len(calls),
            "networkDuringReconciliationAndReplay": 0,
        }
        report_bytes = (json.dumps(report, indent=2) + "\n").encode("utf-8")
        report_path = directory / "result.json"
        report_path.write_bytes(report_bytes)
        print(
            json.dumps(
                {
                    "report": report_path.relative_to(REPO).as_posix(),
                    "reportSha256": hashlib.sha256(report_bytes).hexdigest(),
                    "reportData": report,
                }
            ),
            flush=True,
        )

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
                original_inspection = post(
                    client,
                    "/projects/reconciliation/inspect",
                    {"root": root, "assertionRevisionId": first["assertionRevisionId"]},
                )
                self.assertEqual(first, original_inspection["result"])
                self.assertEqual(
                    {"workId": first["workId"], "revisionId": second["workRevisionId"]},
                    original_inspection["canonicalWork"],
                )
                self.assertEqual(inspection["canonicalFields"], original_inspection["canonicalFields"])
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
        report_bytes = (json.dumps(report, indent=2) + "\n").encode("utf-8")
        (directory / "result.json").write_bytes(report_bytes)
        print(
            json.dumps(
                {
                    "report": (directory / "result.json").relative_to(REPO).as_posix(),
                    "reportSha256": hashlib.sha256(report_bytes).hexdigest(),
                    "reportData": report,
                }
            ),
            flush=True,
        )
