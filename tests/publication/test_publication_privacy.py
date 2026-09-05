import ast
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from publication_privacy import check, frozen_policy, metadata_findings, push_tips, text_findings


class PrivacyBoundaryTests(unittest.TestCase):
    def test_reserved_fixture_domains_and_exact_icon_token(self):
        icon = "icons/synthetic" + "@2x.png"
        self.assertTrue(text_findings(icon, set()))
        self.assertEqual(set(), text_findings(icon, {icon}))
        self.assertTrue(text_findings("icons/unreviewed" + "@2x.png", {icon}))
        for value in ("fixture@example.test", "fixture@evil.invalid"):
            self.assertEqual(set(), text_findings(value, set()))
            self.assertTrue(metadata_findings(f"author Name <{value}> 1 +0000".encode()))

    def test_long_non_email_tokens_remain_linear_and_do_not_hide_email(self):
        text = "a" * 1_000_000
        self.assertEqual(text_findings(text, set()), set())
        self.assertIn("unapproved-email-in-content", text_findings(text + "@private.test", set()))

    def test_profile_spellings_and_encoding(self):
        raw = "C:" + "/Users/" + "private-account/AppData/Local"
        variants = [
            raw,
            raw.replace("/", "\\"),
            raw.replace("/", "\\\\"),
            raw.replace("/", "%2F"),
            raw.replace("/", "%252F"),
            raw.replace("/", "\\u005c"),
            "file:///" + raw,
        ]
        for text in variants:
            with self.subTest(text_index=variants.index(text)):
                self.assertIn("personal-profile-path", text_findings(text, set()))

    def test_workspace_and_unix_paths(self):
        for text in [
            "C:" + "/ai-projects/" + "repo",
            "/home/" + "private-account/project",
            "/Users/" + "private-account/project",
        ]:
            self.assertTrue(text_findings(text, set()))

    def test_explicit_redaction_and_synthetic_fixture(self):
        for text in [
            "C:/workspace/research-observatory",
            "C:" + "/Users/" + "redacted-user/file",
            "C:" + "/Users/" + "researcher/project",
            "${USERPROFILE}/AppData",
        ]:
            self.assertEqual(set(), text_findings(text, set()))

    def test_email_content_and_metadata_are_distinct(self):
        private = "person" + "@personal.example.edu"
        self.assertIn("unapproved-email-in-content", text_findings(private, set()))
        self.assertEqual(set(), text_findings(private, {private}))
        self.assertEqual(
            {"non-public-contributor-email"}, metadata_findings(f"author Name <{private}> 1 +0000".encode())
        )
        for email in ["redacted-identity-1@example.invalid", "123+public@users.noreply.github.com"]:
            self.assertFalse(metadata_findings(f"committer Name <{email}> 1 +0000".encode()))

    def test_committed_history_and_force_added_raw_output(self):
        with tempfile.TemporaryDirectory(prefix="publication-privacy-") as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)

            git("init")
            git("config", "user.name", "Privacy fixture")
            git("config", "user.email", "fixture@example.invalid")
            file = repo / "sample.txt"
            file.write_text("C:" + "/Users/" + "private-account/file", encoding="utf-8")
            git("add", "sample.txt")
            git("commit", "-m", "Private-path fixture")
            file.write_text("safe current content", encoding="utf-8")
            git("add", "sample.txt")
            git("commit", "-m", "Clean tip does not clean history")
            result = check(repo, ["HEAD"], False, {})
            self.assertEqual("FAIL", result["status"])
            self.assertTrue(any("personal-profile-path" in finding["reasons"] for finding in result["findings"]))
            self.assertEqual("PASS", check(repo, [], True, {})["status"])
            output = repo / "artifacts/bootstrap/bootstrap-report.json"
            output.parent.mkdir(parents=True)
            output.write_text("{}", encoding="utf-8")
            git("add", "artifacts/bootstrap/bootstrap-report.json")
            self.assertTrue(
                any(
                    "raw-machine-report-must-stay-local" in finding["reasons"]
                    for finding in check(repo, [], True, {})["findings"]
                )
            )

    def test_unreviewed_binary_and_identity_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="publication-binary-") as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)

            git("init")
            git("config", "user.name", "Privacy fixture")
            git("config", "user.email", "person" + "@personal.example.edu")
            (repo / "image.png").write_bytes(b"synthetic\0binary")
            git("add", "image.png")
            result = check(repo, [], True, {})
            self.assertTrue(any("binary-needs-explicit-privacy-review" in f["reasons"] for f in result["findings"]))
            self.assertTrue(any("non-public-contributor-email" in f["reasons"] for f in result["findings"]))


