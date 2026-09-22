"""Opt-in protected commit diagnostic; no native/packaged or baseline claim.

RO_RUN_IMPORT_COMMIT_SCALE=1 runs 100k synthetic records, or use
RO_IMPORT_COMMIT_RECORDS=1000 for a pilot. No production deadlines are patched.
Retains the isolated vault/project/report under ignored artifacts/tmp. Reuses
only the prior scale runner's helpers, not its completed summary test suite.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.import_commit_repository import SqliteImportCommitRepository
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.storage import open_canonical_database

from tests.service import test_import_review_scale_windows as scale


@unittest.skipUnless(
    os.name == "nt" and os.environ.get("RO_RUN_IMPORT_COMMIT_SCALE") == "1",
    "opt-in current-Windows-principal protected commit diagnostic",
)
class ImportCommitScaleWindowsTests(unittest.TestCase):
    def test_protected_commit_manifest_pages_replay_and_reopen(self):
        count = int(os.environ.get("RO_IMPORT_COMMIT_RECORDS", "100000"))
        self.assertIn(count, (1000, 100000))
        scratch = scale.REPO / "artifacts/tmp"
        self.assertTrue(scratch.is_dir() and not scratch.is_symlink() and not scratch.is_junction())
        self.assertEqual(scratch.absolute(), scratch.resolve(strict=True))
        fixture = Path(tempfile.mkdtemp(prefix="import-commit-scale-windows-", dir=scratch))
        h = scale.ImportReviewScaleWindowsTests(methodName="runTest")
        self.addCleanup(h.doCleanups)
        h.vault = fixture / "vault"
        h.vault.mkdir()
        projects = fixture / "projects"
        projects.mkdir()
        h.report_path = fixture / "diagnostic.json"
        h.started, h.stage = time.monotonic(), "setup"
        h.project_root = h.project_id = None
        h.capability, h.epoch = secrets.token_hex(32), secrets.token_hex(16)
        inputs = scale._inputs()
        inputs[Path(__file__).relative_to(scale.REPO).as_posix()] = scale._digest(Path(__file__))
        h.report = {
            "documentType": "import-commit-scale-windows-diagnostic",
            "schemaVersion": "1.0",
            "task": "CAP-04.S01.T03",
            "performanceQualifying": False,
            "outcome": "running",
            "headBefore": scale._head(),
            "sourceHashesBefore": inputs,
            "fixtureVersion": "repeated-synthetic-csv-v1",
            "bibliographicRecords": count,
            "fixtureDirectory": fixture.relative_to(scale.REPO).as_posix(),
            "fixturesRetained": True,
            "platform": {
                "system": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "logicalCpuCount": os.cpu_count(),
                "python": platform.python_version(),
            },
            "realBoundaries": ["current-user DPAPI", "SQLCipher", "Core composition", "durable worker"],
            "limitations": ["ASGI transport", "synthetic native context", "not packaged", "no reviewed baseline"],
            "memoryScope": "Core plus ASGI test runner in this process; no tracemalloc",
            "memoryBaseline": scale._memory(),
            "memoryMaxObserved": {},
            "stages": {},
            "requests": {},
            "writerSamplesSeconds": [],
            "observationBudgetSeconds": 1200,
        }
        writer = SqliteImportCommitRepository._publish_verified

        def timed_writer(*args, **kwargs):
            started = time.monotonic()
            try:
                return writer(*args, **kwargs)
            finally:
                h.report["writerSamplesSeconds"].append(time.monotonic() - started)

        h._save()
        try:
            with patch.object(SqliteImportCommitRepository, "_publish_verified", timed_writer), h._client() as client:
                with h._stage("project-and-intake"):
                    created = h._post(
                        client,
                        "/projects",
                        {
                            "parentDirectory": str(projects),
                            "directoryName": "synthetic-commit",
                            "displayName": "Synthetic commit",
                            "primaryUseCase": "theory-synthesis",
                            "researchObjective": "Synthetic import commit diagnostic",
                        },
                    )
                    h.project_root, h.project_id = Path(created["root"]), created["projectId"]
                    self.assertEqual(projects, h.project_root.parent)
                    h._post(client, "/projects/open", {"root": str(h.project_root)})
                    project = {"root": str(h.project_root), "projectId": h.project_id}
                    context = {**project, **h._post(client, "/native/imports/context", project)}
                    granted = ImportPermission(value="permitted", basis="researcher-confirmed")
                    created = h._post(
                        client,
                        "/native/imports/create",
                        {
                            **context,
                            "sourceName": "synthetic-commit.csv",
                            "formatName": "csv",
                            "encoding": "utf-8",
                            "delimiter": ",",
                            "rights": ImportRights(store=granted, inspect=granted).model_dump(by_alias=True),
                        },
                    )
                    preview = created["previewId"]
                    native = {**context, "previewId": preview}
                    public = {"root": str(h.project_root), "previewId": preview}
                    digest, length, chunks = hashlib.sha256(), 0, 0
                    pending = bytearray(b"title,doi\n")

                    def append(data):
                        nonlocal length, chunks
                        chunks += 1
                        length += len(data)
                        digest.update(data)
                        h._post(
                            client,
                            "/native/imports/chunk",
                            {
                                **native,
                                "ordinal": chunks,
                                "data": base64.b64encode(data).decode("ascii"),
                            },
                        )

                    for _ in range(count):
                        pending.extend(b"Synthetic scale record,10.99999/scale-fixture\n")
                        if len(pending) >= scale.CHUNK_BYTES:
                            append(bytes(pending[: scale.CHUNK_BYTES]))
                            del pending[: scale.CHUNK_BYTES]
                    if pending:
                        append(bytes(pending))
                    h._post(
                        client,
                        "/native/imports/seal",
                        {
                            **native,
                            "sourceSha256": digest.hexdigest(),
                            "byteLength": length,
                            "chunkCount": chunks,
                        },
                    )
                    h.report["source"] = {"sha256": digest.hexdigest(), "byteLength": length, "chunks": chunks}
                with h._stage("parse-prerequisite"):
                    scheduled = h._post(client, "/native/imports/schedule", native)
                    h._wait_job(scheduled["jobId"], timeout=180)
                    review = h._post(client, "/projects/imports/begin-review", public)
                    self.assertEqual(count + 1, review["recordCount"])
                with h._stage("commit-worker"):
                    prepared = h._post(
                        client, "/projects/imports/commit/prepare", {**public, "revision": review["revision"]}
                    )
                    request = {**public, "requestId": prepared["requestId"], "revision": review["revision"]}
                    scheduled = h._post(client, "/projects/imports/commit/start", request)
                    h._wait_job(scheduled["jobId"], timeout=900)
                with h._stage("cold-manifest-and-warm-pages"):
                    status = h._post(
                        client,
                        "/projects/imports/commit/status",
                        {
                            **public,
                            "requestId": prepared["requestId"],
                        },
                    )
                    manifest = status["manifest"]
                    self.assertEqual(count, manifest["createdCount"])
                    self.assertEqual(count, manifest["selectedCount"])
                    self.assertEqual(count + 1, manifest["recordCount"])
                    h._pages(
                        client,
                        "/projects/imports/manifest/members",
                        {
                            **public,
                            "revisionId": manifest["revisionId"],
                        },
                        start=1,
                        count=count + 1,
                    )
                with h._stage("request-replay"):
                    replay = h._post(client, "/projects/imports/commit/start", request)
                    self.assertEqual(manifest, replay["manifest"])
                    h._post(client, "/projects/close", {"root": str(h.project_root)})
            with h._stage("fresh-runtime-reopen"), h._client() as client:
                h._post(client, "/projects/open", {"root": str(h.project_root)})
                latest = h._post(client, "/projects/imports/commit/latest", public)
                self.assertEqual(manifest, latest["manifest"])
                page = h._post(
                    client,
                    "/projects/imports/manifest/members",
                    {
                        **public,
                        "revisionId": manifest["revisionId"],
                        "after": count,
                        "limit": 100,
                    },
                )
                self.assertTrue(page["complete"])
                self.assertEqual(count + 1, page["nextAfter"])
                with open_canonical_database(
                    h.project_root / "state/project.sqlite3", expected_project_id=h.project_id
                ) as db:
                    self.assertEqual(count, db.execute("SELECT COUNT(*) FROM import_source_records").fetchone()[0])
                    self.assertEqual(1, db.execute("SELECT COUNT(*) FROM import_manifests").fetchone()[0])
                h._post(client, "/projects/close", {"root": str(h.project_root)})
            h.report["outcome"] = "functional-checks-passed-performance-diagnostic-only"
        except BaseException as error:
            h.report.update(outcome="failed", failedStage=h.stage, failureType=type(error).__name__)
            raise
        finally:
            h.report["elapsedSeconds"] = time.monotonic() - h.started
            h.report["headAfter"] = scale._head()
            after = scale._inputs()
            after[Path(__file__).relative_to(scale.REPO).as_posix()] = scale._digest(Path(__file__))
            h.report["sourceInputsUnchanged"] = inputs == after
            h.report["headUnchanged"] = h.report["headBefore"] == h.report["headAfter"]
            if not h.report["sourceInputsUnchanged"] or not h.report["headUnchanged"]:
                h.report["outcome"] = "failed-input-drift"
            try:
                h.report["durableFacts"] = h._facts()
            except Exception as error:
                h.report["durableFactsUnavailable"] = type(error).__name__
            h._save()
            print(
                json.dumps(
                    {
                        key: h.report[key]
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
        self.assertTrue(h.report["sourceInputsUnchanged"])
        self.assertTrue(h.report["headUnchanged"])
