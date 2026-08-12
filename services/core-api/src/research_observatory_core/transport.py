"""Trace correlation and RFC 9457 problem response helpers."""

from __future__ import annotations

import json
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from .models import ProblemDetail

AsgiReceive = Callable[[], Awaitable[dict[str, Any]]]
AsgiSend = Callable[[dict[str, Any]], Awaitable[None]]
AsgiApp = Callable[[dict[str, Any], AsgiReceive, AsgiSend], Awaitable[None]]

TRACE_HEADER = b"x-trace-id"


def problem_detail(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    trace_id: str,
    retryable: bool,
    remediation: str,
) -> ProblemDetail:
    return ProblemDetail(
        type=f"urn:research-observatory:problem:{code.removeprefix('RO-CORE-').casefold()}",
        title=title,
        status=status,
        detail=detail,
        code=code,
        trace_id=trace_id,
        retryable=retryable,
        remediation=remediation,
    )


class CoreProblem(Exception):
    def __init__(self, problem: ProblemDetail) -> None:
        super().__init__(problem.code)
        self.problem = problem


def _trace_values(scope: dict[str, Any]) -> list[bytes]:
    headers = scope.get("headers")
    if not isinstance(headers, (list, tuple)):
        return []
    result: list[bytes] = []
    for item in headers:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            return []
        name, value = item
        if not isinstance(name, bytes) or not isinstance(value, bytes):
            return []
        if name.lower() == TRACE_HEADER:
            result.append(value)
    return result


class TraceCorrelationMiddleware:
    """Attach one secret-safe trace identity to every local HTTP response."""

    def __init__(self, app: AsgiApp) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: AsgiReceive, send: AsgiSend) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        supplied = _trace_values(scope)
        valid = len(supplied) <= 1 and (
            not supplied or (len(supplied[0]) == 32 and all(value in b"0123456789abcdef" for value in supplied[0]))
        )
        trace_id = supplied[0].decode("ascii") if valid and supplied else secrets.token_hex(16)
        state = scope.setdefault("state", {})
        if not isinstance(state, dict):
            state = {}
            scope["state"] = state
        state["trace_id"] = trace_id

        async def traced_send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [item for item in headers if item[0].lower() != TRACE_HEADER]
                headers.append((TRACE_HEADER, trace_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        if not valid:
            problem = problem_detail(
                status=400,
                code="RO-CORE-TRACE-INVALID",
                title="Trace identifier is invalid",
                detail="The request trace identifier did not use the canonical local format.",
                trace_id=trace_id,
                retryable=False,
                remediation="Retry through the supported desktop client.",
            )
            body = json.dumps(problem.model_dump(mode="json", by_alias=True), separators=(",", ":")).encode("utf-8")
            await traced_send(
                {
                    "type": "http.response.start",
                    "status": 400,
                    "headers": [
                        (b"cache-control", b"no-store"),
                        (b"content-type", b"application/problem+json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await traced_send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, traced_send)
