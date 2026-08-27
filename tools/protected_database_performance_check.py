"""Benchmark the W1 protected SQLite profile on the release-authoritative Windows host."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from build_manifest import guarded_atomic_write_json

PROJECT_ID = "123e4567-e89b-42d3-a456-426614174000"
CREATED_AT = "2026-08-27T00:00:00.000Z"
ABSOLUTE_P95_BUDGET_MS = {
    "open": 100.0,
    "representativeQuery": 50.0,
    "integrity": 750.0,
    "backup": 750.0,
    "plaintextMigration": 1500.0,
    "rekey": 1500.0,
}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.999999)))
    return ordered[rank]


def _measure(operation: Callable[[int], None], repetitions: int) -> list[float]:
    samples: list[float] = []
    for index in range(repetitions):
        started = time.perf_counter_ns()
        operation(index)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return samples


def _metric(samples: list[float], budget: float) -> dict[str, Any]:
    p95 = _percentile(samples, 0.95)
    return {
        "samplesMilliseconds": [round(value, 3) for value in samples],
        "medianMilliseconds": round(statistics.median(samples), 3),
        "p95Milliseconds": round(p95, 3),
        "absoluteP95BudgetMilliseconds": budget,
        "futureRegressionThresholdPercent": 20,
        "ok": p95 <= budget,
    }


def run_benchmark(repo: Path, repetitions: int) -> dict[str, Any]:
    if os.name != "nt" or platform.machine().casefold() not in {"amd64", "x86_64"}:
        raise RuntimeError("protected database qualification requires Windows x64")
    core_src = repo / "services" / "core-api" / "src"
    sys.path.insert(0, str(core_src))
    sys.path.insert(0, str(repo))
    try:
        from research_observatory_core.storage import (
            SQLCIPHER_PROFILE,
            configure_protected_database_provider,
            create_protected_database_backup,
            database_integrity_report,
            development_plaintext_database_fixture,
            initialize_database,
            migrate_plaintext_database_to_protected,
            open_canonical_database,
            rekey_protected_database,
        )

        from tests.database_key_fixtures import InMemoryDatabaseKeyProvider

        scratch = repo / "artifacts" / "tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="protected-database-benchmark-", dir=scratch) as temporary:
            root = Path(temporary).resolve(strict=True)
            project = root / "project"
            state = project / "state"
            state.mkdir(parents=True)
            (project / ".tmp").mkdir()
            database = state / "project.sqlite3"
            keys = InMemoryDatabaseKeyProvider()
            configure_protected_database_provider(keys)
            initialize_database(database, project_id=PROJECT_ID, project_created_at=CREATED_AT)

            # One unreported warmup is excluded from all distributions.
            warm = open_canonical_database(database, expected_project_id=PROJECT_ID)
            warm.execute("SELECT project_id FROM projects").fetchone()
            warm.close()

            def open_operation(_index: int) -> None:
                connection = open_canonical_database(database, expected_project_id=PROJECT_ID)
                connection.close()

            def query_operation(_index: int) -> None:
                connection = open_canonical_database(database, expected_project_id=PROJECT_ID)
                try:
                    for _ in range(100):
                        row = connection.execute(
                            "SELECT project_id, created_at FROM projects WHERE singleton=1"
                        ).fetchone()
                        if row is None or row[0] != PROJECT_ID:
                            raise RuntimeError("representative protected query returned the wrong project")
                finally:
                    connection.close()

            def integrity_operation(_index: int) -> None:
                connection = open_canonical_database(database, expected_project_id=PROJECT_ID)
                try:
                    report = database_integrity_report(connection, expected_project_id=PROJECT_ID)
                    if not report.ok:
                        raise RuntimeError("protected integrity benchmark failed")
                finally:
                    connection.close()

            def backup_operation(index: int) -> None:
                backup = root / f"backup-{index}.sqlite3"
                create_protected_database_backup(database, backup, project_id=PROJECT_ID)
                backup.unlink()

            def migration_operation(index: int) -> None:
                candidate_project = root / f"migration-{index}"
                candidate_state = candidate_project / "state"
                candidate_state.mkdir(parents=True)
                (candidate_project / ".tmp").mkdir()
                candidate = candidate_state / "project.sqlite3"
                with development_plaintext_database_fixture():
                    initialize_database(candidate, project_id=PROJECT_ID, project_created_at=CREATED_AT)
                configure_protected_database_provider(InMemoryDatabaseKeyProvider())
                result = migrate_plaintext_database_to_protected(
                    candidate,
                    project_id=PROJECT_ID,
                    operation_id=f"{index + 1:032x}",
                    approval_token="approve-plaintext-to-protected-v1",
                )
                if result.outcome != "protected":
                    raise RuntimeError("protected migration benchmark did not publish ciphertext")
                configure_protected_database_provider(keys)

            def rekey_operation(index: int) -> None:
                result = rekey_protected_database(
                    database,
                    project_id=PROJECT_ID,
                    operation_id=f"{index + 10_000:032x}",
                )
                if result.outcome != "rekeyed":
                    raise RuntimeError("protected rekey benchmark did not activate the new key")

            operations = {
                "open": open_operation,
                "representativeQuery": query_operation,
                "integrity": integrity_operation,
                "backup": backup_operation,
                "plaintextMigration": migration_operation,
                "rekey": rekey_operation,
            }
            metrics = {
                name: _metric(_measure(operation, repetitions), ABSOLUTE_P95_BUDGET_MS[name])
                for name, operation in operations.items()
            }
            tool = Path(__file__).resolve(strict=True)
            return {
                "schemaVersion": "1.0",
                "documentType": "research-observatory-protected-database-performance",
                "ok": all(metric["ok"] for metric in metrics.values()),
                "profileId": SQLCIPHER_PROFILE,
                "fixture": "empty-current-schema-with-100-project-identity-reads",
                "state": "one-filesystem-warmup-then-warm-process-cold-connections",
                "repetitionsPerMetric": repetitions,
                "distribution": "median-and-nearest-rank-p95-all-samples-retained",
                "host": {
                    "operatingSystem": platform.platform(),
                    "machine": platform.machine(),
                    "processor": platform.processor() or "unreported-by-platform-api",
                    "logicalCpuCount": os.cpu_count(),
                    "python": platform.python_version(),
                },
                "tool": {
                    "path": tool.relative_to(repo).as_posix(),
                    "sha256": hashlib.sha256(tool.read_bytes()).hexdigest(),
                },
                "metrics": metrics,
            }
    finally:
        sys.path.remove(str(repo))
        sys.path.remove(str(core_src))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()
    if not 2 <= args.repetitions <= 30:
        parser.error("--repetitions must be between 2 and 30")
    repo = args.repo.resolve(strict=True)
    report = args.report if args.report.is_absolute() else repo / args.report
    document = run_benchmark(repo, args.repetitions)
    guarded_atomic_write_json(repo, report, document, repo / "artifacts" / "tmp")
    print(json.dumps(document, ensure_ascii=True, sort_keys=True))
    return 0 if document["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
