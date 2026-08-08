from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from benchmark_registry import (  # noqa: E402
    REGISTRY_PATH,
    approval_errors,
    baseline_lineage_errors,
    load_registry,
    run_benchmarks,
    safe_output_path,
)


class BenchmarkRegistryTests(unittest.TestCase):
    def temporary_repo(self, temporary: str) -> Path:
        root = Path(temporary)
        shutil.copytree(REPO / "evaluation", root / "evaluation")
        dataset = root / "tests" / "fixtures" / "scholarly-corpus" / "metadata"
        dataset.mkdir(parents=True)
        shutil.copy2(
            REPO / "tests" / "fixtures" / "scholarly-corpus" / "metadata" / "records.json",
            dataset / "records.json",
        )
        (root / "artifacts" / "tmp").mkdir(parents=True)
        return root

    def load_manifest(self, root: Path) -> dict[str, Any]:
        return json.loads((root / REGISTRY_PATH).read_text(encoding="utf-8"))

    def write_manifest(self, root: Path, manifest: dict[str, Any]) -> None:
        (root / REGISTRY_PATH).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def test_two_canonical_benchmarks_run_end_to_end_deterministically(self) -> None:
        first, first_actuals = run_benchmarks(REPO)
        second, second_actuals = run_benchmarks(REPO)

        self.assertEqual("PASS", first["status"])
        self.assertEqual(first, second)
        self.assertEqual(first_actuals, second_actuals)
        self.assertEqual(
            {"golden-parsing", "contract-validation"},
            {result["kind"] for result in first["results"]},
        )
        self.assertTrue(all(result["metrics"]["exactMatch"] == 1 for result in first["results"]))

    def test_dataset_and_baseline_tampering_fail_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            dataset = root / "tests" / "fixtures" / "scholarly-corpus" / "metadata" / "records.json"
            dataset.write_bytes(dataset.read_bytes() + b"tampered")

            report, _ = run_benchmarks(root)

        self.assertEqual("FAIL", report["status"])
        self.assertTrue(any("SHA-256 mismatch" in error for error in report["errors"]))

        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            baseline = root / "evaluation" / "baselines" / "golden-metadata-normalization-v1.json"
            before = baseline.read_bytes()
            baseline.write_bytes(before + b" ")

            report, _ = run_benchmarks(root)

            self.assertEqual(before + b" ", baseline.read_bytes())
        self.assertEqual("FAIL", report["status"])
        self.assertTrue(any("SHA-256 mismatch" in error for error in report["errors"]))

    def test_changed_baseline_requires_exact_version_history_and_approval(self) -> None:
        previous = self.load_manifest(REPO)
        current = copy.deepcopy(previous)
        item = current["benchmarks"][0]
        old_hash = item["expected"]["sha256"]
        new_hash = "1" * 64
        item["expected"]["sha256"] = new_hash
        item["baseline"]["sha256"] = new_hash

        errors = baseline_lineage_errors(current, previous)

        self.assertTrue(any("increment exactly one version" in error for error in errors))
        self.assertTrue(any("append the exact previous baseline" in error for error in errors))
        self.assertTrue(any("requires currentApproval" in error for error in errors))

        item["baseline"] = {
            "version": 2,
            "sha256": new_hash,
            "history": [{"version": 1, "sha256": old_hash, "approval": None}],
            "currentApproval": "evaluation/approvals/golden-v2.json",
        }
        self.assertEqual([], baseline_lineage_errors(current, previous))

    def test_version_two_requires_valid_distinct_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            manifest = self.load_manifest(root)
            item = manifest["benchmarks"][0]
            baseline_path = root / item["expected"]["path"]
            value = json.loads(baseline_path.read_text(encoding="utf-8"))
            value["baselineNote"] = "approved intentional change"
            baseline_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            old_hash = item["expected"]["sha256"]
            new_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
            approval_path = "evaluation/approvals/golden-v2.json"
            item["expected"]["sha256"] = new_hash
            item["baseline"] = {
                "version": 2,
                "sha256": new_hash,
                "history": [{"version": 1, "sha256": old_hash, "approval": None}],
                "currentApproval": approval_path,
            }
            approval = {
                "schemaVersion": "1.0",
                "documentType": "baseline-approval",
                "status": "approved",
                "benchmarkId": item["id"],
                "fromVersion": 1,
                "toVersion": 2,
                "oldSha256": old_hash,
                "newSha256": new_hash,
                "generatedBy": "codex",
                "approvedBy": "human:benchmark-owner",
                "approvedAt": "2026-08-08T16:00:00+00:00",
                "rationale": "Reviewed semantic improvement.",
            }
            (root / approval_path).write_text(json.dumps(approval), encoding="utf-8")
            self.write_manifest(root, manifest)

            _, _, errors = load_registry(root)

            self.assertEqual([], errors)
            approval["generatedBy"] = "human:benchmark-owner"
            (root / approval_path).write_text(json.dumps(approval), encoding="utf-8")
            errors = approval_errors(root, {}, item["id"], 2, old_hash, new_hash, approval_path)

        self.assertTrue(any("cannot approve" in error for error in errors))

    def test_paths_are_confined_and_reports_cannot_escape_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            manifest = self.load_manifest(root)
            manifest["benchmarks"][0]["dataset"]["path"] = "../outside.json"
            self.write_manifest(root, manifest)

            report, _ = run_benchmarks(root)

            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("unsafe repository path" in error for error in report["errors"]))
            with self.assertRaisesRegex(ValueError, "output must remain"):
                safe_output_path(root, Path("../outside.json"))

            shutil.rmtree(root / "artifacts" / "tmp")
            destination = safe_output_path(root, Path("artifacts/tmp/new-report.json"))
            self.assertEqual(root / "artifacts" / "tmp" / "new-report.json", destination)
            self.assertTrue((root / "artifacts" / "tmp").is_dir())


if __name__ == "__main__":
    unittest.main()
