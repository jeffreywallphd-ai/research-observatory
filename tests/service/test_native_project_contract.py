"""Focused actual Windows supervisor/Core project-contract qualification."""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import PRODUCT_MANIFEST, PRODUCT_ROOT, product_build_errors, tool_environment  # noqa: E402
from ui_conformance import confined_path, stable_file_bytes  # noqa: E402


def project_probe_build_command(cargo: Path, *, release: bool = False) -> list[str]:
    """Build the probe with the single manifest embedded for examples by build.rs."""
    return [
        str(cargo),
        "rustc",
        "--message-format=json",
        "--locked",
        "--offline",
        "-p",
        "research-observatory-desktop",
        "--features",
        "integration-harness",
        "--example",
        "project_contract_probe",
        *(["--release"] if release else []),
    ]


def assert_project_probe_manifest(executable: Path) -> None:
    """Inspect the linked PE, not just the requested linker arguments."""
    import pefile  # type: ignore[import-untyped]  # Third-party PE reader has no published type stubs.

    with pefile.PE(str(executable)) as image:
        manifests = [
            language.data.struct
            for kind in image.DIRECTORY_ENTRY_RESOURCE.entries
            if kind.id == 24
            for name in kind.directory.entries
            for language in name.directory.entries
        ]
        assert len(manifests) == 1
        resource = manifests[0]
        manifest = ET.fromstring(image.get_data(resource.OffsetToData, resource.Size))
    dependencies = manifest.findall("./{*}dependency/{*}dependentAssembly/{*}assemblyIdentity")
    assert [item.attrib for item in dependencies] == [
        {
            "type": "win32",
            "name": "Microsoft.Windows.Common-Controls",
            "version": "6.0.0.0",
            "processorArchitecture": "*",
            "publicKeyToken": "6595b64144ccf1df",
            "language": "*",
        }
    ]
    levels = manifest.findall(".//{*}requestedExecutionLevel")
    assert len(levels) == 1 and levels[0].attrib == {"level": "asInvoker", "uiAccess": "false"}


def project_probe_input_hashes() -> dict[str, str]:
    """Validate the frontend before trusting its exact source/artifact inventory."""
    manifest_path = confined_path(REPO, PRODUCT_MANIFEST)
    manifest_bytes = stable_file_bytes(REPO, manifest_path)
    errors = product_build_errors(REPO)
    assert not errors, "Invalid desktop product build: " + "; ".join(errors)
    assert stable_file_bytes(REPO, manifest_path) == manifest_bytes, (
        "Desktop product manifest changed during validation"
    )
    manifest = json.loads(manifest_bytes)
    product_inputs = {
        **manifest["sourceFiles"],
        **{f"{PRODUCT_ROOT}/{name}": digest for name, digest in manifest["artifacts"].items()},
    }
    inputs = subprocess.check_output(
        ["git", "ls-files", "--", "Cargo.toml", "Cargo.lock", "apps/desktop/src-tauri"],
        cwd=REPO,
        text=True,
        encoding="utf-8",
    ).splitlines()
    inputs += [
        "apps/desktop/src-tauri/src/directory_picker.rs",  # Also bind pre-commit characterization.
        "tests/service/test_native_project_contract.py",
        "tools/desktop_app_check.py",
        "tools/ui_conformance.py",
        "design/ui-reference/SITE_MANIFEST.json",
        PRODUCT_MANIFEST,
    ]
    observed = {
        name: hashlib.sha256(stable_file_bytes(REPO, confined_path(REPO, name))).hexdigest()
        for name in sorted(set(inputs) | product_inputs.keys())
    }
    assert all(observed[name] == digest for name, digest in product_inputs.items()), (
        "Desktop product inputs changed after validation"
    )
    assert observed[PRODUCT_MANIFEST] == hashlib.sha256(manifest_bytes).hexdigest(), (
        "Desktop product manifest changed after validation"
    )
    return observed


