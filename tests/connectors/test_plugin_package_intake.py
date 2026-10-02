"""Selected ZIP intake is bounded and remains untrusted until Core verifies it."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_manifest import verify_plugin_package  # noqa: E402
from research_observatory_core.connectors.plugin_package_intake import (  # noqa: E402
    PluginPackageIntakeProblem,
    inspect_plugin_archive,
)

from tests.connectors.test_plugin_manifest_contract import (  # noqa: E402
    PACKAGE_FILE,
    PATH,
    PUBLISHER_ID,
    _manifest_bytes,
    _manifest_document,
)


def archive(*, files: dict[str, bytes] | None = None, manifest: bytes | None = None) -> tuple[bytes, bytes]:
    key = SigningKey(b"\x15" * 32)
    source = manifest or _manifest_bytes(_manifest_document())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        for name, data in (
            files or {"manifest.json": source, "manifest.sig": key.sign(source).signature, PATH: PACKAGE_FILE}
        ).items():
            package.writestr(name, data)
    return buffer.getvalue(), bytes(key.verify_key)


class PluginPackageIntakeTests(unittest.TestCase):
    def test_untrusted_review_digest_matches_later_exact_signature_verification(self):
        raw, key = archive()
        inspected = inspect_plugin_archive(raw)
        self.assertEqual(PUBLISHER_ID, inspected.manifest.publisher_key_id)
        self.assertEqual({PATH: PACKAGE_FILE}, inspected.files)
        self.assertEqual("sha256:" + hashlib.sha256(inspected.manifest_bytes).hexdigest(), inspected.manifest_sha256)
        verified = verify_plugin_package(
            inspected.manifest_bytes, inspected.signature, inspected.files, {PUBLISHER_ID: key}
        )
        self.assertEqual(verified.package_sha256, inspected.package_sha256)

    def test_archive_cannot_smuggle_unlisted_files_paths_or_duplicate_members(self):
        for members in (
            {
                "manifest.json": _manifest_bytes(_manifest_document()),
                "manifest.sig": b"x" * 64,
                PATH: PACKAGE_FILE,
                "unlisted": b"x",
            },
            {
                "manifest.json": _manifest_bytes(_manifest_document()),
                "manifest.sig": b"x" * 64,
                PATH: PACKAGE_FILE,
                "../secret": b"x",
            },
        ):
            with self.subTest(members=tuple(members)), self.assertRaises(PluginPackageIntakeProblem):
                inspect_plugin_archive(archive(files=members)[0])
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as package:
            package.writestr("manifest.json", _manifest_bytes(_manifest_document()))
            package.writestr("manifest.sig", b"x" * 64)
            package.writestr(PATH, PACKAGE_FILE)
            package.writestr(PATH, PACKAGE_FILE)
        with self.assertRaises(PluginPackageIntakeProblem):
            inspect_plugin_archive(raw.getvalue())

    def test_unverified_manifest_hash_and_size_mismatch_deny_before_trust(self):
        with self.assertRaises(PluginPackageIntakeProblem):
            inspect_plugin_archive(
                archive(
                    files={
                        "manifest.json": _manifest_bytes(_manifest_document()),
                        "manifest.sig": b"x" * 64,
                        PATH: b"tamper",
                    }
                )[0]
            )
        with self.assertRaises(PluginPackageIntakeProblem):
            inspect_plugin_archive(b"not a ZIP")
        source = json.loads(_manifest_bytes(_manifest_document()))
        source["files"][0]["sha256"] = "sha256:" + "0" * 64
        with self.assertRaises(PluginPackageIntakeProblem):
            inspect_plugin_archive(archive(manifest=json.dumps(source).encode())[0])


if __name__ == "__main__":
    unittest.main()
