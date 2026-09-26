"""Actual clock/sleep and shared broker lane; synthetic authority, store and HTTP."""

from __future__ import annotations

import asyncio
import time

import httpx2
from research_observatory_core.connectors.broker import ConnectorBroker, ProviderRateController
from research_observatory_core.domain_contracts import new_uuid_v7

from tests.connectors.test_connector_broker import Authority, Cancellation, Repository
from tests.connectors.test_connector_transport import BytesStream
from tests.connectors.test_scholarly_mapping import fixture, request, search


async def rate_wait_sample(check):
    calls, waits = [], []
    active, maximum = 0, 0

    async def respond(wire):
        nonlocal active, maximum
        calls.append(time.perf_counter())
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.05)
            response = httpx2.Response(200, json=fixture("openalex"))
            return httpx2.Response(200, headers=response.headers, stream=BytesStream(response.content))
        finally:
            active -= 1

    async def measured_sleep(seconds):
        start = time.perf_counter()
        await asyncio.sleep(seconds)
        waits.append({"requestedSeconds": seconds, "actualSeconds": time.perf_counter() - start})

    broker = ConnectorBroker(
        authority=Authority(),
        repository=Repository(),
        rates=ProviderRateController(),
        transport=httpx2.MockTransport(respond),
        sleep=measured_sleep,
    )
    start = time.perf_counter()
    try:
        pages = await asyncio.gather(
            *(
                broker.fetch(
                    request("openalex", query=search(), invocationId=new_uuid_v7()), cancellation=Cancellation()
                )
                for _ in range(2)
            )
        )
    finally:
        await broker.aclose()
    check.assertEqual(["complete", "complete"], [page.outcome for page in pages])
    check.assertEqual(2, len(calls))
    check.assertEqual(1, maximum)
    check.assertTrue(waits)
    check.assertTrue(
        all(item["requestedSeconds"] > 0 and item["actualSeconds"] >= item["requestedSeconds"] * 0.99 for item in waits)
    )
    check.assertGreaterEqual(calls[1] - calls[0], 1.0)
    return {
        "seconds": time.perf_counter() - start,
        "wireStartIntervalSeconds": calls[1] - calls[0],
        "maximumConcurrentRequests": maximum,
        "waits": waits,
        "networkCalls": len(calls),
    }
