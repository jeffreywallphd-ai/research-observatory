from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import verification_receipt as receipt  # noqa: E402


class VerificationReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name).resolve()
        for relative in (
            *receipt.SELECTED_FILES,
            *receipt.CONFIG_FILES,
            *receipt.HELPER_FILES,
            receipt.SPEC_PATH,
            receipt.RUNNER_PATH,
        ):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO / relative).read_bytes())

    def run_real(self) -> tuple[int, dict[str, Any], Path]:
        return receipt.run_pilot(self.repo)

    def test_real_process_runs_exact_tests_in_isolation_and_retains_safe_receipt(self) -> None:
        code, result, path = self.run_real()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["execution"], "fresh")
        self.assertEqual(result["authority"], "diagnostic-evidence-only")
        self.assertEqual(result["producerTrust"], "local-producer-asserted")
        self.assertEqual(result["reuse"], {"eligible": False, "reason": "runtime-closure-incomplete"})
        self.assertEqual(result["scope"], "governance-receipt-unit")
        child = result["child"]
        self.assertIsInstance(child, dict)
        assert isinstance(child, dict)
        self.assertGreater(child["testsRun"], 0)
        self.assertEqual(child["skipped"], 0)
        self.assertEqual(child["flags"], {"isolated": 1, "noSite": 1, "noBytecode": True})
        self.assertTrue(child["snapshotDigestMatched"])
        self.assertEqual(json.loads(path.read_bytes()), result)
        self.assertEqual(receipt.read_completed_attempt(path.parent), result)
        self.assertTrue(result["requiresDelivery"])
        self.assertEqual(result["inputs"]["producerGit"], {"observed": False, "reason": "git-root-unavailable"})
        encoded = path.read_text()
        self.assertNotIn(str(self.repo), encoded)
        self.assertNotIn(str(Path(sys.executable)), encoded)
        self.assertNotIn("stdout", result)
        self.assertIsNone(result["cost"]["credits"])
        self.assertTrue((path.parent / "started.json").is_file())

    def test_repeated_run_is_fresh_and_never_overwrites_a_previous_attempt(self) -> None:
        first_code, first, first_path = self.run_real()
        first_bytes = first_path.read_bytes()
        second_code, second, second_path = self.run_real()
        self.assertEqual((first_code, second_code), (0, 0))
        self.assertNotEqual(first["attemptId"], second["attemptId"])
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_path.read_bytes(), first_bytes)
        self.assertEqual(second["execution"], "fresh")

    def test_unknown_spec_or_attempt_to_enable_reuse_is_rejected_before_execution(self) -> None:
        for key, value in (("extra", "hidden"), ("reusePolicy", "enabled"), ("scope", "W1-exit")):
            with self.subTest(key=key):
                modified = copy.deepcopy(receipt.PILOT_SPEC)
                modified[key] = value
                (self.repo / receipt.SPEC_PATH).write_text(json.dumps(modified))
                with patch.object(receipt.subprocess, "run") as child:
                    code, result, path = self.run_real()
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], "INVALID_INPUT")
                self.assertTrue(path.is_file())
                child.assert_not_called()

    def test_reuse_is_explicitly_unavailable_and_does_not_read_a_prior_receipt(self) -> None:
        with patch.object(receipt.subprocess, "run") as child:
            code, result, path = receipt.run_pilot(self.repo, reuse_requested=True)
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "REUSE_UNAVAILABLE")
        self.assertEqual(result["execution"], "not-run")
        self.assertTrue(path.is_file())
        child.assert_not_called()

    def test_escaping_and_noncanonical_paths_are_rejected(self) -> None:
        for relative in (
            "../outside.txt",
            "tools/../pyproject.toml",
            "tools\\governance_kernel.py",
            "/outside",
            "C:/outside.txt",
            "tools/governance_kernel.py:stream",
        ):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                receipt.safe_read(self.repo, relative)

    def test_runtime_identity_change_changes_fingerprint(self) -> None:
        before, _ = receipt.capture_inputs(self.repo)
        runtime = copy.deepcopy(before["runtime"])
        runtime["executableSha256"] = "1" * 64
        with patch.object(receipt, "runtime_identity", return_value=runtime):
            after, _ = receipt.capture_inputs(self.repo)
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])

    def test_git_observation_binds_only_selected_blobs_and_detects_byte_mismatch(self) -> None:
        _, captured = receipt.capture_inputs(self.repo)
        blobs = {
            hashlib.sha1(f"blob {len(value)}\0".encode() + value).hexdigest(): value for value in captured.values()
        }
        entries = {
            relative: hashlib.sha1(f"blob {len(value)}\0".encode() + value).hexdigest()
            for relative, value in captured.items()
        }
        observed_commands: list[list[str]] = []

        def fake_git(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            self.assertIn("--no-replace-objects", argv)
            command = argv[argv.index("-C") + 2 :]
            observed_commands.append(command)
            if command == ["rev-parse", "--show-toplevel"]:
                output = str(self.repo).encode()
            elif command == ["rev-parse", "--verify", "HEAD^{commit}"]:
                output = b"a" * 40
            elif command == ["symbolic-ref", "--quiet", "HEAD"]:
                output = b"refs/heads/codex/synthetic-receipt"
            elif command[:2] == ["ls-tree", "-z"]:
                self.assertEqual(command[4:], list(captured))
                output = b"".join(f"100644 blob {oid}\t{path}\0".encode() for path, oid in entries.items())
            elif command[:2] == ["cat-file", "blob"]:
                output = blobs[command[2]]
            else:
                self.fail(f"unexpected Git command: {command[0]}")
            return subprocess.CompletedProcess(argv, 0, output, b"")

        with patch.object(receipt, "GIT_RUN", side_effect=fake_git):
            first = receipt.git_binding(self.repo, captured)
            changed = {**captured, receipt.SELECTED_FILES[0]: b"changed selected bytes"}
            second = receipt.git_binding(self.repo, changed)
        self.assertTrue(first["observed"])
        self.assertEqual(first["head"], "a" * 40)
        self.assertEqual(first["branch"], "refs/heads/codex/synthetic-receipt")
        self.assertTrue(first["allSelectedRawBytesMatchCommit"])
        self.assertFalse(second["allSelectedRawBytesMatchCommit"])
        self.assertTrue(observed_commands)

    def test_observed_git_identity_changes_fingerprint(self) -> None:
        before, _ = receipt.capture_inputs(self.repo)
        with patch.object(receipt, "git_binding", return_value={"observed": True, "head": "b" * 40}):
            after, _ = receipt.capture_inputs(self.repo)
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])

    def test_missing_input_is_an_adverse_attempt_not_an_old_pass(self) -> None:
        code, _, first_path = self.run_real()
        self.assertEqual(code, 0)
        preserved = first_path.read_bytes()
        (self.repo / receipt.SELECTED_FILES[0]).unlink()
        code, result, path = self.run_real()
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "INVALID_INPUT")
        self.assertNotEqual(path, first_path)
        self.assertEqual(first_path.read_bytes(), preserved)

    def test_input_config_and_spec_bytes_are_in_fingerprint(self) -> None:
        before, _ = receipt.capture_inputs(self.repo)
        for relative in (
            *receipt.SELECTED_FILES,
            *receipt.CONFIG_FILES,
            *receipt.HELPER_FILES,
            receipt.SPEC_PATH,
            receipt.RUNNER_PATH,
        ):
            original = (self.repo / relative).read_bytes()
            with self.subTest(relative=relative):
                (self.repo / relative).write_bytes(original + b"\n")
                after, _ = receipt.capture_inputs(self.repo)
                self.assertNotEqual(before["fingerprint"], after["fingerprint"])
                (self.repo / relative).write_bytes(original)

    def test_worker_uses_captured_source_even_if_live_selected_file_is_changed(self) -> None:
        original_run = subprocess.run

        def mutate_then_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            (self.repo / receipt.SELECTED_FILES[0]).write_text("raise RuntimeError('must not execute live bytes')\n")
            return original_run(*args, **kwargs)

        with patch.object(receipt.subprocess, "run", side_effect=mutate_then_run):
            code, result, _ = self.run_real()
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "INPUT_DRIFT")
        self.assertTrue(result["child"]["successful"])

    def test_ambient_python_configuration_and_credentials_are_not_forwarded(self) -> None:
        original_run = subprocess.run
        observed: dict[str, Any] = {}

        def inspect_then_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            observed.update(kwargs)
            return original_run(*args, **kwargs)

        with (
            patch.dict("os.environ", {"PYTHONPATH": "forbidden", "PRIVATE_TOKEN": "do-not-forward"}),
            patch.object(receipt.subprocess, "run", side_effect=inspect_then_run),
        ):
            code, result, _ = self.run_real()
        self.assertEqual(code, 0, result)
        self.assertNotIn("PYTHONPATH", observed["env"])
        self.assertNotIn("PRIVATE_TOKEN", observed["env"])
        self.assertIn("-I", observed.get("args", []) or result["inputs"]["argv"])

    def test_timeout_spawn_failure_and_cancellation_preserve_attempts(self) -> None:
        errors = (
            (subprocess.TimeoutExpired("synthetic", 1), "TIMEOUT"),
            (OSError("private account path must not be copied"), "SPAWN_FAILED"),
            (KeyboardInterrupt(), "CANCELLED"),
        )
        for error, expected in errors:
            with self.subTest(expected=expected), patch.object(receipt.subprocess, "run", side_effect=error):
                code, result, path = self.run_real()
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], expected)
                self.assertTrue(path.is_file())
                self.assertNotIn("private account", path.read_text())

    def test_malformed_child_output_is_not_pass_and_raw_output_stays_private(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b"private/path/secret", b"hidden detail")
        with patch.object(receipt.subprocess, "run", return_value=completed):
            code, result, path = self.run_real()
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "INVALID_CHILD_RESULT")
        self.assertEqual(result["outputDigests"]["stdoutSha256"], hashlib.sha256(completed.stdout).hexdigest())
        self.assertNotIn("private/path", path.read_text())

    def test_zero_skipped_and_unexpected_success_results_are_nonqualifying(self) -> None:
        for test_source in (
            "import unittest\n",
            "import unittest\nclass T(unittest.TestCase):\n @unittest.skip('synthetic')\n def test_x(self): pass\n",
            "import unittest\nclass T(unittest.TestCase):\n @unittest.expectedFailure\n def test_x(self): pass\n",
            "import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.fail('synthetic')\n",
        ):
            with self.subTest(source=test_source):
                (self.repo / receipt.TEST_FILE).write_text(test_source)
                code, result, _ = self.run_real()
                self.assertNotEqual(code, 0)
                self.assertEqual(result["status"], "FAIL")

    def test_publisher_refuses_existing_destination_and_retains_original_bytes(self) -> None:
        destination = self.repo / "result.json"
        destination.write_bytes(b"retained")
        with self.assertRaises(FileExistsError):
            receipt.publish_json(destination, {"status": "PASS"})
        self.assertEqual(destination.read_bytes(), b"retained")

    def test_publication_failure_leaves_started_not_stale_pass(self) -> None:
        original_publish = receipt.publish_json

        def publish_without_result(path: Path, value: dict[str, Any], **kwargs: Any) -> None:
            if path.name == "receipt.json":
                raise OSError("synthetic publication failure")
            original_publish(path, value, **kwargs)

        with patch.object(receipt, "publish_json", side_effect=publish_without_result):
            code, result, path = self.run_real()
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "PUBLICATION_FAILED")
        self.assertFalse(path.exists())
        self.assertTrue((path.parent / "started.json").exists())

    def test_receipt_without_matching_delivery_is_not_a_complete_attempt(self) -> None:
        original_publish = receipt.publish_json

        def publish_without_delivery(path: Path, value: dict[str, Any], **kwargs: Any) -> None:
            if path.name == "delivery.json":
                raise OSError("synthetic late publication failure")
            original_publish(path, value, **kwargs)

        with patch.object(receipt, "publish_json", side_effect=publish_without_delivery):
            code, result, path = self.run_real()
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "PUBLICATION_FAILED")
        self.assertTrue(json.loads(path.read_bytes())["requiresDelivery"])
        with self.assertRaises((OSError, ValueError)):
            receipt.read_completed_attempt(path.parent)

    def test_delivery_digest_substitution_is_rejected(self) -> None:
        code, _, path = self.run_real()
        self.assertEqual(code, 0)
        delivery_path = path.parent / "delivery.json"
        delivery = json.loads(delivery_path.read_bytes())
        delivery["receiptSha256"] = "0" * 64
        delivery_path.write_text(json.dumps(delivery))
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            receipt.read_completed_attempt(path.parent)

    @unittest.skipUnless(sys.platform == "win32", "Windows publication-handle boundary")
    def test_actual_windows_parent_cannot_be_renamed_during_publication(self) -> None:
        parent = self.repo / "publish-hold"
        parent.mkdir()
        actual_link = receipt.os.link
        denied: list[bool] = []

        def link_while_trying_rename(source: Path, destination: Path) -> None:
            try:
                parent.rename(self.repo / "unexpected-move")
            except PermissionError:
                denied.append(True)
            actual_link(source, destination)

        with patch.object(receipt.os, "link", side_effect=link_while_trying_rename):
            receipt.publish_json(parent / "result.json", {"status": "synthetic"})
        self.assertEqual(denied, [True])

    def test_receipt_records_measured_timings_without_invented_cost_or_savings(self) -> None:
        code, result, _ = self.run_real()
        self.assertEqual(code, 0, result)
        self.assertGreater(result["timing"]["childSeconds"], 0)
        self.assertGreaterEqual(result["timing"]["totalBeforePublicationSeconds"], result["timing"]["childSeconds"])
        self.assertEqual(result["cost"], {"credits": None, "money": None, "tokenUsage": None, "source": "unavailable"})
        self.assertNotIn("savedSeconds", result)


if __name__ == "__main__":
    unittest.main()
