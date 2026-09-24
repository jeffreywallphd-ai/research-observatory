"""Broker-only HTTPS transport with pinned public destinations and bounded data.

No proxy/environment/redirect/cookie authority. The HTTPX-family transport uses
HTTPCore's public network-backend seam so DNS validation governs the actual TCP
destination while the original hostname remains the TLS identity.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import math
import re
import socket
import time
import zlib
from collections.abc import AsyncIterable, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from urllib.parse import quote, quote_plus

import httpcore2
import httpx2

from .providers import HOSTS, ProviderProblem

_PRIVATE_WIRE = ContextVar("connector_private_wire", default=False)


class _WireLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _PRIVATE_WIRE.get()


_FILTER = _WireLogFilter()
# The selected dependency's own debug events can contain raw response headers.
# Filter only this broker's context; unrelated application logging is unchanged.
for _name in ("httpx2", "httpcore2.connection", "httpcore2.http11", "httpcore2.http2", "httpcore2.proxy"):
    logging.getLogger(_name).addFilter(_FILTER)


@contextmanager
def private_wire():
    token = _PRIVATE_WIRE.set(True)
    try:
        yield
    finally:
        _PRIVATE_WIRE.reset(token)


class PublicNetworkBackend(httpcore2.AsyncNetworkBackend):
    def __init__(self, backend: httpcore2.AsyncNetworkBackend | None = None):
        self._backend = backend or httpcore2.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ):
        if host not in HOSTS.values() or port != 443 or local_address is not None:
            raise ProviderProblem("policy-denied")
        async with asyncio.timeout(timeout):
            addresses = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if not addresses:
                raise ProviderProblem("provider-unavailable")
            targets = []
            for entry in addresses:
                address = ipaddress.ip_address(entry[4][0])
                if (
                    not address.is_global
                    or address.is_multicast
                    or address.is_reserved
                    or (
                        isinstance(address, ipaddress.IPv6Address)
                        and (
                            address.ipv4_mapped is not None
                            or address.sixtofour is not None
                            or address.teredo is not None
                        )
                    )
                ):
                    raise ProviderProblem("policy-denied")
                targets.append(str(address))
            # Numeric address passed to the socket implementation: a second DNS
            # answer cannot substitute a private address after the check above.
            return await self._backend.connect_tcp(targets[0], port, timeout, socket_options=socket_options)

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options=None):
        raise ProviderProblem("policy-denied")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class _ResponseStream(httpx2.AsyncByteStream):
    def __init__(self, stream: Any):
        self._stream = stream

    async def __aiter__(self):
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


class PublicHTTPTransport(httpx2.AsyncBaseTransport):
    def __init__(self):
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=httpx2.create_ssl_context(verify=True, trust_env=False),
            network_backend=PublicNetworkBackend(),
            max_connections=4,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if (
            request.url.scheme != "https"
            or request.url.host not in HOSTS.values()
            or request.url.port not in (None, 443)
            or request.url.userinfo
            or request.url.fragment
        ):
            raise ProviderProblem("policy-denied")
        try:
            content = request.content
        except httpx2.RequestNotRead:
            raise ProviderProblem("policy-denied") from None
        if request.method == "POST":
            if (
                request.url.host != HOSTS["semantic-scholar"]
                or request.url.path != "/recommendations/v1/papers"
                or len(content) > 128 * 1024
                or request.headers.get("content-type") != "application/json"
            ):
                raise ProviderProblem("policy-denied")
            payload = bounded_json(content)
            if not isinstance(payload, dict) or set(payload) != {"positivePaperIds", "negativePaperIds"}:
                raise ProviderProblem("policy-denied")
            for name, minimum in (("positivePaperIds", 1), ("negativePaperIds", 0)):
                values = payload[name]
                if (
                    not isinstance(values, list)
                    or not minimum <= len(values) <= 100
                    or any(
                        not isinstance(value, str)
                        or not 1 <= len(value) <= 4100
                        or re.fullmatch(r"[0-9a-f]{40}|DOI:10\.[0-9]{4,9}/[^\s]+", value) is None
                        for value in values
                    )
                ):
                    raise ProviderProblem("policy-denied")
        elif request.method != "GET" or content:
            raise ProviderProblem("policy-denied")
        response = await self._pool.handle_async_request(
            httpcore2.Request(
                method=request.method,
                url=httpcore2.URL(scheme=b"https", host=request.url.raw_host, port=443, target=request.url.raw_path),
                headers=request.headers.raw,
                content=content,
                extensions={"timeout": request.extensions["timeout"]},
            )
        )
        if not isinstance(response.stream, AsyncIterable):
            await response.aclose()
            raise ProviderProblem("incompatible-response")
        return httpx2.Response(response.status, headers=response.headers, stream=_ResponseStream(response.stream))

    async def aclose(self) -> None:
        await self._pool.aclose()


async def read_response(response: httpx2.Response, maximum: int) -> bytes:
    if not 1 <= maximum <= 10 * 1024 * 1024:
        raise ProviderProblem("response-too-large")
    media = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media not in {"application/json", "application/vnd.crossref-api-message+json"}:
        raise ProviderProblem("incompatible-response")
    coding = response.headers.get("content-encoding", "identity").strip().lower()
    if coding not in {"identity", "gzip"}:
        raise ProviderProblem("incompatible-response")
    length = response.headers.get("content-length")
    if length is not None and (
        len(length) > 20 or not length.isascii() or not length.isdecimal() or int(length) > maximum
    ):
        raise ProviderProblem("response-too-large")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if coding == "gzip" else None
    wire = 0
    result = bytearray()
    try:
        async for chunk in response.aiter_raw(chunk_size=8192):
            wire += len(chunk)
            if wire > maximum:
                raise ProviderProblem("response-too-large")
            decoded = decoder.decompress(chunk, maximum - len(result) + 1) if decoder else chunk
            result.extend(decoded)
            if len(result) > maximum or len(result) > max(1024, wire * 100):
                raise ProviderProblem("response-too-large")
        if decoder and (not decoder.eof or decoder.unused_data or decoder.unconsumed_tail):
            raise ProviderProblem("incompatible-response")
        return bytes(result)
    except zlib.error:
        raise ProviderProblem("incompatible-response") from None
    finally:
        result[:] = b"\0" * len(result)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProviderProblem("incompatible-response")
        result[key] = value
    return result


def _constant(_: str) -> Any:
    raise ProviderProblem("incompatible-response")


def bounded_json(body: bytes) -> Any:
    if len(body) > 10 * 1024 * 1024:
        raise ProviderProblem("response-too-large")
    start = time.monotonic()
    depth, quoted, escaped = 0, False, False
    # Reject excessive nesting before handing untrusted data to a recursive parser.
    for char in body:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > 64:
                raise ProviderProblem("incompatible-response")
        elif char in (93, 125):
            depth -= 1
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        pending, count = [value], 0
        while pending:
            item = pending.pop()
            count += 1
            if count > 100000:
                raise ProviderProblem("response-too-large")
            if isinstance(item, dict):
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, float) and not math.isfinite(item):
                raise ProviderProblem("incompatible-response")
        if time.monotonic() - start > 2:
            raise ProviderProblem("timeout")
        return value
    except UnicodeError, ValueError, RecursionError:
        raise ProviderProblem("incompatible-response") from None


def sanitize(value: Any, private_values: tuple[str, ...]) -> tuple[Any, bool]:
    """Remove broker-injected material even in unknown JSON fields and URLs.

    No wire headers/URL/exception objects are persisted. This handles literal,
    JSON-decoded and URL-encoded echoes, not unknowable arbitrary transformations.
    """
    variants = {
        variant
        for secret in private_values
        if secret
        for variant in (secret, quote(secret, safe=""), quote_plus(secret, safe=""))
    }
    applied = False
    pattern = (
        re.compile("|".join(re.escape(x) for x in sorted(variants, key=len, reverse=True)), re.IGNORECASE)
        if variants
        else None
    )

    def clean(item: Any) -> Any:
        nonlocal applied
        if isinstance(item, str) and pattern is not None:
            text_result, matches = pattern.subn("[redacted]", item)
            applied |= matches > 0
            return text_result
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, dict):
            result: dict[str, Any] = {}
            for key, child in item.items():
                normalized = key.lower().replace("-", "").replace("_", "")
                if normalized in {
                    "authorization",
                    "apikey",
                    "accesskey",
                    "accesstoken",
                    "token",
                    "mailto",
                    "email",
                    "cookie",
                    "setcookie",
                }:
                    applied = True
                    continue
                changed = clean(key)
                if changed != key:
                    # Do not collapse two secret-bearing keys into one assertion.
                    applied = True
                    continue
                result[key] = clean(child)
            return result
        return item

    result = clean(value)
    return result, applied
