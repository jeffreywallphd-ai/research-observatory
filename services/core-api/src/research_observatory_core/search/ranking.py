"""Versioned lexical method values; they carry no canonical read authority."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Literal

from .contracts import QueryDocument, QueryNode, node_dict

RANKING_VERSION: Literal["ro-lexical-best-row-per-leaf-bm25-1"] = "ro-lexical-best-row-per-leaf-bm25-1"
# Exact FTS column order: title, abstract, full_text, authors, venue,
# identifiers, tags, decisions. These are engineering parameters, not quality
# estimates or probabilities. User filters do not redefine corpus statistics.
FIELD_WEIGHTS = (8.0, 4.0, 1.0, 2.0, 2.0, 10.0, 1.0, 1.0)
SNIPPET_CODEPOINTS = 384
MAX_HIGHLIGHTS = 32
MAX_EXPLANATION_ITEMS = 50


@dataclass(frozen=True, slots=True)
class LexicalFilters:
    year_from: int | None = None
    year_to: int | None = None

    def __post_init__(self) -> None:
        for value in (self.year_from, self.year_to):
            if value is not None and (type(value) is not int or not 1 <= value <= 9999):
                raise ValueError("lexical year filter is invalid")
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError("lexical year filter is invalid")

    def includes(self, year: int | None) -> bool:
        return (self.year_from is None or (year is not None and year >= self.year_from)) and (
            self.year_to is None or (year is not None and year <= self.year_to)
        )


def leaf_sha256(node: QueryNode) -> str:
    return hashlib.sha256(
        json.dumps(node_dict(node), sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def positive_leaves(document: QueryDocument) -> tuple[tuple[str, QueryNode], ...]:
    """Distinct exact AST leaves under an even number of NOT operations."""
    document.validate()
    found: dict[str, QueryNode] = {}
    pending = [(document.ast, False)]
    while pending:
        node, negative = pending.pop()
        if node.kind in ("and", "or", "not"):
            pending.extend((child, negative ^ (node.kind == "not")) for child in node.operands)
        elif not negative and node.kind in ("literal", "phrase"):
            found[leaf_sha256(node)] = node
    return tuple(sorted(found.items()))


@dataclass(frozen=True, slots=True)
class RankComponent:
    leaf_sha256: str
    entry_id: str
    score: float


@dataclass(frozen=True, slots=True)
class RankedItem:
    item_id: str
    score: float
    components: tuple[RankComponent, ...]

    @classmethod
    def from_components(cls, item_id: str, components: tuple[RankComponent, ...]) -> RankedItem:
        score = sum((component.score for component in components), 0.0)
        if not math.isfinite(score) or score < 0:
            raise ValueError("lexical rank is invalid")
        return cls(item_id, score, components)


@dataclass(frozen=True, slots=True)
class VerifiedSnippet:
    field: str
    start: int
    end: int
    text: str = dc_field(repr=False)
    highlights: tuple[tuple[int, int], ...]
    truncated: bool


def verified_snippet(original: str, marked: str, opening: str, closing: str, field_name: str) -> VerifiedSnippet:
    """Recover original codepoint positions from collision-free FTS markers.

    Marked output is never HTML. Every unmarked byte/codepoint must reproduce
    the same authenticated mirror text. A long phrase may exceed the preview;
    its visible intersection is highlighted and truncation remains explicit.
    """
    if not opening or not closing or opening == closing or opening in original or closing in original:
        raise ValueError("snippet marker binding is invalid")
    pieces: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = position = 0
    while True:
        begin = marked.find(opening, cursor)
        if begin < 0:
            tail = marked[cursor:]
            if closing in tail:
                raise ValueError("snippet marker structure is invalid")
            pieces.append(tail)
            break
        prefix = marked[cursor:begin]
        finish = marked.find(closing, begin + len(opening))
        if finish < 0 or closing in prefix:
            raise ValueError("snippet marker structure is invalid")
        match = marked[begin + len(opening) : finish]
        if not match or opening in match:
            raise ValueError("snippet marker structure is invalid")
        position += len(prefix)
        pieces.extend((prefix, match))
        if len(spans) < MAX_HIGHLIGHTS:
            spans.append((position, position + len(match)))
        position += len(match)
        cursor = finish + len(closing)
    if "".join(pieces) != original:
        raise ValueError("snippet text binding is invalid")
    start = max(0, spans[0][0] - 64) if spans else 0
    end = min(len(original), start + SNIPPET_CODEPOINTS)
    visible = tuple((max(a, start) - start, min(b, end) - start) for a, b in spans if a < end and b > start)
    return VerifiedSnippet(field_name, start, end, original[start:end], visible, start > 0 or end < len(original))
