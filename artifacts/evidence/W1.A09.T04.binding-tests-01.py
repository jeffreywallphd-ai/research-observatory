"""Focused R01 replay; all real mutation is confined to retained dummy Git repos."""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).absolute().parents[2]
HELPER = REPO / "artifacts/evidence/W1.A09.T04.final-binding-01.py"
spec = importlib.util.spec_from_file_location("final_binding", HELPER)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(tempfile.mkdtemp(prefix="W1.A09.T04.binding-tests-", dir=REPO / "artifacts/tmp"))
        cls.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        # Synthetic test data, never user data or the real repository index.
        for name, data in {
            ".gitattributes": b"* text=auto\n",
            "valid.txt": b"original\n",
            "mutable.txt": b"original\n",
            "assume.txt": b"original\n",
            "skip.txt": b"original\n",
            "selected-report.json": b'{"ok": false}\n',
            "valid-report.json": b'{"ok": true}\n',
            "binary.dat": b"\x00original\r\n",
            "synthetic.exe": b"synthetic bytes, never executed\n",
        }.items():
            (cls.repo / name).write_bytes(data)
        cls.git("init", "--quiet")
        cls.git("add", "--", ".gitattributes", "valid.txt", "assume.txt", "skip.txt",
                "selected-report.json", "valid-report.json", "binary.dat", "mutable.txt", "synthetic.exe")
        cls.git("-c", "user.name=Synthetic fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--quiet", "-m", "Synthetic candidate")
        cls.candidate = cls.git("rev-parse", "HEAD").decode().strip()
        cls.git("update-index", "--assume-unchanged", "assume.txt")
        cls.git("update-index", "--skip-worktree", "skip.txt")
        for name in ("assume.txt", "skip.txt"):
            (cls.repo / name).write_bytes(b"modified\n")
        (cls.repo / "selected-report.json").write_bytes(b'{"ok": true}\n')
        # Explicit CRLF worktree representation must preserve Git text identity.
        (cls.repo / "valid.txt").write_bytes(b"original\r\n")
        (cls.repo / "hardlink-original.txt").write_bytes(b"synthetic linked input\n")
        os.link(cls.repo / "hardlink-original.txt", cls.repo / "hardlink-alias.txt")
        print(f"Retained synthetic fixture: {cls.repo.relative_to(REPO).as_posix()}")

    @classmethod
    def git(cls, *args):
        return subprocess.check_output(["git", *args], cwd=cls.repo, env=cls.env, stderr=subprocess.PIPE)

    def setUp(self):
        self.root_patch = patch.object(helper, "REPO", self.repo)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_excluded_aliases_are_denied_before_any_filesystem_lookup(self):
        # Every protected spelling is a string-only/mock case; no real lookup.
        aliases = [
            "artifacts/evidence/W1.A04.B00.json",
            "artifacts/./evidence/W1.A04.B00.json",
            "ARTIFACTS/EVIDENCE/w1.a04.b00.JSON",
            "artifacts\\evidence\\W1.A04.B00.json",
            "artifacts/evidence/W1.A04.B00.json.",
            "artifacts/evidence/W1.A04.B00.json ",
            "./artifacts/evidence/W1.A04.B00.json",
            "artifacts//evidence/W1.A04.B00.json",
            "artifacts/evidence/W1.A04.B00.json:stream",
            "artifacts/evidence/../evidence/W1.A04.B00.json",
            "C:/dummy/input.txt", "/dummy/input.txt", "NUL", "dir/COM1.txt",
            "dir/short~1.json", "dir/control\n.json", "",
        ]
        for name in aliases:
            with (
                self.subTest(name=name),
                patch.object(Path, "resolve", return_value=self.repo / "valid.txt") as resolve,
                patch.object(Path, "lstat") as metadata,
                patch.object(Path, "read_bytes", return_value=b"dummy") as read,
            ):
                with self.assertRaises((AssertionError, ValueError)):
                    helper.sha(name)
                resolve.assert_not_called()
                metadata.assert_not_called()
                read.assert_not_called()

    def test_mock_reparse_is_denied_without_resolving_or_reading_target(self):
        redirected = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=redirected), \
                patch.object(Path, "resolve", return_value=self.repo / "valid.txt") as resolve, \
                patch.object(Path, "read_bytes", return_value=b"dummy") as read:
            with self.assertRaises((AssertionError, ValueError)):
                helper.sha("safe-looking/input.json")
            resolve.assert_not_called()
            read.assert_not_called()

    def test_real_synthetic_hardlink_is_denied(self):
        with self.assertRaises((AssertionError, ValueError)):
            helper.sha("hardlink-alias.txt")

    def test_mock_redirect_below_valid_ancestors_denies_before_descent(self):
        original_lstat = Path.lstat
        for relative in ("pretend-directory/target.json", "pretend-file.json"):
            seen = []

            def metadata(path, seen=seen):
                seen.append(path)
                if path.name.startswith("pretend-"):
                    return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
                return original_lstat(path)

            with self.subTest(relative=relative), patch.object(Path, "lstat", metadata), \
                    patch.object(Path, "open") as opened:
                with self.assertRaises((AssertionError, ValueError)):
                    helper.sha(relative)
                opened.assert_not_called()
                self.assertFalse(any(path.name == "target.json" for path in seen))

    def test_safe_snapshot(self):
        self.assertEqual(helper.snapshot("valid.txt"), b"original\r\n")

    def test_windows_executable_extension_does_not_change_file_identity(self):
        self.assertEqual(helper.snapshot("synthetic.exe"), b"synthetic bytes, never executed\n")

    def test_valid_git_text_binary_and_report_binding(self):
        binder = helper.CandidateInputs(self.candidate)
        self.assertEqual(binder.bytes("valid.txt"), b"original\r\n")
        self.assertEqual(binder.bytes("binary.dat"), b"\x00original\r\n")
        self.assertEqual(binder.read("valid-report.json"), {"ok": True})

    def test_masked_inputs_are_rejected_independently_of_index_flags(self):
        visible = self.git("diff", "--name-only", "HEAD").decode().splitlines()
        for name in ("assume.txt", "skip.txt"):
            with self.subTest(name=name):
                self.assertNotIn(name, visible)
                with self.assertRaises((AssertionError, ValueError)):
                    helper.CandidateInputs(self.candidate).bytes(name)

    def test_changed_selected_report_is_rejected_before_json_parse(self):
        with patch.object(helper.json, "loads") as parse:
            with self.assertRaises((AssertionError, ValueError)):
                helper.CandidateInputs(self.candidate).read("selected-report.json")
            parse.assert_not_called()

    def test_unknown_untracked_input_cannot_become_a_report(self):
        with self.assertRaises((AssertionError, ValueError)):
            helper.CandidateInputs(self.candidate).read("untracked-report.json")

    def test_cached_snapshot_is_consistent_and_later_change_is_denied(self):
        binder = helper.CandidateInputs(self.candidate)
        payload = binder.bytes("mutable.txt")
        (self.repo / "mutable.txt").write_bytes(b"later synthetic edit\n")
        self.assertEqual(binder.bytes("mutable.txt"), payload)
        with self.assertRaises((AssertionError, ValueError)):
            binder.verify_unchanged()


if __name__ == "__main__":
    unittest.main(verbosity=2)
