"""Content-free CAP-04.S03 kernel and protected-project benchmark samples.

The project input is synthetic. Setup uses an ASGI/native-context fixture and
synthetic Crossref transport; the measured batch uses the actual Windows
DPAPI/SQLCipher owner, queue, source authority and worker admission.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.main import create_runtime_app
from research_observatory_core.reconciliation import candidates
from research_observatory_core.reconciliation.candidate_sets import CandidateExplanation, content_digest
from research_observatory_core.storage import open_canonical_database

from tests.reconciliation.duplicate_benchmark import load_split, metrics
from tests.reconciliation.native_fixture import prepare
from tests.service import test_import_preview_service as runtime_fixture


def _kernel() -> dict:
    records, gold = load_split("qualification")
    if len(records) != 2463:
        raise AssertionError("frozen qualification corpus size differs")
    start = time.perf_counter()
    cold = candidates.generate_candidates(records)
    cold_seconds = time.perf_counter() - start
    start = time.perf_counter()
    prepared = tuple(candidates.prepare_record(item) for item in records)
    preparation_seconds = time.perf_counter() - start
    start = time.perf_counter()
    warm = candidates.generate_prepared_candidates(prepared)
    prepared_retrieval_seconds = time.perf_counter() - start
    if cold != warm or cold.compared_pairs != 105451 or cold.record_count != len(records):
        raise AssertionError("frozen kernel comparison or prepared equivalence differs")
    predicted = frozenset(
        (item.left, item.right) for item in cold.pairs if item.left.split(":", 1)[0] != item.right.split(":", 1)[0]
    )
    result = metrics(frozenset(item.key for item in records), predicted, gold)
    if not (
        result["precision"] >= 0.90
        and result["recall"] >= 0.95
        and (result["truePositives"], result["returnedPairs"], result["goldPairs"]) == (1092, 1142, 1115)
    ):
        raise AssertionError("frozen retrieval accuracy differs")
    return {
        "fixtureVersion": "dblp-acm-benchmark-v1/qualification",
        "records": len(records),
        "comparisons": cold.compared_pairs,
        "returnedPairs": len(cold.pairs),
        "crossSourceReturnedPairs": len(predicted),
        "truePositives": result["truePositives"],
        "goldPairs": result["goldPairs"],
        "precision": result["precision"],
        "recall": result["recall"],
        "preparedEquivalent": True,
        "coldSeconds": cold_seconds,
        "preparationSeconds": preparation_seconds,
        "preparedRetrievalSeconds": prepared_retrieval_seconds,
    }


def _run_batch(post, service, phase: str) -> dict:
    observer = (
        patch("research_observatory_core.reconciliation.feature_cache.prepare_record", wraps=candidates.prepare_record)
        if phase == "warm"
        else None
    )
    started = time.perf_counter()

    def finish(request, job):
        deadline = started + 120
        while True:
            service.run_pending()
            status = post("batches/status", requestId=request, jobId=job)
            if status["state"] not in ("runnable", "running"):
                return status
            if time.perf_counter() >= deadline:
                raise AssertionError("protected batch did not reach terminal status within 120 seconds")
            time.sleep(0.1)

    if observer is None:
        request = post("batches/prepare")["requestId"]
        job = post("batches/schedule", requestId=request)["jobId"]
        status = finish(request, job)
        computations = None
    else:
        with observer as compute:
            request = post("batches/prepare")["requestId"]
            job = post("batches/schedule", requestId=request)["jobId"]
            status = finish(request, job)
            computations = compute.call_count
    elapsed = time.perf_counter() - started
    if status["state"] != "succeeded" or status["setRevisionId"] is None:
        raise AssertionError("protected batch did not publish a succeeded candidate set")
    if phase == "warm" and computations != 0:
        raise AssertionError("warm batch recomputed revision-bound features")
    return {
        "phase": phase,
        "seconds": elapsed,
        "requestId": request,
        "jobId": job,
        "setRevisionId": status["setRevisionId"],
        "featureComputations": computations,
    }


def _verify_page_digests(pages: tuple[tuple[int, tuple[str, ...]], ...], expected: tuple[str, ...]) -> str:
    if not expected or len(expected) != len(set(expected)):
        raise AssertionError("candidate page expected identity inventory differs")
    offset = 0
    for after, digests in pages:
        if after != offset or not digests or len(digests) > 100 or digests != expected[after : after + len(digests)]:
            raise AssertionError("candidate page differs from durable ordinal content")
        offset += len(digests)
    if offset != len(expected):
        raise AssertionError("candidate page inventory incomplete")
    return hashlib.sha256("".join(expected).encode()).hexdigest()


def _protected(directory: Path) -> dict:
    project = prepare(directory, records=202)
    root = project["root"]
    app = create_runtime_app(
        settings=CoreSettings(),
        profile_vault_root=directory / "vault",
        workflow_context=NativeWorkflowContext("d" * 32, "c" * 32),
        capability_digest=capability_token_digest("a" * 64),
        expected_authority="127.0.0.1:49152",
    )
    helper = runtime_fixture.ImportRuntimeCompositionTests()

    def post(client, route: str, **body):
        response = client.post("/projects/reconciliation/" + route, json={"root": root, **body})
        if response.status_code != 200:
            raise AssertionError(f"protected benchmark request failed: {route} {response.status_code}")
        return response.json()

    with helper.client(app) as client:
        opened = client.post("/projects/open", json={"root": root})
        if opened.status_code != 200:
            raise AssertionError("protected project reopen failed")
        runtime = app.state.runtime
        service = runtime.reconciliation
        if service is None:
            raise AssertionError("reconciliation service unavailable")
        provider_dispatches = []

        def unexpected_provider():
            provider_dispatches.append(True)
            raise AssertionError("batch attempted provider transport")

        runtime.connectors._transport_factory = unexpected_provider
        samples = [
            _run_batch(lambda route, **body: post(client, route, **body), service, phase) for phase in ("cold", "warm")
        ]
        if len({item["requestId"] for item in samples}) != 2 or len({item["jobId"] for item in samples}) != 2:
            raise AssertionError("warm batch did not create new request and job identities")
        if samples[0]["setRevisionId"] == samples[1]["setRevisionId"]:
            raise AssertionError("warm batch reused the cold candidate set")
        page_samples = []
        observed_pages = []
        after = 0
        expected_count = None
        while True:
            started = time.perf_counter()
            page = post(client, "candidates", setRevisionId=samples[1]["setRevisionId"], after=after, limit=100)
            elapsed = time.perf_counter() - started
            if page["recordCount"] != 203 or page["candidateCount"] < 101:
                raise AssertionError("protected candidate inventory is incomplete")
            if (
                page["setRevisionId"] != samples[1]["setRevisionId"]
                or page["requestId"] != samples[1]["requestId"]
                or page["after"] != after
            ):
                raise AssertionError("candidate page authority or cursor differs")
            if expected_count is None:
                expected_count = page["candidateCount"]
            if page["candidateCount"] != expected_count or len(page["items"]) > 100:
                raise AssertionError("protected candidate page count drift")
            page_samples.append({"after": after, "items": len(page["items"]), "seconds": elapsed})
            observed_pages.append(
                (
                    after,
                    tuple(
                        content_digest(CandidateExplanation.model_validate_json(json.dumps(item)))
                        for item in page["items"]
                    ),
                )
            )
            if page["nextAfter"] is None:
                break
            if page["nextAfter"] <= after:
                raise AssertionError("protected candidate page cursor failed to progress")
            after = page["nextAfter"]
        if len(page_samples) < 2 or sum(item["items"] for item in page_samples) != expected_count:
            raise AssertionError("protected candidate pagination incomplete")
        closed = client.post("/projects/close", json={"root": root})
        if closed.status_code != 200:
            raise AssertionError("protected project close failed")
    encrypted_database = (Path(root) / "state/project.sqlite3").read_bytes()[:16] != b"SQLite format 3\x00"
    if not encrypted_database or provider_dispatches:
        raise AssertionError("protected storage or provider isolation differs")
    with open_canonical_database(Path(root) / "state/project.sqlite3", expected_project_id=project["projectId"]) as db:
        pair_inventories = []
        for item in samples:
            row = db.execute(
                "SELECT candidate_set_json FROM reconciliation_candidate_sets WHERE project_id=? AND revision_id=?",
                (project["projectId"], item["setRevisionId"]),
            ).fetchone()
            if row is None:
                raise AssertionError("candidate page durable set missing")
            expected = tuple(json.loads(row[0])["pairSha256"])
            stored = db.execute(
                "SELECT ordinal,payload_sha256 FROM reconciliation_candidate_pairs "
                "WHERE project_id=? AND set_revision_id=? ORDER BY ordinal",
                (project["projectId"], item["setRevisionId"]),
            ).fetchall()
            if len(stored) != len(expected) or tuple((row[0], row[1]) for row in stored) != tuple(enumerate(expected)):
                raise AssertionError("candidate page durable pair inventory differs")
            pair_inventories.append(expected)
    if pair_inventories[0] != pair_inventories[1]:
        raise AssertionError("cold and warm candidate content differs")
    candidate_digest = _verify_page_digests(tuple(observed_pages), pair_inventories[1])
    # Research content and local paths do not leave this sample.
    for item in samples:
        item["newJob"] = True
        item["newRequest"] = True
        del item["requestId"]
        del item["jobId"]
        del item["setRevisionId"]
    return {
        "fixtureVersion": "synthetic-protected-reconciliation-202-v1",
        "acceptedImportRecords": 202,
        "retainedConnectorRecords": 1,
        "recordCount": 203,
        "candidateCount": expected_count,
        "candidateDigestSha256": candidate_digest,
        "coldWarmCandidateContentEqual": True,
        "batches": samples,
        "pages": page_samples,
        "workerCapacitySubstitutedDuringSetup": True,
        "workerCapacitySubstitutedDuringMeasurement": False,
        "actualDPAPIAndSQLCipher": encrypted_database,
        "providerNetworkDuringMeasurement": len(provider_dispatches),
    }


def run_workload(directory: Path) -> dict:
    return {"kernel": _kernel(), "protected": _protected(directory)}
