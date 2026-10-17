"""Real Windows DPAPI/Core/SQLCipher API composition; synthetic startup principal.

This is distinct from the real Rust-supervisor/generated-client qualification.
All source records and human confirmations belong to this isolated fixture.
"""

import hashlib
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights  # noqa: E402
from research_observatory_core.main import create_runtime_app  # noqa: E402
from research_observatory_core.ports.import_previews import PreviewCreate, PreviewDraftChange  # noqa: E402

from tests.connectors.test_connector_authority import ConnectorAuthorityFixture  # noqa: E402
from tests.service.test_import_preview_service import ImportRuntimeCompositionTests  # noqa: E402


@unittest.skipUnless(os.name == "nt", "actual current-user DPAPI and SQLCipher required")
class SearchRuntimeWindowsTests(unittest.TestCase):
    def test_headless_api_composition_positive_result_current_rights_and_no_claimed_principal(self):
        with tempfile.TemporaryDirectory(prefix="ro-search-runtime-") as directory:
            app = create_runtime_app(
                settings=CoreSettings(),
                profile_vault_root=Path(directory) / "vault",
                workflow_context=NativeWorkflowContext("b" * 32, "c" * 32),
                capability_digest=capability_token_digest("a" * 64),
                expected_authority="127.0.0.1:49152",
            )
            helper = ImportRuntimeCompositionTests()
            started, released = threading.Event(), threading.Event()

            def hold_initialized_phase(step):
                if step == "initialization-acknowledged" and not started.is_set():
                    started.set()
                    if not released.wait(8):
                        raise AssertionError("synthetic guarded-phase barrier was not released")

            with (
                patch(
                    "research_observatory_core.lexical_index_repository._index_step", side_effect=hold_initialized_phase
                ),
                helper.client(app) as client,
            ):

                def post(route, body, expected=200):
                    response = client.post(route, json=body)
                    self.assertEqual(expected, response.status_code, response.text)
                    return response.json()

                project = post(
                    "/projects",
                    {
                        "parentDirectory": directory,
                        "directoryName": "project",
                        "displayName": "Synthetic search",
                        "primaryUseCase": "theory-synthesis",
                        "researchObjective": "Synthetic local lexical lookup",
                    },
                )
                root, project_id = project["root"], project["projectId"]
                post("/projects/open", {"root": root})
                runtime = app.state.runtime
                authority = ConnectorAuthorityFixture()
                authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
                self.assertEqual("accepted", authority.intent("local-only").status)
                imports = runtime.imports
                grant = ImportPermission(value="permitted", basis="researcher-confirmed")
                rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
                preview = new_uuid_v7()
                raw = b"title,doi\nSynthetic observatory lookup,10.99999/search-runtime\n"
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
                drafts = imports._adapters(Path(root), project_id).previews
                draft = drafts.revise_draft(
                    preview, PreviewDraftChange(expected_revision=0, actor=imports.actor("2" * 32))
                )
                imports.schedule_commit(root, preview, revision=draft.revision, request_id=new_uuid_v7())
                imports.run_pending()
                manifest = imports.import_manifest(root, preview)
                member = next(
                    value
                    for value in imports.import_manifest_members(
                        root, preview, revision_id=manifest.revision_id, after=0, limit=10
                    )
                    if value.decision.included
                )
                address = {
                    "kind": "import-member",
                    "contextId": preview,
                    "revisionId": manifest.revision_id,
                    "ordinal": member.ordinal,
                    "recordKey": member.record_key,
                }
                work = post(
                    "/projects/reconciliation/exact", {"root": root, "commandId": new_uuid_v7(), "source": address}
                )
                item = post(
                    "/projects/corpus/create",
                    {
                        "root": root,
                        "commandId": new_uuid_v7(),
                        "source": address,
                        "workId": work["workId"],
                        "workRevisionId": work["workRevisionId"],
                    },
                )
                subject = {
                    "projectId": project_id,
                    "sourceAssertionRevisionId": work["assertionRevisionId"],
                    "address": address,
                    "copyId": work["assertionRevisionId"],
                    "copyLocation": "local-source",
                    "resourceClass": "metadata",
                }
                current = post("/projects/corpus/rights/current", {"root": root, "subject": subject})
                permissions = [
                    {
                        "use": {
                            "action": action,
                            "purpose": purpose,
                            "destinationKind": "local-project",
                            "provider": None,
                            "region": None,
                            "shareGroup": None,
                        },
                        "value": "permitted",
                        "basis": "researcher-confirmed",
                        "confidence": "confirmed",
                        "evidenceRevisionIds": [work["assertionRevisionId"]],
                        "licenseObservationRevisionId": None,
                        "entitlementRevisionId": None,
                        "expiresAt": None,
                    }
                    for purpose, actions in (
                        ("local-search", ("inspect", "index")),
                        ("corpus-membership", ("store", "inspect", "derive", "index")),
                    )
                    for action in actions
                ]
                post(
                    "/projects/corpus/rights/publish",
                    {
                        "root": root,
                        "commandId": new_uuid_v7(),
                        "subject": subject,
                        "permissions": permissions,
                        "expectedPredecessorRevisionId": None if current is None else current["revisionId"],
                        "confirmed": True,
                    },
                )
                command = {
                    "root": root,
                    "projectId": project_id,
                    "commandId": new_uuid_v7(),
                    "query": "identifiers:search-runtime",
                    "filters": {"yearFrom": None, "yearTo": None},
                }
                self.assertEqual(
                    401, client.post("/projects/search/run", json=command, headers={"Authorization": ""}).status_code
                )
                post("/projects/search/run", {**command, "actorId": new_uuid_v7()}, 422)
                post("/projects/search/run", {**command, "sessionId": "d" * 32}, 422)
                job = post("/projects/search/run", command)
                read = {"root": root, "projectId": project_id, "jobId": job["jobId"]}
                try:
                    self.assertTrue(started.wait(12), "the actual protected shadow did not reach the phase barrier")
                    for route, body in (
                        ("/projects/search/run", command),
                        ("/projects/search/status", read),
                        ("/projects/search/cancel", read),
                    ):
                        before = time.monotonic()
                        observed = post(route, body)
                        self.assertLess(
                            time.monotonic() - before, 1.8, "foreground API blocked by paused orchestration"
                        )
                        self.assertEqual(job["jobId"], observed["jobId"])
                finally:
                    released.set()
                cancelled_deadline = time.monotonic() + 15
                while True:
                    cancelled = post("/projects/search/status", read)
                    if (
                        cancelled["state"] in {"cancelled", "failed", "succeeded"}
                        or time.monotonic() >= cancelled_deadline
                    ):
                        break
                    time.sleep(0.05)
                self.assertEqual("cancelled", cancelled["state"])
                post("/projects/search/page", {**read, "after": None, "limit": 50}, 409)
                job = post("/projects/search/run", {**command, "commandId": new_uuid_v7()})
                read = {**read, "jobId": job["jobId"]}
                deadline = time.monotonic() + 60
                while True:
                    status = post("/projects/search/status", read)
                    if status["state"] in {"succeeded", "failed", "cancelled"} or time.monotonic() >= deadline:
                        break
                    time.sleep(0.05)
                self.assertEqual("succeeded", status["state"], status)
                page = post("/projects/search/page", {**read, "after": None, "limit": 50})
                self.assertEqual([item["itemId"]], [value["itemId"] for value in page["hits"]])
                self.assertEqual("unqualified", page["execution"]["semanticState"])
                explanation = post("/projects/search/explain", {**read, "itemId": item["itemId"]})
                self.assertTrue(explanation["components"])
                self.assertNotEqual(b"SQLite format 3\0", (Path(root) / "state/project.sqlite3").read_bytes()[:16])
                for index in (Path(root) / "indexes").glob("lexical-*.sqlite3"):
                    self.assertNotEqual(b"SQLite format 3\0", index.read_bytes()[:16])
                drafts.revise_draft(
                    preview,
                    PreviewDraftChange(
                        expected_revision=draft.revision,
                        actor=imports.actor("3" * 32),
                        rights=rights.model_copy(
                            update={"index": ImportPermission(value="denied", basis="researcher-confirmed")}
                        ),
                    ),
                )
                post("/projects/search/page", {**read, "after": None, "limit": 50}, 409)
                post("/projects/search/status", read, 409)
                post("/projects/close", {"root": root})


if __name__ == "__main__":
    unittest.main()
