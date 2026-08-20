"""Structured, bounded, content-safe Core process diagnostics."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

_EVENT = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_SAFE_FIELDS = frozenset(
    {
        "attempt",
        "auditContext",
        "callingCapability",
        "moduleId",
        "operation",
        "outcome",
        "pid",
        "purpose",
        "reasonCode",
        "referenceToken",
        "state",
        "traceId",
    }
)
_SENSITIVE_FRAGMENTS = ("authorization", "content", "cookie", "credential", "document", "secret", "text", "token")
_TRACE_ID = re.compile(r"^[a-f0-9]{32}$")
_CAPABILITY = re.compile(r"^CAP-[0-9]{2}(?:\.S[0-9]{2})?$")
_SECRET_PURPOSES = frozenset(
    {"connector-authentication", "object-encryption", "provider-authentication", "signing-verification"}
)


def _safe_value(key: str, value: Any) -> str | int | bool | None:
    if key not in _SAFE_FIELDS:
        return "[REDACTED]"
    if key in {"auditContext", "referenceToken"}:
        return value if isinstance(value, str) and _TRACE_ID.fullmatch(value) else "[REDACTED]"
    if key == "callingCapability":
        return value if isinstance(value, str) and _CAPABILITY.fullmatch(value) else "[REDACTED]"
    if key == "operation":
        return value if value in {"put", "lease"} else "[REDACTED]"
    if key == "outcome":
        return value if value == "authorized" else "[REDACTED]"
    if key == "purpose":
        return value if value in _SECRET_PURPOSES else "[REDACTED]"
    if any(fragment in key.casefold() for fragment in _SENSITIVE_FRAGMENTS):
        return "[REDACTED]"
    if key in {"attempt", "pid"} and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if key in {"moduleId", "reasonCode", "state"} and isinstance(value, str) and _EVENT.fullmatch(value):
        return value
    if key == "traceId" and isinstance(value, str) and _TRACE_ID.fullmatch(value):
        return value
    return "[REDACTED]"


def build_log_record(
    event: str,
    *,
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    fields: Mapping[str, Any] | None = None,
) -> dict[str, str | int | bool | None]:
    if not _EVENT.fullmatch(event):
        raise ValueError("log event must be a canonical dotted identifier")
    record: dict[str, str | int | bool | None] = {
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": level,
        "event": event,
    }
    for key, value in (fields or {}).items():
        if not _FIELD.fullmatch(key):
            raise ValueError("log field names must be canonical identifiers")
        record[key] = _safe_value(key, value)
    return record


def emit_log_record(
    event: str,
    *,
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    fields: Mapping[str, Any] | None = None,
) -> None:
    print(json.dumps(build_log_record(event, level=level, fields=fields), sort_keys=True), file=sys.stderr, flush=True)
