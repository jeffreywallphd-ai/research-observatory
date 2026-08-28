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
    prepare_report_path,
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
                "excludedModules": [
                    "mypy",
                    "pip",
                    "pydantic.mypy",
                    "pydantic.v1.mypy",
                    "pytest",
                    "setuptools",
                    "yaml",
                ],
                "hiddenModules": [
                    "_cffi_backend",
                    "research_observatory_core.domain_compatibility",
                    "research_observatory_core.domain_lifecycles",
                    "research_observatory_core.research_intent_contracts",
                    "research_observatory_core.migrations.runner",
                    "research_observatory_core.object_store",
                    "research_observatory_core.ports.credential_store",
                    "research_observatory_core.ports.database_keys",
                    "research_observatory_core.repositories",
                    "research_observatory_core.windows_credentials",
                    "sqlcipher3",
                    "sqlcipher3._sqlite3",
                ],
            },
        )
        self.assertIn("_cffi_backend", contract["requiredModules"])
        self.assertIn("alembic", contract["requiredModules"])
        self.assertIn("nacl", contract["requiredModules"])
        self.assertIn("research_observatory_core.domain_compatibility", contract["requiredModules"])
        self.assertIn("research_observatory_core.domain_lifecycles", contract["requiredModules"])
        self.assertIn("research_observatory_core.research_intent_contracts", contract["requiredModules"])
        self.assertIn("sqlalchemy", contract["requiredModules"])
        self.assertIn("sqlcipher3", contract["requiredModules"])
        self.assertEqual(
            contract["noticeFiles"],
            [
                {
                    "source": "services/core-api/THIRD_PARTY_NOTICES.txt",
                    "destination": "THIRD_PARTY_NOTICES.txt",
                }
            ],
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

    def test_artifact_verifier_rejects_identity_free_and_malformed_manifests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="core-sidecar-manifest-", dir=REPO / "artifacts" / "tmp") as temporary:
            artifact = Path(temporary)
            self.assertTrue(any("schema violation" in error for error in verify_artifact(artifact, {"files": [42]})))
            wrong_identity: dict[str, object] = {
                "schemaVersion": "1.0",
                "documentType": "other",
                "componentId": "other",
                "componentVersion": "0.1.0",
                "targetTriple": "wrong-target",
                "pythonVersion": "3.14.6",
                "builder": None,
                "entrypoint": None,
                "totalBytes": 0,
                "files": [],
            }
            self.assertTrue(any("schema violation" in error for error in verify_artifact(artifact, wrong_identity)))
            identity_free = {"files": [], "totalBytes": 0}
            self.assertTrue(any("schema violation" in error for error in verify_artifact(artifact, identity_free)))

    def test_report_path_rejects_an_existing_hardlink_without_touching_target(self) -> None:
        scratch_root = REPO / "artifacts" / "tmp"
        with tempfile.TemporaryDirectory(prefix="core-sidecar-report-", dir=scratch_root) as temporary:
            checkout = Path(temporary)
            report = checkout / "artifacts" / "tmp" / "core-sidecar-package.json"
            report.parent.mkdir(parents=True)
            outside = checkout / "outside.json"
            outside.write_text("outside remains unchanged", encoding="utf-8")
            os.link(outside, report)
            with self.assertRaisesRegex(SidecarBuildError, "private canonical regular file"):
                prepare_report_path(checkout, report)
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside remains unchanged")

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
            for field, invalid_value in (("componentVersion", "99.99.99"), ("pythonVersion", "3.14.999")):
                wrong_version = {**manifest, field: invalid_value}
                errors = verify_artifact(artifact_root, wrong_version)
                self.assertTrue(any(f"{field} does not match the governed build contract" in error for error in errors))
            self.assertLessEqual(manifest["totalBytes"], 134_217_728)
            packaged_paths = tuple(item["path"].casefold() for item in manifest["files"])
            self.assertIn("third_party_notices.txt", packaged_paths)
            self.assertTrue(any("/sqlcipher3/_sqlite3" in path and path.endswith(".pyd") for path in packaged_paths))
            for excluded_module in ("mypy", "pip", "pytest", "setuptools", "yaml"):
                self.assertFalse(
                    any(f"/{excluded_module}/" in f"/{path}/" for path in packaged_paths),
                    f"build-only module leaked into runtime: {excluded_module}",
                )
            archive = subprocess.run(
                [
                    REPO / ".venv" / "Scripts" / "pyi-archive_viewer.exe",
                    "--recursive",
                    "--list",
                    artifact_root / manifest["entrypoint"],
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(archive.returncode, 0, archive.stderr)
            for archived_module in (
                "pydantic.mypy",
                "pydantic.v1.mypy",
            ):
                self.assertNotIn(f"'{archived_module}'", archive.stdout)
            for required_module in (
                "alembic.operations",
                "research_observatory_core.migrations.runner",
                "research_observatory_core.migrations.versions.v0002_schema_history",
                "research_observatory_core.migrations.versions.v0003_object_envelopes",
                "research_observatory_core.migrations.versions.v0004_object_envelope_upgrades",
                "research_observatory_core.migrations.versions.v0005_object_creation_source",
                "research_observatory_core.object_store",
                "research_observatory_core.ports.credential_store",
                "research_observatory_core.ports.database_keys",
                "research_observatory_core.ports.object_store",
                "research_observatory_core.ports.repositories",
                "research_observatory_core.repositories",
                "research_observatory_core.windows_credentials",
                "sqlcipher3",
                "sqlalchemy.engine",
            ):
                self.assertIn(f"'{required_module}'", archive.stdout)

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
            checked = json.loads(completed.stdout)
            self.assertEqual(checked["status"], "configuration-valid")
            self.assertNotIn("storageMigration", checked)
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
