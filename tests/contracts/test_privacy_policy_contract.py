from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, ClassVar

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "packages" / "contracts" / "privacy"


class PrivacyPolicyContractTests(unittest.TestCase):
    schema: ClassVar[dict[str, Any]]
    profile: ClassVar[dict[str, Any]]
    validator: ClassVar[Draft202012Validator]

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads((CONTRACT / "privacy-policy.schema.json").read_text(encoding="utf-8"))
        cls.profile = json.loads((CONTRACT / "privacy-policy.v1.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_canonical_profile_is_strict_and_valid(self) -> None:
        self.assertEqual([], list(self.validator.iter_errors(self.profile)))
        self.assertNotIn("path", json.dumps(self.profile).casefold())
        self.assertNotIn("credential", json.dumps(self.profile).casefold())

    def test_defaults_are_offline_and_remote_telemetry_is_not_implemented(self) -> None:
        self.assertEqual(self.profile["defaults"]["networkPolicy"], "offline")
        self.assertEqual(self.profile["defaults"]["telemetryMode"], "off")
        self.assertFalse(self.profile["telemetry"]["remoteTelemetryImplemented"])
        changed = json.loads(json.dumps(self.profile))
        changed["defaults"]["networkPolicy"] = "approved-providers"
        self.assertNotEqual([], list(self.validator.iter_errors(changed)))

    def test_egress_and_deletion_never_overclaim_authority(self) -> None:
        self.assertFalse(self.profile["egress"]["settingChangeSendsData"])
        self.assertEqual(self.profile["egress"]["objectContentOutcomes"]["metadata-only"], "deny")
        self.assertEqual(
            self.profile["egress"]["objectContentOutcomes"]["approved-providers"],
            "require-confirmation",
        )
        deletion = self.profile["cacheDeletion"]
        self.assertTrue(deletion["logicalRemoval"])
        self.assertFalse(deletion["physicalErasureGuaranteed"])
        self.assertTrue(deletion["canonicalProjectDataExcluded"])
        unsafe = json.loads(json.dumps(self.profile))
        unsafe["cacheDeletion"]["physicalErasureGuaranteed"] = True
        self.assertNotEqual([], list(self.validator.iter_errors(unsafe)))


if __name__ == "__main__":
    unittest.main()
