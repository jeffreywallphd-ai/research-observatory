"""Actual release Tauri resource resolution with a verified, unstarted package."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tests/service"))
from core_sidecar_build import load_build_contract, verify_artifact  # noqa: E402
from test_native_project_contract import project_probe_input_hashes  # noqa: E402
from ui_conformance import confined_path  # noqa: E402


def main():
    destination = REPO / "artifacts/evidence/W1.A09.T04.resource-resolution-01.json"
    assert not destination.exists(), "Never overwrite observations"
    build_record = REPO / "artifacts/evidence/W1.A09.T04.native-builds-01.json"
    package_record = REPO / "artifacts/evidence/W1.A09.T04.packaging-production-02.json"
    builds = json.loads(build_record.read_bytes())
    package = json.loads(package_record.read_bytes())
    release = next(item for item in builds["builds"] if item["profile"] == "release")
    assert release["inputSha256"] == project_probe_input_hashes()
    native = REPO / "target/release/examples/project_contract_probe.exe"
    assert hashlib.sha256(native.read_bytes()).hexdigest() == release["executableSha256"]
    artifact = confined_path(REPO, package["artifactRoot"])
    contract = load_build_contract(REPO)
    assert not verify_artifact(artifact, package["manifest"], contract=contract)
    root = Path(tempfile.mkdtemp(prefix="t04-resource-resolution-", dir=REPO / "artifacts/tmp"))
    assert root.resolve(strict=True).parent == (REPO / "artifacts/tmp").resolve(strict=True)
    probe = root / native.name
    shutil.copyfile(native, probe)
    temporary = root / "temp"
    temporary.mkdir()
    environment = {"SYSTEMROOT": os.environ["SYSTEMROOT"], "COMSPEC": os.environ["COMSPEC"],
                   "PATH": str(Path(os.environ["SYSTEMROOT"]) / "System32"),
                   "TEMP": str(temporary), "TMP": str(temporary)}

    def observe():
        result = subprocess.run([str(probe), "--check-tauri-resource-root"], cwd=root,
                                env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, "Read-only resource probe did not complete"
        observed = json.loads(result.stdout)
        assert observed["debugAssertions"] is False and observed["readOnly"] is True
        assert observed["normalSetupInvoked"] is False and observed["coreStarted"] is False
        assert observed["resourceDirectoryMatchesExecutableParent"] is True
        return observed

    absent = observe()
    assert absent["resourceRootConstructorAccepted"] is False and absent["runtimeConfigAccepted"] is False
    assert absent["runtimeConfigError"] == "RO-CORE-NOT-PACKAGED"
    target = root / "core-sidecar"
    shutil.copytree(artifact, target)
    assert not verify_artifact(target, package["manifest"], contract=contract)
    present = observe()
    assert present["resourceRootConstructorAccepted"] is True and present["runtimeConfigAccepted"] is True
    assert present["runtimeConfigError"] is None
    assert not verify_artifact(target, package["manifest"], contract=contract)
    assert release["inputSha256"] == project_probe_input_hashes()
    assert hashlib.sha256(probe.read_bytes()).hexdigest() == release["executableSha256"]
    record = {"taskId": "W1.A09.T04", "status": "PASS_WITHIN_RELEASE_RESOURCE_SCOPE",
              "sourceBuildRecord": build_record.relative_to(REPO).as_posix(),
              "packageRecord": package_record.relative_to(REPO).as_posix(),
              "runnerSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "nativeSha256": release["executableSha256"], "all161BuildInputsUnchanged": True,
              "fixture": root.relative_to(REPO).as_posix(), "fixturesRetained": True,
              "missingPackage": absent, "verifiedProductionPackage": present,
              "packageInventoryVerifiedBeforeAndAfter": True, "system32OnlyPath": True,
              "scope": "Actual Tauri resource_dir and release runtime_config without debug fallback. "
                       "Production sidecar copied and verified, never started. No normal desktop setup, "
                       "policy, vault, WebView, sign-in or production-session qualification."}
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": record["status"], "fixture": record["fixture"]}))


if __name__ == "__main__":
    main()
