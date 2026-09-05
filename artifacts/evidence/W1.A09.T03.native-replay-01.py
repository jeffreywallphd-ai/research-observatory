"""Independent, bounded replay of the corrected T03 hidden-window regression.

This advisory working-source report does not approve a task or qualify shown UI.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from desktop_app_check import tool_environment  # noqa: E402

PREFIX = "artifacts/evidence/W1.A09.T03."
REPORT = REPO / (PREFIX + "native-replay-02.json")
PICKER = "apps/desktop/src-tauri/src/directory_picker.rs"
EXPECTED_PICKER = "d92245fed1ccc744d664b9615278d1b723eb7afc2b74abf18deb2527a2b87388"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    assert not REPORT.exists(), "Never overwrite retained observations"
    assert digest(REPO / PICKER) == EXPECTED_PICKER, "Candidate changed before replay"
    environment, _, cargo = tool_environment(REPO)
    temporary = Path(tempfile.mkdtemp(prefix="t03-native-replay-", dir=REPO / "artifacts/tmp"))
    environment.update(TEMP=str(temporary), TMP=str(temporary))
    inputs = subprocess.check_output(
        ["git", "ls-files", "--", "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo",
         "apps/desktop/src-tauri/src", "apps/desktop/src-tauri/build.rs",
         "apps/desktop/src-tauri/Cargo.toml", "apps/desktop/src-tauri/tauri.conf.json",
         "apps/desktop/src-tauri/capabilities"], cwd=REPO, text=True, encoding="utf-8",
    ).splitlines()
    inputs = sorted(set([*inputs, PICKER, "tools/desktop_app_check.py",
                         PREFIX + "native-replay-01.py", PREFIX + "native-replay-01.json",
                         PREFIX + "verification-precommit-02.json"]))

    def hashes() -> dict[str, str]:
        return {name: digest(REPO / name) for name in inputs}

    def head() -> str:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()

    before, commit = hashes(), head()
    base = [str(cargo), "test", "--locked", "--offline", "-p",
            "research-observatory-desktop", "--lib"]
    commands = []
    for repeat in range(1, 4):
        commands.extend([
            (f"picker-production-{repeat}", [*base, "directory_picker"], 25),
            (f"picker-harness-{repeat}", [*base, "--features", "integration-harness",
                                         "directory_picker"], 25),
        ])
    lint = [str(cargo), "clippy", "--locked", "--offline", "-p",
            "research-observatory-desktop", "--lib"]
    commands.extend([
        ("picker-production-lib-lint", [*lint, "--", "-D", "warnings"], None),
        ("picker-harness-lib-lint", [*lint, "--features", "integration-harness",
                                    "--", "-D", "warnings"], None),
    ])
    checks = []
    started_at = datetime.now(UTC).isoformat()
    for name, command, expected in commands:
        print(f"Starting {name}", flush=True)
        started = time.monotonic()
        try:
            result = subprocess.run(command, cwd=REPO, env=environment, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=240)
            code, output = result.returncode, result.stdout + result.stderr
            output_digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
            summaries = [
                {"status": match[0], "passed": int(match[1]), "failed": int(match[2]),
                 "ignored": int(match[3]), "measured": int(match[4]), "filtered": int(match[5])}
                for match in re.findall(
                    r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; "
                    r"(\d+) measured; (\d+) filtered out;", output
                )
            ]
            # Preserve only known Rust identifier tokens: no account/path text.
            cases = [{"name": match[0], "outcome": match[1]} for match in re.findall(
                r"^test (directory_picker::[A-Za-z0-9_:]+) \.\.\. (ok|FAILED)$", output, re.M
            )]
            executed = expected is None or (
                len(summaries) == 1 and summaries[0]["passed"] == expected
                and summaries[0]["failed"] == 0 and summaries[0]["ignored"] == 0
                and len(cases) == expected and all(case["outcome"] == "ok" for case in cases)
            )
        except subprocess.TimeoutExpired:
            code, summaries, cases, executed, output_digest = -1, [], [], False, None
        check = {"name": name, "command": ["{pinned-cargo}", *command[1:]], "exitCode": code,
                 "expectedTests": expected, "testSummaries": summaries, "testCases": cases,
                 "selectionSatisfied": executed, "outputSha256": output_digest,
                 "durationSeconds": round(time.monotonic() - started, 3)}
        checks.append(check)
        print(json.dumps({"name": name, "exitCode": code, "summaries": summaries,
                          "selectionSatisfied": executed}), flush=True)
    after, final_commit = hashes(), head()
    report = {
        "taskId": "W1.A09.T03", "observer": "t03_native_replay",
        "authority": "Independent advisory verification only; not task or release approval",
        "testedWorkingTreeBase": commit, "finalWorkingTreeBase": final_commit,
        "sourceHashesBefore": before, "sourceHashesAfter": after,
        "inputsUnchanged": before == after and commit == final_commit,
        "startedAt": started_at, "completedAt": datetime.now(UTC).isoformat(),
        "checks": checks, "temporaryNamespace": temporary.relative_to(REPO).as_posix(),
        "scope": "Three repeated production and integration-harness picker subsets, and "
                 "Clippy for library targets. No examples compiled or UI driven.",
        "assessment": [
            "The test forces unrelated-message-first ordering using a handshake, then "
            "pumps to WM_CLOSE or a bounded watchdog rather than trusting the first message.",
            "Assertions still require target destruction, preserved sibling HWND, rejected "
            "foreign-STA/null requests, owner-STA close dispatch, and observed forced noise.",
            "Retained verification-precommit-02 remains adverse historical evidence.",
            "Retained native-replay-01 passed all six 25-test runs but failed expanded "
            "test-target Clippy: existing application_lock.rs tests at lines 1336 and 1346 "
            "have clippy::needless_borrow. That file has no working diff from HEAD. "
            "This report selects the task's existing library-target lint inventory; "
            "it does not claim those unrelated test lint findings were repaired.",
            "The prior full picker source bytes are not available in this review's inputs; "
            "the author's claim that the delta is test-only is not independently byte-proven.",
        ],
        "notEstablished": ["Visible Shell dismissal, renderer assets, default folder/Core "
                           "creation, release packaging, or final commit-bound disposition"],
    }
    report["ok"] = report["inputsUnchanged"] and all(
        check["exitCode"] == 0 and check["selectionSatisfied"] for check in checks
    )
    with REPORT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"ok": report["ok"], "report": REPORT.relative_to(REPO).as_posix()}), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
