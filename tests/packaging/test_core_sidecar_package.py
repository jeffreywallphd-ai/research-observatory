from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from core_sidecar_build import (  # noqa: E402
    SidecarBuildError,
    build_sidecar,
    load_build_contract,
    verify_artifact,
)


class CoreSidecarPackageTests(unittest.TestCase):
    def test_build_contract_is_strict_and_version_bound(self) -> None:
        contract = load_build_contract(REPO)
        self.assertEqual(contract["targetTriple"], "x86_64-pc-windows-msvc")
        self.assertEqual(contract["pythonVersion"], "3.14.6")
        self.assertEqual(
            contract["builder"],
            {
                "name": "PyInstaller",
                "version": "6.21.0",
                "mode": "onedir",
                "upx": False,
                "contentsDirectory": "research-observatory-core-runtime",
                "excludedModules": ["mypy", "pip", "pytest", "setuptools", "yaml"],
            },
        )
        self.assertEqual(contract["componentVersion"], "0.1.0")

    def test_build_contract_rejects_a_redirected_governed_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="core-sidecar-contract-", dir=REPO / "artifacts" / "tmp") as temporary:
            checkout = Path(temporary)
            contract_path = checkout / "services" / "core-api" / "packaging" / "sidecar-build.json"
            contract_path.parent.mkdir(parents=True)
            redirected = checkout / "redirected.json"
            redirected.write_text("{}", encoding="utf-8")
            try:
                contract_path.symlink_to(redirected)
            except OSError:
                self.skipTest("file symlinks are not available for this Windows token")
            with self.assertRaisesRegex(SidecarBuildError, "redirected governed path"):
                load_build_contract(checkout)

    def test_artifact_verifier_rejects_duplicate_and_changed_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="core-sidecar-verify-", dir=REPO / "artifacts" / "tmp") as temporary:
            artifact = Path(temporary)
            executable = artifact / "core.exe"
            executable.write_bytes(b"first")
            digest = hashlib.sha256(b"first").hexdigest()
            file_record = {"path": "core.exe", "bytes": 5, "sha256": digest}
            manifest: dict[str, Any] = {
                "entrypoint": "core.exe",
                "totalBytes": 5,
                "files": [file_record, file_record],
            }
            self.assertIn("artifact manifest contains a duplicate path: core.exe", verify_artifact(artifact, manifest))
            manifest["files"] = manifest["files"][:1]
            executable.write_bytes(b"changed")
            self.assertTrue(any("changed" in error for error in verify_artifact(artifact, manifest)))

    def test_packaged_sidecar_runs_without_system_python_and_detects_missing_runtime_file(self) -> None:
        scratch_root = REPO / "artifacts" / "tmp"
        scratch_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="core-sidecar-test-", dir=scratch_root) as temporary:
            artifact_root, manifest = build_sidecar(REPO, Path(temporary))
            schema = json.loads(
                (REPO / "packages" / "contracts" / "core-api" / "sidecar-artifact.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(manifest)), [])
            self.assertEqual(verify_artifact(artifact_root, manifest), [])
            self.assertLessEqual(manifest["totalBytes"], 134_217_728)
            packaged_paths = tuple(item["path"].casefold() for item in manifest["files"])
            for excluded_module in ("mypy", "pip", "pytest", "setuptools", "yaml"):
                self.assertFalse(
                    any(f"/{excluded_module}/" in f"/{path}/" for path in packaged_paths),
                    f"build-only module leaked into runtime: {excluded_module}",
                )

            environment = {
                "COMSPEC": os.environ["COMSPEC"],
                "PATH": str(Path(os.environ["SYSTEMROOT"]) / "System32"),
                "SYSTEMROOT": os.environ["SYSTEMROOT"],
                "TEMP": str(Path(temporary) / "isolated-temp"),
                "TMP": str(Path(temporary) / "isolated-temp"),
            }
            Path(environment["TEMP"]).mkdir()
            executable = artifact_root / manifest["entrypoint"]
            completed = subprocess.run(
                [executable, "--check"],
                cwd=Path(environment["TEMP"]),
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], "configuration-valid")
            self.assertNotIn("python", environment["PATH"].casefold())

            runtime_candidates = sorted(
                path
                for path in artifact_root.rglob("*")
                if path.is_file() and ("pydantic_core" in path.name.casefold() or path.name == "python314.dll")
            )
            self.assertTrue(runtime_candidates)
            removed = runtime_candidates[0]
            backup = removed.with_suffix(removed.suffix + ".missing")
            shutil.move(removed, backup)
            try:
                errors = verify_artifact(artifact_root, manifest)
                self.assertTrue(any("missing" in error for error in errors), errors)
            finally:
                shutil.move(backup, removed)
            self.assertEqual(verify_artifact(artifact_root, manifest), [])


if __name__ == "__main__":
    unittest.main()
