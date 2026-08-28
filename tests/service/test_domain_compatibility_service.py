from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.domain_compatibility import (  # noqa: E402
    DomainCompatibilityProblem,
    contract_releases,
    negotiate_domain_compatibility,
)


def advertisement(role: str, versions: list[str]) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-compatibility-advertisement",
        "role": role,
        "componentVersion": "1.0.0",
        "contractFamily": "research-observatory-domain",
        "supportedContractVersions": versions,
        "supportedEventVersions": list(versions),
        "schemaSetId": contract_releases()[1]["schemaSetId"],
    }


class DomainCompatibilityServiceTests(unittest.TestCase):
    def test_desktop_sidecar_restart_selects_the_same_current_contract(self) -> None:
        advertisements = [advertisement("desktop", ["0.1.0", "1.0.0"]), advertisement("sidecar", ["0.1.0", "1.0.0"])]
        first = negotiate_domain_compatibility(advertisements)
        restarted = negotiate_domain_compatibility(json.loads(json.dumps(advertisements)))
        self.assertEqual(first, restarted)
        self.assertEqual("1.0.0", restarted["contractVersion"])

    def test_optional_server_can_constrain_the_exact_common_version(self) -> None:
        schema_set_id = contract_releases()[0]["schemaSetId"]
        advertisements = [
            advertisement("desktop", ["0.1.0", "1.0.0"]),
            advertisement("sidecar", ["0.1.0", "1.0.0"]),
            advertisement("server", ["0.1.0"]),
        ]
        for item in advertisements:
            item["schemaSetId"] = schema_set_id
        self.assertEqual("0.1.0", negotiate_domain_compatibility(advertisements)["contractVersion"])

    def test_boundary_denial_exposes_only_a_stable_code(self) -> None:
        hostile = advertisement("sidecar", ["1.0.0"])
        hostile["schemaSetId"] = "sha256:" + "0" * 64
        hostile["privateNote"] = "C:\\private\\draft.txt"
        with self.assertRaises(DomainCompatibilityProblem) as denied:
            negotiate_domain_compatibility([advertisement("desktop", ["1.0.0"]), hostile])
        self.assertEqual(("compatibility-advertisement-invalid",), denied.exception.codes)
        self.assertNotIn("private", str(denied.exception))


if __name__ == "__main__":
    unittest.main()
