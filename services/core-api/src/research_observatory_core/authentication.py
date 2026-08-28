"""Fail-closed authentication and request-origin policy for local Core HTTP."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

AsgiReceive = Callable[[], Awaitable[dict[str, Any]]]
AsgiSend = Callable[[dict[str, Any]], Awaitable[None]]
AsgiApp = Callable[[dict[str, Any], AsgiReceive, AsgiSend], Awaitable[None]]

TOKEN_HEX_LENGTH = 64
STARTUP_RECORD_BYTES = len(b"auth ") + TOKEN_HEX_LENGTH + len(b"\n")


def capability_token_digest(token: str | bytes | bytearray | memoryview) -> bytes:
    """Validate a canonical 256-bit token and retain only its digest."""

    encoded = token.encode("ascii") if isinstance(token, str) else token
    if len(encoded) != TOKEN_HEX_LENGTH or any(value not in b"0123456789abcdef" for value in encoded):
        raise ValueError("capability token must be 256-bit lowercase hexadecimal")
    return hashlib.sha256(encoded).digest()


def parse_startup_authentication(record: bytearray) -> bytes:
    """Parse, clear, and reduce the inherited control-pipe record to its digest."""

    try:
        if len(record) != STARTUP_RECORD_BYTES or not record.startswith(b"auth ") or not record.endswith(b"\n"):
            raise ValueError("supervised startup authentication record is invalid")
        return capability_token_digest(memoryview(record)[5:-1])
    finally:
        record[:] = b"\x00" * len(record)


def _header_values(scope: dict[str, Any], name: bytes) -> list[bytes]:
    headers = scope.get("headers")
    if not isinstance(headers, (list, tuple)):
        return []
    values: list[bytes] = []
    for item in headers:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            return []
        key, value = item
        if not isinstance(key, bytes) or not isinstance(value, bytes):
            return []
        if key.lower() == name:
            values.append(value)
    return values


class LocalAuthenticationMiddleware:
    """Require exact loopback peer, authority, absent Origin, and current bearer token."""

    def __init__(self, app: AsgiApp, *, digest: bytes | None, authority: str | None) -> None:
        self.app = app
        if digest is not None and len(digest) != hashlib.sha256().digest_size:
            raise ValueError("capability token digest must be SHA-256")
        self._digest = bytes(digest) if digest is not None else None
        if authority is not None:
            if authority != authority.strip() or authority.casefold() != authority or "@" in authority:
                raise ValueError("local HTTP authority must be canonical")
            host, separator, port = authority.rpartition(":")
            if host != "127.0.0.1" or separator != ":" or not port.isascii() or not port.isdecimal():
                raise ValueError("local HTTP authority must use numeric IPv4 loopback and an explicit port")
            if not 1 <= int(port) <= 65_535 or str(int(port)) != port:
                raise ValueError("local HTTP authority port must be canonical")
        self._authority = authority.encode("ascii") if authority is not None else None

    async def _deny(self, send: AsgiSend, *, status: int, code: str, authenticate: bool = False) -> None:
        payload = json.dumps({"code": code, "status": status}, separators=(",", ":"), sort_keys=True).encode("ascii")
        headers = [
            (b"cache-control", b"no-store"),
            (b"content-length", str(len(payload)).encode("ascii")),
            (b"content-type", b"application/json"),
        ]
        if authenticate:
            headers.append((b"www-authenticate", b"Bearer"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": payload})

    async def __call__(self, scope: dict[str, Any], receive: AsgiReceive, send: AsgiSend) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        try:
            peer = ipaddress.ip_address(
                client[0]
                if isinstance(client, (list, tuple)) and len(client) == 2 and isinstance(client[0], str)
                else ""
            )
        except ValueError:
            await self._deny(send, status=403, code="RO-CORE-TRANSPORT-DENIED")
            return
        host = _header_values(scope, b"host")
        origin = _header_values(scope, b"origin")
        if (
            not peer.is_loopback
            or len(host) != 1
            or self._authority is None
            or not secrets.compare_digest(host[0], self._authority)
        ):
            await self._deny(send, status=403, code="RO-CORE-TRANSPORT-DENIED")
            return
        if origin:
            await self._deny(send, status=403, code="RO-CORE-ORIGIN-DENIED")
            return
        authorization = _header_values(scope, b"authorization")
        if len(authorization) != 1 or not authorization[0].startswith(b"Bearer ") or self._digest is None:
            await self._deny(send, status=401, code="RO-CORE-AUTH-REQUIRED", authenticate=True)
            return
        supplied = authorization[0][7:]
        if len(supplied) != TOKEN_HEX_LENGTH or any(value not in b"0123456789abcdef" for value in supplied):
            await self._deny(send, status=401, code="RO-CORE-AUTH-REQUIRED", authenticate=True)
            return
        candidate = hashlib.sha256(supplied).digest()
        if not secrets.compare_digest(candidate, self._digest):
            await self._deny(send, status=401, code="RO-CORE-AUTH-REQUIRED", authenticate=True)
            return
        if any(_header_values(scope, name) for name in (b"x-actor-id", b"x-actor-type", b"x-research-actor-id")):
            await self._deny(send, status=403, code="RO-CORE-ACTOR-SPOOF-DENIED")
            return
        await self.app(scope, receive, send)
