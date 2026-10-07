"""Unicode-16 NFC/newline projection with exact raw code-point contributors.

No whitespace, ligature, case or hyphen rewriting. Canonical reordering may
make raw contributors nonmonotone or noncontiguous. This module performs no I/O.
"""

from __future__ import annotations

import io
import unicodedata
from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

NORMALIZATION_VERSION: Literal["ro-text-nfc-1"] = "ro-text-nfc-1"
UNICODE_VERSION: Literal["16.0.0"] = "16.0.0"
MAX_IR_BYTES = 64 * 1024 * 1024
type RawRanges = tuple[tuple[int, int], ...]
type _Unit = tuple[str, RawRanges]


class NormalizationProblem(ValueError):
    """Content-free projection failure."""


def _merge_ranges(ranges: Iterator[tuple[int, int]] | RawRanges) -> RawRanges:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


@dataclass(frozen=True, slots=True)
class MappingRun:
    kind: Literal["identity", "transform"]
    normalized_start: int
    normalized_end: int
    raw_ranges: RawRanges


@dataclass(frozen=True, slots=True)
class NormalizedText:
    raw_text: str
    normalized_text: str
    mappings: tuple[MappingRun, ...]
    normalization_version: str = NORMALIZATION_VERSION
    unicode_version: str = UNICODE_VERSION

    def raw_ranges_for(self, start: int, end: int) -> RawRanges:
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(self.normalized_text):
            raise NormalizationProblem("text-range-invalid")
        if start == end:
            return ()
        found: list[tuple[int, int]] = []
        index = max(0, bisect_right(self.mappings, start, key=lambda item: item.normalized_start) - 1)
        for mapping in self.mappings[index:]:
            if mapping.normalized_start >= end:
                break
            lower, upper = max(start, mapping.normalized_start), min(end, mapping.normalized_end)
            if lower >= upper:
                continue
            if mapping.kind == "identity":
                base = mapping.raw_ranges[0][0] - mapping.normalized_start
                found.append((base + lower, base + upper))
            else:
                found.extend(mapping.raw_ranges)
        return _merge_ranges(iter(found))


def _decomposed(raw: str) -> Iterator[_Unit]:
    index = 0
    while index < len(raw):
        end = index + 1
        character = raw[index]
        if character == "\r":
            character = "\n"
            if end < len(raw) and raw[end] == "\n":
                end += 1
        origin = ((index, end),)
        for scalar in unicodedata.normalize("NFD", character):
            yield scalar, origin
        index = end


def _ordered(raw: str) -> Iterator[_Unit]:
    segment: list[_Unit] = []
    for item in _decomposed(raw):
        if unicodedata.combining(item[0]) == 0 and segment:
            yield from sorted(segment, key=lambda unit: unicodedata.combining(unit[0]))
            segment.clear()
        segment.append(item)
    yield from sorted(segment, key=lambda unit: unicodedata.combining(unit[0]))


def _composed(raw: str) -> Iterator[_Unit]:
    pending: list[_Unit] = []
    starter: int | None = None
    last_class = 0
    for character, origin in _ordered(raw):
        combining_class = unicodedata.combining(character)
        if starter is not None and (last_class < combining_class or last_class == 0):
            composite = unicodedata.normalize("NFC", pending[starter][0] + character)
            if len(composite) == 1:
                pending[starter] = (composite, _merge_ranges(pending[starter][1] + origin))
                continue
        if combining_class == 0:
            yield from pending
            pending = [(character, origin)]
            starter = 0
        else:
            pending.append((character, origin))
        last_class = combining_class
    yield from pending


def normalize_text(raw: str) -> NormalizedText:
    if type(raw) is not str or unicodedata.unidata_version != UNICODE_VERSION:
        raise NormalizationProblem("text-or-unicode-version-invalid")
    invalid = False
    try:
        raw.encode("utf-8", errors="strict")
    except UnicodeError:
        invalid = True
    if invalid:
        raise NormalizationProblem("text-scalar-invalid")
    expected = unicodedata.normalize("NFC", raw.replace("\r\n", "\n").replace("\r", "\n"))
    if expected == raw:
        mappings = (MappingRun("identity", 0, len(raw), ((0, len(raw)),)),) if raw else ()
        return NormalizedText(raw, raw, mappings)
    output = io.StringIO()
    mappings_list: list[MappingRun] = []
    for position, (character, origin) in enumerate(_composed(raw)):
        output.write(character)
        identity = len(origin) == 1 and origin[0][1] == origin[0][0] + 1 and raw[origin[0][0]] == character
        if (
            identity
            and mappings_list
            and mappings_list[-1].kind == "identity"
            and mappings_list[-1].raw_ranges[0][1] == origin[0][0]
        ):
            previous = mappings_list[-1]
            mappings_list[-1] = MappingRun(
                "identity", previous.normalized_start, position + 1, ((previous.raw_ranges[0][0], origin[0][1]),)
            )
        else:
            mappings_list.append(MappingRun("identity" if identity else "transform", position, position + 1, origin))
            # Every serialized wire mapping takes at least 64 bytes. This is a
            # lower-bound application of the approved 64 MiB IR limit, not an
            # additional text/count cap; refuse provably oversized maps early.
            if len(mappings_list) * 64 > MAX_IR_BYTES:
                raise NormalizationProblem("text-mapping-exceeds-ir-limit")
    actual = output.getvalue()
    if actual != expected:
        raise NormalizationProblem("text-normalization-inconsistent")
    return NormalizedText(raw, actual, tuple(mappings_list))
