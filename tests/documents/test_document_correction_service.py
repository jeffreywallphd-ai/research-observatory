"""Actual Native-authorized Core/vault/SQLCipher; authored parser output only."""

import hashlib
import io
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.document_attachment_repository import LocalDocumentAttachmentService  # noqa: E402
from research_observatory_core.document_correction_views import CorrectionPage  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.main import create_runtime_app  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402
from research_observatory_core.workflow_executor import WorkerCapacity  # noqa: E402

from tests.desktop.tools.seed_document_drop_fixture import seed  # noqa: E402
from tests.documents.viewer_native_windows_fixture import seed_revision  # noqa: E402
from tests.service import test_import_preview_service as runtime_fixture  # noqa: E402

RAW = "SYNTHETIC correction source with retained original text."


@unittest.skipUnless(sys.platform == "win32", "Actual Windows vault composition")
class DocumentCorrectionServiceTests(unittest.TestCase):
    def test_native_core_draft_accept_reopen_rights_identity_and_stopped_delivery(self):
        root = Path(tempfile.mkdtemp(prefix="directory-dialog-document-correction-", dir=ROOT / "artifacts/tmp"))
        self.assertEqual((ROOT / "artifacts/tmp").resolve(), root.parent.resolve())
        for name in ("projects", "vault", "temporary", "application-data", "webview"):
            (root / name).mkdir()
        selected = {k: v for k, v in seed(root).items() if isinstance(v, str)}
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
                    source_name="synthetic-correction.txt",
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
            original = seed_revision(
                app, project, selected["projectId"], session, attached.attachment_id, RAW, reference=True
            )
            address = {"root": str(project), "projectId": selected["projectId"], "sessionId": session}

            def post(action, **fields):
                return client.post("/native/document-corrections/" + action, json={**address, **fields})

            queue = post("queue")
            self.assertEqual(200, queue.status_code, queue.text)
            self.assertEqual(original.revision_id, queue.json()["items"][0]["revisionId"])
            page_response = post("page", revisionId=original.revision_id)
            self.assertEqual(200, page_response.status_code, page_response.text)
            page = CorrectionPage.model_validate(page_response.json())
            node = page.nodes[0]
            self.assertEqual(RAW, node.preview)
            self.assertIsNone(page.draft)
            targets = post("targets")
            self.assertEqual(200, targets.status_code, targets.text)
            target = next(item for item in targets.json()["items"] if item["workId"] == selected["workId"])
            self.assertEqual("unverified", target["scholarlyVerification"])
            save: dict[str, Any] = {
                "schemaVersion": "1.0",
                "commandId": new_uuid_v7(),
                "draftId": None,
                "expectedDraftRevisionId": None,
                "patch": {
                    "schemaVersion": "1.0",
                    "baseRevisionId": original.revision_id,
                    "expectedStructureSha256": original.structure_sha256,
                    "operations": [
                        {
                            "op": "relabel",
                            "nodeId": node.node_id,
                            "expectedNodeSha256": node.expected_node_sha256,
                            "label": "Authored correction label",
                        },
                        {
                            "op": "reference-rematch",
                            "nodeId": node.node_id,
                            "expectedNodeSha256": node.expected_node_sha256,
                            "referenceId": node.reference_id,
                            "expectedReferenceSha256": node.expected_reference_sha256,
                            "workId": target["workId"],
                            "workRevisionId": target["workRevisionId"],
                        },
                    ],
                },
                "rationale": "Authored correction rationale; no source text change.",
            }
            wrong = {
                **save,
                "commandId": new_uuid_v7(),
                "patch": {
                    **save["patch"],
                    "operations": [{**save["patch"]["operations"][1], "workRevisionId": new_uuid_v7()}],
                },
            }
            self.assertEqual(409, post("save", correction=wrong).status_code)
            saved = post("save", correction=save)
            self.assertEqual(200, saved.status_code, saved.text)
            draft = saved.json()
            self.assertEqual(draft, post("save", correction=save).json())
            proposed_response = post("page", revisionId=original.revision_id)
            self.assertEqual(200, proposed_response.status_code, proposed_response.text)
            proposed = CorrectionPage.model_validate(proposed_response.json())
            self.assertEqual(original.revision_id, proposed.current_revision_id)
            self.assertEqual("Authored correction label", proposed.preview_nodes[0].label)
            self.assertIsNone(proposed.nodes[0].label)
            impact = post("impact", draftRevisionId=draft["record"]["revisionId"])
            self.assertEqual(200, impact.status_code, impact.text)
            self.assertEqual("prospective-rechecked-at-acceptance", impact.json()["state"])
            accept = {
                "schemaVersion": "1.0",
                "commandId": new_uuid_v7(),
                "draftRevisionId": draft["record"]["revisionId"],
                "expectedCurrentRevisionId": original.revision_id,
                "confirmationSha256": draft["confirmationSha256"],
                "decision": "accept-correction",
            }
            accepted_response = post("accept", acceptance=accept)
            self.assertEqual(200, accepted_response.status_code, accepted_response.text)
            accepted = accepted_response.json()
            self.assertNotIn("structure", accepted)
            self.assertEqual(accepted, post("accept", acceptance=accept).json())
            corrected_response = post("page", revisionId=accepted["revisionId"])
            self.assertEqual(200, corrected_response.status_code, corrected_response.text)
            corrected = CorrectionPage.model_validate(corrected_response.json())
            self.assertEqual("Authored correction label", corrected.nodes[0].label)
            self.assertEqual(original.revision_id, corrected.machine_revision_id)
            self.assertEqual(target["workId"], corrected.accepted_reference_matches[0].work_id)
            self.assertEqual(target["workRevisionId"], corrected.accepted_reference_matches[0].work_revision_id)
            self.assertEqual("unverified", corrected.accepted_reference_matches[0].scholarly_verification)
            self.assertEqual(original.revision_id, post("page", revisionId=original.revision_id).json()["revisionId"])
            self.assertEqual(422, post("page", revisionId=accepted["revisionId"], actorId=new_uuid_v7()).status_code)
            address["sessionId"] = "0" * 32
            self.assertEqual(409, post("page", revisionId=accepted["revisionId"]).status_code)
            address["sessionId"] = session
            for right in ("inspect", "derive"):
                permissions(right)
                denied = post("page", revisionId=accepted["revisionId"])
                self.assertEqual(409, denied.status_code)
                self.assertNotIn(RAW, denied.text)
                self.assertNotIn("Authored correction", denied.text)
                permissions()
            factory = revisions.repository_factory

            def changed(*args, **kwargs):
                actor = kwargs["actor"]
                kwargs["actor"] = lambda: replace(actor(), actor_type="worker")
                return factory(*args, **kwargs)

            with patch.object(revisions, "repository_factory", changed):
                self.assertEqual(409, post("page", revisionId=accepted["revisionId"]).status_code)
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            self.assertEqual(409, post("page", revisionId=accepted["revisionId"]).status_code)
            session = runtime.context(str(project), selected["projectId"])
            address["sessionId"] = session
            reopened_response = post("page", revisionId=accepted["revisionId"])
            self.assertEqual(200, reopened_response.status_code, reopened_response.text)
            reopened = CorrectionPage.model_validate(reopened_response.json())
            self.assertEqual(corrected.accepted_labels, reopened.accepted_labels)
            self.assertEqual(corrected.accepted_reference_matches, reopened.accepted_reference_matches)
            original_dump = CorrectionPage.model_dump

            def stop(value, *args, **kwargs):
                result = original_dump(value, *args, **kwargs)
                if kwargs.get("mode") == "json":
                    revisions.imports.signal_stop(str(project))
                return result

            with patch.object(CorrectionPage, "model_dump", stop):
                stopped = post("page", revisionId=accepted["revisionId"])
                self.assertEqual(409, stopped.status_code)
                self.assertNotIn(RAW, stopped.text)
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
        self.assertNotIn(RAW.encode(), (project / "state/project.sqlite3").read_bytes())
