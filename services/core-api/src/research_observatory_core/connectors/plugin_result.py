"""Versioned, source-reported connector assertions from an untrusted worker.

The worker cannot select project identity, source namespace, retrieval time,
rights, policy, package provenance, or a canonical Work. Core binds those facts
after validating this limited scientific payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .contracts import (
    ConnectorModel,
    ConnectorRecord,
    InvocationId,
    ProviderIdentifier,
    SourceField,
    SourceTerms,
)
from .plugin_manifest import Operation, PluginInvocationPlan
from .transport import bounded_json


class PluginResultProblem(ValueError):
    def __init__(self) -> None:
        super().__init__("plugin-worker-output-invalid")


class PluginWorkerField(ConnectorModel):
    name: Annotated[str, Field(strict=True, pattern=r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")]
    encoding: Literal["text", "json"]
    value: Annotated[str, Field(strict=True, max_length=65536)] = Field(repr=False)


class PluginWorkerRecord(ConnectorModel):
    raw_identifier: ProviderIdentifier = Field(repr=False)
    identifiers: Annotated[tuple[ProviderIdentifier, ...], Field(max_length=64)] = Field(repr=False)
    fields: Annotated[tuple[PluginWorkerField, ...], Field(max_length=256)] = Field(repr=False)
    terms: SourceTerms = Field(repr=False)


class PluginWorkerPage(ConnectorModel):
    schema_version: Literal["1.0"]
    invocation_id: InvocationId
    operation: Operation
    records: Annotated[tuple[PluginWorkerRecord, ...], Field(max_length=1000)] = Field(repr=False)
    continuation: Literal["exhausted", "next-page"]
    next_cursor: Annotated[str, Field(strict=True, min_length=1, max_length=4096)] | None = Field(
        default=None, repr=False
    )

    @model_validator(mode="after")
    def coherent_page(self) -> Self:
        if (self.continuation == "next-page") != (self.next_cursor is not None):
            raise ValueError("plugin-worker-cursor-invalid")
        return self


@dataclass(frozen=True, slots=True)
class PluginValidatedPage:
    records: tuple[ConnectorRecord, ...]
    continuation: Literal["exhausted", "next-page"]
    next_cursor: str | None


def validate_plugin_output(plan: PluginInvocationPlan, output: bytes, *, retrieved_at: str) -> PluginValidatedPage:
    """Reject malformed output before encrypted staging or job publication."""

    try:
        if not isinstance(plan, PluginInvocationPlan) or not isinstance(output, bytes):
            raise ValueError
        page = PluginWorkerPage.model_validate(bounded_json(output))
        if page.invocation_id != plan.invocation_id or page.operation != plan.operation:
            raise ValueError
        records = tuple(
            ConnectorRecord(
                provider_id=plan.source_id,
                raw_identifier=record.raw_identifier,
                identifiers=record.identifiers,
                retrieved_at=retrieved_at,
                fields=tuple(
                    SourceField(namespace=plan.source_id, name=field.name, encoding=field.encoding, value=field.value)
                    for field in record.fields
                ),
                terms=record.terms,
            )
            for record in page.records
        )
        return PluginValidatedPage(records, page.continuation, page.next_cursor)
    except Exception:
        raise PluginResultProblem() from None
