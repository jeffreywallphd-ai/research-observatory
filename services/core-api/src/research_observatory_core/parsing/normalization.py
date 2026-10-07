"""Unicode-16 NFC/newline projection with exact raw code-point contributors.

No whitespace, ligature, case or hyphen rewriting. Canonical reordering may
make raw contributors nonmonotone or noncontiguous. This module performs no I/O.
"""

from __future__ import annotations

import io
import unicodedata
from array import array
from bisect import bisect_right
from collections.abc import Callable, Iterator
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


def _decomposed(raw: str, checkpoint: Callable[[], None]) -> Iterator[_Unit]:
    index = 0
    while index < len(raw):
        checkpoint()
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


def _compact_units(values: array[int], checkpoint: Callable[[], None]) -> Iterator[_Unit]:
    for offset in range(0, len(values), 3):
        checkpoint()
        yield chr(values[offset]), ((values[offset + 1], values[offset + 2]),)


def _ordered(raw: str, checkpoint: Callable[[], None]) -> Iterator[_Unit]:
    # Stable canonical-class buckets hold 12-byte scalar/origin triples instead
    # of a source-sized graph of nested Python tuples. Decomposition always
    # gives one raw interval; only composition can merge contributors.
    buckets: dict[int, array[int]] = {}

    def emit() -> Iterator[_Unit]:
        for combining_class in sorted(buckets):
            yield from _compact_units(buckets[combining_class], checkpoint)
        buckets.clear()

    for character, origin in _decomposed(raw, checkpoint):
        combining_class = unicodedata.combining(character)
        if combining_class == 0 and buckets:
            yield from emit()
        values = buckets.setdefault(combining_class, array("I"))
        values.extend((ord(character), origin[0][0], origin[0][1]))
    yield from emit()


def _composed(raw: str, checkpoint: Callable[[], None]) -> Iterator[_Unit]:
    pending = array("I")
    starter: _Unit | None = None
    last_class = 0
    for character, origin in _ordered(raw, checkpoint):
        checkpoint()
        combining_class = unicodedata.combining(character)
        if starter is not None and (last_class < combining_class or last_class == 0):
            composite = unicodedata.normalize("NFC", starter[0] + character)
            if len(composite) == 1:
                starter = (composite, _merge_ranges(starter[1] + origin))
                continue
        if combining_class == 0:
            if starter is not None:
                yield starter
            yield from _compact_units(pending, checkpoint)
            pending = array("I")
            starter = character, origin
        else:
            pending.extend((ord(character), origin[0][0], origin[0][1]))
        last_class = combining_class
    if starter is not None:
        yield starter
    yield from _compact_units(pending, checkpoint)


def normalize_text(raw: str, *, cancelled: Callable[[], bool] | None = None) -> NormalizedText:
    if type(raw) is not str or unicodedata.unidata_version != UNICODE_VERSION or array("I").itemsize != 4:
        raise NormalizationProblem("text-or-unicode-version-invalid")
    steps = 0

    def checkpoint(*, force: bool = False) -> None:
        nonlocal steps
        steps += 1
        if cancelled is None or (not force and steps % 256 != 0):
            return
        stopped = True
        try:
            observation = cancelled()
            stopped = type(observation) is not bool or observation
        except Exception:
            pass
        if stopped:
            raise NormalizationProblem("text-normalization-cancelled")

    checkpoint(force=True)
    invalid = False
    try:
        size = 0
        for offset in range(0, len(raw), 4096):
            checkpoint(force=True)
            size += len(raw[offset : offset + 4096].encode("utf-8", errors="strict"))
            if size > MAX_IR_BYTES:
                raise NormalizationProblem("text-exceeds-ir-limit")
    except UnicodeError:
        invalid = True
    if invalid:
        raise NormalizationProblem("text-scalar-invalid")
    # CPython's quick check refuses descending combining classes before full
    # normalization. Avoid an uninterruptible quadratic sort on hostile runs.
    if "\r" not in raw and unicodedata.is_normalized("NFC", raw):
        checkpoint(force=True)
        mappings = (MappingRun("identity", 0, len(raw), ((0, len(raw)),)),) if raw else ()
        return NormalizedText(raw, raw, mappings)
    output = io.StringIO()
    mappings_list: list[MappingRun] = []
    for position, (character, origin) in enumerate(_composed(raw, checkpoint)):
        checkpoint()
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
    # Preserve the independent built-in NFC comparison on canonical NFD order;
    # the ordering pass is cooperative and does not feed the C routine a
    # descending combining run. This is the same Unicode canonical equivalence.
    expected = unicodedata.normalize("NFC", "".join(character for character, _ in _ordered(raw, checkpoint)))
    checkpoint(force=True)
    if actual != expected:
        raise NormalizationProblem("text-normalization-inconsistent")
    return NormalizedText(raw, actual, tuple(mappings_list))
