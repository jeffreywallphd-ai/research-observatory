"""Real Git boundary tests for prospective privacy, using synthetic data only."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import install_privacy_hooks as installer  # noqa: E402
import prospective_privacy as guard  # noqa: E402

SCANNER = ROOT / ".local/security-audit/gitleaks.exe"
UNSAFE_PATH = "C:" + "/Users/" + "actual-person/private"
UNSAFE_EMAIL = "private-person" + "@" + "real-domain.edu"


class ProspectivePrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="privacy-guard-", dir=ROOT / "artifacts/tmp")
        self.addCleanup(self.scratch.cleanup)
        self.repo = Path(self.scratch.name)
        self.env = dict(os.environ)
        for name in (*guard.REDIRECT, "GIT_INDEX_FILE", "GIT_CONFIG_COUNT"):
            self.env.pop(name, None)
        self.env.update(
            GIT_AUTHOR_NAME="Synthetic researcher",
            GIT_COMMITTER_NAME="Synthetic researcher",
            GIT_AUTHOR_EMAIL="synthetic@example.invalid",
            GIT_COMMITTER_EMAIL="synthetic@example.invalid",
        )
        self.git("init", "-q")
        self.git("config", "core.hooksPath", str(self.repo / "no-hooks"))
        self.git("config", "commit.gpgsign", "false")
        self.write("legacy.txt", UNSAFE_PATH + "\n")
        self.base = self.commit("Legacy baseline")
        self.config = self.repo / "scanner.toml"
        self.config.write_bytes(installer.CONFIG)
        self.policy: dict = {
            "baselineCommit": self.base,
            "allowedContentEmails": [],
            "scannerSha256": hashlib.sha256(SCANNER.read_bytes()).hexdigest(),
            "remoteUrl": "https://example.invalid/repo.git",
            "remoteRef": "refs/heads/backup",
        }

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env, capture_output=True, check=check)

    def write(self, name: str, text: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.git("add", "--", name)

    def commit(self, message: str) -> str:
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").stdout.decode().strip()

    def inspect(self, *, staged: bool = False, tip: str | None = None) -> dict:
        with patch.dict(os.environ, self.env, clear=True):
            return guard.inspect(
                self.repo,
                self.policy,
                staged=staged,
                tips=[tip or "0" * 40] if not staged else [],
                scanner=SCANNER,
                config=self.config,
            )

    def test_baseline_and_safe_descendant_pass(self) -> None:
        self.assertEqual("PASS", self.inspect(tip=self.base)["status"])
        self.write("safe.txt", "Use a repository-relative path.\n")
        self.assertEqual("PASS", self.inspect(staged=True)["status"])
        tip = self.commit("Safe change")
        self.assertEqual(1, self.inspect(tip=tip)["commitsChecked"])

    def test_added_encoded_and_copied_legacy_paths_fail(self) -> None:
        for content in (UNSAFE_PATH, UNSAFE_PATH.replace("/", "%2f"), UNSAFE_EMAIL):
            self.write("new.txt", content)
            self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.write("new.txt", UNSAFE_PATH + "\n")
        tip = self.commit("Copied old blob")
        self.assertEqual("FAIL", self.inspect(tip=tip)["status"])

    def test_history_removed_from_tip_still_fails(self) -> None:
        self.write("leak.txt", UNSAFE_PATH)
        self.commit("Intermediate leak")
        self.git("rm", "leak.txt")
        final = self.commit("Remove leak")
        self.assertEqual("FAIL", self.inspect(tip=final)["status"])

    def test_merge_side_parent_cannot_hide_leak(self) -> None:
        branch = self.git("branch", "--show-current").stdout.decode().strip()
        self.git("checkout", "-qb", "side")
        self.write("leak.txt", UNSAFE_EMAIL)
        self.commit("Side leak")
        self.git("checkout", branch)
        self.write("safe.txt", "Safe")
        self.commit("Main change")
        self.git("merge", "-s", "ours", "side", "-m", "Preserve tree")
        tip = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.assertEqual("FAIL", self.inspect(tip=tip)["status"])

    def test_protected_index_rejected_before_blob_reads(self) -> None:
        self.write(guard.PROTECTED, "Synthetic sentinel, not the actual repository witness")
        original = guard.git
        reads = []

        def observe(repo: Path, *args: str, data: bytes | None = None) -> bytes:
            if args[:2] == ("cat-file", "blob"):
                reads.append(args)
            return original(repo, *args, data=data)

        with patch.object(guard, "git", side_effect=observe), self.assertRaisesRegex(ValueError, "Protected"):
            self.inspect(staged=True)
        self.assertEqual([], reads)

    def test_private_output_binary_and_symlink_fail(self) -> None:
        self.write(".local/test.txt", "Private local output")
        with self.assertRaisesRegex(ValueError, "private output"):
            self.inspect(staged=True)
        self.git("rm", "--cached", ".local/test.txt")
        self.write("new.png", "not even a real image")
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.git("rm", "--cached", "new.png")
        oid = self.git("rev-parse", "HEAD:legacy.txt").stdout.decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"120000,{oid},link")
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])

    def test_metadata_and_message_checked(self) -> None:
        self.write("safe.txt", "Safe")
        self.env["GIT_AUTHOR_EMAIL"] = UNSAFE_EMAIL
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.env["GIT_AUTHOR_EMAIL"] = "synthetic@example.invalid"
        tip = self.commit("Message " + UNSAFE_PATH)
        self.assertEqual("FAIL", self.inspect(tip=tip)["status"])

    def test_wrong_scanner_and_real_synthetic_secret_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "identity"):
            guard.secret_scan(b"safe", SCANNER, "0" * 64, self.config)
        token = "gh" + "p_" + "7F3aBc9De2Gh5Jk8Lm1Np4Qr6St0UvXyZaBc"
        with self.assertRaisesRegex(ValueError, "Credential"):
            guard.secret_scan(token.encode(), SCANNER, self.policy["scannerSha256"], self.config)

    def test_secret_in_filename_is_checked(self) -> None:
        token = "gh" + "p_" + "7F3aBc9De2Gh5Jk8Lm1Np4Qr6St0UvXyZaBc"
        self.write(token + ".txt", "Innocent content")
        with self.assertRaisesRegex(ValueError, "Credential"):
            self.inspect(staged=True)
        tip = self.commit("Synthetic filename regression")
        with self.assertRaisesRegex(ValueError, "Credential"):
            self.inspect(tip=tip)

    def test_large_embedded_text_has_bounded_scan_time(self) -> None:
        started = time.monotonic()
        self.assertEqual(set(), guard.text_reasons("a" * (1024 * 1024), set()))
        self.assertLess(time.monotonic() - started, 3.0)

    def test_destinations_deletions_and_opaque_refs_fail(self) -> None:
        sha, zero = "1" * 40, "0" * 40
        self.assertEqual([sha], guard.push_tips(f"local {sha} refs/heads/backup {zero}", "refs/heads/backup"))
        for data in (
            f"local {sha} refs/heads/main {zero}",
            f"local {zero} refs/heads/backup {sha}",
            "bad",
        ):
            with self.assertRaises(ValueError):
                guard.push_tips(data, "refs/heads/backup")

    def test_replacement_refs_fail(self) -> None:
        self.write("safe.txt", "Safe")
        tip = self.commit("Another commit")
        self.git("replace", self.base, tip)
        with self.assertRaisesRegex(ValueError, "Replacement"):
            self.inspect(tip=tip)

    def test_actual_installed_hooks_allow_safe_and_block_private_commit(self) -> None:
        (self.repo / ".local").mkdir(exist_ok=True)
        self.write("tools/prospective_privacy.py", (ROOT / "tools/prospective_privacy.py").read_text())
        self.write(".privacy-baseline.json", json.dumps(self.policy))
        self.commit("Install guard source")
        hooks = installer.prepare(self.repo, SCANNER)
        self.git("config", "core.hooksPath", str(hooks))
        self.write("safe.txt", "Safe staged content")
        self.assertEqual(0, self.git("commit", "-m", "Safe commit", check=False).returncode)
        self.write("bad.txt", UNSAFE_PATH)
        self.assertNotEqual(0, self.git("commit", "-m", "Blocked commit", check=False).returncode)
        self.git("rm", "--cached", "bad.txt")
        self.write("safe.txt", "Another safe change")
        self.assertNotEqual(0, self.git("commit", "-m", UNSAFE_PATH, check=False).returncode)
        (hooks / "policy.json").write_text("{}")
        self.assertNotEqual(0, self.git("commit", "-m", "Tamper denied", check=False).returncode)

    def test_plain_push_real_remote_and_later_leak_denial(self) -> None:
        remote = self.repo / "remote.git"
        self.git("init", "--bare", str(remote))
        self.policy["remoteUrl"] = remote.as_posix()
        (self.repo / ".local").mkdir(exist_ok=True)
        self.write("tools/prospective_privacy.py", (ROOT / "tools/prospective_privacy.py").read_text())
        self.write(".privacy-baseline.json", json.dumps(self.policy))
        # The fixture policy contains its own task-local path; freeze that as
        # pre-install baseline, just as real installation freezes owner-approved history.
        self.base = self.commit("Fixture guard source")
        self.policy["baselineCommit"] = self.base
        (self.repo / ".privacy-baseline.json").write_text(json.dumps(self.policy))
        hooks = installer.prepare(self.repo, SCANNER)
        self.git("config", "core.hooksPath", str(hooks))
        self.git("remote", "add", "origin", remote.as_posix())
        branch = self.git("branch", "--show-current").stdout.decode().strip()
        self.git("config", "push.default", "upstream")
        self.git("config", f"branch.{branch}.remote", "origin")
        self.git("config", f"branch.{branch}.merge", "refs/heads/backup")
        self.git("push", "--dry-run")
        self.assertEqual(b"", self.git("ls-remote", "--heads", "origin").stdout)
        self.git("push")
        published = self.git("ls-remote", "--heads", "origin").stdout
        self.assertIn(self.base.encode(), published)
        self.write("leak.txt", UNSAFE_PATH)
        self.git("-c", "core.hooksPath=" + str(self.repo / "no-hooks"), "commit", "-m", "Simulated bypass")
        self.assertNotEqual(0, self.git("push", check=False).returncode)
        self.assertEqual(published, self.git("ls-remote", "--heads", "origin").stdout)


if __name__ == "__main__":
    unittest.main()
