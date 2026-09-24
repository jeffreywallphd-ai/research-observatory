"""Real HTTP/TLS on a synthetic loopback server; never a live provider claim.

Only the test's lower TCP seam maps the already-validated public address to the
fixture listener. TLS handshake, hostname checking, HTTP framing and streaming
use the actual runtime stack. Test CA trust is process-local, never installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpcore2
import httpx2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.transport import (  # noqa: E402
    PublicHTTPTransport,
    PublicNetworkBackend,
    private_wire,
    read_response,
)


class _LocalSocketBackend(httpcore2.AsyncNetworkBackend):
    def __init__(self, port):
        self.port, self.targets = port, []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.targets.append((host, port))
        return await httpcore2.AnyIOBackend().connect_tcp("127.0.0.1", self.port, timeout)


class ConnectorTlsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-connector-tls-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        cert_path, key_path = (
            Path(self.temporary.name) / "fixture-cert.pem",
            Path(self.temporary.name) / "fixture-key.pem",
        )
        openssl = shutil.which("openssl")
        if openssl is None and os.name == "nt":
            bundled = Path(os.environ["PROGRAMFILES"]) / "Git/usr/bin/openssl.exe"
            openssl = str(bundled) if bundled.is_file() else None
        if openssl is None:
            self.fail("The real TLS fixture needs OpenSSL (Git for Windows includes it).")
        subprocess.run(
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=api.openalex.org",
                "-addext",
                "subjectAltName=DNS:api.openalex.org",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        self.pem = cert_path.read_bytes()
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert_path, key_path)
        self.received, self.negotiated = [], []
        self.response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n"
            b'Connection: close\r\n\r\nb\r\n{"ok":true}\r\n0\r\n\r\n'
        )

        async def serve(reader, writer):
            try:
                self.negotiated.append(writer.get_extra_info("ssl_object").version())
                self.received.append(await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=3))
                writer.write(self.response)
                await writer.drain()
            finally:
                writer.close()
                with suppress(ConnectionError):
                    await writer.wait_closed()

        self.server = await asyncio.start_server(serve, "127.0.0.1", 0, ssl=server_context)
        self.backend = _LocalSocketBackend(self.server.sockets[0].getsockname()[1])

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def exchange(self, *, trusted, host="api.openalex.org"):
        client_context = ssl.create_default_context()
        if trusted:
            client_context.load_verify_locations(cadata=self.pem.decode("ascii"))
        self.assertTrue(client_context.check_hostname)
        self.assertEqual(ssl.CERT_REQUIRED, client_context.verify_mode)
        # Keep the real public-address filter, replacing only its lower socket
        # seam. The trusted certificate is limited to this one test context.
        backend = PublicNetworkBackend(self.backend)
        resolver = AsyncMock(return_value=[(0, 0, 0, "", ("93.184.216.34", 443))])
        with (
            patch("research_observatory_core.connectors.transport.PublicNetworkBackend", return_value=backend),
            patch("httpx2.create_ssl_context", return_value=client_context) as context_factory,
            patch("asyncio.BaseEventLoop.getaddrinfo", new=resolver),
        ):
            transport = PublicHTTPTransport()
            try:
                with private_wire():
                    response = await transport.handle_async_request(
                        httpx2.Request(
                            "GET",
                            f"https://{host}/works",
                            extensions={"timeout": {key: 3.0 for key in ("connect", "read", "write", "pool")}},
                        )
                    )
                    try:
                        return json.loads(await read_response(response, 1024))
                    finally:
                        await response.aclose()
            finally:
                await transport.aclose()
                context_factory.assert_called_once_with(verify=True, trust_env=False)

    async def test_verified_tls_and_chunked_http_use_original_hostname_and_public_ip(self):
        result = await self.exchange(trusted=True)
        self.assertEqual({"ok": True}, result)
        self.assertEqual([("93.184.216.34", 443)], self.backend.targets)
        self.assertIn(b"Host: api.openalex.org\r\n", self.received[0])
        self.assertTrue(all(value in {"TLSv1.2", "TLSv1.3"} for value in self.negotiated))

    async def test_untrusted_and_wrong_host_certificates_never_send_http(self):
        for trusted, host in ((False, "api.openalex.org"), (True, "api.crossref.org")):
            with self.subTest(trusted=trusted, host=host), self.assertRaises(httpcore2.ConnectError):
                await self.exchange(trusted=trusted, host=host)
        self.assertEqual([], self.received)

    async def test_wire_headers_are_not_emitted_by_dependency_debug_logs(self):
        self.response = self.response.replace(b"Content-Type:", b"X-Future: private-wire-sentinel\r\nContent-Type:")
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture()
        loggers = [logging.getLogger(name) for name in ("httpcore2.connection", "httpcore2.http11", "httpx2")]
        levels = [logger.level for logger in loggers]
        try:
            for logger in loggers:
                logger.addHandler(handler)
                logger.setLevel(logging.DEBUG)
            self.assertEqual({"ok": True}, await self.exchange(trusted=True))
        finally:
            for logger, level in zip(loggers, levels, strict=True):
                logger.removeHandler(handler)
                logger.setLevel(level)
        self.assertFalse(
            any("private-wire-sentinel" in value or "receive_response_headers" in value for value in records)
        )


if __name__ == "__main__":
    unittest.main()
