"""The parser derivative cannot silently modify unrelated CPython bytes."""

import difflib
import hashlib
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools")]
from parser_socket_build import PATCH, _patched_source, patched_socket  # noqa: E402
from plugin_worker_runtime_build import WorkerBuildError  # noqa: E402


class ParserSocketBuildTests(unittest.TestCase):
    def test_substituted_source_cannot_acquire_patch_authority(self):
        patch = PATCH.read_bytes()
        with self.assertRaisesRegex(WorkerBuildError, "source-mismatch"):
            patched_socket(b"substituted source", patch)

    def test_multihunk_source_variant_preserves_unaffected_lines_and_refuses_tamper(self):
        source = "\n".join(f"unchanged line {i}" for i in range(40)) + "\n"
        target = source.replace("unchanged line 4\n", "first replacement\nextra line\n")
        target = target.replace("unchanged line 32\n", "last replacement\n")
        patch = "".join(
            difflib.unified_diff(
                source.splitlines(True),
                target.splitlines(True),
                fromfile="Modules/fixture.c",
                tofile="Modules/fixture.c",
            )
        ).encode()
        digest = hashlib.sha256(source.encode()).hexdigest()
        patch_digest = hashlib.sha256(patch).hexdigest()
        self.assertEqual(_patched_source(source.encode(), patch, digest, patch_digest, "fixture.c"), target.encode())
        with self.assertRaisesRegex(WorkerBuildError, "patch-mismatch"):
            _patched_source(
                source.encode(), patch.replace(b"extra line", b"unauthorized"), digest, patch_digest, "fixture.c"
            )


if __name__ == "__main__":
    unittest.main()
