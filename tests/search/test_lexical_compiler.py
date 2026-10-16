"""Field/Boolean lowering never interpolates private query values into SQL."""

import sqlite3
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.search import QueryError, QueryNode, parse_query  # noqa: E402
from research_observatory_core.search.compiler import compile_query  # noqa: E402


class LexicalCompilerTests(unittest.TestCase):
    def test_only_closed_field_names_and_quoted_bound_fts_values(self):
        value = 'title:"private \\"marker\\" OR x" OR full-text:alpha-beta'
        compiled = compile_query(parse_query(value))
        self.assertNotIn("private", compiled.sql)
        self.assertNotIn("alpha", compiled.sql)
        self.assertEqual(('title : "private ""marker"" OR x"', 'full_text : "alpha-beta"'), compiled.parameters)
        self.assertNotIn("private", repr(compiled))

    def test_complement_uses_same_authorized_universe_and_each_leaf_is_filtered(self):
        compiled = compile_query(parse_query("NOT title:alpha OR beta AND year>=2020"))
        self.assertIn("FROM allowed_items EXCEPT", compiled.sql)
        self.assertEqual(3, compiled.sql.count("JOIN allowed_entries"))
        self.assertIn("INTERSECT", compiled.sql)
        self.assertIn("UNION", compiled.sql)
        self.assertIn("year >= ?", compiled.sql)
        self.assertEqual(('title : "alpha"', '"beta"', 2020), compiled.parameters)

    def test_forged_snapshot_is_revalidated(self):
        query = parse_query("alpha")
        with self.assertRaises(QueryError):
            compile_query(replace(query, ast=QueryNode("literal", field="title", value="alpha")))

    def test_real_sql_set_semantics_and_denied_field_do_not_cross_contaminate(self):
        # Ordinary in-memory SQLite tests lowering only, not protected storage.
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(
            "CREATE TABLE search_rows(rowid INTEGER PRIMARY KEY,entry_id TEXT,item_id TEXT,year INTEGER);"
            "CREATE VIRTUAL TABLE search_fts USING fts5(title,full_text,tokenize='unicode61 remove_diacritics 2');"
            "CREATE TEMP TABLE allowed_items(item_id TEXT PRIMARY KEY);"
            "CREATE TEMP TABLE allowed_entries(entry_id TEXT PRIMARY KEY);"
        )
        for row, entry, item, year, title, text in (
            (1, "a", "one", 2024, "alpha-beta café", ""),
            (2, "b", "one", 2024, "", "gamma"),
            (3, "c", "two", 2019, "delta", "restrictedsecret"),
            (4, "d", "three", None, "omega", ""),
        ):
            db.execute("INSERT INTO search_rows VALUES (?,?,?,?)", (row, entry, item, year))
            db.execute("INSERT INTO search_fts(rowid,title,full_text) VALUES (?,?,?)", (row, title, text))
        db.executemany("INSERT INTO allowed_items VALUES (?)", [(x,) for x in ("one", "two")])
        db.executemany("INSERT INTO allowed_entries VALUES (?)", [(x,) for x in ("a", "b", "d")])
        for query, expected in (
            ("alpha-beta AND gamma", ("one",)),
            ("title:cafe", ("one",)),
            ("NOT alpha", ("two",)),
            ("NOT full-text:restrictedsecret", ("one", "two")),
            ("full-text:restrictedsecret", ()),
            ("!!!", ()),
            ("year>=2020 AND gamma", ("one",)),
            ("NOT NOT alpha", ("one",)),
            ("omega", ()),
        ):
            with self.subTest(query=query):
                compiled = compile_query(parse_query(query))
                self.assertEqual(expected, tuple(row[0] for row in db.execute(compiled.sql, compiled.parameters)))


if __name__ == "__main__":
    unittest.main()
