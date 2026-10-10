"""Exact current Reader rights over real encrypted storage; authored synthetic IR."""

import json
import unittest
from contextlib import closing
from unittest.mock import patch

from research_observatory_core.document_revisions import DocumentRevisionProblem
from research_observatory_core.document_viewer_repository import LocalDocumentViewerRepository
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.rights_policy import RightsPermission, RightsPolicyRevision, RightsUse
from research_observatory_core.storage import open_canonical_database

from tests.documents import test_viewer_anchor_context as contexts


class ViewerActionTests(unittest.TestCase):
    def setUp(self):
        self.f = contexts.ViewerAnchorContextTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.selector, self.anchor = self.f.selector, self.f.anchor
        self.parse = self.f.f.f.f
        self.rights, self.actor = self.parse.fixture.rights, self.parse.actor
        self.subject = self.parse.candidate.rights_subject

    def viewer(self):
        return self.f.viewer()

    def policy(self):
        return self.rights.current(self.subject, actor=self.actor)

    def review(self, action="copy-quotation", *, command=None, predecessor=None):
        return self.viewer().review_action_permissions(
            self.selector,
            action=action,
            expected_policy_revision_id=predecessor or self.policy().revision_id,
            command_id=command or new_uuid_v7(),
            confirmed=True,
        )

    def payload(self, action="copy-quotation", anchor=None):
        return self.viewer().action_payload(
            self.selector,
            action=action,
            anchor_id=None if action == "open-external-original" else anchor or self.anchor.anchor_id,
            expected_policy_revision_id=self.policy().revision_id,
        )

    def append(self, use, value="permitted", *, expires_at=None, recorded_at="2025-01-01T00:00:00.000Z"):
        old = self.policy()
        permission = RightsPermission(
            assertion_id=new_uuid_v7(),
            subject=self.subject,
            use=use,
            value=value,
            basis="researcher-confirmed",
            confidence="confirmed",
            asserted_by_actor_id=self.actor.actor_id,
            evidence_revision_ids=(self.subject.source_assertion_revision_id,),
            license_observation_revision_id=None,
            entitlement_revision_id=None,
            recorded_at=recorded_at,
            expires_at=expires_at,
        )
        policy = RightsPolicyRevision(
            revision_id=new_uuid_v7(),
            predecessor_revision_id=old.revision_id,
            subject=self.subject,
            permissions=(*old.permissions, permission),
        )
        return self.rights.publish(policy, command_id=new_uuid_v7(), command_sha256="7" * 64, actor=self.actor)

    def test_missing_quotation_permission_is_audited_and_never_materializes_text(self):
        with patch.object(LocalDocumentViewerRepository, "resolve_anchor", side_effect=AssertionError("no quote read")):
            decision = self.viewer().action_policy(
                self.selector, action="copy-quotation", anchor_id=self.anchor.anchor_id
            )
            self.assertEqual("review-required", decision.state)
            self.assertTrue(decision.can_review)
            with self.assertRaises(DocumentRevisionProblem):
                self.payload()
        with closing(
            open_canonical_database(self.parse.fixture.corpus.database, expected_project_id=self.subject.project_id)
        ) as db:
            rows = [tuple(row) for row in db.execute("SELECT * FROM rights_use_decisions")]
        self.assertGreater(len(rows), 0)
        self.assertNotIn(self.anchor.target.quote.exact, json.dumps(rows))

    def test_explicit_review_preserves_assertions_and_restart_exports_only_exact_quote_with_ids(self):
        old = self.policy()
        command = new_uuid_v7()
        accepted = self.review(command=command)
        self.assertEqual(old.permissions, self.policy().permissions[: len(old.permissions)])
        self.assertEqual(accepted, self.review(command=command, predecessor=old.revision_id))
        payload = self.payload()
        document = json.loads(payload.content_utf8)
        self.assertEqual(self.anchor.target.quote.exact, document["text"])
        self.assertNotIn("context", document)
        self.assertNotIn("prefix", document)
        self.assertEqual(self.anchor.anchor_id, document["anchorId"])
        self.assertEqual(self.anchor.anchor_revision_id, document["anchorRevisionId"])
        self.assertEqual(self.anchor.target.source.model_dump(mode="json", by_alias=True), document["source"])
        self.assertEqual(self.selector.normalized_revision_id, document["normalizedRevisionId"])
        self.assertEqual("unverified", document["scholarlyVerification"])
        self.assertEqual(self.policy().revision_id, document["policyRevisionId"])
        self.assertEqual(payload, self.payload())

    def test_permission_is_action_specific_and_does_not_open_original_or_print(self):
        self.review()
        self.assertEqual(
            "ready",
            self.viewer().action_policy(self.selector, action="copy-quotation", anchor_id=self.anchor.anchor_id).state,
        )
        for action in ("print-quotation", "export-quotation", "export-annotation", "open-external-original"):
            with self.subTest(action=action), self.assertRaises(DocumentRevisionProblem):
                self.payload(action)

    def test_annotation_and_original_handoffs_preserve_identity_without_quotation_or_context(self):
        for action in ("export-annotation", "open-external-original"):
            self.review(action)
            output = json.loads(self.payload(action).content_utf8)
            self.assertEqual(action, output["action"])
            self.assertEqual(self.anchor.target.source.model_dump(mode="json", by_alias=True), output["source"])
            self.assertEqual("unverified", output["scholarlyVerification"])
            self.assertFalse({"text", "quote", "context", "prefix", "suffix"}.intersection(output))
            if action == "export-annotation":
                self.assertEqual(self.anchor.anchor_id, output["anchorId"])
                self.assertEqual(self.anchor.anchor_revision_id, output["anchorRevisionId"])
            else:
                self.assertFalse({"anchorId", "anchorRevisionId", "nodeId"}.intersection(output))

    def test_unrelated_expired_assertion_keeps_its_original_id_and_times(self):
        expired = self.append(
            RightsUse(
                action="share", purpose="unrelated-history", destination_kind="collaboration", share_group="reviewers"
            ),
            expires_at="2025-01-02T00:00:00.000Z",
        )
        self.review()
        self.assertEqual(expired.permissions, self.policy().permissions[: len(expired.permissions)])
        self.assertEqual(self.anchor.target.quote.exact, json.loads(self.payload().content_utf8)["text"])

    def test_explicit_denial_and_expiry_cannot_be_overridden_by_the_review_button(self):
        for value, expiry in (("denied", None), ("permitted", "2025-01-02T00:00:00.000Z")):
            with self.subTest(value=value):
                self.append(
                    RightsUse(action="export", purpose="viewer-copy-quotation", destination_kind="local-export"),
                    value,
                    expires_at=expiry,
                )
                old = self.policy()
                state = self.viewer().action_policy(
                    self.selector, action="copy-quotation", anchor_id=self.anchor.anchor_id
                )
                self.assertEqual("denied", state.state)
                self.assertFalse(state.can_review)
                with self.assertRaises(DocumentRevisionProblem):
                    self.review()
                self.assertEqual(old, self.policy())

    def test_unknown_selected_assertion_is_replaced_but_stale_predecessor_is_refused(self):
        old = self.append(
            RightsUse(action="quote", purpose="viewer-quotation", destination_kind="local-project"), "unknown"
        )
        self.review()
        self.assertNotIn(old.permissions[-1], self.policy().permissions)
        current = self.policy()
        with self.assertRaises(DocumentRevisionProblem):
            self.review("print-quotation", predecessor=old.revision_id)
        self.assertEqual(current, self.policy())
        self.payload()

    def test_no_anchor_and_substituted_selection_deliver_no_plaintext(self):
        self.review()
        state = self.viewer().action_policy(self.selector, action="copy-quotation", anchor_id=None)
        self.assertEqual("unavailable", state.state)
        for field in ("attachment_id", "document_revision_id", "normalized_revision_id"):
            with self.subTest(field=field), self.assertRaises(DocumentRevisionProblem):
                self.viewer().action_payload(
                    self.selector.model_copy(update={field: new_uuid_v7()}),
                    action="copy-quotation",
                    anchor_id=self.anchor.anchor_id,
                    expected_policy_revision_id=self.policy().revision_id,
                )
        with self.assertRaises(DocumentRevisionProblem):
            self.payload(anchor=new_uuid_v7())

    def test_policy_change_after_materialization_prevents_successful_old_delivery(self):
        self.review()
        original = LocalDocumentViewerRepository.resolve_anchor
        owner = self

        def revoke(viewer, *args, **kwargs):
            result = original(viewer, *args, **kwargs)
            owner.append(
                RightsUse(action="export", purpose="viewer-copy-quotation", destination_kind="local-export"), "denied"
            )
            return result

        with (
            patch.object(LocalDocumentViewerRepository, "resolve_anchor", revoke),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.payload()


if __name__ == "__main__":
    unittest.main(verbosity=2)
