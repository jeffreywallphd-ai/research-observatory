"""Core-owned, fixed-route HTTP broker for isolated connector plugins.

The worker supplies scientific parameters, never a URL, header, credential or
plan authority. This module is not an LPAC sandbox: its caller must admit the
worker and bind each call to the current Core-owned invocation first.
"""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import json
import re
import socket
import time
from collections.abc import Awaitable, Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Self
from urllib.parse import quote

import httpcore2
import httpx2
from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import ContractModel
from .plugin_manifest import (
    Operation,
    PluginDestination,
    PluginInvocationPlan,
    PluginInvocationRequest,
    PluginProjectGrant,
    Scope,
    VerifiedPluginPackage,
    authorize_plugin_invocation,
)
from .providers import ProviderProblem
from .transport import _ResponseStream, bounded_json, private_wire, read_response, sanitize

_MAX_RESPONSE = 10 * 1024 * 1024
_MAX_QUERY = 16 * 1024
_MAX_WIRE_TARGET = 16 * 1024
_TIMEOUT = 30.0
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:/-]{0,4095}$")
_REPOSITORY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CURSOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,4095}$")
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class PluginBrokerProblem(ValueError):
    """A bounded diagnostic category; never pass through a wire exception."""

    def __init__(
        self,
        code: Literal[
            "policy-denied",
            "route-denied",
            "credential-denied",
            "redirect-denied",
            "response-too-large",
            "incompatible-response",
            "provider-unavailable",
            "timeout",
            "audit-unavailable",
        ],
    ):
        self.code = code
        super().__init__(code)


class PluginBrokerCall(ContractModel):
    """Scientific parameters are operation-specific; arbitrary HTTP is absent."""

    model_config = ConfigDict(revalidate_instances="always", hide_input_in_errors=True)
    operation: Operation
    identifier: str | None = Field(default=None, strict=True, min_length=1, max_length=4096, repr=False)
    query: str | None = Field(default=None, strict=True, min_length=1, max_length=4096, repr=False)
    repository_id: str | None = Field(default=None, strict=True, min_length=1, max_length=128, repr=False)
    cursor: str | None = Field(default=None, strict=True, min_length=1, max_length=4096, repr=False)
    page_size: Annotated[int, Field(strict=True, ge=1, le=1000)] | None = None
    credential_scope: Scope | None = None

    @model_validator(mode="after")
    def operation_shape(self) -> Self:
        values = {
            "identifier": self.identifier,
            "query": self.query,
            "repository_id": self.repository_id,
            "cursor": self.cursor,
            "page_size": self.page_size,
        }
        allowed = {
            "lookup": {"identifier"},
            "search": {"query", "cursor", "page_size"},
            "references": {"identifier", "cursor"},
            "citations": {"identifier", "cursor"},
            "open-access-locations": {"identifier"},
            "repository-metadata": {"repository_id"},
        }[self.operation]
        required = {
            "lookup": "identifier",
            "search": "query",
            "references": "identifier",
            "citations": "identifier",
            "open-access-locations": "identifier",
            "repository-metadata": "repository_id",
        }[self.operation]
        if values[required] is None or any(value is not None and name not in allowed for name, value in values.items()):
            raise ValueError("plugin-broker-operation-shape-invalid")
        if self.identifier is not None and (
            _IDENTIFIER.fullmatch(self.identifier) is None
            or any(part in {".", ".."} for part in self.identifier.split("/"))
            or "//" in self.identifier
        ):
            raise ValueError("plugin-broker-identifier-invalid")
        if self.repository_id is not None and (
            _REPOSITORY_ID.fullmatch(self.repository_id) is None or ".." in self.repository_id
        ):
            raise ValueError("plugin-broker-repository-id-invalid")
        if self.query is not None and (
            not self.query.strip() or any(ord(char) < 32 or ord(char) == 127 for char in self.query)
        ):
            raise ValueError("plugin-broker-query-invalid")
        if self.cursor is not None and _CURSOR.fullmatch(self.cursor) is None:
            raise ValueError("plugin-broker-cursor-invalid")
        return self


