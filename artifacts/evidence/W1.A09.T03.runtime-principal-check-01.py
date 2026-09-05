"""Read-only Python process-principal comparison; never starts Core or storage.

Only this task-keyed, exclusively created report is written. Paths used to launch
or identify the current interpreter remain internal and are never reported.
"""

from __future__ import annotations

import argparse
import ast
import ctypes
import hashlib
import json
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
REPORT = REPO / "artifacts/evidence/W1.A09.T03.runtime-principal-check-01.json"
RUNNER = REPO / "artifacts/evidence/W1.A09.T03.default-core-check-01.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same(first: str, second: str) -> bool:
    return os.path.normcase(os.path.normpath(first)) == os.path.normcase(os.path.normpath(second))


def process_facts(expected: dict[str, str]) -> dict[str, object]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    package = kernel.GetCurrentPackageFullName
    package.argtypes = [ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    package.restype = wintypes.LONG
    length = wintypes.UINT(0)
    package_result = package(ctypes.byref(length), None)
    module_name = kernel.GetModuleFileNameW
    module_name.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    module_name.restype = wintypes.DWORD

    def image(handle: int | None) -> Path:
        buffer = ctypes.create_unicode_buffer(32768)
        count = module_name(handle, buffer, len(buffer))
        assert 0 < count < len(buffer), "process image unavailable"
        return Path(buffer.value)

    executable = image(None)
    python_dll = image(sys.dllhandle)
    return {
        "pythonVersion": ".".join(map(str, sys.version_info[:3])),
        "executableSha256": digest(Path(sys.executable)),
        "processImageSha256": digest(executable),
        "pythonDllSha256": digest(python_dll),
        "baseExecutableSha256": digest(Path(sys._base_executable)),
        "sysExecutableEqualsRequestedLauncher": same(sys.executable, expected["launcher"]),
        "processImageEqualsRequestedLauncher": same(str(executable), expected["launcher"]),
        "baseExecutableEqualsParentBase": same(sys._base_executable, expected["base"]),
        "prefixEqualsBasePrefix": same(sys.prefix, sys.base_prefix),
        "sysExecutableUsesWindowsApps": "windowsapps" in sys.executable.casefold(),
        "baseExecutableUsesWindowsApps": "windowsapps" in sys._base_executable.casefold(),
        "processImageUsesWindowsApps": "windowsapps" in str(executable).casefold(),
        "packageIdentityProbeResult": package_result,
        "packageIdentityClassification": (
            "no-package"
            if package_result == 15700
            else "package-identity-present"
            if package_result == 122
            else "unclassified"
        ),
        "flags": {
            "noUserSite": sys.flags.no_user_site,
            "safePath": sys.flags.safe_path,
            "isolated": sys.flags.isolated,
            "optimize": sys.flags.optimize,
            "noBytecode": sys.dont_write_bytecode,
        },
    }


def core_environment(temporary: Path) -> dict[str, str]:
    environment = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
    environment.update(
        {
            "TEMP": str(temporary),
            "TMP": str(temporary),
            "RO_CORE_PROFILE": "local",
            "RO_CORE_BIND_HOST": "127.0.0.1",
            "RO_CORE_BIND_PORT": "0",
            "RO_CORE_LOG_LEVEL": "INFO",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "PYTHONPATH": os.pathsep.join([str(REPO / "services/core-api/src"), str(REPO / ".venv/Lib/site-packages")]),
        }
    )
    return environment


def validate_environment_projection() -> None:
    """Compare the existing runner's one pure function, without importing it."""
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "core_environment"]
    assert len(functions) == 1
    module = ast.Module(body=functions, type_ignores=[])
    namespace = {"Path": Path, "os": os, "REPO": REPO}
    exec(compile(module, "<reviewed-core-environment-only>", "exec"), namespace)
    assert namespace["core_environment"](REPO / "artifacts/tmp") == core_environment(REPO / "artifacts/tmp")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    assert os.name == "nt" and not sys.flags.optimize
    if args.child:
        print(json.dumps(process_facts(json.loads(sys.stdin.read(65536))), sort_keys=True))
        return 0

    assert not REPORT.exists(), "diagnostic report already exists"
    venv = REPO / ".venv/Scripts/python.exe"
    assert same(sys.executable, str(venv)), "use the approved repository launcher"
    base = Path(sys._base_executable)
    before = {"helper": digest(SELF), "runner": digest(RUNNER), "venv": digest(venv), "base": digest(base)}
    validate_environment_projection()
    expected_version = json.loads((REPO / "runtime-versions.json").read_text())["runtimes"]["python"]["version"]
    parent = process_facts({"launcher": str(venv), "base": str(base)})
    children = []
    for role, launcher in (("repository-venv", venv), ("base-interpreter", base)):
        completed = subprocess.run(
            [str(launcher), "-s", "-P", "-B", str(SELF), "--child"],
            input=json.dumps({"launcher": str(launcher), "base": str(base)}),
            cwd=REPO / "artifacts/tmp",
            env=core_environment(REPO / "artifacts/tmp"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert completed.returncode == 0, "metadata-only child failed; raw output suppressed"
        facts = json.loads(completed.stdout)
        assert facts["pythonVersion"] == expected_version, "runtime pin mismatch"
        children.append(
            {"launcherRole": role, "facts": facts, "unpublishedStderrBytes": len(completed.stderr.encode("utf-8"))}
        )
    after = {"helper": digest(SELF), "runner": digest(RUNNER), "venv": digest(venv), "base": digest(base)}
    assert before == after, "diagnostic inputs changed"
    payload = {
        "status": "PASS_WITHIN_METADATA_SCOPE",
        "inputHashes": before,
        "inputsUnchanged": True,
        "expectedPythonVersion": expected_version,
        "parent": parent,
        "children": children,
        "sameLoadedPythonDllAcrossLaunchers": children[0]["facts"]["pythonDllSha256"]
        == children[1]["facts"]["pythonDllSha256"],
        "coreEnvironmentProjectionMatchesRunner": True,
        "scope": (
            "Metadata-only equivalent child launch with the runner's executable/flags/environment shape; "
            "no Core imports, service startup, storage, default-project writes, vault or security-setting reads. "
            "Existing artifacts/tmp substitutes for the fixture cwd/temp. "
            "This is not an actual --serve child or an absence-of-virtualization proof."
        ),
    }
    with REPORT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(
            json.dumps(
                {"status": "FAIL", "reason": "metadata-diagnostic-did-not-complete", "rawExceptionSuppressed": True}
            )
        )
        raise SystemExit(1) from None
