from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from runtime_check import declaration_errors, extract_version, installed_errors, load_contract  # noqa: E402


class RuntimeContractTests(unittest.TestCase):
    def test_declarations_and_lockfiles_match_contract(self) -> None:
        contract = load_contract(REPO)
        self.assertEqual([], declaration_errors(REPO, contract))

    def test_extracts_versions_from_ecosystem_outputs(self) -> None:
        self.assertEqual("24.19.0", extract_version("v24.19.0"))
        self.assertEqual("1.96.1", extract_version("rustc 1.96.1 (example)"))

    def test_rejects_unsupported_runtime_with_actionable_message(self) -> None:
        contract = json.loads(json.dumps(load_contract(REPO)))

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            outputs = {
                "node": "v20.20.1",
                "python": "Python 3.14.6",
                "rustc": "rustc 1.96.1",
                "pnpm": "11.20.0",
                "uv": "uv 0.12.2",
            }
            key = "pnpm" if command[0] in {"corepack", "corepack.cmd"} else command[0]
            return subprocess.CompletedProcess(command, 0, outputs[key], "")

        errors = installed_errors(contract, runner)
        self.assertEqual(1, len(errors))
        self.assertIn("node 20.20.1 is unsupported; expected 24.19.0", errors[0])
        self.assertIn("Install Node.js 24.19.0 LTS", errors[0])

    def test_rejects_missing_tool_with_install_hint(self) -> None:
        contract = json.loads(json.dumps(load_contract(REPO)))

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if command[0] == "rustc":
                raise FileNotFoundError(command[0])
            expected = {
                "node": "v24.19.0",
                "python": "Python 3.14.6",
                "pnpm": "11.20.0",
                "uv": "uv 0.12.2",
            }
            key = "pnpm" if command[0] in {"corepack", "corepack.cmd"} else command[0]
            return subprocess.CompletedProcess(command, 0, expected[key], "")

        errors = installed_errors(contract, runner)
        self.assertEqual(1, len(errors))
        self.assertIn("rust is unavailable", errors[0])
        self.assertIn("Install rustup", errors[0])


if __name__ == "__main__":
    unittest.main()
