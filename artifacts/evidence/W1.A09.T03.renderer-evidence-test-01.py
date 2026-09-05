"""Synthetic report-scope and publication-race tests; no browser or native UI."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "t03_renderer_evidence", REPO / "artifacts/evidence/W1.A09.T03.renderer-check-01.py"
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RendererEvidenceTests(unittest.TestCase):
    def test_scope_and_namespace_rejected_before_filesystem_access(self) -> None:
        with mock.patch.object(Path, "exists", side_effect=AssertionError("unexpected access")):
            for path in (
                REPO / "outside.json",
                runner.REPORTS / "W9.A01.T01.json",
                runner.REPORTS / "../outside.json",
            ):
                with self.subTest(name=path.name), self.assertRaisesRegex(ValueError, "scope|namespace"):
                    runner.report_target(path)

    def test_concurrent_publication_preserves_existing_bytes(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="renderer-evidence-", dir=REPO / "artifacts/tmp"))
        path = root / "W1.A09.T03.renderer-check-01.race.json"
        with mock.patch.object(runner, "REPORTS", root):
            self.assertEqual(runner.report_target(path), path)
            path.write_text("synthetic concurrent witness", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                runner.publish_report(path, {"unexpected": True})
            with mock.patch.object(runner, "report_target", return_value=path), self.assertRaises(FileExistsError):
                runner.publish_report(path, {"unexpected": True})
            self.assertEqual(path.read_text(encoding="utf-8"), "synthetic concurrent witness")
            successful = root / "W1.A09.T03.renderer-check-01.success.json"
            runner.publish_report(successful, {"synthetic": True})
            self.assertEqual(json.loads(successful.read_text(encoding="utf-8")), {"synthetic": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
