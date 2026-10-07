"""Portable, versioned parse request and discriminated terminal staged results."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .contracts import DocumentIR, IRValue, ParseBinding
from .selection import ParserSelection, selected_values, selection_sha256


class ParseRequest(IRValue):
    schema_version: Literal["1.0"]
    binding: ParseBinding
    selection: ParserSelection

    @model_validator(mode="after")
    def chosen_binding(self) -> Self:
        source, producer = selected_values(self.selection)
        if (source, producer, selection_sha256(self.selection)) != (
            self.binding.source,
            self.binding.producer,
            self.binding.selection_sha256,
        ) or self.selection.fallback_from_attempt_id == self.binding.attempt.attempt_id:
            raise ValueError("parse-request-selection-mismatch")
        return self


type FailureCode = Literal[
    "parser-failed",
    "parser-timeout",
    "parser-memory-limit",
    "parser-assets-unavailable",
    "parser-runtime-unavailable",
    "parser-input-invalid",
    "parser-input-unsupported",
    "parser-resource-limit",
    "parse-output-invalid",
    "parse-producer-mismatch",
    "parse-source-denied",
    "parse-delivery-denied",
]


class ParseSuccess(IRValue):
    schema_version: Literal["1.0"]
    kind: Literal["success"]
    binding: ParseBinding
    ir: DocumentIR = Field(repr=False)

    @model_validator(mode="after")
    def same_binding(self) -> Self:
        if self.binding != self.ir.binding:
            raise ValueError("parse-result-binding-mismatch")
        return self


class ParseFailure(IRValue):
    schema_version: Literal["1.0"]
    kind: Literal["failure"]
    binding: ParseBinding
    code: FailureCode


class ParseCancelled(IRValue):
    schema_version: Literal["1.0"]
    kind: Literal["cancelled"]
    binding: ParseBinding
    code: Literal["cancelled"]


type ParseResult = Annotated[ParseSuccess | ParseFailure | ParseCancelled, Field(discriminator="kind")]
