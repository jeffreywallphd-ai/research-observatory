"""Compiled modules retain source introspection without loose source files."""

import hashlib
import inspect
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from workers.document.source_bundle import SourceBundleError, install_source_loader  # noqa: E402


class ParserSourceBundleTests(unittest.TestCase):
    def bundle(self, root, *, extra=None, source=None):
        self.source = b"def declared_function():\n    return 'synthetic code fixture'\n" if source is None else source
        archive = root / "parser-sources.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as writer:
            writer.writestr("torch/synthetic.py", self.source)
            if extra:
                writer.writestr(*extra)
        document = {
            "schemaVersion": "1.0",
            "documentType": "pinned-parser-python-sources",
            "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "files": [
                {
                    "path": "torch/synthetic.py",
                    "sha256": hashlib.sha256(self.source).hexdigest(),
                    "bytes": len(self.source),
                }
            ],
        }
        (root / "parser-source-index.json").write_text(json.dumps(document))

    def test_source_introspection_works_for_compiled_module_without_plaintext_file(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            self.bundle(root)

            class Loader:
                path = str(root / "torch/synthetic.py")

                def get_source(self, fullname):
                    return None

            loader = Loader()
            module = types.ModuleType("torch.synthetic")
            module.__file__, module.__loader__ = loader.path, loader
            exec(compile(self.source, loader.path, "exec"), module.__dict__)
            sys.modules[module.__name__] = module
            original = Loader.get_source
            try:
                with self.assertRaises(OSError):
                    inspect.getsource(module.declared_function)
                install_source_loader(root, Loader)
                self.assertEqual(self.source.decode(), inspect.getsource(module.declared_function))
                self.assertFalse(Path(loader.path).exists())
            finally:
                Loader.get_source = original
                sys.modules.pop(module.__name__, None)

    def test_unlisted_traversal_or_altered_archive_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)

            class Loader:
                def get_source(self, fullname):
                    return None

            for extra in (("../foreign.py", b"foreign"), ("torch/unlisted.py", b"foreign")):
                self.bundle(root, extra=extra)
                with self.assertRaisesRegex(SourceBundleError, "^parser-source-bundle-invalid$"):
                    install_source_loader(root, Loader)
            self.bundle(root)
            with (root / "parser-sources.zip").open("ab") as writer:
                writer.write(b"modified")
            with self.assertRaisesRegex(SourceBundleError, "^parser-source-bundle-invalid$"):
                install_source_loader(root, Loader)

    def test_package_compaction_preserves_source_native_and_resource_bytes(self):
        sys.path.insert(0, str(REPO / "tools"))
        from document_parser_runtime_build import _bundle_sources

        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            source = root / "torch/nn/declared.py"
            source.parent.mkdir(parents=True)
            wire = b"# Exact public synthetic source bytes.\nDECLARED = 7\n"
            source.write_bytes(wire)
            native = root / "torch/lib/declared.dll"
            native.parent.mkdir()
            native.write_bytes(b"synthetic native bytes")
            resource = root / "torch/declared.json"
            resource.write_bytes(b'{"synthetic":true}')
            _bundle_sources(root)
            self.assertFalse(source.exists())
            self.assertEqual(b"synthetic native bytes", native.read_bytes())
            self.assertEqual(b'{"synthetic":true}', resource.read_bytes())
            with zipfile.ZipFile(root / "parser-sources.zip") as archive:
                self.assertEqual(wire, archive.read("torch/nn/declared.py"))
            index = json.loads((root / "parser-source-index.json").read_bytes())
            self.assertEqual(
                [{"path": "torch/nn/declared.py", "sha256": hashlib.sha256(wire).hexdigest(), "bytes": len(wire)}],
                index["files"],
            )

    def test_empty_upstream_source_is_preserved(self):
        sys.path.insert(0, str(REPO / "tools"))
        from document_parser_runtime_build import _bundle_sources

        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            source = root / "torch/__init__.py"
            source.parent.mkdir()
            source.write_bytes(b"")
            _bundle_sources(root)

            class Loader:
                path = str(source)

                def get_source(self, fullname):
                    return None

            install_source_loader(root, Loader)
            self.assertEqual("", Loader().get_source("torch"))
            self.assertFalse(source.exists())

    def test_archive_identity_does_not_replace_member_identity(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            self.bundle(root)
            index_path = root / "parser-source-index.json"
            index = json.loads(index_path.read_bytes())
            index["files"][0]["sha256"] = "0" * 64
            index_path.write_text(json.dumps(index))

            class Loader:
                path = str(root / "torch/synthetic.py")

                def get_source(self, fullname):
                    return None

            install_source_loader(root, Loader)
            with self.assertRaisesRegex(SourceBundleError, "^parser-source-bundle-invalid$"):
                Loader().get_source("torch.synthetic")


if __name__ == "__main__":
    unittest.main()
