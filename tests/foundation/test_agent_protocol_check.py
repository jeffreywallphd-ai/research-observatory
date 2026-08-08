from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from agent_protocol_check import load_protocol, task_brief, validate_protocol  # noqa: E402


class AgentProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.protocol = load_protocol(REPO)

    def test_repository_agent_protocol_is_complete(self) -> None:
        self.assertEqual([], validate_protocol(REPO, self.protocol))

    def test_partial_slice_approval_cannot_start_campaign(self) -> None:
        protocol = copy.deepcopy(self.protocol)
        protocol["campaign"]["partialApprovalStartsCampaign"] = True

        errors = validate_protocol(REPO, protocol)

        self.assertIn("campaign.partialApprovalStartsCampaign must be False", errors)

    def test_missing_continuous_campaign_instruction_is_rejected(self) -> None:
        agents = (REPO / "AGENTS.md").read_text(encoding="utf-8").replace(
            "### One approval and one durable campaign", "### Campaign"
        )

        errors = validate_protocol(REPO, self.protocol, {"AGENTS.md": agents})

        self.assertTrue(any("One approval and one durable campaign" in error for error in errors))

    def test_unfamiliar_agent_can_state_scope_checks_and_completion_for_ready_task(self) -> None:
        task = {
            "id": "CAP-00.S99.T01",
            "status": "READY",
            "objective": "Prove the task briefing contract.",
            "deliverables": ["A deterministic brief."],
            "acceptance_criteria": ["Scope, checks, and completion are explicit."],
            "dependencies": ["CAP-00.S98.T01"],
            "deployment_profiles": ["LOC"],
            "platform_targets": ["platform-neutral"],
            "verification_profiles": ["foundation"],
            "verification_commands": ["python tools/verify.py --profile foundation"],
        }

        brief = task_brief(task, self.protocol)

        self.assertEqual("Prove the task briefing contract.", brief["permittedScope"]["objective"])
        self.assertEqual(["foundation"], brief["requiredChecks"]["profiles"])
        self.assertIn("required-independent-review", brief["completionProtocol"])
        self.assertIn("taskctl.py", brief["claimCommandTemplate"])

    def test_non_ready_task_has_no_claim_brief(self) -> None:
        with self.assertRaisesRegex(ValueError, "is not READY"):
            task_brief({"id": "CAP-00.S99.T02", "status": "BLOCKED"}, self.protocol)


if __name__ == "__main__":
    unittest.main()
