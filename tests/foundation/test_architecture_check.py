from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from architecture_check import core_data_boundary_errors, load_json, validate_contract  # noqa: E402


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

    def test_package_style_storage_and_repository_authority_imports_are_rejected(self) -> None:
        attacks = {
            "storage-module.py": (
                (
                    "import research_observatory_core.storage as store\n"
                    "def attack(path):\n"
                    "    return store.open_canonical_database(path)\n"
                ),
                "storage connection authority",
            ),
            "storage-attribute.py": (
                (
                    "from research_observatory_core import storage\n"
                    "def attack(path):\n"
                    "    return storage.open_canonical_database(path)\n"
                ),
                "storage connection authority",
            ),
            "repository-module.py": (
                (
                    "import research_observatory_core.repositories as adapter\n"
                    "def attack(path, project_id):\n"
                    "    return adapter.create_sqlite_unit_of_work_factory(path, project_id)\n"
                ),
                "concrete repository adapter",
            ),
            "repository-attribute.py": (
                (
                    "from research_observatory_core import repositories\n"
                    "def attack(path, project_id):\n"
                    "    return repositories.create_sqlite_unit_of_work_factory(path, project_id)\n"
                ),
                "concrete repository adapter",
            ),
            "object-store-module.py": (
                (
                    "import research_observatory_core.object_store as adapter\n"
                    "def attack(root, project_id):\n"
                    "    return adapter.create_local_object_store(root, project_id)\n"
                ),
                "concrete object-store adapter",
            ),
            "object-store-attribute.py": (
                (
                    "from research_observatory_core import object_store\n"
                    "def attack(root, project_id):\n"
                    "    return object_store.create_local_object_store(root, project_id)\n"
                ),
                "concrete object-store adapter",
            ),
        }
        for name, (source, expected) in attacks.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / name).write_text(source, encoding="utf-8")
                errors = core_data_boundary_errors(root)
                self.assertTrue(any(expected in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
