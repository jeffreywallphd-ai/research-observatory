"""Fresh production sidecar smoke, with retained artifacts and no runtime startup.

Only --check is executed. This is not an ordinary-vault or desktop startup test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from core_sidecar_build import build_sidecar, load_build_contract, verify_artifact  # noqa: E402
from ui_conformance import confined_path, stable_file_bytes  # noqa: E402


def source_hashes() -> dict[str, str]:
    paths = subprocess.check_output(
        ["git", "ls-files", "--", "services/core-api", "packages/contracts", "pyproject.toml",
         "uv.lock", "tools/core_sidecar_build.py", "tools/build_manifest.py", "tools/ui_conformance.py",
         "tests/packaging/test_core_sidecar_package.py"],
        cwd=REPO, text=True, encoding="utf-8",
    ).splitlines()
    paths.append(Path(__file__).relative_to(REPO).as_posix())
    return {
        name: hashlib.sha256(stable_file_bytes(REPO, confined_path(REPO, name))).hexdigest()
        for name in sorted(set(paths))
    }


def redact(value: str) -> str:
    for path, replacement in ((str(REPO), "{repo}"), (os.environ.get("USERPROFILE", ""), "{user-profile}")):
        if path:
            for spelling in (path.replace("\\", "\\\\"), path, path.replace("\\", "/")):
                value = value.replace(spelling, replacement)
    value = re.sub(r"(?m)^\t[^\r\n]+ \(S-[0-9-]+\)", "\t{local-account} ({sid})", value)
    value = re.sub(r"\bS-1-[0-9-]+\b", "{sid}", value)
    return re.sub(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"']+", "{user-profile}", value)


def run(report_name: str) -> int:
    if not re.fullmatch(r"W1\.A09\.T04\.packaging-[a-z0-9-]+\.json", report_name):
        raise ValueError("Use a new task-namespaced report basename")
    report_parent = confined_path(REPO, "artifacts/evidence")
    report = report_parent / report_name
    if report.exists() or report.is_symlink():
        raise ValueError("Never replace retained evidence")
    scratch = confined_path(REPO, "artifacts/tmp")
    output = Path(tempfile.mkdtemp(prefix="t04-production-sidecar-", dir=scratch))
    assert output.resolve(strict=True).parent == scratch and not output.is_junction()
    before = source_hashes()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    started = datetime.now(UTC).isoformat()
    command = [sys.executable, "-I", "-B", str(Path(__file__)), "--build-worker", str(output)]
    build_start = time.monotonic()
    built = subprocess.run(command, cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert built.returncode == 0, redact(built.stderr)
    payload = json.loads(built.stdout)
    manifest = payload["manifest"]
    expected_root = output / "dist" / manifest["entrypoint"].removesuffix(".exe")
    artifact = confined_path(REPO, payload["artifactRoot"])
    assert artifact == expected_root
    contract = load_build_contract(REPO)
    assert not verify_artifact(artifact, manifest, contract=contract)
    isolated_temp = output / "check-temp"
    isolated_temp.mkdir()
    environment = {
        "SYSTEMROOT": os.environ["SYSTEMROOT"], "COMSPEC": os.environ["COMSPEC"],
        "PATH": str(Path(os.environ["SYSTEMROOT"]) / "System32"),
        "TEMP": str(isolated_temp), "TMP": str(isolated_temp),
    }
    executable = artifact / manifest["entrypoint"]
    checked = subprocess.run(
        [str(executable), "--check"], cwd=isolated_temp, env=environment,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert checked.returncode == 0, redact(checked.stderr)
    configuration = json.loads(checked.stdout)
    assert configuration["status"] == "configuration-valid" and "storageMigration" not in configuration
    assert "python" not in environment["PATH"].casefold()
    assert source_hashes() == before, "Packaged Core inputs changed during verification"
    assert not verify_artifact(artifact, manifest, contract=contract)
    record = {
        "taskId": "W1.A09.T04", "status": "PASS_WITHIN_PACKAGING_SMOKE_SCOPE",
        "observedHead": head, "sourceHashes": before, "inputsUnchanged": True,
        "startedAt": started, "completedAt": datetime.now(UTC).isoformat(),
        "buildDurationSeconds": round(time.monotonic() - build_start, 3),
        "artifactRoot": artifact.relative_to(REPO).as_posix(), "fixturesRetained": True,
        "manifest": manifest, "executableSha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "configurationCheck": configuration, "configurationExitCode": checked.returncode,
        "buildCommand": [redact(item) for item in command], "buildExitCode": built.returncode,
        "buildOutput": redact(built.stderr), "checkStderr": redact(checked.stderr),
        "system32OnlyPath": True, "freshCleanBuild": True,
        "scope": "Unmodified governed production Core sidecar build/inventory and frozen --check only. "
                 "No socket, project, actor/vault initialization, application policy, desktop startup, "
                 "sign-in, signed installer or Wave approval is claimed.",
    }
    assert confined_path(REPO, "artifacts/evidence") == report_parent
    with report.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": record["status"], "report": report.relative_to(REPO).as_posix(),
                      "artifactRoot": record["artifactRoot"], "files": len(manifest["files"]),
                      "totalBytes": manifest["totalBytes"]}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--report")
    group.add_argument("--build-worker", type=Path)
    args = parser.parse_args()
    if args.build_worker is not None:
        output = args.build_worker.absolute()
        assert output.parent == REPO / "artifacts/tmp"
        assert re.fullmatch(r"t04-production-sidecar-[a-z0-9_]+", output.name)
        artifact, manifest = build_sidecar(REPO, output)
        print(json.dumps({"artifactRoot": artifact.relative_to(REPO).as_posix(), "manifest": manifest}))
        return 0
    return run(args.report)


if __name__ == "__main__":
    raise SystemExit(main())
