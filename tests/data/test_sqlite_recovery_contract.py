"""A pre-v17 recovery manifest keeps its exact versioned reader."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[2]
_STORAGE = _ROOT / "packages" / "contracts" / "storage"
_V16_SCHEMA_SHA256 = "80a7a5de635ec1b3d88ee76e16e910dadea6cb11250a0c07ca91689eee418384"


def _v16_manifest() -> dict[str, object]:
    attempt = "a" * 32
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-sqlite-migration-recovery",
        "attemptId": attempt,
        "createdAt": "2026-09-01T12:00:00.000Z",
        "status": "backup-verified",
        "databaseRelativePath": "state/project.sqlite3",
        "projectId": "123e4567-e89b-42d3-a456-426614174000",
        "sourceSchemaVersion": 15,
        "targetSchemaVersion": 16,
        "migrationIds": ["0016_work_versions"],
        "sourceSchemaSha256": "6361c684264358e94c19c90bd67f6f2d47eda21c107d1012a3f86b5cf2faf949",
        "targetSchemaSha256": "faa1dcd5823f086986ea3a86a8cc85369edd826f2a0c1d724f923bdff9f293f5",
        "checkpoint": {"mode": "passive-under-writer-reservation", "logFrames": 0, "checkpointedFrames": 0},
        "backup": {
            "relativePath": f"state/migration-backups/v15-to-v16-{attempt}/project.sqlite3",
            "sha256": "b" * 64,
            "sizeBytes": 1,
            "quickCheck": "ok",
        },
    }


class SqliteRecoveryContractTests(unittest.TestCase):
    def test_old_manifest_retains_exact_predecessor_reader(self) -> None:
        predecessor_path = _STORAGE / "sqlite-migration-recovery.v16.snapshot.json"
        raw = predecessor_path.read_bytes()
        self.assertEqual(_V16_SCHEMA_SHA256, hashlib.sha256(raw).hexdigest())
        schema = json.loads(raw)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(_v16_manifest())))

        altered = _v16_manifest() | {"sourceSchemaSha256": "0" * 64}
        self.assertNotEqual([], list(validator.iter_errors(altered)))

    def test_new_manifest_reader_does_not_reinterpret_v16_history(self) -> None:
        current = json.loads((_STORAGE / "sqlite-migration-recovery.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(current)
        self.assertNotEqual([], list(Draft202012Validator(current).iter_errors(_v16_manifest())))


if __name__ == "__main__":
    unittest.main()
