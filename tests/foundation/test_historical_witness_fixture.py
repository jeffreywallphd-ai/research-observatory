from __future__ import annotations

import copy
import hashlib
import importlib
import inspect
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import gcr2ctl  # noqa: E402
import recoveryctl  # noqa: E402
import taskctl  # noqa: E402
from historical_witness_fixture import (  # noqa: E402
    BOOTSTRAP_VALIDATORS,
    HISTORICAL_BOOTSTRAP_CANDIDATE,
    HISTORICAL_SHA256,
    SYNTHETIC_SHA256,
    SYNTHETIC_WITNESS,
    VALIDATORS,
    WITNESS_PATH,
    FixtureWitnesses,
    adapted_bootstrap_validator,
    adapted_validator,
    bootstrap_fixture_digest,
    checkout_historical_repository,
    historical_bytes,
    init_shared_repository,
)


class HistoricalWitnessFixtureTests(unittest.TestCase):
    def bootstrap_repo(self, revision: str = "f6f0f640e9acd0da74a1ff73afe85f09db797a8e") -> Path:
        repo = Path(self.enterContext(tempfile.TemporaryDirectory()))
        checkout_historical_repository(repo, REPO, revision, gcr2ctl.BRANCH)
        return repo

    @staticmethod
    def target_descriptor() -> dict:
        return {
            "id": "W1.A04.B00",
            "candidateCommit": HISTORICAL_BOOTSTRAP_CANDIDATE,
            "evidence": {"path": WITNESS_PATH, "sha256": HISTORICAL_SHA256, "commit": HISTORICAL_BOOTSTRAP_CANDIDATE},
        }

    def test_bootstrap_adapter_keeps_frozen_packets_and_denies_changed_bytes_and_metadata(self) -> None:
        repo = self.bootstrap_repo()
        data = taskctl.historical_backlog_document(repo, self.git(repo, "rev-parse", "HEAD"))
        assert data is not None
        hold = next(
            item for item in data["control_plane"]["recovery_holds"] if item["recovery_request_id"] == "GRR-0002"
        )
        supplements = [item for item in hold["supplements"] if item["id"] in {"GRR-0002.S01", "GRR-0002.S02"}]
        self.assertEqual(2, len(supplements))
        with FixtureWitnesses(REPO) as adapter:
            witness = adapter.write(repo)
            for supplement in supplements:
                errors, _packet = taskctl.recovery_supplement_authority_errors(data, repo, hold, supplement)
                self.assertEqual([], errors)
            changed_id = json.loads(SYNTHETIC_WITNESS)
            changed_id["taskId"] = "W1.A99.B00"
            changed_commit = json.loads(SYNTHETIC_WITNESS)
            changed_commit["commit"] = "0" * 40
            for payload in (
                SYNTHETIC_WITNESS + b" ",
                b"not json",
                json.dumps(changed_id).encode(),
                json.dumps(changed_commit).encode(),
            ):
                witness.write_bytes(payload)
                errors, _packet = taskctl.recovery_supplement_authority_errors(data, repo, hold, supplements[-1])
                self.assertTrue(any("target bootstrap" in item for item in errors))
            witness.unlink()
            errors, _packet = taskctl.recovery_supplement_authority_errors(data, repo, hold, supplements[-1])
            self.assertTrue(any("cannot load target bootstrap" in item for item in errors))

    def test_preappend_adapter_preserves_the_exact_boundary_and_byte_tamper_denial(self) -> None:
        packet = json.loads((REPO / "planning/governance-recovery-requests/GRR-0002.S02.packet.json").read_bytes())
        revision = packet["triggerEvidence"]["discoveryCommit"]
        repo = self.bootstrap_repo(revision)
        (repo / "planning/backlog.yaml").write_bytes(
            historical_bytes(REPO, revision, "planning/backlog.yaml", packet["triggerEvidence"]["backlogSha256"])
        )
        _payload, data, _caps, _slices, tasks, _gates = recoveryctl.backlog_state(repo)
        hold = recoveryctl.recovery_hold(data, "GRR-0002")
        kwargs = {
            "hold": hold,
            "wave": taskctl.wave_map(data)["W1"],
            "blocked_task": tasks["CAP-02.S04.T03"],
            "installed": [],
            "require_installed": False,
        }
        with FixtureWitnesses(REPO) as adapter:
            witness = adapter.write(repo)
            recoveryctl.validate_preappend_supplement_boundary(repo, packet, data, **kwargs)
            witness.write_bytes(SYNTHETIC_WITNESS + b" ")
            with self.assertRaisesRegex(SystemExit, "evidence identity/hash mismatch"):
                recoveryctl.validate_preappend_supplement_boundary(repo, packet, data, **kwargs)

    def test_bootstrap_digest_selector_is_exact_and_leaves_other_paths_unadapted(self) -> None:
        target = self.target_descriptor()
        args = ("GRR-0002", "W1", "GRR-0002.S02", "GRR-0002.B02")
        self.assertEqual(SYNTHETIC_SHA256, bootstrap_fixture_digest(target, *args))
        for field in ("id", "candidateCommit"):
            changed = copy.deepcopy(target)
            changed[field] = "wrong"
            with self.assertRaisesRegex(AssertionError, "exact historical"):
                bootstrap_fixture_digest(changed, *args)
        for field in ("sha256", "commit"):
            changed = copy.deepcopy(target)
            changed["evidence"][field] = "wrong"
            with self.assertRaisesRegex(AssertionError, "exact historical"):
                bootstrap_fixture_digest(changed, *args)
        for changed_args in (
            ("GRR-0001", *args[1:]),
            (args[0], "W2", *args[2:]),
            (args[0], args[1], "GRR-0002.S03", "GRR-0002.B03"),
        ):
            with self.assertRaisesRegex(AssertionError, "exact historical"):
                bootstrap_fixture_digest(target, *changed_args)
        other = copy.deepcopy(target)
        other["evidence"].update(path="artifacts/evidence/fixture.json", sha256=hashlib.sha256(b"fixture").hexdigest())
        self.assertEqual(hashlib.sha256(b"fixture").hexdigest(), bootstrap_fixture_digest(other, *args))
        self.assertNotEqual(hashlib.sha256(b"tampered").hexdigest(), bootstrap_fixture_digest(other, *args))

    def test_bootstrap_adapters_reject_unregistered_roots_and_restore_after_errors(self) -> None:
        originals = {
            (module, name): getattr(importlib.import_module(module), name) for module, name in BOOTSTRAP_VALIDATORS
        }
        with (
            self.assertRaisesRegex(RuntimeError, "fixture exit"),
            FixtureWitnesses(REPO),
            patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected read")),
        ):
            with self.assertRaisesRegex(AssertionError, "registered temporary root"):
                taskctl.recovery_supplement_authority_errors({}, REPO, {}, {})
            with self.assertRaisesRegex(AssertionError, "registered temporary root"):
                recoveryctl.validate_preappend_supplement_boundary(
                    REPO, {}, {}, hold={}, wave={}, blocked_task={}, installed=[], require_installed=False
                )
            raise RuntimeError("fixture exit")
        for (module, name), original in originals.items():
            self.assertIs(original, getattr(importlib.import_module(module), name))

    def test_bootstrap_adapter_rejects_missing_or_duplicate_comparison(self) -> None:
        original = taskctl.recovery_supplement_authority_errors
        assert isinstance(original, types.FunctionType)
        source = inspect.getsource(original)
        comparison = 'hashlib.sha256(evidence_payload).hexdigest() != evidence.get("sha256")'
        for changed in (
            source.replace(comparison, "False"),
            source.replace(comparison, f"({comparison}) or ({comparison})"),
        ):
            with (
                patch("inspect.getsource", return_value=changed),
                self.assertRaisesRegex(AssertionError, "changed or is ambiguous"),
            ):
                adapted_bootstrap_validator(original)

    def git(self, repo: Path, *args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=repo, text=True, stderr=subprocess.STDOUT).strip()

    def fixture(self, directory: str) -> Path:
        repo = Path(directory)
        self.git(repo, "init", "-b", gcr2ctl.BRANCH)
        self.git(repo, "config", "user.name", "Synthetic Fixture")
        self.git(repo, "config", "user.email", "fixture@example.invalid")
        self.git(repo, "config", "core.autocrlf", "false")
        (repo / "sentinel.txt").write_bytes(b"fixture\n")
        self.git(repo, "add", "sentinel.txt")
        self.git(repo, "commit", "-m", "synthetic fixture")
        return repo

    def test_exact_operand_clones_leave_original_constants_and_functions_unchanged(self) -> None:
        def semantic_constant(value: object) -> object:
            if isinstance(value, types.CodeType):
                return (
                    value.co_code,
                    value.co_names,
                    value.co_varnames,
                    tuple(semantic_constant(item) for item in value.co_consts),
                )
            return value

        originals = {}
        for module_name, name, variable, constant in VALIDATORS:
            module = importlib.import_module(module_name)
            original = getattr(module, name)
            originals[(module_name, name)] = original
            clone = adapted_validator(original, variable, constant)
            self.assertEqual(original.__defaults__, clone.__defaults__)
            before = {semantic_constant(item) for item in original.__code__.co_consts}
            after = {semantic_constant(item) for item in clone.__code__.co_consts}
            self.assertEqual({SYNTHETIC_SHA256}, after - before)
            self.assertEqual(set(), before - after)
            self.assertEqual(HISTORICAL_SHA256, getattr(module, constant))
        with FixtureWitnesses(REPO):
            for (module_name, name), original in originals.items():
                self.assertIsNot(original, getattr(importlib.import_module(module_name), name))
        for (module_name, name), original in originals.items():
            self.assertIs(original, getattr(importlib.import_module(module_name), name))
        self.assertEqual(SYNTHETIC_SHA256, hashlib.sha256(SYNTHETIC_WITNESS).hexdigest())
        self.assertNotEqual(HISTORICAL_SHA256, SYNTHETIC_SHA256)

    def test_live_and_unregistered_roots_deny_before_witness_read(self) -> None:
        with (
            FixtureWitnesses(REPO),
            patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected read")),
            self.assertRaisesRegex(AssertionError, "registered temporary root"),
        ):
            gcr2ctl.validate_trigger(REPO)

    def test_real_hash_missing_staged_tracked_and_extra_file_denials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, FixtureWitnesses(REPO) as adapter:
            repo = self.fixture(temporary)
            witness = adapter.write(repo)
            gcr2ctl.require_workspace(repo)
            witness.write_bytes(SYNTHETIC_WITNESS + b"changed")
            with self.assertRaisesRegex(SystemExit, "has changed"):
                gcr2ctl.validate_trigger(repo)
            witness.unlink()
            with self.assertRaises(SystemExit):
                gcr2ctl.validate_trigger(repo)
            witness.write_bytes(SYNTHETIC_WITNESS)
            extra = repo / "extra.txt"
            extra.write_bytes(b"not admitted\n")
            with self.assertRaisesRegex(SystemExit, "untracked-path boundary"):
                gcr2ctl.require_workspace(repo)
            extra.unlink()
            self.git(repo, "add", WITNESS_PATH)
            with self.assertRaisesRegex(SystemExit, "untracked|unstaged"):
                gcr2ctl.validate_trigger(repo)
            self.git(repo, "commit", "-m", "synthetic forbidden tracking")
            with self.assertRaisesRegex(SystemExit, "untracked"):
                gcr2ctl.validate_trigger(repo)

    def test_redirected_ancestor_cannot_create_an_outside_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            repo = self.fixture(temporary)
            link = repo / "artifacts"
            destination = Path(outside)
            if sys.platform == "win32":
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(destination)], capture_output=True, text=True
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            else:
                link.symlink_to(destination, target_is_directory=True)
            try:
                with FixtureWitnesses(REPO) as adapter, self.assertRaisesRegex(AssertionError, "redirected"):
                    adapter.write(repo)
                self.assertFalse((destination / "evidence").exists())
            finally:
                if sys.platform == "win32":
                    link.rmdir()
                else:
                    link.unlink()

    def test_historical_aliases_deny_before_git_access(self) -> None:
        paths = (
            WITNESS_PATH,
            "./" + WITNESS_PATH,
            "planning/../" + WITNESS_PATH,
            WITNESS_PATH.replace("/", "\\"),
            "/" + WITNESS_PATH,
            "C:/fixture",
            "planning//backlog.yaml",
        )
        with patch("subprocess.check_output", side_effect=AssertionError("Git must not be called")):
            for relative in paths:
                with self.subTest(relative=relative), self.assertRaisesRegex(AssertionError, "non-witness"):
                    historical_bytes(REPO, "a" * 40, relative, "b" * 64)

    def test_shared_repository_rejects_redirected_root_before_any_outside_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            link = Path(temporary) / "redirected-root"
            target = Path(outside)
            if sys.platform == "win32":
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            else:
                link.symlink_to(target, target_is_directory=True)
            try:
                for repo in (link, link / "new-repo"):
                    with self.subTest(repo=repo.name), self.assertRaisesRegex(AssertionError, "nonredirected"):
                        init_shared_repository(repo, REPO)
                self.assertEqual([], list(target.iterdir()))
            finally:
                if sys.platform == "win32":
                    link.rmdir()
                else:
                    link.unlink()

    def test_original_strict_schema_still_rejects_changed_or_authoritative_descriptor(self) -> None:
        from jsonschema import Draft202012Validator

        schema = json.loads((REPO / gcr2ctl.RUNTIME_SCHEMA_PATH).read_bytes())
        validator = Draft202012Validator({"$ref": "#/$defs/witness", "$defs": schema["$defs"]})
        descriptor = gcr2ctl.trigger_witness()
        with FixtureWitnesses(REPO):
            self.assertEqual([], list(validator.iter_errors(descriptor)))
            self.assertTrue(list(validator.iter_errors({**descriptor, "sha256": SYNTHETIC_SHA256})))
            self.assertTrue(list(validator.iter_errors({**descriptor, "authoritative": True})))

    def test_explicit_child_installation_runs_real_validation_before_abrupt_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.fixture(temporary)
            with FixtureWitnesses(REPO) as adapter:
                adapter.write(repo)
            helper_root = Path(__file__).resolve().parent
            child = "\n".join(
                [
                    "import os, pathlib, sys",
                    f"sys.path[:0] = [{str(helper_root)!r}, {str(REPO / 'tools')!r}]",
                    "import gcr2ctl",
                    "from historical_witness_fixture import FixtureWitnesses",
                    "repo = pathlib.Path(sys.argv[1])",
                    f"with FixtureWitnesses(pathlib.Path({str(REPO)!r})) as adapter:",
                    "    adapter.register(repo)",
                    "    gcr2ctl.require_workspace(repo)",
                    "    os._exit(77)",
                ]
            )
            result = subprocess.run([sys.executable, "-B", "-c", child, str(repo)], capture_output=True, text=True)
            self.assertEqual(77, result.returncode, result.stdout + result.stderr)
            with FixtureWitnesses(REPO) as adapter:
                adapter.register(repo)
                gcr2ctl.require_workspace(repo)


if __name__ == "__main__":
    unittest.main()
