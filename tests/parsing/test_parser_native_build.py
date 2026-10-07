"""Imported source and patch redirects are refused before build execution."""

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from parser_native_build import apply_source_patch, extract_source  # noqa: E402
from plugin_worker_runtime_build import WorkerBuildError  # noqa: E402


class ParserNativeBuildTests(unittest.TestCase):
    def test_archive_redirects_and_duplicate_names_leave_no_extracted_source(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            for index, name in enumerate(("../escape", "C:/escape", "x\\escape", "normal")):
                archive = root / f"{index}.tar"
                with tarfile.open(archive, "w") as output:
                    item = tarfile.TarInfo(name)
                    if name == "normal":
                        item.type = tarfile.SYMTYPE
                        item.linkname = "../escape"
                    else:
                        item.size = 1
                    output.addfile(item, io.BytesIO(b"x"))
                target = root / f"source{index}"
                with self.assertRaises(WorkerBuildError):
                    extract_source(archive, target)
                self.assertFalse(target.exists())
            archive = root / "duplicate.tar"
            with tarfile.open(archive, "w") as output:
                for name in ("file", "FILE"):
                    item = tarfile.TarInfo(name)
                    item.size = 1
                    output.addfile(item, io.BytesIO(b"x"))
            with self.assertRaises(WorkerBuildError):
                extract_source(archive, root / "duplicate")
            self.assertFalse((root / "duplicate").exists())

    def test_exact_patch_context_and_paths_are_required(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            (root / "source.h").write_bytes(b"original\n")
            patch = b"--- a/source.h\n+++ b/source.h\n@@ -1 +1 @@\n-original\n+derived\n"
            self.assertEqual("source.h", apply_source_patch(root, patch)[0]["path"])
            self.assertEqual(b"derived\n", (root / "source.h").read_bytes())
            with self.assertRaises(WorkerBuildError):
                apply_source_patch(root, patch)
            self.assertEqual(b"derived\n", (root / "source.h").read_bytes())
            for name in (b"../escape", b"C:/escape", b"C:\\escape"):
                with self.assertRaises(WorkerBuildError):
                    apply_source_patch(root, patch.replace(b"source.h", name))


if __name__ == "__main__":
    unittest.main()
