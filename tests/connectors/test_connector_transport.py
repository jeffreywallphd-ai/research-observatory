"""No external traffic: hostile resolver, wire stream and TLS policy tests."""

from __future__ import annotations

import gzip
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.providers import ProviderProblem  # noqa: E402
from research_observatory_core.connectors.transport import (  # noqa: E402
    PublicHTTPTransport,
    PublicNetworkBackend,
    bounded_json,
    read_response,
    sanitize,
)


class BytesStream(httpx2.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    async def __aiter__(self):
        for index in range(0, len(self.body), 7):
            yield self.body[index : index + 7]


class ConnectorTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_post_admission_is_limited_to_bounded_recommendation_payload(self):
        good = json.dumps({"positivePaperIds": ["a" * 40], "negativePaperIds": []}).encode()
        for method, url, body in (
            ("POST", "https://api.openalex.org/works", good),
            ("POST", "https://api.semanticscholar.org/graph/v1/paper/batch", good),
            ("PUT", "https://api.semanticscholar.org/recommendations/v1/papers", good),
            ("GET", "https://api.semanticscholar.org/graph/v1/paper/test", good),
            ("POST", "https://api.semanticscholar.org/recommendations/v1/papers", b"{}"),
            ("POST", "https://api.semanticscholar.org/recommendations/v1/papers", b"x" * (128 * 1024 + 1)),
        ):
            transport = PublicHTTPTransport()
            try:
                with patch.object(transport._pool, "handle_async_request", new=AsyncMock()) as network:
                    with self.subTest(method=method, url=url), self.assertRaises(ProviderProblem):
                        await transport.handle_async_request(
                            httpx2.Request(method, url, content=body, headers={"Content-Type": "application/json"})
                        )
                    network.assert_not_called()
            finally:
                await transport.aclose()

    async def test_private_mixed_and_embedded_addresses_never_reach_connector(self):
        for addresses in (
            ("127.0.0.1",),
            ("169.254.169.254",),
            ("10.0.0.1",),
            ("::1",),
            ("8.8.8.8", "192.168.0.1"),
            ("::ffff:127.0.0.1",),
            ("ff02::1",),
            ("2002:7f00:1::",),
        ):

            async def resolve(host, port, addresses=addresses, **kwargs):
                return [(0, 0, 0, "", (ip, port)) for ip in addresses]

            socket_backend = AsyncMock()
            with (
                patch("asyncio.BaseEventLoop.getaddrinfo", side_effect=resolve),
                self.assertRaises(ProviderProblem),
            ):
                await PublicNetworkBackend(socket_backend).connect_tcp("api.openalex.org", 443)
            socket_backend.connect_tcp.assert_not_called()

    async def test_destination_is_pinned_to_validated_ip_not_resolved_twice(self):
        resolved = [(0, 0, 0, "", ("8.8.8.8", 443))]
        socket_backend = AsyncMock()
        with patch("asyncio.BaseEventLoop.getaddrinfo", new=AsyncMock(return_value=resolved)) as resolver:
            await PublicNetworkBackend(socket_backend).connect_tcp("api.openalex.org", 443, timeout=2)
        resolver.assert_awaited_once()
        self.assertEqual("8.8.8.8", socket_backend.connect_tcp.await_args.args[0])
        for host, port in (("api.openalex.org.attacker.invalid", 443), ("api.openalex.org", 80), ("127.0.0.1", 443)):
            with self.assertRaises(ProviderProblem):
                await PublicNetworkBackend(socket_backend).connect_tcp(host, port)

    async def test_limits_cover_wire_decompressed_bombs_and_unsupported_encoding(self):
        for headers, body, maximum, expected in (
            ({"content-type": "application/json"}, b'{"ok":true}', 100, {"ok": True}),
            (
                {"content-type": "application/json", "content-encoding": "gzip"},
                gzip.compress(b'{"ok":true}'),
                1000,
                {"ok": True},
            ),
        ):
            response = httpx2.Response(200, headers=headers, stream=BytesStream(body))
            self.assertEqual(expected, bounded_json(await read_response(response, maximum)))
        bad = (
            ({"content-type": "application/json"}, b"x" * 101, 100),
            ({"content-type": "text/html"}, b"{}", 100),
            ({"content-type": "application/json", "content-encoding": "gzip"}, gzip.compress(b"x" * 100000), 1000),
            ({"content-type": "application/json", "content-encoding": "br"}, b"{}", 100),
            ({"content-type": "application/json", "content-encoding": "gzip"}, gzip.compress(b"{}")[:-2], 100),
        )
        for headers, body, maximum in bad:
            with self.subTest(headers=headers), self.assertRaises(ProviderProblem):
                await read_response(httpx2.Response(200, headers=headers, stream=BytesStream(body)), maximum)

    def test_json_has_depth_duplicate_nonfinite_and_node_bounds(self):
        for body in (
            b'{"x":1,"x":2}',
            b'{"x":NaN}',
            b'{"x":1e400}',
            b'{"x":-1e400}',
            b"[" * 65 + b"0" + b"]" * 65,
            b'"bad\x00"',
        ):
            with self.subTest(body=body[:20]), self.assertRaises(ProviderProblem):
                bounded_json(body)
        self.assertEqual({"x": [True, None, 4]}, bounded_json(b'{"x":[true,null,4]}'))

    def test_sanitizer_removes_private_values_from_unknown_keys_and_encoded_urls(self):
        body = {
            "future": {
                "private-key-sentinel": "Bearer private-key-sentinel",
                "url": "https://example.invalid/?mailto=synthetic%40example.invalid",
            },
            "Authorization": "hidden",
            "title": "Ordinary synthetic data",
            "x": ["synthetic@example.invalid"],
        }
        clean, applied = sanitize(body, ("private-key-sentinel", "synthetic@example.invalid"))
        encoded = json.dumps(clean)
        self.assertTrue(applied)
        for forbidden in ("private-key-sentinel", "synthetic@example.invalid", "synthetic%40example.invalid", "hidden"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual("Ordinary synthetic data", clean["title"])
        self.assertEqual(body["title"], clean["title"])


if __name__ == "__main__":
    unittest.main()
