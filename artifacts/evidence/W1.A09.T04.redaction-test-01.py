"""Synthetic identifiers exercise publication redaction, not real account discovery."""

import importlib.util
import unittest
from pathlib import Path


def load_package_runner():
    path = Path(__file__).with_name("W1.A09.T04.package-check-01.py")
    spec = importlib.util.spec_from_file_location("t04_package_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvidenceRedactionTests(unittest.TestCase):
    def test_plain_and_repr_paths_are_redacted(self):
        runner = load_package_runner()
        for value in (r"C:\Users\example-test\runtime", repr(r"C:\Users\example-test\runtime"),
                      repr(str(runner.REPO / "tools"))):
            with self.subTest(value=value):
                redacted = runner.redact(value)
                self.assertNotIn("example-test", redacted)
                self.assertNotIn(str(runner.REPO).replace("\\", "\\\\"), redacted)

    def test_git_principal_diagnostics_are_redacted_not_erased(self):
        runner = load_package_runner()
        value = "fatal: detected dubious ownership\n\tExamplePC/TestAccount (S-1-5-21-111-222-333-1001)\n"
        redacted = runner.redact(value)
        self.assertIn("fatal: detected dubious ownership", redacted)
        self.assertNotIn("TestAccount", redacted)
        self.assertNotIn("S-1-5-", redacted)

    def test_test_outcome_and_repository_relative_evidence_are_unchanged(self):
        runner = load_package_runner()
        value = "FAILED (failures=1) artifacts/evidence/W1.A09.T04.verification-units-01.json"
        self.assertEqual(value, runner.redact(value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
