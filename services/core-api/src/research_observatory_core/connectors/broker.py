"""Core-owned one-page execution; no implicit query, credential or rights grant."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpcore2
import httpx2

from ..domain_contracts import new_uuid_v7
from ..ports.connector_runtime import (
    ConnectorAuthority,
    ConnectorAuthorityStamp,
    ConnectorCacheEntry,
    ConnectorPageRepository,
    ConnectorPublication,
    ConnectorStage,
)
from ..ports.connectors import ConnectorCancellation
from ..ports.credential_store import (
    CredentialStore,
    CredentialStoreProblem,
    SecretAccessContext,
    SecretPurpose,
    SecretReference,
)
from .contracts import (
    CacheObservation,
    ConnectorError,
    ConnectorRequest,
    ConnectorResultPage,
    ErrorCode,
    RateLimitState,
    ResponseRetention,
)
from .providers import MappedPage, ProviderProblem, WireQuery, compile_request, map_response, source_terms
from .settings import ConnectorSettings
from .transport import PublicHTTPTransport, bounded_json, private_wire, read_response, sanitize


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(slots=True)
class _Bucket:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_start: float = 0.0
    interval: float = 1.0
    failures: int = 0
    open_until: float = 0.0
    retry_until: float = 0.0


class ProviderRateController:
    """One instance per Core runtime, shared by every project/adapter/retry."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def bucket(self, provider: str) -> _Bucket:
        return self._buckets.setdefault(provider, _Bucket())


async def _cancellable[Result](work: Awaitable[Result], cancellation: ConnectorCancellation) -> Result:
    task = asyncio.ensure_future(work)
    try:
        while not task.done():
            if cancellation.cancelled:
                raise ProviderProblem("cancelled")
            await asyncio.wait((task,), timeout=0.05)
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def _age(now: str, earlier: str) -> int:
    return int(
        (
            datetime.fromisoformat(now.replace("Z", "+00:00")) - datetime.fromisoformat(earlier.replace("Z", "+00:00"))
        ).total_seconds()
        * 1000
    )


def _retry_after(headers: httpx2.Headers, now: str) -> float | None:
    value = headers.get("retry-after")
    if value is None or len(value) > 128:
        return None
    try:
        if value.isascii() and value.isdecimal():
            return float(int(value))
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            return None
        return max(0.0, (target - datetime.fromisoformat(now.replace("Z", "+00:00"))).total_seconds())
    except TypeError, ValueError, OverflowError:
        return None


def _advertised_interval(headers: httpx2.Headers) -> float:
    count, interval = headers.get("x-rate-limit-limit", ""), headers.get("x-rate-limit-interval", "")
    if (
        len(interval) <= 32
        and re.fullmatch(r"[1-9][0-9]{0,8}", count)
        and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?s", interval)
    ):
        return max(1.0, float(interval[:-1]) / int(count))
    return 1.0


@dataclass(frozen=True, slots=True)
class _Received:
    status: int
    body: bytes | None = field(repr=False)
    redacted: bool
    etag: str | None = field(repr=False)
    last_modified: str | None = field(repr=False)
    retry_after: float | None
    interval: float


