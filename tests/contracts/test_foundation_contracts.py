from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from ci_check import validate_ci  # noqa: E402
from runtime_check import declaration_errors, load_contract  # noqa: E402


class FoundationPortableContractTests(unittest.TestCase):
    def test_runtime_declarations_are_portable_and_locked(self) -> None:
        contract = load_contract(REPO)

        self.assertEqual([], declaration_errors(REPO, contract))

    def test_ci_contract_is_locally_enforceable(self) -> None:
        self.assertEqual([], validate_ci(REPO))


if __name__ == "__main__":
    unittest.main()
