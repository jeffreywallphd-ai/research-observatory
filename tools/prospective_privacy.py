"""Prospective Git privacy checks; existing approved history is not rewritten."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

PROTECTED = "artifacts/evidence/W1.A04.B00.json"
RAW_REPORTS = {"artifacts/bootstrap/bootstrap-report.json", "artifacts/bootstrap/setup-verification.json"}
SHA = re.compile(r"[0-9a-f]{40}")
EMAIL_LOCAL = r"A-Za-z0-9.!#$%&'*+/=?^_`{|}~-"
EMAIL = re.compile(rf"(?<![{EMAIL_LOCAL}])[{EMAIL_LOCAL}]+@[A-Za-z0-9.-]+\.[A-Za-z]{{2,}}")
PROFILE = re.compile(r"(?i)(?:[a-z]:/|(?<![\w:])/)(?:users|home|documents and settings)/([^/\s\"'<>`]+)")
WORKSPACE = re.compile(r"(?i)[a-z]:/ai-projects(?:/|\b)")
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".exe", ".dll"}
REDIRECT = {"GIT_DIR", "GIT_WORK_TREE", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_SHALLOW_FILE", "GIT_GRAFT_FILE"}


def git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *args], input=data, capture_output=True, check=False
    )
    if result.returncode:
        raise ValueError("Git input could not be verified")
    return result.stdout


def normalize(text: str) -> str:
    for _ in range(4):
        text = html.unescape(unquote(text))
        text = re.sub(r"\\u([0-9a-f]{4})", lambda m: chr(int(m[1], 16)), text, flags=re.I)
    return re.sub(r"\\+", "/", text)


def text_reasons(text: str, allowed: set[str], *, metadata: bool = False) -> set[str]:
    value = normalize(text)
    reasons = set()
    if any(m[1].casefold() not in {"researcher", "redacted-user"} for m in PROFILE.finditer(value)):
        reasons.add("personal-profile-path")
    if WORKSPACE.search(value):
        reasons.add("concrete-workspace-path")
    for email in EMAIL.findall(value):
        domain = email.rpartition("@")[2].casefold()
        safe = domain in {"users.noreply.github.com", "example.invalid"}
        if not metadata:
            safe = safe or domain in {"example.com", "example.org", "example.net", "example.test"}
            safe = safe or domain.endswith(".invalid") or email.casefold() in allowed
        if not safe:
            reasons.add("non-public-email")
    return reasons


def validate_path(path: str) -> None:
    lower = path.casefold()
    if lower == PROTECTED.casefold():
        raise ValueError("Protected witness is tracked; no content read")
    if lower.startswith((".local/", "artifacts/tmp/")):
        raise ValueError("Ignored private output is tracked")


def entries(repo: Path, commit: str | None) -> dict[str, tuple[str, str]]:
    result = {}
    args = ("ls-files", "--stage", "-z") if commit is None else ("ls-tree", "-r", "-z", commit)
    for record in git(repo, *args).split(b"\0"):
        if not record:
            continue
        fields, raw_path = record.split(b"\t", 1)
        mode, second, third = fields.decode("ascii").split()
        path = raw_path.decode("utf-8")
        validate_path(path)
        if commit is None:
            oid = second
            if third != "0":
                raise ValueError("Unmerged index is not publishable")
        else:
            oid = third
        result[path] = mode, oid
    return result


def validate_history(repo: Path, baseline: str) -> None:
    if not SHA.fullmatch(baseline):
        raise ValueError("Invalid approved baseline")
    if any(os.environ.get(key) for key in REDIRECT):
        raise ValueError("Ambient Git redirection is unsupported")
    git(repo, "rev-parse", "--verify", baseline + "^{commit}")
    if git(repo, "rev-parse", "--is-shallow-repository").strip() != b"false":
        raise ValueError("Full history is required")
    for name in ("info/grafts", "objects/info/alternates"):
        path = Path(git(repo, "rev-parse", "--git-path", name).decode().strip())
        if (path if path.is_absolute() else repo / path).exists():
            raise ValueError("Substituted history is unsupported")
    if git(repo, "for-each-ref", "--format=%(refname)", "refs/replace").strip():
        raise ValueError("Replacement history is unsupported")
    # Names only, including deleted versions. Never read the protected witness.
    if git(repo, "log", "--format=", "--name-only", baseline, "--", PROTECTED).strip():
        raise ValueError("Protected witness in baseline history; no content read")


def changed_entries(
    current: dict[str, tuple[str, str]], predecessors: list[dict[str, tuple[str, str]]]
) -> dict[str, tuple[str, str]]:
    # A merge entry must be unchanged in every parent to skip inspection.
    return {
        p: item for p, item in current.items() if not predecessors or any(old.get(p) != item for old in predecessors)
    }


def secret_scan(raw: bytes, scanner: Path, scanner_sha: str, config: Path) -> None:
    if hashlib.sha256(scanner.read_bytes()).hexdigest() != scanner_sha:
        raise ValueError("Credential scanner identity changed")
    if (config.parent / "no-suppressions").exists():
        raise ValueError("Credential suppressions are not permitted")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITLEAKS_")}
    process = subprocess.run(
        [
            str(scanner),
            "stdin",
            "--no-banner",
            "--no-color",
            "--redact=100",
            "--ignore-gitleaks-allow",
            "--gitleaks-ignore-path",
            str(config.parent / "no-suppressions"),
            "--config",
            str(config),
            "--report-format",
            "json",
            "--report-path",
            "-",
            "--log-level",
            "error",
        ],
        input=raw,
        capture_output=True,
        env=env,
        check=False,
        timeout=120,
    )
    if process.returncode:
        raise ValueError("Credential scan failed or requires review; raw values withheld")


def inspect(
    repo: Path,
    policy: dict,
    *,
    staged: bool,
    tips: list[str],
    scanner: Path,
    config: Path,
) -> dict:
    baseline = policy["baselineCommit"]
    validate_history(repo, baseline)
    allowed = {value.casefold() for value in policy["allowedContentEmails"]}
    findings = []
    payloads: list[bytes] = []
    seen: set[tuple[str, str, str]] = set()
    count = 0

    def check_tree(current: dict[str, tuple[str, str]], prior: list[dict[str, tuple[str, str]]]) -> None:
        nonlocal count
        for path, (mode, oid) in changed_entries(current, prior).items():
            identity = path, mode, oid
            if identity in seen:
                continue
            seen.add(identity)
            count += 1
            payloads.extend((path.encode("utf-8"), normalize(path).encode("utf-8")))
            reasons = text_reasons(path, allowed)
            if path.casefold() in RAW_REPORTS:
                reasons.add("raw-machine-report")
            if mode not in {"100644", "100755"}:
                reasons.add("unsupported-file-mode")
            else:
                size = int(git(repo, "cat-file", "-s", oid))
                if size > 16 * 1024 * 1024:
                    reasons.add("oversized-file-needs-review")
                else:
                    raw = git(repo, "cat-file", "blob", oid)
                    if b"\0" in raw or Path(path).suffix.lower() in BINARY:
                        reasons.add("binary-needs-privacy-review")
                    else:
                        try:
                            text = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            reasons.add("non-text-needs-privacy-review")
                        else:
                            reasons.update(text_reasons(text, allowed))
                            payloads.append(raw)
            if reasons:
                findings.append({"pathSha256": hashlib.sha256(path.encode()).hexdigest(), "reasons": sorted(reasons)})

    commits = []
    if staged:
        tree = entries(repo, None)
        prior = entries(repo, "HEAD")
        check_tree(tree, [prior])
        for role in ("AUTHOR", "COMMITTER"):
            identity = git(repo, "var", f"GIT_{role}_IDENT").decode()
            reasons = text_reasons(identity, set(), metadata=True)
            if reasons:
                findings.append({"field": role.lower(), "reasons": sorted(reasons)})
            payloads.append(identity.encode())
    else:
        for tip in tips:
            if not SHA.fullmatch(tip):
                raise ValueError("Invalid push tip")
            git(repo, "rev-parse", "--verify", tip + "^{commit}")
        commits = (
            git(repo, "rev-list", "--reverse", "--topo-order", *tips, "--not", baseline, "--").decode().splitlines()
        )
        # Complete path inventory before any new commit/blob content is read.
        trees = {commit: entries(repo, commit) for commit in commits}
        for commit in commits:
            line = git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()
            check_tree(trees[commit], [entries(repo, parent) for parent in line[1:]])
            raw = git(repo, "cat-file", "commit", commit)
            reasons = text_reasons(raw.decode("utf-8"), set(), metadata=True)
            if reasons:
                findings.append({"commit": commit, "reasons": sorted(reasons)})
            payloads.append(raw)
    if findings:
        return {"status": "FAIL", "commitsChecked": len(commits), "entriesChecked": count, "findings": findings}
    # Full new content plus metadata, not only added diff lines. No repository allowlists.
    for raw in payloads:
        secret_scan(raw, scanner, policy["scannerSha256"], config)
    return {"status": "PASS", "commitsChecked": len(commits), "entriesChecked": count, "findings": []}


def push_tips(data: str, destination: str) -> list[str]:
    tips = []
    for line in data.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError("Malformed push update")
        _, local, remote_ref, remote = fields
        if not SHA.fullmatch(local) or not SHA.fullmatch(remote) or local == "0" * 40:
            raise ValueError("Invalid push or deletion")
        if remote_ref != destination:
            raise ValueError("Push destination is not the configured backup branch")
        tips.append(local)
    return sorted(set(tips))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("staged", "push", "message"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--remote-url")
    parser.add_argument("--message", type=Path)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        if args.mode == "message":
            if args.message is None:
                raise ValueError("Commit message is required")
            message = args.message.read_bytes()
            if text_reasons(message.decode("utf-8"), set(), metadata=True):
                raise ValueError("Commit message includes private metadata")
            secret_scan(message, args.scanner.resolve(), policy["scannerSha256"], args.config.resolve())
            print("Prospective privacy: commit message passed.")
            return 0
        tips = []
        if args.mode == "push":
            if args.remote_url != policy["remoteUrl"]:
                raise ValueError("Unexpected remote URL")
            tips = push_tips(sys.stdin.read(), policy["remoteRef"])
            if not tips:
                print("Prospective privacy: no new push objects.")
                return 0
        result = inspect(
            args.repo.resolve(),
            policy,
            staged=args.mode == "staged",
            tips=tips,
            scanner=args.scanner.resolve(),
            config=args.config.resolve(),
        )
        print(json.dumps(result))
        return int(result["status"] != "PASS")
    except ValueError, OSError, KeyError, UnicodeError, subprocess.SubprocessError:
        print("Prospective privacy: blocked; inputs or new content require review. No sensitive values printed.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
