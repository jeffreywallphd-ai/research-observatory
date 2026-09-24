"""Offline broker protocol proofs; a separate suite covers actual persistence."""

from __future__ import annotations

import asyncio
import hashlib
import sys
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.broker import ConnectorBroker, ProviderRateController  # noqa: E402
from research_observatory_core.connectors.providers import ProviderProblem  # noqa: E402
from research_observatory_core.ports.connector_runtime import ConnectorAuthorityStamp, ConnectorCacheEntry  # noqa: E402
from research_observatory_core.ports.credential_store import (  # noqa: E402
    SecretKind,
    SecretLease,
    SecretRecord,
    SecretReference,
)

from tests.connectors.test_connector_transport import BytesStream  # noqa: E402
from tests.connectors.test_scholarly_mapping import fixture, request, search  # noqa: E402


class Clock:
    def __init__(self):
        self.seconds = 0.0
        self.waits = []

    def monotonic(self):
        return self.seconds

    def now(self):
        return (
            (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self.seconds))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    async def sleep(self, seconds):
        self.waits.append(seconds)
        self.seconds += seconds
        await asyncio.sleep(0)


class Cancellation:
    cancelled = False


class Authority:
    def __init__(self):
        self.stamp = ConnectorAuthorityStamp(
            request("openalex").project_id,
            "synthetic-session",
            "0190a000-0000-7000-8000-000000000040",
            intent_sha256="sha256:" + "a" * 64,
            policy_sha256="sha256:" + "a" * 64,
            confirmation_sha256="sha256:" + "a" * 64,
            rights_sha256="sha256:" + "a" * 64,
            retain_body=True,
            actor_id="0190a000-0000-7000-8000-000000000041",
        )
        self.denied = False
        self.stages = []

    def guard(self, value, stage, action):
        self.stages.append(stage)
        if self.denied or value.project_id != self.stamp.project_id:
            raise ProviderProblem("policy-denied")
        return action(self.stamp)


class Repository:
    def __init__(self):
        self.pages, self.bodies = [], []
        self.entry = None

    def cached(self, value):
        return self.entry

    def replay(self, value):
        return None

    def checkpoint(self, value):
        return None

    def publish(self, page, *, body, etag, last_modified, authority, publication=None):
        self.pages.append(page)
        self.bodies.append(body)
        if body is not None and page.outcome == "complete" and page.cache.state != "hit":
            self.entry = ConnectorCacheEntry(
                page.request.project_id,
                page.request.page_sha256(),
                body,
                page.retrieved_at,
                page.observed_at,
                etag,
                last_modified,
                page.response.redaction == "applied",
            )
        return page


class Secrets:
    def __init__(self):
        self.buffers, self.contexts = [], []

    def lease_record(self, reference, context):
        self.contexts.append(context)
        body = bytearray(b"private-key-sentinel")
        self.buffers.append(body)
        return SecretRecord("a" * 32, reference.kind), SecretLease(body)

    def lease(self, reference, context):
        return self.lease_record(reference, context)[1]

    def put(self, reference, material, context, *, expected_version=None):
        raise AssertionError("the connector must never write authentication material")


