"""Actual Core-to-JSON boundary and portable structural validation."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))
sys.path.insert(0, str(REPO / "tools"))

from core_api_contract import generated_artifacts  # noqa: E402
from research_observatory_core.search import QueryDocument, QueryError, QueryNode, parse_query  # noqa: E402
from research_observatory_core.search.schemas import analyzer_profile, query_schemas  # noqa: E402


class QueryContractTests(unittest.TestCase):
    def test_pre_w3_artifacts_and_api_operations_remain_available(self):
        fixture = json.loads((REPO / "tests/fixtures/search/core-api.pre-w3.v1.json").read_text("utf-8"))
        generated = generated_artifacts(REPO)
        artifact_paths = {path.relative_to(REPO).as_posix() for path in generated}
        self.assertTrue(set(fixture["artifactPaths"]) <= artifact_paths)
        api = json.loads(generated[REPO / "packages/contracts/core-api/openapi.json"])
        for operation in fixture["operations"]:
            with self.subTest(path=operation["path"], method=operation["method"]):
                self.assertEqual(
                    operation["operationId"], api["paths"][operation["path"]][operation["method"]]["operationId"]
                )

    def test_generated_schemas_and_analyzer_profile_are_current(self):
        for filename, expected in query_schemas().items():
            with self.subTest(filename=filename):
                Draft202012Validator.check_schema(expected)
                actual = json.loads((REPO / "packages/contracts/search" / filename).read_text("utf-8"))
                self.assertEqual(expected, actual)
        profile = analyzer_profile()
        self.assertEqual(
            ("unicode61", 2, False, "unchanged"),
            (
                profile["tokenizer"],
                profile["removeDiacritics"],
                profile["stemming"],
                profile["sourceNormalization"],
            ),
        )
        Draft202012Validator(query_schemas()["analyzer-profile.schema.json"]).validate(profile)

    def test_valid_snapshots_and_safe_diagnostics_match_portable_schemas(self):
        schemas = query_schemas()
        validator = Draft202012Validator(schemas["query-document.schema.json"])
        for source in ('title:"phrase" OR NOT (tags:manual AND year>=2020)', "é e\u0301", "NOT NOT alpha"):
            document = parse_query(source).to_dict()
            validator.validate(document)
            for change in ({"schemaVersion": "future"}, {"analyzerId": "future"}, {"other": True}):
                self.assertFalse(validator.is_valid(document | change))
        try:
            parse_query("alpha AND")
        except QueryError as error:
            Draft202012Validator(schemas["query-diagnostic.schema.json"]).validate(error.diagnostic.to_dict())
        else:
            self.fail("invalid query accepted")

    def test_expanded_aliases_and_forged_documents_are_bounded_before_dump(self):
        node = QueryNode(kind="literal", value="alpha")
        for _ in range(9):
            parent = object.__new__(QueryNode)
            for key, value in (
                ("kind", "and"),
                ("field", None),
                ("value", None),
                ("operator", None),
                ("operands", (node, node)),
            ):
                object.__setattr__(parent, key, value)
            node = parent
        with self.assertRaises(QueryError):
            QueryDocument("alpha", "alpha", node)
        document = parse_query("alpha")
        object.__setattr__(document, "ast", node)
        with self.assertRaises(QueryError):
            document.to_dict()

    def test_core_query_contract_runs_in_isolated_process_without_ui_imports(self):
        script = """
import json, sys
sys.path.insert(0, sys.argv[1])
from research_observatory_core.search import parse_query, load_query_document
query = parse_query('title:"local evidence" AND year>=2020')
assert load_query_document(query.to_json()) == query
assert not any(name.startswith(('fastapi', 'uvicorn', 'PySide', 'tkinter')) for name in sys.modules)
print(json.dumps({'roundtrip': True, 'grammarVersion': query.grammar_version}))
"""
        result = subprocess.run(
            [sys.executable, "-I", "-c", script, str(REPO / "services/core-api/src")],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["roundtrip"])


if __name__ == "__main__":
    unittest.main()
