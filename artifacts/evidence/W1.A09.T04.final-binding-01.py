"""Bind retained, explicitly selected T04 observations to the delivery candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO = Path(__file__).absolute().parents[2]
BASE = "cd4838e9c64fdbf3adb8f326781f95404a0c945d"
sys.path.insert(0, str(REPO / "tools"))
from build_manifest import windows_path_locks  # noqa: E402
from desktop_app_check import inline_product_index  # noqa: E402
from governance_kernel import paused_predecessor_record_hash  # noqa: E402


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True, encoding="utf-8").strip()


def scoped(relative: str) -> Path:
    """Lexical validation only: never resolve an untrusted spelling."""
    assert isinstance(relative, str) and relative
    assert not any(ord(c) < 32 or c in '\\:<>"|?*~' for c in relative)
    parts = relative.split("/")
    assert all(p and p not in (".", "..") and p == p.rstrip(" .") for p in parts)
    assert all(not re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])(?:\..*)?", p, re.I) for p in parts)
    assert relative.casefold() != "artifacts/evidence/w1.a04.b00.json"
    return REPO.joinpath(*parts)


def identity(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink,
            info.st_mode, getattr(info, "st_file_attributes", 0))


@contextmanager
def held_path(relative: str, *, directory: bool = False):
    path = scoped(relative)
    # Inspect top-down before descending; lstat never follows the current entry.
    # Reuse existing Windows no-delete/write guards, not a new platform adapter.
    with ExitStack() as locks:
        for entry in [*reversed(path.parents), path]:
            is_directory = entry != path or directory
            before = entry.lstat()
            assert not stat.S_ISLNK(before.st_mode) and not getattr(before, "st_file_attributes", 0) & 0x400
            assert stat.S_ISDIR(before.st_mode) if is_directory else stat.S_ISREG(before.st_mode)
            if not is_directory:
                assert before.st_nlink == 1, "Linked evidence inputs are not permitted"
            locks.enter_context(windows_path_locks([entry], directories=is_directory))
            after = entry.lstat()
            assert identity(before) == identity(after), "Input identity changed before pinning"
        yield path


def snapshot(relative: str) -> bytes:
    with held_path(relative) as path:
        before = path.lstat()
        assert before.st_size <= 128 * 1024 * 1024, "Input exceeds bounded snapshot size"
        with path.open("rb") as source:
            assert identity(os.fstat(source.fileno())) == identity(before)
            payload = source.read(128 * 1024 * 1024 + 1)
            assert identity(os.fstat(source.fileno())) == identity(before)
        assert len(payload) == before.st_size and identity(path.lstat()) == identity(before)
        return payload


def sha(relative: str) -> str:
    return hashlib.sha256(snapshot(relative)).hexdigest()


class CandidateInputs:
    """Authenticate and parse one snapshot; index flags are never proof."""

    def __init__(self, candidate: str):
        assert re.fullmatch(r"[a-f0-9]{40}", candidate)
        self.candidate = candidate
        self.tree = {}
        for record in subprocess.check_output(
            ["git", "ls-tree", "-rz", "--full-tree", candidate], cwd=REPO,
        ).split(b"\0"):
            if record:
                metadata, name = record.split(b"\t", 1)
                mode, kind, oid = metadata.decode("ascii").split()
                self.tree[name.decode("utf-8")] = (mode, kind, oid)
        self.snapshots: dict[str, bytes] = {}
        self.blobs: dict[str, str] = {}
        self.artifacts: set[str] = set()

    def bytes(self, relative: str, *, artifact: bool = False) -> bytes:
        scoped(relative)  # Deny aliases even before consulting the tree.
        if relative in self.tree:
            mode, kind, expected = self.tree[relative]
            assert kind == "blob" and mode in ("100644", "100755")
        else:
            assert artifact and (
                relative == ".venv/pyvenv.cfg"
                or relative.startswith(("apps/desktop/dist/", "apps/desktop/product-dist/"))
                or relative in {
                    "artifacts/tmp/W1.A09.T04.performance-02.json",
                    "artifacts/tmp/blind-novice-repeat-20260905-d02/runtime/project_contract_probe.exe",
                }
            ), "Input is neither a candidate file nor an explicitly qualified artifact"
            self.artifacts.add(relative)
        if relative not in self.snapshots:
            payload = snapshot(relative)
            if relative in self.tree:
                actual = subprocess.check_output(
                    ["git", f"--attr-source={self.candidate}", "hash-object", f"--path={relative}", "--stdin"],
                    cwd=REPO, input=payload,
                ).decode("ascii").strip()
                assert actual == expected, f"Snapshot differs from candidate blob: {relative}"
                self.blobs[relative] = expected
            self.snapshots[relative] = payload
        return self.snapshots[relative]

    def sha(self, relative: str) -> str:
        return hashlib.sha256(self.bytes(relative, artifact=True)).hexdigest()

    def read(self, relative: str, *, artifact: bool = False) -> dict:
        return json.loads(self.bytes(relative, artifact=artifact).decode("utf-8"))

    def canonical_text_sha(self, relative: str) -> str:
        payload = self.bytes(relative)
        payload.decode("utf-8")
        normalized = payload.replace(b"\r\n", b"\n")
        assert b"\r" not in normalized
        return hashlib.sha256(normalized).hexdigest()

    def verify_unchanged(self) -> None:
        for relative, payload in self.snapshots.items():
            assert snapshot(relative) == payload, f"Input changed during binding: {relative}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"W1\.A09\.T04\.final-binding-[0-9]{2}\.json", args.report)
    destination = REPO / "artifacts/evidence" / args.report
    head = git("rev-parse", "HEAD")
    assert git("merge-base", BASE, head) == BASE
    assert git("branch", "--show-current") == "codex/w1-windows-local-runtime"
    inputs = CandidateInputs(head)
    sha, read = inputs.sha, inputs.read
    observed_sources: dict[str, str] = {}
    selected = []

    def bind(relative: str, entries: dict[str, str]) -> None:
        assert entries
        for name, digest in entries.items():
            assert re.fullmatch(r"[a-f0-9]{64}", digest)
            assert sha(name) == digest, f"Current input differs: {name}"
            assert name not in observed_sources or observed_sources[name] == digest
            observed_sources[name] = digest
        selected.append({"report": relative, "rawSha256": sha(relative), "matchingInputs": len(entries)})

    for suffix, count in (("units-03", 15), ("native-02", 4), ("integration-02", 2)):
        relative = f"artifacts/evidence/W1.A09.T04.verification-{suffix}.json"
        report = read(relative)
        assert report["ok"] and report["inputsUnchanged"] and len(report["checks"]) == count
        assert all(c["exitCode"] == 0 and c["testSelectionSatisfied"] for c in report["checks"])
        bind(relative, report["sourceHashes"])

    relative = "artifacts/evidence/W1.A09.T04.native-builds-01.json"
    builds = read(relative)["builds"]
    assert {b["profile"] for b in builds} == {"debug", "release"}
    for build in builds:
        assert build["embeddedCommonControls6AsInvokerVerified"] and build["executablePathConfirmedByCargo"]
        bind(relative, build["inputSha256"])
    relative = "artifacts/evidence/W1.A09.T04.production-native-build-01.json"
    production = read(relative)
    assert production["productionNoHarnessBuild"] and production["inputsUnchanged"] and not production["executed"]
    bind(relative, production["inputSha256"])

    relative = "artifacts/evidence/W1.A09.T04.packaging-production-02.json"
    package = read(relative)
    assert package["status"] == "PASS_WITHIN_PACKAGING_SMOKE_SCOPE"
    assert package["inputsUnchanged"] and package["buildExitCode"] == package["configurationExitCode"] == 0
    bind(relative, package["sourceHashes"])
    relative = "artifacts/evidence/W1.A09.T04.presentation-check-01.json"
    presentation = read(relative)
    assert presentation["checkpointStatus"] == "PASS" and presentation["inputBinding"]["membershipAndBytesUnchanged"]
    bind(relative, presentation["inputBinding"]["inputFilesRawSha256"])

    performance = read("artifacts/evidence/W1.A09.T04.performance-02.json")
    assert performance == read("artifacts/tmp/W1.A09.T04.performance-02.json", artifact=True)
    assert performance["ok"] and not performance["errors"] and not performance["unexpectedRequests"]
    assert performance["methodology"]["repetitions"] == 12
    for measure in performance["measurements"].values():
        assert len(measure["samplesMs"]) == 12
        assert measure["passesAbsoluteBudget"] and measure["passesRegressionThreshold"]
    assert performance["uiComponentPerformance"]["ok"]
    assert sha(performance["fixture"]["applicationManifest"]) == performance["fixture"]["applicationManifestSha256"]
    assert sha("apps/desktop/product-dist/assets/app.js") == performance["fixture"]["runtimeSha256"]
    for item in (performance["regressionBaseline"], performance["uiComponentPerformance"]["regressionBaseline"]):
        assert sha(item["path"]) == item["sha256"]
    component = performance["uiComponentPerformance"]["fixture"]
    for key in ("benchmarkEntry", "benchmarkRunner"):
        assert inputs.canonical_text_sha(component[key]) == component[f"{key}Sha256"]
    copied_probe = "artifacts/tmp/blind-novice-repeat-20260905-d02/runtime/project_contract_probe.exe"
    assert sha(copied_probe) == next(b["executableSha256"] for b in builds if b["profile"] == "debug")

    backlog = yaml.safe_load(inputs.bytes("planning/backlog.yaml").decode("utf-8"))
    amendment = next(a for a in backlog["wave_amendments"] if a["id"] == "W1.A09")
    parent = next(a for a in backlog["wave_amendments"] if a["id"] == "W1.A08")
    prepared = read("artifacts/evidence/W1.A09.T04.return-preparation.json")
    packet = read("planning/enabler-change-requests/ECR-0008.packet.json")
    assert prepared["correctionReturn"] == amendment["correction"] == packet["authorityChain"]["pausedPredecessor"]
    assert paused_predecessor_record_hash(parent) == prepared["correctionReturn"]["recordSha256"]
    assert parent["lifecycle"]["status"] == "PAUSED"
    assert all(t["status"] == "DONE" and t["review"]["result"] == "approved" for t in amendment["tasks"][:-1])
    assert amendment["tasks"][-1]["status"] == "IN_PROGRESS"

    invariant_scopes = [
        "services/core-api/src", "packages/contracts", "packages/ui-components", "design/ui-reference",
        "verification/baselines", "apps/desktop/src", "apps/desktop/src-tauri/capabilities",
        "apps/desktop/src-tauri/src/directory_picker.rs", "apps/desktop/src-tauri/src/supervisor.rs",
        "apps/desktop/src-tauri/src/application_sign_in_policy.rs", "tools/planctl.py", "tools/taskctl.py",
        "tools/governance_kernel.py", "tools/desktop_performance_check.py", "verification-profiles.json",
        "planning/wave-amendment-approvals",
        "planning/enabler-change-requests/ECR-0008.packet.json",
    ]
    assert not git("diff", "--name-only", BASE, "HEAD", "--", *invariant_scopes)
    observed_sources["artifacts/evidence/W1.A09.T04.final-binding-01.py"] = sha(
        "artifacts/evidence/W1.A09.T04.final-binding-01.py"
    )
    tracked = set(inputs.tree)
    nontracked = set(observed_sources) - tracked
    assert all(
        name == ".venv/pyvenv.cfg" or name.startswith(("apps/desktop/dist/", "apps/desktop/product-dist/"))
        for name in nontracked
    )
    ignored = subprocess.check_output(
        ["git", "check-ignore", "-z", "--stdin"], cwd=REPO,
        input=("\0".join(sorted(nontracked)) + "\0").encode("utf-8"),
    ).decode("utf-8").rstrip("\0").split("\0")
    assert set(ignored) == nontracked
    assert inline_product_index(REPO), "Product assembly manifest must validate against current inputs"
    inputs.verify_unchanged()
    assert head == git("rev-parse", "HEAD")
    report = {
        "taskId": "W1.A09.T04", "status": "PASS", "observedAt": datetime.now(UTC).isoformat(),
        "candidateCommit": head, "baseCommit": BASE, "selectedReports": selected,
        "sourceHashes": observed_sources, "sourceInputCount": len(observed_sources),
        "currentTrackedObservedInputsMatchCommittedCandidate": True,
        "candidateBlobIds": inputs.blobs,
        "authenticatedSnapshotRawSha256": {
            name: hashlib.sha256(payload).hexdigest() for name, payload in inputs.snapshots.items()
        },
        "candidateBindingMethod": (
            "Single bounded no-follow snapshots; Git-clean hash-object stdin with candidate attributes compared "
            "directly to candidate ls-tree blobs, independent of index/stat diff. Selected reports authenticated "
            "before parsing. Raw and field-specific canonical hashes remain distinct."
        ),
        "nontrackedQualifiedArtifactAndRuntimeInputs": sorted(nontracked),
        "nontrackedInputsMatchObservedHashesAndRemainIgnored": True,
        "productAssemblyManifestValidatesCurrentInputs": True,
        "performanceCopyPreservesParsedReportAndAllSamples": True,
        "performanceBuildAndBaselineHashesMatch": True,
        "blindWorkingCopyMatchesBuiltDebugExecutableAfterNormalClose": True,
        "exactCorrectionReturnAndFrozenPausedParent": True,
        "unchangedScopeSinceT03": invariant_scopes,
        "helperRawSha256": sha("artifacts/evidence/W1.A09.T04.final-binding-01.py"),
        "limits": (
            "Mechanical binding of earlier observations, not fresh replay or independent acceptance. "
            "Original observed HEADs and dirty-performance disclosure remain unchanged. "
            "Historic helper mismatches/adverse reports remain retained. "
            "Windows guards bound each read; portable fallback detects metadata drift. "
            "Neither is hostile same-account isolation. "
            "No protected witness access, production startup, adoption, A08 activation, Wave or release approval."
        ),
    }
    with (
        held_path("artifacts/evidence", directory=True),
        destination.open("x", encoding="utf-8", newline="\n") as output,
    ):
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({"status": "PASS", "candidateCommit": head, "sourceInputCount": len(observed_sources)}))


if __name__ == "__main__":
    main()
