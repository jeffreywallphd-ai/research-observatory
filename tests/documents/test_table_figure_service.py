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
from tests.documents.test_table_figure_repository import RAW, table_figure_ir
from tests.documents.viewer_native_windows_fixture import publish_derive, seed_revision
from tests.service import test_import_preview_service as runtime_fixture

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == "win32", "Actual Windows-backed local composition")
class TableFigureServiceTests(unittest.TestCase):
    def test_actual_runtime_tables_exclusion_reopen_denial_session_and_budget(self):
        root = Path(tempfile.mkdtemp(prefix="directory-dialog-table-figure-service-", dir=ROOT / "artifacts/tmp"))
        self.assertEqual(root.parent.resolve(), (ROOT / "artifacts/tmp").resolve())
        for name in ("projects", "vault", "temporary", "application-data", "webview"):
            (root / name).mkdir()
        selected = seed(root)

        def identity(key: str) -> str:
            value = selected[key]
            assert isinstance(value, str)
            return value

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
            session = runtime.context(str(project), identity("projectId"))

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
                    service._database, identity("projectId"), service._objects, inspector=inspect
                )
                operation = new_uuid_v7()
                candidate = local.stage(
                    io.BytesIO(RAW.encode()),
                    source_name="synthetic-reference.txt",
                    declared_media_type="text/plain",
                    source_assertion_revision_id=identity("sourceAssertionRevisionId"),
                    work_id=identity("workId"),
                    work_revision_id=identity("workRevisionId"),
                    version_id=identity("versionId"),
                    version_revision_id=identity("versionRevisionId"),
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
                    exact_selection=(
                        identity("sourceAssertionRevisionId"),
                        identity("workId"),
                        identity("workRevisionId"),
                        identity("versionId"),
                        identity("versionRevisionId"),
                    ),
                )
                return candidate, attached

            candidate, attached = runtime._action(str(project), identity("projectId"), session, "1" * 32, attach)
            publish_derive(runtime, project, identity("projectId"), session, candidate, "permitted")
            accepted = seed_revision(
                app,
                project,
                identity("projectId"),
                session,
                attached.attachment_id,
                RAW,
                change=table_figure_ir,
            )
            address = {"root": str(project), "projectId": identity("projectId"), "sessionId": session}

            def post(action, fields):
                return client.post("/native/document-revisions/" + action, json={**address, **fields})

            read = dict(
                revisionId=accepted.revision_id,
                expectedCollectionRevisionId=None,
                afterOrder=None,
                afterCell=None,
                cellObjectId=None,
            )
            self.assertIsNone(post("table-figures-read", read).json())
            command = dict(
                schemaVersion="1.0",
                revisionId=accepted.revision_id,
                commandId=new_uuid_v7(),
                expectedCollectionRevisionId=None,
            )
            response = post("table-figures-enrich", dict(enrichment=command))
            self.assertEqual(200, response.status_code, response.text)
            page = response.json()
            self.assertEqual(["A", "B"], [c["textPreview"] for c in page["entries"][0]["cells"]])
            self.assertEqual("low-confidence", page["entries"][0]["cells"][0]["triage"])
            self.assertEqual("unverified", page["scholarlyVerification"])
            self.assertEqual(page, post("table-figures-enrich", dict(enrichment=command)).json())
            next_page = post(
                "table-figures-read",
                read | dict(afterOrder=0, expectedCollectionRevisionId=page["collectionRevisionId"]),
            )
            self.assertEqual(200, next_page.status_code, next_page.text)
            self.assertEqual("figure", next_page.json()["entries"][0]["kind"])
            self.assertEqual(
                422, post("table-figures-enrich", dict(enrichment=command | dict(actorId=new_uuid_v7()))).status_code
            )
            self.assertEqual(
                422,
                post(
                    "table-figures-read", read | dict(afterCell=0, cellObjectId=page["entries"][0]["nodeId"])
                ).status_code,
            )
            exclusion = command | dict(
                commandId=new_uuid_v7(),
                expectedCollectionRevisionId=page["collectionRevisionId"],
                nodeId=page["entries"][0]["nodeId"],
                rationale="Synthetic human exclusion of unreliable extraction.",
            )
            excluded = post("table-figures-exclude", dict(enrichment=exclusion))
            self.assertEqual(200, excluded.status_code, excluded.text)
            self.assertTrue(excluded.json()["entries"][0]["excluded"])
            self.assertEqual(excluded.json(), post("table-figures-exclude", dict(enrichment=exclusion)).json())
            self.assertEqual(
                409, post("table-figures-enrich", dict(enrichment=command | dict(commandId=new_uuid_v7()))).status_code
            )
            with patch(
                "research_observatory_core.document_viewer_allocations.ViewerArtifactReads.cost_multiplier", 10**9
            ):
                limited = post("table-figures-read", read)
                self.assertEqual(200, limited.status_code, limited.text)
                self.assertEqual("viewer-resource-limit", limited.json()["reasonCode"])
                self.assertNotIn("textPreview", limited.text)
            publish_derive(runtime, project, identity("projectId"), session, candidate, "denied")
            for action, fields in (("table-figures-read", read), ("table-figures-exclude", dict(enrichment=exclusion))):
                denied = post(action, fields)
                self.assertEqual(409, denied.status_code)
                self.assertNotIn("textPreview", denied.text)
                self.assertNotIn("collectionRevisionId", denied.text)
            publish_derive(runtime, project, identity("projectId"), session, candidate, "permitted")
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            self.assertEqual(409, post("table-figures-read", read).status_code)
            session = runtime.context(str(project), identity("projectId"))
            address["sessionId"] = session
            self.assertEqual(excluded.json(), post("table-figures-read", read).json())
            replacement = post(
                "table-figures-enrich",
                dict(
                    enrichment=command
                    | dict(
                        commandId=new_uuid_v7(), expectedCollectionRevisionId=excluded.json()["collectionRevisionId"]
                    )
                ),
            )
            self.assertEqual(200, replacement.status_code, replacement.text)
            self.assertTrue(replacement.json()["entries"][0]["excluded"])
            self.assertNotEqual(page["collectionRevisionId"], replacement.json()["collectionRevisionId"])
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
        self.assertNotEqual(b"SQLite format 3\x00", (project / "state/project.sqlite3").read_bytes()[:16])
        (root / "table-figure-service-receipt.json").write_text(
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
