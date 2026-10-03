"""Closed, content-free parsing of Core-held connector scientific parameters."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..domain_contracts import is_uuid_v7
from .plugin_broker import PluginBrokerCall
from .plugin_manifest import Operation

_MAX_REQUEST = 4096
_FIELD: dict[Operation, str] = {
    "lookup": "identifier",
    "search": "query",
    "references": "identifier",
    "citations": "identifier",
    "open-access-locations": "identifier",
    "repository-metadata": "repositoryId",
}


class PluginScientificRequestProblem(ValueError):
    def __init__(self) -> None:
        super().__init__("plugin-scientific-request-invalid")


@dataclass(frozen=True, slots=True)
class PluginScientificRequest:
    call: PluginBrokerCall
    previous_invocation_id: str | None


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, value in pairs:
        if key in fields:
            raise PluginScientificRequestProblem()
        fields[key] = value
    return fields


def parse_plugin_scientific_request(input_data: bytes, operation: Operation) -> PluginScientificRequest:
    """The consented bytes authorize exactly one broker call and, for search, one prior page."""

    try:
        if not isinstance(input_data, bytes) or not input_data or len(input_data) > _MAX_REQUEST:
            raise PluginScientificRequestProblem()
        fields = json.loads(input_data.decode("utf-8"), object_pairs_hook=_unique_fields)
        if not isinstance(fields, dict) or any(value is None for value in fields.values()):
            raise PluginScientificRequestProblem()
        required = _FIELD[operation]
        previous: str | None = None
        if operation == "search":
            if required not in fields or not set(fields) <= {"query", "pageSize", "cursor", "previousInvocationId"}:
                raise PluginScientificRequestProblem()
            if ("cursor" in fields) != ("previousInvocationId" in fields):
                raise PluginScientificRequestProblem()
            previous_value = fields.pop("previousInvocationId", None)
            if previous_value is not None:
                if not isinstance(previous_value, str) or not is_uuid_v7(previous_value):
                    raise PluginScientificRequestProblem()
                previous = previous_value
        elif set(fields) != {required}:
            raise PluginScientificRequestProblem()
        call = PluginBrokerCall.model_validate({"operation": operation, **fields})
        return PluginScientificRequest(call, previous)
    except ValueError, UnicodeError, KeyError, TypeError:
        raise PluginScientificRequestProblem() from None
