from __future__ import annotations

import json
import os
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
    git_blob_sha1,
    git_source,
    guarded_atomic_write_json,
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
            elif len(arguments) >= 3 and arguments[:2] == ["cat-file", "blob"]:
                stdout = (REPO / arguments[2].removeprefix("HEAD:")).read_bytes()
            elif len(arguments) >= 3 and arguments[0] == "hash-object":
                payload = _.get("input")
                assert isinstance(payload, bytes)
                stdout = git_blob_sha1(payload).encode("ascii") + b"\n"
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

    def test_model_manifest_inputs_remain_governed_empty_until_cap_07(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            inputs_path = root / INPUTS_PATH
            inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
            inputs["modelManifests"] = [{"id": "not-a-model", "path": "CHANGELOG.md"}]
            inputs_path.write_text(json.dumps(inputs), encoding="utf-8")

            _, _, _, errors = source_contract(root)

        self.assertTrue(any("must remain empty until CAP-07" in error for error in errors))

    def test_malformed_ecosystem_mirrors_and_changelog_fail_actionably(self) -> None:
        mutations = {
            "package-root": ("package.json", "[]\n", "package.json must contain an object"),
            "python-project": ("pyproject.toml", 'project = "scalar"\n', "project must be a table"),
            "cargo-workspace": ("Cargo.toml", 'workspace = "scalar"\n', "workspace and workspace.package"),
            "changelog-date": (
                "CHANGELOG.md",
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] not-a-date\n",
                "invalid release heading",
            ),
            "changelog-duplicate": (
                "CHANGELOG.md",
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-08-08\n\n## [0.1.0] - 2026-08-07\n",
                "duplicate release headings",
            ),
            "changelog-invalid-calendar-date": (
                "CHANGELOG.md",
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-02-30\n",
                "has an invalid date",
            ),
            "changelog-title-order": (
                "CHANGELOG.md",
                "## [Unreleased]\n\n## [0.1.0] - 2026-08-08\n\n# Changelog\n",
                "first nonblank line",
            ),
            "changelog-version-order": (
                "CHANGELOG.md",
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-08-08\n\n## [0.2.0] - 2026-08-07\n",
                "newest to oldest",
            ),
            "changelog-non-semver": (
                "CHANGELOG.md",
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-08-08\n\n## [release-one] - 2026-08-07\n",
                "not a semantic version",
            ),
            "changelog-leading-zero-core": (
                "CHANGELOG.md",
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-08-08\n\n## [00.0.1] - 2026-08-07\n",
                "not a semantic version",
            ),
            "changelog-leading-zero-prerelease": (
                "CHANGELOG.md",
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-08-08\n\n## [0.0.1-01] - 2026-08-07\n",
                "not a semantic version",
            ),
            "changelog-empty-prerelease-identifier": (
                "CHANGELOG.md",
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-08-08\n\n## [0.0.1-alpha..1] - 2026-08-07\n",
                "not a semantic version",
            ),
            "changelog-extra-level-two": (
                "CHANGELOG.md",
                "# Changelog\n\n## Notes\n\n## [Unreleased]\n\n## [0.1.0] - 2026-08-08\n",
                "invalid release heading",
            ),
        }
        for label, (path, content, expected) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = self.contract_repo(temporary)
                (root / path).write_text(content, encoding="utf-8")

                _, _, _, errors = source_contract(root)

                self.assertTrue(any(expected in error for error in errors), errors)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            (root / "CHANGELOG.md").write_bytes(b"\xff\xfe")

            _, _, _, errors = source_contract(root)

        self.assertTrue(any("cannot decode CHANGELOG.md" in error for error in errors))

    def test_product_authority_and_schemas_reject_invalid_semver_forms(self) -> None:
        for invalid in ("00.0.1", "0.0.1-01", "0.0.1-alpha..1"):
            with self.subTest(version=invalid), tempfile.TemporaryDirectory() as temporary:
                root = self.contract_repo(temporary)
                version_path = root / VERSION_PATH
                version_document = json.loads(version_path.read_text(encoding="utf-8"))
                version_document["version"] = invalid
                version_path.write_text(json.dumps(version_document), encoding="utf-8")

                _, _, _, errors = source_contract(root)

                self.assertTrue(any("productVersion.version" in error for error in errors), errors)
                self.assertTrue(
                    any("product version must be semantic version text" in error for error in errors), errors
                )

    def test_reserved_model_manifest_tree_rejects_every_entry_before_cap_07(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            reserved = root / "packaging" / "model-manifests"
            reserved.mkdir()
            (reserved / "extensionless-manifest").write_text("premature\n", encoding="utf-8")

            _, _, _, errors = source_contract(root)

        self.assertTrue(any("must remain empty until CAP-07" in error for error in errors), errors)

    def test_clean_manifest_rejects_input_status_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            committed = {
                path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()
            }
            mutated = False

            def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
                nonlocal mutated
                arguments = command[1:]
                if arguments[:2] == ["rev-parse", "--verify"]:
                    stdout = b"a" * 40 + b"\n"
                elif arguments[:3] == ["show", "-s", "--format=%cI"]:
                    stdout = b"2026-08-08T17:05:34-04:00\n"
                elif arguments[:3] == ["show", "-s", "--format=%ct"]:
                    stdout = b"1786223134\n"
                elif arguments[:2] == ["status", "--porcelain=v1"]:
                    if not mutated:
                        (root / "Cargo.lock").write_bytes(b"raced lock bytes\n")
                        mutated = True
                    stdout = b""
                elif len(arguments) >= 3 and arguments[:2] == ["cat-file", "blob"]:
                    stdout = committed[arguments[2].removeprefix("HEAD:")]
                elif len(arguments) >= 3 and arguments[0] == "hash-object":
                    payload = _.get("input")
                    assert isinstance(payload, bytes)
                    stdout = git_blob_sha1(payload).encode("ascii") + b"\n"
                else:
                    return subprocess.CompletedProcess(command, 2, b"", b"unexpected Git command")
                return subprocess.CompletedProcess(command, 0, stdout, b"")

            manifest, errors = generate_build_manifest(root, runner=runner)

        self.assertIsNone(manifest)
        self.assertTrue(
            any("differs from the committed HEAD checkout: Cargo.lock" in error for error in errors), errors
        )

    def test_guarded_write_rejects_parent_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent = root / "apps" / "desktop"
            parent.mkdir(parents=True)
            destination = parent / "component-manifest.json"
            original = root / "apps" / "desktop-original"

            def swap_parent() -> None:
                parent.rename(original)
                parent.mkdir()

            with self.assertRaises((OSError, ValueError)):
                guarded_atomic_write_json(root, destination, {"safe": True}, root, before_replace=swap_parent)

            self.assertFalse(destination.exists())

    def test_dirty_manifest_rejects_mutation_during_final_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.contract_repo(temporary)
            lock_path = root / "Cargo.lock"
            lock_path.write_bytes(b"first dirty state\n")
            status_calls = 0

            def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
                nonlocal status_calls
                arguments = command[1:]
                if arguments[:2] == ["rev-parse", "--verify"]:
                    stdout = b"a" * 40 + b"\n"
                elif arguments[:3] == ["show", "-s", "--format=%cI"]:
                    stdout = b"2026-08-08T17:05:34-04:00\n"
                elif arguments[:3] == ["show", "-s", "--format=%ct"]:
                    stdout = b"1786223134\n"
                elif arguments[:2] == ["status", "--porcelain=v1"]:
                    status_calls += 1
                    if status_calls == 3:
                        lock_path.write_bytes(b"second dirty state\n")
                    stdout = b" M Cargo.lock\0"
                else:
                    return subprocess.CompletedProcess(command, 2, b"", b"unexpected Git command")
                return subprocess.CompletedProcess(command, 0, stdout, b"")

            manifest, errors = generate_build_manifest(root, runner=runner)

        self.assertIsNone(manifest)
        self.assertTrue(
            any("governed input changed" in error or "Git command is unavailable" in error for error in errors), errors
        )

    def test_output_rejects_redirected_scratch_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary).resolve()
            (root / "artifacts").mkdir()
            link = root / "artifacts" / "tmp"
            try:
                link.symlink_to(Path(outside), target_is_directory=True)
            except OSError as exc:
                junction = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(Path(outside).resolve())],
                    capture_output=True,
                    check=False,
                )
                if junction.returncode != 0:
                    self.skipTest(f"directory redirects unavailable: {exc}; {junction.stderr!r}")
            try:
                with self.assertRaisesRegex(ValueError, "canonical artifacts/tmp"):
                    safe_output_path(root, Path("artifacts/tmp/escaped.json"))
            finally:
                os.rmdir(link)

    def test_output_cannot_escape_artifacts_scratch(self) -> None:
        with self.assertRaisesRegex(ValueError, "must remain"):
            safe_output_path(REPO, Path("../outside.json"))


if __name__ == "__main__":
    unittest.main()