def build_project_probe(*, release: bool = False) -> dict:
    """Bind validated native, renderer and artifact bytes across actual linking."""
    before = project_probe_input_hashes()
    environment, _, cargo = tool_environment(REPO)
    environment["CARGO_BUILD_JOBS"] = "1"
    command = project_probe_build_command(cargo, release=release)
    result = subprocess.run(
        command, cwd=REPO, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=180
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    assert before == project_probe_input_hashes(), (
        "Native implementation or product build inputs changed while compiling"
    )
    profile = "release" if release else "debug"
    executable = REPO / f"target/{profile}/examples/project_contract_probe.exe"
    # An inherited Cargo target override must not cause us to attest an older
    # binary at the usual path. Bind Cargo's actual compiler-artifact event.
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    linked = [
        event.get("executable")
        for event in events
        if event.get("reason") == "compiler-artifact"
        and event.get("target", {}).get("name") == "project_contract_probe"
        and event.get("target", {}).get("kind") == ["example"]
    ]
    assert len(linked) == 1 and linked[0] == str(executable), "Cargo did not report the expected probe executable"
    assert_project_probe_manifest(executable)
    return {
        "profile": profile,
        "argv": ["{cargo}", *command[1:]],
        "inputSha256": before,
        "executableSha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "embeddedCommonControls6AsInvokerVerified": True,
        "executablePathConfirmedByCargo": True,
    }


def seed_canonical_lineage(project_root: str, vault_root: str) -> None:
    """Append synthetic canonical revisions only inside the runner-owned fixture."""
    sys.path.insert(0, str(REPO / "services/core-api/src"))
    from research_observatory_core.projects import ProjectLifecycleService
    from research_observatory_core.repositories import create_sqlite_unit_of_work_factory
    from research_observatory_core.storage import configure_protected_database_provider
    from research_observatory_core.windows_credentials import create_windows_database_key_provider

    from tests.service.test_provenance import draft, event

    root = Path(project_root).resolve(strict=True)
    vault = Path(vault_root).resolve(strict=True)
    temporary = (REPO / "artifacts/tmp").resolve(strict=True)
    assert root.parent.name == "projects"
    assert root.parent.parent == vault.parent
    assert vault.name == "vault"
    assert vault.parent.parent == temporary
    assert vault.parent.name.startswith("project-native-contract-")
    configure_protected_database_provider(create_windows_database_key_provider(vault))
    projects = ProjectLifecycleService()
    try:
        opened = projects.open(root=str(root), trace_id="b" * 32)
        factory = create_sqlite_unit_of_work_factory(root / "state/project.sqlite3", opened.project_id)
        with factory() as unit:
            first = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()
        with factory() as unit:
            second = unit.aggregates.append(draft(2), event(1), expected_revision=0)
            unit.commit()
        print(json.dumps({"firstRevisionId": first.revision_id, "secondRevisionId": second.revision_id}))
    finally:
        projects.shutdown()


def recovery_probe_input_hashes() -> dict[str, str]:
    """Bind build inputs without granting shipping/frontend conformance."""
    from desktop_app_check import PRODUCT_EXCLUDED_DIRECTORIES, PRODUCT_EXTERNAL_INPUTS, PRODUCT_PACKAGE_ROOTS
    from ui_conformance import file_inventory

    manifest = json.loads(stable_file_bytes(REPO, confined_path(REPO, PRODUCT_MANIFEST)))
    sources = {}
    for name in ("apps/desktop", *PRODUCT_PACKAGE_ROOTS):
        sources.update(
            file_inventory(REPO, confined_path(REPO, name), excluded_directories=PRODUCT_EXCLUDED_DIRECTORIES)
        )
    for name in PRODUCT_EXTERNAL_INPUTS:
        sources[name] = hashlib.sha256(stable_file_bytes(REPO, confined_path(REPO, name))).hexdigest()
    assert manifest["sourceFiles"] == dict(sorted(sources.items())), "Recovery probe frontend inputs are stale"
    artifacts = file_inventory(REPO, confined_path(REPO, PRODUCT_ROOT))
    artifacts.pop(PRODUCT_MANIFEST)
    assert manifest["artifacts"] == dict(
        sorted((name.removeprefix(PRODUCT_ROOT + "/"), digest) for name, digest in artifacts.items())
    ), "Recovery build artifacts changed"
    names = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--",
            "Cargo.toml",
            "Cargo.lock",
            "apps/desktop/src-tauri",
            "services/core-api/src",
            "workers",
            "packages/contracts",
            "tests/service/fixtures/native_integration_sidecar.py",
            "tests/service/test_provenance.py",
            "tests/service/test_native_project_contract.py",
            "tools/desktop_app_check.py",
            "tools/ui_conformance.py",
        ],
        cwd=REPO,
        text=True,
        encoding="utf-8",
    ).splitlines()
    names.append("services/core-api/src/research_observatory_core/ports/project_recovery.py")
    names.append(PRODUCT_MANIFEST)
    return {
        name: hashlib.sha256(stable_file_bytes(REPO, confined_path(REPO, name))).hexdigest()
        for name in sorted(set(names) | sources.keys() | artifacts.keys())
    }


