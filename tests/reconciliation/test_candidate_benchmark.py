"""Retain the scoring freeze while exercising the known qualification corpus."""

import ast
import hashlib
import json
import unittest
from pathlib import Path

from research_observatory_core.reconciliation import candidates

from tests.reconciliation.duplicate_benchmark import FIXTURE, load_split, metrics


def scoring_nodes(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    selected = {}
    for node in tree.body:
        name = getattr(node, "name", None)
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in {
            "ALGORITHM",
            "FEATURE_VERSION",
            "FIELD_NAMES",
            "_WEIGHTS",
            "_WORDS",
            "CandidateConfig",
            "_hash",
            "_prepare",
            "_dice",
            "_similarity",
            "compare_records",
        }:
            selected[name] = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
        if isinstance(node, ast.FunctionDef) and name in {"generate_candidates", "generate_prepared_candidates"}:
            start = next(
                (
                    index
                    for index, item in enumerate(node.body)
                    if isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id == "postings"
                ),
                None,
            )
            if start is not None:
                selected["blocking-and-ranking"] = hashlib.sha256(
                    ast.dump(ast.Module(body=node.body[start:], type_ignores=[]), include_attributes=False).encode()
                ).hexdigest()
    return selected


class CandidateBenchmarkTests(unittest.TestCase):
    def test_cached_entry_point_preserves_frozen_scoring_and_blocking(self):
        bridge = json.loads((FIXTURE / "scoring-cache-bridge-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(
            bridge["frozenScoringNodes"], scoring_nodes(Path(candidates.__file__).read_text(encoding="utf-8"))
        )
        self.assertTrue(bridge["qualificationResultsPreviouslyObserved"])
        self.assertEqual(bridge["configurationFingerprint"], candidates.DEFAULT_CONFIG.fingerprint)

    def test_known_qualification_corpus_meets_original_precision_and_recall_targets(self):
        records, gold = load_split("qualification")
        retrieval = candidates.generate_candidates(records)
        predicted = frozenset(
            (item.left, item.right)
            for item in retrieval.pairs
            if item.left.split(":", 1)[0] != item.right.split(":", 1)[0]
        )
        result = metrics(frozenset(item.key for item in records), predicted, gold)
        self.assertGreaterEqual(result["precision"], 0.90, result)
        self.assertGreaterEqual(result["recall"], 0.95, result)
        self.assertEqual(
            (1092, 1142, 1115, 20, 23),
            tuple(
                result[name]
                for name in (
                    "truePositives",
                    "returnedPairs",
                    "goldPairs",
                    "overmergedComponents",
                    "fragmentedComponents",
                )
            ),
        )
