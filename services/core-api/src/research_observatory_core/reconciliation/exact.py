"""Deterministic exact matching and source precedence, never probabilistic truth."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field

from ..ingestion.import_drafts import DraftValue
from .identifiers import NormalizedIdentifier, normalize_identifier

type VerificationState = Literal["unverified", "verified", "disputed", "invalid"]
type SourceOrigin = Literal["observed", "correction"]
type MatchFlag = Literal[
    "invalid-identifier",
    "disputed-identifier",
    "identifier-reassigned",
    "identifier-reassignment-suspected",
    "conflicting-identifiers",
    "multiple-work-matches",
    "incompatible-version",
]
type MatchDisposition = Literal["new-work", "exact-linked", "review-required"]
type IdentifierKey = tuple[str, str]
_WORK_SCHEMES = frozenset({"doi", "pmid", "arxiv", "isbn", "openalex", "s2-paper", "s2-corpus"})
_PROVIDER_SCHEMES = frozenset({"openalex", "s2-paper", "s2-corpus"})


class IdentifierAssertion(DraftValue):
    scheme: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    observed: Annotated[str, Field(max_length=65536)] = Field(repr=False)
    role: Literal["subject", "person", "organization", "container", "location"] = "subject"
    verification_state: VerificationState = "unverified"
    reassignment_observed: bool = False
    origin: SourceOrigin = "observed"
    active_for_matching: bool = True
    source_selector: Annotated[str, Field(min_length=1, max_length=128)] = "observed-value"
    source_encoding: Literal["text", "json-string", "bibtex-literal"] = "text"

    @property
    def normalized(self) -> NormalizedIdentifier:
        value = self.observed
        if self.source_encoding == "json-string":
            try:
                decoded = json.loads(value)
                value = decoded if isinstance(decoded, str) else ""
            except ValueError:
                value = ""
        elif self.source_encoding == "bibtex-literal":
            value = _bib_literal(value)
        result = normalize_identifier(self.scheme, value)
        return result.model_copy(update={"observed": self.observed})


def _bib_literal(value: str) -> str:
    """Decode one literal only. Macro/concatenation expressions stay unresolved.

    The immutable parser candidate may have Unicode-folded a DOI, so it cannot
    recover the original identifier. Preserve the raw expression for review.
    """
    value = value.strip()
    if len(value) < 2 or value[0] not in '{"':
        return ""
    depth, escaped = 0, False
    for index, char in enumerate(value[1:], start=1):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "{":
            depth += 1
        elif depth == 0 and char == ("}" if value[0] == "{" else '"'):
            return value[1:index] if index == len(value) - 1 else ""
        elif char == "}":
            depth -= 1
            if depth < 0:
                return ""
    return ""


def exact_keys(assertions: tuple[IdentifierAssertion, ...]) -> frozenset[IdentifierKey]:
    keys: set[IdentifierKey] = set()
    for assertion in assertions:
        normalized = assertion.normalized
        if (
            assertion.active_for_matching
            and assertion.role == "subject"
            and assertion.scheme in _WORK_SCHEMES
            and assertion.verification_state not in {"disputed", "invalid"}
            and not assertion.reassignment_observed
            and normalized.status == "valid"
            and normalized.scope in {"work", "work-version"}
            and normalized.canonical is not None
        ):
            keys.add((assertion.scheme, normalized.canonical))
    return frozenset(keys)


def _values(keys: frozenset[IdentifierKey]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for scheme, value in keys:
        result.setdefault(scheme, set()).add(value)
    return result


def _flags(assertions: tuple[IdentifierAssertion, ...]) -> set[MatchFlag]:
    result: set[MatchFlag] = set()
    for assertion in assertions:
        if not assertion.active_for_matching or assertion.role != "subject" or assertion.scheme not in _WORK_SCHEMES:
            continue
        if assertion.normalized.status == "invalid" or assertion.verification_state == "invalid":
            result.add("invalid-identifier")
        if assertion.verification_state == "disputed":
            result.add("disputed-identifier")
        if assertion.reassignment_observed:
            result.add("identifier-reassigned")
    if any(len(values) > 1 for values in _values(exact_keys(assertions)).values()):
        # A version graph or explicit adjudication may explain this later. Do
        # not flatten multiple DOI/PMID/manifestation assertions in this path.
        result.add("conflicting-identifiers")
    return result


@dataclass(frozen=True, slots=True)
class MatchAssessment:
    disposition: MatchDisposition
    target: str | None
    candidates: tuple[str, ...]
    flags: tuple[MatchFlag, ...]
    matching_keys: tuple[IdentifierKey, ...] = field(repr=False)


def assess_match(
    incoming: tuple[IdentifierAssertion, ...], works: Mapping[str, tuple[IdentifierAssertion, ...]]
) -> MatchAssessment:
    """Assess the complete overlapping set; the repository fences its snapshot.

    Exact, unique valid identifiers may link under ADR-0027. The match is a
    deterministic inferred association, not a change to verification states.
    """
    if len(incoming) > 128 or len(works) > 256:
        raise ValueError("reconciliation-bound-exceeded")
    incoming = tuple(IdentifierAssertion.model_validate(item) for item in incoming)
    incoming_keys = exact_keys(incoming)
    flags = _flags(incoming)
    candidates: list[str] = []
    matched: set[IdentifierKey] = set()
    values = _values(incoming_keys)
    for identity, assertions in sorted(works.items()):
        if len(assertions) > 32768:
            raise ValueError("reconciliation-bound-exceeded")
        existing_keys = exact_keys(assertions)
        common = incoming_keys & existing_keys
        if not common:
            continue
        candidates.append(identity)
        matched.update(common)
        flags.update(_flags(assertions))
        old_values = _values(existing_keys)
        conflicting = {scheme for scheme in values.keys() & old_values.keys() if values[scheme] != old_values[scheme]}
        if conflicting:
            flags.add("conflicting-identifiers")
            if "arxiv" in conflicting or "isbn" in conflicting:
                flags.add("incompatible-version")
            if any(scheme in _PROVIDER_SCHEMES for scheme, _ in common):
                flags.add("identifier-reassignment-suspected")
    if len(candidates) > 1:
        flags.add("multiple-work-matches")
    disposition: MatchDisposition = "review-required" if flags else "exact-linked" if candidates else "new-work"
    return MatchAssessment(
        disposition,
        candidates[0] if disposition == "exact-linked" else None,
        tuple(candidates),
        tuple(sorted(flags)),
        tuple(sorted(matched)),
    )


@dataclass(frozen=True, slots=True)
class FieldSelection:
    assertions: tuple[tuple[str, str, SourceOrigin], ...] = field(repr=False)
    selected: str | None = field(repr=False)
    status: Literal["observed", "adjudicated", "disputed", "not-reported"]
    reason: Literal["consistent-source-values", "accepted-correction", "competing-assertions", "no-assertion"]


def select_field(assertions: tuple[tuple[str, str, SourceOrigin], ...]) -> FieldSelection:
    """Prefer an accepted correction without discarding competing observations.

    This helper selects one scalar field. Multi-valued author lists and other
    structures are opaque source assertions, not person-identity inferences.
    """
    if not assertions:
        return FieldSelection((), None, "not-reported", "no-assertion")
    if len(assertions) > 32768 or any(origin not in {"observed", "correction"} for _, _, origin in assertions):
        raise ValueError("reconciliation-field-invalid")
    corrections = {value for _, value, origin in assertions if origin == "correction"}
    candidates = corrections or {value for _, value, _ in assertions}
    if len(candidates) != 1:
        return FieldSelection(assertions, None, "disputed", "competing-assertions")
    return FieldSelection(
        assertions,
        next(iter(candidates)),
        "adjudicated" if corrections else "observed",
        "accepted-correction" if corrections else "consistent-source-values",
    )