def build_recovery_native_probe(cargo: Path, environment: dict[str, str]) -> dict:
    """Additive real headless T01 build; original shipping builder is unchanged."""
    before = recovery_probe_input_hashes()
    command = project_probe_build_command(cargo)
    result = subprocess.run(
        command, cwd=REPO, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=360
    )
    assert result.returncode == 0, result.stderr
    assert before == recovery_probe_input_hashes(), "Recovery Native build inputs drifted"
    executable = REPO / "target/debug/examples/project_contract_probe.exe"
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    linked = [
        event.get("executable")
        for event in events
        if event.get("reason") == "compiler-artifact"
        and event.get("target", {}).get("name") == "project_contract_probe"
        and event.get("target", {}).get("kind") == ["example"]
    ]
    assert linked == [str(executable)], "Recovery Cargo artifact does not bind the actual probe"
    assert_project_probe_manifest(executable)
    # CPython exposes its base interpreter here; typeshed omits the private field.
    base_python = sys._base_executable  # type: ignore[attr-defined]
    return {
        "scope": "T01 headless Native/Core only; no shipping UI or frontend acceptance",
        "inputSha256": before,
        "executableSha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "cargoExecutableSha256": hashlib.sha256(cargo.read_bytes()).hexdigest(),
        "pythonExecutableSha256": hashlib.sha256(Path(str(base_python)).read_bytes()).hexdigest(),
        "argv": ["{cargo}", *command[1:]],
        "embeddedCommonControls6AsInvokerVerified": True,
    }


