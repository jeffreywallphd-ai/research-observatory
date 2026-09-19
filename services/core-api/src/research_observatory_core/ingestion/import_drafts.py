"""Immutable preview decisions, distinct from source observations and commit authority.

All bibliographic values belong in protected project storage. A digest identifies
a draft; neither constructing these values nor hashing them authorizes a commit,
an object read, an export or a workflow transition.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable, Iterator
from typing import Annotated, Literal, Self, cast

from pydantic import ConfigDict, Field, model_validator

from ..models import ContractModel
from .reference_imports import PARSER_VERSION, ImportRecord, normalize_import_field

type Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
type Identity = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
type ProjectIdentity = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
]
type MappedName = Literal["title", "doi", "year", "author", "container"]
type TextValue = Annotated[str, Field(min_length=1, max_length=65536)]
type Revision = Annotated[int, Field(strict=True, ge=1, le=2147483647)]
type FieldIndex = Annotated[int, Field(strict=True, ge=0, le=4095)]
type RightsAction = Literal["store", "inspect", "index", "derive", "model-use", "quote", "export", "share"]


class DraftValue(ContractModel):
    model_config = ConfigDict(strict=True, revalidate_instances="always")


class ImportPermission(DraftValue):
    value: Literal["permitted", "denied", "unknown"] = "unknown"
    basis: Literal["not-reported", "researcher-confirmed"] = "not-reported"

    @model_validator(mode="after")
    def explicit_basis(self) -> Self:
        if self.value != "unknown" and self.basis != "researcher-confirmed":
            raise ValueError("rights-require-explicit-basis")
        return self


class ImportRights(DraftValue):
    store: ImportPermission = Field(default_factory=ImportPermission)
    inspect: ImportPermission = Field(default_factory=ImportPermission)
    index: ImportPermission = Field(default_factory=ImportPermission)
    derive: ImportPermission = Field(default_factory=ImportPermission)
    model_use: ImportPermission = Field(default_factory=ImportPermission, alias="model-use")
    quote: ImportPermission = Field(default_factory=ImportPermission)
    export: ImportPermission = Field(default_factory=ImportPermission)
    share: ImportPermission = Field(default_factory=ImportPermission)

    def permits(self, action: RightsAction) -> bool:
        # Runtime callers cannot turn an unknown action into a default grant.
        if action not in {"store", "inspect", "index", "derive", "model-use", "quote", "export", "share"}:
            return False
        permission: ImportPermission = getattr(self, action.replace("-", "_"))
        return permission.value == "permitted" and permission.basis == "researcher-confirmed"


class FieldMapping(DraftValue):
    source_name: TextValue
    occurrence: FieldIndex
    target: MappedName


class MappingProfile(DraftValue):
    profile_id: Identity
    revision: Revision
    predecessor_revision: Revision | None
    mode: Literal["automatic", "columns"]
    bindings: tuple[FieldMapping, ...] = Field(max_length=256)

    @model_validator(mode="after")
    def coherent_revision(self) -> Self:
        if self.predecessor_revision != (self.revision - 1 if self.revision > 1 else None):
            raise ValueError("mapping-predecessor-mismatch")
        selectors = [(binding.source_name, binding.occurrence) for binding in self.bindings]
        if len(set(selectors)) != len(selectors):
            raise ValueError("duplicate-mapping-selector")
        if self.mode == "automatic" and self.bindings:
            raise ValueError("automatic-mapping-has-bindings")
        return self


class MappedField(DraftValue):
    name: MappedName
    value: TextValue
    source_field_index: FieldIndex | None
    origin: Literal["candidate", "mapping", "correction"]

    @model_validator(mode="after")
    def provenance_and_size(self) -> Self:
        if (self.origin == "correction") != (self.source_field_index is None):
            raise ValueError("mapped-field-origin-mismatch")
        if len(self.value.encode("utf-8")) > 65536 or not self.value.strip():
            raise ValueError("mapped-field-limit")
        if any(ord(char) < 32 or ord(char) == 127 for char in self.value):
            raise ValueError("mapped-field-control-character")
        return self


class MappingPreview(DraftValue):
    fields: tuple[MappedField, ...]
    conflicts: tuple[MappedName, ...]
    warnings: tuple[str, ...]


class RecordDecision(DraftValue):
    record_key: Digest
    ordinal: Annotated[int, Field(strict=True, ge=1, le=10000000)]
    included: bool
    fields: tuple[MappedField, ...] = Field(max_length=4096)
    rights: ImportRights | None = None


class ImportOptions(DraftValue):
    duplicate_policy: Literal["review"] = "review"
    malformed_policy: Literal["exclude-and-report"] = "exclude-and-report"


class DraftAuthority(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    preview_id: Identity
    source_sha256: Digest
    parser_version: Literal["local-reference-imports/1.0.0"] = PARSER_VERSION
    mapping: MappingProfile
    rights: ImportRights
    options: ImportOptions = Field(default_factory=ImportOptions)


def _conflicts(fields: Iterable[MappedField]) -> tuple[MappedName, ...]:
    values: dict[MappedName, set[str]] = {}
    for field in fields:
        values.setdefault(field.name, set()).add(field.value)
    return tuple(sorted(name for name, candidates in values.items() if name != "author" and len(candidates) > 1))


def propose_fields(record: ImportRecord, mapping: MappingProfile) -> MappingPreview:
    """Suggestions only; ambiguous singleton fields remain visible, not merged."""
    mapping = MappingProfile.model_validate(mapping)
    if record.kind != "record" or record.status != "parsed":
        return MappingPreview(fields=(), conflicts=(), warnings=record.warnings)
    warnings = set(record.warnings)
    fields: list[MappedField] = []
    if mapping.mode == "automatic":
        for candidate in record.candidates:
            fields.append(
                MappedField(
                    name=cast(MappedName, candidate.name),
                    value=candidate.value,
                    source_field_index=candidate.source_field_index,
                    origin="candidate",
                )
            )
    else:
        if record.format_name != "csv":
            raise ValueError("column-mapping-requires-csv")
        positions: dict[tuple[str, int], int] = {}
        counts: dict[str, int] = {}
        for index, field in enumerate(record.fields):
            occurrence = counts.get(field.name, 0)
            positions[(field.name, occurrence)] = index
            counts[field.name] = occurrence + 1
        for binding in mapping.bindings:
            selected_index = positions.get((binding.source_name, binding.occurrence))
            if selected_index is None:
                warnings.add("mapping-source-missing")
                continue
            mapped = normalize_import_field(
                binding.target, record.fields[selected_index].raw_value, selected_index, warnings
            )
            if mapped is not None:
                fields.append(
                    MappedField(
                        name=binding.target, value=mapped.value, source_field_index=selected_index, origin="mapping"
                    )
                )
    return MappingPreview(fields=tuple(fields), conflicts=_conflicts(fields), warnings=tuple(sorted(warnings)))


def review_record(
    record: ImportRecord,
    *,
    included: bool,
    fields: tuple[MappedField, ...],
    rights: ImportRights | None = None,
) -> RecordDecision:
    """Bind a decision to a real IR record; no source or canonical state mutates."""
    decision = RecordDecision(
        record_key=record.record_key, ordinal=record.ordinal, included=included, fields=fields, rights=rights
    )
    if included and (record.kind != "record" or record.status != "parsed"):
        raise ValueError("record-not-importable")
    if included and _conflicts(decision.fields):
        raise ValueError("conflicting-mapped-field")
    for field in decision.fields:
        index = field.source_field_index
        if index is not None:
            if index >= len(record.fields):
                raise ValueError("source-field-mismatch")
            if field.origin == "candidate":
                valid = any(
                    candidate.name == field.name
                    and candidate.value == field.value
                    and candidate.source_field_index == index
                    for candidate in record.candidates
                )
            else:
                candidate = (
                    normalize_import_field(field.name, record.fields[index].raw_value, index, set())
                    if record.format_name == "csv"
                    else None
                )
                valid = candidate is not None and candidate.value == field.value
            if not valid:
                raise ValueError("source-field-mismatch")
        if field.name == "doi" and normalize_import_field("doi", field.value, 0, set()) is None:
            raise ValueError("invalid-mapped-doi")
    return decision


def _canonical(value: DraftValue) -> bytes:
    return json.dumps(
        value.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def effective_draft_sha256(authority: DraftAuthority, decisions: Iterable[RecordDecision]) -> str:
    """Versioned, streaming serialization; repository supplies the full ordered draft.

    This does not certify source traversal, current rights or record membership.
    The service must check those again before accepting any consequential action.
    Preview identity is deliberately excluded: identical scientific decisions can
    be replayed from a new UI session. Project scope is retained.
    """
    authority = DraftAuthority.model_validate(authority)
    header = authority.model_dump(mode="json", by_alias=True, exclude={"preview_id"})
    digest = hashlib.sha256(b'["effective-import-draft/1",')
    digest.update(json.dumps(header, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
    digest.update(b",[")
    previous = 0
    for decision in decisions:
        decision = RecordDecision.model_validate(decision)
        if decision.ordinal <= previous:
            raise ValueError("draft-record-order")
        if previous:
            digest.update(b",")
        digest.update(_canonical(decision))
        previous = decision.ordinal
    digest.update(b"]]")
    return digest.hexdigest()


def spreadsheet_cell(value: str) -> str:
    """Quoting is not formula neutralization; protected raw content stays intact."""
    active = value.lstrip().startswith(("=", "+", "-", "@")) or (value and ord(value[0]) < 32)
    return "'" + value if active else value


def diagnostic_csv(records: Iterable[ImportRecord]) -> Iterator[str]:
    """Content-free diagnostic rows only. Caller must verify complete source parse.

    No filename, digest, local path, raw value, title or exception text is exported.
    A content-bearing export is a separate action requiring current export rights.
    """
    yield "ordinal,line_start,line_end,status,diagnostic\r\n"
    for record in records:
        for warning in record.warnings or ("none",):
            if len(warning) > 64 or re.fullmatch(r"[a-z]+(?:-[a-z]+)*", warning) is None:
                raise ValueError("invalid-diagnostic-code")
            stream = io.StringIO(newline="")
            csv.writer(stream).writerow(
                (record.ordinal, record.line_start, record.line_end, record.status, spreadsheet_cell(warning))
            )
            yield stream.getvalue()
