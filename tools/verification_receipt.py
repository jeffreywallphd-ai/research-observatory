#!/usr/bin/env python3
"""Opt-in, fresh-only receipts for one isolated, pure-stdlib test workload.

This is local producer-asserted diagnostic evidence, not an attestation, task
approval, native proof or Wave qualification. Executable/DLL identities are
recorded, but the installed stdlib/OS dependency closure is not authenticated;
therefore this pilot deliberately cannot consume or reuse prior PASS receipts.
The three selected source files execute from captured memory, never live paths.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from build_manifest import windows_path_locks

SELECTED_FILES = (
    "tools/governance_kernel.py",
    "tools/governance_receipt.py",
    "tests/foundation/test_governance_receipt.py",
)
TEST_FILE = SELECTED_FILES[2]
CONFIG_FILES = (".python-version", "runtime-versions.json", "pyproject.toml", "uv.lock")
HELPER_FILES = ("tools/build_manifest.py",)
SPEC_PATH = "verification/receipt-specs/governance-receipt-unit.json"
RUNNER_PATH = "tools/verification_receipt.py"
REPORT_ROOT = "artifacts/tmp/verification-receipts"
GIT_RUN = subprocess.run
PILOT_SPEC: dict[str, Any] = {
    "schemaVersion": "1.0",
    "scope": "governance-receipt-unit",
    "kind": "deterministic-unit-pilot",
    "files": list(SELECTED_FILES),
    "testFile": TEST_FILE,
    "configFiles": list(CONFIG_FILES),
    "pythonFlags": ["-I", "-S", "-B"],
    "timeoutSeconds": 30,
    "reusePolicy": "disabled-incomplete-runtime-closure",
}

# Shared literally by the producer and child; its executing bytes are bound in
# workerSha256. No account name, runtime path or ambient environment is emitted.
RUNTIME_CODE = r"""
def runtime_facts():
    import hashlib, os, platform, sys
    from pathlib import Path
    def digest_file(path):
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    facts = {
        "implementation": sys.implementation.name,
        "version": list(sys.version_info[:3]),
        "versionBuildSha256": hashlib.sha256(sys.version.encode()).hexdigest(),
        "executableSha256": digest_file(sys.executable),
        "baseExecutableSha256": digest_file(getattr(sys, "_base_executable", sys.executable)),
        "processImageSha256": None,
        "pythonDllSha256": None,
        "platform": {"system": platform.system(), "release": platform.release(),
                     "version": platform.version(), "machine": platform.machine()},
        "stdlibAndOsClosureAuthenticated": False,
    }
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        # platform.machine() on Windows consults ambient processor environment
        # variables. Read the OS architecture instead; the child does not inherit
        # those variables or any other unrelated user environment.
        system_info = ctypes.create_string_buffer(64)
        architecture = kernel.GetNativeSystemInfo
        architecture.argtypes = (wintypes.LPVOID,)
        architecture.restype = None
        architecture(system_info)
        processor = int.from_bytes(system_info.raw[:2], "little")
        facts["platform"]["machine"] = {0: "x86", 9: "AMD64", 12: "ARM64"}.get(processor, "unknown")
        locate = kernel.GetModuleFileNameW
        locate.argtypes = (wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD)
        locate.restype = wintypes.DWORD
        for handle, field in ((None, "processImageSha256"), (sys.dllhandle, "pythonDllSha256")):
            buffer = ctypes.create_unicode_buffer(32768)
            size = locate(handle, buffer, len(buffer))
            if not size or size >= len(buffer):
                raise OSError("runtime identity unavailable")
            facts[field] = digest_file(Path(buffer.value))
    return facts
"""

WORKER_CODE = (
    RUNTIME_CODE
    + r"""
import base64, contextlib, hashlib, io, json, sys, types, unittest
from pathlib import Path

