"""Private ASGI/native-session rights path with actual SQLCipher/encrypted fixtures."""

import json
import threading
import unittest
from contextlib import closing
from unittest.mock import patch

from research_observatory_core.document_viewer_repository import LocalDocumentViewerRepository
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.storage import open_canonical_database

from tests.service import test_document_viewer_api as viewer_api


class ViewerActionsApiTests(unittest.TestCase):
    def setUp(self):
        self.api = viewer_api.DocumentViewerApiTests(methodName="runTest")
        self.api.setUp()
        self.addCleanup(self.api.doCleanups)
        self.command, self.anchor = self.api.anchor_command()
        self.command["action"] = "copy-quotation"

    def post(self, endpoint, command=None, **kwargs):
        selected = dict(self.command if command is None else command)
        selected.setdefault("requestId", new_uuid_v7())
        return self.api.client.post(self.api.path + endpoint, json=selected, **kwargs)

    def test_cancel_waits_for_physical_action_closure_and_early_cancel_is_not_absence(self):
        command = self.grant()
        command["requestId"] = new_uuid_v7()
        cancel = {key: command[key] for key in ("root", "projectId", "sessionId", "requestId")}
        entered, release = threading.Event(), threading.Event()
        original = LocalDocumentViewerRepository.action_payload
        responses = []

        def held(repository, *args, **kwargs):
            value = original(repository, *args, **kwargs)
            entered.set()
            self.assertTrue(release.wait(8))
            return value

        with patch.object(LocalDocumentViewerRepository, "action_payload", held):
            worker = threading.Thread(target=lambda: responses.append(self.post("/action-payload", command)))
            worker.start()
            try:
                self.assertTrue(entered.wait(8))
                self.assertFalse(self.post("/cancel", cancel).json()["drained"])
                # The physically held owner also retains the single action slot.
                self.assertEqual(413, self.post("/action-policy").status_code)
            finally:
                release.set()
                worker.join(8)
            self.assertFalse(worker.is_alive())
        self.assertEqual(409, responses[0].status_code)
        self.assertNotIn("Synthetic", responses[0].text)
        self.assertTrue(self.post("/cancel", cancel).json()["drained"])
        command["requestId"] = new_uuid_v7()
        cancel["requestId"] = command["requestId"]
        self.assertFalse(self.post("/cancel", cancel).json()["drained"])
        self.assertEqual(409, self.post("/action-payload", command).status_code)
        self.assertTrue(self.post("/cancel", cancel).json()["drained"])

    def grant(self):
        decision = self.post("/action-policy")
        self.assertEqual(200, decision.status_code, decision.text)
        self.assertEqual("review-required", decision.json()["state"])
        for requirement in decision.json()["requirements"]:
            self.assertEqual(
                {"action", "purpose", "destinationKind", "provider", "region", "shareGroup"}, set(requirement["use"])
            )
            self.assertTrue(all(requirement["use"][key] is None for key in ("provider", "region", "shareGroup")))
        review = {key: value for key, value in self.command.items() if key != "anchorId"}
        review.update(
            commandId=new_uuid_v7(), confirmed=True, expectedPolicyRevisionId=decision.json()["policyRevisionId"]
        )
        result = self.post("/rights-review", review)
        self.assertEqual(200, result.status_code, result.text)
        return dict(self.command, expectedPolicyRevisionId=result.json()["policyRevisionId"])

    def test_distinct_explicit_rights_review_then_exact_private_quotation(self):
        request = self.grant()
        reply = self.post("/action-payload", request)
        self.assertEqual(200, reply.status_code, reply.text)
        body = json.loads(reply.json()["contentUtf8"])
        self.assertEqual("Synthetic", body["text"])
        self.assertEqual(self.anchor.anchor_id, body["anchorId"])
        self.assertEqual(self.anchor.target.source.document_revision_id, body["source"]["documentRevisionId"])
        self.assertNotIn("context", body)
        self.assertEqual("unverified", body["scholarlyVerification"])

    def test_renderer_origin_and_supplied_authority_never_reach_private_actions(self):
        for endpoint in ("/action-policy", "/rights-review", "/action-payload"):
            self.assertEqual(403, self.post(endpoint, headers={"Origin": "http://tauri.localhost"}).status_code)
            self.assertNotIn(self.api.path + endpoint, self.api.client.get("/openapi.json").json()["paths"])
        for field in ("text", "actorId", "rights", "destination", "rootOverride", "applicationPath"):
            with self.subTest(field=field):
                self.assertEqual(
                    422, self.post("/action-policy", dict(self.command, **{field: "untrusted"})).status_code
                )

    def test_policy_principal_and_session_changes_prevent_plaintext_delivery(self):
        request = self.grant()
        for replacements in ({"expectedPolicyRevisionId": new_uuid_v7()}, {"expectedAuthoritySha256": "f" * 64}):
            reply = self.post("/action-payload", dict(request, **replacements))
            self.assertEqual(409, reply.status_code)
            self.assertNotIn("Synthetic", reply.text)
        original = LocalDocumentViewerRepository.action_payload

        def revoke(repository, *args, **kwargs):
            value = original(repository, *args, **kwargs)
            self.api.f.f.permit(derive="denied")
            return value

        with patch.object(LocalDocumentViewerRepository, "action_payload", revoke):
            reply = self.post("/action-payload", request)
        self.assertEqual(409, reply.status_code)
        self.assertNotIn("Synthetic", reply.text)
        self.api.imports.detach(self.command["root"])
        self.assertEqual(409, self.post("/action-payload", request).status_code)

    def test_no_selection_is_audited_without_quote_or_context_and_consent_is_strict(self):
        request = self.grant()
        command = dict(self.command, anchorId=None)
        state = self.post("/action-policy", command)
        self.assertEqual(200, state.status_code)
        self.assertEqual("viewer-selection-required", state.json()["reasonCode"])
        review = {key: value for key, value in self.command.items() if key != "anchorId"}
        review.update(
            commandId=new_uuid_v7(), confirmed=False, expectedPolicyRevisionId=request["expectedPolicyRevisionId"]
        )
        self.assertEqual(409, self.post("/rights-review", review).status_code)
        self.assertEqual(422, self.post("/rights-review", dict(review, confirmed="true")).status_code)
        with closing(
            open_canonical_database(self.api.f.f.fixture.corpus.database, expected_project_id=self.command["projectId"])
        ) as db:
            rows = [tuple(row) for row in db.execute("SELECT * FROM rights_use_decisions")]
        self.assertNotIn("Synthetic", json.dumps(rows))
        self.assertIn("viewer-selection-required", json.dumps(rows))

    def test_alternate_direct_transfer_is_explicitly_denied_and_audited_even_with_permission(self):
        request = self.grant()
        command = dict(self.command, anchorId=None, directTransfer=True)
        response = self.post("/action-policy", command)
        self.assertEqual(200, response.status_code)
        self.assertEqual("denied", response.json()["state"])
        self.assertFalse(response.json()["canReview"])
        self.assertEqual("viewer-direct-transfer-disabled", response.json()["reasonCode"])
        self.assertNotIn("Synthetic", response.text)
        self.assertEqual(422, self.post("/action-payload", dict(request, directTransfer=True)).status_code)
        with closing(
            open_canonical_database(self.api.f.f.fixture.corpus.database, expected_project_id=self.command["projectId"])
        ) as db:
            rows = [tuple(row) for row in db.execute("SELECT * FROM rights_use_decisions")]
        self.assertIn("viewer-direct-transfer-disabled", json.dumps(rows))
        self.assertNotIn("Synthetic", json.dumps(rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
