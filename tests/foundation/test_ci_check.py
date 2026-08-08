from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from ci_check import validate_ci  # noqa: E402


class ContinuousIntegrationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    def test_repository_workflow_is_pinned_least_privilege_and_retains_reports(self) -> None:
        self.assertEqual([], validate_ci(REPO))

    def test_rejects_mutable_action_reference(self) -> None:
        mutated = self.workflow.replace(
            "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
            "actions/checkout@v6",
            1,
        )

        errors = validate_ci(REPO, mutated)

        self.assertTrue(any("not pinned to the approved commit SHA" in error for error in errors))

    def test_rejects_secret_consumption(self) -> None:
        mutated = self.workflow.replace('UV_NO_PROGRESS: "1"', "TOKEN: ${{ secrets.PRODUCTION_TOKEN }}", 1)

        errors = validate_ci(REPO, mutated)

        self.assertIn("production or repository secrets are forbidden", errors)

    def test_rejects_bracket_style_secret_consumption(self) -> None:
        mutated = self.workflow.replace('UV_NO_PROGRESS: "1"', "TOKEN: ${{ secrets['PRODUCTION_TOKEN'] }}", 1)

        errors = validate_ci(REPO, mutated)

        self.assertIn("production or repository secrets are forbidden", errors)

    def test_rejects_shortened_artifact_retention(self) -> None:
        mutated = self.workflow.replace("retention-days: 14", "retention-days: 1", 1)

        errors = validate_ci(REPO, mutated)

        self.assertTrue(any("artifact retention" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
