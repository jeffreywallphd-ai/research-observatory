"""Owned Windows fixture: synthetic parser output, real vault/Core/SQLCipher.

The later Wry production-component test uses actual Native correction dispatch.
No model executes, and all paths/identity receipts stay in ignored task output.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.document_attachment_repository import LocalDocumentAttachmentService  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.main import create_runtime_app  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402
from research_observatory_core.workflow_executor import WorkerCapacity  # noqa: E402

from tests.desktop.tools.seed_document_drop_fixture import seed  # noqa: E402
from tests.documents.viewer_native_windows_fixture import seed_revision  # noqa: E402
from tests.service import test_import_preview_service as runtime_fixture  # noqa: E402

RAW = "SYNTHETIC Native correction witness source. Original parser text is retained."


def create():
    root = Path(tempfile.mkdtemp(prefix="directory-dialog-correction-native-", dir=ROOT / "artifacts/tmp"))
    if root.parent.resolve() != (ROOT / "artifacts/tmp").resolve() or root.is_symlink() or root.is_junction():
        raise RuntimeError("Owned fixture required")
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
        response = client.post("/projects/open", json={"root": str(project)})
        if response.status_code != 200:
            raise RuntimeError("Fixture open failed")
        app.state.runtime.document_revisions.shutdown()
        runtime = app.state.runtime.attachments
        session = runtime.context(str(project), selected["projectId"])

        def attach(service, actor):
            def inspect(stream, **_):
                raw = stream.read()
                return SimpleNamespace(
                    format="plain-text",
                    media_type="text/plain",
                    size_bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),
                )

            local = LocalDocumentAttachmentService(
                service._database, selected["projectId"], service._objects, inspector=inspect
            )
            operation = new_uuid_v7()
            candidate = local.stage(
                io.BytesIO(RAW.encode()),
                source_name="SYNTHETIC-correction.txt",
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
            prior = service._rights.current(candidate.rights_subject, actor=actor)
            permissions = tuple(
                RightsPermissionDraft(
                    use=RightsUse(
                        action=action,
                        purpose="document-attachment" if action == "store" else "document-analysis",
                        destination_kind="local-project",
                    ),
                    value="permitted",
                    basis="researcher-confirmed",
                    confidence="confirmed",
                    grantee_actor_id=actor.actor_id,
                    evidence_revision_ids=(candidate.source_assertion_revision_id,),
                )
                for action in ("store", "inspect", "derive")
            )
            service._rights.publish_draft(
                candidate.rights_subject,
                permissions,
                prior.revision_id,
                command_id=new_uuid_v7(),
                command_sha256="5" * 64,
                actor=actor,
            )
            return attached

        attached = runtime._action(str(project), selected["projectId"], session, "1" * 32, attach)
        original = seed_revision(app, project, selected["projectId"], session, attached.attachment_id, RAW)
        receipt = {
            "root": str(project),
            "projectId": selected["projectId"],
            "originalRevisionId": original.revision_id,
            "documentId": original.document_id,
            "jobId": original.result.binding.attempt.job_id,
            "attachmentId": attached.attachment_id,
            "sourceSha256": original.structure.binding.source.object_sha256,
            "raw": RAW,
            "modelExecuted": False,
        }
        (root / "correction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return root


if __name__ == "__main__":
    print(json.dumps({"fixture": str(create()), "modelExecuted": False}))
