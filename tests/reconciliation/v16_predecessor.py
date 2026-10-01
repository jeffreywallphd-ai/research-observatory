"""Frozen populated v16 predecessor, captured before corpus schema changes.

The historical schema objects and rows are restored literally. Neither this
loader nor its witness inventory uses the current storage DDL.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/scholarly-metadata"
SOURCE_COMMIT = "ec1742afb5ecdf9cc516b5dc76f82a33f809c1ac"
FIXTURE_HASHES = {
    "schema-v16-authority.json": "0a698412aa5bd7a5705824cf85b26d831eba71410277dd2fd6591db78e1f3b4d",
    "schema-v16-populated.json": "0f1689aa8da0db72238139a7029d3df1062430627dffdf1903889f9a91cfaebe",
}
ORIGINAL_BINARY_SHA256 = "803ad49622c2b81e60e19bdb016caac5c107c0decf02a3fabba6edf23d05f205"
SCHEMA_SHA256 = "faa1dcd5823f086986ea3a86a8cc85369edd826f2a0c1d724f923bdff9f293f5"
ROWS_SHA256 = "1ed12a874625b8227680372db4dab3981738df88f13dcdf9cb66ec7b77993d64"
PROFILE_SHA256 = "2cf19511744a6536b5da695027768893bd54946460f57172dd790050bdafda72"
APPLICATION_ID = 0x524F4253
PROJECT_ID = "02e2e404-5b49-438e-9b59-ed562626b658"
FIRST_VERSION_REVISION_ID = "01a0f503-65f9-763e-af00-aacc9aca6494"
SECOND_VERSION_REVISION_ID = "01a0f503-663c-77d1-b0a7-445355a0d8ab"
POPULATED_COUNTS = {
    "import_previews": 2,
    "import_source_records": 2,
    "import_manifests": 2,
    "reconciliation_assertions": 2,
    "reconciliation_work_states": 7,
    "reconciliation_versions": 4,
    "reconciliation_version_sources": 4,
    "reconciliation_version_preferences": 1,
    "reconciliation_version_relations": 1,
    "provenance_events": 31,
    "outbox_events": 30,
}


def schema_fingerprint(db: sqlite3.Connection) -> str:
    """Compute the historical fingerprint directly from the stored schema rows."""

    rows = [
        {"type": str(row[0]), "name": str(row[1]), "table": str(row[2]), "sql": str(row[3])}
        for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    payload = json.dumps(rows, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def row_fingerprint(db: sqlite3.Connection) -> str:
    """Hash every historical table row without depending on row or page order."""

    tables = []
    for (name,) in db.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        quoted = '"' + name.replace('"', '""') + '"'
        rows = [
            [{"blobHex": value.hex()} if isinstance(value, bytes) else value for value in row]
            for row in db.execute(f"SELECT * FROM {quoted}")
        ]
        rows.sort(key=lambda row: json.dumps(row, ensure_ascii=True, separators=(",", ":")))
        tables.append({"table": name, "rows": rows})
    payload = json.dumps(tables, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def inspect_v16(database: Path) -> dict[str, object]:
    """Check the frozen database and return its criterion-relevant witnesses."""

    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        if db.execute("PRAGMA user_version").fetchone()[0] != 16:
            raise AssertionError("v16-user-version-changed")
        if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
            raise AssertionError("v16-application-id-changed")
        if schema_fingerprint(db) != SCHEMA_SHA256:
            raise AssertionError("v16-schema-changed")
        if row_fingerprint(db) != ROWS_SHA256:
            raise AssertionError("v16-rows-changed")
        metadata = db.execute(
            "SELECT schema_version,profile_sha256,schema_sha256 FROM schema_metadata WHERE singleton=1"
        ).fetchone()
        if metadata != (16, PROFILE_SHA256, SCHEMA_SHA256):
            raise AssertionError("v16-metadata-changed")
        if db.execute("SELECT project_id FROM projects WHERE singleton=1").fetchone() != (PROJECT_ID,):
            raise AssertionError("v16-project-changed")
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise AssertionError("v16-integrity-failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise AssertionError("v16-foreign-keys-failed")
        counts = {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in POPULATED_COUNTS}
        if counts != POPULATED_COUNTS:
            raise AssertionError("v16-populated-history-changed")
        revisions = {
            row[0]
            for row in db.execute(
                "SELECT revision_id FROM reconciliation_versions WHERE revision_id IN (?,?)",
                (FIRST_VERSION_REVISION_ID, SECOND_VERSION_REVISION_ID),
            )
        }
        if revisions != {FIRST_VERSION_REVISION_ID, SECOND_VERSION_REVISION_ID}:
            raise AssertionError("v16-version-witness-changed")
    return {"projectId": PROJECT_ID, "counts": counts, "versionRevisionIds": tuple(sorted(revisions))}


def restore_v16(database: Path) -> dict[str, object]:
    """Restore literal pre-corpus schema/rows, refusing changed documents."""

    documents = []
    for name, digest in FIXTURE_HASHES.items():
        raw = (FIXTURES / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise AssertionError("v16-fixture-bytes-changed")
        document = json.loads(raw)
        if document["sourceCommit"] != SOURCE_COMMIT or document["schemaVersion"] != 16:
            raise AssertionError("v16-fixture-origin-changed")
        documents.append(document)
    authority, populated = documents
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        raise AssertionError("v16-restore-target-exists")
    with closing(sqlite3.connect(database, autocommit=True)) as db:
        for item in authority["schemaObjects"]:
            if item["type"] == "table":
                db.execute(item["sql"])
        for name, rows in populated["tables"].items():
            quoted = '"' + name.replace('"', '""') + '"'
            for row in rows:
                db.execute(f"INSERT INTO {quoted} VALUES ({','.join('?' for _ in row)})", row)
        for item in authority["schemaObjects"]:
            if item["type"] != "table":
                db.execute(item["sql"])
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute("PRAGMA user_version=16")
        db.execute("PRAGMA foreign_keys=ON")
        if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
            raise AssertionError("v16-journal-mode-unavailable")
        if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() != (0, 0, 0):
            raise AssertionError("v16-checkpoint-failed")
    return inspect_v16(database)
