"""Four-source production Core composition with synthetic external responses.

DPAPI, SQLCipher, durable jobs and publication are real; HTTP and native context
are isolated. These fixtures never describe actual scholarship or live service.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

# ruff: noqa: E402
from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.main import create_runtime_app
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.connectors import test_connector_authority as authority_fixtures
from tests.connectors.source_public_handoff import assert_source_handoff
from tests.connectors.source_rate_wait import rate_wait_sample
from tests.connectors.test_connector_network_failures import InterruptedStream
from tests.connectors.test_connector_settings import CONTACT, KEY
from tests.connectors.test_connector_transport import BytesStream
from tests.connectors.test_graph_oa_mapping import PAPER, graph_request, oa_document, oa_request, paper
from tests.connectors.test_scholarly_mapping import fixture, request, search
from tests.service import test_import_preview_service as runtime_fixture

PROVIDERS = ("openalex", "crossref", "unpaywall", "semantic-scholar")
FIXTURE_VERSION = "four-scholarly-sources-page-v1"


def documents(count):
    alex, cross = fixture("openalex"), fixture("crossref")
    alex["results"] = [
        copy.deepcopy(alex["results"][0]) | {"id": f"https://openalex.org/W99999999{index:04d}"}
        for index in range(count)
    ]
    for index, row in enumerate(alex["results"]):
        row["doi"] = f"https://doi.org/10.99999/synthetic-{index}"
        row["ids"] = {"openalex": row["id"], "doi": row["doi"]}
    alex["meta"] = {"count": count, "next_cursor": None}
    cross["message"]["items"] = [
        copy.deepcopy(cross["message"]["items"][0]) | {"DOI": f"10.99999/synthetic-{index}"} for index in range(count)
    ]
    cross["message"]["total-results"] = count
    graph = {
        "offset": 0,
        "data": [
            {"citingPaper": paper(f"{index + 1:040x}"), "contexts": ["Synthetic citation context"]}
            for index in range(count)
        ],
    }
    return {"openalex": alex, "crossref": cross, "unpaywall": oa_document(), "semantic-scholar": graph}


def source_request(provider, identity, count, *, cache=False):
    changes = {
        "projectId": identity,
        "invocationId": new_uuid_v7(),
        "pageSize": 1 if provider == "unpaywall" else count,
    }
    if provider == "unpaywall":
        value = oa_request(**changes)
    elif provider == "semantic-scholar":
        value = graph_request(
            {"kind": "citations", "seed": {"scheme": "semantic-scholar", "value": PAPER}, "direction": "citations"},
            **changes,
        )
    else:
        value = request(provider, query=search(), **changes)
    return value.model_copy(
        update={
            "policy": value.policy.model_copy(
                update={
                    "cache_mode": "allow-fresh" if cache else "bypass",
                    "maximum_fresh_age_ms": 300000 if cache else 0,
                    "maximum_attempts": 1,
                }
            )
        }
    )


def run_workload(check, directory, *, count=100, boundaries=True):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    vault = directory / "vault"
    source_documents = documents(count)
    calls, samples, handoff = [], [], []
    state: dict[str, Any] = {
        "failure": False,
        "hold": False,
        "entered": False,
        "active": 0,
        "maximumActive": 0,
        "fault": None,
    }
    root, identity = None, None
    helper = runtime_fixture.ImportRuntimeCompositionTests()
    retained = {}
    cancelled = None
    failed_exchanges = []

    async def respond(wire):
        provider = {
            "api.openalex.org": "openalex",
            "api.crossref.org": "crossref",
            "api.unpaywall.org": "unpaywall",
            "api.semanticscholar.org": "semantic-scholar",
        }[wire.url.host]
        calls.append({"provider": provider, "started": time.perf_counter()})
        state["active"] += 1
        state["maximumActive"] = max(state["active"], state["maximumActive"])
        try:
            if provider == "unpaywall":
                check.assertEqual(CONTACT, wire.url.params["email"])
            if provider == "semantic-scholar":
                check.assertEqual(KEY, wire.headers["x-api-key"])
            state["entered"] = True
            while state["hold"]:
                await asyncio.sleep(0.01)
            if state["fault"] is not None:
                return httpx2.Response(
                    200, headers={"content-type": "application/json"}, stream=InterruptedStream(state["fault"])
                )
            result = httpx2.Response(503) if state["failure"] else httpx2.Response(200, json=source_documents[provider])
            return httpx2.Response(result.status_code, headers=result.headers, stream=BytesStream(result.content))
        finally:
            state["active"] -= 1

    def application(epoch):
        app = create_runtime_app(
            settings=CoreSettings(),
            profile_vault_root=vault,
            workflow_context=NativeWorkflowContext(epoch * 32, "c" * 32),
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        return app

    def post(client, route, body, expected=200):
        response = client.post(route, json=body)
        check.assertEqual(expected, response.status_code, response.text)
        return response.json()

    def preview(client, value):
        return post(
            client,
            "/projects/connectors/previews",
            {
                "root": root,
                "request": value.model_dump(mode="json", by_alias=True),
                "retention": {
                    "rights": {
                        name: {"value": "permitted", "basis": "researcher-confirmed"} for name in ("store", "inspect")
                    },
                    "retainBody": True,
                },
            },
        )

    def confirm(client, preview_value):
        return post(
            client,
            "/projects/connectors/confirmations",
            {"root": root, "previewId": preview_value["previewId"], "confirmation": preview_value["confirmation"]},
        )

    def wait(client, job):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = post(client, "/projects/connectors/jobs/status", {"root": root, "jobId": job["jobId"]})
            if status["state"] in {"succeeded", "failed", "cancelled"}:
                return status
            time.sleep(0.01)
        raise AssertionError("source worker did not reach a terminal state")

    def execute(client, value, expected="succeeded"):
        started = time.perf_counter()
        item = preview(client, value)
        job = confirm(client, item)
        status = wait(client, job)
        check.assertEqual(expected, status["state"], status)
        return item, status, time.perf_counter() - started

    with patch(
        "research_observatory_core.repositories._windows_worker_capacity",
        return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
    ):
        first = application("b")
        with helper.client(first) as client:
            first.state.runtime.connectors._transport_factory = lambda: httpx2.MockTransport(respond)
            created = post(
                client,
                "/projects",
                {
                    "parentDirectory": str(directory),
                    "directoryName": "sources",
                    "displayName": "Synthetic four-source qualification",
                    "primaryUseCase": "theory-synthesis",
                    "researchObjective": "Synthetic source integration",
                },
            )
            root, identity = created["root"], created["projectId"]
            post(client, "/projects/open", {"root": root})
            runtime = first.state.runtime
            authority = authority_fixtures.ConnectorAuthorityFixture()
            authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
            authority.intent(providers=PROVIDERS)
            authority.policy()
            initial = client.get("/projects/connectors/capabilities").json()
            check.assertEqual(
                "not-configured",
                next(item["configuration"] for item in initial["items"] if item["providerId"] == "unpaywall"),
            )
            for provider, key, contact in (("unpaywall", None, CONTACT), ("semantic-scholar", KEY, None)):
                post(
                    client,
                    "/native/connectors/configuration/replace",
                    {
                        "root": root,
                        "projectId": identity,
                        "providerId": provider,
                        "key": key,
                        "contact": contact,
                        "expectedVersion": None,
                    },
                )
            check.assertEqual([], calls)
            for provider in PROVIDERS:
                for phase, cache in (("cold", False), ("cache", True)):
                    value = source_request(provider, identity, count, cache=cache)
                    before = len(calls)
                    item, job, seconds = execute(client, value)
                    saved = runtime.connectors._adapters(Path(root), identity).pages.replay(value)
                    check.assertIsNotNone(saved)
                    check.assertEqual(1 if provider == "unpaywall" else count, len(saved.records))
                    check.assertEqual("hit" if cache else "disabled", saved.cache.state)
                    check.assertEqual(before if cache else before + 1, len(calls))
                    check.assertNotIn(CONTACT, saved.model_dump_json())
                    check.assertNotIn(KEY, saved.model_dump_json())
                    samples.append(
                        {
                            "provider": provider,
                            "phase": phase,
                            "seconds": seconds,
                            "records": len(saved.records),
                            "networkCalls": len(calls) - before,
                        }
                    )
                    if phase == "cold":
                        handoff.append(
                            {"page": saved.model_dump(mode="json", by_alias=True), "retention": item["retention"]}
                        )
                        retained[provider] = (value, saved, item, job)
            if boundaries:
                authority.policy(False)
                denied = client.post(
                    "/projects/connectors/previews",
                    json={
                        "root": root,
                        "request": source_request("crossref", identity, count).model_dump(mode="json", by_alias=True),
                        "retention": {
                            "rights": {
                                name: {"value": "permitted", "basis": "researcher-confirmed"}
                                for name in ("store", "inspect")
                            },
                            "retainBody": True,
                        },
                    },
                )
                check.assertEqual(403, denied.status_code, denied.text)
                check.assertEqual(4, len(calls))
                authority.policy()
                state["failure"] = True
                _, failed, _ = execute(client, source_request("semantic-scholar", identity, count), "failed")
                check.assertIn("provider-unavailable", failed["diagnosticCode"])
                for value, saved, _, _ in retained.values():
                    check.assertEqual(saved, runtime.connectors._adapters(Path(root), identity).pages.replay(value))
                state["failure"] = False
                execute(client, source_request("semantic-scholar", identity, count))
                for provider, mode, code in (
                    ("openalex", "timeout", "timeout"),
                    ("crossref", "reset", "provider-unavailable"),
                ):
                    state["fault"] = mode
                    value = source_request(provider, identity, count)
                    value = value.model_copy(update={"policy": value.policy.model_copy(update={"timeout_ms": 20})})
                    repository = runtime.connectors._adapters(Path(root), identity).pages
                    checkpoint = repository.checkpoint(value)
                    before = len(calls)
                    item, job, _ = execute(client, value, "failed")
                    check.assertIn(code, job["diagnosticCode"])
                    check.assertEqual(before + 1, len(calls))
                    failed_page = repository.replay(value)
                    check.assertIsNotNone(failed_page)
                    check.assertEqual("failed", failed_page.outcome)
                    check.assertEqual(code, failed_page.errors[0].code)
                    check.assertEqual((), failed_page.records)
                    check.assertIsNone(failed_page.next_cursor)
                    check.assertEqual("unavailable", failed_page.response.body_state)
                    check.assertEqual(checkpoint, repository.checkpoint(value))
                    failed_exchanges.append((value, failed_page, item, job, checkpoint))
                    state["fault"] = None
                state["hold"], state["entered"] = True, False
                cancelled_request = source_request("crossref", identity, count)
                cancelled_preview = preview(client, cancelled_request)
                preceding_checkpoint = runtime.connectors._adapters(Path(root), identity).pages.checkpoint(
                    cancelled_request
                )
                pending = confirm(client, cancelled_preview)
                deadline = time.monotonic() + 10
                while not state["entered"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                check.assertTrue(state["entered"])
                post(client, "/projects/connectors/jobs/cancel", {"root": root, "jobId": pending["jobId"]})
                check.assertEqual("cancelled", wait(client, pending)["state"])
                state["hold"] = False
                check.assertIsNone(runtime.connectors._adapters(Path(root), identity).pages.replay(cancelled_request))
                cancelled = (cancelled_request, cancelled_preview, pending, preceding_checkpoint)
            post(client, "/projects/close", {"root": root})
        second = application("d")
        with helper.client(second) as client:
            second.state.runtime.connectors._transport_factory = lambda: httpx2.MockTransport(respond)
            post(client, "/projects/open", {"root": root})
            before = len(calls)
            for value, saved, item, job in retained.values():
                check.assertEqual(
                    saved, second.state.runtime.connectors._adapters(Path(root), identity).pages.replay(value)
                )
                status = post(client, "/projects/connectors/jobs/status", {"root": root, "jobId": job["jobId"]})
                check.assertEqual("succeeded", status["state"])
                inspection = post(
                    client,
                    "/projects/connectors/inspect",
                    {"root": root, "previewId": item["previewId"], "recordOffset": len(saved.records) - 1},
                )
                check.assertEqual(saved.observation_id, inspection["observation"]["observationId"])
                check.assertEqual(len(saved.records), inspection["observation"]["recordCount"])
                check.assertIsNone(inspection["nextRecordOffset"])
                expected_record = saved.records[-1].model_dump(mode="json", by_alias=True)
                expected_record["fields"] = [
                    field
                    for field in expected_record["fields"]
                    if field["name"] in {"candidate.title", "candidate.oa-locations", "candidate.discovery"}
                ]
                check.assertEqual([expected_record], inspection["observation"]["records"])
                check.assertEqual(
                    value.query.model_dump(mode="json", by_alias=True), json.loads(inspection["queryJson"])
                )
                check.assertEqual(value.scientific_sha256(), inspection["scientificRequestSha256"])
            if cancelled is not None:
                value, item, job, checkpoint = cancelled
                repository = second.state.runtime.connectors._adapters(Path(root), identity).pages
                check.assertIsNone(repository.replay(value))
                check.assertEqual(checkpoint, repository.checkpoint(value))
                inspection = post(
                    client,
                    "/projects/connectors/inspect",
                    {"root": root, "previewId": item["previewId"], "recordOffset": 0},
                )
                check.assertEqual(job["jobId"], inspection["job"]["jobId"])
                check.assertEqual("cancelled", inspection["job"]["state"])
                check.assertIsNone(inspection["observation"])
                check.assertEqual(
                    "cancelled",
                    post(client, "/projects/connectors/jobs/status", {"root": root, "jobId": job["jobId"]})["state"],
                )
            for value, failed_page, _item, job, checkpoint in failed_exchanges:
                repository = second.state.runtime.connectors._adapters(Path(root), identity).pages
                check.assertEqual(failed_page, repository.replay(value))
                check.assertEqual(checkpoint, repository.checkpoint(value))
                status = post(client, "/projects/connectors/jobs/status", {"root": root, "jobId": job["jobId"]})
                check.assertEqual("failed", status["state"])
                check.assertIn(failed_page.errors[0].code, status["diagnosticCode"])
            check.assertEqual(before, len(calls))
            check.assertNotEqual(b"SQLite format 3\x00", (Path(root) / "state/project.sqlite3").read_bytes()[:16])
            post(client, "/projects/close", {"root": root})
    assert_source_handoff(check, handoff, count)
    return {
        "fixtureVersion": FIXTURE_VERSION,
        "recordsPerPage": count,
        "samples": samples,
        "handoff": handoff,
        "networkCalls": len(calls),
        "boundariesExercised": boundaries,
        "restartPreserved": True,
        "cancelledStatePreserved": cancelled is not None,
        "failedExchangeCodes": [page.errors[0].code for _, page, _, _, _ in failed_exchanges],
        "observedConcurrentRequests": state["maximumActive"],
        "rateWait": asyncio.run(rate_wait_sample(check)),
    }


@unittest.skipUnless(os.name == "nt", "Windows DPAPI and SQLCipher required")
class SourceSliceRuntimeTests(unittest.TestCase):
    def test_four_sources_cache_failure_denial_cancellation_and_restart(self):
        directory = Path(tempfile.mkdtemp(prefix="source-slice-", dir=REPO / "artifacts/tmp")) / "fixture"
        result = run_workload(self, directory, count=5)
        (directory.parent / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"report": (directory.parent / "result.json").relative_to(REPO).as_posix()}), flush=True)
