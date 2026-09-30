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
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import benchmark_registry  # noqa: E402
from benchmark_registry import (  # noqa: E402
    REGISTRY_PATH,
    approval_errors,
    baseline_lineage_errors,
    git_history_errors,
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

    def initialize_git(self, root: Path) -> None:
        for command in (
            ["git", "init"],
            ["git", "config", "user.email", "foundation@example.invalid"],
            ["git", "config", "user.name", "Foundation Test"],
            ["git", "config", "core.autocrlf", "false"],
        ):
            subprocess.run(command, cwd=root, capture_output=True, check=True)
        self.commit_all(root, "initial benchmark registry")

    def commit_all(self, root: Path, message: str) -> None:
        subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=root, capture_output=True, check=True)

    def add_unrelated_followup(self, root: Path) -> None:
        marker = root / "unrelated.txt"
        marker.write_text(marker.read_text(encoding="utf-8") + "x\n" if marker.exists() else "x\n", encoding="utf-8")
        self.commit_all(root, "unrelated follow-up")

    def establish_version_two(self, root: Path) -> tuple[dict[str, Any], str]:
        manifest = self.load_manifest(root)
        item = manifest["benchmarks"][0]
        baseline_path = root / item["expected"]["path"]
        value = json.loads(baseline_path.read_text(encoding="utf-8"))
        value["baselineNote"] = "approved intentional change"
        baseline_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        old_hash = item["expected"]["sha256"]
        new_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
        approval_path = "evaluation/approvals/golden-v2.json"
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
            "currentApprovalSha256": hashlib.sha256(approval_payload).hexdigest(),
        }
        self.write_manifest(root, manifest)
        self.commit_all(root, "approved version two baseline")
        _, _, errors = load_registry(root)
        self.assertEqual([], errors)
        return manifest, approval_path

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
            self.initialize_git(root)
            approval.write_text('{"approvedBy":"human:rewriter"}\n', encoding="utf-8")

            dirty_errors = git_history_errors(root, {})

            self.commit_all(root, "rewrite approval")
            self.add_unrelated_followup(root)
            committed_errors = git_history_errors(root, {})

        self.assertTrue(any("rewritten or removed" in error for error in dirty_errors))
        self.assertTrue(any("rewritten or removed" in error for error in committed_errors))

    def test_approval_rewrite_and_repin_cannot_be_laundered_by_followup_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            manifest, approval_path = self.establish_version_two(root)
            approval = json.loads((root / approval_path).read_text(encoding="utf-8"))
            approval["rationale"] = "Rewritten after approval."
            payload = json.dumps(approval).encode()
            (root / approval_path).write_bytes(payload)
            manifest["benchmarks"][0]["baseline"]["currentApprovalSha256"] = hashlib.sha256(payload).hexdigest()
            self.write_manifest(root, manifest)
            self.commit_all(root, "rewrite and repin approval")
            self.add_unrelated_followup(root)

            _, _, errors = load_registry(root)

        self.assertTrue(any("immutable baseline approval record" in error for error in errors))
        self.assertTrue(any("baseline lineage changed without expected-output change" in error for error in errors))

    def test_approval_removal_cannot_be_laundered_by_followup_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            _, approval_path = self.establish_version_two(root)
            (root / approval_path).unlink()
            self.commit_all(root, "remove approval")
            self.add_unrelated_followup(root)

            _, _, errors = load_registry(root)

        self.assertTrue(any("immutable baseline approval record" in error for error in errors))

    def test_baseline_history_rewrite_cannot_be_laundered_by_followup_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            manifest, approval_path = self.establish_version_two(root)
            item = manifest["benchmarks"][0]
            forged_old_hash = "3" * 64
            item["baseline"]["history"][0]["sha256"] = forged_old_hash
            approval = json.loads((root / approval_path).read_text(encoding="utf-8"))
            approval["oldSha256"] = forged_old_hash
            forged_approval_path = "evaluation/approvals/forged-history-v2.json"
            payload = json.dumps(approval).encode()
            (root / forged_approval_path).write_bytes(payload)
            item["baseline"]["currentApproval"] = forged_approval_path
            item["baseline"]["currentApprovalSha256"] = hashlib.sha256(payload).hexdigest()
            self.write_manifest(root, manifest)
            self.commit_all(root, "rewrite baseline history")
            self.add_unrelated_followup(root)

            _, _, errors = load_registry(root)

        self.assertTrue(any("baseline lineage changed without expected-output change" in error for error in errors))

    def test_same_identity_prompt_mutation_cannot_be_laundered_by_followup_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            manifest = self.load_manifest(root)
            prompt_path = "evaluation/prompts/real-prompt-v1.txt"
            first_payload = b"First governed prompt.\n"
            (root / prompt_path).write_bytes(first_payload)
            manifest["benchmarks"][0]["prompt"] = {
                "id": "real-prompt",
                "version": "v1",
                "path": prompt_path,
                "sha256": hashlib.sha256(first_payload).hexdigest(),
            }
            self.write_manifest(root, manifest)
            self.commit_all(root, "add versioned prompt")
            _, _, initial_errors = load_registry(root)
            self.assertEqual([], initial_errors)

            second_payload = b"Mutated without a new identity.\n"
            (root / prompt_path).write_bytes(second_payload)
            manifest["benchmarks"][0]["prompt"]["sha256"] = hashlib.sha256(second_payload).hexdigest()
            self.write_manifest(root, manifest)
            self.commit_all(root, "mutate prompt without version")
            self.add_unrelated_followup(root)

            _, _, errors = load_registry(root)

        self.assertTrue(
            any("prompt content or path changed without a new prompt identity" in error for error in errors)
        )

    def test_git_inspection_failure_is_closed_in_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").write_text("gitdir: unavailable\n", encoding="utf-8")
            with patch("benchmark_registry.run_git", return_value=None):
                errors = git_history_errors(root, {})

        self.assertEqual(["cannot inspect governed Git history in this checkout"], errors)

    def test_complete_history_enumeration_failure_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            self.add_unrelated_followup(root)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, check=True
            ).stdout.strip()
            git = benchmark_registry.run_git
            for payload in (None, b"", head + b"\n", head + b" " + b"1" * 40 + b"\n", head + b"\n" + head + b"\n"):
                with self.subTest(payload=payload):

                    def fail_enumeration(repo: Path, arguments: list[str], payload: bytes | None = payload) -> Any:
                        if arguments[0] == "rev-list":
                            return None if payload is None else subprocess.CompletedProcess(arguments, 0, payload, b"")
                        return git(repo, arguments)

                    with patch("benchmark_registry.run_git", side_effect=fail_enumeration):
                        errors = git_history_errors(root, self.load_manifest(root))

                    self.assertEqual(["cannot enumerate complete reachable benchmark history"], errors)

    def test_repeated_history_objects_are_read_once_without_skipping_commit_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            for _ in range(3):
                self.add_unrelated_followup(root)
            git = benchmark_registry.run_git
            blob_reads: list[str] = []

            def observe(repo: Path, arguments: list[str]) -> Any:
                result = git(repo, arguments)
                if arguments[0] in {"show", "cat-file"} and result is not None and result.returncode == 0:
                    blob_reads.append(hashlib.sha256(result.stdout).hexdigest())
                return result

            with (
                patch("benchmark_registry.run_git", side_effect=observe),
                patch(
                    "benchmark_registry.historical_asset_errors", wraps=benchmark_registry.historical_asset_errors
                ) as assets,
                patch(
                    "benchmark_registry.historical_registry_schema_errors",
                    wraps=benchmark_registry.historical_registry_schema_errors,
                ) as schemas,
            ):
                errors = git_history_errors(root, self.load_manifest(root))

            self.assertEqual([], errors)
            self.assertEqual(4, assets.call_count)
            self.assertEqual(4, schemas.call_count)
            self.assertTrue(blob_reads)
            self.assertEqual(len(set(blob_reads)), len(blob_reads), "unchanged immutable blobs need only one read")

    def test_unchanged_registry_cannot_hide_repaired_historical_asset_or_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            manifest = self.load_manifest(root)
            dataset = root / manifest["benchmarks"][0]["dataset"]["path"]
            original = dataset.read_bytes()
            dataset.write_bytes(original + b"tampered")
            self.commit_all(root, "change asset without registry change")
            dataset.write_bytes(original)
            self.commit_all(root, "restore asset")
            schema_path = root / "evaluation/registry.schema.json"
            schema_bytes = schema_path.read_bytes()
            schema = json.loads(schema_bytes)
            schema["properties"]["registryVersion"] = {"const": "invalid-for-this-registry"}
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            self.commit_all(root, "change only contemporaneous schema")
            schema_path.write_bytes(schema_bytes)
            self.commit_all(root, "restore schema")

            errors = git_history_errors(root, manifest)

            self.assertTrue(any("governed registry asset SHA-256 mismatch" in error for error in errors))
            self.assertTrue(any("registry.registryVersion" in error for error in errors))

    def test_historical_object_read_failure_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            git = benchmark_registry.run_git
            for failing_command in ("ls-tree", "cat-file"):
                with self.subTest(command=failing_command):

                    def fail_read(repo: Path, arguments: list[str], command: str = failing_command) -> Any:
                        if arguments[0] == command:
                            return None
                        return git(repo, arguments)

                    with patch("benchmark_registry.run_git", side_effect=fail_read) as observed:
                        errors = git_history_errors(root, self.load_manifest(root))
                    self.assertTrue(any(call.args[1][0] == failing_command for call in observed.call_args_list))
                    self.assertTrue(errors, "a failed tree/blob read must not become missing history")

    def test_history_cache_preserves_literal_and_noncanonical_path_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            manifest = self.load_manifest(root)
            specification = manifest["benchmarks"][0]["dataset"]
            original = root / specification["path"]
            literal_path = "evaluation/cases/réview %23 #&.json"
            (root / literal_path).write_bytes(original.read_bytes())
            specification["path"] = literal_path
            self.write_manifest(root, manifest)
            self.initialize_git(root)
            self.assertEqual([], git_history_errors(root, manifest))

            specification["path"] = literal_path.replace("/cases/", "//cases/")
            self.write_manifest(root, manifest)
            self.commit_all(root, "record an invalid noncanonical Git path")
            errors = git_history_errors(root, manifest)

            self.assertTrue(any("cannot read Git blob" in error for error in errors))

    def test_rewrite_revert_branch_hidden_by_treesame_merge_remains_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            approval_root = root / "evaluation" / "approvals"
            approval_root.mkdir(parents=True)
            approval = approval_root / "immutable.json"
            original = b'{"approvedBy":"human:owner"}\n'
            approval.write_bytes(original)
            self.initialize_git(root)
            main_branch = subprocess.run(
                ["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True, check=True
            ).stdout.strip()
            subprocess.run(["git", "switch", "-c", "rewrite-side"], cwd=root, capture_output=True, check=True)
            approval.write_bytes(b'{"approvedBy":"human:rewriter"}\n')
            self.commit_all(root, "rewrite approval on side branch")
            approval.write_bytes(original)
            self.commit_all(root, "revert approval on side branch")
            subprocess.run(["git", "switch", main_branch], cwd=root, capture_output=True, check=True)
            self.add_unrelated_followup(root)
            subprocess.run(
                ["git", "merge", "--no-ff", "rewrite-side", "-m", "merge reverted side branch"],
                cwd=root,
                capture_output=True,
                check=True,
            )

            with patch("benchmark_registry.run_git", wraps=benchmark_registry.run_git) as observed_git:
                errors = git_history_errors(root, {})

            enumeration = [call.args[1] for call in observed_git.call_args_list if call.args[1][0] == "rev-list"]
            self.assertEqual(1, len(enumeration), "parent discovery must not spawn a process for every commit")
            self.assertIn("--parents", enumeration[0])
            self.assertNotIn("--", enumeration[0], "path simplification can hide a reverted side branch")

        self.assertTrue(any("immutable baseline approval record" in error for error in errors))
        self.assertTrue(any("multiple reachable blob identities" in error for error in errors))

    def test_divergent_same_approval_path_blobs_reject_merge_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            approval_root = root / "evaluation" / "approvals"
            approval_root.mkdir(parents=True)
            (approval_root / "README.md").write_text("approvals\n", encoding="utf-8")
            self.initialize_git(root)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
            ).stdout.strip()
            approval = approval_root / "shared-v2.json"
            subprocess.run(["git", "switch", "-c", "approval-a"], cwd=root, capture_output=True, check=True)
            first = b'{"approvedBy":"human:owner-a"}\n'
            approval.write_bytes(first)
            self.commit_all(root, "add approval identity A")
            subprocess.run(["git", "switch", "-c", "approval-b", base], cwd=root, capture_output=True, check=True)
            approval.write_bytes(b'{"approvedBy":"human:owner-b"}\n')
            self.commit_all(root, "add approval identity B")
            subprocess.run(["git", "switch", "approval-a"], cwd=root, capture_output=True, check=True)
            merge = subprocess.run(
                ["git", "merge", "--no-ff", "approval-b", "-m", "merge divergent approvals"],
                cwd=root,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, merge.returncode)
            approval.write_bytes(first)
            self.commit_all(root, "resolve approval to identity A")

            errors = git_history_errors(root, {})

        self.assertTrue(any("multiple reachable blob identities" in error for error in errors))
        self.assertTrue(any("immutable baseline approval record" in error for error in errors))

    def test_repaired_historical_schema_violation_remains_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.temporary_repo(temporary)
            self.initialize_git(root)
            canonical = self.load_manifest(root)
            invalid = copy.deepcopy(canonical)
            invalid["unexpectedHistoricalField"] = True
            self.write_manifest(root, invalid)
            self.commit_all(root, "commit schema-invalid registry")
            self.write_manifest(root, canonical)
            self.commit_all(root, "repair schema-invalid registry")

            _, _, errors = load_registry(root)

        self.assertTrue(any("unexpectedHistoricalField" in error for error in errors))

    def test_repaired_malformed_historical_shapes_report_without_crashing(self) -> None:
        shapes = ("benchmarks", "schemas", "history", "prompt", "expected")
        for shape in shapes:
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                root = self.temporary_repo(temporary)
                self.initialize_git(root)
                canonical = self.load_manifest(root)
                invalid = copy.deepcopy(canonical)
                item = invalid["benchmarks"][0]
                if shape == "benchmarks":
                    invalid["benchmarks"] = None
                elif shape == "schemas":
                    item["schemas"] = None
                elif shape == "history":
                    item["baseline"]["history"] = None
                else:
                    item[shape] = None
                self.write_manifest(root, invalid)
                self.commit_all(root, f"commit malformed {shape} registry")
                self.write_manifest(root, canonical)
                self.commit_all(root, f"repair malformed {shape} registry")

                _, _, errors = load_registry(root)

                self.assertTrue(errors)
                self.assertTrue(any("registry." in error for error in errors))

    def test_shallow_checkout_denies_durable_history_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = self.temporary_repo(str(Path(temporary) / "source"))
            self.initialize_git(source)
            (source / "unrelated.txt").write_text("follow-up\n", encoding="utf-8")
            self.commit_all(source, "follow-up")
            clone = Path(temporary) / "shallow"
            subprocess.run(
                ["git", "clone", "--depth", "1", "--no-local", str(source), str(clone)],
                capture_output=True,
                check=True,
            )

            _, _, errors = load_registry(clone)

        self.assertTrue(any("complete, non-shallow Git checkout" in error for error in errors))

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
