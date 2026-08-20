from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any, ClassVar

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO / "packages" / "contracts" / "security"


class CredentialStoreContractTests(unittest.TestCase):
    profile: ClassVar[dict[str, Any]]
    validator: ClassVar[Any]

    @classmethod
    def setUpClass(cls) -> None:
        schema = json.loads((CONTRACT_ROOT / "credential-store-profile.schema.json").read_text(encoding="utf-8"))
        cls.profile = json.loads((CONTRACT_ROOT / "credential-store-profile.v1.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def test_exact_profile_is_strict_user_scoped_and_secret_safe(self) -> None:
        self.assertEqual([], list(self.validator.iter_errors(self.profile)))
        self.assertEqual("windows-current-user-dpapi", self.profile["osProtection"])
        self.assertEqual("forbidden", self.profile["machineScope"])
        self.assertEqual("null-prompt-ui-forbidden", self.profile["promptMode"])
        self.assertEqual("xchacha20poly1305-with-scope-aad", self.profile["recordAuthentication"])
        self.assertEqual("hmac-sha256-no-plaintext-identifiers", self.profile["physicalIdentity"])
        self.assertEqual("callback-lease-zeroed-on-close", self.profile["secretDelivery"])
        self.assertEqual("cross-process-lock-create-or-compare-and-swap", self.profile["writeConcurrency"])
        self.assertEqual(
            "capability-purpose-operation-outcome-reason-context-opaque-reference-only",
            self.profile["auditProjection"],
        )
        self.assertEqual(
            ["provider-key", "connector-token", "signing-trust", "encryption-key-material"],
            self.profile["secretKinds"],
        )
        self.assertEqual(
            ["sqlite", "project-package", "project-export", "support-bundle", "process-arguments"],
            self.profile["forbiddenSecretDestinations"],
        )

    def test_profile_rejects_weaker_scope_and_contract_expansion(self) -> None:
        for field, value in (
            ("machineScope", "allowed"),
            ("recordAuthentication", "dpapi-only"),
            ("physicalIdentity", "provider-and-secret-name"),
            ("secretDelivery", "plain-bytes-dto"),
            ("auditProjection", "reason-only"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.profile)
                changed[field] = value
                self.assertTrue(list(self.validator.iter_errors(changed)))
        expanded = copy.deepcopy(self.profile)
        expanded["implementationPath"] = "C:/private/vault"
        self.assertTrue(list(self.validator.iter_errors(expanded)))


if __name__ == "__main__":
    unittest.main()