def main():
    payload = json.load(sys.stdin)
    expected = ["tools/governance_kernel.py", "tools/governance_receipt.py",
                "tests/foundation/test_governance_receipt.py"]
    if list(payload["files"]) != expected:
        raise ValueError("unexpected input inventory")
    sources = {}
    for relative in expected:
        record = payload["files"][relative]
        content = base64.b64decode(record["base64"], validate=True)
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError("snapshot digest mismatch")
        sources[relative] = content
    transcript = io.StringIO()
    with contextlib.redirect_stdout(transcript), contextlib.redirect_stderr(transcript):
        for relative, name in ((expected[0], "governance_kernel"),
                               (expected[1], "governance_receipt"),
                               (expected[2], "receipt_pilot_tests")):
            module = types.ModuleType(name)
            module.__file__ = str(Path.cwd() / "memory-snapshot" / relative)
            sys.modules[name] = module
            exec(compile(sources[relative], module.__file__, "exec"), module.__dict__)
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules["receipt_pilot_tests"])
        def ids(node):
            if isinstance(node, unittest.TestSuite):
                return [item for child in node for item in ids(child)]
            return [node.id()]
        test_ids = ids(suite)
        result = unittest.TextTestRunner(stream=transcript, verbosity=1).run(suite)
    successful = (result.wasSuccessful() and result.testsRun > 0 and not result.skipped
                  and not result.expectedFailures and not result.unexpectedSuccesses)
    document = {
        "schemaVersion": "1.0", "successful": successful, "testsRun": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "expectedFailures": len(result.expectedFailures), "unexpectedSuccesses": len(result.unexpectedSuccesses),
        "testIdsSha256": hashlib.sha256(json.dumps(sorted(test_ids)).encode()).hexdigest(),
        "transcriptSha256": hashlib.sha256(transcript.getvalue().encode()).hexdigest(),
        "snapshotDigestMatched": True,
        "flags": {"isolated": sys.flags.isolated, "noSite": sys.flags.no_site,
                  "noBytecode": sys.dont_write_bytecode},
        "runtime": runtime_facts(),
    }
    print(json.dumps(document, sort_keys=True))
    return 0 if successful else 1

try:
    code = main()
except Exception as error:
    print(json.dumps({"workerError": type(error).__name__}))
    code = 2
