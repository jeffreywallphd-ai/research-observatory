"""Literal approved v15 database; independent of current generated DDL and rows."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from research_observatory_core import storage

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/scholarly-metadata"
SCHEMA_SHA = "6361c684264358e94c19c90bd67f6f2d47eda21c107d1012a3f86b5cf2faf949"
PROFILE_SHA = "1db7b16d30ea6c1b629ba935c68a542129855391ab69246f62696623d067cd37"
FIXTURE_HASHES = {
    "schema-v15-authority.json": "6b9d71f80a0ad0eb0b7df50a49a50b7bf839df7ebdaeecfd340a169a4a61a7a8",
    "schema-v15-populated.json": "7934d48dd53592de28fcd7feff317fa0d2df18e61e9292f7b5a37ea70736b098",
}


def restore_v15(database: Path) -> dict:
    documents = []
    for name, digest in FIXTURE_HASHES.items():
        raw = (FIXTURES / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise AssertionError("v15-fixture-differs")
        document = json.loads(raw)
        if document["sourceCommit"] != "0738c2543db85af8189bd0948393698b04662de6":
            raise AssertionError("v15-fixture-origin-differs")
        documents.append(document)
    authority, populated = documents
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, autocommit=True)) as db:
        for item in authority["schemaObjects"]:
            if item["type"] == "table":
                db.execute(item["sql"])
        for table, rows in populated["tables"].items():
            for row in rows:
                db.execute('INSERT INTO "' + table + '" VALUES (' + ",".join("?" for _ in row) + ")", row)
        for item in authority["schemaObjects"]:
            if item["type"] != "table":
                db.execute(item["sql"])
        db.execute("PRAGMA user_version=15")
        db.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        storage._configure_connection(db, initialize=True)
        if storage._schema_fingerprint(db) != SCHEMA_SHA or db.execute("PRAGMA foreign_key_check").fetchall():
            raise AssertionError("v15-frozen-fixture-invalid")
    return populated
