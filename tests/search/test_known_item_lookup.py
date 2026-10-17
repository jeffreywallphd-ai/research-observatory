"""Frozen synthetic lookup comparison through actual protected FTS5/BM25.

IDs are minted by Core before lookup. Explicit lawful mirror rows and in-memory
key adapters isolate ranking quality; this is not a Native/rights-boundary test
or evidence of scientific relevance, external corpus recall or coverage.
"""

import hashlib
import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402
from research_observatory_core.search.ranking import FIELD_WEIGHTS, RANKING_VERSION  # noqa: E402

from tests.search.fixture_support import ProtectedIndexFixture  # noqa: E402
from tests.search.test_protected_lexical_store import row  # noqa: E402


class KnownItemLookupTests(ProtectedIndexFixture):
    def test_frozen_complete_held_out_title_and_doi_recall_at_twenty(self):
        payload = (ROOT / "tests/search/fixtures/synthetic-known-items.v1.json").read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        self.assertEqual("62f37a7259351dfa82c9ea1f2de8148d9e299c6c6db27cad16a903ee45a9ae32", digest)
        fixture = json.loads(payload)
        mapping = {item["caseId"]: new_uuid_v7() for item in fixture["items"]}
        output = ROOT / "artifacts/tmp" / ("CAP-06.S01.T03.known-items-" + new_uuid_v7() + ".json")
        report = {
            "status": "RUNNING",
            "fixtureSha256": digest,
            "boundary": (
                "actual SQLCipher FTS5/BM25; explicit synthetic lawful mirror; "
                "Core UUID factory; in-memory vault/key adapters"
            ),
            "limits": fixture["scopeLimits"],
            "mappingBoundBeforeLookup": mapping,
            "rankingVersion": RANKING_VERSION,
            "fieldWeights": FIELD_WEIGHTS,
            "queries": [],
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        values = tuple(
            row(
                mapping[item["caseId"]],
                item["title"],
                abstract=item["abstract"],
                authors=item["authors"],
                venue=item["venue"],
                identifiers=item["doi"],
                year=item["year"],
            )
            for item in fixture["items"]
        )
        entries, items = tuple(value.entry_id for value in values), tuple(value.item_id for value in values)
        failures = []
        with self.store(create=True) as store:
            store.apply(values, (), expected_checkpoint=0, checkpoint=1)
            store.integrity_check()
            for query in fixture["queries"]:
                started = time.perf_counter()
                outcome = {
                    "queryId": query["queryId"],
                    "split": query["split"],
                    "kind": query["kind"],
                    "expectedItemIds": [mapping[key] for key in query["expectedCaseIds"]],
                }
                try:
                    parsed = parse_query(query["originalQuery"])
                    ranked = store.rank(parsed, entries, items, explain_limit=0)
                    replay = store.rank(parsed, tuple(reversed(entries)), tuple(reversed(items)), explain_limit=0)
                    self.assertEqual(ranked, replay)
                    top = [value.item_id for value in ranked[:20]]
                    outcome.update(
                        status="PASS",
                        top20ItemIds=top,
                        recallAt20=sum(value in top for value in outcome["expectedItemIds"])
                        / len(outcome["expectedItemIds"]),
                    )
                except Exception as error:
                    outcome.update(status="FAIL", errorType=type(error).__name__, recallAt20=0)
                    failures.append(query["queryId"])
                outcome["elapsedSecondsIncludingReplay"] = time.perf_counter() - started
                report["queries"].append(outcome)
                output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["strata"] = []
        for split, expected_count in (("development", 8), ("held-out", 64)):
            selected = [value for value in report["queries"] if value["split"] == split]
            self.assertEqual(expected_count, len(selected))
            for kind in ("all", "title", "doi"):
                selected_kind = selected if kind == "all" else [value for value in selected if value["kind"] == kind]
                report["strata"].append(
                    {
                        "split": split,
                        "kind": kind,
                        "denominator": len(selected_kind),
                        "meanRecallAt20": sum(value["recallAt20"] for value in selected_kind) / len(selected_kind),
                    }
                )
        held_out = next(value for value in report["strata"] if value["split"] == "held-out" and value["kind"] == "all")
        report["status"] = "PASS" if not failures and held_out["meanRecallAt20"] >= 0.90 else "FAIL"
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Synthetic known-item report:", output.relative_to(ROOT).as_posix())
        self.assertEqual([], failures)
        self.assertGreaterEqual(held_out["meanRecallAt20"], 0.90)


if __name__ == "__main__":
    unittest.main()