class PluginRepositoryMetadata(ContractModel):
    """The only accepted repository-metadata response assertion."""

    model_config = ConfigDict(revalidate_instances="always", hide_input_in_errors=True)
    repository_id: str = Field(strict=True, min_length=1, max_length=128, repr=False)
    display_name: str = Field(strict=True, min_length=1, max_length=512, repr=False)
    description: str | None = Field(default=None, strict=True, max_length=2048, repr=False)

    @field_validator("repository_id", "display_name", "description")
    @classmethod
    def bounded_public_text(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError("plugin-repository-metadata-text-invalid")
        return value


@dataclass(frozen=True, slots=True)
class PluginBrokerResponse:
    body: bytes = field(repr=False)
    redacted: bool


def _public_address(text: str) -> bool:
    address = ipaddress.ip_address(text)
    return bool(
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not (
            isinstance(address, ipaddress.IPv6Address)
            and (address.ipv4_mapped is not None or address.sixtofour is not None or address.teredo is not None)
        )
    )


class PluginPublicNetworkBackend(httpcore2.AsyncNetworkBackend):
    """Resolve each connection and dial only its checked numeric address."""

    def __init__(self, host: str, port: int, backend: httpcore2.AsyncNetworkBackend | None = None):
        self._host, self._port = host, port
        self._backend = backend or httpcore2.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ):
        if host != self._host or port != self._port or local_address is not None:
            raise PluginBrokerProblem("route-denied")
        try:
            async with asyncio.timeout(min(_TIMEOUT, timeout) if timeout is not None else _TIMEOUT):
                answers = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except TimeoutError:
            raise PluginBrokerProblem("timeout") from None
        except OSError:
            raise PluginBrokerProblem("provider-unavailable") from None
        if not answers:
            raise PluginBrokerProblem("provider-unavailable")
        addresses = [answer[4][0] for answer in answers]
        if not all(isinstance(value, str) for value in addresses):
            raise PluginBrokerProblem("route-denied")
        numeric_addresses = [str(value) for value in addresses]
        if not all(_public_address(value) for value in numeric_addresses):
            raise PluginBrokerProblem("route-denied")
        # HTTPCore retains the original hostname for TLS/SNI. No second DNS lookup
        # can replace the approved result after this point.
        return await self._backend.connect_tcp(numeric_addresses[0], port, timeout, socket_options=socket_options)

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options=None):
        raise PluginBrokerProblem("route-denied")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class _PluginHTTPTransport(httpx2.AsyncBaseTransport):
    def __init__(self, destination: PluginDestination, path: str):
        self._destination, self._path = destination, path
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=httpx2.create_ssl_context(verify=True, trust_env=False),
            network_backend=PluginPublicNetworkBackend(destination.host, destination.port),
            max_connections=1,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        url = request.url
        if (
            request.method != "GET"
            or request.content
            or url.scheme != "https"
            or url.host != self._destination.host
            or url.port not in (None, self._destination.port)
            or url.userinfo
            or url.fragment
            or url.raw_path.split(b"?", 1)[0].decode("ascii") != self._path
        ):
            raise PluginBrokerProblem("route-denied")
        response = await self._pool.handle_async_request(
            httpcore2.Request(
                method="GET",
                url=httpcore2.URL(scheme=b"https", host=url.raw_host, port=self._destination.port, target=url.raw_path),
                headers=request.headers.raw,
                content=b"",
                extensions={"timeout": request.extensions["timeout"]},
            )
        )
        return httpx2.Response(response.status, headers=response.headers, stream=_ResponseStream(response.stream))

    async def aclose(self) -> None:
        await self._pool.aclose()


def _route(destination: PluginDestination, call: PluginBrokerCall) -> tuple[str, tuple[tuple[str, str], ...]]:
    values = {
        "identifier": call.identifier,
        "query": call.query,
        "repository_id": call.repository_id,
        "cursor": call.cursor,
        "page_size": str(call.page_size) if call.page_size is not None else None,
    }
    placeholders = set(_PLACEHOLDER.findall(destination.path_template))
    if any(values.get(name) is None for name in placeholders):
        raise PluginBrokerProblem("route-denied")
    path = _PLACEHOLDER.sub(lambda match: quote(values[match[1]] or "", safe=""), destination.path_template)
    pairs = tuple(
        (wire_name, value)
        for field_name, wire_name, value in (
            ("identifier", "identifier", call.identifier),
            ("query", "query", call.query),
            ("repository_id", "repositoryId", call.repository_id),
            ("cursor", "cursor", call.cursor),
            ("page_size", "pageSize", str(call.page_size) if call.page_size is not None else None),
        )
        if value is not None and field_name not in placeholders
    )
    if len(path) > 8192 or sum(len(name) + len(value) for name, value in pairs) > _MAX_QUERY:
        raise PluginBrokerProblem("route-denied")
    return path, pairs


@dataclass(slots=True)
class _PluginRateBucket:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_start: float = 0.0


