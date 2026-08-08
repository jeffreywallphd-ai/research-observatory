from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
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
    approval_immutability_errors,
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
            "expectedPath": item["expected"]["path"],
            "sha256": new_hash,
            "history": [
                {
                    "version": 1,
                    "expectedPath": item["expected"]["path"],
                    "sha256": old_hash,
                    "approval": None,
                    "approvalSha256": None,
                }
            ],
            "currentApproval": "evaluation/approvals/golden-v2.json",
            "currentApprovalSha256": "2" * 64,
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
                "expectedPath": item["expected"]["path"],
                "sha256": new_hash,
                "history": [
                    {
                        "version": 1,
                        "expectedPath": item["expected"]["path"],
                        "sha256": old_hash,
                        "approval": None,
                        "approvalSha256": None,
                    }
                ],
                "currentApproval": approval_path,
                "currentApprovalSha256": None,
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
            approval_payload = json.dumps(approval).encode()
            (root / approval_path).write_bytes(approval_payload)
            approval_hash = hashlib.sha256(approval_payload).hexdigest()
            item["baseline"]["currentApprovalSha256"] = approval_hash
            self.write_manifest(root, manifest)

            _, _, errors = load_registry(root)

            self.assertEqual([], errors)
            approval["generatedBy"] = "human:benchmark-owner"
            changed_payload = json.dumps(approval).encode()
            (root / approval_path).write_bytes(changed_payload)
            errors = approval_errors(
                root,
                {},
                item["id"],
                2,
                old_hash,
                new_hash,
                approval_path,
                hashlib.sha256(changed_payload).hexdigest(),
            )

        self.assertTrue(any("cannot approve" in error for error in errors))

    def test_approval_contract_rejects_extras_boolean_versions_and_blank_human(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            benchmark = self.load_manifest(root)["benchmarks"][0]
            approval_path = "evaluation/approvals/strictness.json"
            approval = {
                "schemaVersion": "1.0",
                "documentType": "baseline-approval",
                "status": "approved",
                "benchmarkId": benchmark["id"],
                "fromVersion": 1,
                "toVersion": 2,
                "oldSha256": benchmark["expected"]["sha256"],
                "newSha256": "1" * 64,
                "generatedBy": "codex",
                "approvedBy": "human:benchmark-owner",
                "approvedAt": "2026-08-08T16:00:00+00:00",
                "rationale": "Reviewed semantic improvement.",
            }
            for key, value in (
                ("unreviewedOverride", True),
                ("fromVersion", True),
                ("approvedBy", "human:"),
            ):
                mutated = copy.deepcopy(approval)
                mutated[key] = value
                payload = json.dumps(mutated).encode()
                (root / approval_path).write_bytes(payload)

                errors = approval_errors(
                    root,
                    {},
                    benchmark["id"],
                    2,
                    benchmark["expected"]["sha256"],
                    "1" * 64,
                    approval_path,
                    hashlib.sha256(payload).hexdigest(),
                )

                self.assertTrue(errors, key)

    def test_expected_output_is_canonical_and_path_is_lineage_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            manifest = self.load_manifest(root)
            item = manifest["benchmarks"][0]
            previous = copy.deepcopy(manifest)
            redirected = "evaluation/cases/contract-normalized-record.json"
            item["expected"]["path"] = redirected
            item["expected"]["sha256"] = hashlib.sha256((root / redirected).read_bytes()).hexdigest()
            item["baseline"]["sha256"] = item["expected"]["sha256"]
            self.write_manifest(root, manifest)

            _, _, errors = load_registry(root)
            lineage_errors = baseline_lineage_errors(manifest, previous)

        self.assertTrue(any("expected output must use canonical path" in error for error in errors))
        self.assertTrue(any("increment exactly one version" in error for error in lineage_errors))

    def test_real_prompt_requires_canonical_path_and_exact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            manifest = self.load_manifest(root)
            prompt = manifest["benchmarks"][0]["prompt"]
            prompt.update({"id": "real-prompt", "version": "v1", "path": None, "sha256": None})
            self.write_manifest(root, manifest)

            _, _, missing_errors = load_registry(root)

            prompt_path = "evaluation/prompts/real-prompt-v1.txt"
            payload = b"Normalize the supplied metadata deterministically.\n"
            (root / prompt_path).write_bytes(payload)
            prompt.update({"path": prompt_path, "sha256": hashlib.sha256(payload).hexdigest()})
            self.write_manifest(root, manifest)

            _, _, valid_errors = load_registry(root)

        self.assertTrue(missing_errors)
        self.assertEqual([], valid_errors)

    def test_prompt_hash_change_requires_new_identity(self) -> None:
        previous = self.load_manifest(REPO)
        previous["benchmarks"][0]["prompt"] = {
            "id": "real-prompt",
            "version": "v1",
            "path": "evaluation/prompts/real-prompt-v1.txt",
            "sha256": "1" * 64,
        }
        current = copy.deepcopy(previous)
        current["benchmarks"][0]["prompt"]["sha256"] = "2" * 64

        errors = baseline_lineage_errors(current, previous)

        self.assertTrue(any("without a new prompt identity" in error for error in errors))

    def test_tracked_approval_records_reject_dirty_and_committed_rewrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            approval_root = root / "evaluation" / "approvals"
            approval_root.mkdir(parents=True)
            approval = approval_root / "immutable.json"
            approval.write_text('{"approvedBy":"human:owner"}\n', encoding="utf-8")
            commands = [
                ["git", "init"],
                ["git", "config", "user.email", "foundation@example.invalid"],
                ["git", "config", "user.name", "Foundation Test"],
                ["git", "add", "."],
                ["git", "commit", "-m", "initial approval"],
            ]
            for command in commands:
                subprocess.run(command, cwd=root, capture_output=True, check=True)
            approval.write_text('{"approvedBy":"human:rewriter"}\n', encoding="utf-8")

            dirty_errors = approval_immutability_errors(root)

            subprocess.run(["git", "add", "."], cwd=root, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "rewrite approval"], cwd=root, capture_output=True, check=True)
            committed_errors = approval_immutability_errors(root)

        self.assertTrue(any("rewritten or removed" in error for error in dirty_errors))
        self.assertTrue(any("rewritten or removed" in error for error in committed_errors))

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
