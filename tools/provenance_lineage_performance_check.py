#!/usr/bin/env python3
"""Qualify bounded large-lineage inspection on a real local SQLite project."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

FIXTURE_VERSION = "provenance-lineage-wide-dag-v1"
LEAF_COUNT = 4_096
BRANCH_FACTOR = 64
EXPECTED_FACT_COUNT = 16_642
CURSOR_BOUNDARY = 10_000
PAGE_SIZE = 100
REPETITIONS = 3
REFERENCE_P95_MS = 15_000.0
REGRESSION_LIMIT_MS = REFERENCE_P95_MS * 1.20
ABSOLUTE_LIMIT_MS = 30_000.0
PROJECT_ID = "018f0000-0000-4000-8000-600000000001"
ACTOR_ID = "018f0000-0000-7000-8000-500000000001"
OCCURRED_AT = "2026-08-30T00:00:00.000Z"


def _uuid7(namespace: int, index: int) -> str:
    return f"018f0000-0000-7000-8000-{namespace + index:012x}"


def _draft(index: int, *, inputs: tuple[Any, ...] = ()) -> Any:
    from research_observatory_core.ports.repositories import AggregateRevisionDraft

    return AggregateRevisionDraft(
        revision_id=_uuid7(0x200000000000, index),
        aggregate_id=_uuid7(0x100000000000, index),
        aggregate_kind="evidence",
        created_at=OCCURRED_AT,
        modified_at=OCCURRED_AT,
        display_label_observed=f"Lineage benchmark revision {index}",
        display_label_normalized=None,
        knowledge_status="verified",
        rights_status="allowed",
        provenance_inputs=inputs,
    )


def _event(index: int) -> Any:
    from research_observatory_core.ports.repositories import AtomicRepositoryEvent

    return AtomicRepositoryEvent(
        event_id=_uuid7(0x300000000000, index),
        outbox_id=_uuid7(0x400000000000, index),
        event_type="evidence.revision-recorded",
        occurred_at=OCCURRED_AT,
        available_at=OCCURRED_AT,
        trace_id=f"{index + 1:032x}",
        actor_type="worker",
        actor_id=ACTOR_ID,
        idempotency_key=f"lineage-benchmark-{index}",
    )


def _percentile_95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _build_fixture(database: Path) -> tuple[Any, float]:
    from research_observatory_core.repositories import create_sqlite_unit_of_work_factory
    from research_observatory_core.storage import initialize_database

    started = time.perf_counter_ns()
    initialize_database(database, project_id=PROJECT_ID, project_created_at=OCCURRED_AT)
    factory = create_sqlite_unit_of_work_factory(database, PROJECT_ID)
    leaves: list[Any] = []
    for batch_start in range(0, LEAF_COUNT, 256):
        with factory() as unit:
            for index in range(batch_start, min(batch_start + 256, LEAF_COUNT)):
                leaves.append(unit.aggregates.append(_draft(index), _event(index), expected_revision=None))
            unit.commit()
    intermediate: list[Any] = []
    with factory() as unit:
        for offset in range(0, LEAF_COUNT, BRANCH_FACTOR):
            index = LEAF_COUNT + len(intermediate)
            intermediate.append(
                unit.aggregates.append(
                    _draft(index, inputs=tuple(leaves[offset : offset + BRANCH_FACTOR])),
                    _event(index),
                    expected_revision=None,
                )
            )
        unit.commit()
    root_index = LEAF_COUNT + len(intermediate)
    with factory() as unit:
        root = unit.aggregates.append(
            _draft(root_index, inputs=tuple(intermediate)),
            _event(root_index),
            expected_revision=None,
        )
        unit.commit()
    return root, (time.perf_counter_ns() - started) / 1_000_000


def _run(repo: Path) -> dict[str, Any]:
    service_src = repo / "services" / "core-api" / "src"
    sys.path.insert(0, str(service_src))
    import research_observatory_core.repositories as repository_module
    from research_observatory_core.repositories import (
        _SqliteProvenanceLedgerRepository,
        sqlite_provenance_ledger_repository,
    )
    from research_observatory_core.storage import development_plaintext_database_fixture, open_canonical_database

    with (
        development_plaintext_database_fixture(),
        tempfile.TemporaryDirectory(prefix="ro-provenance-lineage-performance-") as temporary,
    ):
        root_path = Path(temporary).resolve()
        database = root_path / "state" / "project.sqlite3"
        database.parent.mkdir()
        root, fixture_build_ms = _build_fixture(database)
        connection = open_canonical_database(database, expected_project_id=PROJECT_ID)
        try:
            fact_count = int(
                connection.execute(
                    "SELECT count(*) FROM provenance_ledger_relations WHERE entity_revision_id IS NOT NULL"
                ).fetchone()[0]
            )
            revision_count = int(connection.execute("SELECT count(*) FROM aggregate_revisions").fetchone()[0])
        finally:
            connection.close()

        integrity_samples_ms: list[float] = []
        original_integrity_state = repository_module._ledger_integrity_state

        def measured_integrity_state(connection: Any, project_id: str) -> str:
            started = time.perf_counter_ns()
            result = original_integrity_state(connection, project_id)
            integrity_samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
            return result

        repository_module._ledger_integrity_state = measured_integrity_state
        samples_ms: list[float] = []
        stable_fact_ids: tuple[str, ...] | None = None
        boundary_page = None
        for _ in range(REPETITIONS):
            started = time.perf_counter_ns()
            page = sqlite_provenance_ledger_repository(root_path, PROJECT_ID).lineage(
                revision_id=root.revision_id,
                direction="ancestors",
                cursor=CURSOR_BOUNDARY,
                page_size=PAGE_SIZE,
                max_depth=4,
            )
            samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
            fact_ids = tuple(item.fact_id for item in page.items)
            if stable_fact_ids is None:
                stable_fact_ids = fact_ids
            elif stable_fact_ids != fact_ids:
                raise RuntimeError("large-lineage ordering changed across reopened queries")
            boundary_page = page
        if boundary_page is None:
            raise RuntimeError("large-lineage measurement did not run")

        try:
            scan_page = _SqliteProvenanceLedgerRepository(
                database,
                PROJECT_ID,
                absolute_scan_limit=64,
            ).lineage(
                revision_id=root.revision_id,
                direction="ancestors",
                cursor=0,
                page_size=PAGE_SIZE,
                max_depth=4,
            )
        finally:
            repository_module._ledger_integrity_state = original_integrity_state
        p95_ms = _percentile_95(samples_ms)
        expected_boundary = (
            fact_count == EXPECTED_FACT_COUNT
            and len(boundary_page.items) == PAGE_SIZE
            and boundary_page.next_cursor is None
            and boundary_page.truncated
            and boundary_page.truncation_reason == "cursor-limit"
            and boundary_page.integrity_state == "integrity-review"
            and not boundary_page.export_allowed
            and boundary_page.export_denial_reason == "integrity-review"
            and fact_count - CURSOR_BOUNDARY - len(boundary_page.items) > 0
        )
        expected_scan = (
            bool(scan_page.items)
            and scan_page.truncated
            and scan_page.truncation_reason == "scan-limit"
            and scan_page.integrity_state == "integrity-review"
            and not scan_page.export_allowed
            and scan_page.export_denial_reason == "integrity-review"
        )
        performance_ok = p95_ms <= ABSOLUTE_LIMIT_MS and p95_ms <= REGRESSION_LIMIT_MS
        return {
            "schemaVersion": "1.0",
            "documentType": "provenance-lineage-performance-report",
            "fixture": {
                "version": FIXTURE_VERSION,
                "shape": "4096 leaves -> 64 intermediates -> 1 root",
                "revisionCount": revision_count,
                "factCount": fact_count,
                "expectedFactCount": EXPECTED_FACT_COUNT,
                "fixtureBuildMs": round(fixture_build_ms, 3),
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
                "distribution": "all raw samples plus nearest-rank p95",
                "state": (
                    "new SQLite connection and full integrity verification per sample; "
                    "first sample cold-process/connection, later samples warm-filesystem"
                ),
                "cursor": CURSOR_BOUNDARY,
                "pageSize": PAGE_SIZE,
                "maxDepth": 4,
            },
            "thresholds": {
                "referenceP95Ms": REFERENCE_P95_MS,
                "regressionPercent": 20,
                "regressionLimitMs": REGRESSION_LIMIT_MS,
                "absoluteLimitMs": ABSOLUTE_LIMIT_MS,
            },
            "measurements": {
                "samplesMs": [round(sample, 3) for sample in samples_ms],
                "p95Ms": round(p95_ms, 3),
                "integritySamplesMs": [round(sample, 3) for sample in integrity_samples_ms[:REPETITIONS]],
                "traversalSamplesMs": [
                    round(total - integrity, 3)
                    for total, integrity in zip(
                        samples_ms,
                        integrity_samples_ms[:REPETITIONS],
                        strict=True,
                    )
                ],
            },
            "cursorBoundary": {
                "returnedFacts": len(boundary_page.items),
                "hiddenAcceptedBoundFacts": fact_count - CURSOR_BOUNDARY - len(boundary_page.items),
                "nextCursor": boundary_page.next_cursor,
                "truncated": boundary_page.truncated,
                "truncationReason": boundary_page.truncation_reason,
                "integrityState": boundary_page.integrity_state,
                "exportAllowed": boundary_page.export_allowed,
            },
            "scanBoundary": {
                "returnedFacts": len(scan_page.items),
                "nextCursor": scan_page.next_cursor,
                "truncated": scan_page.truncated,
                "truncationReason": scan_page.truncation_reason,
                "integrityState": scan_page.integrity_state,
                "exportAllowed": scan_page.export_allowed,
            },
            "stableOrderingAcrossReopen": stable_fact_ids is not None,
            "boundedPageMaterialization": len(boundary_page.items) <= PAGE_SIZE,
            "checks": {
                "cursorBoundaryFailsClosed": expected_boundary,
                "scanBoundaryFailsClosed": expected_scan,
                "performanceWithinBudget": performance_ok,
            },
            "ok": expected_boundary and expected_scan and performance_ok,
            "sampleFactIdsSha256": hashlib.sha256("\n".join(stable_fact_ids or ()).encode("utf-8")).hexdigest(),
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
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=list) + "\n", encoding="utf-8")
    if report["ok"]:
        print(f"Provenance lineage performance: PASS - p95 {report['measurements']['p95Ms']} ms")
        return 0
    print("Provenance lineage performance: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
