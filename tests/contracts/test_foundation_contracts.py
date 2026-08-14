from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from ci_check import validate_ci  # noqa: E402
from runtime_check import declaration_errors, load_contract  # noqa: E402


def pointer_value(document: dict[str, Any], pointer: str) -> object:
    value: object = document
    for segment in pointer.removeprefix("/").split("/"):
        if not isinstance(value, dict):
            raise ValueError("semantic rule pointer does not address an object field")
        value = value[segment]
    return value


def release_version(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ValueError("semantic version operand must be a string")
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError("semantic version operand must be a release version")
    major, minor, patch = parts
    return int(major), int(minor), int(patch)


def manifest_semantic_errors(manifest: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for raw_rule in rules["rules"]:
        rule = cast(dict[str, str], raw_rule)
        left = pointer_value(manifest, rule["leftPointer"])
        right = pointer_value(manifest, rule["rightPointer"])
        operator = rule["operator"]
        if operator == "semver-less-than":
            valid = release_version(left) < release_version(right)
        elif operator == "instant-not-after":
            valid = datetime.fromisoformat(str(left).replace("Z", "+00:00")) <= datetime.fromisoformat(
                str(right).replace("Z", "+00:00")
            )
        else:
            raise ValueError(f"unsupported semantic rule operator: {operator}")
        if not valid:
            errors.append(rule["ruleId"])
    return errors


class FoundationPortableContractTests(unittest.TestCase):
    def test_runtime_declarations_are_portable_and_locked(self) -> None:
        contract = load_contract(REPO)

        self.assertEqual([], declaration_errors(REPO, contract))

    def test_ci_contract_is_locally_enforceable(self) -> None:
        self.assertEqual([], validate_ci(REPO))

    def test_project_manifest_and_layout_are_strict_portable_contracts(self) -> None:
        contract_root = REPO / "packages" / "contracts" / "project"
        manifest_schema = json.loads((contract_root / "project-manifest.schema.json").read_text(encoding="utf-8"))
        semantic_schema = json.loads(
            (contract_root / "project-manifest-semantic-rules.schema.json").read_text(encoding="utf-8")
        )
        semantic_rules = json.loads(
            (contract_root / "project-manifest.semantic-rules.json").read_text(encoding="utf-8")
        )
        layout_schema = json.loads((contract_root / "project-layout.schema.json").read_text(encoding="utf-8"))
        layout = json.loads((contract_root / "project-layout.v1.json").read_text(encoding="utf-8"))
        manifest = json.loads(
            (contract_root / "fixtures" / "valid-project-manifest.v1.json").read_text(encoding="utf-8")
        )
        invalid_manifest = json.loads(
            (contract_root / "fixtures" / "invalid-project-manifest-extra-path.json").read_text(encoding="utf-8")
        )

        Draft202012Validator.check_schema(manifest_schema)
        Draft202012Validator.check_schema(semantic_schema)
        Draft202012Validator.check_schema(layout_schema)
        manifest_validator = Draft202012Validator(manifest_schema, format_checker=FormatChecker())
        layout_validator = Draft202012Validator(layout_schema)
        semantic_validator = Draft202012Validator(semantic_schema)
        self.assertEqual(
            "project-manifest.semantic-rules.json",
            manifest_schema["x-research-observatory-semanticRules"],
        )
        self.assertEqual([], list(manifest_validator.iter_errors(manifest)))
        self.assertEqual([], list(layout_validator.iter_errors(layout)))
        self.assertEqual([], list(semantic_validator.iter_errors(semantic_rules)))
        self.assertEqual([], manifest_semantic_errors(manifest, semantic_rules))
        self.assertTrue(list(manifest_validator.iter_errors(invalid_manifest)))

        path_bearing = copy.deepcopy(manifest)
        path_bearing["absolutePath"] = "C:\\private\\study"
        self.assertTrue(list(manifest_validator.iter_errors(path_bearing)))

        redirected_layout = copy.deepcopy(layout)
        redirected_layout["entries"][0]["relativePath"] = "../outside/project.sqlite3"
        self.assertTrue(list(layout_validator.iter_errors(redirected_layout)))

        reversed_range = copy.deepcopy(manifest)
        reversed_range["applicationCompatibility"] = {"minimum": "1.0.0", "maximumExclusive": "0.1.0"}
        older_modified = copy.deepcopy(manifest)
        older_modified["modifiedAt"] = "2026-08-12T23:59:59Z"
        offset_timestamps = copy.deepcopy(manifest)
        offset_timestamps["createdAt"] = "2026-08-13T00:00:00+00:00"
        offset_timestamps["modifiedAt"] = "2026-08-13T00:00:00+00:00"
        unsafe_revision = copy.deepcopy(manifest)
        unsafe_revision["projectRevision"] = 9_007_199_254_740_992

        for candidate in (reversed_range, older_modified):
            self.assertEqual([], list(manifest_validator.iter_errors(candidate)))
            self.assertTrue(manifest_semantic_errors(candidate, semantic_rules))
        for candidate in (offset_timestamps, unsafe_revision):
            self.assertTrue(list(manifest_validator.iter_errors(candidate)))


if __name__ == "__main__":
    unittest.main()
