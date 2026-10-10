"""Actual Core/Native principal, Windows vault and SQLCipher; synthetic parse only."""

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.document_attachment_repository import LocalDocumentAttachmentService
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.main import create_runtime_app
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.desktop.tools.seed_document_drop_fixture import seed
from tests.documents.test_citation_repository import BODY, citation_ir
from tests.documents.viewer_native_windows_fixture import publish_derive, seed_revision
from tests.service import test_import_preview_service as runtime_fixture

ROOT = Path(__file__).resolve().parents[2]

RAW = BODY + "[1] Synthetic Author (2024). Synthetic document drop Work. doi:10.99999/document-drop"


@unittest.skipUnless(sys.platform == "win32", "Actual Windows-backed local composition")
class CitationServiceTests(unittest.TestCase):
    def test_actual_runtime_citation_publication_reference_refresh_reopen_denial_and_budget(self):
        root = Path(tempfile.mkdtemp(prefix="directory-dialog-reference-service-", dir=ROOT / "artifacts/tmp"))
        self.assertEqual(root.parent.resolve(), (ROOT / "artifacts/tmp").resolve())
        for name in ("projects", "vault", "temporary", "application-data", "webview"):
            (root / name).mkdir()
        selected = seed(root)
        project = root / "projects/document-drop-project"
        helper = runtime_fixture.ImportRuntimeCompositionTests()
        app = create_runtime_app(
            settings=CoreSettings(),
            profile_vault_root=root / "vault",
            workflow_context=NativeWorkflowContext("b" * 32, "c" * 32),
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        with (
            patch(
                "research_observatory_core.repositories._windows_worker_capacity",
                return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
            ),
            helper.client(app) as client,
        ):
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            revisions = app.state.runtime.document_revisions
            revisions.shutdown()  # No installed model/parser can claim the authored fixture.
            runtime = app.state.runtime.attachments
            session = runtime.context(str(project), selected["projectId"])

            def attach(service, actor):
                def inspect(stream, **_):
                    content = stream.read()
                    return SimpleNamespace(
                        format="plain-text",
                        media_type="text/plain",
                        size_bytes=len(content),
                        sha256=hashlib.sha256(content).hexdigest(),
                    )

                local = LocalDocumentAttachmentService(
                    service._database, selected["projectId"], service._objects, inspector=inspect
                )
                operation = new_uuid_v7()
                candidate = local.stage(
                    io.BytesIO(RAW.encode()),
                    source_name="synthetic-reference.txt",
                    declared_media_type="text/plain",
                    source_assertion_revision_id=selected["sourceAssertionRevisionId"],
                    work_id=selected["workId"],
                    work_revision_id=selected["workRevisionId"],
                    version_id=selected["versionId"],
                    version_revision_id=selected["versionRevisionId"],
                    actor=actor,
                    operation_id=operation,
                    session_id=session,
                )
                attached = local.commit(
                    candidate.candidate_id,
                    confirmation_sha256=candidate.candidate_sha256,
                    command_id=new_uuid_v7(),
                    actor=actor,
                    operation_id=operation,
                    session_id=session,
                    match_confirmed=True,
                    permitted_use="project-only",
                    exact_selection=tuple(
                        selected[k]
                        for k in (
                            "sourceAssertionRevisionId",
                            "workId",
                            "workRevisionId",
                            "versionId",
                            "versionRevisionId",
                        )
                    ),
                )
                return candidate, attached

            candidate, attached = runtime._action(str(project), selected["projectId"], session, "1" * 32, attach)
            publish_derive(runtime, project, selected["projectId"], session, candidate, "permitted")
            accepted = seed_revision(
                app,
                project,
                selected["projectId"],
                session,
                attached.attachment_id,
                RAW,
                change=lambda value: citation_ir(value, raw=RAW, identifier="10.99999/document-drop"),
            )
            address = {"root": str(project), "projectId": selected["projectId"], "sessionId": session}

            def post(action, fields):
                return client.post("/native/document-revisions/" + action, json={**address, **fields})

            read = dict(revisionId=accepted.revision_id, expectedCollectionRevisionId=None, afterOrder=None)
            reference = post(
                "references-enrich",
                dict(
                    enrichment=dict(
                        revisionId=accepted.revision_id, commandId=new_uuid_v7(), expectedCollectionRevisionId=None
                    )
                ),
            )
            self.assertEqual(200, reference.status_code, reference.text)
            self.assertEqual("exact-linked", reference.json()["entries"][0]["linkState"])
            self.assertEqual(200, post("citations-read", read).status_code)
            self.assertIsNone(post("citations-read", read).json())
            command = dict(
                revisionId=accepted.revision_id,
                commandId=new_uuid_v7(),
                referenceCollectionRevisionId=reference.json()["collectionRevisionId"],
                expectedCollectionRevisionId=None,
            )
            response = post("citations-enrich", dict(enrichment=command))
            self.assertEqual(200, response.status_code, response.text)
            page = response.json()
            self.assertEqual("[1]", page["entries"][0]["markerPreview"])
            self.assertEqual("candidate", page["entries"][0]["resolution"])
            self.assertIn("Missing [9]", page["entries"][0]["paragraph"]["textPreview"])
            self.assertEqual(selected["workId"], page["entries"][0]["targets"][0]["references"][0]["target"]["workId"])
            self.assertEqual("unverified", page["scholarlyVerification"])
            self.assertEqual(page, post("citations-enrich", dict(enrichment=command)).json())
            next_page = post(
                "citations-read", read | dict(afterOrder=0, expectedCollectionRevisionId=page["collectionRevisionId"])
            )
            self.assertEqual(200, next_page.status_code, next_page.text)
            self.assertEqual("unresolved", next_page.json()["entries"][0]["resolution"])
            self.assertEqual(23, next_page.json()["entries"][0]["textOffset"])
            bad = post(
                "citations-enrich", dict(enrichment=command | dict(commandId=new_uuid_v7(), context="untrusted"))
            )
            self.assertEqual(422, bad.status_code)
            with patch(
                "research_observatory_core.document_viewer_allocations.ViewerArtifactReads.cost_multiplier", 10**9
            ):
                limited = post("citations-read", read)
                self.assertEqual(200, limited.status_code, limited.text)
                self.assertEqual("viewer-resource-limit", limited.json()["reasonCode"])
                self.assertNotIn("markerPreview", limited.text)
            publish_derive(runtime, project, selected["projectId"], session, candidate, "denied")
            denied = post("citations-read", read)
            self.assertEqual(409, denied.status_code)
            self.assertNotIn("markerPreview", denied.text)
            self.assertNotIn("collectionRevisionId", denied.text)
            publish_derive(runtime, project, selected["projectId"], session, candidate, "permitted")
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            self.assertEqual(409, post("citations-read", read).status_code)
            session = runtime.context(str(project), selected["projectId"])
            address["sessionId"] = session
            self.assertEqual(page, post("citations-read", read).json())
            refreshed = post(
                "references-enrich",
                dict(
                    enrichment=dict(
                        revisionId=accepted.revision_id,
                        commandId=new_uuid_v7(),
                        expectedCollectionRevisionId=reference.json()["collectionRevisionId"],
                    )
                ),
            )
            self.assertEqual(200, refreshed.status_code, refreshed.text)
            stale = post("citations-read", read)
            self.assertEqual(200, stale.status_code, stale.text)
            self.assertEqual("citations-unavailable", stale.json()["reasonCode"])
            self.assertNotIn("markerPreview", stale.text)
            self.assertEqual(409, post("citations-enrich", dict(enrichment=command)).status_code)
            new_command = command | dict(
                commandId=new_uuid_v7(),
                expectedCollectionRevisionId=page["collectionRevisionId"],
                referenceCollectionRevisionId=refreshed.json()["collectionRevisionId"],
            )
            replacement = post("citations-enrich", dict(enrichment=new_command))
            self.assertEqual(200, replacement.status_code, replacement.text)
            self.assertNotEqual(page["collectionRevisionId"], replacement.json()["collectionRevisionId"])
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
        self.assertNotEqual(b"SQLite format 3\x00", (project / "state/project.sqlite3").read_bytes()[:16])
        (root / "citation-service-receipt.json").write_text(
            json.dumps(
                dict(
                    scope="actual Windows vault/Core/SQLCipher, authored IR, no model",
                    modelExecuted=False,
                    candidateCollection=page["collectionRevisionId"],
                    refreshedCollection=replacement.json()["collectionRevisionId"],
                )
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