class ConnectorBrokerFixture(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock, self.authority, self.repository, self.cancel = Clock(), Authority(), Repository(), Cancellation()
        self.calls = []

    def broker(self, responses, **kwargs):
        async def handler(wire):
            self.calls.append(wire)
            value = responses.pop(0)
            if callable(value):
                value = value(wire)
            # Exercise the same raw streaming boundary as the production transport.
            return httpx2.Response(value.status_code, headers=value.headers, stream=BytesStream(value.content))

        return ConnectorBroker(
            authority=self.authority,
            repository=self.repository,
            transport=httpx2.MockTransport(handler),
            rates=ProviderRateController(clock=self.clock.monotonic),
            now=self.clock.now,
            sleep=self.clock.sleep,
            **kwargs,
        )


class ConnectorBrokerTests(ConnectorBrokerFixture):
    async def test_denial_before_secret_cache_and_network(self):
        self.authority.denied = True
        secrets = Secrets()
        broker = self.broker(
            [],
            credentials=secrets,
            key_references={"openalex": SecretReference("local", SecretKind.PROVIDER_KEY, "openalex", "api-key")},
        )
        page = await broker.fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("policy-denied", page.errors[0].code)
        self.assertEqual([], self.calls)
        self.assertEqual([], secrets.contexts)
        self.assertEqual([], self.repository.pages)

    async def test_overflowing_json_number_is_a_typed_failure(self):
        broker = self.broker(
            [httpx2.Response(200, content=b'{"unknown":1e400}', headers={"Content-Type": "application/json"})]
        )
        page = await broker.fetch(request("openalex"), cancellation=self.cancel)
        self.assertEqual("failed", page.outcome)
        self.assertEqual("incompatible-response", page.errors[0].code)
        self.assertEqual((), page.records)
        self.assertTrue(all(saved.outcome != "complete" for saved in self.repository.pages))
        self.assertEqual(1, len(self.calls))

    async def test_shared_provider_lane_serializes_dispatch_and_recovers_circuit(self):
        active, maximum = 0, 0
        starts = []

        async def respond(wire):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            starts.append(self.clock.seconds)
            await asyncio.sleep(0)
            active -= 1
            response = httpx2.Response(200, json=fixture("openalex"))
            return httpx2.Response(200, headers=response.headers, stream=BytesStream(response.content))

        rates = ProviderRateController(clock=self.clock.monotonic)
        brokers = [
            ConnectorBroker(
                authority=self.authority,
                repository=self.repository,
                transport=httpx2.MockTransport(respond),
                rates=rates,
                now=self.clock.now,
                sleep=self.clock.sleep,
            )
            for _ in range(2)
        ]
        pages = await asyncio.gather(
            *(broker.fetch(request("openalex"), cancellation=self.cancel) for broker in brokers)
        )
        self.assertTrue(all(page.outcome == "complete" for page in pages))
        self.assertEqual(1, maximum)
        self.assertGreaterEqual(starts[1] - starts[0], 1)
        for broker in brokers:
            await broker.aclose()

        failing = self.broker([httpx2.Response(503)] * 3 + [httpx2.Response(200, json=fixture("openalex"))])
        first = await failing.fetch(request("openalex"), cancellation=self.cancel)
        self.assertEqual("open", first.rate.circuit)
        denied = await failing.fetch(request("openalex"), cancellation=self.cancel)
        self.assertEqual("provider-unavailable", denied.errors[0].code)
        self.assertEqual(3, len(self.calls))
        self.clock.seconds += 31
        recovered = await failing.fetch(request("openalex"), cancellation=self.cancel)
        self.assertEqual("complete", recovered.outcome)
        self.assertEqual("closed", recovered.rate.circuit)
        self.assertEqual(4, len(self.calls))
        await failing.aclose()

    async def test_response_close_failure_discards_page_and_clears_secret_lease(self):
        class FailingClose(BytesStream):
            async def aclose(self):
                raise OSError("synthetic-close-failure")

        async def respond(wire):
            self.calls.append(wire)
            response = httpx2.Response(200, json=fixture("openalex"))
            return httpx2.Response(200, headers=response.headers, stream=FailingClose(response.content))

        secrets = Secrets()
        broker = ConnectorBroker(
            authority=self.authority,
            repository=self.repository,
            rates=ProviderRateController(clock=self.clock.monotonic),
            transport=httpx2.MockTransport(respond),
            credentials=secrets,
            key_references={"openalex": SecretReference("local", SecretKind.PROVIDER_KEY, "openalex", "api-key")},
            now=self.clock.now,
            sleep=self.clock.sleep,
        )
        page = await broker.fetch(request("openalex"), cancellation=self.cancel)
        self.assertEqual("provider-unavailable", page.errors[0].code)
        self.assertEqual((), page.records)
        self.assertTrue(all(not any(buffer) for buffer in secrets.buffers))
        self.assertTrue(all(saved.outcome == "failed" for saved in self.repository.pages))
        await broker.aclose()

    async def test_retry_rate_limits_and_terminal_authentication(self):
        broker = self.broker(
            [
                httpx2.Response(429, headers={"Retry-After": "2"}),
                httpx2.Response(503),
                httpx2.Response(200, json=fixture("openalex")),
            ]
        )
        page = await broker.fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("complete", page.outcome)
        self.assertEqual(3, len(self.calls))
        self.assertGreaterEqual(self.clock.seconds, 4)
        self.assertEqual(1, len(self.repository.pages))
        broker = self.broker([httpx2.Response(401)])
        page = await broker.fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("authentication", page.errors[0].code)
        self.assertFalse(page.errors[0].retryable)
        self.assertIsNone(page.next_cursor)
        self.assertEqual(4, len(self.calls))

    async def test_retry_after_beyond_budget_does_not_retry_early(self):
        broker = self.broker([httpx2.Response(429, headers={"Retry-After": "600"})])
        page = await broker.fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("rate-limit", page.errors[0].code)
        self.assertEqual(1, len(self.calls))

    async def test_terminal_denial_ignores_retry_header(self):
        page = await self.broker([httpx2.Response(401, headers={"Retry-After": "10"})]).fetch(
            request("openalex", query=search()), cancellation=self.cancel
        )
        self.assertEqual("authentication", page.errors[0].code)
        self.assertIsNone(page.errors[0].retry_after_ms)

    async def test_advertised_delay_beyond_budget_returns_without_sleeping(self):
        broker = self.broker(
            [httpx2.Response(503, headers={"X-Rate-Limit-Limit": "1", "X-Rate-Limit-Interval": "90000s"})]
        )
        page = await broker.fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("rate-limit", page.errors[0].code)
        self.assertEqual([], self.clock.waits)
        self.assertEqual(1, len(self.calls))
        page = await broker.fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("rate-limit", page.errors[0].code)
        self.assertEqual(1, len(self.calls))

    async def test_secret_echo_removed_before_mapping_or_publication_and_lease_cleared(self):
        body = fixture("openalex")
        body["results"][0]["future_field"]["echo"] = "private-key-sentinel"

        def response(wire):
            self.assertEqual("Bearer private-key-sentinel", wire.headers["Authorization"])
            self.assertNotIn("private-key-sentinel", str(wire.url))
            return httpx2.Response(200, json=body, headers={"ETag": "private-key-sentinel"})

        secrets = Secrets()
        broker = self.broker(
            [response],
            credentials=secrets,
            key_references={"openalex": SecretReference("local", SecretKind.PROVIDER_KEY, "openalex", "api-key")},
        )
        page = await broker.fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("complete", page.outcome)
        self.assertEqual("applied", page.response.redaction)
        self.assertNotIn("private-key-sentinel", page.model_dump_json())
        self.assertNotIn(b"private-key-sentinel", self.repository.bodies[0])
        self.assertEqual(hashlib.sha256(self.repository.bodies[0]).hexdigest(), page.response.object_sha256)
        assert self.repository.entry is not None
        self.assertIsNone(self.repository.entry.etag)
        self.assertTrue(all(not any(buffer) for buffer in secrets.buffers))
        self.assertEqual("connector-authentication", secrets.contexts[0].purpose.value)

    async def test_cache_requires_exact_project_page_body_and_current_authority(self):
        value = request("openalex", query=search())
        policy = value.policy.model_dump() | {"cache_mode": "allow-fresh", "maximum_fresh_age_ms": 5000}
        value = type(value).model_validate(value.model_dump() | {"policy": policy})
        broker = self.broker([httpx2.Response(200, json=fixture("openalex"))])
        first = await broker.fetch(value, cancellation=self.cancel)
        self.clock.seconds += 1
        second = await broker.fetch(value, cancellation=self.cancel)
        self.assertEqual("hit", second.cache.state)
        self.assertNotEqual(first.observation_id, second.observation_id)
        self.assertEqual(first.retrieved_at, second.retrieved_at)
        self.assertEqual(1, len(self.calls))
        assert self.repository.entry is not None
        self.repository.entry = replace(self.repository.entry, page_sha256="sha256:" + "b" * 64)
        page = await broker.fetch(value, cancellation=self.cancel)
        self.assertEqual("incompatible-response", page.errors[0].code)
        self.authority.denied = True
        page = await broker.fetch(value, cancellation=self.cancel)
        self.assertEqual("policy-denied", page.errors[0].code)
        self.assertEqual(1, len(self.calls))

    async def test_revalidation_requires_a_real_retained_body(self):
        value = request("openalex", query=search())
        value = type(value).model_validate(
            value.model_dump() | {"policy": value.policy.model_dump() | {"cache_mode": "revalidate"}}
        )

        def conditional(wire):
            self.assertEqual('"synthetic-etag"', wire.headers["if-none-match"])
            return httpx2.Response(304)

        broker = self.broker(
            [httpx2.Response(200, json=fixture("openalex"), headers={"ETag": '"synthetic-etag"'}), conditional]
        )
        await broker.fetch(value, cancellation=self.cancel)
        page = await broker.fetch(value, cancellation=self.cancel)
        self.assertEqual("revalidated", page.cache.state)
        self.repository.entry = None
        page = await self.broker([httpx2.Response(304)]).fetch(value, cancellation=self.cancel)
        self.assertEqual("incompatible-response", page.errors[0].code)

    async def test_changed_authority_cancellation_and_redirect_publish_no_success(self):
        def revoke(wire):
            self.authority.stamp = replace(self.authority.stamp, policy_sha256="sha256:" + "b" * 64)
            return httpx2.Response(200, json=fixture("openalex"))

        page = await self.broker([revoke]).fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("policy-denied", page.errors[0].code)
        self.assertEqual([], self.repository.pages)
        self.cancel.cancelled = True
        page = await self.broker([]).fetch(request("openalex", query=search()), cancellation=self.cancel)
        self.assertEqual("cancelled", page.errors[0].code)
        self.cancel.cancelled = False
        page = await self.broker([httpx2.Response(302, headers={"Location": "http://127.0.0.1/private"})]).fetch(
            request("openalex", query=search()), cancellation=self.cancel
        )
        self.assertEqual("policy-denied", page.errors[0].code)
        self.assertEqual(2, len(self.calls))

    async def test_unknown_retention_rights_do_not_cache_raw_body(self):
        self.authority.stamp = replace(self.authority.stamp, retain_body=False)
        page = await self.broker([httpx2.Response(200, json=fixture("openalex"))]).fetch(
            request("openalex", query=search()), cancellation=self.cancel
        )
        self.assertEqual("complete", page.outcome)
        self.assertEqual("permitted-fields-only", page.response.body_state)
        self.assertEqual([None], self.repository.bodies)
        self.assertIsNone(self.repository.entry)
        self.assertEqual((), page.records[0].fields)


if __name__ == "__main__":
    unittest.main()
