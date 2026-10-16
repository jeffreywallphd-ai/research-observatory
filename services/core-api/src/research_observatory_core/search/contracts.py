"""Engine-neutral, immutable local search snapshots and content-free errors."""

from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Literal, NoReturn, TypeGuard, cast

GRAMMAR_VERSION: Literal["ro-search-query-1"] = "ro-search-query-1"
ANALYZER_ID: Literal["ro-unicode61-diacritics2-1"] = "ro-unicode61-diacritics2-1"
MAX_QUERY_LENGTH = 8192
MAX_DEPTH = 16
MAX_NODES = 256
MAX_OPERANDS = 32
MAX_WIRE_BYTES = 262144
TEXT_FIELDS = ("title", "abstract", "full-text", "authors", "venue", "identifiers", "tags", "decisions")
NodeKind = Literal["literal", "phrase", "year", "and", "or", "not"]
YearOperator = Literal["=", ">", ">=", "<", "<="]


@dataclass(frozen=True, slots=True)
class QueryDiagnostic:
    """Half-open original codepoint offsets and one-based line/column."""

    code: str
    start: int = 0
    end: int = 0
    line: int = 1
    column: int = 1

    def to_dict(self) -> dict[str, str | int]:
        return {"code": self.code, "start": self.start, "end": self.end, "line": self.line, "column": self.column}


class QueryError(ValueError):
    """Only a stable code and numeric locations; never query text or parser causes."""

    def __init__(self, diagnostic: QueryDiagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.code)


def fail(code: str) -> NoReturn:
    raise QueryError(QueryDiagnostic(code))


def valid_text(value: object) -> TypeGuard[str]:
    return (
        type(value) is str
        and len(value) <= MAX_QUERY_LENGTH
        and all(not 0xD800 <= ord(char) <= 0xDFFF for char in value)
    )


@dataclass(frozen=True, slots=True, repr=False)
class QueryNode:
    """A discriminated AST; branches own immutable child tuples, never SQL."""

    kind: NodeKind
    field: str | None = None
    value: str | int | None = dc_field(default=None, repr=False)
    operator: YearOperator | None = None
    operands: tuple[QueryNode, ...] = dc_field(default=(), repr=False)

    def __post_init__(self) -> None:
        validate_tree(self)

    def __repr__(self) -> str:
        return "QueryNode()"


def validate_tree(root: object) -> None:
    """Iterative prewalk counts expanded occurrences, including shared children."""
    pending: list[tuple[object, int, frozenset[int]]] = [(root, 1, frozenset())]
    count = 0
    while pending:
        node, depth, ancestors = pending.pop()
        count += 1
        if type(node) is not QueryNode or count > MAX_NODES or depth > MAX_DEPTH or id(node) in ancestors:
            fail("invalid-ast-budget")
        try:
            kind, field_name, value, operator, operands = (
                node.kind,
                node.field,
                node.value,
                node.operator,
                node.operands,
            )
        except AttributeError:
            kind, field_name, value, operator, operands = None, None, None, None, None
        if type(kind) is not str or type(operands) is not tuple or len(operands) > MAX_OPERANDS:
            fail("invalid-ast")
        if kind in ("literal", "phrase"):
            if field_name is not None and (type(field_name) is not str or field_name not in TEXT_FIELDS):
                fail("invalid-ast-field")
            if not valid_text(value) or not value or len(value) > MAX_QUERY_LENGTH or operator is not None or operands:
                fail("invalid-ast-literal")
            if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
                fail("invalid-ast-literal")
            if kind == "literal" and (
                value in ("AND", "OR", "NOT") or any(char.isspace() or char in ':()"\\*?~^<>=[]{}' for char in value)
            ):
                fail("invalid-ast-literal")
        elif kind == "year":
            if (
                type(value) is not int
                or not 1 <= value <= 9999
                or type(field_name) is not str
                or field_name != "year"
                or type(operator) is not str
                or operator not in ("=", ">", ">=", "<", "<=")
                or operands
            ):
                fail("invalid-ast-year")
        elif kind in ("and", "or", "not"):
            if field_name is not None or value is not None or operator is not None:
                fail("invalid-ast-branch")
            if (kind == "not" and len(operands) != 1) or (kind != "not" and len(operands) < 2):
                fail("invalid-ast-branch")
        else:
            fail("invalid-ast-kind")
        next_ancestors = ancestors | {id(node)}
        pending.extend((child, depth + 1, next_ancestors) for child in operands)


def node_dict(node: QueryNode) -> dict:
    """Internal serialization only after the complete bounded tree was validated."""
    if node.kind in ("and", "or", "not"):
        return {"kind": node.kind, "operands": [node_dict(child) for child in node.operands]}
    if node.kind == "year":
        return {"kind": "year", "field": "year", "operator": node.operator, "value": node.value}
    return {"kind": node.kind, "field": node.field, "value": node.value}


