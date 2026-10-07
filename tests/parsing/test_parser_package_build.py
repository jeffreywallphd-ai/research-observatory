"""Frozen model discovery keeps package bootstrap files and selected factories."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO), str(REPO / "services/core-api/src")]

from document_parser_runtime_build import _assemble_package  # noqa: E402
from plugin_worker_runtime_build import WorkerBuildError  # noqa: E402

from workers.windows.runtime_inventory import PARSER_IMAGE_DIRECTORY  # noqa: E402


class ParserPackageBuildTests(unittest.TestCase):
    def test_selected_factory_pruning_preserves_root_module_files(self):
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            image = root / "frozen"
            models = image / "_internal/transformers/models"
            models.mkdir(parents=True)
            for name in ("__init__.py", "bootstrap.py"):
                (models / name).write_text("# Synthetic immutable module-discovery input.\n")
            selected = ("auto", "rt_detr", "rt_detr_v2", "encoder_decoder")
            for name in (*selected, "unselected_synthetic_model"):
                folder = models / name
                folder.mkdir()
                (folder / "__init__.py").write_text("# Synthetic factory source.\n")
            # Copy selection precedes native build admission. That admission is
            # deliberately unavailable in this fixture; no PE/signing occurs.
            with self.assertRaisesRegex(WorkerBuildError, "parser-native-admission-derivative-missing"):
                _assemble_package(
                    frozen_image=image,
                    source_root=root,
                    assets=root,
                    output=root / "output",
                    pe_signer=root,
                    pe_verifier=root,
                    inventory_signer=root,
                    application_public_key=root,
                )
            bundled = root / "output/package" / PARSER_IMAGE_DIRECTORY / "_internal/transformers/models"
            self.assertEqual((models / "__init__.py").read_bytes(), (bundled / "__init__.py").read_bytes())
            self.assertEqual((models / "bootstrap.py").read_bytes(), (bundled / "bootstrap.py").read_bytes())
            self.assertTrue(all((bundled / name / "__init__.py").is_file() for name in selected))
            self.assertFalse((bundled / "unselected_synthetic_model").exists())


if __name__ == "__main__":
    unittest.main()
