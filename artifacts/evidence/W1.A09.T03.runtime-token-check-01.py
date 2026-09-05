"""Read-only token/package observations around fixture-only Core startup.

Queries only this process and exact children it creates. No token identities,
credentials, paths, package names, real defaults, or security settings are read
or changed. The isolated Core creates its retained synthetic workspace vault.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location(
    "t03_token_fixture", REPO / "artifacts/evidence/W1.A09.T03.default-core-check-01.py"
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def process_classification(process_handle: int) -> dict:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    package = kernel.GetPackageFullName
    package.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    package.restype = wintypes.LONG
    length = wintypes.UINT(0)
    package_result = package(process_handle, ctypes.byref(length), None)
    open_token = advapi.OpenProcessToken
    open_token.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    open_token.restype = wintypes.BOOL
    information = advapi.GetTokenInformation
    information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    information.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    assert open_token(process_handle, 0x8, ctypes.byref(token)), "read-only process token query unavailable"

    def integer(kind: int) -> int:
        result, size = wintypes.DWORD(), wintypes.DWORD()
        assert information(token, kind, ctypes.byref(result), ctypes.sizeof(result), ctypes.byref(size))
        assert size.value == ctypes.sizeof(result)
        return result.value

    try:
        assert integer(8) == 1, "only primary process tokens are classified"
        classifications = {
            "primaryProcessToken": True,
            "appContainer": bool(integer(29)),
            "virtualizationAllowed": bool(integer(23)),
            "virtualizationEnabled": bool(integer(24)),
        }
        size = wintypes.DWORD()
        assert not information(token, 25, None, 0, ctypes.byref(size))
        assert ctypes.get_last_error() == 122 and 0 < size.value <= 256
        buffer = ctypes.create_string_buffer(size.value)
        try:
            assert information(token, 25, buffer, len(buffer), ctypes.byref(size))
            # TOKEN_MANDATORY_LABEL begins with SID_AND_ATTRIBUTES. Only the
            # integrity RID is classified; no SID bytes/string leave this call.
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
            valid = advapi.IsValidSid
            valid.argtypes = [wintypes.LPVOID]
            valid.restype = wintypes.BOOL
            assert valid(sid)
            count = advapi.GetSidSubAuthorityCount
            count.argtypes = [wintypes.LPVOID]
            count.restype = ctypes.POINTER(ctypes.c_ubyte)
            subauthority = advapi.GetSidSubAuthority
            subauthority.argtypes = [wintypes.LPVOID, wintypes.DWORD]
            subauthority.restype = ctypes.POINTER(wintypes.DWORD)
            entries = count(sid).contents.value
            assert entries > 0
            rid = subauthority(sid, entries - 1).contents.value
            classifications["integrity"] = {
                0x0: "untrusted",
                0x1000: "low",
                0x2000: "medium",
                0x2100: "medium-plus",
                0x3000: "high",
                0x4000: "system",
                0x5000: "protected",
            }.get(rid, "unclassified")
        finally:
            ctypes.memset(buffer, 0, len(buffer))
    finally:
        close(token)
    return {
        "packageIdentityProbeResult": package_result,
        "packageIdentity": "no-package"
        if package_result == 15700
        else "present"
        if package_result == 122
        else "unclassified",
        **classifications,
    }


def metadata_only_child(root: Path) -> dict:
    process = subprocess.Popen(
        [sys._base_executable, "-s", "-P", "-B", str(SELF), "--metadata-wait"],
        cwd=root,
        env=runner.core_environment(root),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert process.stdout and process.stdin and process.stderr
    observed: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=lambda: observed.put(process.stdout.readline()), daemon=True)
    reader.start()
    try:
        assert observed.get(timeout=10).strip() == "metadata-ready"
        result = process_classification(int(process._handle))
        process.stdin.write("finish\n")
        process.stdin.flush()
        assert process.wait(timeout=10) == 0
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        reader.join(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-wait", action="store_true")
    parser.add_argument("--label", choices=("agent", "user-launch"), default="agent")
    args = parser.parse_args()
    if args.metadata_wait:
        print("metadata-ready", flush=True)
        assert sys.stdin.readline().strip() == "finish"
        return 0
    assert os.name == "nt" and not sys.flags.optimize
    report = REPO / f"artifacts/evidence/W1.A09.T03.runtime-token-check-01.{args.label}.json"
    assert not report.exists(), "existing report retained"
    before = runner.hashes(native=False)
    before[SELF.relative_to(REPO).as_posix()] = hashlib.sha256(SELF.read_bytes()).hexdigest()
    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    observations = {"parent": process_classification(kernel.GetCurrentProcess())}
    with runner.DirectoryPins() as pins:
        pins.pin_chain(runner.TEMP)
        pins.pin_chain(runner.REPORTS)
        root = Path(tempfile.mkdtemp(prefix="directory-default-token-", dir=runner.TEMP))
        pins.pin_chain(root)
        observations["metadataOnlyChild"] = metadata_only_child(root)
        core = runner.ActualCore(root, pins)
        try:
            core.ready()
            observations["coreAfterStartup"] = process_classification(int(core.process._handle))
            assert core.mutations == 0
            assert core.request("GET", "/workflow-profiles/catalog")[0] == 200
            observations["coreAfterReadonlyCatalog"] = process_classification(int(core.process._handle))
        finally:
            core.stop()
        assert len(core.runtime_principals) == 1
        pins.revalidate()
        after = runner.hashes(native=False)
        after[SELF.relative_to(REPO).as_posix()] = hashlib.sha256(SELF.read_bytes()).hexdigest()
        assert before == after, "inputs changed during observation"
        payload = {
            "status": "OBSERVATION_COMPLETE",
            "inputHashes": before,
            "inputsUnchanged": True,
            "observations": observations,
            "beforeCoreImports": core.runtime_principals[0],
            "projectMutations": core.mutations,
            "fixtureRoot": root.relative_to(REPO).as_posix(),
            "fixturesRetained": True,
            "normalOwnedChildShutdown": True,
            "scope": (
                "Read-only primary-token classifications and package-presence result for this process and "
                "its owned children; no identities, names, raw token bytes or privileges are reported. "
                "Core startup uses an isolated workspace vault; no actual-default project or real user vault. "
                "No token, security policy, launch-escape flags, package activation "
                "or virtualization controls changed. "
                "These process flags are not a comprehensive filesystem-filter or absence-of-redirection proof."
            ),
            "primarySources": [
                "https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class",
                "https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation",
                "https://learn.microsoft.com/en-us/windows/win32/api/appmodel/nf-appmodel-getpackagefullname",
                "https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control",
            ],
        }
        with report.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
    print(json.dumps({key: value for key, value in payload.items() if key != "inputHashes"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({"status": "FAIL", "rawExceptionSuppressed": True}))
        raise SystemExit(1) from None
