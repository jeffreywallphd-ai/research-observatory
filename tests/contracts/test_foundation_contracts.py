from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from ci_check import validate_ci  # noqa: E402
from runtime_check import declaration_errors, load_contract  # noqa: E402


class FoundationPortableContractTests(unittest.TestCase):
    def test_runtime_declarations_are_portable_and_locked(self) -> None:
        contract = load_contract(REPO)

        self.assertEqual([], declaration_errors(REPO, contract))

    def test_ci_contract_is_locally_enforceable(self) -> None:
        self.assertEqual([], validate_ci(REPO))

    def test_project_manifest_and_layout_are_strict_portable_contracts(self) -> None:
        contract_root = REPO / "packages" / "contracts" / "project"
        manifest_schema = json.loads((contract_root / "project-manifest.schema.json").read_text(encoding="utf-8"))
        layout_schema = json.loads((contract_root / "project-layout.schema.json").read_text(encoding="utf-8"))
        layout = json.loads((contract_root / "project-layout.v1.json").read_text(encoding="utf-8"))
        manifest = json.loads(
            (contract_root / "fixtures" / "valid-project-manifest.v1.json").read_text(encoding="utf-8")
        )
        invalid_manifest = json.loads(
            (contract_root / "fixtures" / "invalid-project-manifest-extra-path.json").read_text(encoding="utf-8")
        )

        Draft202012Validator.check_schema(manifest_schema)
        Draft202012Validator.check_schema(layout_schema)
        manifest_validator = Draft202012Validator(manifest_schema, format_checker=FormatChecker())
        layout_validator = Draft202012Validator(layout_schema)
        self.assertEqual([], list(manifest_validator.iter_errors(manifest)))
        self.assertEqual([], list(layout_validator.iter_errors(layout)))
        self.assertTrue(list(manifest_validator.iter_errors(invalid_manifest)))

        path_bearing = copy.deepcopy(manifest)
        path_bearing["absolutePath"] = "C:\\private\\study"
        self.assertTrue(list(manifest_validator.iter_errors(path_bearing)))

        redirected_layout = copy.deepcopy(layout)
        redirected_layout["entries"][0]["relativePath"] = "../outside/project.sqlite3"
        self.assertTrue(list(layout_validator.iter_errors(redirected_layout)))


if __name__ == "__main__":
    unittest.main()
