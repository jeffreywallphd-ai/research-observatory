"""Literal v14 restore for migration tests; no generated/current DDL or rows."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from research_observatory_core import storage

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/scholarly-metadata"
SCHEMA_SHA = "4b8b87b1024b855fa1eee932b41b9d4a8d8492823b17968eb3d17eda24b5ccb2"
PROFILE_SHA = "49ee17767e8a0652a381925181f3a6e38722b9635f15f704c22b648f0e981a89"
FIXTURE_HASHES = {
    "schema-v14-populated.json": "c361c336f5f5840c048236b1a49d09349dc419641f9567c9ca77c43bdc6f2efd",
    "schema-v14-identity-cases.json": "cdbf01f6f93d43872a7c470ac6fa4b9bcb4dc71782415d74f9367fd672297e17",
}


def restore_v14(database: Path, fixture: str = "schema-v14-identity-cases.json") -> dict:
    authority_raw = (FIXTURES / "schema-v14-authority.json").read_bytes()
    if hashlib.sha256(authority_raw).hexdigest() != "d0e7f06c2066b5fe12c23175e75a42152c752d732a304258bbe648e92414310d":
        raise AssertionError("v14-schema-fixture-differs")
    if fixture not in FIXTURE_HASHES:
        raise AssertionError("v14-fixture-unknown")
    raw = (FIXTURES / fixture).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_HASHES[fixture]:
        raise AssertionError("v14-populated-fixture-differs")
    authority, populated = json.loads(authority_raw), json.loads(raw)
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
        db.execute("PRAGMA user_version=14")
        db.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        storage._configure_connection(db, initialize=True)
        if storage._schema_fingerprint(db) != SCHEMA_SHA or db.execute("PRAGMA foreign_key_check").fetchall():
            raise AssertionError("v14-frozen-fixture-invalid")
    return populated
