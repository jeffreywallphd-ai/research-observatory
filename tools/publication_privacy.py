#!/usr/bin/env python3
"""Fail-closed privacy checks for the sanitized publication, not W1 approval."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import threading
from functools import cache
from pathlib import Path
from urllib.parse import unquote

EXCLUDED_WITNESS = "artifacts/evidence/W1.A04.B00.json"
RAW_OUTPUTS = {
    "artifacts/bootstrap/bootstrap-report.json",
    "artifacts/bootstrap/setup-verification.json",
}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".webp", ".gif", ".zip"}
SAFE_DOMAINS = {"example.invalid", "example.com", "example.org", "example.net", "example.test"}
EMAIL_LOCAL = r"A-Za-z0-9.!#$%&'*+/=?^_`{|}~-"
# A complete local-part boundary prevents quadratic retries on long hashes or
# embedded assets without '@', while still admitting every email-shaped token.
EMAIL = re.compile(rf"(?<![{EMAIL_LOCAL}])[{EMAIL_LOCAL}]+@[A-Za-z0-9.-]+\.[A-Za-z]{{2,}}")
IDENTITY = re.compile(rb"(?m)^(?:author|committer|tagger) [^\n]*<([^>]+)>")
PROFILE = re.compile(r"(?i)[a-z]:/(?:users|documents and settings)/([^/\r\n\"'<>`]+)")
UNIX_PROFILE = re.compile(r"(?i)(?:file:/+|(?<![\w:/])/)(?:users|home)/([^/\r\n\"'<>`]+)")
WORKSPACE = re.compile(r"(?i)[a-z]:/ai-projects(?:/|\b)")
SAFE_PROFILE_NAMES = {"redacted-user", "researcher"}


def normalize(text: str) -> str:
    for _ in range(3):
        text = unquote(html.unescape(text))
    text = re.sub(r"\\u([0-9a-f]{4})", lambda match: chr(int(match.group(1), 16)), text, flags=re.I)
    return re.sub(r"\\+", "/", text)


def safe_email(email: str, *, metadata: bool = False) -> bool:
    domain = email.rpartition("@")[2].lower()
    return (
        domain == "users.noreply.github.com"
        or domain == "example.invalid"
        or (not metadata and (domain in SAFE_DOMAINS or domain.endswith(".invalid")))
    )


def text_findings(text: str, allowed_emails: set[str]) -> set[str]:
    normalized = normalize(text)
    findings: set[str] = set()
    if any(
        match.group(1).lower() not in SAFE_PROFILE_NAMES
        for pattern in (PROFILE, UNIX_PROFILE)
        for match in pattern.finditer(normalized)
    ):
        findings.add("personal-profile-path")
    if WORKSPACE.search(normalized):
        findings.add("concrete-development-workspace")
    if any(not safe_email(value) and value.lower() not in allowed_emails for value in EMAIL.findall(normalized)):
        findings.add("unapproved-email-in-content")
    return findings


def metadata_findings(data: bytes) -> set[str]:
    return {
        "non-public-contributor-email"
        for match in IDENTITY.finditer(data)
        if not safe_email(match.group(1).decode("utf-8", errors="replace"), metadata=True)
    }


def git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repo), *args], input=data, stderr=subprocess.PIPE
    )


def object_contents(repo: Path, oids: list[str]):
    if not oids:
        return
    proc = subprocess.Popen(
        ["git", "--no-replace-objects", "-C", str(repo), "cat-file", "--batch", "--buffer"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None
    writer_errors: list[Exception] = []

    def send() -> None:
        try:
            proc.stdin.write(("\n".join(oids) + "\n").encode("ascii"))
            proc.stdin.close()
        except Exception as error:
            writer_errors.append(error)

    writer = threading.Thread(target=send)
    writer.start()
    completed = False
    try:
        for expected in oids:
            parts = proc.stdout.readline().split()
            if len(parts) != 3 or parts[0].decode() != expected:
                raise ValueError("Git object boundary mismatch")
            size = int(parts[2])
            if size > 64 * 1024 * 1024:
                raise ValueError("Object exceeds bounded privacy-review size")
            data = proc.stdout.read(size)
            if len(data) != size or proc.stdout.read(1) != b"\n":
                raise ValueError("Truncated Git object")
            yield expected, parts[1].decode(), data
        writer.join(timeout=5)
        if writer.is_alive() or proc.wait(timeout=5) != 0:
            raise ValueError("Git object reader did not complete")
        completed = True
    finally:
        if not completed and proc.poll() is None:
            proc.terminate()
        writer.join(timeout=5)
        proc.wait(timeout=5)
        proc.stdout.close()
        assert proc.stderr is not None
        proc.stderr.close()
        if not proc.stdin.closed:
            proc.stdin.close()
    if writer_errors:
        raise ValueError("Git inventory stream failed")


def complete_history_names(repo: Path, refs: list[str]) -> dict[str, set[str]]:
    if git(repo, "rev-parse", "--is-shallow-repository").strip() != b"false":
        raise ValueError("Full-history privacy checks reject shallow repositories")
    for relative in ("info/grafts", "objects/info/alternates"):
        raw_path = Path(git(repo, "rev-parse", "--git-path", relative).decode().strip())
        path = raw_path if raw_path.is_absolute() else repo / raw_path
        if path.exists():
            raise ValueError("Full-history privacy checks reject grafts and object alternates")
    if os.environ.get("GIT_ALTERNATE_OBJECT_DIRECTORIES") or os.environ.get("GIT_SHALLOW_FILE"):
        raise ValueError("Ambient ancestry/object substitution is unsupported")
    oids = git(repo, "rev-list", "--objects", "--no-object-names", *refs, "--").splitlines()
    types = {}
    for record in git(repo, "cat-file", "--batch-check", data=b"\n".join(oids) + b"\n").splitlines():
        oid, kind, _ = record.split()
        types[oid.decode()] = kind.decode()
    object_size = {b"sha1": 20, b"sha256": 32}[git(repo, "rev-parse", "--show-object-format").strip()]
    trees = {}
    for oid, kind, raw in object_contents(repo, sorted(key for key, value in types.items() if value == "tree")):
        if kind != "tree":
            raise ValueError("Historical tree changed during admission")
        entries = []
        cursor = 0
        while cursor < len(raw):
            space = raw.index(b" ", cursor)
            end = raw.index(b"\0", space)
            mode = raw[cursor:space]
            name = raw[space + 1 : end].decode("utf-8")
            child = raw[end + 1 : end + 1 + object_size]
            if len(child) != object_size or "/" in name or name in {"", ".", ".."}:
                raise ValueError("Invalid historical tree entry")
            entries.append((mode, name, child.hex()))
            cursor = end + 1 + object_size
        trees[oid] = entries

    @cache
    def flatten(oid: str) -> tuple[tuple[str, str], ...]:
        result = []
        for mode, name, child in trees[oid]:
            if mode == b"40000":
                result.extend((name + "/" + path, blob) for path, blob in flatten(child))
            elif mode in {b"100644", b"100755", b"120000"} and types.get(child) == "blob":
                result.append((name, child))
            else:
                raise ValueError("Unreviewed submodule or unsupported historical mode")
        return tuple(result)

    names = {key: {""} for key, kind in types.items() if kind in {"commit", "tag"}}
    roots = set(git(repo, "log", "--format=%T", *refs, "--").decode().splitlines())
    for root in roots:
        for path, oid in flatten(root):
            names.setdefault(oid, set()).add(path)
    return names


def check(repo: Path, refs: list[str], staged: bool, policy: dict) -> dict:
    names: dict[str, set[str]] = {}
    findings: list[dict] = []
    if staged:
        for record in git(repo, "ls-files", "--stage", "-z").split(b"\0"):
            if not record:
                continue
            header, name = record.split(b"\t", 1)
            _, oid, stage = header.split()
            if stage != b"0":
                raise ValueError("Resolve unmerged index before publication")
            names.setdefault(oid.decode(), set()).add(name.decode("utf-8"))
        for role in ("AUTHOR", "COMMITTER"):
            identity = git(repo, "var", f"GIT_{role}_IDENT").decode()
            if metadata_findings((role.lower() + " " + identity).encode()):
                findings.append({"path": "[next-commit-identity]", "reasons": ["non-public-contributor-email"]})
    else:
        if not refs:
            raise ValueError("At least one explicit publication ref is required")
        for ref in refs:
            if ref.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_./-]+", ref):
                raise ValueError("Invalid explicit publication ref")
            git(repo, "rev-parse", "--verify", ref + "^{commit}")
            tip_paths = {
                value.decode("utf-8") for value in git(repo, "ls-tree", "-r", "--name-only", "-z", ref).split(b"\0")
            }
            for path in sorted(tip_paths & RAW_OUTPUTS):
                findings.append({"path": path, "reasons": ["raw-machine-report-must-stay-local"]})
        names = complete_history_names(repo, refs)
    for paths in names.values():
        if any(path.casefold() == EXCLUDED_WITNESS.casefold() for path in paths):
            raise ValueError("Protected witness present in Git inventory; no content read")
        if any(path.casefold().startswith((".local/", "artifacts/tmp/")) for path in paths):
            raise ValueError("Private local output is tracked")
    allowed_emails = {value.lower() for value in policy.get("allowedContentEmails", [])}
    approved_binary = set(policy.get("reviewedBinaryBlobIds", []))
    for paths in names.values():
        for path in paths:
            reasons = text_findings(path, allowed_emails)
            if reasons:
                findings.append(
                    {
                        "path": "[redacted-filename]",
                        "pathDigest": hashlib.sha256(path.encode()).hexdigest(),
                        "reasons": sorted(reasons),
                    }
                )
    checked = 0
    for oid, kind, data in object_contents(repo, sorted(names)):
        if kind not in {"blob", "commit", "tag"}:
            continue
        checked += 1
        paths = names[oid]
        label = sorted(paths)[0] or "[commit-or-tag-metadata]"
        if text_findings(label, allowed_emails):
            label = "[redacted-filename]"
        reasons = metadata_findings(data) if kind in {"commit", "tag"} else set()
        binary = b"\0" in data or any(Path(path).suffix.lower() in BINARY_SUFFIXES for path in paths)
        if binary:
            if oid not in approved_binary:
                reasons.add("binary-needs-explicit-privacy-review")
        else:
            try:
                reasons.update(text_findings(data.decode("utf-8"), allowed_emails))
            except UnicodeDecodeError:
                if oid not in approved_binary:
                    reasons.add("non-utf8-needs-explicit-privacy-review")
        if paths & RAW_OUTPUTS:
            reasons.add("raw-machine-report-must-stay-local")
        # A reviewed denial fixture can deliberately contain a private-looking
        # path. Its exact immutable blob is allowed, never a username or file.
        approved_profile_paths = policy.get("reviewedSyntheticProfileBlobs", {}).get(oid, [])
        if kind == "blob" and paths and paths.issubset(set(approved_profile_paths)):
            reasons.discard("personal-profile-path")
        if reasons:
            findings.append({"object": oid, "path": label, "reasons": sorted(reasons)})
    return {"status": "FAIL" if findings else "PASS", "objectsChecked": checked, "findings": findings}


def push_tips(data: str, allowed_emails: set[str]) -> list[str]:
    tips = []
    for line in data.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError("Malformed pre-push update")
        _, local_sha, remote_ref, remote_sha = fields
        if not re.fullmatch(r"[0-9a-f]{40}", local_sha) or not re.fullmatch(r"[0-9a-f]{40}", remote_sha):
            raise ValueError("Invalid pre-push object identity")
        if local_sha == "0" * 40:
            continue
        if not remote_ref.startswith("refs/") or text_findings(remote_ref, allowed_emails):
            raise ValueError("Private or invalid destination reference")
        tips.append(local_sha)
    return sorted(set(tips))


def frozen_policy(repo: Path, refs: list[str], staged: bool, expected: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Configure a reviewed publication policy fingerprint first")
    sources = [":.publication-policy.json"] if staged else [ref + ":.publication-policy.json" for ref in refs]
    policy = None
    for source in sources:
        raw = git(repo, "show", source)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Publication policy changed without updating the independently reviewed fingerprint")
        policy = json.loads(raw)
        if policy.get("schemaVersion") != "1.0" or policy.get("authority") != "sanitized-publication-only":
            raise ValueError("Missing or unsupported publication policy")
    if policy is None:
        raise ValueError("No policy-bearing publication update")
    return policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--policy-sha256")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--pre-push", action="store_true")
    mode.add_argument("--ref", action="append", default=[])
    args = parser.parse_args()
    try:
        repo = args.repo.resolve()
        refs = args.ref
        if args.pre_push:
            refs = push_tips(sys.stdin.read(), set())
            if not refs:
                print(json.dumps({"status": "PASS", "objectsChecked": 0, "findings": [], "scope": "no new objects"}))
                return 0
        for ref in refs:
            if ref.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_./-]+", ref):
                raise ValueError("Invalid publication reference")
        expected = (
            args.policy_sha256
            or git(repo, "config", "--local", "--get", "publication.approvedPolicySha256").decode().strip()
        )
        policy = frozen_policy(repo, refs, args.staged, expected)
        report = check(repo, refs, args.staged, policy)
        print(json.dumps(report, sort_keys=True))
        return int(report["status"] != "PASS")
    except (ValueError, OSError, KeyError, RecursionError, subprocess.SubprocessError):
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "Privacy check could not validate its exact inputs; raw diagnostics withheld",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
