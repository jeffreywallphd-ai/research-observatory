"""Bind retained, explicitly selected T04 observations to the delivery candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

REPO = Path(__file__).resolve().parents[2]
BASE = "cd4838e9c64fdbf3adb8f326781f95404a0c945d"
sys.path.insert(0, str(REPO / "tools"))
from desktop_app_check import inline_product_index  # noqa: E402
from desktop_performance_check import canonical_text_sha256  # noqa: E402
from governance_kernel import paused_predecessor_record_hash  # noqa: E402


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True, encoding="utf-8").strip()


def scoped(relative: str) -> Path:
    name = PurePosixPath(relative)
    assert not name.is_absolute() and ".." not in name.parts and ":" not in relative
    assert relative != "artifacts/evidence/W1.A04.B00.json"
    path = (REPO / relative).resolve(strict=True)
    assert path.is_relative_to(REPO)
    return path


def sha(relative: str) -> str:
    return hashlib.sha256(scoped(relative).read_bytes()).hexdigest()


def read(relative: str) -> dict:
    return json.loads(scoped(relative).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"W1\.A09\.T04\.final-binding-[0-9]{2}\.json", args.report)
    destination = REPO / "artifacts/evidence" / args.report
    assert not destination.exists(), "Retain earlier observations"
    head = git("rev-parse", "HEAD")
    assert git("merge-base", BASE, head) == BASE
    assert git("branch", "--show-current") == "codex/w1-windows-local-runtime"
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
    assert performance == read("artifacts/tmp/W1.A09.T04.performance-02.json")
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
        assert canonical_text_sha256(scoped(component[key])) == component[f"{key}Sha256"]
    copied_probe = "artifacts/tmp/blind-novice-repeat-20260905-d02/runtime/project_contract_probe.exe"
    assert sha(copied_probe) == next(b["executableSha256"] for b in builds if b["profile"] == "debug")

    backlog = yaml.safe_load(scoped("planning/backlog.yaml").read_text(encoding="utf-8"))
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
    tracked = set(git("ls-files").splitlines())
    nontracked = set(observed_sources) - tracked
    assert all(
        name == ".venv/pyvenv.cfg" or name.startswith(("apps/desktop/dist/", "apps/desktop/product-dist/"))
        for name in nontracked
    )
    ignored = subprocess.check_output(
        ["git", "check-ignore", "--stdin"], cwd=REPO,
        input="\n".join(sorted(nontracked)) + "\n", text=True, encoding="utf-8",
    ).splitlines()
    assert set(ignored) == nontracked
    assert inline_product_index(REPO), "Product assembly manifest must validate against current inputs"
    assert not set(git("diff", "--name-only", "HEAD").splitlines()) & set(observed_sources)
    assert head == git("rev-parse", "HEAD")
    report = {
        "taskId": "W1.A09.T04", "status": "PASS", "observedAt": datetime.now(UTC).isoformat(),
        "candidateCommit": head, "baseCommit": BASE, "selectedReports": selected,
        "sourceHashes": observed_sources, "sourceInputCount": len(observed_sources),
        "currentTrackedObservedInputsMatchCommittedCandidate": True,
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
            "No protected witness access, production startup, adoption, A08 activation, Wave or release approval."
        ),
    }
    with destination.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({"status": "PASS", "candidateCommit": head, "sourceInputCount": len(observed_sources)}))


if __name__ == "__main__":
    main()
