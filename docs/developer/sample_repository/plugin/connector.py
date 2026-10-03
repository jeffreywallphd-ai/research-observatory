"""One-page synthetic public repository adapter for the signed connector SDK.

This example never opens a file, socket, project, or credential. The parent
broker alone supplies a sanitized public metadata response. Source terms in
the returned page are observations; they are not Core rights decisions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

_CURSOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,4095}\Z")
_REPOSITORY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_UUID_V7 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_NO_REPORT = {"state": "not-reported", "value": None}


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("sample-contract-invalid")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("sample-contract-invalid")


def _document(raw: bytes, *, maximum: int) -> dict[str, Any]:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= maximum:
        raise ValueError("sample-contract-invalid")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields, parse_constant=_reject_constant)
    except UnicodeError, ValueError, RecursionError:
        raise ValueError("sample-contract-invalid") from None
    if not isinstance(value, dict):
        raise ValueError("sample-contract-invalid")
    return value


def _text(value: Any, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 0 < len(value) <= maximum
        or not value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("sample-contract-invalid")
    return value


def _terms(license_value: Any, access: Any) -> dict[str, Any]:
    if not isinstance(access, str) or access not in {"open", "closed", "unknown", "not-reported"}:
        raise ValueError("sample-contract-invalid")
    license_observation = (
        {"state": "reported", "value": _text(license_value, 4096)} if license_value is not None else dict(_NO_REPORT)
    )
    return {"license": license_observation, "terms": dict(_NO_REPORT), "access": access}


def _repository_metadata(source: dict[str, Any], requested_id: str) -> dict[str, Any]:
    if not {"repositoryId", "displayName"} <= source.keys() or set(source) - {
        "repositoryId",
        "displayName",
        "description",
    }:
        raise ValueError("sample-contract-invalid")
    repository_id = _text(source["repositoryId"], 128)
    if _REPOSITORY_ID.fullmatch(repository_id) is None or repository_id != requested_id:
        raise ValueError("sample-contract-invalid")
    fields = [{"name": "displayName", "encoding": "text", "value": _text(source["displayName"], 512)}]
    if source.get("description") is not None:
        fields.append({"name": "description", "encoding": "text", "value": _text(source["description"], 2048)})
    identifier = {"scheme": "repository", "value": repository_id}
    return {
        "rawIdentifier": identifier,
        "identifiers": [identifier],
        "fields": fields,
        "terms": _terms(None, "unknown"),
    }


def _search_record(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict) or set(source) != {"id", "title", "license", "access"}:
        raise ValueError("sample-contract-invalid")
    identifier_value = _text(source["id"], 128)
    if _REPOSITORY_ID.fullmatch(identifier_value) is None:
        raise ValueError("sample-contract-invalid")
    identifier = {"scheme": "repository", "value": identifier_value}
    return {
        "rawIdentifier": identifier,
        "identifiers": [identifier],
        "fields": [{"name": "title", "encoding": "text", "value": _text(source["title"], 65536)}],
        "terms": _terms(source["license"], source["access"]),
    }


def invoke(
    input_data: bytes, broker: Callable[[dict[str, Any]], bytes], operation: str, *, context: Mapping[str, Any]
) -> bytes:
    """Map one broker response into one source-assertions-v1 worker page.

    ``context`` supplies only the Core-owned invocation label. It does not
    authorize the source, project, destination, rights, or any broker call.
    """

    if not callable(broker) or not isinstance(context, Mapping):
        raise ValueError("sample-contract-invalid")
    invocation_id = context.get("invocationId")
    if not isinstance(invocation_id, str) or _UUID_V7.fullmatch(invocation_id) is None:
        raise ValueError("sample-contract-invalid")
    request = _document(input_data, maximum=4096)
    if operation == "repository-metadata":
        if set(request) != {"repositoryId"}:
            raise ValueError("sample-contract-invalid")
        repository_id = _text(request["repositoryId"], 128)
        if _REPOSITORY_ID.fullmatch(repository_id) is None:
            raise ValueError("sample-contract-invalid")
        response = _document(broker({"operation": operation, "repositoryId": repository_id}), maximum=10 * 1024 * 1024)
        records = [_repository_metadata(response, repository_id)]
        continuation, next_cursor = "exhausted", None
    elif operation == "search":
        if set(request) - {"query", "pageSize", "cursor", "previousInvocationId"} or "query" not in request:
            raise ValueError("sample-contract-invalid")
        query = _text(request["query"], 4096)
        page_size = request.get("pageSize")
        if page_size is not None and (type(page_size) is not int or not 1 <= page_size <= 1000):
            raise ValueError("sample-contract-invalid")
        cursor = request.get("cursor")
        predecessor = request.get("previousInvocationId")
        if ("cursor" in request) != ("previousInvocationId" in request):
            raise ValueError("sample-contract-invalid")
        if "cursor" in request and (not isinstance(cursor, str) or _CURSOR.fullmatch(cursor) is None):
            raise ValueError("sample-contract-invalid")
        if "previousInvocationId" in request and (
            not isinstance(predecessor, str) or _UUID_V7.fullmatch(predecessor) is None or predecessor == invocation_id
        ):
            raise ValueError("sample-contract-invalid")
        call: dict[str, Any] = {"operation": operation, "query": query}
        if page_size is not None:
            call["pageSize"] = page_size
        if cursor is not None:
            call["cursor"] = cursor
        response = _document(broker(call), maximum=10 * 1024 * 1024)
        if set(response) - {"records", "nextCursor"} or not isinstance(response.get("records"), list):
            raise ValueError("sample-contract-invalid")
        sources = response["records"]
        if len(sources) > (page_size or 1000):
            raise ValueError("sample-contract-invalid")
        records = [_search_record(source) for source in sources]
        next_cursor = response.get("nextCursor")
        if next_cursor is not None and (
            not isinstance(next_cursor, str)
            or _CURSOR.fullmatch(next_cursor) is None
            or next_cursor == cursor
            or not records
        ):
            raise ValueError("sample-contract-invalid")
        continuation = "next-page" if next_cursor is not None else "exhausted"
    else:
        raise ValueError("sample-operation-unsupported")
    page: dict[str, Any] = {
        "schemaVersion": "1.0",
        "invocationId": invocation_id,
        "operation": operation,
        "records": records,
        "continuation": continuation,
    }
    if next_cursor is not None:
        page["nextCursor"] = next_cursor
    return json.dumps(page, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("ascii")
