from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from install_trivy import InstallError, extract_executable, platform_key, sha256  # noqa: E402


class TrivyInstallerTests(unittest.TestCase):
    def test_supported_platforms_map_to_pinned_asset_keys(self) -> None:
        self.assertEqual("windows-x64", platform_key("Windows", "AMD64"))
        self.assertEqual("linux-arm64", platform_key("Linux", "aarch64"))
        self.assertEqual("macos-arm64", platform_key("Darwin", "arm64"))

    def test_unsupported_platform_fails_closed(self) -> None:
        with self.assertRaisesRegex(InstallError, "unsupported Trivy platform"):
            platform_key("Plan9", "mips")

    def test_sha256_hashes_binary_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "artifact.bin"
            artifact.write_bytes(b"controlled scanner fixture")

            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), sha256(artifact))

    def test_zip_extraction_accepts_one_safe_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "scanner.zip"
            destination = root / "trivy.exe"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("nested/trivy.exe", b"controlled executable")

            extract_executable(archive, "zip", "trivy.exe", destination)

            self.assertEqual(b"controlled executable", destination.read_bytes())

    def test_zip_extraction_rejects_traversal_and_ambiguous_executables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "scanner.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../trivy.exe", b"traversal")
                bundle.writestr("one/trivy.exe", b"one")
                bundle.writestr("two/trivy.exe", b"two")

            with self.assertRaisesRegex(InstallError, "expected exactly one safe"):
                extract_executable(archive, "zip", "trivy.exe", root / "trivy.exe")


if __name__ == "__main__":
    unittest.main()
