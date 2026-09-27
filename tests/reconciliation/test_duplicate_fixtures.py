"""Authenticate pre-scoring labels and exact populated predecessor independently."""

import csv
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from research_observatory_core import storage
from research_observatory_core.reconciliation.contracts import ReconciliationResult, SourceAssertion

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BENCHMARK = FIXTURES / "scholarly-duplicates"
METADATA = FIXTURES / "scholarly-metadata"
V14_SCHEMA = "4b8b87b1024b855fa1eee932b41b9d4a8d8492823b17968eb3d17eda24b5ccb2"
V14_PROFILE = "49ee17767e8a0652a381925181f3a6e38722b9635f15f704c22b648f0e981a89"


class DuplicateFixtureTests(unittest.TestCase):
    def test_frozen_source_bytes_labels_and_component_disjoint_split(self):
        raw = (BENCHMARK / "benchmark-v1.json").read_bytes()
        self.assertEqual(
            "6b77da6f8aef1fe669bcfa607cfda184e357ae7742333a74588d224a69ef6d8c", hashlib.sha256(raw).hexdigest()
        )
        manifest = json.loads(raw)
        rows = {}
        for name, expected in manifest["members"].items():
            member = (BENCHMARK / name).read_bytes()
            self.assertEqual(expected["fixtureSha256"], hashlib.sha256(member).hexdigest())
            self.assertEqual(expected["fixtureByteLength"], len(member))
            decoded = member.decode(expected["fixtureEncoding"])
            original = decoded.encode(expected["encoding"])
            self.assertEqual(expected["sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(expected["byteLength"], len(original))
            rows[name] = list(csv.DictReader(io.StringIO(decoded, newline="")))
            self.assertEqual(expected["rowCount"], len(rows[name]))
        left = {"dblp:" + row["id"] for row in rows["DBLP2.csv"]}
        right = {"acm:" + row["id"] for row in rows["ACM.csv"]}
        self.assertEqual((2616, 2294), (len(left), len(right)))
        pairs = {("dblp:" + row["idDBLP"], "acm:" + row["idACM"]) for row in rows["DBLP-ACM_perfectMapping.csv"]}
        self.assertEqual(2224, len(pairs))
        self.assertEqual(2224, len({pair[0] for pair in pairs}))
        self.assertEqual(2224, len({pair[1] for pair in pairs}))
        self.assertTrue(all(a in left and b in right for a, b in pairs))
        expected_splits = {"development": set(), "qualification": set()}
        matched = {item for pair in pairs for item in pair}
        components = [sorted(pair) for pair in pairs] + [[item] for item in (left | right) - matched]
        for component in components:
            digest = hashlib.sha256(("DBLP-ACM-component-split-v1\n" + "\n".join(component)).encode()).digest()
            expected_splits["development" if digest[0] % 2 == 0 else "qualification"].update(component)
        self.assertEqual(left | right, set.union(*expected_splits.values()))
        self.assertFalse(set.intersection(*expected_splits.values()))
        for name, expected in expected_splits.items():
            self.assertEqual(sorted(expected), manifest["splits"][name])
            self.assertGreater(sum(a in expected and b in expected for a, b in pairs), 1000)
        self.assertEqual(
            {"precisionMinimum": 0.90, "recallMinimum": 0.95, "appliesTo": ["development", "qualification"]},
            manifest["targets"],
        )

    def test_exact_populated_v14_schema_restores_without_current_ddl(self):
        authority_raw = (METADATA / "schema-v14-authority.json").read_bytes()
        populated_raw = (METADATA / "schema-v14-populated.json").read_bytes()
        self.assertEqual(
            "d0e7f06c2066b5fe12c23175e75a42152c752d732a304258bbe648e92414310d",
            hashlib.sha256(authority_raw).hexdigest(),
        )
        self.assertEqual(
            "c361c336f5f5840c048236b1a49d09349dc419641f9567c9ca77c43bdc6f2efd",
            hashlib.sha256(populated_raw).hexdigest(),
        )
        authority, populated = json.loads(authority_raw), json.loads(populated_raw)
        for document in (authority, populated):
            self.assertEqual(
                (14, V14_SCHEMA, V14_PROFILE),
                (document["schemaVersion"], document["schemaSha256"], document["profileSha256"]),
            )
            self.assertEqual("691205f48cf8ee80b323a9971413f7da1d0608e1", document["sourceCommit"])
        with tempfile.TemporaryDirectory(prefix="ro-v14-frozen-") as temporary:
            database = Path(temporary) / "project.sqlite3"
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
                self.assertEqual(V14_SCHEMA, storage._schema_fingerprint(db))
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual("ok", db.execute("PRAGMA quick_check").fetchone()[0])
                assertions = [
                    SourceAssertion.model_validate_json(row[0])
                    for row in db.execute("SELECT assertion_json FROM reconciliation_assertions")
                ]
                receipts = [
                    ReconciliationResult.model_validate_json(row[0])
                    for row in db.execute("SELECT result_json FROM reconciliation_assertions")
                ]
                self.assertEqual(2, len(assertions))
                self.assertEqual({"new-work", "exact-linked"}, {item.disposition for item in receipts})
                self.assertEqual(1, len({item.work_id for item in receipts}))
                self.assertEqual(2, len({item.work_revision_id for item in receipts}))
                self.assertEqual(
                    {"Synthetic", "Synthetic competing title"},
                    {field.observed for item in assertions for field in item.fields if field.name == "title"},
                )
                for item in assertions:
                    self.assertTrue(
                        all(item.rights.permits(action) for action in ("store", "inspect", "derive", "index"))
                    )
                    row = db.execute(
                        "SELECT raw_sha256 FROM import_manifest_members WHERE project_id=? "
                        "AND manifest_revision_id=? AND ordinal=? AND source_record_revision_id=?",
                        (item.project_id, item.address.revision_id, item.address.ordinal, item.source_revision_id),
                    ).fetchone()
                    self.assertIsNotNone(row)
                    self.assertEqual(row[0], item.source_sha256)


if __name__ == "__main__":
    unittest.main()
