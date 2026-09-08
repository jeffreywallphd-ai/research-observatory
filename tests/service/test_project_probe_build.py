"""Fail-closed renderer binding at the native probe's actual build boundary."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import (  # noqa: E402
    PRODUCT_EXTERNAL_INPUTS,
    PRODUCT_MANIFEST,
    PRODUCT_ROOT,
    product_build_errors,
)
from ui_conformance import file_inventory  # noqa: E402

from tests.service import test_native_project_contract as probe  # noqa: E402


class ProjectProbeSeedImportTests(unittest.TestCase):
    def test_direct_seed_entry_resolves_fixtures_without_repository_on_pythonpath(self) -> None:
        # Stop at nonexistent fixture paths after imports, before any project,
        # vault or Windows credential-provider access. Exercise the actual CLI.
        with tempfile.TemporaryDirectory(prefix="ro-seed-import-fixture-") as directory:
            root = Path(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(Path(__file__).with_name("test_native_project_contract.py")),
                    "--seed-lineage",
                    str(root / "absent-project"),
                    str(root / "absent-vault"),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("FileNotFoundError", result.stderr)
        self.assertNotIn("ModuleNotFoundError", result.stderr)


class ProjectProbeBuildBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        # Only the identity fields are reused; all source/artifact bytes below
        # are synthetic and inventoried by the real product validator.
        self.manifest = json.loads((probe.REPO / PRODUCT_MANIFEST).read_bytes())
        self.files = {
            **dict.fromkeys(PRODUCT_EXTERNAL_INPUTS, b"synthetic input"),
            "apps/desktop/src/app.tsx": b"synthetic renderer source",
            "apps/desktop/src-tauri/src/directory_picker.rs": b"synthetic native source",
            "apps/desktop/src-tauri/tauri.conf.json": b'{"build":{"frontendDist":"../product-dist"}}',
            "packages/ui-components/src/index.tsx": b"synthetic shared component",
            "packages/ui-tokens/src/index.css": b"synthetic shared tokens",
            "design/ui-reference/SITE_MANIFEST.json": b'{"pages":[]}',
            "tests/service/test_native_project_contract.py": b"synthetic build helper",
            "tools/desktop_app_check.py": b"synthetic validator input",
            "tools/ui_conformance.py": b"synthetic inventory input",
            f"{PRODUCT_ROOT}/index.html": b"<!doctype html><title>Synthetic product</title>",
            f"{PRODUCT_ROOT}/assets/app.js": b"synthetic renderer artifact",
            f"{PRODUCT_ROOT}/assets/app.js.map": b"{}",
            f"{PRODUCT_ROOT}/assets/app.css": b"synthetic style artifact",
            "target/debug/examples/project_contract_probe.exe": b"synthetic binary; never executed",
        }
        self.files["verification/extensions/desktop-ui.json"] = json.dumps(
            {key: self.manifest[key] for key in ("referenceId", "referencePackageSha256")}
        ).encode()
        for name, payload in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        self.publish_manifest()
        self.assertEqual([], product_build_errors(self.root))
        self.native_inputs = "Cargo.toml\nCargo.lock\napps/desktop/src-tauri/tauri.conf.json\n"
        self.addCleanup(patch.stopall)
        patch.object(probe, "REPO", self.root).start()
        patch.object(probe.subprocess, "check_output", return_value=self.native_inputs).start()
        patch.object(probe, "tool_environment", return_value=({}, Path("corepack"), Path("cargo"))).start()
        self.build_output = (
            json.dumps(
                {
                    "reason": "compiler-artifact",
                    "target": {"name": "project_contract_probe", "kind": ["example"]},
                    "executable": str(self.root / "target/debug/examples/project_contract_probe.exe"),
                }
            )
            + "\n"
        )
        self.run_process = patch.object(
            probe.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, self.build_output, "")
        ).start()
        self.pe = patch.object(probe, "assert_project_probe_manifest").start()

    def publish_manifest(self) -> None:
        sources = {}
        for name in ("apps/desktop", "packages/ui-components", "packages/ui-tokens"):
            sources.update(
                file_inventory(self.root, self.root / name, excluded_directories=frozenset({"product-dist"}))
            )
        for name in PRODUCT_EXTERNAL_INPUTS:
            sources[name] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.manifest["sourceFiles"] = dict(sorted(sources.items()))
        self.manifest["artifacts"] = {
            name.removeprefix(PRODUCT_ROOT + "/"): hashlib.sha256((self.root / name).read_bytes()).hexdigest()
            for name in self.files
            if name.startswith(PRODUCT_ROOT + "/")
        }
        (self.root / PRODUCT_MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_valid_build_binds_exact_renderer_and_artifact_bytes(self) -> None:
        record = probe.build_project_probe()
        for name in ("apps/desktop/src/app.tsx", f"{PRODUCT_ROOT}/assets/app.js", PRODUCT_MANIFEST):
            self.assertEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(), record["inputSha256"][name])
        self.run_process.assert_called_once()
        self.pe.assert_called_once()

    def test_stale_renderer_source_is_rejected_before_compilation(self) -> None:
        (self.root / "apps/desktop/src/app.tsx").write_bytes(b"unbuilt change")
        with self.assertRaisesRegex(AssertionError, "product"):
            probe.build_project_probe()
        self.run_process.assert_not_called()

    def test_missing_compiler_artifact_cannot_attest_a_stale_binary(self) -> None:
        self.run_process.return_value = subprocess.CompletedProcess([], 0, "", "")
        with self.assertRaisesRegex(AssertionError, "Cargo.*executable"):
            probe.build_project_probe()
        self.pe.assert_not_called()

    def test_different_cargo_output_cannot_attest_a_stale_expected_binary(self) -> None:
        event = json.loads(self.build_output)
        event["executable"] = str(self.root / "alternate-target/debug/examples/project_contract_probe.exe")
        self.run_process.return_value = subprocess.CompletedProcess([], 0, json.dumps(event), "")
        with self.assertRaisesRegex(AssertionError, "Cargo.*executable"):
            probe.build_project_probe()
        self.pe.assert_not_called()

    def test_modified_renderer_artifact_is_rejected_before_compilation(self) -> None:
        (self.root / PRODUCT_ROOT / "assets/app.js").write_bytes(b"unbound artifact")
        with self.assertRaisesRegex(AssertionError, "product"):
            probe.build_project_probe()
        self.run_process.assert_not_called()

    def test_unlisted_artifact_is_rejected_before_compilation(self) -> None:
        (self.root / PRODUCT_ROOT / "extra.js").write_bytes(b"unlisted")
        with self.assertRaisesRegex(AssertionError, "product"):
            probe.build_project_probe()
        self.run_process.assert_not_called()

    def test_source_change_after_validation_is_rejected_before_compilation(self) -> None:
        def validate_then_change(root):
            errors = product_build_errors(root)
            (root / "apps/desktop/src/app.tsx").write_bytes(b"changed after validation")
            return errors

        with (
            patch.object(probe, "product_build_errors", side_effect=validate_then_change),
            self.assertRaisesRegex(AssertionError, "product inputs changed"),
        ):
            probe.build_project_probe()
        self.run_process.assert_not_called()

    def test_manifest_swap_during_validation_is_rejected_before_using_its_paths(self) -> None:
        def validate_then_swap(root):
            errors = product_build_errors(root)
            self.manifest["sourceFiles"]["../never-read"] = "0" * 64
            (root / PRODUCT_MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")
            return errors

        with (
            patch.object(probe, "product_build_errors", side_effect=validate_then_swap),
            self.assertRaisesRegex(AssertionError, "product manifest changed during validation"),
        ):
            probe.build_project_probe()
        self.run_process.assert_not_called()

    def test_artifact_change_during_compilation_cannot_receive_a_build_record(self) -> None:
        def compile_and_change(*_args, **_kwargs):
            (self.root / PRODUCT_ROOT / "assets/app.js").write_bytes(b"unbound during build")
            return subprocess.CompletedProcess([], 0, self.build_output, "")

        self.run_process.side_effect = compile_and_change
        with self.assertRaisesRegex(AssertionError, "product"):
            probe.build_project_probe()
        self.pe.assert_not_called()

    def test_even_consistently_rebuilt_product_during_compilation_is_rejected(self) -> None:
        def compile_and_rebuild(*_args, **_kwargs):
            (self.root / "apps/desktop/src/app.tsx").write_bytes(b"rebuilt source")
            (self.root / PRODUCT_ROOT / "assets/app.js").write_bytes(b"rebuilt artifact")
            self.publish_manifest()
            self.assertEqual([], product_build_errors(self.root))
            return subprocess.CompletedProcess([], 0, self.build_output, "")

        self.run_process.side_effect = compile_and_rebuild
        with self.assertRaisesRegex(AssertionError, "changed"):
            probe.build_project_probe()
        self.pe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