raise SystemExit(code)
"""
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def canonical_directory(path: Path) -> Path:
    """Reject links/junctions, including an existing ancestor of a destination."""
    absolute = path.absolute()
    if absolute.resolve(strict=True) != absolute:
        raise ValueError("noncanonical directory")
    for current in (absolute, *absolute.parents):
        information = current.lstat()
        if not stat.S_ISDIR(information.st_mode) or (
            getattr(information, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("linked or non-directory ancestor")
    return absolute


def safe_read(repo: Path, relative: str) -> bytes:
    parsed = PurePosixPath(relative)
    if (
        parsed.is_absolute()
        or ":" in relative
        or "\\" in relative
        or ".." in parsed.parts
        or parsed.as_posix() != relative
    ):
        raise ValueError("unsafe input path")
    target = repo.joinpath(*parsed.parts)
    canonical_directory(target.parent)
    before = target.lstat()
    if not stat.S_ISREG(before.st_mode) or (
        getattr(before, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise ValueError("input must be a regular nonlinked file")
    if target.resolve(strict=True) != target or before.st_size > 16 * 1024 * 1024:
        raise ValueError("invalid input file boundary")
    payload = target.read_bytes()
    after = target.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or target.resolve(strict=True) != target:
        raise ValueError("input changed during read")
    return payload


def runtime_identity() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec(RUNTIME_CODE, namespace)
    result: dict[str, Any] = namespace["runtime_facts"]()
    return result


def environment_binding() -> dict[str, Any]:
    return {
        "inheritedKeys": ["SYSTEMROOT"] if "SYSTEMROOT" in os.environ else [],
        "systemRootSha256": digest(os.environ["SYSTEMROOT"].encode()) if "SYSTEMROOT" in os.environ else None,
        "TEMP": "{attempt}/temp",
        "TMP": "{attempt}/temp",
    }


def git_binding(repo: Path, snapshot: dict[str, bytes]) -> dict[str, Any]:
    """Observe exact-root Git and exact selected blobs, never inventory contents.

    Raw-byte correspondence is deliberately conservative about checkout filters:
    differently normalized bytes remain a mismatch, not an inferred clean claim.
    Observed Git provenance does not establish independent approval of a receipt.
    """
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0"})
    executable = shutil.which("git", path=environment.get("PATH", ""))
    if executable is None:
        return {"observed": False, "reason": "git-executable-unavailable"}

    def command(*arguments: str) -> subprocess.CompletedProcess[bytes]:
        return GIT_RUN(
            [
                executable,
                "--no-replace-objects",
                "--no-optional-locks",
                "-c",
                f"safe.directory={repo}",
                "-C",
                str(repo),
                *arguments,
            ],
            env=environment,
            capture_output=True,
            check=False,
            timeout=10,
        )

    try:
        top = command("rev-parse", "--show-toplevel")
        if top.returncode:
            return {"observed": False, "reason": "git-root-unavailable"}
        if Path(os.fsdecode(top.stdout.strip())).resolve() != repo:
            return {"observed": False, "reason": "not-exact-git-root"}
        head = command("rev-parse", "--verify", "HEAD^{commit}")
        commit = head.stdout.decode("ascii").strip()
        if head.returncode or len(commit) != 40 or any(item not in "0123456789abcdef" for item in commit):
            return {"observed": False, "reason": "commit-unavailable"}
        branch = command("symbolic-ref", "--quiet", "HEAD")
        reference = branch.stdout.decode("utf-8").strip() if branch.returncode == 0 else None
        listing = command("ls-tree", "-z", commit, "--", *snapshot)
        if listing.returncode:
            return {"observed": False, "reason": "selected-blobs-unavailable"}
        entries = {}
        for entry in listing.stdout.split(b"\0"):
            if not entry:
                continue
            header, raw_path = entry.split(b"\t", 1)
            mode, kind, object_id = header.decode("ascii").split()
            relative = raw_path.decode("utf-8")
            if relative not in snapshot or kind != "blob" or mode not in ("100644", "100755"):
                raise ValueError("unexpected selected Git entry")
            entries[relative] = object_id
        records = []
        for relative, payload in snapshot.items():
            selected_blob_id = entries.get(relative)
            blob = command("cat-file", "blob", selected_blob_id) if selected_blob_id else None
            records.append(
                {
                    "path": relative,
                    "blob": selected_blob_id,
                    "rawBytesMatchCommit": blob is not None and blob.returncode == 0 and blob.stdout == payload,
                }
            )
        return {
            "observed": True,
            "executableSha256": digest(Path(executable).read_bytes()),
            "head": commit,
            "branch": reference,
            "selectedInputs": records,
            "allSelectedRawBytesMatchCommit": all(item["rawBytesMatchCommit"] for item in records),
            "trust": "local-producer-observation-not-independent-approval",
        }
    except OSError, ValueError, UnicodeError, subprocess.TimeoutExpired:
        return {"observed": False, "reason": "git-observation-unavailable"}


def capture_inputs(repo: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    repo = canonical_directory(repo)
    snapshot = {
        relative: safe_read(repo, relative)
        for relative in (*SELECTED_FILES, *CONFIG_FILES, *HELPER_FILES, SPEC_PATH, RUNNER_PATH)
    }
    if json.loads(snapshot[SPEC_PATH]) != PILOT_SPEC:
        raise ValueError("unsupported closed-input specification")
    observed_git = git_binding(repo, snapshot)
    if (repo / ".git").exists() and not observed_git["observed"]:
        raise ValueError("Git metadata exists but exact-root provenance is unavailable")
    document: dict[str, Any] = {
        "files": [{"path": relative, "sha256": digest(value)} for relative, value in snapshot.items()],
        "workerSha256": digest(WORKER_CODE.encode()),
        "argv": ["{bound-python}", "-I", "-S", "-B", "-c", "{bound-worker}"],
        "cwd": "{isolated-attempt}",
        "environment": environment_binding(),
        "runtime": runtime_identity(),
        "producerGit": observed_git,
        "thirdPartyWorkerDependencies": [],
        "snapshotStorage": "captured-memory-passed-over-stdin",
        "scope": PILOT_SPEC["scope"],
    }
    document["fingerprint"] = digest(json_bytes(document))
    return document, snapshot


def create_attempt(repo: Path) -> Path:
    cursor = canonical_directory(repo)
    for part in PurePosixPath(REPORT_ROOT).parts:
        cursor /= part
        cursor.mkdir(exist_ok=True)
        canonical_directory(cursor)
    return canonical_directory(Path(tempfile.mkdtemp(prefix="attempt-", dir=cursor)))


def directory_chain(root: Path, parent: Path) -> list[Path]:
    root = canonical_directory(root)
    parent = canonical_directory(parent)
    relative = parent.relative_to(root)
    chain = [root]
    for part in relative.parts:
        chain.append(chain[-1] / part)
    return chain


def publish_json(destination: Path, value: dict[str, Any], *, root: Path | None = None) -> None:
    """Publish one new record; neither old receipts nor partial attempts are overwritten.

    A same-directory exclusive temporary file is fsynced, then hard-linked to
    its final name. Linking refuses an occupied name on Windows and POSIX.
    Filesystems without hard-link support fail closed and retain the pending
    record. This local publication is not Windows-account isolation.
    """
    parent = canonical_directory(destination.parent)
    with windows_path_locks(directory_chain(root or parent, parent), directories=True):
        canonical_directory(parent)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("receipt destination occupied")
        encoded = json_bytes(value)
        pending = parent / (destination.name + ".pending")
        with pending.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        canonical_directory(parent)
        with windows_path_locks([pending], directories=False):
            if pending.read_bytes() != encoded:
                raise ValueError("pending receipt changed before publication")
            os.link(pending, destination)
            if destination.read_bytes() != encoded:
                raise ValueError("published receipt differs from prepared bytes")
        pending.unlink()


def read_completed_attempt(attempt: Path) -> dict[str, Any]:
    """Check local delivery completeness, NOT authenticity, acceptance or reuse."""
    attempt = canonical_directory(attempt)
    if len(attempt.parents) < 4:
        raise ValueError("attempt must be in the dedicated receipt root")
    root = attempt.parents[3]
    if attempt.relative_to(root).as_posix() != f"{REPORT_ROOT}/{attempt.name}":
        raise ValueError("attempt must be in the dedicated receipt root")
    with windows_path_locks(directory_chain(root, attempt), directories=True):
        paths = [attempt / name for name in ("started.json", "receipt.json", "delivery.json")]
        with windows_path_locks(paths, directories=False):
            started = json.loads(safe_read(attempt, "started.json"))
            encoded = safe_read(attempt, "receipt.json")
            result = json.loads(encoded)
            delivery = json.loads(safe_read(attempt, "delivery.json"))
    if (
        not isinstance(result, dict)
        or not isinstance(started, dict)
        or not isinstance(delivery, dict)
        or result.get("requiresDelivery") is not True
        or result.get("documentType") != "verification-execution-receipt"
        or delivery.get("documentType") != "verification-receipt-delivery"
        or started.get("documentType") != "verification-receipt-attempt"
        or started.get("status") != "STARTED"
        or any(item.get("attemptId") != attempt.name for item in (started, result, delivery))
        or delivery.get("receiptSha256") != digest(encoded)
        or result.get("authority") != "diagnostic-evidence-only"
        or result.get("producerTrust") != "local-producer-asserted"
        or result.get("reuse") != {"eligible": False, "reason": "runtime-closure-incomplete"}
    ):
        raise ValueError("incomplete or inconsistent local receipt delivery")
    return result


def valid_child(document: Any, expected_runtime: dict[str, Any], returncode: int) -> bool:
    fields = {
        "schemaVersion",
        "successful",
        "testsRun",
        "failures",
        "errors",
        "skipped",
        "expectedFailures",
        "unexpectedSuccesses",
        "testIdsSha256",
        "transcriptSha256",
        "snapshotDigestMatched",
        "flags",
        "runtime",
    }
    if not isinstance(document, dict) or set(document) != fields or document["schemaVersion"] != "1.0":
        return False
    for key in ("testsRun", "failures", "errors", "skipped", "expectedFailures", "unexpectedSuccesses"):
        if type(document[key]) is not int or not 0 <= document[key] <= 10000:
            return False
    for key in ("testIdsSha256", "transcriptSha256"):
        value = document[key]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            return False
    expected_success = document["testsRun"] > 0 and all(
        document[key] == 0 for key in ("failures", "errors", "skipped", "expectedFailures", "unexpectedSuccesses")
    )
    return (
        type(document["successful"]) is bool
        and document["successful"] == expected_success
        and returncode == (0 if expected_success else 1)
        and document["snapshotDigestMatched"] is True
        and document["flags"] == {"isolated": 1, "noSite": 1, "noBytecode": True}
        and document["runtime"] == expected_runtime
    )


def run_pilot(
    repo: Path, *, reuse_requested: bool = False, clock: Callable[[], float] = time.monotonic
) -> tuple[int, dict[str, Any], Path]:
    start = clock()
    attempt = create_attempt(repo)
    destination = attempt / "receipt.json"
    started = {
        "schemaVersion": "1.0",
        "documentType": "verification-receipt-attempt",
        "attemptId": attempt.name,
        "status": "STARTED",
        "scope": PILOT_SPEC["scope"],
        "startedAt": dt.datetime.now(dt.UTC).isoformat(),
    }
    publish_json(attempt / "started.json", started, root=repo)
    result: dict[str, Any] = {
        **started,
        "documentType": "verification-execution-receipt",
        "status": "INVALID_INPUT",
        "execution": "not-run",
        "authority": "diagnostic-evidence-only",
        "producerTrust": "local-producer-asserted",
        "requiresDelivery": True,
        "reuse": {"eligible": False, "reason": "runtime-closure-incomplete"},
        "inputs": None,
        "child": None,
        "exitCode": None,
        "outputDigests": None,
        "timing": {"snapshotSeconds": 0.0, "childSeconds": 0.0},
        "cost": {"credits": None, "money": None, "tokenUsage": None, "source": "unavailable"},
        "limitations": [
            "No authenticated complete stdlib/OS dependency closure or cross-run reuse.",
            "No independently attested producer or implicit Git candidate binding.",
            "No native, performance, full-profile, Wave, or release qualification.",
            "Local isolated-source execution, not an operating-system security sandbox.",
        ],
    }
    code = 2
    try:
        if reuse_requested:
            result["status"] = "REUSE_UNAVAILABLE"
        else:
            snapshot_start = clock()
            inputs, snapshot = capture_inputs(repo)
            result["inputs"] = inputs
            result["timing"]["snapshotSeconds"] = round(clock() - snapshot_start, 6)
            payload = {
                "files": {
                    relative: {
                        "base64": base64.b64encode(snapshot[relative]).decode(),
                        "sha256": digest(snapshot[relative]),
                    }
                    for relative in SELECTED_FILES
                }
            }
            temporary = attempt / "temp"
            temporary.mkdir()
            environment = {"TEMP": str(temporary), "TMP": str(temporary)}
            if "SYSTEMROOT" in os.environ:
                environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
            child_start = clock()
            result["execution"] = "fresh"
            try:
                completed = subprocess.run(
                    [sys.executable, "-I", "-S", "-B", "-c", WORKER_CODE],
                    cwd=attempt,
                    env=environment,
                    input=json.dumps(payload).encode(),
                    capture_output=True,
                    check=False,
                    timeout=PILOT_SPEC["timeoutSeconds"],
                )
            finally:
                result["timing"]["childSeconds"] = round(clock() - child_start, 6)
            result["exitCode"] = completed.returncode
            result["outputDigests"] = {
                "stdoutSha256": digest(completed.stdout),
                "stderrSha256": digest(completed.stderr),
            }
            try:
                child = json.loads(completed.stdout)
            except ValueError, UnicodeDecodeError:
                child = None
            if not valid_child(child, inputs["runtime"], completed.returncode):
                result["status"] = "INVALID_CHILD_RESULT"
            else:
                result["child"] = child
                result["status"] = "PASS" if child["successful"] else "FAIL"
                code = 0 if child["successful"] else 1
            try:
                after, _ = capture_inputs(repo)
            except OSError, ValueError:
                after = None
            if after != inputs:
                result["status"] = "INPUT_DRIFT"
                code = 2
    except subprocess.TimeoutExpired:
        result["status"] = "TIMEOUT"
    except KeyboardInterrupt:
        result["status"] = "CANCELLED"
    except OSError:
        result["execution"] = "not-run"
        result["status"] = "SPAWN_FAILED" if result["inputs"] is not None else "INVALID_INPUT"
    except ValueError, TypeError:
        result["status"] = "INVALID_INPUT"
    result["timing"]["totalBeforePublicationSeconds"] = round(clock() - start, 6)
    result["timing"]["publicationTiming"] = "measured-separately-in-delivery.json"
    result["finishedAt"] = dt.datetime.now(dt.UTC).isoformat()
    publication_start = clock()
    try:
        publish_json(destination, result, root=repo)
        publication_seconds = clock() - publication_start
        publish_json(
            attempt / "delivery.json",
            {
                "schemaVersion": "1.0",
                "documentType": "verification-receipt-delivery",
                "attemptId": attempt.name,
                "receiptSha256": digest(json_bytes(result)),
                "receiptPublicationSeconds": round(publication_seconds, 6),
                "totalThroughReceiptPublicationSeconds": round(clock() - start, 6),
                "excludes": "delivery-record-publication",
            },
            root=repo,
        )
        if read_completed_attempt(attempt) != result:
            raise ValueError("completed delivery changed")
    except OSError, ValueError, KeyboardInterrupt:
        return 2, {**result, "status": "PUBLICATION_FAILED"}, destination
    return code, result, destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--reuse-receipt", help="Reserved refusal: reuse is not supported by this fresh-only pilot.")
    args = parser.parse_args()
    repo = args.repo.absolute()
    try:
        code, result, path = run_pilot(repo, reuse_requested=args.reuse_receipt is not None)
    except OSError, ValueError, KeyboardInterrupt:
        print(json.dumps({"status": "ATTEMPT_UNAVAILABLE", "reason": "no-safe-published-attempt"}))
        return 2
    print(
        json.dumps(
            {"status": result["status"], "execution": result["execution"], "receipt": path.relative_to(repo).as_posix()}
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
