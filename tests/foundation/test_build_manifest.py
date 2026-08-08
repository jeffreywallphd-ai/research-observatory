from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from build_manifest import (  # noqa: E402
    BUILD_SCHEMA_PATH,
    COMPONENT_SCHEMA_PATH,
    INPUTS_PATH,
    VERSION_PATH,
    VERSION_SCHEMA_PATH,
    generate_build_manifest,
    git_source,
    safe_output_path,
    source_contract,
    synchronize_component_manifests,
)


class BuildManifestTests(unittest.TestCase):
    @staticmethod
    def git_runner(status: bytes = b""):
        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
            arguments = command[1:]
            if arguments[:2] == ["rev-parse", "--verify"]:
                stdout = b"a" * 40 + b"\n"
            elif arguments[:3] == ["show", "-s", "--format=%cI"]:
                stdout = b"2026-08-08T17:05:34-04:00\n"
            elif arguments[:3] == ["show", "-s", "--format=%ct"]:
                stdout = b"1786223134\n"
            elif arguments[:2] == ["status", "--porcelain=v1"]:
                stdout = status
            else:
                return subprocess.CompletedProcess(command, 2, b"", b"unexpected Git command")
            return subprocess.CompletedProcess(command, 0, stdout, b"")

        return runner

    def contract_repo(self, temporary: str) -> Path:
        root = Path(temporary)
        inputs = json.loads((REPO / INPUTS_PATH).read_text(encoding="utf-8"))
        paths = {
            VERSION_PATH,
            VERSION_SCHEMA_PATH,
            INPUTS_PATH,
            COMPONENT_SCHEMA_PATH,
            BUILD_SCHEMA_PATH,
            "package.json",
            "pyproject.toml",
            "Cargo.toml",
            "Cargo.lock",
            "pnpm-lock.yaml",
            "uv.lock",
            "CHANGELOG.md",
            *(item["manifestPath"] for item in inputs["components"]),
            *(item["path"] for item in inputs["dependencyLocks"]),
            *inputs["schemaPaths"],
        }
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        (root / "artifacts" / "tmp").mkdir(parents=True)
        return root

    def test_clean_build_manifest_is_deterministic_and_complete(self) -> None:
        first, first_errors = generate_build_manifest(REPO, runner=self.git_runner())
        second, second_errors = generate_build_manifest(REPO, runner=self.git_runner())

        self.assertEqual([], first_errors)
        self.assertEqual([], second_errors)
        self.assertEqual(first, second)
        assert first is not None
        self.assertEqual("0.1.0+gaaaaaaa", first["buildIdentity"])
        self.assertFalse(first["source"]["dirty"])
        self.assertEqual(
            {"desktop", "core-api", "worker-fabric"}, {item["componentId"] for item in first["components"]}
        )
        self.assertEqual({"0.1.0"}, {item["version"] for item in first["components"]})
        self.assertEqual(3, len(first["dependencies"]["entries"]))
        self.assertGreaterEqual(len(first["schemas"]["entries"]), 11)
        self.assertEqual([], first["modelManifests"]["entries"])
        self.assertRegex(first["modelManifests"]["setId"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(first["manifestId"], r"^sha256:[0-9a-f]{64}$")

    def test_dirty_build_is_labeled_and_lists_changed_inputs(self) -> None:
        status = b" M package.json\0?? local-note.txt\0"

        manifest, errors = generate_build_manifest(REPO, runner=self.git_runner(status))

        self.assertEqual([], errors)
        assert manifest is not None
        self.assertTrue(manifest["source"]["dirty"])
        self.assertEqual(["local-note.txt", "package.json"], manifest["source"]["dirtyPaths"])
        self.assertEqual("0.1.0+gaaaaaaa.dirty", manifest["buildIdentity"])

    def test_rename_status_records_both_paths(self) -> None:
        source, errors = git_source(REPO, runner=self.git_runner(b"R  new-name.txt\0old-name.txt\0"))

        self.assertEqual([], errors)
        assert source is not None
        self.assertEqual(["new-name.txt", "old-name.txt"], source["dirtyPaths"])

    def test_ecosystem_and_component_version_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            package = json.loads((root / "package.json").read_text(encoding="utf-8"))
            package["version"] = "9.9.9"
            (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
            component_path = root / "services/core-api/component-manifest.json"
            component = json.loads(component_path.read_text(encoding="utf-8"))
            component["version"] = "9.9.9"
            component_path.write_text(json.dumps(component), encoding="utf-8")

            _, _, _, errors = source_contract(root)

        self.assertTrue(any("package.json version" in error for error in errors))
        self.assertTrue(any("core-api" in error for error in errors))
        self.assertTrue(any("incompatible" in error for error in errors))

    def test_schema_inventory_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            extra = root / "packages" / "contracts" / "unregistered.schema.json"
            extra.parent.mkdir(parents=True)
            extra.write_text(
                '{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:test:unregistered"}\n',
                encoding="utf-8",
            )

            _, _, _, errors = source_contract(root)

        self.assertTrue(any("exactly inventory" in error for error in errors))

    def test_component_manifests_can_be_regenerated_from_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            component_path = root / "services/core-api/component-manifest.json"
            component_path.write_text('{"version":"9.9.9"}\n', encoding="utf-8")

            synchronization_errors = synchronize_component_manifests(root)
            _, _, components, contract_errors = source_contract(root)

        self.assertEqual([], synchronization_errors)
        self.assertEqual([], contract_errors)
        self.assertEqual({"0.1.0"}, {component["version"] for component in components})

    def test_noncanonical_component_and_lock_inputs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            inputs_path = root / INPUTS_PATH
            inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
            inputs["components"][0]["manifestPath"] = "CHANGELOG.md"
            inputs["dependencyLocks"][0] = {"id": "cargo", "path": "CHANGELOG.md"}
            inputs_path.write_text(json.dumps(inputs), encoding="utf-8")

            _, _, _, errors = source_contract(root)

        self.assertTrue(any("canonical desktop" in error for error in errors))
        self.assertTrue(any("Cargo, pnpm, and uv" in error for error in errors))

    def test_output_cannot_escape_artifacts_scratch(self) -> None:
        with self.assertRaisesRegex(ValueError, "must remain"):
            safe_output_path(REPO, Path("../outside.json"))


if __name__ == "__main__":
    unittest.main()
