"""Reject vacuous native-test success in the bounded T03 evidence runner."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "t03_verification_evidence", REPO / "artifacts/evidence/W1.A09.T03.verify-01.py"
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class VerificationEvidenceTests(unittest.TestCase):
    def test_zero_or_missing_native_test_result_is_not_passing_evidence(self) -> None:
        for output in (
            "running 0 tests\ntest result: ok. 0 passed; 0 failed; 95 filtered out",
            "", "running 6 tests", "test result: FAILED. 5 passed; 1 failed",
        ):
            with self.subTest(output=output):
                self.assertFalse(runner.native_tests_executed(output))

    def test_completed_nonzero_native_suite_is_recognized(self) -> None:
        self.assertTrue(runner.native_tests_executed(
            "running 6 tests\ntest result: ok. 6 passed; 0 failed; 0 ignored; 89 filtered out"
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