@dataclass(frozen=True, slots=True, repr=False)
class QueryDocument:
    """Intentional private content; repr and diagnostics omit the content."""

    original_query: str = dc_field(repr=False)
    normalized_query: str = dc_field(repr=False)
    ast: QueryNode = dc_field(repr=False)
    schema_version: Literal["1.0"] = "1.0"
    grammar_version: Literal["ro-search-query-1"] = GRAMMAR_VERSION
    analyzer_id: Literal["ro-unicode61-diacritics2-1"] = ANALYZER_ID

    def __post_init__(self) -> None:
        self.validate()

    def __repr__(self) -> str:
        return "QueryDocument()"

    def validate(self) -> None:
        from .grammar import parse_parts

        complete = True
        try:
            # Validate presence before reading forged/partially constructed snapshots.
            _ = (
                self.schema_version,
                self.grammar_version,
                self.analyzer_id,
                self.original_query,
                self.normalized_query,
                self.ast,
            )
        except AttributeError:
            complete = False
        if not complete:
            fail("invalid-query-document")
        if (
            type(self.schema_version) is not str
            or type(self.grammar_version) is not str
            or type(self.analyzer_id) is not str
            or self.schema_version != "1.0"
            or self.grammar_version != GRAMMAR_VERSION
            or self.analyzer_id != ANALYZER_ID
            or not valid_text(self.original_query)
            or not valid_text(self.normalized_query)
        ):
            fail("invalid-query-document")
        validate_tree(self.ast)
        expected, normalized = parse_parts(self.original_query)
        if expected != self.ast or normalized != self.normalized_query:
            fail("query-document-mismatch")
        reparsed, renormalized = parse_parts(self.normalized_query)
        if reparsed != expected or renormalized != normalized:
            fail("query-document-mismatch")

    def to_dict(self) -> dict:
        self.validate()
        return {
            "schemaVersion": self.schema_version,
            "grammarVersion": self.grammar_version,
            "analyzerId": self.analyzer_id,
            "originalQuery": self.original_query,
            "normalizedQuery": self.normalized_query,
            "ast": node_dict(self.ast),
        }

    def to_json(self) -> str:
        encoded = json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_WIRE_BYTES:
            fail("wire-budget")
        return encoded


class _WireFailure(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise _WireFailure()
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise _WireFailure()


def _wire_preflight(raw: str | bytes) -> str:
    if type(raw) not in (str, bytes) or len(raw) > MAX_WIRE_BYTES:
        fail("wire-budget")
    text = None
    try:
        text = raw.decode("utf-8", errors="strict") if isinstance(raw, bytes) else raw
        if len(text.encode("utf-8", errors="strict")) > MAX_WIRE_BYTES:
            text = None
    except UnicodeError:
        text = None
    if text is None:
        fail("invalid-wire")
    # Bound containers before recursive JSON decoding. Braces in strings are data.
    depth = containers = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            containers += 1
            if depth > MAX_DEPTH * 2 + 4 or containers > MAX_NODES * 2 + 4:
                fail("wire-budget")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                fail("invalid-wire")
    return text


def _read_node(raw: object, depth: int, count: list[int]) -> QueryNode:
    count[0] += 1
    if type(raw) is not dict or count[0] > MAX_NODES or depth > MAX_DEPTH:
        fail("invalid-ast-budget")
    kind = raw.get("kind")
    if type(kind) is not str:
        fail("invalid-ast-kind")
    if kind in ("and", "or", "not"):
        children = raw.get("operands")
        if set(raw) != {"kind", "operands"} or type(children) is not list or len(children) > MAX_OPERANDS:
            fail("invalid-ast-branch")
        return QueryNode(
            kind=cast(NodeKind, kind), operands=tuple(_read_node(child, depth + 1, count) for child in children)
        )
    keys = {"kind", "field", "value", "operator"} if kind == "year" else {"kind", "field", "value"}
    if set(raw) != keys:
        fail("invalid-ast")
    return QueryNode(kind=cast(NodeKind, kind), field=raw["field"], value=raw["value"], operator=raw.get("operator"))


def load_query_document(raw: str | bytes) -> QueryDocument:
    """Decode the portable snapshot, then authenticate all fields against original text."""
    text = _wire_preflight(raw)
    decoded = None
    with suppress(ValueError, RecursionError):
        decoded = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    # Raise outside decoder handlers so private decoder inputs cannot enter a chained traceback.
    if type(decoded) is not dict or set(decoded) != {
        "schemaVersion",
        "grammarVersion",
        "analyzerId",
        "originalQuery",
        "normalizedQuery",
        "ast",
    }:
        fail("invalid-wire")
    return QueryDocument(
        original_query=decoded["originalQuery"],
        normalized_query=decoded["normalizedQuery"],
        ast=_read_node(decoded["ast"], 1, [0]),
        schema_version=decoded["schemaVersion"],
        grammar_version=decoded["grammarVersion"],
        analyzer_id=decoded["analyzerId"],
    )
