"""Bounded typed IR metadata for protected storage; original bytes stay in objects."""

from __future__ import annotations

from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from .import_drafts import Digest, DraftValue, FieldIndex, MappedName, TextValue
from .reference_imports import FieldCandidate, ImportRecord, ImportSource, RawField

type WarningCode = Annotated[str, Field(max_length=64, pattern=r"^[a-z]+(?:-[a-z]+)*$")]
type Warnings = Annotated[tuple[WarningCode, ...], Field(max_length=32)]


class StoredRawField(DraftValue):
    name: Annotated[str, Field(max_length=65536)]
    raw_value: Annotated[str, Field(max_length=65536)]
    warnings: Warnings


class StoredCandidate(DraftValue):
    name: MappedName
    value: TextValue
    source_field_index: FieldIndex


class StoredImportRecord(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    parser_version: Literal["local-reference-imports/1.0.0"] = "local-reference-imports/1.0.0"
    ordinal: Annotated[int, Field(ge=1, le=200000)]
    byte_start: Annotated[int, Field(ge=0, le=268435456)]
    byte_end: Annotated[int, Field(ge=0, le=268435456)]
    line_start: Annotated[int, Field(ge=1, le=268435457)]
    line_end: Annotated[int, Field(ge=1, le=268435457)]
    raw_sha256: Digest
    kind: Literal["record", "header", "directive"]
    status: Literal["parsed", "malformed"]
    fields: Annotated[tuple[StoredRawField, ...], Field(max_length=4096)]
    candidates: Annotated[tuple[StoredCandidate, ...], Field(max_length=4096)]
    warnings: Warnings

    @model_validator(mode="after")
    def locations(self) -> Self:
        if self.byte_end < self.byte_start or self.line_end < self.line_start:
            raise ValueError("import-record-location-order")
        if any(item.source_field_index >= len(self.fields) for item in self.candidates):
            raise ValueError("import-candidate-source-missing")
        if any(not set(item.warnings).issubset(self.warnings) for item in self.fields):
            raise ValueError("import-field-warning-missing")
        return self

    @classmethod
    def from_record(cls, record: ImportRecord) -> Self:
        return cls(
            ordinal=record.ordinal,
            byte_start=record.byte_start,
            byte_end=record.byte_end,
            line_start=record.line_start,
            line_end=record.line_end,
            raw_sha256=record.raw_sha256,
            kind=cast(Literal["record", "header", "directive"], record.kind),
            status=cast(Literal["parsed", "malformed"], record.status),
            fields=tuple(
                StoredRawField(name=item.name, raw_value=item.raw_value, warnings=item.warnings)
                for item in record.fields
            ),
            candidates=tuple(
                StoredCandidate(
                    name=cast(MappedName, item.name), value=item.value, source_field_index=item.source_field_index
                )
                for item in record.candidates
            ),
            warnings=record.warnings,
        )

    def restore(self, source: ImportSource, format_name: str) -> ImportRecord:
        return ImportRecord(
            source=source,
            format_name=format_name,
            ordinal=self.ordinal,
            byte_start=self.byte_start,
            byte_end=self.byte_end,
            line_start=self.line_start,
            line_end=self.line_end,
            raw_sha256=self.raw_sha256,
            raw_bytes=None,
            kind=self.kind,
            status=self.status,
            fields=tuple(RawField(item.name, item.raw_value, item.warnings) for item in self.fields),
            candidates=tuple(
                FieldCandidate(item.name, item.value, item.source_field_index) for item in self.candidates
            ),
            warnings=self.warnings,
        )
