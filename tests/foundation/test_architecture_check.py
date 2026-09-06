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

    def test_model_catalog_adapter_is_owned_and_cannot_leak_into_business_or_ports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model_registry_repository.py").write_text(
                "import sqlite3\nfrom .storage import open_canonical_database\n"
                "def save(connection):\n    connection.execute('SELECT 1')\n",
                encoding="utf-8",
            )
            (root / "main.py").write_text(
                "from .model_registry_repository import sqlite_model_catalog_repository\n",
                encoding="utf-8",
            )
            self.assertEqual([], core_data_boundary_errors(root))
        imports = (
            "from .model_registry_repository import SqliteModelCatalogRepository\n",
            "import research_observatory_core.model_registry_repository as adapter\n",
            "from research_observatory_core import model_registry_repository as adapter\n",
            "from . import model_registry_repository\n",
        )
        for location in ("business.py", "ports/model_registry.py"):
            for source in imports:
                with self.subTest(location=location, source=source), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    path = root / location
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(source, encoding="utf-8")
                    self.assertTrue(any("concrete" in error for error in core_data_boundary_errors(root)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rogue = root / "business/model_registry_repository.py"
            rogue.parent.mkdir()
            rogue.write_text("import sqlite3\n", encoding="utf-8")
            self.assertTrue(any("outside adapter" in error for error in core_data_boundary_errors(root)))

    def test_typed_async_port_execution_is_not_a_database_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ports").mkdir()
            (root / "ports/compute.py").write_text(
                "from typing import Protocol\nclass Compute(Protocol):\n    async def execute(self, task): ...\n",
                encoding="utf-8",
            )
            source = "from .ports.compute import Compute as Port\nasync def run(adapter: Port):\n"
            cases = (
                ("    return await adapter.execute(task)\n", False),
                ("    return adapter.execute(task)\n", True),
                ("    adapter = connection\n    return await adapter.execute(task)\n", True),
                ("    return await connection.execute(task)\n", True),
                ("    return await adapter.executemany(task)\n", True),
                ("    from example import connection as adapter\n    return await adapter.execute(task)\n", True),
                ("    import example as adapter\n    return await adapter.execute(task)\n", True),
                (
                    "    try:\n        operation()\n    except Exception as adapter:\n"
                    "        return await adapter.execute(task)\n",
                    True,
                ),
                (
                    "    match task:\n        case {'connection': adapter}:\n"
                    "            return await adapter.execute(task)\n",
                    True,
                ),
                ("    class adapter:\n        pass\n    return await adapter.execute(task)\n", True),
                ("    def adapter():\n        pass\n    return await adapter.execute(task)\n", True),
            )
            for body, denied in cases:
                with self.subTest(body=body):
                    (root / "business.py").write_text(source + body, encoding="utf-8")
                    self.assertEqual(denied, bool(core_data_boundary_errors(root)))
            (root / "business.py").write_text(
                "async def run(adapter):\n    return await adapter.execute(task)\n",
                encoding="utf-8",
            )
            self.assertTrue(core_data_boundary_errors(root))
            (root / "ports/compute.py").write_text(
                "Protocol = object\nclass Compute(Protocol):\n    async def execute(self, statement): ...\n",
                encoding="utf-8",
            )
            (root / "business.py").write_text(source + "    return await adapter.execute(task)\n", encoding="utf-8")
            self.assertTrue(core_data_boundary_errors(root))
            (root / "ports/compute.py").write_text(
                "from typing import Protocol\nclass Compute(Protocol):\n    async def execute(self, task): ...\n",
                encoding="utf-8",
            )
            for consumer in (
                "from .ports.compute import Compute as Port\ndef outer(Port):\n"
                "    async def run(adapter: Port):\n        return await adapter.execute(task)\n",
                "from .ports.compute import Compute as Port\nfrom typing import Any as Port\n"
                "async def run(adapter: Port):\n    return await adapter.execute(task)\n",
                "from .ports.compute import Compute as Port, Other as Port\n"
                "async def run(adapter: Port):\n    return await adapter.execute(task)\n",
                "from .ports.compute import Compute as Port\nfrom example import *\n"
                "async def run(adapter: Port):\n    return await adapter.execute(task)\n",
            ):
                with self.subTest(consumer=consumer):
                    (root / "business.py").write_text(consumer, encoding="utf-8")
                    self.assertTrue(core_data_boundary_errors(root))
            (root / "business.py").write_text(source + "    return await adapter.execute(task)\n", encoding="utf-8")
            for replacement in (
                "from typing import Protocol\nfrom example import *\n"
                "class Compute(Protocol):\n    async def execute(self, task): ...\n",
                "from typing import Protocol, Any\n"
                "class Compute(Protocol):\n    async def execute(self, task): ...\nCompute = Any\n",
            ):
                with self.subTest(replacement=replacement):
                    (root / "ports/compute.py").write_text(replacement, encoding="utf-8")
                    self.assertTrue(core_data_boundary_errors(root))


if __name__ == "__main__":
    unittest.main()