class ConnectorBroker:
    def __init__(
        self,
        *,
        authority: ConnectorAuthority,
        repository: ConnectorPageRepository,
        rates: ProviderRateController,
        transport: httpx2.AsyncBaseTransport | None = None,
        credentials: CredentialStore | None = None,
        key_references: dict[str, SecretReference] | None = None,
        contact_references: dict[str, SecretReference] | None = None,
        settings: ConnectorSettings | None = None,
        now: Callable[[], str] = utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        publication: ConnectorPublication | None = None,
    ):
        self._authority, self._repository, self._rates = authority, repository, rates
        self._transport = transport or PublicHTTPTransport()
        self._credentials = credentials
        self._keys, self._contacts = dict(key_references or {}), dict(contact_references or {})
        if settings is not None and (credentials is not None or self._keys or self._contacts):
            raise ValueError("connector-private-configuration-conflict")
        self._settings = settings
        self._now, self._sleep = now, sleep
        self._publication = publication

    def _guard[Result](
        self,
        request: ConnectorRequest,
        stage: ConnectorStage,
        stamp: ConnectorAuthorityStamp | None,
        action: Callable[[ConnectorAuthorityStamp], Result],
    ) -> Result:
        def run(current: ConnectorAuthorityStamp) -> Result:
            if current.project_id != request.project_id or (stamp is not None and current != stamp):
                raise ProviderProblem("policy-denied")
            return action(current)

        return self._authority.guard(request, stage, run)

    def _secret(self, reference: SecretReference, request: ConnectorRequest, stack: ExitStack) -> str:
        if self._credentials is None:
            raise ProviderProblem("not-configured")
        context = SecretAccessContext(
            "CAP-04.S02", SecretPurpose.CONNECTOR_AUTHENTICATION, request.invocation_id.replace("-", "")
        )
        try:
            _, lease = self._credentials.lease_record(reference, context)
            stack.enter_context(lease)
            value = lease.use(lambda view: bytes(view).decode("utf-8"))
            if not 3 <= len(value) <= 1024 or any(ord(char) < 33 or ord(char) > 126 for char in value):
                raise ProviderProblem("not-configured")
            return value
        except CredentialStoreProblem, UnicodeError:
            raise ProviderProblem("not-configured") from None

    async def _exchange(
        self,
        request: ConnectorRequest,
        plan: WireQuery,
        stamp: ConnectorAuthorityStamp,
        cache: ConnectorCacheEntry | None,
    ) -> _Received:
        with ExitStack() as stack, private_wire():
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "User-Agent": "ResearchObservatory/0.1 (scholarly metadata)",
            }
            pairs = list(plan.parameters)
            private_values = []

            def credentials(current):
                key = contact = None
                if self._settings is not None:
                    connection = stack.enter_context(
                        self._settings.lease(
                            request.provider_id,
                            SecretAccessContext(
                                "CAP-04.S02",
                                SecretPurpose.CONNECTOR_AUTHENTICATION,
                                request.invocation_id.replace("-", ""),
                            ),
                        )
                    )
                    key, contact = connection.key, connection.contact
                else:
                    if request.provider_id in self._keys:
                        key = self._secret(self._keys[request.provider_id], request, stack)
                    if request.provider_id in self._contacts:
                        contact = self._secret(self._contacts[request.provider_id], request, stack)
                if key is not None:
                    private_values.append(key)
                    if request.provider_id == "openalex":
                        headers["Authorization"] = "Bearer " + key
                    elif request.provider_id == "semantic-scholar":
                        headers["x-api-key"] = key
                    else:
                        raise ProviderProblem("unsupported-operation")
                if contact is not None:
                    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact) is None:
                        raise ProviderProblem("not-configured")
                    private_values.append(contact)
                    pairs.append(("email" if request.provider_id == "unpaywall" else "mailto", contact))
                elif request.provider_id == "unpaywall":
                    raise ProviderProblem("not-configured")

            self._guard(request, "dispatch", stamp, credentials)
            if cache is not None:
                if cache.etag:
                    headers["If-None-Match"] = cache.etag
                elif cache.last_modified:
                    headers["If-Modified-Since"] = cache.last_modified
            seconds = request.policy.timeout_ms / 1000
            if plan.body is not None:
                headers["Content-Type"] = "application/json"
            wire = httpx2.Request(
                plan.method,
                "https://" + plan.host + plan.path,
                params=httpx2.QueryParams(tuple(pairs)) if pairs else None,
                headers=headers,
                content=plan.body or b"",
                extensions={"timeout": {key: seconds for key in ("connect", "read", "write", "pool")}},
            )
            response = None
            try:
                async with asyncio.timeout(seconds):
                    response = await self._transport.handle_async_request(wire)
                    if response.status_code == 200:
                        body = await read_response(response, request.policy.maximum_response_bytes)
                        value, applied = sanitize(bounded_json(body), tuple(private_values))
                        body = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode(
                            "ascii"
                        )
                        if len(body) > request.policy.maximum_response_bytes:
                            raise ProviderProblem("response-too-large")
                    else:
                        # Errors, redirects and 304 never contribute provider bytes
                        # to diagnostics, replay, normalized fields or provenance.
                        body, applied = None, False
                    validators = []
                    for name in ("etag", "last-modified"):
                        value = response.headers.get(name)
                        clean, changed = sanitize(value, tuple(private_values))
                        validators.append(
                            clean
                            if value and not changed and len(value) <= 1024 and all(32 <= ord(x) < 127 for x in value)
                            else None
                        )
                    return _Received(
                        response.status_code,
                        body,
                        applied,
                        validators[0],
                        validators[1],
                        _retry_after(response.headers, self._now()),
                        _advertised_interval(response.headers),
                    )
            except httpx2.TimeoutException, httpcore2.TimeoutException, TimeoutError:
                raise ProviderProblem("timeout") from None
            except httpx2.HTTPError, httpcore2.NetworkError, httpcore2.ProtocolError, OSError:
                raise ProviderProblem("provider-unavailable") from None
            finally:
                try:
                    if response is not None:
                        await asyncio.wait_for(response.aclose(), timeout=min(seconds, 2.0))
                except httpx2.HTTPError, httpcore2.NetworkError, httpcore2.ProtocolError, OSError, TimeoutError:
                    raise ProviderProblem("provider-unavailable") from None
                finally:
                    headers.clear()
                    pairs.clear()
                    private_values.clear()

    def _page(
        self,
        request: ConnectorRequest,
        bucket: _Bucket,
        *,
        mapped: MappedPage | None = None,
        retrieved_at: str | None = None,
        body: bytes | None = None,
        redacted: bool = False,
        cache: CacheObservation | None = None,
        error: ErrorCode | None = None,
        retry_after_ms: int | None = None,
        retain: bool = False,
    ) -> ConnectorResultPage:
        now = self._now()
        digest = hashlib.sha256(body).hexdigest() if body is not None else None
        retained = body is not None and retain and request.policy.raw_retention == "if-permitted"
        response = ResponseRetention(
            body_state="retained" if retained else "permitted-fields-only" if body is not None else "unavailable",
            object_sha256=digest if retained else None,
            content_sha256=digest,
            byte_length=len(body) if body is not None else None,
            redaction="applied" if redacted else "not-required" if body is not None else "unavailable",
            reason="permitted" if retained else "policy" if body is not None else "not-received",
        )
        terminal = error in {
            "authentication",
            "permission-denied",
            "policy-denied",
            "cancelled",
            "not-configured",
            "unsupported-operation",
            "invalid-query",
            "invalid-cursor",
        }
        return ConnectorResultPage(
            schema_version="1.0",
            observation_id=new_uuid_v7(),
            request=request,
            observed_at=now,
            retrieved_at=retrieved_at,
            terms=mapped.terms if mapped else source_terms(request.provider_id),
            outcome="complete" if error is None else "failed",
            continuation=("next-page" if mapped and mapped.next_cursor else "exhausted")
            if error is None
            else "unavailable"
            if terminal
            else "retry-current",
            next_cursor=mapped.next_cursor if mapped else None,
            records=mapped.records if mapped else (),
            errors=()
            if error is None
            else (
                ConnectorError(
                    code=error,
                    retryable=error in {"rate-limit", "provider-unavailable", "timeout"},
                    retry_after_ms=retry_after_ms,
                ),
            ),
            warnings=mapped.warnings if mapped else (),
            rate=RateLimitState(
                provider_id=request.provider_id,
                observed_at=now,
                remaining=None,
                retry_after_ms=retry_after_ms,
                circuit="open" if bucket.open_until > self._rates.clock() else "closed",
            ),
            response=response,
            cache=cache
            or CacheObservation(
                state="disabled" if request.policy.cache_mode == "bypass" else "miss", age_ms=None, request_sha256=None
            ),
        )

    async def fetch(self, request: ConnectorRequest, *, cancellation: ConnectorCancellation) -> ConnectorResultPage:
        request = ConnectorRequest.model_validate(request)
        bucket = self._rates.bucket(request.provider_id)
        stamp = None
        locked = False
        page = None
        body, etag, modified = None, None, None
        try:
            plan = compile_request(request)
            if cancellation.cancelled:
                raise ProviderProblem("cancelled")
            try:
                request.assert_resumable(self._now())
            except ValueError:
                raise ProviderProblem("invalid-cursor") from None
            stamp = self._guard(request, "admission", None, lambda current: current)

            # New observations and replays use current configuration even when
            # scientific response bytes are cached. Authorization precedes access.
            def check_settings(current):
                if self._settings is not None:
                    with self._settings.lease(
                        request.provider_id,
                        SecretAccessContext(
                            "CAP-04.S02", SecretPurpose.CONNECTOR_AUTHENTICATION, request.invocation_id.replace("-", "")
                        ),
                    ):
                        pass
                elif request.provider_id == "unpaywall" and request.provider_id not in self._contacts:
                    raise ProviderProblem("not-configured")

            self._guard(request, "cache", stamp, check_settings)
            replayed = self._guard(request, "cache", stamp, lambda current: self._repository.replay(request))
            if replayed is not None:
                if not stamp.retain_body and (
                    replayed.response.body_state == "retained"
                    or any(
                        item.name not in stamp.permitted_fields for record in replayed.records for item in record.fields
                    )
                ):
                    raise ProviderProblem("policy-denied")
                if self._publication is not None:
                    replayed = self._guard(
                        request,
                        "publication",
                        stamp,
                        lambda current: self._repository.publish(
                            replayed,
                            body=None,
                            etag=None,
                            last_modified=None,
                            authority=current,
                            publication=self._publication,
                        ),
                    )
                return ConnectorResultPage.model_validate(replayed)
            cache = None
            if request.policy.cache_mode != "bypass" and stamp.retain_body:
                cache = self._guard(request, "cache", stamp, lambda current: self._repository.cached(request))
                if cache is not None:
                    if cache.project_id != request.project_id or cache.page_sha256 != request.page_sha256():
                        raise ProviderProblem("incompatible-response")
                    age = _age(self._now(), cache.validated_at)
                    if age < 0 or _age(cache.validated_at, cache.retrieved_at) < 0:
                        raise ProviderProblem("incompatible-response")
                    if request.policy.cache_mode == "allow-fresh" and age <= request.policy.maximum_fresh_age_ms:
                        mapped = map_response(request, bounded_json(cache.body), retrieved_at=cache.retrieved_at)
                        if (
                            mapped.next_cursor
                            and mapped.next_cursor.expires_at
                            and mapped.next_cursor.expires_at <= self._now()
                        ):
                            raise ProviderProblem("invalid-cursor")
                        body, etag, modified = cache.body, cache.etag, cache.last_modified
                        page = self._page(
                            request,
                            bucket,
                            mapped=mapped,
                            retrieved_at=cache.retrieved_at,
                            body=body,
                            redacted=cache.redacted,
                            cache=CacheObservation(state="hit", age_ms=age, request_sha256=request.page_sha256()),
                            retain=True,
                        )
            if page is None:
                await _cancellable(bucket.lock.acquire(), cancellation)
                locked = True
                clock = self._rates.clock
                if bucket.retry_until > clock():
                    raise ProviderProblem("rate-limit")
                if bucket.open_until > clock():
                    raise ProviderProblem("provider-unavailable")
                for attempt in range(request.policy.maximum_attempts):
                    delay = max(0.0, bucket.next_start - clock())
                    if delay * 1000 > request.policy.maximum_retry_after_ms:
                        raise ProviderProblem("rate-limit")
                    if delay:
                        await _cancellable(self._sleep(delay), cancellation)
                    self._guard(request, "dispatch", stamp, lambda current: None)
                    if cancellation.cancelled:
                        raise ProviderProblem("cancelled")
                    bucket.next_start = clock() + max(bucket.interval, request.policy.minimum_interval_ms / 1000)
                    received = None
                    try:
                        received = await _cancellable(self._exchange(request, plan, stamp, cache), cancellation)
                        bucket.interval = max(bucket.interval, received.interval)
                        bucket.next_start = max(bucket.next_start, clock() + bucket.interval)
                        status = received.status
                        if status == 200 or (status == 304 and cache is not None) or (status == 404 and plan.singleton):
                            body = cache.body if status == 304 and cache else received.body
                            retrieved = cache.retrieved_at if status == 304 and cache else self._now()
                            mapped = (
                                MappedPage((), None, source_terms(request.provider_id))
                                if status == 404
                                else map_response(request, bounded_json(body or b""), retrieved_at=retrieved)
                            )
                            if (
                                mapped.next_cursor
                                and mapped.next_cursor.expires_at
                                and mapped.next_cursor.expires_at <= self._now()
                            ):
                                raise ProviderProblem("invalid-cursor")
                            etag, modified = (
                                (received.etag or cache.etag, received.last_modified or cache.last_modified)
                                if status == 304 and cache
                                else (received.etag, received.last_modified)
                            )
                            cache_result = (
                                CacheObservation(
                                    state="revalidated",
                                    age_ms=_age(self._now(), retrieved),
                                    request_sha256=request.page_sha256(),
                                )
                                if status == 304
                                else None
                            )
                            page = self._page(
                                request,
                                bucket,
                                mapped=mapped,
                                retrieved_at=retrieved,
                                body=body,
                                redacted=received.redacted or (status == 304 and cache is not None and cache.redacted),
                                cache=cache_result,
                                retain=stamp.retain_body,
                            )
                            bucket.failures, bucket.open_until = 0, 0.0
                            break
                        code: ErrorCode = (
                            "authentication"
                            if status == 401
                            else "permission-denied"
                            if status == 403
                            else "rate-limit"
                            if status == 429
                            else "provider-unavailable"
                            if status >= 500
                            else "policy-denied"
                            if 300 <= status < 400 and status != 304
                            else "incompatible-response"
                            if status == 304
                            else "invalid-query"
                        )
                    except ProviderProblem as problem:
                        code = problem.code
                    retry = code in {"rate-limit", "provider-unavailable", "timeout"}
                    after = received.retry_after if received is not None and retry else None
                    retry_ms = (
                        math.ceil(after * 1000)
                        if after is not None and after * 1000 <= request.policy.maximum_retry_after_ms
                        else None
                    )
                    if after is not None:
                        bucket.retry_until = clock() + after
                    if retry:
                        bucket.failures += 1
                    if bucket.failures >= 3:
                        bucket.open_until = max(clock() + 30, bucket.retry_until)
                    if (
                        not retry
                        or attempt + 1 >= request.policy.maximum_attempts
                        or (after is not None and after * 1000 > request.policy.maximum_retry_after_ms)
                    ):
                        page = self._page(request, bucket, error=code, retry_after_ms=retry_ms)
                        break
                    delay = max(after or 0, (2**attempt) + random.SystemRandom().uniform(0, 0.25))
                    bucket.next_start = max(bucket.next_start, clock() + delay)
            if cancellation.cancelled:
                raise ProviderProblem("cancelled")
            if page is None or stamp is None:
                raise ProviderProblem("incompatible-response")
            if not stamp.retain_body:
                page = ConnectorResultPage.model_validate(
                    page.model_dump()
                    | {
                        "records": tuple(
                            type(record).model_validate(
                                record.model_dump()
                                | {
                                    "fields": tuple(
                                        item for item in record.fields if item.name in stamp.permitted_fields
                                    )
                                }
                            )
                            for record in page.records
                        )
                    }
                )
            saved = self._guard(
                request,
                "publication",
                stamp,
                lambda current: self._repository.publish(
                    page,
                    body=body if page.response.body_state == "retained" else None,
                    etag=etag,
                    last_modified=modified,
                    authority=current,
                    publication=self._publication,
                ),
            )
            return ConnectorResultPage.model_validate(saved)
        except ProviderProblem as problem:
            return self._page(request, bucket, error=problem.code)
        finally:
            if locked:
                bucket.lock.release()

    async def aclose(self) -> None:
        with private_wire():
            try:
                await asyncio.wait_for(self._transport.aclose(), timeout=2.0)
            except httpx2.HTTPError, httpcore2.NetworkError, httpcore2.ProtocolError, OSError, TimeoutError:
                raise ProviderProblem("provider-unavailable") from None
