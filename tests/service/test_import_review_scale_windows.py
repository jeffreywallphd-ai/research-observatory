"""Opt-in real-DPAPI/SQLCipher 100k import diagnostic; no ordinary profile access.

Run with RO_RUN_IMPORT_REVIEW_SCALE=1 and the Core source on PYTHONPATH.
Uses production composition/worker/deadlines. ASGI transport, native workflow
context, source bytes, project and vault are explicit fixture substitutions.
Measurements are not a reviewed performance baseline, packaged execution,
native dialog/session proof, or whole-task qualification. Fixtures and
content-free reports are retained in one fresh ignored directory for inspection.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ingestion.reference_imports import ImportLimits
from research_observatory_core.main import create_runtime_app
from research_observatory_core.repositories import sqlite_workflow_queue_repository
from research_observatory_core.storage import open_canonical_database

REPO = Path(__file__).resolve().parents[2]
RECORDS = 100_000
CHUNK_BYTES = 128 * 1024
RESPONSE_BYTES = 900_000


class _ProcessMemory(ctypes.Structure):
    # Same Windows PROCESS_MEMORY_COUNTERS_EX layout used by the sidecar tool.
    _fields_ = [("cb", ctypes.c_ulong), ("pageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t)
        for name in (
            "peakWorkingSetSize",
            "workingSetSize",
            "quotaPeakPagedPoolUsage",
            "quotaPagedPoolUsage",
            "quotaPeakNonPagedPoolUsage",
            "quotaNonPagedPoolUsage",
            "pagefileUsage",
            "peakPagefileUsage",
            "privateUsage",
        )
    ]


def _memory() -> dict[str, int]:
    counters = _ProcessMemory()
    counters.cb = ctypes.sizeof(counters)
    query = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    query.argtypes = (ctypes.c_void_p, ctypes.POINTER(_ProcessMemory), ctypes.c_ulong)
    query.restype = ctypes.c_int
    if not query(ctypes.c_void_p(-1), ctypes.byref(counters), counters.cb):
        raise RuntimeError("process-memory-unavailable")
    return {name: int(getattr(counters, name)) for name in ("workingSetSize", "peakWorkingSetSize", "privateUsage")}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inputs() -> dict[str, str]:
    paths = subprocess.check_output(
        ["git", "ls-files", "--", "services/core-api/src", "packages/contracts", "pyproject.toml", "uv.lock"],
        cwd=REPO,
        text=True,
        encoding="utf-8",
    ).splitlines()
    paths.append(Path(__file__).resolve().relative_to(REPO).as_posix())
    return {name: _digest(REPO / name) for name in sorted(set(paths))}


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def _chunks() -> Iterator[bytes]:
    # Repeated synthetic rows exercise one giant raw/DOI candidate group. No
    # source file or complete source/result list is materialized by this runner.
    pending = bytearray(b"title,doi\n")
    row = b"Synthetic scale record,10.99999/scale-fixture\n"
    for _ in range(RECORDS):
        pending.extend(row)
        if len(pending) >= CHUNK_BYTES:
            yield bytes(pending[:CHUNK_BYTES])
            del pending[:CHUNK_BYTES]
    if pending:
        yield bytes(pending)


@unittest.skipUnless(
    os.name == "nt" and os.environ.get("RO_RUN_IMPORT_REVIEW_SCALE") == "1",
    "opt-in current-Windows-principal protected import scale diagnostic",
)
class ImportReviewScaleWindowsTests(unittest.TestCase):
    def test_real_protected_100k_import_summary_paging_and_reopen(self) -> None:
        scratch = REPO / "artifacts/tmp"
        self.assertTrue(scratch.is_dir() and not scratch.is_symlink() and not scratch.is_junction())
        self.assertEqual(scratch.absolute(), scratch.resolve(strict=True))
        fixture = Path(tempfile.mkdtemp(prefix="import-review-scale-windows-", dir=scratch))
        self.assertEqual(scratch, fixture.resolve(strict=True).parent)
        self.vault = fixture / "vault"
        self.vault.mkdir()
        projects = fixture / "projects"
        projects.mkdir()
        self.report_path = fixture / "diagnostic.json"
        self.started = time.monotonic()
        self.stage = "setup"
        self.project_root: Path | None = None
        self.project_id: str | None = None
        self.report: dict[str, Any] = {
            "documentType": "import-review-scale-windows-diagnostic",
            "schemaVersion": "1.0",
            "task": "CAP-04.S01.T02",
            "performanceQualifying": False,
            "observationBudgetsSeconds": {"parse": 180, "summary": 360, "overall": 1200},
            "outcome": "running",
            "startedAt": datetime.now(UTC).isoformat(),
            "headBefore": _head(),
            "sourceHashesBefore": _inputs(),
            "fixtureVersion": "repeated-synthetic-csv-v1",
            "bibliographicRecords": RECORDS,
            "parserDefaults": {"maxSeconds": ImportLimits().max_seconds, "maxRecords": ImportLimits().max_records},
            "fixtureSubstitutions": [
                "ASGI transport",
                "native workflow context",
                "capability token",
                "source bytes",
                "project directory",
                "explicit profile vault directory",
            ],
            "realBoundaries": [
                "current-Windows-user DPAPI",
                "SQLCipher",
                "local actor vault",
                "encrypted object store",
                "production Core composition",
                "durable worker",
            ],
            "limitations": [
                "not native-window/dialog/session proof",
                "not packaged execution",
                "no reviewed latency or process-memory baseline",
                "no evidence reuse",
            ],
            "fixtureDirectory": fixture.relative_to(REPO).as_posix(),
            "fixturesRetained": True,
            "platform": {
                "system": platform.platform(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "logicalCpuCount": os.cpu_count(),
            },
            "runtime": {
                "pythonExecutableSha256": _digest(Path(sys.executable)),
                "dependencies": {
                    name: importlib.metadata.version(name)
                    for name in ("fastapi", "starlette", "pydantic", "sqlcipher3", "pynacl", "uvicorn")
                },
            },
            "memoryScope": "current process including production Core, ASGI client and test runner; no tracemalloc",
            "memoryBaseline": _memory(),
            "memoryMaxObserved": {},
            "stages": {},
            "requests": {},
        }
        self.capability = secrets.token_hex(32)
        self.epoch = secrets.token_hex(16)
        self._save()
        try:
            with self._client() as client:
                with self._stage("project-create-open"):
                    created = self._post(
                        client,
                        "/projects",
                        {
                            "parentDirectory": str(projects),
                            "directoryName": "synthetic-scale",
                            "displayName": "Synthetic scale",
                            "primaryUseCase": "theory-synthesis",
                            "researchObjective": "Synthetic bibliography scale diagnostic",
                        },
                    )
                    self.project_root = Path(created["root"])
                    self.project_id = created["projectId"]
                    self.assertEqual(projects, self.project_root.parent)
                    self._post(client, "/projects/open", {"root": str(self.project_root)})
                    project = {"root": str(self.project_root), "projectId": self.project_id}
                    context = {**project, **self._post(client, "/native/imports/context", project)}
                    canonical_before = self._facts()["canonicalRecords"]
                    self.assertEqual(0, canonical_before)
                with self._stage("streaming-intake"):
                    granted = ImportPermission(value="permitted", basis="researcher-confirmed")
                    rights = ImportRights(store=granted, inspect=granted)
                    created = self._post(
                        client,
                        "/native/imports/create",
                        {
                            **context,
                            "sourceName": "synthetic-scale.csv",
                            "formatName": "csv",
                            "encoding": "utf-8",
                            "delimiter": ",",
                            "rights": rights.model_dump(by_alias=True),
                        },
                    )
                    preview = created["previewId"]
                    native = {**context, "previewId": preview}
                    public = {"root": str(self.project_root), "previewId": preview}
                    digest, byte_length, chunk_count = hashlib.sha256(), 0, 0
                    for chunk_count, chunk in enumerate(_chunks(), 1):
                        digest.update(chunk)
                        byte_length += len(chunk)
                        self._post(
                            client,
                            "/native/imports/chunk",
                            {
                                **native,
                                "ordinal": chunk_count,
                                "data": base64.b64encode(chunk).decode("ascii"),
                            },
                        )
                    self._post(
                        client,
                        "/native/imports/seal",
                        {
                            **native,
                            "sourceSha256": digest.hexdigest(),
                            "byteLength": byte_length,
                            "chunkCount": chunk_count,
                        },
                    )
                    self.report["source"] = {
                        "byteLength": byte_length,
                        "chunks": chunk_count,
                        "sha256": digest.hexdigest(),
                    }
                with self._stage("parse-worker"):
                    scheduled = self._post(client, "/native/imports/schedule", native)
                    self._wait_job(scheduled["jobId"], timeout=180)
                    status = self._post(client, "/native/imports/status", native)
                    self.assertEqual("succeeded", status["jobState"])
                    review = self._post(client, "/projects/imports/begin-review", public)
                    self.assertEqual(RECORDS + 1, review["recordCount"])
                    revision = review["revision"]
                    summary_address = {**public, "revision": revision}
                with self._stage("summary-worker"):
                    scheduled = self._post(client, "/projects/imports/summary/start", summary_address)
                    self._wait_job(scheduled["jobId"], timeout=360)
                    summary = self._post(client, "/projects/imports/summary", summary_address)
                    counts = summary["counts"]
                    self.assertEqual("succeeded", summary["jobState"])
                    for name, expected in {
                        "sourceRows": RECORDS + 1,
                        "recordRows": RECORDS,
                        "contextRows": 1,
                        "includedRecords": RECORDS,
                        "malformedRows": 0,
                        "excludedRecords": 0,
                        "candidateRecords": RECORDS,
                        "rawDuplicateGroups": 1,
                        "doiDuplicateGroups": 1,
                    }.items():
                        self.assertEqual(expected, counts[name], name)
                    self.assertEqual(RECORDS, counts["coverage"]["title"])
                    self.assertEqual(RECORDS, counts["coverage"]["doi"])
                    self.report["summaryCounts"] = counts
                with self._stage("review-pages"):
                    self._pages(client, "/projects/imports/records", summary_address, start=1, count=RECORDS + 1)
                with self._stage("duplicate-group-pages"):
                    for reason in ("raw", "doi"):
                        groups = self._post(
                            client,
                            "/projects/imports/summary/groups",
                            {
                                **summary_address,
                                "reason": reason,
                                "after": None,
                                "limit": 100,
                            },
                        )
                        self.assertTrue(groups["complete"])
                        self.assertEqual(1, len(groups["groups"]))
                        self.assertEqual(RECORDS, groups["groups"][0]["memberCount"])
                        if reason == "doi":
                            self._pages(
                                client,
                                "/projects/imports/summary/members",
                                {
                                    **summary_address,
                                    "reason": reason,
                                    "groupKey": groups["groups"][0]["groupKey"],
                                },
                                start=2,
                                count=RECORDS,
                            )
                with self._stage("close-original-runtime"):
                    self._post(client, "/projects/close", {"root": str(self.project_root)})
            with self._stage("fresh-runtime-reopen"), self._client() as client:
                self._post(client, "/projects/open", {"root": str(self.project_root)})
                reopened = self._post(client, "/projects/imports/summary", summary_address)
                self.assertEqual(counts, reopened["counts"])
                self.assertEqual("succeeded", reopened["jobState"])
                last = self._post(
                    client,
                    "/projects/imports/records",
                    {
                        **summary_address,
                        "after": RECORDS,
                        "limit": 100,
                    },
                )
                self.assertTrue(last["complete"])
                self.assertEqual(RECORDS + 1, last["nextAfter"])
                self.assertEqual(1, len(last["records"]))
                self.assertEqual(canonical_before, self._facts()["canonicalRecords"])
                self._post(client, "/projects/close", {"root": str(self.project_root)})
            self.report["outcome"] = "functional-checks-passed-performance-diagnostic-only"
        except BaseException as error:
            self.report.update(outcome="failed", failedStage=self.stage, failureType=type(error).__name__)
            raise
        finally:
            self.report["elapsedSeconds"] = time.monotonic() - self.started
            self.report["headAfter"] = _head()
            self.report["sourceHashesAfter"] = _inputs()
            self.report["sourceInputsUnchanged"] = self.report["sourceHashesBefore"] == self.report["sourceHashesAfter"]
            self.report["headUnchanged"] = self.report["headBefore"] == self.report["headAfter"]
            if not self.report["sourceInputsUnchanged"]:
                self.report["outcome"] = "failed-input-drift"
            try:
                self.report["durableFacts"] = self._facts()
            except Exception as error:
                self.report["durableFactsUnavailable"] = type(error).__name__
            self._save()
            print(
                json.dumps(
                    {
                        key: self.report[key]
                        for key in (
                            "outcome",
                            "fixtureDirectory",
                            "elapsedSeconds",
                            "sourceInputsUnchanged",
                            "headUnchanged",
                        )
                    }
                ),
                flush=True,
            )
        self.assertTrue(self.report["sourceInputsUnchanged"], "backend inputs changed during diagnostic")

    def _client(self) -> TestClient:
        app = create_runtime_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(self.capability),
            expected_authority="127.0.0.1:49152",
            profile_vault_root=self.vault,
            workflow_context=NativeWorkflowContext(self.epoch, secrets.token_hex(16)),
        )
        return TestClient(
            app,
            base_url="http://127.0.0.1:49152",
            headers={"Authorization": "Bearer " + self.capability},
            client=("127.0.0.1", 50000),
        )

    def _save(self) -> None:
        observed = _memory()
        for key, value in observed.items():
            self.report["memoryMaxObserved"][key] = max(value, self.report["memoryMaxObserved"].get(key, 0))
        self.report_path.write_text(json.dumps(self.report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @contextmanager
    def _stage(self, name: str) -> Iterator[None]:
        self.stage = name
        started = time.monotonic()
        self.report["stages"][name] = {"state": "running"}
        self._save()
        print(json.dumps({"stage": name, "state": "running"}), flush=True)
        try:
            yield
        except BaseException:
            self.report["stages"][name]["state"] = "failed"
            raise
        else:
            self.report["stages"][name]["state"] = "passed"
        finally:
            self.report["stages"][name]["seconds"] = time.monotonic() - started
            self._save()

    def _post(self, client: TestClient, route: str, body: dict[str, Any]) -> dict[str, Any]:
        self.assertLess(time.monotonic() - self.started, 1200, "diagnostic observation budget exhausted")
        started = time.monotonic()
        response = client.post(route, json=body)
        elapsed = time.monotonic() - started
        metric = self.report["requests"].setdefault(route, {"count": 0, "maxSeconds": 0.0, "maxBytes": 0})
        metric["count"] += 1
        metric["maxSeconds"] = max(metric["maxSeconds"], elapsed)
        metric["maxBytes"] = max(metric["maxBytes"], len(response.content))
        if response.status_code != 200:
            self.report["httpFailure"] = {"route": route, "status": response.status_code}
        self.assertEqual(200, response.status_code, f"bounded request failed: {route}")
        if "imports" in route:
            self.assertLessEqual(len(response.content), RESPONSE_BYTES)
        return response.json()

    def _wait_job(self, job_id: str, *, timeout: int) -> None:
        assert self.project_root is not None and self.project_id is not None
        queue = sqlite_workflow_queue_repository(self.project_root, self.project_id)
        deadline, next_report = time.monotonic() + timeout, 0.0
        while time.monotonic() < deadline:
            job = queue.get(job_id)
            self.report["lastJob"] = {
                "state": job.state,
                "attemptCount": job.attempt_count,
                "diagnosticCode": job.diagnostic_code,
                "interruptionKind": job.interruption_kind,
            }
            if job.state in {"succeeded", "failed", "cancelled"}:
                self.assertEqual("succeeded", job.state, "worker did not succeed; see content-free diagnostic")
                return
            if time.monotonic() >= next_report:
                self._save()
                next_report = time.monotonic() + 5
            time.sleep(0.5)
        self.fail("worker observation deadline elapsed; product deadlines were not modified")

    def _pages(self, client: TestClient, route: str, address: dict[str, Any], *, start: int, count: int) -> None:
        after, observed, pages = 0, 0, 0
        while True:
            page = self._post(client, route, {**address, "after": after, "limit": 100})
            rows = page["records"]
            self.assertTrue(rows)
            self.assertLessEqual(len(rows), 100)
            for row in rows:
                self.assertEqual(start + observed, row["ordinal"])
                observed += 1
            self.assertEqual(rows[-1]["ordinal"], page["nextAfter"])
            self.assertGreater(page["nextAfter"], after)
            after = page["nextAfter"]
            pages += 1
            if pages % 25 == 0:
                self._save()
            if page["complete"]:
                break
        self.assertEqual(count, observed)
        self.report.setdefault("pageCoverage", {})[route] = {"pages": pages, "records": observed, "complete": True}

    def _facts(self) -> dict[str, Any]:
        if self.project_root is None or self.project_id is None:
            return {"projectCreated": False}
        database = self.project_root / "state/project.sqlite3"
        with database.open("rb") as source:
            encrypted = source.read(16) != b"SQLite format 3\x00"
        self.assertTrue(encrypted)
        with open_canonical_database(database, expected_project_id=self.project_id) as connection:
            return {
                "encryptedHeader": encrypted,
                "canonicalRecords": connection.execute("SELECT COUNT(*) FROM scholarly_records").fetchone()[0],
                "parseRows": connection.execute("SELECT COUNT(*) FROM import_parse_records").fetchone()[0],
                "summaryRows": connection.execute("SELECT COUNT(*) FROM import_summary_rows").fetchone()[0],
                "summaryCompletions": connection.execute("SELECT COUNT(*) FROM import_summary_completions").fetchone()[
                    0
                ],
                "acceptedOutputs": connection.execute("SELECT COUNT(*) FROM workflow_committed_outputs").fetchone()[0],
            }


if __name__ == "__main__":
    unittest.main(verbosity=2)
