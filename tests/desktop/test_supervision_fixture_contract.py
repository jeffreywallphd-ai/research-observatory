"""Keep release supervision stimuli aligned with the existing strict contract.

These are source-contract checks, not actual process or packaging qualification.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.modules import default_module_registry  # noqa: E402


def literal_array(body: str) -> list[str]:
    return json.loads("[" + re.sub(r",\s*$", "", body) + "]")


class SupervisionFixtureContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.capabilities = list(default_module_registry().capabilities)

    def test_production_supervisor_matches_core_capabilities(self) -> None:
        source = (ROOT / "apps/desktop/src-tauri/src/supervisor.rs").read_text(encoding="utf-8")
        matches = re.findall(r"const EXPECTED_CORE_CAPABILITIES: &\[&str\] = &\[(.*?)\];", source, re.S)
        self.assertEqual(1, len(matches))
        self.assertEqual(self.capabilities, literal_array(matches[0]))

    def test_measurement_health_expectation_matches_core_capabilities(self) -> None:
        source = (ROOT / "apps/desktop/src-tauri/examples/supervision_check.rs").read_text(encoding="utf-8")
        matches = re.findall(r'body\["capabilities"\]\s*==\s*serde_json::json!\(\[(.*?)\]\)', source, re.S)
        self.assertEqual(1, len(matches))
        self.assertEqual(self.capabilities, literal_array(matches[0]))

    def test_fixture_handshake_and_readiness_match_core_capabilities(self) -> None:
        source = (ROOT / "apps/desktop/src-tauri/examples/supervisor_fixture.rs").read_text(encoding="utf-8")
        matches = re.findall(r'\\"capabilities\\":(\[.*?\])', source)
        self.assertEqual(2, len(matches), "Both handshake and readiness stimuli must be checked")
        for index, encoded in enumerate(matches):
            with self.subTest(message=index):
                self.assertEqual(self.capabilities, json.loads(json.loads('"' + encoded + '"')))


if __name__ == "__main__":
    unittest.main()
