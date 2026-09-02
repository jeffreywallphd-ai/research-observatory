#!/usr/bin/env python3
"""Qualify deterministic dependency-impact planning on a large cyclic graph."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

FIXTURE_VERSION = "dependency-impact-scc-v1"
MEMBER_COUNT = 1_100
REPETITIONS = 7
REFERENCE_P95_MS = 400.0
REGRESSION_LIMIT_MS = 500.0
ABSOLUTE_LIMIT_MS = 1_000.0
PROJECT_ID = "01890f6e-6a40-4cc5-98b7-123456789abc"
ACTOR_ID = "01890f6e-6a40-7cc5-98b7-000000000301"
OCCURRED_AT = "2026-09-01T22:00:00.000Z"


def _uid(index: int) -> str:
    return f"01890f6e-6a40-7cc5-98b7-{index:012x}"


def _fingerprint(character: str) -> str:
    return "sha256:" + character * 64


def _fixture() -> tuple[Any, Any, tuple[Any, ...], tuple[str, ...]]:
    from research_observatory_core.dependency_impacts import DependencyGraphEdge
    from research_observatory_core.ports.repositories import AggregateRevision, DependencyChange

    previous = AggregateRevision(
        revision_id=_uid(1),
        aggregate_id=_uid(101),
        aggregate_kind="evidence",
        project_id=PROJECT_ID,
        revision=1,
        contract_version="1.0",
        created_at=OCCURRED_AT,
        modified_at=OCCURRED_AT,
        display_label_observed="benchmark source",
        display_label_normalized=None,
        knowledge_status="observed",
        rights_status="unknown",
    )
    change = DependencyChange(
        change_id=_uid(80_001),
        idempotency_key="dependency-impact-performance-v1",
        reason="SOURCE_VERSION",
        dependency_kind="source-revision",
        previous_revision_id=previous.revision_id,
        replacement_revision_id=_uid(2),
        configuration_id=None,
        previous_configuration_version=None,
        replacement_configuration_version=None,
        previous_fingerprint=_fingerprint("a"),
        replacement_fingerprint=_fingerprint("b"),
        propagation_policy_id="dependency.propagation.v1",
        propagation_policy_version="1.0.0",
        actor_id=ACTOR_ID,
        trace_id="9" * 32,
        occurred_at=OCCURRED_AT,
    )
    hub = _uid(10_000)
    members = tuple(_uid(11_000 + index) for index in range(MEMBER_COUNT))
    edges = [
        DependencyGraphEdge(
            _uid(100_000),
            previous.revision_id,
            hub,
            "evidence",
            "direct",
            _fingerprint("a"),
            "dependency.propagation.v1",
            "1.0.0",
        )
    ]
    edges.extend(
        DependencyGraphEdge(
            _uid(101_000 + index),
            hub,
            member,
            "evidence",
            "direct",
            _fingerprint("c"),
            "dependency.propagation.v1",
            "1.0.0",
        )
        for index, member in enumerate(members)
    )
    edges.extend(
        DependencyGraphEdge(
            _uid(103_000 + index),
            member,
            members[(index + 1) % len(members)],
            "evidence",
            "direct",
            _fingerprint("d"),
            "dependency.propagation.v1",
            "1.0.0",
        )
        for index, member in enumerate(members)
    )
    return previous, change, tuple(edges), members


def _percentile_95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _run(repo: Path) -> dict[str, Any]:
    sys.path.insert(0, str(repo / "services" / "core-api" / "src"))
    from research_observatory_core.dependency_impacts import plan_dependency_impact

    _, change, edges, members = _fixture()

    started = time.perf_counter_ns()
    cold_preview = plan_dependency_impact(PROJECT_ID, change, edges)
    cold_ms = (time.perf_counter_ns() - started) / 1_000_000

    samples_ms: list[float] = []
    stable_preview_sha256 = cold_preview.preview_sha256
    final_preview = cold_preview
    for _ in range(REPETITIONS):
        started = time.perf_counter_ns()
        final_preview = plan_dependency_impact(PROJECT_ID, change, edges)
        samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        if final_preview.preview_sha256 != stable_preview_sha256:
            raise RuntimeError("dependency-impact preview changed across identical repetitions")

    p95_ms = _percentile_95(samples_ms)
    exact_cycle = any(group.member_revision_ids == members for group in final_preview.cycle_groups)
    expected_shape = (
        exact_cycle
        and final_preview.visited_nodes == MEMBER_COUNT + 1
        and final_preview.visited_edges == MEMBER_COUNT * 2 + 1
        and len(final_preview.impacts) == MEMBER_COUNT + 1
    )
    performance_ok = p95_ms <= REGRESSION_LIMIT_MS and p95_ms <= ABSOLUTE_LIMIT_MS
    return {
        "schemaVersion": "1.0",
        "documentType": "dependency-impact-performance-report",
        "fixture": {
            "version": FIXTURE_VERSION,
            "shape": "one changed revision -> hub -> 1,100-member directed cycle",
            "nodeCount": MEMBER_COUNT + 2,
            "edgeCount": MEMBER_COUNT * 2 + 1,
            "memberCount": MEMBER_COUNT,
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logicalCpuCount": os.cpu_count(),
            "pythonVersion": platform.python_version(),
            "sqliteVersion": sqlite3.sqlite_version,
        },
        "method": {
            "timer": "time.perf_counter_ns",
            "repetitions": REPETITIONS,
            "distribution": "one cold sample plus all warm samples and nearest-rank p95",
            "state": "fixture constructed once; first planner call cold, later calls warm-process",
        },
        "thresholds": {
            "referenceP95Ms": REFERENCE_P95_MS,
            "regressionPercent": 25,
            "regressionLimitMs": REGRESSION_LIMIT_MS,
            "absoluteLimitMs": ABSOLUTE_LIMIT_MS,
            "basis": "initial conservative local Windows x64 guard; relaxation requires review",
        },
        "measurements": {
            "coldMs": round(cold_ms, 3),
            "samplesMs": [round(sample, 3) for sample in samples_ms],
            "p95Ms": round(p95_ms, 3),
        },
        "checks": {
            "exactCycleAndTraversalShape": expected_shape,
            "stablePreviewAcrossRepetitions": final_preview.preview_sha256 == stable_preview_sha256,
            "performanceWithinBudget": performance_ok,
        },
        "ok": expected_shape and performance_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    report = _run(repo)
    report_path = args.report if args.report.is_absolute() else repo / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if report["ok"]:
        print(f"Dependency impact performance: PASS - p95 {report['measurements']['p95Ms']} ms")
        return 0
    print("Dependency impact performance: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
