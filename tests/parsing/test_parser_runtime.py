"""Application-selected parsing profile; connector limits retain their meaning."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "services/core-api/src")]

from workers.windows.runtime_inventory import (  # noqa: E402
    RuntimeInventoryError,
    SignedWorkerRuntime,
    verify_worker_runtime,
)

IMAGE = "research-observatory-document-parser-x86_64-pc-windows-msvc"
DIRECTORY = "parser"
IMAGE_PATH = f"{DIRECTORY}/{IMAGE}.exe"


class ParserRuntimeTests(unittest.TestCase):
    def runtime(self, root, *, profile="ro-parser-cpu-1"):
        paths = [
            IMAGE_PATH,
            *(
                f"{DIRECTORY}/_internal/{name}"
                for name in ("parser-config.json", "parser-assets.json", "parser-runtime.lock")
            ),
        ]
        paths.extend(f"{DIRECTORY}/_internal/synthetic-{index}.dat" for index in range(257))
        paths.extend(
            f"{DIRECTORY}/_internal/{name}"
            for name in ("torch-2.14.0+cpu.dist-info/METADATA", "[Content_Types].xml", "Lorem ipsum.txt")
        )
        entries = []
        for name in paths:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic runtime fixture")
            entries.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        document = {
            "schemaVersion": "2.0",
            "documentType": "application-signed-lpac-parser-package",
            "imagePath": IMAGE_PATH,
            "launchProfile": profile,
            "files": entries,
        }
        raw = json.dumps(document).encode()
        key = SigningKey.generate()
        return SignedWorkerRuntime(root, raw, key.sign(raw).signature, bytes(key.verify_key))

    def test_parser_package_is_not_authority_to_expand_connector_profile(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            runtime = self.runtime(Path(temporary))
            with self.assertRaises(RuntimeInventoryError):
                verify_worker_runtime(runtime)
            self.assertEqual(verify_worker_runtime(runtime, profile="parser"), runtime.package / IMAGE_PATH)

    def test_signed_unknown_profile_and_modified_asset_are_refused(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            runtime = self.runtime(root, profile="unbounded-parser")
            with self.assertRaises(RuntimeInventoryError):
                verify_worker_runtime(runtime, profile="parser")
            runtime = self.runtime(root)
            (root / DIRECTORY / "_internal/parser-assets.json").write_bytes(b"substituted")
            with self.assertRaisesRegex(RuntimeInventoryError, "hash-mismatch"):
                verify_worker_runtime(runtime, profile="parser")

    def test_wheel_filename_admission_does_not_admit_redirect_syntax(self):
        from workers.windows.runtime_inventory import _safe_parser_path

        for name in ("../model", "model:secret", "a\\b", "a/CON.txt", "a/.", "a/trailing ", "a/*"):
            with self.subTest(name=name):
                self.assertFalse(_safe_parser_path(name))

    def test_nested_unlisted_payload_and_changed_bytes_are_not_hidden_by_enumeration(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            runtime = self.runtime(root)
            injected = root / DIRECTORY / "_internal/unselected/deep/payload.dll"
            injected.parent.mkdir(parents=True)
            injected.write_bytes(b"unapproved payload")
            with self.assertRaisesRegex(RuntimeInventoryError, "hash-mismatch"):
                verify_worker_runtime(runtime, profile="parser")

            injected.unlink()
            self.assertEqual(runtime.package / IMAGE_PATH, verify_worker_runtime(runtime, profile="parser"))
            original = root / DIRECTORY / "_internal/parser-config.json"
            original.write_bytes(b"different bytes at the same length"[: original.stat().st_size])
            with self.assertRaisesRegex(RuntimeInventoryError, "hash-mismatch"):
                verify_worker_runtime(runtime, profile="parser")

    def test_internal_directory_redirect_cannot_escape_signed_package(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            parent = Path(temporary)
            root = parent / "package"
            root.mkdir()
            runtime = self.runtime(root)
            outside = parent / "outside"
            outside.mkdir()
            (outside / "foreign.dll").write_bytes(b"unapproved outside payload")
            alias = root / DIRECTORY / "_internal/redirect"
            try:
                alias.symlink_to(outside, target_is_directory=True)
            except OSError:
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(alias), str(outside)], capture_output=True, check=False
                )
                if result.returncode:
                    self.skipTest("directory redirect creation unavailable")
            with self.assertRaisesRegex(RuntimeInventoryError, "redirect-denied"):
                verify_worker_runtime(runtime, profile="parser")

    def test_installed_producer_binds_complete_authenticated_package(self):
        from research_observatory_core.document_parser_runtime import InstalledDocumentParserRuntime

        from workers.document.parser_package import ASSETS_SHA256, CONFIGURATION_SHA256

        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            runtime = self.runtime(Path(temporary))
            with (
                patch.object(sys, "frozen", True, create=True),
                patch("workers.windows.runtime_inventory.load_installed_parser_runtime", return_value=runtime),
                patch(
                    "workers.document.parser_package.package_observations",
                    return_value=(CONFIGURATION_SHA256, ASSETS_SHA256),
                ),
            ):
                loader = InstalledDocumentParserRuntime()
                selected = loader.load()
                native = loader.load_native()
                inspection = loader.load_inspection()
            self.assertIs(selected.runtime, runtime)
            digest = hashlib.sha256(runtime.inventory_bytes).hexdigest()
            for descriptor in (selected.descriptor, native.descriptor, inspection.descriptor):
                self.assertEqual(
                    [
                        (asset.version, asset.sha256)
                        for asset in descriptor.assets
                        if asset.component == "parser-runtime"
                    ],
                    [("ro-parser-cpu-1", digest)],
                )
            self.assertEqual(selected.descriptor.configuration_sha256, CONFIGURATION_SHA256)
            self.assertEqual(native.descriptor.kind, "native")
            self.assertEqual(inspection.descriptor.kind, "degraded-inspection")

    def test_uninstalled_core_and_invalid_package_cannot_select_a_producer(self):
        from research_observatory_core.document_parser_runtime import InstalledDocumentParserRuntime
        from research_observatory_core.ports.parsing import ParseProblem

        loader = InstalledDocumentParserRuntime()
        with patch.object(sys, "frozen", False, create=True), self.assertRaises(ParseProblem):
            loader.load()
        with (
            patch.object(sys, "frozen", True, create=True),
            patch("workers.windows.runtime_inventory.load_installed_parser_runtime", side_effect=ValueError("private")),
            self.assertRaisesRegex(ParseProblem, "^parser-runtime-unavailable$") as problem,
        ):
            loader.load()
        self.assertIsNone(problem.exception.__context__)


if __name__ == "__main__":
    unittest.main()
