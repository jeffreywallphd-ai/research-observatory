from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class ProtectedDatabasePerformanceCheckTests(unittest.TestCase):
    def test_check_records_required_distributions_and_passes_absolute_budgets(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="protected-database-performance-", dir=REPO / "artifacts" / "tmp"
        ) as temp:
            report = Path(temp) / "report.json"
            completed = subprocess.run(
                [
                    str(REPO / ".venv" / "Scripts" / "python.exe"),
                    str(REPO / "tools" / "protected_database_performance_check.py"),
                    "--repo",
                    str(REPO),
                    "--report",
                    str(report),
                    "--repetitions",
                    "2",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            document = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(document["ok"])
            self.assertEqual(document["repetitionsPerMetric"], 2)
            self.assertEqual(
                set(document["metrics"]),
                {"open", "representativeQuery", "integrity", "backup", "plaintextMigration", "rekey"},
            )
            for metric in document["metrics"].values():
                self.assertEqual(len(metric["samplesMilliseconds"]), 2)
                self.assertEqual(metric["futureRegressionThresholdPercent"], 20)


if __name__ == "__main__":
    unittest.main()
