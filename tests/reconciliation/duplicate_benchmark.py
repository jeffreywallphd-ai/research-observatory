"""Frozen cross-source oracle evaluation, separate from matching implementation."""

import csv
import hashlib
import io
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from research_observatory_core.reconciliation.candidates import CandidateRecord

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/scholarly-duplicates"
MANIFEST_SHA = "6b77da6f8aef1fe669bcfa607cfda184e357ae7742333a74588d224a69ef6d8c"


def load_split(split: str) -> tuple[tuple[CandidateRecord, ...], frozenset[tuple[str, str]]]:
    if split not in {"development", "qualification"}:
        raise ValueError("unknown benchmark split")
    raw = (FIXTURE / "benchmark-v1.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError("benchmark manifest differs")
    manifest = json.loads(raw)
    selected = set(manifest["splits"][split])
    tables = {}
    for name, authority in manifest["members"].items():
        raw = (FIXTURE / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != authority["fixtureSha256"]:
            raise ValueError("benchmark member differs")
        tables[name] = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    records = []
    for name, namespace in (("DBLP2.csv", "dblp:"), ("ACM.csv", "acm:")):
        for row in tables[name]:
            key = namespace + row["id"]
            if key in selected:
                # Source IDs and labels are not features. No missing field is filled.
                fields = tuple((field, (row[field],)) for field in ("title", "authors", "venue", "year") if row[field])
                records.append(
                    CandidateRecord(key, hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(), fields)
                )
    pairs = frozenset(
        ("acm:" + row["idACM"], "dblp:" + row["idDBLP"])
        for row in tables["DBLP-ACM_perfectMapping.csv"]
        if "dblp:" + row["idDBLP"] in selected
    )
    if any(a not in selected or b not in selected for a, b in pairs) or {item.key for item in records} != selected:
        raise ValueError("benchmark split differs")
    return tuple(records), pairs


def _components(keys: frozenset[str], pairs: frozenset[tuple[str, str]]) -> tuple[frozenset[str], ...]:
    parents = {key: key for key in keys}

    def root(value):
        while parents[value] != value:
            parents[value] = parents[parents[value]]
            value = parents[value]
        return value

    for a, b in sorted(pairs):
        parents[root(b)] = root(a)
    groups: dict[str, set[str]] = defaultdict(set)
    for key in keys:
        groups[root(key)].add(key)
    return tuple(frozenset(group) for _, group in sorted(groups.items()))


def metrics(keys: frozenset[str], predicted: frozenset[tuple[str, str]], gold: frozenset[tuple[str, str]]) -> dict:
    for pairs in (predicted, gold):
        if any(a >= b or a not in keys or b not in keys or a.split(":", 1)[0] == b.split(":", 1)[0] for a, b in pairs):
            raise ValueError("benchmark pair identity invalid")
    true_positive = predicted & gold
    expected, actual = _components(keys, gold), _components(keys, predicted)
    expected_index = {key: index for index, group in enumerate(expected) for key in group}
    actual_index = {key: index for index, group in enumerate(actual) for key in group}
    closure = frozenset(
        (a, b)
        for group in actual
        for a, b in combinations(sorted(group), 2)
        if a.split(":", 1)[0] != b.split(":", 1)[0]
    )
    return {
        "truePositives": len(true_positive),
        "returnedPairs": len(predicted),
        "goldPairs": len(gold),
        "precision": len(true_positive) / len(predicted) if predicted else 0,
        "recall": len(true_positive) / len(gold) if gold else 0,
        "falsePositivePairs": sorted(predicted - gold),
        "falseNegativePairs": sorted(gold - predicted),
        "overmergedComponents": sum(len({expected_index[key] for key in group}) > 1 for group in actual),
        "fragmentedComponents": sum(len({actual_index[key] for key in group}) > 1 for group in expected),
        "transitiveFalsePositivePairs": sorted(closure - gold),
        "transitiveFalseNegativePairs": sorted(gold - closure),
    }
