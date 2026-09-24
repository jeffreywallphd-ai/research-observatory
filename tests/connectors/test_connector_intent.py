"""Existing durable Intent path: declaration is never exact-query consent."""

import unittest

from tests.service import test_research_intents as fixtures


class ConnectorIntentTests(unittest.TestCase):
    def setUp(self):
        fixtures.ResearchIntentServiceTests.setUp(self)

    def tearDown(self):
        fixtures.ResearchIntentServiceTests.tearDown(self)

    def accept(self, draft):
        command = fixtures.IntentAcceptRequest(
            root=self.root,
            expected_revision=draft.revision,
            expected_revision_content_hash=draft.revision_content_hash,
            confirmed=True,
            decision_rationale="Accept only these synthetic metadata destinations.",
        )
        return self.service.accept(command, trace_id=fixtures.TRACE, idempotency_key=str(draft.revision + 1) * 32)

    def test_accepted_destination_requires_separate_confirmation_and_defaults_deny(self):
        initial = self.service.save_draft(
            fixtures.draft_request(self.root), trace_id=fixtures.TRACE, idempotency_key="1" * 32
        )
        accepted = self.accept(initial)
        command = fixtures.draft_request(
            self.root,
            expected_revision=accepted.revision,
            egressPolicy={"mode": "approved-content", "approvedDestinationIds": ["openalex"]},
        )
        preview = self.service.preview(command.to_impact_request())
        self.assertIn("egress-policy", preview.change_categories)
        self.assertTrue(preview.acknowledgement_required)
        with self.assertRaises(fixtures.IntentProblem):
            self.service.save_draft(command, trace_id=fixtures.TRACE, idempotency_key="3" * 32)
        draft = self.service.save_draft(
            command.model_copy(update={"impact_acknowledgement": preview.acknowledgement_token}),
            trace_id=fixtures.TRACE,
            idempotency_key="3" * 32,
        )
        for destination in (None, "openalex", "crossref"):
            denied = self.service.evaluate_policy(
                fixtures.IntentPolicyRequest(
                    root=self.root, action="external-egress", subject_type="human", destination_id=destination
                ),
                trace_id=fixtures.TRACE,
            )
            self.assertEqual("deny", denied.outcome)  # an unaccepted draft grants nothing
        approved = self.accept(draft)
        for destination, outcome in ((None, "deny"), ("crossref", "deny"), ("openalex", "require-confirmation")):
            decision = self.service.evaluate_policy(
                fixtures.IntentPolicyRequest(
                    root=self.root, action="external-egress", subject_type="human", destination_id=destination
                ),
                trace_id=fixtures.TRACE,
            )
            self.assertEqual(outcome, decision.outcome)
            self.assertEqual(approved.revision_id, decision.governing_intent.revision_id)
        # Old clients omitting the additive field preserve, not erase, current declaration.
        preserved = self.service.save_draft(
            fixtures.draft_request(self.root, expected_revision=approved.revision),
            trace_id=fixtures.TRACE,
            idempotency_key="5" * 32,
        )
        self.assertEqual(approved.egress_policy, preserved.egress_policy)

    def test_destination_substitution_invalidates_impact_acknowledgement(self):
        initial = self.service.save_draft(
            fixtures.draft_request(self.root), trace_id=fixtures.TRACE, idempotency_key="1" * 32
        )
        command = fixtures.draft_request(
            self.root,
            expected_revision=initial.revision,
            egressPolicy={"mode": "approved-content", "approvedDestinationIds": ["openalex"]},
        )
        preview = self.service.preview(command.to_impact_request())
        changed = fixtures.draft_request(
            self.root,
            expected_revision=initial.revision,
            egressPolicy={"mode": "approved-content", "approvedDestinationIds": ["crossref"]},
            impactAcknowledgement=preview.acknowledgement_token,
        )
        with self.assertRaises(fixtures.IntentProblem):
            self.service.save_draft(changed, trace_id=fixtures.TRACE, idempotency_key="2" * 32)


if __name__ == "__main__":
    unittest.main()
