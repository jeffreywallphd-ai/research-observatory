from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from architecture_check import load_json, validate_contract  # noqa: E402


class ArchitectureContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_json(REPO / "architecture-boundaries.json")

    def test_repository_architecture_contract_is_complete(self) -> None:
        self.assertEqual([], validate_contract(REPO, self.contract))

    def test_missing_governed_module_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["modules"] = [module for module in contract["modules"] if module["path"] != "workers"]

        errors = validate_contract(REPO, contract)

        self.assertTrue(any("repository modules lack architecture rules: ['workers']" in error for error in errors))

    def test_prohibited_reverse_dependency_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        service = next(module for module in contract["modules"] if module["path"] == "services/core-api")
        service["allowedDependencies"].append("apps/desktop")

        errors = validate_contract(REPO, contract)

        self.assertTrue(
            any(
                "('services/core-api', 'apps/desktop')" in error and "both allowed and prohibited" in error
                for error in errors
            )
        )

    def test_deferred_cloud_profile_cannot_be_marked_active_early(self) -> None:
        contract = copy.deepcopy(self.contract)
        cloud = next(profile for profile in contract["deploymentProfiles"] if profile["id"] == "cloud")
        cloud["status"] = "active"

        errors = validate_contract(REPO, contract)

        self.assertIn("cloud profile phase/status does not match the architecture baseline", errors)


if __name__ == "__main__":
    unittest.main()
