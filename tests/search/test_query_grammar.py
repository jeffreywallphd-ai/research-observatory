"""Local query language and untrusted portable snapshots, without UI or a database."""

from __future__ import annotations

import copy
import json
import sys
import traceback
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.search import (  # noqa: E402
    ANALYZER_ID,
    MAX_DEPTH,
    MAX_NODES,
    MAX_QUERY_LENGTH,
    MAX_WIRE_BYTES,
    QueryDocument,
    QueryError,
    QueryNode,
    load_query_document,
    parse_query,
)


class QueryGrammarTests(unittest.TestCase):
    def test_precedence_implicit_conjunction_and_unary_not(self):
        query = parse_query("alpha OR beta gamma AND NOT NOT delta")
        self.assertEqual("or", query.ast.kind)
        conjunction = query.ast.operands[1]
        self.assertEqual("and", conjunction.kind)
        self.assertEqual(["literal", "literal", "not"], [node.kind for node in conjunction.operands])
        self.assertEqual("not", conjunction.operands[2].operands[0].kind)
        for source in ("NOT alpha", "alpha OR NOT beta", "title:alpha beta", "(alpha OR beta) gamma"):
            with self.subTest(source=source):
                self.assertEqual(parse_query(source).ast, parse_query(parse_query(source).normalized_query).ast)

    def test_all_fields_year_filters_and_unicode_literal_roundtrip(self):
        examples = [
            'title:"two words"',
            "abstract:é",
            "full-text:e\u0301",
            "authors:山田",
            "venue:journal",
            'identifiers:"doi:10.1234/a-b_c(1)"',
            "tags:review",
            "decisions:included",
            "year:2020",
            "year>=2020",
            "year<=2025",
            "year>1999",
            "year<2026",
            "year=1",
            '"AND"',
            '"a \\"quote\\" and \\\\ slash"',
            "😀 alpha",
            "identifiers:10.1234/example",
        ]
        for source in examples:
            with self.subTest(source=source):
                document = parse_query(source)
                self.assertEqual(source, document.original_query)
                self.assertEqual(ANALYZER_ID, document.analyzer_id)
                reparsed = parse_query(document.normalized_query)
                self.assertEqual(document.ast, reparsed.ast)
                self.assertEqual(document.normalized_query, reparsed.normalized_query)
                self.assertEqual(document, load_query_document(document.to_json()))
        self.assertEqual("year=2020", parse_query("year:2020").normalized_query)
        self.assertNotEqual(parse_query("é").ast, parse_query("e\u0301").ast)

    def test_original_whitespace_is_retained_but_normalization_is_deterministic(self):
        query = parse_query("  alpha\r\n   OR (beta   gamma) ")
        self.assertEqual("  alpha\r\n   OR (beta   gamma) ", query.original_query)
        self.assertEqual("alpha OR beta AND gamma", query.normalized_query)
        self.assertEqual(query.ast, parse_query(query.normalized_query).ast)

    def test_composed_queries_roundtrip_without_changing_operand_order_or_literals(self):
        leaves = ('title:"café"', 'identifiers:"urn:example:a-b"', "year<=2026", '"AND"', "tags:review")
        for first in leaves:
            for second in leaves:
                for source in (f"NOT ({first} OR {second})", f"{first} ({second} OR NOT tags:other)"):
                    with self.subTest(source=source):
                        original = parse_query(source)
                        self.assertEqual(original.ast, parse_query(original.normalized_query).ast)
                        self.assertEqual(original, load_query_document(original.to_json().encode("utf-8")))

    def test_invalid_syntax_has_original_codepoint_locations(self):
        examples = [
            ("", "empty-query", 0, 0, 1, 1),
            ("alpha AND", "expected-expression", 9, 9, 1, 10),
            ("😀\r\nAND )", "expected-expression", 7, 8, 2, 5),
            ('alpha "secret', "unclosed-phrase", 6, 13, 1, 7),
            ("title:(alpha OR abstract:beta)", "unsupported-field-group", 6, 7, 1, 7),
            ("unknown:alpha", "unknown-field", 0, 7, 1, 1),
            ("alpha*", "unsupported-syntax", 5, 6, 1, 6),
            ('"alpha"~3', "unsupported-syntax", 7, 8, 1, 8),
            ('"a\\q"', "invalid-escape", 2, 4, 1, 3),
            ("year>=true", "invalid-year", 6, 10, 1, 7),
            ("()", "expected-expression", 1, 2, 1, 2),
        ]
        for source, code, start, end, line, column in examples:
            with self.subTest(source=source), self.assertRaises(QueryError) as caught:
                parse_query(source)
            diagnostic = caught.exception.diagnostic
            self.assertEqual(
                (code, start, end, line, column),
                (
                    diagnostic.code,
                    diagnostic.start,
                    diagnostic.end,
                    diagnostic.line,
                    diagnostic.column,
                ),
            )

    def test_limits_are_enforced_at_and_above_boundaries(self):
        self.assertEqual("a" * MAX_QUERY_LENGTH, parse_query("a" * MAX_QUERY_LENGTH).normalized_query)
        with self.assertRaises(QueryError):
            parse_query("a" * (MAX_QUERY_LENGTH + 1))
        parse_query("(" * MAX_DEPTH + "a" + ")" * MAX_DEPTH)
        with self.assertRaises(QueryError):
            parse_query("(" * (MAX_DEPTH + 1) + "a" + ")" * (MAX_DEPTH + 1))
        # Eight bounded disjunctions each contain31 leaves: 1+8+248=257 expanded nodes.
        source = " AND ".join("(" + " OR ".join(f"a{i}_{j}" for j in range(31)) + ")" for i in range(8))
        at_cap = " AND ".join(
            "(" + " OR ".join(f"a{i}_{j}" for j in range(30 if i == 7 else 31)) + ")" for i in range(8)
        )
        self.assertEqual(256, MAX_NODES)
        parse_query(at_cap)
        with self.assertRaises(QueryError):
            parse_query(source)
        # A short implicit-conjunction input must not normalize beyond the accepted input cap.
        with self.assertRaises(QueryError):
            parse_query(" ".join("a" * 252 for _ in range(32)))

    def test_snapshot_substitution_and_unknown_contracts_fail_closed(self):
        raw = parse_query('title:"sensitive phrase" AND year>=2020').to_dict()
        changes = [
            {"originalQuery": "other"},
            {"normalizedQuery": "other"},
            {"grammarVersion": "future"},
            {"analyzerId": "other"},
            {"schemaVersion": "2.0"},
            {"unexpected": "private"},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(QueryError):
                load_query_document(json.dumps(raw | change))
        for value in (True, "2020", 2020.0, 0, 10000):
            changed = copy.deepcopy(raw)
            changed["ast"]["operands"][1]["value"] = value
            with self.subTest(value=value), self.assertRaises(QueryError):
                load_query_document(json.dumps(changed))
        for delta in ({"kind": "sql"}, {"field": "abstract"}, {"value": "replacement"}, {"extra": 1}):
            changed = copy.deepcopy(raw)
            changed["ast"]["operands"][0].update(delta)
            with self.subTest(delta=delta), self.assertRaises(QueryError):
                load_query_document(json.dumps(changed))

    def test_wire_preflight_rejects_excess_bytes_depth_duplicates_and_invalid_unicode(self):
        for raw in (
            b" " * (MAX_WIRE_BYTES + 1),
            "[" * 10000 + "]" * 10000,
            '{"schemaVersion":"1.0","schemaVersion":"1.0"}',
            b"\xff",
            '{"x":NaN}',
            '{"x":"\\ud800"}',
        ):
            with self.subTest(size=len(raw)), self.assertRaises(QueryError):
                load_query_document(raw)
        encoded = parse_query("alpha").to_json().encode("utf-8")
        at_cap = b" " * (MAX_WIRE_BYTES - len(encoded)) + encoded
        self.assertEqual("alpha", load_query_document(at_cap).original_query)
        with self.assertRaises(QueryError):
            load_query_document(at_cap + b" ")
        duplicate_nested = encoded.replace(b'"kind":"literal"', b'"kind":"literal","kind":"literal"')
        with self.assertRaises(QueryError):
            load_query_document(duplicate_nested)
        for raw in ('"' + "😀" * (MAX_WIRE_BYTES // 3) + '"', "\ud800"):
            with self.assertRaises(QueryError):
                load_query_document(raw)

    def test_depth_and_operand_limits_also_apply_to_direct_constructors(self):
        node = QueryNode(kind="literal", value="alpha")
        for _ in range(MAX_DEPTH - 1):
            node = QueryNode(kind="not", operands=(node,))
        with self.assertRaises(QueryError):
            QueryNode(kind="not", operands=(node,))
        leaf = QueryNode(kind="literal", value="alpha")
        QueryNode(kind="and", operands=(leaf,) * 32)
        with self.assertRaises(QueryError):
            QueryNode(kind="and", operands=(leaf,) * 33)
        for source in (
            "alpha\x00",
            '"\x7f"',
            '"\u0080"',
            '"\u009f"',
            "\ud800",
            "title:AND",
            "year:\u0660\u0661",
            "year:00000",
        ):
            with self.subTest(source=repr(source)), self.assertRaises(QueryError):
                parse_query(source)

    def test_invalid_utf8_text_and_wire_budgets_fail_before_json_decode(self):
        invalid = parse_query("alpha").to_json().replace("alpha", "\ud800")
        for raw in (invalid, b"\xff", b" " * (MAX_WIRE_BYTES + 1)):
            with (
                self.subTest(raw_type=type(raw).__name__),
                patch(
                    "research_observatory_core.search.contracts.json.loads",
                    side_effect=AssertionError("decoder must not run"),
                ),
                self.assertRaises(QueryError),
            ):
                load_query_document(raw)

    def test_immutable_objects_and_rehydration_reject_constructed_cycles(self):
        query = parse_query("alpha AND beta")
        with self.assertRaises(FrozenInstanceError):
            query.ast.__setattr__("operands", ())
        with self.assertRaises(QueryError):
            QueryNode(kind="year", value=True, operator="=", field="year")
        with self.assertRaises(QueryError):
            QueryDocument("other", query.normalized_query, query.ast)
        cyclic = object.__new__(QueryNode)
        for key, value in (("kind", "not"), ("field", None), ("value", None), ("operator", None)):
            object.__setattr__(cyclic, key, value)
        object.__setattr__(cyclic, "operands", (cyclic,))
        with self.assertRaises(QueryError):
            QueryDocument("alpha", "alpha", cyclic)
        object.__setattr__(query, "original_query", "tampered")
        with self.assertRaises(QueryError):
            query.to_json()
        with self.assertRaises(QueryError):
            object.__new__(QueryDocument).to_dict()

    def test_errors_and_representations_do_not_disclose_query_contents(self):
        secret = "synthetic-private-canary"
        self.assertNotIn(secret, repr(parse_query(secret)))
        self.assertNotIn(secret, repr(parse_query(secret).ast))
        for operation in (lambda: parse_query('"' + secret), lambda: load_query_document('{"x":"' + secret + '"}')):
            try:
                operation()
            except QueryError as error:
                surfaces = (
                    str(error) + repr(error) + repr(error.diagnostic) + "".join(traceback.format_exception(error))
                )
                self.assertNotIn(secret, surfaces)
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
            else:
                self.fail("invalid query accepted")


if __name__ == "__main__":
    unittest.main()
