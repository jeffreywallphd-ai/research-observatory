from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from repository_structure_check import validate_repository  # noqa: E402
from taskctl import load, save_atomic  # noqa: E402


class RepositoryStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo = Path(self.tempdir.name)
        self.manifest = json.loads((REPO / "repository-structure.json").read_text(encoding="utf-8"))
        for module in self.manifest["modules"]:
            directory = self.repo / module["path"]
            directory.mkdir(parents=True)
            (directory / "README.md").write_text(
                f"# Module\n\nOwner: {module['owner']}  \nBoundary: {module['boundary']}\n",
                encoding="utf-8",
            )
        (self.repo / "repository-structure.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_accepts_complete_documented_skeleton(self) -> None:
        self.assertEqual([], validate_repository(self.repo))

    def test_rejects_module_without_readme(self) -> None:
        (self.repo / "apps" / "desktop" / "README.md").unlink()
        errors = validate_repository(self.repo)
        self.assertIn("Module apps/desktop has no README.md", errors)

    def test_rejects_deferred_cloud_implementation_path(self) -> None:
        (self.repo / "infrastructure" / "terraform").mkdir(parents=True)
        errors = validate_repository(self.repo)
        self.assertIn(
            "Deferred implementation path must be absent: infrastructure/terraform",
            errors,
        )

    def test_rejects_tracked_binary(self) -> None:
        (self.repo / "apps" / "desktop" / "generated.exe").write_bytes(b"MZ")
        errors = validate_repository(self.repo)
        self.assertIn("Tracked generated binary is forbidden: apps/desktop/generated.exe", errors)

    def test_taskctl_does_not_serialize_runtime_slice_positions(self) -> None:
        backlog = self.repo / "minimal-backlog.yaml"
        backlog.write_text(
            "capabilities:\n"
            "- id: CAP-00\n"
            "  slices:\n"
            "  - id: CAP-00.S01\n"
            "    title: ‘Repository bootstrap’\n"
            "    tasks: []\n"
            "release_gates: []\n",
            encoding="utf-8",
        )
        data, _, slices, _, _ = load(str(backlog), validate_schema=False)
        self.assertEqual(0, slices["CAP-00.S01"]["_position"])
        save_atomic(str(backlog), data)
        serialized = backlog.read_text(encoding="utf-8")
        self.assertNotIn("_position", serialized)
        self.assertIn("‘Repository bootstrap’", serialized)
        self.assertNotIn("\\u2018", serialized)


if __name__ == "__main__":
    unittest.main()
