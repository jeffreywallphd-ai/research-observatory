"""Drive real exchange timeout/reset cleanup with synthetic streaming failures."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

import httpx2

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/core-api/src"))

from research_observatory_core.connectors.broker import ConnectorBroker, ProviderRateController
from research_observatory_core.ports.credential_store import SecretKind, SecretReference

from tests.connectors.test_connector_broker import Authority, Cancellation, Clock, Repository, Secrets
from tests.connectors.test_scholarly_mapping import request, search


class InterruptedStream(httpx2.AsyncByteStream):
    def __init__(self, mode):
        self.mode, self.closed = mode, False
        self.entered = asyncio.Event()

    async def __aiter__(self):
        yield b'{"results":['
        self.entered.set()
        if self.mode == "reset":
            raise httpx2.ReadError("synthetic private-key-sentinel reset")
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


class ConnectorNetworkFailureTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, mode, *, cancel=False):
        clock, authority, repository, secrets = Clock(), Authority(), Repository(), Secrets()
        cancellation = Cancellation()
        streams = []
        entered = asyncio.Event()

        async def respond(wire):
            self.assertEqual("Bearer private-key-sentinel", wire.headers["Authorization"])
            stream = InterruptedStream(mode)
            streams.append(stream)
            entered.set()
            return httpx2.Response(200, headers={"content-type": "application/json"}, stream=stream)

        rates = ProviderRateController(clock=clock.monotonic)
        broker = ConnectorBroker(
            authority=authority,
            repository=repository,
            transport=httpx2.MockTransport(respond),
            rates=rates,
            now=clock.now,
            sleep=clock.sleep,
            credentials=secrets,
            key_references={"openalex": SecretReference("local", SecretKind.PROVIDER_KEY, "openalex", "api-key")},
        )
        value = request("openalex", query=search())
        value = value.model_copy(
            update={
                "policy": value.policy.model_copy(update={"timeout_ms": 1000 if cancel else 20, "maximum_attempts": 2})
            }
        )
        try:
            task = asyncio.create_task(broker.fetch(value, cancellation=cancellation))
            if cancel:
                await asyncio.wait_for(entered.wait(), timeout=1)
                await asyncio.wait_for(streams[0].entered.wait(), timeout=1)
                cancellation.cancelled = True
            page = await asyncio.wait_for(task, timeout=2)
        finally:
            await broker.aclose()
        self.assertEqual("failed", page.outcome)
        self.assertEqual(
            "cancelled" if cancel else "timeout" if mode == "timeout" else "provider-unavailable", page.errors[0].code
        )
        self.assertEqual(1 if cancel else 2, len(streams))
        self.assertEqual(len(streams), len(secrets.buffers))
        self.assertTrue(all(stream.closed for stream in streams))
        self.assertTrue(all(not any(buffer) for buffer in secrets.buffers))
        self.assertFalse(rates.bucket("openalex").lock.locked())
        self.assertEqual((), page.records)
        self.assertIsNone(page.next_cursor)
        self.assertEqual("unavailable", page.response.body_state)
        self.assertIsNone(repository.entry)
        self.assertIsNone(repository.checkpoint(value))
        self.assertTrue(all(row.outcome == "failed" for row in repository.pages))
        self.assertTrue(all(body is None for body in repository.bodies))
        self.assertNotIn("private-key-sentinel", page.model_dump_json())
        if cancel:
            self.assertEqual([], repository.pages)
        else:
            self.assertEqual(1, len(repository.pages))
            self.assertTrue(clock.waits, "bounded retry backoff must occur")

    async def test_hanging_partial_read_times_out_and_retries_with_cleanup(self):
        await self.exercise("timeout")

    async def test_connection_reset_after_partial_bytes_is_unavailable_and_retries(self):
        await self.exercise("reset")

    async def test_cancel_during_hanging_read_closes_stream_and_lease_without_retry(self):
        await self.exercise("timeout", cancel=True)