class _RecoveryNativeJob:
    """Test-owned no-breakaway Job; assign the Native host before it executes."""

    def __init__(self) -> None:
        from ctypes import wintypes

        from workers.windows.lpac_launcher import _ExtendedLimitInformation

        class Accounting(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_int64)
                for name in ("TotalUserTime", "TotalKernelTime", "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")
            ] + [
                (name, wintypes.DWORD)
                for name in ("TotalPageFaultCount", "TotalProcesses", "ActiveProcesses", "TotalTerminatedProcesses")
            ]

        self.accounting = Accounting
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, args, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            (
                "SetInformationJobObject",
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                wintypes.BOOL,
            ),
            (
                "QueryInformationJobObject",
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p],
                wintypes.BOOL,
            ),
            ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ("TerminateJobObject", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway.
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def launch(self, argv: list[str], environment: dict[str, str], stderr) -> subprocess.Popen:
        from ctypes import wintypes

        process = subprocess.Popen(
            argv,
            cwd=REPO,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            encoding="utf-8",
            creationflags=0x4 | 0x08000000,
        )
        try:
            # The actual Windows Popen handle is required to assign before resume.
            process_handle = wintypes.HANDLE(int(process._handle))  # type: ignore[attr-defined]
            if not self.api.AssignProcessToJobObject(self.handle, process_handle):
                raise ctypes.WinError(ctypes.get_last_error())
            resume = ctypes.WinDLL("ntdll").NtResumeProcess
            resume.argtypes, resume.restype = [wintypes.HANDLE], wintypes.LONG
            if resume(process_handle) != 0:
                raise AssertionError("Owned Native resume failed")
            return process
        except BaseException:
            process.kill()
            process.wait(timeout=10)
            raise

    def observe(self) -> dict[str, int]:
        information = self.accounting()
        if not self.api.QueryInformationJobObject(
            self.handle, 1, ctypes.byref(information), ctypes.sizeof(information), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"total": information.TotalProcesses, "active": information.ActiveProcesses}

    def terminate(self) -> dict[str, int]:
        if not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            observation = self.observe()
            if observation["active"] == 0:
                return observation
            time.sleep(0.025)
        raise AssertionError("Owned whole Native/Core Job did not become empty")

    def close(self) -> None:
        if self.handle:
            self.api.TerminateJobObject(self.handle, 1)
            self.api.CloseHandle(self.handle)
            self.handle = None


class _RecoveryNativeDriver:
    """Drive existing public requests through the actual compiled supervisor."""

    def __init__(self, fixture: Path, vault: Path, environment: dict[str, str], label: str) -> None:
        self.messages: queue.Queue = queue.Queue(maxsize=128)
        self.job = _RecoveryNativeJob()
        self.stderr = (fixture / f"{label}.stderr.log").open("x", encoding="utf-8")
        self.stdout = (fixture / f"{label}.stdout.log").open("x", encoding="utf-8")
        try:
            base_python = sys._base_executable  # type: ignore[attr-defined]
            self.process = self.job.launch(
                [
                    str(REPO / "target/debug/examples/project_contract_probe.exe"),
                    str(base_python),
                    str(REPO),
                    os.pathsep.join(
                        str(REPO / name)
                        for name in ("tests/service/fixtures", "services/core-api/src", ".venv/Lib/site-packages")
                    ),
                    str(vault),
                ],
                environment,
                self.stderr,
            )
        except BaseException:
            self.job.close()
            self.stderr.close()
            self.stdout.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self._start()
        except BaseException:
            self.close()
            raise

    def _start(self) -> None:
        if self.next()["kind"] != "initialized":
            raise AssertionError("Native driver did not initialize")
        self.exchange({"control": "start"})
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            snapshot = self.exchange({"control": "status"})["snapshot"]
            if snapshot["state"] == "ready":
                return
            if snapshot["state"] not in ("stopped", "starting"):
                raise AssertionError(f"Actual Native/Core startup failed: {snapshot}")
            time.sleep(0.025)
        raise AssertionError("Actual Native/Core startup timed out")

    def _read(self) -> None:
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                self.stdout.write(line)
                self.stdout.flush()
                self.messages.put(json.loads(line), timeout=1)
        finally:
            self.messages.put(None, timeout=1)

    def next(self) -> dict:
        value = self.messages.get(timeout=45)
        if value is None:
            raise AssertionError("Actual Native driver exited")
        return value

    def exchange(self, command: dict) -> dict:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()
        return self.next()

    def request(self, path: str, body: dict) -> dict:
        result = self.exchange(
            {"method": "POST", "path": path, "body": json.dumps(body), "ifMatch": None, "idempotencyKey": None}
        )
        if result.get("kind") != "response":
            raise AssertionError(f"Actual Native request denied: {result}")
        response = result["response"]
        if response["status"] != 200:
            raise AssertionError(f"Actual Core request failed: {response}")
        return json.loads(response["body"])

    def close(self) -> None:
        try:
            self.job.terminate()
            self.process.wait(timeout=10)
        finally:
            self.job.close()
            if self.process.stdin is not None:
                self.process.stdin.close()
            self.reader.join(timeout=5)
            if self.process.stdout is not None:
                self.process.stdout.close()
            self.stderr.close()
            self.stdout.close()


@unittest.skipUnless(os.name == "nt", "Windows x64 Native/Core recovery boundary")
class NativeRecoveryContractTests(unittest.TestCase):
    """Additive T01 headless proof; no shipping frontend predicate substitution."""

    environment: dict[str, str]
    input_holds: contextlib.ExitStack
    source_inputs: dict[str, str]
    build_binding: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.environment, _, cargo = tool_environment(REPO)
        cls.environment["CARGO_BUILD_JOBS"] = "1"
        sys.path.insert(0, str(REPO / "services/core-api/src"))
        from research_observatory_core.projects import _recovery_held_file

        cls.input_holds = contextlib.ExitStack()
        cls.addClassCleanup(cls.input_holds.close)
        cls.source_inputs = recovery_probe_input_hashes()
        for name in cls.source_inputs:
            cls.input_holds.enter_context(_recovery_held_file(confined_path(REPO, name)))
        cls.build_binding = build_recovery_native_probe(cargo, cls.environment)
        cls.input_holds.enter_context(_recovery_held_file(REPO / "target/debug/examples/project_contract_probe.exe"))

    @classmethod
    def tearDownClass(cls) -> None:
        assert cls.source_inputs == recovery_probe_input_hashes(), "Held recovery inputs changed during actual run"
        assert (
            cls.build_binding["executableSha256"]
            == hashlib.sha256((REPO / "target/debug/examples/project_contract_probe.exe").read_bytes()).hexdigest()
        ), "Held Native executable changed during actual run"

    def test_whole_native_core_death_recovers_verified_protected_copy(self) -> None:
        """Real OS/process/DPAPI/SQLCipher proof; shipping UI remains T02's check."""
        sys.path.insert(0, str(REPO / "services/core-api/src"))
        from research_observatory_core import storage, windows_credentials
        from research_observatory_core.object_store import create_local_object_store
        from research_observatory_core.ports.object_store import ObjectPutCommand
        from research_observatory_core.storage import EXPECTED_TABLES, open_canonical_database
        from research_observatory_core.windows_credentials import (
            WindowsProjectRecoveryWitnessStore,
            create_windows_database_key_provider,
            create_windows_object_key_provider,
        )

        fixture = Path(tempfile.mkdtemp(prefix="project-native-contract-", dir=REPO / "artifacts/tmp")).resolve()
        # Private test storage, not a new user's profile or any production fixture.
        private = fixture / "private"
        with windows_credentials._recovery_security_attributes(windows_credentials._recovery_current_sid()) as sa:
            self.assertTrue(windows_credentials._recovery_windows_api()["CreateDirectoryW"](str(private), sa))
        vault = private / "vault"
        projects = private / "projects"
        vault.mkdir()
        projects.mkdir()
        first = _RecoveryNativeDriver(fixture, vault, self.environment, "original-pair")
        self.addCleanup(first.close)
        created = first.request(
            "/projects",
            {
                "parentDirectory": str(projects),
                "directoryName": "original",
                "displayName": "Recovery proof study",
                "primaryUseCase": "theory-synthesis",
                "researchObjective": "Retain synthetic human facts after abrupt death.",
            },
        )
        root = Path(created["root"])
        project_id = created["projectId"]
        # Seed protected scholarly facts while closed, then acquire a new real eligible session.
        first.request("/projects/open", {"root": str(root)})
        first.request("/projects/close", {"root": str(root)})
        previous_protection = storage._DATABASE_PROTECTION
        self.addCleanup(setattr, storage, "_DATABASE_PROTECTION", previous_protection)
        storage.configure_protected_database_provider(create_windows_database_key_provider(vault))
        from research_observatory_core.repositories import create_sqlite_unit_of_work_factory

        from tests.service.test_provenance import draft, event

        factory = create_sqlite_unit_of_work_factory(root / "state/project.sqlite3", project_id)
        with factory() as unit:
            earlier = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()
        with factory() as unit:
            later = unit.aggregates.append(draft(2), event(1), expected_revision=0)
            unit.commit()
        payload = b"Synthetic retained encrypted recovery object.\n" * 128
        keys = create_windows_object_key_provider(vault)
        objects = create_local_object_store(root, project_id, key_provider=keys)
        stored = objects.put(
            io.BytesIO(payload),
            ObjectPutCommand(
                "application/pdf",
                "allowed",
                "project-encrypted-v1",
                "project-lifetime",
                "test-fixture",
                "2026-08-18T12:00:00.000Z",
            ),
        )
        self.assertNotEqual(b"SQLite format 3\x00", (root / "state/project.sqlite3").read_bytes()[:16])
        first.request("/projects/open", {"root": str(root)})
        lock_path = root / ".locks/session.lock"
        lock = json.loads(lock_path.read_bytes())
        token_hash = hashlib.sha256(lock["recoveryToken"].encode()).hexdigest()
        witness_store = WindowsProjectRecoveryWitnessStore(vault / "project-recovery")
        old_witness = witness_store.read(project_id, lock["instanceId"], "opened", token_sha256=token_hash)
        self.assertEqual(first.process.pid, old_witness.native_session.native.process_id)
        self.assertEqual(lock["processId"], old_witness.native_session.core.process_id)
        self.assertNotEqual(first.process.pid, lock["processId"])
        live_preview = first.request(
            "/projects/recovery/preview",
            {
                "root": str(root),
                "destinationRoot": str(projects / "live-owner-copy"),
            },
        )
        self.assertIn(live_preview["state"], ("denied", "unavailable-proof"))
        self.assertFalse((projects / "live-owner-copy").exists())
        # A genuinely separate same-host Native/Core instance cannot close the
        # original owner's project or retire its still-live recovery authority.
        foreign = _RecoveryNativeDriver(fixture, vault, self.environment, "foreign-close-pair")
        try:
            self.assertNotEqual(first.process.pid, foreign.process.pid)
            denied_close = foreign.exchange(
                {
                    "method": "POST",
                    "path": "/projects/close",
                    "body": json.dumps({"root": str(root)}),
                    "ifMatch": None,
                    "idempotencyKey": None,
                }
            )
            self.assertEqual("response", denied_close["kind"], denied_close)
            self.assertEqual(409, denied_close["response"]["status"], denied_close)
            self.assertEqual("RO-CORE-PROJECT-OPEN-ELSEWHERE", json.loads(denied_close["response"]["body"])["code"])
            after_denial = json.loads(lock_path.read_bytes())
            self.assertEqual(
                {key: value for key, value in lock.items() if key != "heartbeatAt"},
                {key: value for key, value in after_denial.items() if key != "heartbeatAt"},
            )
            self.assertEqual(
                old_witness,
                witness_store.read(project_id, lock["instanceId"], "opened", token_sha256=token_hash),
            )
            self.assertEqual(project_id, first.request("/projects/intent", {"root": str(root)})["projectId"])
        finally:
            foreign.close()
        before_death = first.job.observe()
        self.assertGreaterEqual(before_death["active"], 2)
        after_death = first.job.terminate()
        first.process.wait(timeout=10)
        self.assertEqual(0, after_death["active"])

        def inventory(path: Path) -> dict[str, str]:
            return {
                file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
                for file in path.rglob("*")
                if file.is_file()
            }

        original_bytes = inventory(root)
        self.assertIn("state/project.sqlite3", original_bytes)
        self.assertIn(".locks/session.lock", original_bytes)
        self.assertTrue(any(name.startswith("objects/") for name in original_bytes))
        # Test-only raw oracle: never open the preserved Original database after death.
        oracle = private / "raw-oracle"
        shutil.copytree(root, oracle)

        def facts(path: Path) -> dict[str, tuple]:
            connection = open_canonical_database(path / "state/project.sqlite3", expected_project_id=project_id)
            try:
                return {
                    table: tuple(
                        sorted((tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"')), key=repr)
                    )
                    for table in EXPECTED_TABLES
                }
            finally:
                connection.close()

        expected_facts = facts(oracle)
        self.assertEqual(original_bytes, inventory(root))
        fresh = _RecoveryNativeDriver(fixture, vault, self.environment, "fresh-pair")
        self.addCleanup(fresh.close)
        self.assertNotEqual(first.process.pid, fresh.process.pid)
        destination = projects / "recovered"
        preview = fresh.request(
            "/projects/recovery/preview",
            {
                "root": str(root),
                "destinationRoot": str(destination),
            },
        )
        self.assertEqual("preview-ready", preview["state"], preview)
        self.assertTrue(preview["requiresConfirmation"])
        self.assertFalse(destination.exists())
        command = {"root": str(root), "previewId": preview["previewId"]}
        fresh.request("/projects/recovery/confirm", {**command, "confirmation": "recover-working-copy"})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = fresh.request("/projects/recovery/status", command)
            if status["state"] != "copying":
                break
            time.sleep(0.025)
        self.assertEqual("verified-copy-ready", status["state"], status)
        self.assertIn("1 encrypted objects", status["verifiedFactSummary"])
        self.assertFalse((destination / ".locks/session.lock").exists())
        self.assertEqual(expected_facts, facts(destination))
        self.assertEqual(original_bytes, inventory(root))
        opened = fresh.request("/projects/open", {"root": str(destination)})
        self.assertEqual(project_id, opened["projectId"])
        self.assertEqual("recovered", fresh.request("/projects/recovery/status", command)["state"])
        new_lock = json.loads((destination / ".locks/session.lock").read_bytes())
        new_witness = witness_store.read(
            project_id,
            new_lock["instanceId"],
            "opened",
            token_sha256=hashlib.sha256(new_lock["recoveryToken"].encode()).hexdigest(),
        )
        self.assertEqual(fresh.process.pid, new_witness.native_session.native.process_id)
        self.assertNotEqual(old_witness.native_session.launch_session, new_witness.native_session.launch_session)
        self.assertNotEqual(old_witness.native_session.core, new_witness.native_session.core)
        lineage = fresh.request(
            "/projects/provenance/lineage",
            {
                "root": str(destination),
                "revisionId": later.revision_id,
                "direction": "ancestors",
                "cursor": 0,
                "pageSize": 50,
                "maxDepth": 8,
            },
        )
        self.assertTrue(any(item["revisionId"] == earlier.revision_id for item in lineage["items"]))
        intent = fresh.request("/projects/intent", {"root": str(destination)})
        self.assertEqual("Retain synthetic human facts after abrupt death.", intent["current"]["researchObjective"])
        recovered_objects = create_local_object_store(
            destination, project_id, key_provider=keys, reconcile_abandoned=False
        )
        with contextlib.closing(recovered_objects.open(stored.object_sha256, purpose="test-verification")) as stream:
            self.assertEqual(payload, stream.read())
        fresh.request("/projects/close", {"root": str(destination)})
        self.assertEqual(original_bytes, inventory(root))
        fresh_end = fresh.job.terminate()
        fresh.process.wait(timeout=10)
        self.assertEqual(0, fresh_end["active"])
        print(
            json.dumps(
                {
                    "wholeNativeCoreRecovery": {
                        "oldJob": before_death,
                        "oldJobAfterDeath": after_death,
                        "freshJobAfterDeath": fresh_end,
                        "oldNativePid": old_witness.native_session.native.process_id,
                        "oldCorePid": old_witness.native_session.core.process_id,
                        "freshNativePid": new_witness.native_session.native.process_id,
                        "freshCorePid": new_witness.native_session.core.process_id,
                        "wholePairChanged": True,
                        "originalBytesUnchanged": True,
                        "allCanonicalRowsPreservedBeforeOpen": sum(map(len, expected_facts.values())),
                        "actualProtectedLineageReadback": True,
                        "actualProtectedIntentReadback": True,
                        "authenticatedObjectSha256": stored.object_sha256,
                        "liveOwnerDenied": True,
                        "actualSameHostForeignInstanceCloseDenied": True,
                        "fixtureRetained": fixture.relative_to(REPO).as_posix(),
                        "shippingGuiQualification": False,
                    },
                    "buildBinding": self.build_binding,
                },
                sort_keys=True,
            )
        )


@unittest.skipUnless(os.name == "nt", "Windows x64 native qualification")
class NativeProjectContractTests(unittest.TestCase):
    environment: dict[str, str]
    build_binding: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.environment, _, _ = tool_environment(REPO)
        native_inputs = subprocess.check_output(
            [
                "git",
                "ls-files",
                "--",
                "Cargo.toml",
                "Cargo.lock",
                "apps/desktop/src-tauri",
            ],
            cwd=REPO,
            text=True,
            encoding="utf-8",
        ).splitlines()

        def hashes() -> dict[str, str]:
            return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in native_inputs}

        before = hashes()
        cls.build_binding = build_project_probe()
        if before != hashes():
            raise AssertionError("Native inputs changed while Cargo was building the probe.")
        cls.environment = {**cls.environment, "RO_PROJECT_PROBE_BUILD_INPUTS": json.dumps(before)}

    def test_packaged_path_spelling_does_not_admit_redirected_executable(self) -> None:
        import _winapi

        # Retain these inert fixtures for inspection. The native probe validates
        # their paths only and never executes the synthetic .exe bytes.
        fixture_parent = (REPO / "artifacts/tmp").resolve(strict=True)
        fixture = Path(tempfile.mkdtemp(prefix="project-native-path-", dir=fixture_parent))
        self.assertEqual(fixture_parent, fixture.resolve(strict=True).parent)
        target = fixture / "canonical"
        target.mkdir()
        executable = target / "research-observatory-core-x86_64-pc-windows-msvc.exe"
        executable.write_bytes(b"Synthetic path fixture; never executable.")
        redirect = fixture / "redirect"
        _winapi.CreateJunction(str(target), str(redirect))
        self.assertTrue(redirect.is_junction())

        def check(candidate: str, accepted: bool) -> None:
            result = subprocess.run(
                [str(REPO / "target/debug/examples/project_contract_probe.exe"), "--check-packaged-path", candidate],
                cwd=REPO,
                env=self.environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                {"accepted": accepted, "code": None if accepted else "RO-CORE-INTEGRITY-FAILED"},
                json.loads(result.stdout),
            )

        check(str(executable), True)
        check("\\\\?\\" + str(executable), True)
        check(str(redirect / executable.name), False)
        check("\\\\?\\" + str(redirect / executable.name), False)

        link_parent = fixture / "symbolic"
        link_parent.mkdir()
        symbolic = link_parent / executable.name
        try:
            symbolic.symlink_to(executable)
        except OSError as error:
            if error.winerror != 1314:
                raise
            symbolic_result = "unavailable: Windows did not grant symbolic-link creation privilege"
        else:
            self.assertTrue(symbolic.is_symlink())
            check(str(symbolic), False)
            check("\\\\?\\" + str(symbolic), False)
            symbolic_result = "denied in plain and verbatim forms"
        print(
            json.dumps(
                {
                    "packagedPath": {
                        "plainAndVerbatim": "accepted",
                        "junctionRedirects": "denied",
                        "symbolicLinks": symbolic_result,
                    },
                    "fixtureDirectory": fixture.relative_to(REPO).as_posix(),
                    "fixturesRetained": True,
                },
                sort_keys=True,
            )
        )

    def test_generated_requests_reach_actual_native_and_protected_core(self) -> None:
        result = subprocess.run(
            [
                str(REPO / ".local/toolchains/node-v24.19.0-win-x64/node.exe"),
                str(REPO / "artifacts/evidence/W1.A09.T02.native-check-01.mjs"),
            ],
            cwd=REPO,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertGreater(report["outcomes"]["retainedLineageNodes"], 1)
        self.assertTrue(report["outcomes"]["restartPreservedIntentWorkflowAndLineage"])
        self.assertTrue(report["outcomes"]["readRetryCreatedNothing"])
        print(json.dumps(report, sort_keys=True))

    def test_probe_rejects_missing_or_substituted_build_binding_before_launch(self) -> None:
        fixture_parent = REPO / "artifacts/tmp"
        before = {path.name for path in fixture_parent.glob("project-native-contract-*")}
        substituted = json.loads(self.environment["RO_PROJECT_PROBE_BUILD_INPUTS"])
        substituted["apps/desktop/src-tauri/src/supervisor.rs"] = "0" * 64
        for binding in ("null", json.dumps(substituted)):
            with self.subTest(binding="missing" if binding == "null" else "substituted"):
                result = subprocess.run(
                    [
                        str(REPO / ".local/toolchains/node-v24.19.0-win-x64/node.exe"),
                        str(REPO / "artifacts/evidence/W1.A09.T02.native-check-01.mjs"),
                    ],
                    cwd=REPO,
                    env={**self.environment, "RO_PROJECT_PROBE_BUILD_INPUTS": binding},
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=45,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn("native input hashes must match the successful Cargo build interval", result.stderr)
                self.assertEqual("", result.stdout)
        self.assertEqual(before, {path.name for path in fixture_parent.glob("project-native-contract-*")})


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--seed-lineage":
        seed_canonical_lineage(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