class HistoryBoundaryTests(unittest.TestCase):
    def test_windows_clone_preserves_extensionless_hook_lf(self):
        self.commit_file(".gitattributes", "* text=auto\n.githooks/* text eol=lf\n")
        hook = "#!/bin/sh\nexit 0\n"
        self.commit_file(".githooks/pre-push", hook)
        with tempfile.TemporaryDirectory(prefix="publication-windows-clone-") as directory:
            clone = Path(directory) / "copy"
            subprocess.run(
                ["git", "-c", "core.autocrlf=true", "clone", "--no-local", str(self.repo), str(clone)],
                check=True,
                capture_output=True,
            )
            self.assertEqual(hook.encode(), (clone / ".githooks/pre-push").read_bytes())

    def test_synthetic_profile_exception_is_exact_blob_and_reason_only(self):
        path = "fixture.txt"
        self.commit_file(path, "/home/" + "private/paper.pdf")
        blob = self.git("rev-parse", "HEAD:" + path).decode().strip()
        policy = {"reviewedSyntheticProfileBlobs": {blob: [path]}}
        self.assertEqual("PASS", check(self.repo, ["HEAD"], False, policy)["status"])
        self.commit_file(path, "/home/" + "private/paper.pdf\nchanged")
        self.assertEqual("FAIL", check(self.repo, ["HEAD"], False, policy)["status"])
        self.commit_file(path, "/home/" + "private/paper.pdf\nreal" + "@personal.example.edu")
        updated = self.git("rev-parse", "HEAD:" + path).decode().strip()
        result = check(self.repo, [], True, {"reviewedSyntheticProfileBlobs": {updated: [path]}})
        self.assertTrue(any("unapproved-email-in-content" in item["reasons"] for item in result["findings"]))
        self.commit_file("unreviewed-path.txt", "/home/" + "private/paper.pdf")
        copied = check(self.repo, [], True, policy)
        self.assertTrue(
            any(
                item.get("object") == blob and "personal-profile-path" in item["reasons"] for item in copied["findings"]
            )
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="publication-boundary-")
        self.repo = Path(self.temporary.name)
        self.git("init")
        self.git("config", "user.name", "Privacy fixture")
        self.git("config", "user.email", "fixture@example.invalid")

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE)

    def commit_file(self, relative, content):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        self.git("add", "--", relative)
        self.git("commit", "-m", "Synthetic privacy fixture")
        return self.git("rev-parse", "HEAD").decode().strip()

    def policy(self):
        policy = {"schemaVersion": "1.0", "authority": "sanitized-publication-only", "allowedContentEmails": []}
        raw = (json.dumps(policy) + "\n").encode()
        self.commit_file(".publication-policy.json", raw.decode())
        return hashlib.sha256(raw).hexdigest(), policy

    def test_python_313_and_complete_profile_components(self):
        import publication_privacy

        ast.parse(Path(publication_privacy.__file__).read_text(encoding="utf-8"), feature_version=(3, 13))
        for name in ("researcher private-account", "redacted-user real-account"):
            self.assertIn("personal-profile-path", text_findings("C:" + "/Users/" + name + "/file", set()))
        for url in ("https://example.invalid/users/api-client", "https://example.invalid/home/documentation"):
            self.assertEqual(set(), text_findings(url, set()))
        self.assertIn("personal-profile-path", text_findings("file:///Users/" + "private-account/file", set()))

    def test_replacement_objects_do_not_hide_original_content(self):
        original = self.commit_file("sample.txt", "C:" + "/Users/" + "private-account/file")
        self.git("checkout", "--orphan", "safe-root")
        self.commit_file("sample.txt", "safe replacement")
        self.git("replace", original, "HEAD")
        self.assertEqual("FAIL", check(self.repo, [original], False, {})["status"])

    def test_every_historical_filename_alias_is_admitted_before_content(self):
        self.commit_file("sample.txt", "same safe blob")
        self.commit_file(".local/same-blob.txt", "same safe blob")
        self.git("rm", ".local/same-blob.txt")
        self.git("commit", "-m", "Remove private alias only at tip")
        with self.assertRaisesRegex(ValueError, "Private local output"):
            check(self.repo, ["HEAD"], False, {})

    def test_raw_report_is_denied_even_when_deleted_at_tip(self):
        self.commit_file("sample.txt", "safe")
        self.commit_file("artifacts/bootstrap/bootstrap-report.json", "{}")
        self.git("rm", "artifacts/bootstrap/bootstrap-report.json")
        self.git("commit", "-m", "Remove raw output only at tip")
        self.assertTrue(
            any(
                "raw-machine-report-must-stay-local" in f["reasons"]
                for f in check(self.repo, ["HEAD"], False, {})["findings"]
            )
        )

    def test_shallow_history_cannot_claim_full_history(self):
        self.commit_file("sample.txt", "safe")
        target = self.repo / "shallow"
        subprocess.check_output(
            ["git", "clone", "--depth", "1", self.repo.as_uri(), str(target)], stderr=subprocess.PIPE
        )
        with self.assertRaisesRegex(ValueError, "shallow"):
            check(target, ["HEAD"], False, {})

    def test_frozen_policy_cannot_authorize_its_own_expansion(self):
        pin, policy = self.policy()
        policy["allowedContentEmails"] = ["person" + "@personal.example.edu"]
        path = self.repo / ".publication-policy.json"
        path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        self.assertEqual([], frozen_policy(self.repo, [], True, pin)["allowedContentEmails"])
        self.git("add", ".publication-policy.json")
        with self.assertRaisesRegex(ValueError, "without updating"):
            frozen_policy(self.repo, [], True, pin)
        self.assertEqual([], frozen_policy(self.repo, ["HEAD"], False, pin)["allowedContentEmails"])

    def test_pre_push_destination_and_deletion_contract(self):
        sha, zero = "1" * 40, "0" * 40
        self.assertEqual([sha], push_tips(f"refs/heads/local {sha} refs/heads/main {zero}\n", set()))
        destination = "refs/heads/person" + "@personal.example.edu"
        with self.assertRaisesRegex(ValueError, "destination"):
            push_tips(f"refs/heads/local {sha} {destination} {zero}\n", set())
        self.assertEqual([], push_tips(f"(delete) {zero} {destination} {sha}\n", set()))
        with self.assertRaises(ValueError):
            push_tips("malformed update", set())

    def test_real_hook_receives_updates_and_enforces_pin_and_destination(self):
        import publication_privacy

        pin, _ = self.policy()
        self.git("config", "publication.approvedPolicySha256", pin)
        target = self.repo / "receiver.git"
        subprocess.check_output(["git", "init", "--bare", str(target)], stderr=subprocess.PIPE)
        command = " ".join(
            shlex.quote(value)
            for value in (Path(sys.executable).as_posix(), Path(publication_privacy.__file__).as_posix(), "--pre-push")
        )
        hook = self.repo / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\nexec " + command + "\n", encoding="utf-8", newline="\n")
        hook.chmod(0o755)

        def push(destination):
            return subprocess.run(
                ["git", "-C", str(self.repo), "push", "--dry-run", str(target), "HEAD:" + destination],
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, push("refs/heads/main").returncode)
        self.assertNotEqual(0, push("refs/heads/person" + "@personal.example.edu").returncode)
        self.git("config", "publication.approvedPolicySha256", "0" * 64)
        self.assertNotEqual(0, push("refs/heads/main").returncode)
        self.assertEqual(
            b"", subprocess.check_output(["git", "-C", str(target), "for-each-ref", "--format=%(refname)"])
        )


if __name__ == "__main__":
    unittest.main()
