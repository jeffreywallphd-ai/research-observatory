"""Actual supervised Core, protected storage and default-folder acceptance proof.

The fixture controls vault and temporary locations without replacing key providers.
No existing user vault/policy is read. Reports deliberately omit account paths.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))
TEMP = REPO / "artifacts/tmp"
REPORTS = REPO / "artifacts/evidence"
RUNTIME_METADATA_HELPER = REPORTS / "W1.A09.T03.runtime-principal-check-01.py"
CREATE_FAILURE_STAGES = {
    "Creation stopped before workflow and Research Intent authority were published.": "workflow-intent-authority",
    "Creation stopped before the staged project and canonical database were published.": "protected-storage",
    "Creation stopped before the staged project was published.": "os-staging-publication",
}
STORAGE_FAILURE_CODES = {
    "database path must be the canonical project database location": "canonical-location",
    "database parent is unavailable or redirected": "canonical-parent",
    "database file is redirected, linked, or non-regular": "canonical-file",
    "database file is not canonical": "canonical-file-name",
    "database initialization will not replace an existing entry": "existing-entry",
    "database path could not be held against replacement": "filesystem-guard-acquisition",
    "protected database runtime is unavailable": "protected-runtime",
    "protected database compatibility profile was not applied": "cipher-compatibility",
    "canonical database could not enter WAL mode": "wal-mode",
    "canonical database connection profile was not applied": "connection-profile",
    "protected database key authority is not configured": "key-unconfigured",
    "protected database key material is invalid": "key-invalid",
    "protected database key authority is unavailable": "key-unavailable",
    "protected database project identity is required": "project-identity-required",
    "database identity changed before open": "identity-before-open",
    "production profile rejected a plaintext project database": "plaintext-denied",
    "database parent identity changed during open": "parent-identity-drift",
    "database identity changed during open": "identity-drift",
    "new database identity is not exclusive": "new-identity-exclusive",
    "compiled schema does not match its reviewed fingerprint": "schema-fingerprint",
    "new database did not satisfy its integrity contract": "new-integrity",
    "new database identity changed during initialization": "new-identity-drift",
    "protected database initialization produced plaintext": "new-plaintext-denied",
}


def bounded_failure(error: BaseException) -> dict:
    """Observe fixed error categories/numeric codes only, never exception text."""
    causes = []
    current: BaseException | None = error
    for _ in range(5):
        if current is None:
            break
        name = type(current).__name__
        entry = {
            "type": name
            if name
            in {
                "ProjectLifecycleProblem",
                "StorageProblem",
                "OSError",
                "PermissionError",
                "FileNotFoundError",
                "OperationalError",
                "DatabaseError",
                "IntegrityError",
                "ValueError",
                "RuntimeError",
            }
            else "other"
        }
        for field in ("winerror", "errno", "sqlite_errorcode"):
            value = getattr(current, field, None)
            if type(value) is int:
                entry[field] = value
        if name == "StorageProblem" and len(current.args) == 1 and isinstance(current.args[0], str):
            entry["code"] = STORAGE_FAILURE_CODES.get(current.args[0], "unclassified")
        causes.append(entry)
        current = current.__cause__
    return {
        "kind": "t03-create-diagnostic",
        "stage": CREATE_FAILURE_STAGES.get(getattr(error, "detail", None), "unclassified"),
        "causes": causes,
    }


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _FileInformation(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD),
        ("created", _FileTime),
        ("accessed", _FileTime),
        ("written", _FileTime),
        ("volume", wintypes.DWORD),
        ("size_high", wintypes.DWORD),
        ("size_low", wintypes.DWORD),
        ("links", wintypes.DWORD),
        ("index_high", wintypes.DWORD),
        ("index_low", wintypes.DWORD),
    ]


_KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
_KERNEL.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
_KERNEL.CreateFileW.restype = wintypes.HANDLE
_KERNEL.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(_FileInformation)]
_KERNEL.GetFileInformationByHandle.restype = wintypes.BOOL
_KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
_KERNEL.CloseHandle.restype = wintypes.BOOL
_INVALID_HANDLE = ctypes.c_void_p(-1).value


def _open_pinned(path: Path, *, directory: bool) -> int:
    # Attribute-only handles do not enforce share-delete denial. Include
    # LIST_DIRECTORY and deny delete sharing. Directory write sharing is needed
    # for unchanged Core staged publication. This does NOT prevent a hostile
    # same-account writer from changing a directory into a reparse in place.
    handle = _KERNEL.CreateFileW(
        str(path), 0x81 if directory else 0x80000000, 0x3 if directory else 0x1, None, 3, 0x02000000 | 0x00200000, None
    )
    if handle == _INVALID_HANDLE:
        raise AssertionError("no-follow fixture handle unavailable")
    return handle


def _identity(handle: int, *, directory: bool) -> tuple[int, int]:
    information = _FileInformation()
    assert _KERNEL.GetFileInformationByHandle(handle, ctypes.byref(information)), "fixture identity unavailable"
    assert not information.attributes & 0x400, "reparse object denied"
    assert bool(information.attributes & 0x10) == directory, "unexpected object type"
    return information.volume, (information.index_high << 32) | information.index_low


class DirectoryPins:
    """Retained rename-denial handles and identity checks, not host isolation."""

    def __init__(self) -> None:
        self.entries: dict[Path, tuple[int, tuple[int, int]]] = {}

    def pin_chain(self, path: Path) -> None:
        assert path.is_absolute() and ".." not in path.parts
        for directory in (*reversed(path.parents), path):
            if directory in self.entries:
                self._check(directory)
                continue
            handle = _open_pinned(directory, directory=True)
            try:
                identity = _identity(handle, directory=True)
            except BaseException:
                _KERNEL.CloseHandle(handle)
                raise
            self.entries[directory] = (handle, identity)

    def _check(self, path: Path) -> None:
        handle, identity = self.entries[path]
        assert _identity(handle, directory=True) == identity, "held fixture identity changed"
        current = _open_pinned(path, directory=True)
        try:
            assert _identity(current, directory=True) == identity, "named fixture identity changed"
        finally:
            _KERNEL.CloseHandle(current)

    def revalidate(self) -> None:
        # Parents were inserted first, so reject an altered ancestor before
        # opening any child name beneath it.
        for path in self.entries:
            self._check(path)

    def close(self) -> None:
        for handle, _ in reversed(tuple(self.entries.values())):
            _KERNEL.CloseHandle(handle)
        self.entries.clear()

    def __enter__(self) -> DirectoryPins:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def read_database(path: Path, pins: DirectoryPins) -> bytes:
    import msvcrt

    pins.revalidate()
    pins.pin_chain(path.parent)
    try:
        handle = _open_pinned(path, directory=False)
        try:
            identity = _identity(handle, directory=False)
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            _KERNEL.CloseHandle(handle)
            raise
        with os.fdopen(descriptor, "rb") as stream:  # Owns and closes the Windows handle.
            result = stream.read()
            assert _identity(handle, directory=False) == identity, "test database identity changed"
            return result
    finally:
        pins.revalidate()


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


def report_target(path: Path) -> Path:
    candidate = path if path.is_absolute() else REPO / path
    assert ".." not in candidate.parts and candidate.parent == REPORTS, "report scope denied"
    assert re.fullmatch(
        r"W1\.A09\.T03\.default-core-(?:fresh|complete)-[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.json", candidate.name
    ), "report namespace denied"
    assert not candidate.exists(), "report already exists"
    return candidate


def publish_report(path: Path, payload: dict) -> None:
    # Recheck exact scope, then create exclusively even if another writer wins
    # after the early path check during this potentially long proof.
    path = report_target(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")


def verify_native_probe(executable: Path, build: dict) -> None:
    from test_native_project_contract import assert_project_probe_manifest

    assert hashlib.sha256(executable.read_bytes()).hexdigest() == build["executableSha256"], (
        "probe differs from bound build"
    )
    assert_project_probe_manifest(executable)


def run_native_resolver(executable: Path, build: dict) -> dict:
    verify_native_probe(executable, build)
    try:
        result = subprocess.run(
            [str(executable), "--default-parent"],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert result.returncode == 0, "native default resolver failed"
        return json.loads(result.stdout)
    finally:
        # Also check unsuccessful executions; do not accept a replaced binary
        # merely because a plausible resolver envelope was returned.
        verify_native_probe(executable, build)


def plain_directory(path: Path) -> None:
    status = path.lstat()
    assert path.is_dir() and not path.is_symlink() and not path.is_junction()
    assert not status.st_file_attributes & 0x400
    assert path.resolve(strict=True) == path


def fixture_scope(path: Path) -> None:
    # Reject outside paths before resolving, statting or reading them.
    assert path.parent == TEMP and path.name.startswith("directory-default-")
    suffix = path.name.removeprefix("directory-default-")
    assert suffix and all(char.isascii() and (char.isalnum() or char in "-_") for char in suffix)


def fixture_root(path: Path) -> Path:
    fixture_scope(path)
    for directory in (REPO, REPO / "artifacts", TEMP, path):
        plain_directory(directory)
    return path


def runtime_principal_observation() -> dict:
    """Inspect only this serving process before importing the Core composition."""
    before = hashlib.sha256(RUNTIME_METADATA_HELPER.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("t03_runtime_principal", RUNTIME_METADATA_HELPER)
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    facts = helper.process_facts({"launcher": sys._base_executable, "base": sys._base_executable})
    assert hashlib.sha256(RUNTIME_METADATA_HELPER.read_bytes()).hexdigest() == before
    return {
        "kind": "t03-runtime-principal",
        "observationPhase": "before-core-import-and-startup",
        "metadataHelperSha256": before,
        "metadataHelperUnchanged": True,
        "coreModulesAlreadyLoaded": any(
            name == "research_observatory_core" or name.startswith("research_observatory_core.") for name in sys.modules
        ),
        "facts": facts,
    }


def serve(root: Path) -> int:
    # Keep stdout's actual Core handshake untouched. Only the fixture parent's
    # bounded stderr collector receives this path-free process observation.
    print(json.dumps(runtime_principal_observation()), file=sys.stderr, flush=True)
    from research_observatory_core.config import CoreSettings
    from research_observatory_core.main import run_supervised

    root = fixture_root(root)
    from research_observatory_core import storage
    from research_observatory_core.projects import ProjectLifecycleService

    original_create = ProjectLifecycleService._create_at
    original_canonical_database = storage._canonical_database_path

    def observe_canonical_database(path, *, must_exist):
        try:
            return original_canonical_database(path, must_exist=must_exist)
        except storage.StorageProblem:
            parent = Path(path).parent
            # Observe only the staging database the synthetic create just made.
            if parent.name == "state" and parent.parent.name.startswith(".t03-default-proof-"):
                resolved = parent.resolve(strict=True)
                details = {
                    "kind": "t03-create-diagnostic",
                    "stage": "canonical-parent-observation",
                    "isDirectory": parent.is_dir(),
                    "isSymlink": parent.is_symlink(),
                    "isJunction": parent.is_junction(),
                    "resolvedEqualsNamed": resolved == parent,
                    "namedLength": len(str(parent)),
                    "resolvedLength": len(str(resolved)),
                    "namedDepth": len(parent.parts),
                    "resolvedDepth": len(resolved.parts),
                    "sameDrive": parent.drive.casefold() == resolved.drive.casefold(),
                    "sameFileIdentity": os.path.samefile(parent, resolved),
                    "resolvedUsesExtendedPrefix": str(resolved).startswith("\\\\?\\"),
                    "resolvedContainsPackageLocalCache": "packages" in [part.casefold() for part in resolved.parts]
                    and "localcache" in [part.casefold() for part in resolved.parts],
                    "baseInterpreterUsesWindowsApps": "windowsapps" in sys._base_executable.casefold(),
                    "differingComponentIndexes": [
                        i
                        for i, (a, b) in enumerate(zip(parent.parts, resolved.parts, strict=False))
                        if a.casefold() != b.casefold()
                    ],
                }
                print(json.dumps(details), file=sys.stderr, flush=True)
            raise

    storage._canonical_database_path = observe_canonical_database

    def observe_create(self, **kwargs):
        try:
            return original_create(self, **kwargs)
        except Exception as error:
            print(json.dumps(bounded_failure(error)), file=sys.stderr, flush=True)
            raise

    # Fixture-process observation only: invoke the unchanged implementation and
    # re-raise unchanged. Do not inspect paths, exception text or key material.
    ProjectLifecycleService._create_at = observe_create
    vault = root / "Research Observatory/security/profile-default"
    for directory in (root / "Research Observatory", vault.parent, vault, vault / "records"):
        if directory.exists() or directory.is_symlink() or directory.is_junction():
            plain_directory(directory)
    return run_supervised(CoreSettings(), profile_vault_root=vault)


class ActualCore:
    def __init__(self, root: Path, pins: DirectoryPins) -> None:
        fixture_scope(root)
        self.pins = pins
        pins.pin_chain(root)
        pins.revalidate()
        self.root = fixture_root(root)
        temporary = root / "runtime-temp"
        if temporary not in pins.entries:
            temporary.mkdir()  # Exclusive first creation; never reuse an unpinned temp directory.
            pins.pin_chain(temporary)
        pins.revalidate()
        self.token = secrets.token_hex(32)
        self.messages: queue.Queue[str] = queue.Queue()
        self.stderr_bytes = 0
        self.diagnostics: list[dict] = []
        self.runtime_principals: list[dict] = []
        self._stopped = False
        self.process = subprocess.Popen(
            [sys._base_executable, "-s", "-P", "-B", str(Path(__file__).resolve()), "--serve", str(root)],
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=core_environment(temporary),
        )
        assert self.process.stdin and self.process.stdout and self.process.stderr
        self.process.stdin.reconfigure(newline="\n")  # Native protocol requires LF, including on Windows.

        def stdout() -> None:
            for line in self.process.stdout:
                self.messages.put(line)

        def stderr() -> None:
            for line in self.process.stderr:
                self.stderr_bytes += len(line.encode("utf-8"))
                try:
                    diagnostic = json.loads(line)
                    if diagnostic.get("kind") == "t03-create-diagnostic":
                        self.diagnostics.append(diagnostic)
                    elif diagnostic.get("kind") == "t03-runtime-principal":
                        self.runtime_principals.append(diagnostic)
                        # Existing diagnostic callers publish this collection;
                        # retain the helper identity wherever its facts are used.
                        self.diagnostics.append(diagnostic)
                except ValueError, AttributeError:
                    pass

        self.readers = [threading.Thread(target=stdout, daemon=True), threading.Thread(target=stderr, daemon=True)]
        for reader in self.readers:
            reader.start()
        self.process.stdin.write("auth " + self.token + "\n")
        self.process.stdin.flush()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.mutations = 0
        self.validate_or_stop()

    def ready(self) -> None:
        handshake = json.loads(self.messages.get(timeout=30))
        assert handshake["host"] == "127.0.0.1" and handshake["pid"] == self.process.pid
        assert handshake["protocolVersion"] == "1.0" and 1 <= handshake["port"] <= 65535
        self.url = "http://127.0.0.1:" + str(handshake["port"])
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                status, body = self.request("GET", "/workflow-profiles/catalog")
                assert status == 200 and len(body["profiles"]) == 14
                # These directories deliberately do not exist at first launch.
                # Pin them as soon as provisioning is observable, and retain
                # them through all project work, shutdown, and the next child.
                self.pin_chain_or_stop(self.root / "Research Observatory/security/profile-default/records")
                return
            except urllib.error.URLError:
                if self.process.poll() is not None:
                    raise AssertionError("Core exited before readiness") from None
                time.sleep(0.05)
        raise AssertionError("Core readiness timed out")

    def request(self, method: str, endpoint: str, body: dict | None = None) -> tuple[int, dict]:
        assert endpoint in {"/workflow-profiles/catalog", "/projects", "/projects/open", "/projects/close"}
        self.validate_or_stop()
        if method == "POST":
            self.mutations += 1
        request = urllib.request.Request(
            self.url + endpoint,
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            try:
                response = self.opener.open(request, timeout=20)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, json.loads(response.read(2_000_000))
        finally:
            self.validate_or_stop()

    def validate_or_stop(self) -> None:
        try:
            self.pins.revalidate()
        except BaseException:
            # Stop without asking Core to perform normal project cleanup on a
            # path whose authority has just drifted. Only this owned child.
            self.stop(on_drift=True)
            raise

    def pin_chain_or_stop(self, path: Path) -> None:
        try:
            self.pins.pin_chain(path)
            self.pins.revalidate()
        except BaseException:
            self.stop(on_drift=True)
            raise

    def read_database(self, path: Path) -> bytes:
        self.validate_or_stop()
        try:
            return read_database(path, self.pins)
        except BaseException:
            self.stop(on_drift=True)
            raise
        finally:
            self.validate_or_stop()

    def stop(self, *, on_drift: bool = False) -> None:
        if self._stopped:
            return
        drift_error: BaseException | None = None
        if not on_drift:
            try:
                self.pins.revalidate()
            except BaseException as error:
                # A caller may be unwinding an error outside the HTTP/DB
                # guards. Never ask Core to clean up through observed drift.
                on_drift = True
                drift_error = error
        assert self.process.stdin
        try:
            if self.process.poll() is None:
                if on_drift:
                    self.process.terminate()
                else:
                    try:
                        self.process.stdin.write("shutdown\n")
                        self.process.stdin.flush()
                    except OSError:
                        pass  # The exact child may have exited after poll().
            code = self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.terminate()  # Only the exact process created by this fixture.
            self.process.wait(timeout=10)
            raise AssertionError("Core failed graceful shutdown") from None
        finally:
            self.process.stdin.close()
            for reader in self.readers:
                reader.join(timeout=2)
            for stream in (self.process.stdout, self.process.stderr):
                if stream is not None:
                    stream.close()
            self.token = ""
            self._stopped = True
        if drift_error is not None:
            raise drift_error
        if not on_drift:
            assert code == 0


def create_reopen_collision(core: ActualCore, parent: Path, name: str) -> dict:
    core.pin_chain_or_stop(parent)
    plain_directory(parent)
    destination = parent / name
    assert not destination.exists()
    request = {
        "parentDirectory": str(parent),
        "directoryName": name,
        "displayName": "Synthetic default-folder acceptance proof",
        "primaryUseCase": "theory-synthesis",
        "researchObjective": "A disposable folder-selection test.\nNo research data.",
    }
    status, created = core.request("POST", "/projects", request)
    assert status == 200, {
        "status": status,
        "code": created.get("code"),
        "stage": CREATE_FAILURE_STAGES.get(created.get("detail"), "unclassified"),
        "diagnostics": core.diagnostics,
    }
    assert Path(created["root"]) == destination and created["open"] is False
    database = destination / "state/project.sqlite3"
    assert core.read_database(database)[:16] != b"SQLite format 3\x00", "Project database must be protected SQLCipher"
    for _ in range(2):
        status, opened = core.request("POST", "/projects/open", {"root": str(destination)})
        assert status == 200 and opened["open"] and opened["projectId"] == created["projectId"]
        status, closed = core.request("POST", "/projects/close", {"root": str(destination)})
        assert status == 200 and not closed["open"]
    before = hashlib.sha256(core.read_database(database)).hexdigest()
    status, collision = core.request("POST", "/projects", request)
    assert status == 409 and collision["code"] == "RO-CORE-PROJECT-ALREADY-EXISTS"
    assert hashlib.sha256(core.read_database(database)).hexdigest() == before
    assert not (parent / (name + "-1")).exists()
    return {
        "createdClosedReopenedTwice": True,
        "protectedDatabase": True,
        "collisionPreservedBytes": True,
        "noSilentNumbering": True,
        "childName": name,
        "fixtureRetained": True,
    }


def hashes(*, native: bool) -> dict[str, str]:
    scopes = ["services/core-api/src"]
    if native:
        scopes += ["apps/desktop/src-tauri", "Cargo.lock", "Cargo.toml"]
    inputs = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--",
            *scopes,
        ],
        cwd=REPO,
        text=True,
    ).splitlines()
    inputs += [
        "artifacts/evidence/W1.A09.T03.default-core-check-01.py",
        "artifacts/evidence/W1.A09.T03.default-core-pin-test-01.py",
        "artifacts/evidence/W1.A09.T03.runtime-principal-check-01.py",
    ]
    if native:
        inputs += ["apps/desktop/src-tauri/src/directory_picker.rs", "tests/service/test_native_project_contract.py"]
    return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in sorted(set(inputs))}


def run_proof(args: argparse.Namespace, pins: DirectoryPins) -> int:
    assert os.name == "nt" and args.report is not None
    report = report_target(args.report)
    assert report.name.startswith(f"W1.A09.T03.default-core-{args.mode}-"), "report mode mismatch"
    pins.pin_chain(REPORTS)
    pins.pin_chain(TEMP)
    before = hashes(native=args.mode == "complete")
    native_builds = []
    if args.mode == "complete":
        sys.path.insert(0, str(REPO / "tests/service"))
        from test_native_project_contract import build_project_probe

        native_builds = [build_project_probe(release=release) for release in (False, True)]
        assert hashes(native=True) == before
    root = fixture_root(Path(tempfile.mkdtemp(prefix="directory-default-", dir=TEMP)))
    pins.pin_chain(root)
    product = root / "Research Observatory"
    assert not product.exists()
    retained_projects: list[Path] = []
    outcomes: dict[str, object] = {"productChainAbsentBeforeStartup": True}
    core = ActualCore(root, pins)
    try:
        core.ready()
        assert (product / "security/profile-default").is_dir()
        assert core.mutations == 0
        outcomes["startupProvisionedIsolatedProductChainWithoutProjectMutation"] = True
        outcomes["freshDefaultParent"] = create_reopen_collision(core, product, "fresh-default-study")
        retained_projects.append(product / "fresh-default-study")
        secondary = product / "secondary-parent"
        secondary.mkdir()
        second_name = "t03-default-proof-" + uuid.uuid4().hex
        outcomes["secondFreshParent"] = create_reopen_collision(core, secondary, second_name)
        retained_projects.append(secondary / second_name)
        if args.mode == "complete":
            from research_observatory_core.windows_credentials import default_windows_profile_vault_path

            actual_parent = default_windows_profile_vault_path().parent.parent
            core.pin_chain_or_stop(actual_parent)
            plain_directory(actual_parent)
            live_child = "t03-default-proof-" + uuid.uuid4().hex
            assert not (actual_parent / live_child).exists()
            parent_before = actual_parent.stat()
            resolutions = []
            for build in native_builds:
                profile = build["profile"]
                assert profile in {"debug", "release"}
                executable = REPO / f"target/{profile}/examples/project_contract_probe.exe"
                core.validate_or_stop()
                try:
                    envelope = run_native_resolver(executable, build)
                finally:
                    core.validate_or_stop()
                assert envelope["kind"] == "actual-default-parent" and envelope["readOnly"] is True
                assert envelope["fixtureSubstitution"] is False
                assert envelope["debugAssertions"] == (profile == "debug")
                outcome = envelope["outcome"]
                assert outcome["status"] == "available" and Path(outcome["path"]) == actual_parent
                resolutions.append(
                    {
                        "profile": profile,
                        "executableSha256": build["executableSha256"],
                        "boundHashAndEmbeddedManifestVerifiedBeforeAndAfter": True,
                        "matchesActualShellCoreParent": True,
                    }
                )
            outcomes["nativeDefaultResolvers"] = resolutions
            parent_after = actual_parent.stat()
            assert (parent_before.st_dev, parent_before.st_ino, parent_before.st_mtime_ns) == (
                parent_after.st_dev,
                parent_after.st_ino,
                parent_after.st_mtime_ns,
            )
            assert not (actual_parent / live_child).exists()
            outcomes["nativeDiscoveryDidNotChangeParentOrCreateProject"] = True
            # Local-only recovery association: this synthetic project uses the
            # retained fixture vault, not the user's ordinary production vault.
            with (root / "retained-project-association.json").open("x", encoding="utf-8") as association:
                json.dump(
                    {
                        "project": str(actual_parent / live_child),
                        "vault": str(product / "security/profile-default"),
                        "synthetic": True,
                        "notAnOrdinaryProductionProject": True,
                    },
                    association,
                )
            outcomes["actualShellDefaultParent"] = create_reopen_collision(core, actual_parent, live_child)
            retained_projects.append(actual_parent / live_child)
    finally:
        core.stop()
    pins.revalidate()
    restart = ActualCore(root, pins)
    try:
        restart.ready()
        assert restart.mutations == 0
        for project in retained_projects:
            status, opened = restart.request("POST", "/projects/open", {"root": str(project)})
            assert status == 200 and opened["open"] and Path(opened["root"]) == project
            status, closed = restart.request("POST", "/projects/close", {"root": str(project)})
            assert status == 200 and not closed["open"]
        outcomes["freshProcessReopenedWithRetainedDpapiVault"] = len(retained_projects)
    finally:
        restart.stop()
    pins.revalidate()
    assert hashes(native=args.mode == "complete") == before, "Sources changed during default/Core proof"
    for instance in (core, restart):
        assert len(instance.runtime_principals) == 1, "exactly one serving-child observation required"
        observation = instance.runtime_principals[0]
        assert observation["coreModulesAlreadyLoaded"] is False
        assert (
            observation["metadataHelperSha256"] == before["artifacts/evidence/W1.A09.T03.runtime-principal-check-01.py"]
        )
    payload = {
        "status": "PASS",
        "mode": args.mode,
        "sourceHashes": before,
        "nativeBuilds": native_builds,
        "fixtureRoot": root.relative_to(REPO).as_posix(),
        "outcomes": outcomes,
        "runtimePrincipalObservations": {
            "firstServingChild": core.runtime_principals[0],
            "restartServingChild": restart.runtime_principals[0],
        },
        "gracefulCoreShutdown": True,
        "harnessSafeguards": {
            "explicitLoopbackEphemeralEnvironment": True,
            "fixtureTemporaryDirectory": True,
            "noInheritedPythonConfigurationOrUserSite": True,
            "retainedDirectoryRenameDenialAndIdentityObservationAcrossRestart": True,
            "heldAndNamedNoFollowChecksBeforeAndAfterHttpAndDatabaseReads": True,
            "newlyProvisionedVaultPinnedAtFirstReadiness": True,
            "absentVaultChainNotClaimedPinnedBeforeProvisioning": True,
            "databaseReadThroughValidatedNoFollowHandle": True,
            "exclusiveTaskNamespacedReport": True,
        },
        "priorAdversePinObservations": [
            "LIST_DIRECTORY|READ_ATTRIBUTES with read-only sharing blocked normal child staging rename (WinError32); "
            "fresh Core create returned RO-CORE-PROJECT-CREATE-FAILED.",
            "Adding write sharing permitted normal staging and denied parent rename, but actual same-account "
            "FSCTL_SET_REPARSE_POINT changed a pinned directory into a junction in place. "
            "Revalidation detected it; the handles did not prevent it.",
        ],
        "residualLimitation": (
            "Concurrent same-Windows-account writers can redirect a directory between checks. "
            "Post-operation detection cannot undo writes. No host-account isolation or general race-free "
            "confinement is claimed (accepted ADR-0017/ADR-0018 boundary). An observed drift stops the exact "
            "child and retains fixtures without following or cleaning the suspect path. First-start vault "
            "descendants cannot be pinned before Core creates them; they are validated at first readiness."
        ),
        "stderrBytesNotPublished": core.stderr_bytes + restart.stderr_bytes,
        "scope": (
            "Actual Windows DPAPI/SQLCipher and authenticated supervised Core; Python fixture supervisor, "
            "not Tauri/packaging/authentication proof. Vault and temporary locations are fixture-controlled; "
            "key providers are unchanged. All fixtures retained."
        ),
    }
    publish_report(report, payload)
    print(json.dumps({key: value for key, value in payload.items() if key != "sourceHashes"}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", type=Path)
    parser.add_argument("--mode", choices=("fresh", "complete"), default="fresh")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.serve is not None:
        return serve(args.serve)
    with DirectoryPins() as pins:
        return run_proof(args, pins)


if __name__ == "__main__":
    raise SystemExit(main())
