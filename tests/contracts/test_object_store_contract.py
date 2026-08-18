from __future__ import annotations

import copy
import importlib
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"


class ObjectStoreContractTests(unittest.TestCase):
    def setUp(self) -> None:
        contract_root = REPO / "packages" / "contracts" / "storage"
        self.profile = json.loads((contract_root / "object-store-profile.v1.json").read_text(encoding="utf-8"))
        self.schema = json.loads((contract_root / "object-store-profile.schema.json").read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(self.schema)

    def test_exact_profile_is_strict_and_declares_the_encrypted_storage_boundary(self) -> None:
        self.assertEqual([], list(self.validator.iter_errors(self.profile)))
        self.assertEqual("project-only", self.profile["deduplicationScope"])
        self.assertEqual("verified-controlled-stream-no-path", self.profile["openMode"])
        self.assertEqual(
            "restore-unless-delete-metadata-committed",
            self.profile["deleteCrashRecovery"],
        )
        self.assertEqual("bounded-busy-retry", self.profile["activeReaderDelete"])
        self.assertEqual(
            "document-link-requires-available-object",
            self.profile["referenceAvailability"],
        )
        self.assertEqual("secretstream-xchacha20poly1305-v1", self.profile["encryptionBoundary"])
        self.assertEqual("explicit-test-only", self.profile["plaintextFixtureMode"])
        self.assertEqual("forbidden", self.profile["plaintextTemporaryStorage"])
        self.assertEqual(
            "pre-open-durable-journaled-verified-copy-on-write",
            self.profile["priorEnvelopeUpgrade"],
        )
        self.assertEqual("mandatory-core-pre-open-coordinator", self.profile["upgradeComposition"])
        self.assertEqual(
            "retain-plaintext-outside-temp-until-production-open-verifies",
            self.profile["upgradeRollback"],
        )
        self.assertEqual(
            "pre-and-post-journal-fsync-rename-verification-metadata-commit-cleanup",
            self.profile["upgradeInterruptionCoverage"],
        )
        self.assertEqual(
            "journaled-safe-boundary-preserve-and-resume",
            self.profile["upgradeCancellation"],
        )
        self.assertEqual("corrupt-quarantine", self.profile["malformedEnvelopeFailure"])
        self.assertEqual("key-unavailable-preserve", self.profile["wrappedKeyAuthenticationFailure"])
        self.assertEqual(
            "deployment-supplied-project-and-shared-cache-soft-hard-thresholds",
            self.profile["quotaPolicy"],
        )
        self.assertEqual(
            "deny-new-object-writes-preserve-reads-and-cleanup",
            self.profile["lowDiskBehavior"],
        )
        self.assertEqual(
            "unreferenced-derived-rebuildable-only",
            self.profile["automaticCanonicalReclamation"],
        )
        self.assertEqual(
            "preview-lease-revalidate-reference-reader-and-file-identity",
            self.profile["garbageCollection"],
        )
        self.assertEqual(
            "optional-explicit-root-layout-deferred-to-cap-02-s05",
            self.profile["sharedCacheAuthority"],
        )
        self.assertEqual("authenticated-encrypted-object-adapter", self.profile["releaseQualification"])

        changed = copy.deepcopy(self.profile)
        changed["deduplicationScope"] = "cross-project"
        self.assertTrue(list(self.validator.iter_errors(changed)))
        expanded = copy.deepcopy(self.profile)
        expanded["filesystemPath"] = "objects/plaintext-hash"
        self.assertTrue(list(self.validator.iter_errors(expanded)))

    def test_port_import_is_dependency_neutral_and_exposes_no_adapter_factory(self) -> None:
        sys.path.insert(0, str(SERVICE_SRC))
        try:
            before_sqlite = "sqlite3" in sys.modules
            before_sqlalchemy = "sqlalchemy" in sys.modules
            port = importlib.import_module("research_observatory_core.ports.object_store")
            self.assertEqual(before_sqlite, "sqlite3" in sys.modules)
            self.assertEqual(before_sqlalchemy, "sqlalchemy" in sys.modules)
            self.assertFalse(hasattr(port, "create_local_object_store"))
        finally:
            sys.path.remove(str(SERVICE_SRC))


if __name__ == "__main__":
    unittest.main()
