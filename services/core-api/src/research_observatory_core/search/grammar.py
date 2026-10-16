"""Bounded local query parser; no SQL, store, UI, network, or mutable runtime authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NoReturn, cast

from .contracts import (
    MAX_DEPTH,
    MAX_NODES,
    MAX_OPERANDS,
    MAX_QUERY_LENGTH,
    TEXT_FIELDS,
    NodeKind,
    QueryDiagnostic,
    QueryDocument,
    QueryError,
    QueryNode,
    YearOperator,
    valid_text,
    validate_tree,
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    start: int
    end: int
    value: str = field(repr=False)


def _error(text: str, code: str, start: int, end: int) -> NoReturn:
    prefix = text[:start].replace("\r\n", "\n").replace("\r", "\n")
    raise QueryError(QueryDiagnostic(code, start, end, prefix.count("\n") + 1, len(prefix.rsplit("\n", 1)[-1]) + 1))


def _tokens(text: str) -> list[_Token]:
    result: list[_Token] = []
    index = 0
    while index < len(text):
        start = index
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if ord(char) < 32 or 127 <= ord(char) <= 159:
            _error(text, "invalid-character", index, index + 1)
        if char == '"':
            index += 1
            value: list[str] = []
            while index < len(text) and text[index] != '"':
                char = text[index]
                if char == "\\":
                    if index + 1 >= len(text) or text[index + 1] not in ('"', "\\"):
                        _error(text, "invalid-escape", index, min(index + 2, len(text)))
                    index += 1
                    char = text[index]
                if ord(char) < 32 or 127 <= ord(char) <= 159:
                    _error(text, "invalid-character", index, index + 1)
                value.append(char)
                index += 1
            if index == len(text):
                _error(text, "unclosed-phrase", start, index)
            index += 1
            if not value:
                _error(text, "empty-phrase", start, index)
            result.append(_Token("phrase", start, index, "".join(value)))
        elif char in "():=<>":
            index += 1
            if char in "<>" and index < len(text) and text[index] == "=":
                index += 1
            result.append(_Token(text[start:index], start, index, text[start:index]))
        elif char in "\\*?~^[]{}":
            _error(text, "unsupported-syntax", start, start + 1)
        else:
            while index < len(text) and not text[index].isspace() and text[index] not in ':()"\\*?~^<>=[]{}':
                if ord(text[index]) < 32 or 127 <= ord(text[index]) <= 159:
                    _error(text, "invalid-character", index, index + 1)
                index += 1
            value_text = text[start:index]
            result.append(
                _Token(value_text if value_text in ("AND", "OR", "NOT") else "literal", start, index, value_text)
            )
        if len(result) > MAX_NODES * 4:
            _error(text, "query-budget", start, index)
    result.append(_Token("eof", len(text), len(text), ""))
    return result


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = _tokens(text)
        self.index = 0

    @property
    def token(self) -> _Token:
        return self.tokens[self.index]

    def take(self) -> _Token:
        token = self.token
        self.index += 1
        return token

    def error(self, code: str, token: _Token | None = None) -> NoReturn:
        token = token or self.token
        _error(self.text, code, token.start, token.end)

    def branch(self, kind: NodeKind, children: list[QueryNode]) -> QueryNode:
        flattened: list[QueryNode] = []
        for child in children:
            flattened.extend(child.operands if child.kind == kind else (child,))
        if len(flattened) > MAX_OPERANDS:
            self.error("operand-budget")
        return QueryNode(kind=kind, operands=tuple(flattened))

    def expression(self, depth: int = 0) -> QueryNode:
        children = [self.conjunction(depth)]
        while self.token.kind == "OR":
            self.take()
            children.append(self.conjunction(depth))
            if len(children) > MAX_OPERANDS:
                self.error("operand-budget")
        return children[0] if len(children) == 1 else self.branch("or", children)

    def conjunction(self, depth: int) -> QueryNode:
        children = [self.unary(depth)]
        while self.token.kind not in ("OR", ")", "eof"):
            if self.token.kind == "AND":
                self.take()
            children.append(self.unary(depth))
            if len(children) > MAX_OPERANDS:
                self.error("operand-budget")
        return children[0] if len(children) == 1 else self.branch("and", children)

    def unary(self, depth: int) -> QueryNode:
        if self.token.kind in ("NOT", "("):
            if depth >= MAX_DEPTH:
                self.error("depth-budget")
            if self.take().kind == "NOT":
                return QueryNode(kind="not", operands=(self.unary(depth + 1),))
            node = self.expression(depth + 1)
            if self.token.kind != ")":
                self.error("expected-close-group")
            self.take()
            return node
        return self.leaf()

    def leaf(self) -> QueryNode:
        token = self.token
        if token.kind not in ("literal", "phrase"):
            self.error("expected-expression")
        self.take()
        field_name = None
        if token.kind == "literal" and self.token.kind in (":", "=", ">", ">=", "<", "<="):
            field_name = token.value
            operator = self.take()
            if field_name not in (*TEXT_FIELDS, "year"):
                self.error("unknown-field", token)
            if field_name == "year":
                year_token = self.token
                if (
                    year_token.kind != "literal"
                    or not year_token.value.isascii()
                    or not year_token.value.isdecimal()
                    or len(year_token.value) > 4
                    or not 1 <= int(year_token.value) <= 9999
                ):
                    self.error("invalid-year")
                self.take()
                return QueryNode(
                    kind="year",
                    field="year",
                    value=int(year_token.value),
                    operator=cast(YearOperator, "=" if operator.kind == ":" else operator.kind),
                )
            if operator.kind != ":":
                self.error("unsupported-field-operator", operator)
            if self.token.kind == "(":
                self.error("unsupported-field-group")
            token = self.token
            if token.kind not in ("literal", "phrase"):
                self.error("expected-literal")
            self.take()
        return QueryNode(kind=cast(NodeKind, token.kind), field=field_name, value=token.value)


def _normalize(node: QueryNode, parent_precedence: int = 0) -> str:
    precedence = {"or": 1, "and": 2, "not": 3}.get(node.kind, 4)
    if node.kind in ("literal", "phrase"):
        value = cast(str, node.value)
        if node.kind == "phrase":
            value = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        text = (node.field + ":" if node.field else "") + value
    elif node.kind == "year":
        text = "year" + str(node.operator) + str(node.value)
    elif node.kind == "not":
        text = "NOT " + _normalize(node.operands[0], precedence)
    else:
        text = (" " + node.kind.upper() + " ").join(_normalize(child, precedence) for child in node.operands)
    return "(" + text + ")" if precedence < parent_precedence else text


def parse_parts(text: str) -> tuple[QueryNode, str]:
    if type(text) is str and len(text) > MAX_QUERY_LENGTH:
        _error(text, "length-budget", MAX_QUERY_LENGTH, len(text))
    if not valid_text(text):
        _error("", "invalid-query-text", 0, 0)
    parser = _Parser(text)
    if parser.token.kind == "eof":
        parser.error("empty-query")
    node = parser.expression()
    if parser.token.kind != "eof":
        parser.error("unexpected-token")
    validate_tree(node)
    normalized = _normalize(node)
    if len(normalized) > MAX_QUERY_LENGTH:
        _error(text, "normalized-length-budget", 0, len(text))
    return node, normalized


def parse_query(text: str) -> QueryDocument:
    node, normalized = parse_parts(text)
    return QueryDocument(text, normalized, node)
