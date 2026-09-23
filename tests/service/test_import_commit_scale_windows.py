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
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_observatory_core.import_commit_repository import SqliteImportCommitRepository
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.storage import open_canonical_database

from tests.service import test_import_review_scale_windows as scale


class _CommitObservation:
    """Content-free, bounded phase counters; only the observing thread writes reports."""

    def __init__(self):
        self._lock = threading.Lock()
        self._phases = {}

    @contextmanager
    def phase(self, name):
        started = time.monotonic()
        with self._lock:
            phase = self._phases.setdefault(name, {"entered": 0, "exited": 0, "totalSeconds": 0.0})
            phase["entered"] += 1
            phase["active"] = True
        try:
            yield
        except BaseException as error:
            with self._lock:
                phase["lastFailureType"] = type(error).__name__
            raise
        finally:
            with self._lock:
                phase["exited"] += 1
                phase["active"] = False
                phase["totalSeconds"] += time.monotonic() - started

    def snapshot(self):
        with self._lock:
            return {name: dict(phase) for name, phase in self._phases.items()}

    def wrap(self, name, operation):
        def measured(*args, **kwargs):
            with self.phase(name):
                return operation(*args, **kwargs)

        return measured


def _observe_job(report, job):
    report["lastJob"] = {
        "state": job.state,
        "attemptCount": job.attempt_count,
        "diagnosticCode": job.diagnostic_code,
        "interruptionKind": job.interruption_kind,
    }
    if job.attempt_count > 1:
        report["retryObserved"] = True
        raise AssertionError("worker retry observed; this diagnostic did not prevent the production retry")


def _wait_commit(h, job_id, observation, *, timeout):
    queue = scale.sqlite_workflow_queue_repository(h.project_root, h.project_id)
    deadline, next_report = time.monotonic() + timeout, 0.0
    while time.monotonic() < deadline:
        job = queue.get(job_id)
        h.report["commitPhases"] = observation.snapshot()
        _observe_job(h.report, job)
        if job.state in {"succeeded", "failed", "cancelled"}:
            h.assertEqual("succeeded", job.state, "commit worker did not succeed; see diagnostic")
            return
        if time.monotonic() >= next_report:
            h._save()
            print(
                json.dumps(
                    {"state": job.state, "attempt": job.attempt_count, "commitPhases": h.report["commitPhases"]}
                ),
                flush=True,
            )
            next_report = time.monotonic() + 5
        time.sleep(0.5)
    h.fail("commit observation deadline elapsed; product deadlines were not modified")


def _commit_facts(database, project_id):
    with open_canonical_database(database, expected_project_id=project_id) as db:
        return {
            "counts": {
                name: db.execute(f"SELECT COUNT(*) FROM {name} WHERE project_id=?", (project_id,)).fetchone()[0]
                for name in (
                    "import_commit_rows",
                    "import_source_records",
                    "import_manifests",
                    "import_manifest_members",
                    "import_manifest_seals",
                )
            },
            "acceptedCommitOutputs": db.execute(
                "SELECT COUNT(*) FROM workflow_committed_outputs o JOIN workflow_queue_jobs j "
                "ON j.project_id=o.project_id AND j.job_id=o.job_id "
                "WHERE o.project_id=? AND j.activity_type='local-import-commit'",
                (project_id,),
            ).fetchone()[0],
            "attempts": [
                {"attempt": row[0], "state": row[1], "diagnosticCode": row[2]}
                for row in db.execute(
                    "SELECT a.attempt_number,a.state,a.diagnostic_code FROM workflow_job_attempts a "
                    "JOIN workflow_queue_jobs j ON j.project_id=a.project_id AND j.job_id=a.job_id "
                    "WHERE a.project_id=? AND j.activity_type='local-import-commit' ORDER BY j.rowid,a.attempt_number",
                    (project_id,),
                )
            ],
        }


class ImportCommitDiagnosticReportingTests(unittest.TestCase):
    def test_writer_entry_is_visible_before_completion_and_failure_is_preserved(self):
        observation = _CommitObservation()
        with self.assertRaises(ValueError), observation.phase("atomic-publication"):
            during = observation.snapshot()["atomic-publication"]
            self.assertEqual((1, 0, True), (during["entered"], during["exited"], during["active"]))
            raise ValueError("synthetic failure")
        after = observation.snapshot()["atomic-publication"]
        self.assertEqual((1, 1, False), (after["entered"], after["exited"], after["active"]))
        self.assertEqual("ValueError", after["lastFailureType"])
        self.assertGreaterEqual(after["totalSeconds"], 0)

    def test_success_on_a_retry_cannot_hide_the_first_attempt_failure(self):
        report = {}
        job = SimpleNamespace(state="succeeded", attempt_count=2, diagnostic_code=None, interruption_kind=None)
        with self.assertRaisesRegex(AssertionError, "retry observed"):
            _observe_job(report, job)
        self.assertTrue(report["retryObserved"])
        self.assertEqual(2, report["lastJob"]["attemptCount"])

    def test_commit_facts_do_not_count_the_parser_receipt_as_a_commit(self):
        from tests.data import test_import_commit_publication as publication

        case = publication.ImportCommitPublicationTests(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        f = case.fixture
        before = _commit_facts(f.database, f.inputs.project_id)
        self.assertEqual(0, before["acceptedCommitOutputs"])
        case.publish()
        after = _commit_facts(f.database, f.inputs.project_id)
        self.assertEqual(1, after["acceptedCommitOutputs"])
        self.assertEqual(
            (1, 1, 2, 1),
            tuple(
                after["counts"][name]
                for name in (
                    "import_source_records",
                    "import_manifests",
                    "import_manifest_members",
                    "import_manifest_seals",
                )
            ),
        )
        self.assertEqual([{"attempt": 1, "state": "succeeded", "diagnosticCode": None}], after["attempts"])


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
            "commitPhases": {},
            "retryObserved": False,
            "observationBudgetSeconds": 1200,
        }
        observation = _CommitObservation()
        h._save()
        try:
            with (
                patch.object(
                    SqliteImportCommitRepository,
                    "_publish_verified",
                    observation.wrap("atomic-publication", SqliteImportCommitRepository._publish_verified),
                ),
                patch.object(
                    SqliteImportCommitRepository,
                    "_verified_identity",
                    observation.wrap("identity-verification", SqliteImportCommitRepository._verified_identity),
                ),
                patch.object(
                    SqliteImportCommitRepository,
                    "append_commit_page",
                    observation.wrap("staging-pages", SqliteImportCommitRepository.append_commit_page),
                ),
                h._client() as client,
            ):
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
                    _wait_commit(h, scheduled["jobId"], observation, timeout=900)
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
            h.report["commitPhases"] = observation.snapshot()
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
                if h.project_root is not None:
                    h.report["commitFacts"] = _commit_facts(h.project_root / "state/project.sqlite3", h.project_id)
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
