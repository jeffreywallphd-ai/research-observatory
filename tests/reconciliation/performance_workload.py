"""Content-free CAP-04.S03 kernel and protected-project benchmark samples.

The project input is synthetic. Setup uses an ASGI/native-context fixture and
synthetic Crossref transport; the measured batch uses the actual Windows
DPAPI/SQLCipher owner, queue, source authority and worker admission.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.main import create_runtime_app
from research_observatory_core.reconciliation import candidates

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
        samples = []
        identities = []
        for phase in ("cold", "warm"):
            started = time.perf_counter()
            request = post(client, "batches/prepare")["requestId"]
            job = post(client, "batches/schedule", requestId=request)["jobId"]
            if phase == "warm":
                with patch(
                    "research_observatory_core.reconciliation.feature_cache.prepare_record",
                    wraps=candidates.prepare_record,
                ) as compute:
                    service.run_pending()
                    feature_computations = compute.call_count
            else:
                service.run_pending()
                feature_computations = None
            status = post(client, "batches/status", requestId=request, jobId=job)
            elapsed = time.perf_counter() - started
            if status["state"] != "succeeded" or status["setRevisionId"] is None:
                raise AssertionError("protected batch did not publish a succeeded candidate set")
            if phase == "warm" and feature_computations != 0:
                raise AssertionError("warm batch recomputed revision-bound features")
            identities.append((request, job))
            samples.append(
                {
                    "phase": phase,
                    "seconds": elapsed,
                    "newJob": True,
                    "newRequest": True,
                    "setRevisionId": status["setRevisionId"],
                    "featureComputations": feature_computations,
                }
            )
        if len({item[0] for item in identities}) != 2 or len({item[1] for item in identities}) != 2:
            raise AssertionError("warm batch did not create new request and job identities")
        if samples[0]["setRevisionId"] == samples[1]["setRevisionId"]:
            raise AssertionError("warm batch reused the cold candidate set")
        page_samples = []
        after = 0
        expected_count = None
        while True:
            started = time.perf_counter()
            page = post(client, "candidates", setRevisionId=samples[1]["setRevisionId"], after=after, limit=100)
            elapsed = time.perf_counter() - started
            if page["recordCount"] != 203 or page["candidateCount"] < 101:
                raise AssertionError("protected candidate inventory is incomplete")
            if expected_count is None:
                expected_count = page["candidateCount"]
            if page["candidateCount"] != expected_count or len(page["items"]) > 100:
                raise AssertionError("protected candidate page count drift")
            page_samples.append({"after": after, "items": len(page["items"]), "seconds": elapsed})
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
    # Research content and local paths do not leave this sample.
    for item in samples:
        del item["setRevisionId"]
    return {
        "fixtureVersion": "synthetic-protected-reconciliation-202-v1",
        "acceptedImportRecords": 202,
        "retainedConnectorRecords": 1,
        "recordCount": 203,
        "candidateCount": expected_count,
        "batches": samples,
        "pages": page_samples,
        "workerCapacitySubstitutedDuringSetup": True,
        "workerCapacitySubstitutedDuringMeasurement": False,
        "actualDPAPIAndSQLCipher": encrypted_database,
        "providerNetworkDuringMeasurement": len(provider_dispatches),
    }


def run_workload(directory: Path) -> dict:
    return {"kernel": _kernel(), "protected": _protected(directory)}
