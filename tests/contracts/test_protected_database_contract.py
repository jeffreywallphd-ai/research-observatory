from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO / "packages" / "contracts" / "storage"


class ProtectedDatabaseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        schema = json.loads((CONTRACT_ROOT / "protected-database-profile.schema.json").read_text(encoding="utf-8"))
        self.profile = json.loads((CONTRACT_ROOT / "protected-database-profile.v1.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)

    def test_profile_is_strict_encrypted_and_vault_backed(self) -> None:
        self.assertEqual([], list(self.validator.iter_errors(self.profile)))
        self.assertEqual("sqlcipher-4.12-community-wal-v1", self.profile["profileId"])
        self.assertEqual("random-raw-256-bit", self.profile["keyProfile"]["material"])
        self.assertEqual(
            ["project-files", "exports", "logs", "environment", "process-arguments"],
            self.profile["keyProfile"]["forbiddenDestinations"],
        )
        self.assertIn("cipher_integrity_check", self.profile["connectionControls"]["integrityChecks"])
        self.assertIn("fail-closed", self.profile["keyLoss"])

    def test_profile_rejects_plaintext_or_weakened_key_authority(self) -> None:
        for path, value in (
            (("profileId",), "sqlite-wal-v1"),
            (("plaintextPolicy",), "plaintext-allowed"),
            (("keyProfile", "material"), "passphrase"),
            (("keyProfile", "authority"), "project-file"),
            (("connectionControls", "plaintextHeaderBytes"), 32),
        ):
            with self.subTest(path=path):
                changed = copy.deepcopy(self.profile)
                target = changed
                for segment in path[:-1]:
                    target = target[segment]
                target[path[-1]] = value
                self.assertTrue(list(self.validator.iter_errors(changed)))
        expanded = copy.deepcopy(self.profile)
        expanded["keyPath"] = "C:/secret"
        self.assertTrue(list(self.validator.iter_errors(expanded)))


if __name__ == "__main__":
    unittest.main()
