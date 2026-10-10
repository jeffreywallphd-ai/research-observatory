"""Actual Native Core, Windows vault and SQLCipher; no model/parser execution."""

import hashlib
import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.document_attachment_repository import LocalDocumentAttachmentService  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.main import create_runtime_app  # noqa: E402
from research_observatory_core.parsing.quality import ParsingQualityReport  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402
from research_observatory_core.workflow_executor import WorkerCapacity  # noqa: E402

from tests.desktop.tools.seed_document_drop_fixture import seed  # noqa: E402
from tests.documents.viewer_native_windows_fixture import seed_revision  # noqa: E402
from tests.service import test_import_preview_service as runtime_fixture  # noqa: E402

RAW = "SYNTHETIC parsing-quality protected source."


@unittest.skipUnless(sys.platform == "win32", "Actual Windows vault composition")
class ParsingQualityServiceTests(unittest.TestCase):
    def test_actual_native_quality_reopen_rights_principal_and_stopped_delivery(self):
        root = Path(tempfile.mkdtemp(prefix="directory-dialog-parsing-quality-", dir=ROOT / "artifacts/tmp"))
        self.assertEqual((ROOT / "artifacts/tmp").resolve(), root.parent.resolve())
        for name in ("projects", "vault", "temporary", "application-data", "webview"):
            (root / name).mkdir()
        selected = {key: value for key, value in seed(root).items() if isinstance(value, str)}
        project = root / "projects/document-drop-project"
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
            revisions = app.state.runtime.document_revisions
            revisions.shutdown()
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
                    source_name="synthetic-quality.txt",
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
                    exact_selection=(
                        selected["sourceAssertionRevisionId"],
                        selected["workId"],
                        selected["workRevisionId"],
                        selected["versionId"],
                        selected["versionRevisionId"],
                    ),
                )
                return candidate, attached

            candidate, attached = runtime._action(str(project), selected["projectId"], session, "1" * 32, attach)

            def permissions(denied=None):
                def publish(service, actor):
                    prior = service._rights.current(candidate.rights_subject, actor=actor)
                    values = tuple(
                        RightsPermissionDraft(
                            use=RightsUse(
                                action=action,
                                purpose="document-attachment" if action == "store" else "document-analysis",
                                destination_kind="local-project",
                            ),
                            value="denied" if action == denied else "permitted",
                            basis="researcher-confirmed",
                            confidence="confirmed",
                            grantee_actor_id=actor.actor_id,
                            evidence_revision_ids=(candidate.source_assertion_revision_id,),
                        )
                        for action in ("store", "inspect", "derive")
                    )
                    service._rights.publish_draft(
                        candidate.rights_subject,
                        values,
                        prior.revision_id,
                        command_id=new_uuid_v7(),
                        command_sha256="5" * 64,
                        actor=actor,
                    )

                runtime._action(str(project), selected["projectId"], session, "1" * 32, publish)

            permissions()
            accepted = seed_revision(app, project, selected["projectId"], session, attached.attachment_id, RAW)
            address = {
                "root": str(project),
                "projectId": selected["projectId"],
                "sessionId": session,
                "jobId": accepted.result.binding.attempt.job_id,
            }

            def read():
                return client.post("/native/document-revisions/parse-quality", json=address)

            response = read()
            self.assertEqual(200, response.status_code, response.text)
            report = response.json()
            self.assertEqual(accepted.result.result_id, report["resultId"])
            self.assertEqual(accepted.result.binding.source.model_dump(mode="json", by_alias=True), report["source"])
            self.assertEqual(accepted.result.binding.attempt.attempt_id, report["attemptId"])
            self.assertEqual("unverified", report["assessment"]["scholarlyVerification"])
            self.assertNotIn(RAW, response.text)
            for right in ("inspect", "derive"):
                permissions(right)
                denied = read()
                self.assertEqual(409, denied.status_code)
                self.assertNotIn("resultId", denied.text)
                self.assertNotIn("dimensions", denied.text)
                self.assertNotIn(RAW, denied.text)
                permissions()
            factory = revisions.repository_factory
            for field, altered in (("actor_type", "worker"), ("intent_sha256", "0" * 64), ("policy_sha256", "0" * 64)):

                def changed(*args, field=field, altered=altered, **kwargs):
                    actor = kwargs["actor"]
                    kwargs["actor"] = lambda: replace(actor(), **{field: altered})
                    return factory(*args, **kwargs)

                with patch.object(revisions, "repository_factory", changed):
                    self.assertEqual(409, read().status_code)
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            self.assertEqual(409, read().status_code)
            session = runtime.context(str(project), selected["projectId"])
            address["sessionId"] = session
            self.assertEqual(report, read().json())
            original_dump = ParsingQualityReport.model_dump

            def stop_after_materialization(value, *args, **kwargs):
                output = original_dump(value, *args, **kwargs)
                if kwargs.get("mode") == "json":
                    revisions.imports.signal_stop(str(project))
                return output

            with patch.object(ParsingQualityReport, "model_dump", stop_after_materialization):
                stopped = read()
                self.assertEqual(409, stopped.status_code)
                self.assertNotIn("dimensions", stopped.text)
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
        self.assertNotEqual(b"SQLite format 3\x00", (project / "state/project.sqlite3").read_bytes()[:16])
        (root / "parsing-quality-service-receipt.json").write_text(
            json.dumps(
                {
                    "scope": "actual Native Core/Windows vault/SQLCipher; authored parser output",
                    "modelExecuted": False,
                    "jobId": report["jobId"],
                    "attemptId": report["attemptId"],
                    "resultId": report["resultId"],
                    "schemaVersion": report["schemaVersion"],
                }
            ),
            encoding="utf-8",
        )
        plain_app = helper.application(None)
        with helper.client(plain_app) as plain_client:
            denied = plain_client.post("/native/document-revisions/parse-quality", json=address)
            self.assertEqual(409, denied.status_code)
            self.assertNotIn("dimensions", denied.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
