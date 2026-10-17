"""Strict executed lexical request values; no persistence or permission claim."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.search import parse_query  # noqa: E402


class SearchRunValueTests(unittest.TestCase):
    def request(self, **changes):
        from research_observatory_core.search.run_values import SearchRequestInput

        value = {
            "projectId": "0199e895-0000-7000-8000-000000000001",
            "commandId": "0199e895-0000-7000-8000-000000000002",
            "actorId": "0199e895-0000-7000-8000-000000000003",
            "sessionId": "1" * 32,
            "intent": {
                "projectId": "0199e895-0000-7000-8000-000000000001",
                "domainProjectId": "0199e895-0000-7000-8000-000000000004",
                "intentId": "0199e895-0000-7000-8000-000000000005",
                "revisionId": "0199e895-0000-7000-8000-000000000006",
                "contentHash": "sha256:" + "a" * 64,
                "status": "accepted",
            },
            "policySha256": "b" * 64,
            "queryDocument": parse_query('title:"café ledger" AND year>=2020').to_json(),
            "filters": {"yearFrom": 2021, "yearTo": None},
        }
        value.update(changes)
        return SearchRequestInput.model_validate_json(__import__("json").dumps(value))

    def test_roundtrip_binds_original_normalized_ast_and_every_authority_field(self):
        from research_observatory_core.search.run_values import SearchRequestInput

        value = self.request()
        self.assertEqual(value, SearchRequestInput.model_validate_json(value.model_dump_json(by_alias=True)))
        self.assertEqual(71, len(value.configuration_hash))
        self.assertEqual(value.configuration_hash, self.request().configuration_hash)
        changed = self.request(queryDocument=parse_query("different").to_json())
        self.assertNotEqual(value.configuration_hash, changed.configuration_hash)
        self.assertEqual(value.idempotency_key, changed.idempotency_key)
        self.assertNotIn("café", repr(value))

    def test_extra_forged_query_filter_and_unaccepted_authority_are_rejected(self):
        from pydantic import ValidationError

        valid = self.request()
        for changes in (
            {"sql": "DROP TABLE"},
            {"queryDocument": valid.query_document.replace("café ledger", "altered", 1)},
            {"filters": {"yearFrom": True, "yearTo": None}},
            {"filters": {"yearFrom": 2025, "yearTo": 2024}},
            {"rankingVersion": "unregistered-rank"},
            {"sessionId": "untrusted"},
            {"projectId": "0199e895-0000-7000-8000-000000000099"},
            {"intent": {**valid.intent.model_dump(mode="json", by_alias=True), "status": "draft"}},
        ):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ValidationError):
                self.request(**changes)


if __name__ == "__main__":
    unittest.main()