class PluginBrokerRates:
    """Core-owned shared one-in-flight and one-request-per-second buckets."""

    def __init__(self):
        self._buckets: dict[tuple[str, str], _PluginRateBucket] = {}

    def bucket(self, package: VerifiedPluginPackage) -> _PluginRateBucket:
        manifest = package.manifest
        return self._buckets.setdefault((manifest.publisher_key_id, manifest.plugin_id), _PluginRateBucket())


class PluginNetworkBroker:
    """Reauthorize a Core-owned plan and concrete call at every request."""

    def __init__(
        self,
        *,
        package: VerifiedPluginPackage,
        current_grant: Callable[[str, str], PluginProjectGrant | None],
        current_request: Callable[[str, str], PluginInvocationRequest | None],
        recheck: Callable[[PluginInvocationPlan, PluginBrokerCall], None] | None,
        audit_denial: Callable[[str], None],
        current_credential_origin: Callable[[str, PluginInvocationPlan], tuple[str, str, int] | None],
        rates: PluginBrokerRates,
        lease_secret: Callable[[str, PluginInvocationPlan], AbstractContextManager[str]] | None = None,
        transport_factory: Callable[[PluginDestination, str], httpx2.AsyncBaseTransport] = _PluginHTTPTransport,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if (
            not callable(current_request)
            or not callable(audit_denial)
            or not callable(current_credential_origin)
            or inspect.iscoroutinefunction(audit_denial)
            or inspect.iscoroutinefunction(type(audit_denial).__call__)
            or not isinstance(rates, PluginBrokerRates)
        ):
            raise ValueError("plugin-broker-authority-audit-required")
        self._package, self._current_grant, self._current_request = package, current_grant, current_request
        self._recheck, self._audit_denial = recheck, audit_denial
        self._current_credential_origin = current_credential_origin
        self._lease_secret, self._transport_factory = lease_secret, transport_factory
        self._clock, self._sleep = clock, sleep
        self._bucket = rates.bucket(package)

    def _credential_allowed(self, plan: PluginInvocationPlan, call: PluginBrokerCall) -> None:
        scope = call.credential_scope
        if scope is None:
            return
        if scope not in self._package.manifest.credential_scopes or "credential-broker" not in plan.permissions:
            raise PluginBrokerProblem("credential-denied")
        if self._lease_secret is None:
            raise PluginBrokerProblem("credential-denied")
        try:
            origin = self._current_credential_origin(scope, plan)
        except Exception:
            raise PluginBrokerProblem("credential-denied") from None
        if origin != (plan.destination.scheme, plan.destination.host, plan.destination.port):
            raise PluginBrokerProblem("credential-denied")

    def _authorize(self, plan: PluginInvocationPlan, call: PluginBrokerCall) -> None:
        if self._recheck is None or plan.operation != call.operation or "provider-network" not in plan.permissions:
            raise PluginBrokerProblem("policy-denied")
        try:
            owned = self._current_request(plan.project_id, plan.invocation_id)
            if owned is None:
                raise PluginBrokerProblem("policy-denied")
            request = PluginInvocationRequest.model_validate(owned)
            if request.project_id != plan.project_id or request.invocation_id != plan.invocation_id:
                raise PluginBrokerProblem("policy-denied")
            grant = self._current_grant(plan.project_id, plan.plugin_id)
            if grant is None or authorize_plugin_invocation(self._package, grant, request) != plan:
                raise PluginBrokerProblem("policy-denied")
            self._recheck(plan, call)
        except PluginBrokerProblem:
            raise
        except Exception:
            # This includes stale/revoked grant, rights and policy failures. A
            # caller's diagnostic or private value is never surfaced here.
            raise PluginBrokerProblem("policy-denied") from None

    async def fetch(self, plan: PluginInvocationPlan, call: PluginBrokerCall) -> PluginBrokerResponse:
        try:
            return await self._fetch(plan, call)
        except PluginBrokerProblem as error:
            try:
                # Core binds this callback to its authoritative job; only a
                # content-free reason code enters the durable audit record.
                outcome = self._audit_denial(error.code)
                if inspect.isawaitable(outcome):
                    if inspect.iscoroutine(outcome):
                        outcome.close()
                    raise TypeError("asynchronous-denial-audit")
            except Exception:
                raise PluginBrokerProblem("audit-unavailable") from None
            raise

    async def _fetch(self, plan: PluginInvocationPlan, call: PluginBrokerCall) -> PluginBrokerResponse:
        if not isinstance(plan, PluginInvocationPlan) or not isinstance(call, PluginBrokerCall):
            raise PluginBrokerProblem("policy-denied")
        try:
            # model_copy can bypass validation; neither a worker's plan-shaped
            # JSON nor a mutated in-memory value is authority.
            plan = PluginInvocationPlan.model_validate(plan)
            call = PluginBrokerCall.model_validate(call)
        except Exception:
            raise PluginBrokerProblem("policy-denied") from None
        self._authorize(plan, call)
        path, pairs = _route(plan.destination, call)
        self._credential_allowed(plan, call)
        async with self._bucket.lock:
            delay = max(0.0, self._bucket.next_start - self._clock())
            if delay:
                await self._sleep(delay)
            # Permission, rights, terms, project intent and exact scientific
            # parameters may change while rate-limited or across retries.
            self._authorize(plan, call)
            self._credential_allowed(plan, call)
            self._bucket.next_start = self._clock() + 1.0
            headers = {"Accept": "application/json", "Accept-Encoding": "gzip", "User-Agent": "ResearchObservatory/0.1"}
            private_values: tuple[str, ...] = ()
            with private_wire():
                if call.credential_scope is not None:
                    try:
                        lease = self._lease_secret(call.credential_scope, plan)  # type: ignore[misc]
                        with lease as secret:
                            if (
                                not isinstance(secret, str)
                                or not 3 <= len(secret) <= 1024
                                or any(ord(c) < 33 or ord(c) > 126 for c in secret)
                            ):
                                raise PluginBrokerProblem("credential-denied")
                            headers["Authorization"] = "Bearer " + secret
                            private_values = (secret,)
                            return await self._send(plan.destination, call, path, pairs, headers, private_values)
                    except PluginBrokerProblem:
                        raise
                    except Exception:
                        raise PluginBrokerProblem("credential-denied") from None
                return await self._send(plan.destination, call, path, pairs, headers, private_values)

    async def _send(
        self,
        destination: PluginDestination,
        call: PluginBrokerCall,
        path: str,
        pairs: tuple[tuple[str, str], ...],
        headers: dict[str, str],
        private_values: tuple[str, ...],
    ) -> PluginBrokerResponse:
        port = "" if destination.port == 443 else f":{destination.port}"
        url = f"https://{destination.host}{port}{path}"
        timeout = {name: _TIMEOUT for name in ("connect", "read", "write", "pool")}
        try:
            request = httpx2.Request(
                "GET",
                url,
                params=httpx2.QueryParams(pairs) if pairs else None,
                headers=headers,
                extensions={"timeout": timeout},
            )
            # The provider sees encoded bytes, not Python character counts.
            if len(request.url.raw_path) > _MAX_WIRE_TARGET:
                raise PluginBrokerProblem("route-denied")
        except PluginBrokerProblem:
            raise
        except Exception:
            raise PluginBrokerProblem("route-denied") from None
        try:
            transport = self._transport_factory(destination, path)
        except Exception:
            raise PluginBrokerProblem("provider-unavailable") from None
        response = None
        try:
            async with asyncio.timeout(_TIMEOUT):
                response = await transport.handle_async_request(request)
                status = response.status_code
                if 300 <= status < 400:
                    raise PluginBrokerProblem("redirect-denied")
                if status != 200:
                    raise PluginBrokerProblem("provider-unavailable")
                body = await read_response(response, _MAX_RESPONSE)
                value, applied = sanitize(bounded_json(body), private_values)
                if call.operation == "repository-metadata":
                    try:
                        metadata = PluginRepositoryMetadata.model_validate(value)
                        if metadata.repository_id != call.repository_id:
                            raise ValueError("plugin-repository-metadata-identity-mismatch")
                        value = metadata.model_dump(mode="json", by_alias=True, exclude_none=True)
                    except ValueError:
                        raise PluginBrokerProblem("incompatible-response") from None
                clean = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("ascii")
                if len(clean) > _MAX_RESPONSE:
                    raise PluginBrokerProblem("response-too-large")
                return PluginBrokerResponse(body=clean, redacted=applied)
        except PluginBrokerProblem:
            raise
        except ProviderProblem as error:
            code = (
                error.code
                if error.code in {"response-too-large", "incompatible-response", "timeout"}
                else "provider-unavailable"
            )
            raise PluginBrokerProblem(code) from None
        except TimeoutError:
            raise PluginBrokerProblem("timeout") from None
        except Exception:
            raise PluginBrokerProblem("provider-unavailable") from None
        finally:
            close_failed = False
            try:
                if response is not None:
                    await response.aclose()
            except Exception:
                close_failed = True
            try:
                await transport.aclose()
            except Exception:
                close_failed = True
            finally:
                headers.clear()
            if close_failed:
                raise PluginBrokerProblem("provider-unavailable") from None
