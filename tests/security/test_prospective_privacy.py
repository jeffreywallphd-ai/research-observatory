"""Real Git boundary tests for prospective privacy, using synthetic data only."""

from __future__ import annotations

import copy
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
            "remoteRefs": ["refs/heads/main"],
        }
        self.reviews: dict | None = None

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
                reviews=self.reviews,
            )

    def approve_bytes(self, path: str, raw: bytes, *, binary: bool = False) -> dict:
        self.reviews = {
            "schemaVersion": "1.0",
            "documentType": "independent-artifact-privacy-review",
            "baselineCommit": self.base,
            "scannerSha256": self.policy["scannerSha256"],
            "configSha256": hashlib.sha256(installer.CONFIG).hexdigest(),
            "reviewer": "independent-fixture-reviewer",
            "implementer": "fixture-owner",
            "disposition": "approved",
            "rationale": "Exact synthetic fixture only; no actual account or credentials.",
            "artifacts": [
                {
                    "path": path,
                    "mode": "100644",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size": len(raw),
                    "binaryReviewed": binary,
                    "nonEmailTokens": [],
                    "credentialFindingFingerprints": [],
                }
            ],
        }
        return self.reviews["artifacts"][0]

    def test_exact_reviewed_binary_only_accepts_indexed_bytes_path_and_mode(self) -> None:
        raw = b"synthetic image payload\0"
        self.write("capture.png", raw.decode())
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.approve_bytes("capture.png", raw, binary=True)
        self.assertEqual("PASS", self.inspect(staged=True)["status"])
        (self.repo / "capture.png").write_bytes(b"different unstaged bytes")
        self.assertEqual("PASS", self.inspect(staged=True)["status"])
        self.git("add", "capture.png")
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.write("capture.png", raw.decode())
        self.write("copy.png", raw.decode())
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.git("rm", "--cached", "copy.png")
        self.git("update-index", "--chmod=+x", "capture.png")
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])

    def approve_retained_metadata(self, *, successor_line: int = 1) -> dict:
        parent = self.git("rev-parse", "HEAD").stdout.decode().strip()
        path = "legacy.txt"
        baseline_oid = self.git("rev-parse", self.base + ":" + path).stdout.decode().strip()
        prior_oid = self.git("rev-parse", parent + ":" + path).stdout.decode().strip()
        baseline = self.git("cat-file", "blob", baseline_oid).stdout
        prior = self.git("cat-file", "blob", prior_oid).stdout
        raw = self.git("show", ":" + path).stdout
        entry = self.approve_bytes(path, raw)
        entry["retainedMetadata"] = [
            {
                "schemaVersion": "1.0",
                "disposition": "unchanged-existing-metadata",
                "rationale": "Synthetic existing field retained at the same logical location.",
                "baselineBlob": baseline_oid,
                "baselineSha256": hashlib.sha256(baseline).hexdigest(),
                "baselineSize": len(baseline),
                "predecessorCommit": parent,
                "predecessorBlob": prior_oid,
                "predecessorSha256": hashlib.sha256(prior).hexdigest(),
                "predecessorSize": len(prior),
                "lines": [
                    {
                        "baselineLine": 1,
                        "predecessorLine": 1,
                        "successorLine": successor_line,
                        "sha256": hashlib.sha256(baseline.splitlines(keepends=True)[0]).hexdigest(),
                        "logicalLocation": "fixture.existing.metadata",
                        "unchangedLogicalLocation": True,
                    }
                ],
            }
        ]
        return entry

    def test_exact_retention_staged_index_and_push_preserve_unchanged_metadata(self) -> None:
        self.write("legacy.txt", UNSAFE_PATH + "\nstatus: updated\n")
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.approve_retained_metadata()
        self.assertEqual("PASS", self.inspect(staged=True)["status"])
        (self.repo / "legacy.txt").write_text("Unstaged unrelated bytes")
        self.assertEqual("PASS", self.inspect(staged=True)["status"])
        tip = self.commit("Retain historical metadata")
        self.assertEqual("PASS", self.inspect(tip=tip)["status"])

    def test_retention_never_admits_changed_copied_moved_or_encoded_candidates(self) -> None:
        original = UNSAFE_PATH + "\nstatus: updated\n"
        self.write("legacy.txt", original)
        self.approve_retained_metadata()
        for changed in (
            original.replace("private", "different"),
            original + UNSAFE_PATH,
            "new-field:\n" + original,
            original.replace("/", "%2f"),
        ):
            with self.subTest(changed=changed):
                self.write("legacy.txt", changed)
                self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.write("legacy.txt", original)
        self.write("copy.txt", original)
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.git("rm", "--cached", "copy.txt")
        self.git("update-index", "--chmod=+x", "legacy.txt")
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])

    def test_retention_validates_full_provenance_and_unique_raw_line_mapping(self) -> None:
        self.write("legacy.txt", UNSAFE_PATH + "\nstatus: updated\n")
        self.approve_retained_metadata()
        original = copy.deepcopy(self.reviews)
        for field, value in (
            ("baselineBlob", "0" * 40),
            ("baselineSha256", "0" * 64),
            ("baselineSize", 0),
            ("predecessorCommit", "0" * 40),
            ("predecessorBlob", "0" * 40),
            ("predecessorSha256", "0" * 64),
            ("predecessorSize", 0),
            ("disposition", "new-disclosure"),
            ("lines", []),
        ):
            with self.subTest(field=field):
                self.reviews = copy.deepcopy(original)
                assert self.reviews is not None
                self.reviews["artifacts"][0]["retainedMetadata"][0][field] = value
                with self.assertRaises(ValueError):
                    self.inspect(staged=True)
        for field, value in (
            ("baselineLine", 2),
            ("predecessorLine", 0),
            ("successorLine", 2),
            ("sha256", "0" * 64),
            ("unchangedLogicalLocation", 1),
            ("logicalLocation", ""),
        ):
            with self.subTest(field=field):
                self.reviews = copy.deepcopy(original)
                assert self.reviews is not None
                self.reviews["artifacts"][0]["retainedMetadata"][0]["lines"][0][field] = value
                with self.assertRaises(ValueError):
                    self.inspect(staged=True)
        self.reviews = copy.deepcopy(original)
        assert self.reviews is not None
        lines = self.reviews["artifacts"][0]["retainedMetadata"][0]["lines"]
        lines.append(copy.deepcopy(lines[0]))
        with self.assertRaises(ValueError):
            self.inspect(staged=True)

    def test_retention_authorization_is_parent_specific_even_for_identical_blob(self) -> None:
        self.write("legacy.txt", UNSAFE_PATH + "\nstatus: updated\n")
        self.approve_retained_metadata()
        approved = self.commit("Reviewed retained transition")
        self.assertEqual("PASS", self.inspect(tip=approved)["status"])
        self.git("rm", "legacy.txt")
        self.commit("Delete fixture field")
        self.write("legacy.txt", UNSAFE_PATH + "\nstatus: updated\n")
        tip = self.commit("Unreviewed reintroduction of identical bytes")
        with self.assertRaises(ValueError):
            self.inspect(tip=tip)

    def test_retention_cannot_mask_credentials_or_private_identity(self) -> None:
        token = "gh" + "p_" + "7F3aBc9De2Gh5Jk8Lm1Np4Qr6St0UvXyZaBc"
        self.write("legacy.txt", UNSAFE_PATH + " " + token + "\n")
        self.base = self.commit("Synthetic secret in legacy fixture")
        self.policy["baselineCommit"] = self.base
        self.write("legacy.txt", UNSAFE_PATH + " " + token + "\nstatus: updated\n")
        self.approve_retained_metadata()
        with self.assertRaisesRegex(ValueError, "Credential"):
            self.inspect(staged=True)

    def test_retention_rejects_staged_and_committed_merges(self) -> None:
        branch = self.git("branch", "--show-current").stdout.decode().strip()
        self.git("switch", "-c", "side")
        self.write("side.txt", "Safe side content")
        self.commit("Fixture side branch")
        self.git("switch", branch)
        self.write("main.txt", "Safe main content")
        self.commit("Fixture main branch")
        self.git("merge", "--no-commit", "--no-ff", "side")
        self.write("legacy.txt", UNSAFE_PATH + "\nstatus: updated\n")
        self.approve_retained_metadata()
        with self.assertRaises(ValueError):
            self.inspect(staged=True)
        tip = self.commit("Fixture merge with retained metadata")
        with self.assertRaises(ValueError):
            self.inspect(tip=tip)

    def test_retention_does_not_mask_unmapped_private_lines(self) -> None:
        self.write("legacy.txt", UNSAFE_PATH + "\n" + UNSAFE_EMAIL + "\n")
        self.approve_retained_metadata()
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])

    def test_installed_retention_receipt_allows_commit_push_and_denies_new_disclosure(self) -> None:
        remote = self.repo / "remote.git"
        self.git("init", "--bare", str(remote))
        self.policy["remoteUrl"] = remote.as_posix()
        (self.repo / ".local").mkdir(exist_ok=True)
        self.write("tools/prospective_privacy.py", (ROOT / "tools/prospective_privacy.py").read_text())
        self.write(".privacy-baseline.json", json.dumps(self.policy))
        self.base = self.commit("Fixture source before retention installation")
        self.policy["baselineCommit"] = self.base
        (self.repo / ".privacy-baseline.json").write_text(json.dumps(self.policy))
        self.write("legacy.txt", UNSAFE_PATH + "\nstatus: updated\n")
        self.approve_retained_metadata()
        review = self.repo / ".local/review.json"
        review.write_text(json.dumps(self.reviews))
        hooks = installer.prepare(self.repo, SCANNER, review, hashlib.sha256(review.read_bytes()).hexdigest())
        self.git("config", "core.hooksPath", str(hooks))
        self.git("branch", "-m", "main")
        self.git("remote", "add", "origin", remote.as_posix())
        tip = self.commit("Exact independently reviewed retained field")
        self.git("push", "origin", "main")
        published = self.git("ls-remote", "--heads", "origin").stdout
        self.assertIn(tip.encode(), published)
        self.write("legacy.txt", UNSAFE_PATH + "\nstatus: updated\n" + UNSAFE_EMAIL)
        self.assertNotEqual(0, self.git("commit", "-m", "New disclosure denied", check=False).returncode)
        self.git("-c", "core.hooksPath=" + str(self.repo / "no-hooks"), "commit", "-m", "Simulated bypass")
        self.assertNotEqual(0, self.git("push", "origin", "main", check=False).returncode)
        self.assertEqual(published, self.git("ls-remote", "--heads", "origin").stdout)

    def test_review_cannot_waive_private_text_or_identity(self) -> None:
        self.write("capture.png", UNSAFE_PATH)
        self.approve_bytes("capture.png", UNSAFE_PATH.encode(), binary=True)
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        self.write("capture.png", "safe")
        self.approve_bytes("capture.png", b"safe", binary=True)
        self.env["GIT_AUTHOR_EMAIL"] = UNSAFE_EMAIL
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])

    def test_reviewed_icon_token_does_not_exempt_new_email(self) -> None:
        icon = "icons/AppIcon-20x20" + "@" + "2x.png"
        raw = json.dumps({"input": icon}).encode()
        self.write("manifest.json", raw.decode())
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        entry = self.approve_bytes("manifest.json", raw)
        entry["nonEmailTokens"] = [icon]
        self.assertEqual("PASS", self.inspect(staged=True)["status"])
        self.write("manifest.json", raw.decode() + UNSAFE_EMAIL)
        self.assertEqual("FAIL", self.inspect(staged=True)["status"])
        entry["nonEmailTokens"] = [UNSAFE_EMAIL]
        with self.assertRaises(ValueError):
            self.inspect(staged=True)

    def test_exact_scanner_findings_and_errors_remain_closed(self) -> None:
        report = [
            {
                "RuleID": "generic-api-key",
                "StartLine": 1,
                "EndLine": 1,
                "StartColumn": 1,
                "EndColumn": 64,
                "Match": "REDACTED",
                "Secret": "REDACTED",
            }
        ]
        fingerprint = hashlib.sha256(json.dumps(report[0], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        result = subprocess.CompletedProcess([], 1, json.dumps(report).encode(), b"")
        with patch.object(guard.subprocess, "run", return_value=result):
            with self.assertRaises(ValueError):
                guard.secret_scan(b"fixture", SCANNER, self.policy["scannerSha256"], self.config)
            guard.secret_scan(b"fixture", SCANNER, self.policy["scannerSha256"], self.config, [fingerprint])
            for code, output in (
                (2, json.dumps(report).encode()),
                (1, b"bad"),
                (1, json.dumps(report + report).encode()),
                (0, json.dumps(report).encode()),
            ):
                result.returncode, result.stdout = code, output
                with self.assertRaises(ValueError):
                    guard.secret_scan(b"fixture", SCANNER, self.policy["scannerSha256"], self.config, [fingerprint])

    def test_real_digest_false_positive_needs_exact_review_and_rejects_added_secret(self) -> None:
        raw = ('api_key="' + hashlib.sha256(b"non-secret source digest").hexdigest() + '"').encode()
        self.write("digest.txt", raw.decode())
        with self.assertRaises(ValueError):
            self.inspect(staged=True)
        report = guard.credential_report(raw, SCANNER, self.policy["scannerSha256"], self.config)
        self.assertGreater(len(report), 0)
        entry = self.approve_bytes("digest.txt", raw)
        entry["credentialFindingFingerprints"] = [
            hashlib.sha256(json.dumps(f, sort_keys=True, separators=(",", ":")).encode()).hexdigest() for f in report
        ]
        self.assertEqual("PASS", self.inspect(staged=True)["status"])
        token = "gh" + "p_" + "7F3aBc9De2Gh5Jk8Lm1Np4Qr6St0UvXyZaBc"
        extended = raw + b"\n" + token.encode()
        self.write("digest.txt", extended.decode())
        entry["sha256"], entry["size"] = hashlib.sha256(extended).hexdigest(), len(extended)
        with self.assertRaises(ValueError):
            self.inspect(staged=True)

    def test_reviewed_binary_passes_real_commit_push_and_changed_image_is_denied(self) -> None:
        remote = self.repo / "remote.git"
        self.git("init", "--bare", str(remote))
        self.policy["remoteUrl"] = remote.as_posix()
        (self.repo / ".local").mkdir(exist_ok=True)
        self.write("tools/prospective_privacy.py", (ROOT / "tools/prospective_privacy.py").read_text())
        self.write(".privacy-baseline.json", json.dumps(self.policy))
        self.base = self.commit("Fixture source before installation")
        self.policy["baselineCommit"] = self.base
        (self.repo / ".privacy-baseline.json").write_text(json.dumps(self.policy))
        raw = b"synthetic image payload\0"
        self.approve_bytes("capture.png", raw, binary=True)
        review = self.repo / ".local/review.json"
        review.write_text(json.dumps(self.reviews))
        hooks = installer.prepare(self.repo, SCANNER, review, hashlib.sha256(review.read_bytes()).hexdigest())
        self.git("config", "core.hooksPath", str(hooks))
        self.git("branch", "-m", "main")
        self.git("remote", "add", "origin", remote.as_posix())
        self.git("config", "push.default", "simple")
        self.git("config", "branch.main.remote", "origin")
        self.git("config", "branch.main.merge", "refs/heads/main")
        self.write("capture.png", raw.decode())
        self.commit("Exact reviewed synthetic image")
        self.git("push")
        published = self.git("ls-remote", "--heads", "origin").stdout
        self.write("capture.png", "Changed image")
        self.git("-c", "core.hooksPath=" + str(self.repo / "no-hooks"), "commit", "-m", "Simulated bypass")
        self.assertNotEqual(0, self.git("push", check=False).returncode)
        self.assertEqual(published, self.git("ls-remote", "--heads", "origin").stdout)

    def test_installed_review_is_pinned_and_does_not_trust_live_changes(self) -> None:
        (self.repo / ".local").mkdir(exist_ok=True)
        self.write("tools/prospective_privacy.py", (ROOT / "tools/prospective_privacy.py").read_text())
        self.write(".privacy-baseline.json", json.dumps(self.policy))
        self.commit("Guard fixture")
        raw = b"synthetic image payload\0"
        self.approve_bytes("capture.png", raw, binary=True)
        review = self.repo / ".local/review.json"
        review.write_text(json.dumps(self.reviews))
        pin = hashlib.sha256(review.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            installer.prepare(self.repo, SCANNER, review, "0" * 64)
        hooks = installer.prepare(self.repo, SCANNER, review, pin)
        self.git("config", "core.hooksPath", str(hooks))
        review.write_text("{}")
        self.write("capture.png", raw.decode())
        self.assertEqual(0, self.git("commit", "-m", "Reviewed synthetic image", check=False).returncode)
        (hooks / "reviewed-artifacts.json").write_text("{}")
        self.write("safe.txt", "Safe")
        self.assertNotEqual(0, self.git("commit", "-m", "Tampered review", check=False).returncode)

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
        self.assertEqual([sha], guard.push_tips(f"refs/heads/main {sha} refs/heads/main {zero}", ["refs/heads/main"]))
        self.assertEqual(
            [sha],
            guard.push_tips(f"refs/heads/codex/test {sha} refs/heads/codex/test {zero}", self.policy["remoteRefs"]),
        )
        for data in (
            f"refs/heads/main {sha} refs/heads/main-original {zero}",
            f"refs/heads/main {zero} refs/heads/main {sha}",
            f"refs/heads/unrelated {sha} refs/heads/unrelated {zero}",
            f"refs/heads/codex/t03-unsplit-backup {sha} refs/heads/codex/t03-unsplit-backup {zero}",
            "bad",
        ):
            with self.assertRaises(ValueError):
                guard.push_tips(data, self.policy["remoteRefs"])

    def test_replacement_refs_fail(self) -> None:
        self.write("safe.txt", "Safe")
        tip = self.commit("Another commit")
        self.git("replace", self.base, tip)
        with self.assertRaisesRegex(ValueError, "Replacement"):
            self.inspect(tip=tip)

    def test_new_ref_privacy_and_credentials_are_checked_for_baseline_tip(self) -> None:
        for name in (UNSAFE_EMAIL, UNSAFE_PATH.replace(":", "%3a").replace("/", "%2f")):
            ref = "refs/heads/codex/" + name
            with self.assertRaisesRegex(ValueError, "metadata"):
                guard.push_tips(f"{ref} {self.base} {ref} {'0' * 40}", self.policy["remoteRefs"])
        policy = self.repo / "policy.json"
        policy.write_text(json.dumps(self.policy))
        token = "gh" + "p_" + "7F3aBc9De2Gh5Jk8Lm1Np4Qr6St0UvXyZaBc"
        ref = "refs/heads/codex/" + token
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/prospective_privacy.py"),
                "push",
                "--repo",
                str(self.repo),
                "--policy",
                str(policy),
                "--scanner",
                str(SCANNER),
                "--config",
                str(self.config),
                "--remote-url",
                self.policy["remoteUrl"],
            ],
            input=f"{ref} {self.base} {ref} {'0' * 40}\n".encode(),
            env=self.env,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, process.returncode)

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
        self.git("branch", "-m", "main")
        branch = "main"
        self.git("config", "push.default", "simple")
        self.git("config", f"branch.{branch}.remote", "origin")
        self.git("config", f"branch.{branch}.merge", "refs/heads/main")
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
