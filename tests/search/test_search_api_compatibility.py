"""New search delivery must preserve every existing public API definition."""

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR = "a6e2b9146f788d489006998fccb0669bfba91bc7"


class SearchApiCompatibilityTests(unittest.TestCase):
    def test_exact_previous_operations_and_schemas_remain_available_unchanged(self):
        previous = json.loads(
            subprocess.check_output(
                ["git", "show", PREDECESSOR + ":packages/contracts/core-api/openapi.json"], cwd=ROOT
            )
        )
        current = json.loads((ROOT / "packages/contracts/core-api/openapi.json").read_bytes())
        for name, schema in previous["components"]["schemas"].items():
            with self.subTest(schema=name):
                self.assertTrue(name in current["components"]["schemas"], f"previous schema missing: {name}")
                self.assertEqual(schema, current["components"]["schemas"][name])
        old_operations = set()
        new_operations: set[str] = set()
        for path, methods in previous["paths"].items():
            self.assertIn(path, current["paths"])
            for verb, operation in methods.items():
                with self.subTest(path=path, verb=verb):
                    self.assertEqual(operation, current["paths"][path][verb])
                    old_operations.add(operation["operationId"])
        for methods in current["paths"].values():
            new_operations.update(operation["operationId"] for operation in methods.values())
        self.assertEqual(102, len(old_operations))
        self.assertEqual(
            {
                "validateLexicalQuery",
                "executeLexicalSearch",
                "inspectLexicalSearch",
                "pageLexicalSearch",
                "explainLexicalSearch",
                "cancelLexicalSearch",
            },
            new_operations - old_operations,
        )


if __name__ == "__main__":
    unittest.main()
