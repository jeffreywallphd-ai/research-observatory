"""Closed first-party registry and deterministic, recorded parser preference.

Caller admission/basis and runtime availability are trusted Core observations,
not request/worker grants. Selection never replaces current protected-read and
delivery rights. No document-supplied loader or third-party parser is exposed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Self, cast

from pydantic import model_validator

from ..domain_contracts import is_uuid_v7
from .contracts import Identity, IRValue, ParserDescriptor, SourceIdentity, Token

_FORMAT_ORDER = {name: order for order, name in enumerate(("jats", "tei", "xml", "html", "pdf", "docx", "plain-text"))}
_FAMILIES = {
    "ro-native-structured": ("native", frozenset({"jats", "tei", "xml", "html"})),
    "ro-native-text": ("native", frozenset({"plain-text"})),
    "ro-docling-cpu": ("docling-cpu", frozenset({"pdf", "docx"})),
    "ro-page-text-fallback": ("degraded-inspection", frozenset({"pdf"})),
}
type Availability = Literal["available", "unavailable", "rights-denied"]
type SelectionBasis = Literal["primary", "explicit-alternative", "same-object", "unproven"]
type Disposition = Literal[
    "selected",
    "eligible",
    "unavailable",
    "rights-denied",
    "equivalence-unproven",
    "source-mismatch",
    "format-unsupported",
]


class SelectionProblem(ValueError):
    """Content-free policy/registry refusal."""


@dataclass(frozen=True, slots=True)
class RegisteredParser:
    descriptor: ParserDescriptor
    availability: Literal["available", "unavailable"]


@dataclass(frozen=True, slots=True)
class SelectionSource:
    source: SourceIdentity
    availability: Availability
    basis: SelectionBasis


class ParserRegistry:
    """Core-created snapshot of exactly the approved first-party families."""

    def __init__(self, entries: tuple[RegisteredParser, ...]) -> None:
        admitted: dict[str, RegisteredParser] = {}
        failed = False
        for entry in entries:
            try:
                descriptor = ParserDescriptor.model_validate(entry.descriptor)
            except ValueError:
                failed = True
                continue
            family = _FAMILIES.get(descriptor.parser_id)
            if (
                family is None
                or descriptor.kind != family[0]
                or frozenset(descriptor.input_formats) != family[1]
                or descriptor.parser_id in admitted
                or entry.availability not in {"available", "unavailable"}
                or (descriptor.kind == "docling-cpu" and descriptor.version != "2.126.0")
                or (descriptor.kind != "docling-cpu" and not descriptor.version.startswith("1."))
                or (
                    descriptor.kind == "docling-cpu"
                    and entry.availability == "available"
                    and not any(asset.component == "docling-assets" for asset in descriptor.assets)
                )
            ):
                failed = True
                continue
            admitted[descriptor.parser_id] = RegisteredParser(descriptor, entry.availability)
        if failed:
            raise SelectionProblem("parser-registry-invalid")
        self._entries = tuple(admitted[key] for key in sorted(admitted))

    @property
    def entries(self) -> tuple[RegisteredParser, ...]:
        return self._entries


class RegistryObservation(IRValue):
    descriptor: ParserDescriptor
    availability: Literal["available", "unavailable"]


class SourceSelection(IRValue):
    source: SourceIdentity
    basis: SelectionBasis
    disposition: Disposition


class ParserSelection(IRValue):
    schema_version: Literal["1.0"]
    policy_version: Literal["ro-parser-policy-1"]
    candidates: tuple[SourceSelection, ...]
    parsers: tuple[RegistryObservation, ...]
    selected_attachment_id: Identity | None
    selected_parser_id: Token | None
    outcome: Literal["selected", "inspection-only", "unavailable"]
    fallback_from_attempt_id: Identity | None
    fallback_reason: Literal["parser-failed", "parser-timeout", "parser-memory-limit"] | None

    @model_validator(mode="after")
    def coherent_choice(self) -> Self:
        if len({candidate.source.attachment_id for candidate in self.candidates}) != len(self.candidates) or len(
            {parser.descriptor.parser_id for parser in self.parsers}
        ) != len(self.parsers):
            raise ValueError("parser-selection-duplicate")
        chosen = [candidate for candidate in self.candidates if candidate.disposition == "selected"]
        parsers = [parser for parser in self.parsers if parser.descriptor.parser_id == self.selected_parser_id]
        if self.outcome == "unavailable":
            if (
                chosen
                or self.selected_attachment_id is not None
                or self.selected_parser_id is not None
                or self.fallback_from_attempt_id is not None
                or self.fallback_reason is not None
            ):
                raise ValueError("parser-selection-unavailable-invalid")
        elif (
            len(chosen) != 1
            or chosen[0].source.attachment_id != self.selected_attachment_id
            or len(parsers) != 1
            or parsers[0].availability != "available"
            or chosen[0].source.format not in parsers[0].descriptor.input_formats
        ):
            raise ValueError("parser-selection-choice-invalid")
        if self.outcome != "unavailable":
            degraded = parsers[0].descriptor.kind == "degraded-inspection"
            if degraded != (self.outcome == "inspection-only") or degraded != (
                self.fallback_from_attempt_id is not None and self.fallback_reason is not None
            ):
                raise ValueError("parser-selection-fallback-invalid")
            if not degraded and (self.fallback_from_attempt_id is not None or self.fallback_reason is not None):
                raise ValueError("parser-selection-unexpected-fallback")
        return self


def selection_sha256(selection: ParserSelection) -> str:
    selection = ParserSelection.model_validate(selection)
    return hashlib.sha256(selection.model_dump_json(by_alias=True).encode("utf-8")).hexdigest()


def selected_values(selection: ParserSelection) -> tuple[SourceIdentity, ParserDescriptor]:
    selection = ParserSelection.model_validate(selection)
    if selection.outcome == "unavailable":
        raise SelectionProblem("parser-selection-unavailable")
    source = next(
        item.source for item in selection.candidates if item.source.attachment_id == selection.selected_attachment_id
    )
    descriptor = next(
        item.descriptor for item in selection.parsers if item.descriptor.parser_id == selection.selected_parser_id
    )
    return source, descriptor


def select_parser(
    sources: tuple[SelectionSource, ...],
    registry: ParserRegistry,
    *,
    primary_attachment_id: str,
    fallback_from: tuple[str, str, ParserSelection] | None = None,
) -> ParserSelection:
    unique: dict[str, SelectionSource] = {}
    failed = False
    for candidate in sources:
        try:
            source = SourceIdentity.model_validate(candidate.source)
        except ValueError:
            failed = True
            continue
        if candidate.availability not in {"available", "unavailable", "rights-denied"} or candidate.basis not in {
            "primary",
            "explicit-alternative",
            "same-object",
            "unproven",
        }:
            failed = True
            continue
        item = SelectionSource(source, candidate.availability, candidate.basis)
        previous = unique.get(source.attachment_id)
        if previous is not None and previous != item:
            failed = True
        unique[source.attachment_id] = item
    primary = unique.get(primary_attachment_id)
    if (
        failed
        or primary is None
        or primary.basis != "primary"
        or sum(item.basis == "primary" for item in unique.values()) != 1
    ):
        raise SelectionProblem("parser-source-candidates-invalid")
    prior_id = None
    prior_reason: Literal["parser-failed", "parser-timeout", "parser-memory-limit"] | None = None
    if fallback_from is not None:
        prior_id, observed_reason, prior = fallback_from
        prior = ParserSelection.model_validate(prior)
        prior_source, _ = selected_values(prior)
        if (
            not is_uuid_v7(prior_id)
            or observed_reason not in {"parser-failed", "parser-timeout", "parser-memory-limit"}
            or prior.outcome != "selected"
            or prior.selected_parser_id != "ro-docling-cpu"
            or primary.source.format != "pdf"
            or prior_source != primary.source
        ):
            raise SelectionProblem("parser-fallback-not-permitted")
        prior_reason = cast(Literal["parser-failed", "parser-timeout", "parser-memory-limit"], observed_reason)
    records: list[SourceSelection] = []
    choices: list[tuple[int, int, str, str, SourceIdentity, ParserDescriptor]] = []
    for key in sorted(unique):
        item = unique[key]
        source = item.source
        disposition: Disposition = "eligible"
        if item.availability != "available":
            disposition = item.availability
        elif (source.project_id, source.work_id, source.version_id) != (
            primary.source.project_id,
            primary.source.work_id,
            primary.source.version_id,
        ):
            disposition = "source-mismatch"
        elif item.basis == "unproven" or (
            item.basis == "same-object"
            and (source.object_sha256, source.source_assertion_revision_id)
            != (primary.source.object_sha256, primary.source.source_assertion_revision_id)
        ):
            disposition = "equivalence-unproven"
        allowed = [
            entry
            for entry in registry.entries
            if source.format in entry.descriptor.input_formats
            and (entry.descriptor.kind == "degraded-inspection") == (fallback_from is not None)
        ]
        if fallback_from is not None and source != primary.source:
            allowed = []
        if disposition == "eligible":
            available = [entry for entry in allowed if entry.availability == "available"]
            if not available:
                disposition = "unavailable" if allowed else "format-unsupported"
            for entry in available:
                choices.append(
                    (
                        _FORMAT_ORDER[source.format],
                        int(item.basis != "primary"),
                        source.attachment_id,
                        entry.descriptor.parser_id,
                        source,
                        entry.descriptor,
                    )
                )
        records.append(SourceSelection(source=source, basis=item.basis, disposition=disposition))
    selected_source = None
    selected_descriptor = None
    if choices:
        _, _, _, _, selected_source, selected_descriptor = min(choices, key=lambda item: item[:4])
        records = [
            item.model_copy(update={"disposition": "selected"}) if item.source == selected_source else item
            for item in records
        ]
    outcome: Literal["selected", "inspection-only", "unavailable"] = (
        "unavailable" if selected_source is None else ("inspection-only" if fallback_from is not None else "selected")
    )
    return ParserSelection(
        schema_version="1.0",
        policy_version="ro-parser-policy-1",
        candidates=tuple(records),
        parsers=tuple(
            RegistryObservation(descriptor=item.descriptor, availability=item.availability) for item in registry.entries
        ),
        selected_attachment_id=selected_source.attachment_id if selected_source else None,
        selected_parser_id=selected_descriptor.parser_id if selected_descriptor else None,
        outcome=outcome,
        fallback_from_attempt_id=prior_id if selected_source else None,
        fallback_reason=prior_reason if selected_source else None,
    )
