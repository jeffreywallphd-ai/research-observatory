"""Bounded synthetic Windows boundary regressions for the T03 proof runner.

Fixtures are exclusively created below artifacts/tmp and retained. These tests
do not launch native UI, use a real default parent, or read any user vault.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "t03_default_core", REPO / "artifacts/evidence/W1.A09.T03.default-core-check-01.py"
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
sys.path.insert(0, str(REPO / "tests/service"))
import test_native_project_contract as native_helper  # noqa: E402


class ProofRunnerBoundaryTests(unittest.TestCase):
    def test_runtime_principal_observation_is_path_free_and_helper_bound(self) -> None:
        observation = runner.runtime_principal_observation()
        self.assertEqual(
            set(observation),
            {
                "kind",
                "observationPhase",
                "metadataHelperSha256",
                "metadataHelperUnchanged",
                "coreModulesAlreadyLoaded",
                "facts",
            },
        )
        self.assertEqual(observation["kind"], "t03-runtime-principal")
        self.assertEqual(observation["observationPhase"], "before-core-import-and-startup")
        self.assertEqual(
            observation["metadataHelperSha256"], hashlib.sha256(runner.RUNTIME_METADATA_HELPER.read_bytes()).hexdigest()
        )
        self.assertTrue(observation["metadataHelperUnchanged"])
        encoded = json.dumps(observation)
        self.assertNotIn(str(REPO), encoded)
        self.assertNotIn(sys._base_executable.replace("\\", "\\\\"), encoded)
        facts = observation["facts"]
        self.assertTrue(
            all(
                len(value) == 64 and all(character in "0123456789abcdef" for character in value)
                for key, value in facts.items()
                if key.endswith("Sha256")
            )
        )
        self.assertIn("artifacts/evidence/W1.A09.T03.runtime-principal-check-01.py", runner.hashes(native=False))

    def test_actual_serving_child_reports_metadata_before_core_imports(self) -> None:
        with runner.DirectoryPins() as pins:
            pins.pin_chain(self.root)
            core = runner.ActualCore(self.root, pins)
            try:
                core.ready()
                self.assertEqual(core.mutations, 0)
            finally:
                core.stop()
            self.assertEqual(len(core.runtime_principals), 1)
            observation = core.runtime_principals[0]
            self.assertFalse(observation["coreModulesAlreadyLoaded"])
            self.assertEqual(observation["facts"]["pythonVersion"], "3.14.6")
            self.assertEqual(
                observation["metadataHelperSha256"],
                hashlib.sha256(runner.RUNTIME_METADATA_HELPER.read_bytes()).hexdigest(),
            )
            self.assertIn(observation, core.diagnostics)

    def test_creation_diagnostics_exclude_exception_text_and_paths(self) -> None:
        error = RuntimeError("SYNTHETIC_PRIVATE_TEXT must never enter evidence")
        cause = PermissionError(13, "SYNTHETIC_PRIVATE_PATH", "SYNTHETIC_PRIVATE_FILENAME")
        error.__cause__ = cause
        observed = runner.bounded_failure(error)
        self.assertEqual(
            observed,
            {
                "kind": "t03-create-diagnostic",
                "stage": "unclassified",
                "causes": [{"type": "RuntimeError"}, {"type": "PermissionError", "errno": 13}],
            },
        )
        self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(observed))

    def setUp(self) -> None:
        with runner.DirectoryPins() as pins:
            pins.pin_chain(runner.TEMP)
            self.root = Path(tempfile.mkdtemp(prefix="directory-default-pin-", dir=runner.TEMP))
            pins.pin_chain(self.root)
            runner.fixture_root(self.root)

    @staticmethod
    def open_read_only_shared(path: Path, *, directory: bool) -> int:
        # Retain the adverse predecessor sharing mode as a characterization.
        handle = runner._KERNEL.CreateFileW(
            str(path),
            0x81 if directory else 0x80000000,
            0x1,
            None,
            3,
            0x02000000 | 0x00200000,
            None,
        )
        if handle == runner._INVALID_HANDLE:
            raise AssertionError("experimental no-follow handle unavailable")
        return handle

    def test_predecessor_read_only_sharing_blocks_normal_child_staging_rename(self) -> None:
        staging = self.root / "staging"
        published = self.root / "published"
        with (
            mock.patch.object(runner, "_open_pinned", side_effect=self.open_read_only_shared),
            runner.DirectoryPins() as pins,
        ):
            pins.pin_chain(self.root)
            staging.mkdir()
            with self.assertRaises(OSError) as error:
                staging.rename(published)
            self.assertEqual(error.exception.winerror, 32)
            pins.revalidate()
        staging.rename(published)
        self.assertTrue(published.is_dir())

    def test_read_write_sharing_denies_parent_replacement_but_allows_staged_child_publication(self) -> None:
        subject = self.root / "subject"
        subject.mkdir()
        moved = self.root / "moved"
        code = (
            "import json,os,pathlib,sys; source=pathlib.Path(sys.argv[1]); target=pathlib.Path(sys.argv[2]); "
            "staging=source/'staging'; staging.mkdir(); staging.rename(source/'published'); "
            "\ntry: os.rename(source,target)"
            "\nexcept OSError as error: print(json.dumps({'denied':error.winerror in (5,32),"
            "'published':(source/'published').is_dir()}))"
            "\nelse: print(json.dumps({'denied':False}))"
        )
        with runner.DirectoryPins() as pins:
            pins.pin_chain(subject)
            child = subprocess.run(
                [sys._base_executable, "-s", "-P", "-B", "-c", code, str(subject), str(moved)],
                cwd=self.root,
                env=runner.core_environment(self.root),
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(child.returncode, 0)
            self.assertEqual(json.loads(child.stdout), {"denied": True, "published": True})
            pins.revalidate()
        subject.rename(moved)
        self.assertTrue(moved.is_dir())

    def test_same_account_in_place_reparse_mutation_remains_possible_but_is_detected(self) -> None:
        import ctypes
        from ctypes import wintypes

        subject = self.root / "subject"
        target = self.root / "target"
        subject.mkdir()
        target.mkdir()
        substitute = ("\\??\\" + str(target)).encode("utf-16-le")
        printable = str(target).encode("utf-16-le")
        payload = (
            struct.pack(
                "<IHHHHHH",
                0xA0000003,
                8 + len(substitute) + 2 + len(printable) + 2,
                0,
                0,
                len(substitute),
                len(substitute) + 2,
                len(printable),
            )
            + substitute
            + b"\0\0"
            + printable
            + b"\0\0"
        )
        device_io = runner._KERNEL.DeviceIoControl
        device_io.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        device_io.restype = wintypes.BOOL
        with runner.DirectoryPins() as pins:
            pins.pin_chain(subject)
            pinned_handle, identity = pins.entries[subject]
            handle = runner._KERNEL.CreateFileW(str(subject), 0x40000000, 0x7, None, 3, 0x02200000, None)
            self.assertNotEqual(handle, runner._INVALID_HANDLE)
            try:
                returned = wintypes.DWORD()
                buffer = ctypes.create_string_buffer(payload)
                changed = device_io(handle, 0x000900A4, buffer, len(payload), None, 0, ctypes.byref(returned), None)
                self.assertTrue(changed, "characterize actual same-account in-place junction mutation")
                information = runner._FileInformation()
                self.assertTrue(runner._KERNEL.GetFileInformationByHandle(pinned_handle, ctypes.byref(information)))
                self.assertEqual((information.volume, (information.index_high << 32) | information.index_low), identity)
                self.assertTrue(information.attributes & 0x400)
                # ADR-0017/0018 exclude malicious same-account isolation. The
                # prior prevention expectation failed; preserve that adverse
                # fact, and prove observation rejects it without following it.
                with self.assertRaisesRegex(AssertionError, "reparse"):
                    pins.revalidate()
            finally:
                runner._KERNEL.CloseHandle(handle)

    def test_real_child_cannot_replace_pinned_directory_but_can_create_ordinary_child(self) -> None:
        subject = self.root / "subject"
        subject.mkdir()
        moved = self.root / "moved"
        code = (
            "import json,os,pathlib,sys; "
            "source=pathlib.Path(sys.argv[1]); target=pathlib.Path(sys.argv[2]); "
            "(source/'ordinary-child').mkdir(); "
            "\ntry: os.rename(source,target)"
            "\nexcept OSError as error: print(json.dumps({'denied':error.winerror in (5,32)}))"
            "\nelse: print(json.dumps({'denied':False}))"
        )
        with runner.DirectoryPins() as pins:
            pins.pin_chain(subject)
            child = subprocess.run(
                [sys._base_executable, "-s", "-P", "-B", "-c", code, str(subject), str(moved)],
                cwd=self.root,
                env=runner.core_environment(self.root),
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(child.returncode, 0)
            self.assertEqual(json.loads(child.stdout), {"denied": True})
            self.assertTrue((subject / "ordinary-child").is_dir())
            pins.revalidate()
        subject.rename(moved)
        self.assertTrue(moved.is_dir(), "closing the last pin releases the rename denial")

    def test_actual_junction_is_rejected_without_inspecting_its_target(self) -> None:
        target = self.root / "target"
        target.mkdir()
        junction = self.root / "junction"
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(result.returncode, 0, "synthetic junction setup failed")
        opened = []
        actual_open = runner._open_pinned

        def observe(path: Path, *, directory: bool) -> int:
            opened.append(path)
            return actual_open(path, directory=directory)

        with (
            runner.DirectoryPins() as pins,
            mock.patch.object(runner, "_open_pinned", side_effect=observe),
            self.assertRaisesRegex(AssertionError, "reparse"),
        ):
            pins.pin_chain(junction / "must-not-be-inspected")
        self.assertIn(junction, opened)
        self.assertNotIn(junction / "must-not-be-inspected", opened)
        self.assertNotIn(target, opened)

    def test_revalidation_rechecks_held_and_named_attributes_and_identity(self) -> None:
        with runner.DirectoryPins() as pins:
            pins.pin_chain(self.root)
            actual_identity = runner._identity
            calls = []

            def observe(handle: int, *, directory: bool) -> tuple[int, int]:
                calls.append(handle)
                return actual_identity(handle, directory=directory)

            with mock.patch.object(runner, "_identity", side_effect=observe):
                pins.revalidate()
            self.assertEqual(len(calls), len(pins.entries) * 2)
            handle, identity = pins.entries[self.root]
            pins.entries[self.root] = (handle, (identity[0], identity[1] + 1))
            with self.assertRaisesRegex(AssertionError, "identity changed"):
                pins.revalidate()

    def test_database_read_uses_no_follow_handle_and_blocks_inflight_replacement(self) -> None:
        state = self.root / "project/state"
        state.mkdir(parents=True)
        database = state / "project.sqlite3"
        database.write_bytes(b"synthetic protected header")
        with runner.DirectoryPins() as pins:
            pins.pin_chain(self.root)
            with mock.patch.object(pins, "revalidate", wraps=pins.revalidate) as validate:
                self.assertEqual(runner.read_database(database, pins), b"synthetic protected header")
                self.assertEqual(validate.call_count, 2, "direct read must validate before and after")
            self.assertIn(state, pins.entries)
            handle = runner._open_pinned(database, directory=False)
            try:
                runner._identity(handle, directory=False)
                with self.assertRaises(OSError):
                    database.rename(state / "replacement.sqlite3")
            finally:
                runner._KERNEL.CloseHandle(handle)

    def test_real_fresh_child_is_stopped_on_observed_drift_after_http_without_cleanup_request(self) -> None:
        with runner.DirectoryPins() as pins:
            pins.pin_chain(self.root)
            core = runner.ActualCore(self.root, pins)
            try:
                core.ready()
                events = []
                actual_validate = pins.revalidate
                actual_open = core.opener.open

                def validate() -> None:
                    events.append("validate")
                    actual_validate()

                def open_response(*args: object, **kwargs: object) -> object:
                    events.append("http")
                    return actual_open(*args, **kwargs)

                with (
                    mock.patch.object(pins, "revalidate", side_effect=validate),
                    mock.patch.object(core.opener, "open", side_effect=open_response),
                ):
                    self.assertEqual(core.request("GET", "/workflow-profiles/catalog")[0], 200)
                self.assertEqual(events, ["validate", "http", "validate"])

                def return_then_drift(*args: object, **kwargs: object) -> object:
                    response = actual_open(*args, **kwargs)
                    handle, identity = pins.entries[self.root]
                    # Synthetic identity-observation drift, not a filesystem
                    # attack on the child. The shutdown boundary is real.
                    pins.entries[self.root] = (handle, (identity[0], identity[1] + 1))
                    return response

                with (
                    mock.patch.object(core.opener, "open", side_effect=return_then_drift),
                    mock.patch.object(core.process.stdin, "write", wraps=core.process.stdin.write) as control,
                ):
                    with self.assertRaisesRegex(AssertionError, "identity changed"):
                        core.request("GET", "/workflow-profiles/catalog")
                    control.assert_not_called()  # No cleanup/shutdown command after drift.
                self.assertIsNotNone(core.process.poll())
                self.assertTrue(core._stopped)
                self.assertEqual(core.token, "")
            finally:
                core.stop()

    def test_http_precheck_drift_stops_without_sending_request(self) -> None:
        core = runner.ActualCore.__new__(runner.ActualCore)
        core.pins = mock.Mock()
        core.pins.revalidate.side_effect = AssertionError("synthetic identity changed")
        core.opener = mock.Mock()
        with mock.patch.object(core, "stop") as stop:
            with self.assertRaisesRegex(AssertionError, "identity changed"):
                core.request("GET", "/workflow-profiles/catalog")
            stop.assert_called_once_with(on_drift=True)
            core.opener.open.assert_not_called()

    def test_real_fresh_child_final_stop_drift_terminates_without_shutdown_write(self) -> None:
        with runner.DirectoryPins() as pins:
            pins.pin_chain(self.root)
            core = runner.ActualCore(self.root, pins)
            try:
                core.ready()
                handle, identity = pins.entries[self.root]
                # Synthetic observation drift immediately before the normal
                # final-stop path; the child and termination boundary are real.
                pins.entries[self.root] = (handle, (identity[0], identity[1] + 1))
                with mock.patch.object(core.process.stdin, "write", wraps=core.process.stdin.write) as control:
                    with self.assertRaisesRegex(AssertionError, "identity changed"):
                        core.stop()
                    control.assert_not_called()
                self.assertIsNotNone(core.process.poll())
                self.assertTrue(core._stopped)
                self.assertEqual(core.token, "")
            finally:
                core.stop()

    def test_environment_drops_inherited_python_network_and_profile_configuration(self) -> None:
        poison = {
            "PYTHONHOME": "unapproved",
            "PYTHONUSERBASE": "unapproved",
            "PYTHONPATH": "unapproved",
            "PYTHONSTARTUP": "unapproved",
            "PYTHONINSPECT": "1",
            "PYTHONOPTIMIZE": "2",
            "RO_CORE_BIND_HOST": "0.0.0.0",
            "RO_CORE_BIND_PORT": "9999",
            "RO_CORE_PROFILE": "hosted",
            "HTTP_PROXY": "unapproved",
            "USERPROFILE": "unapproved",
            "TEMP": "unapproved",
        }
        with mock.patch.dict(os.environ, poison):
            environment = runner.core_environment(self.root)
        expected = {
            "TEMP",
            "TMP",
            "RO_CORE_PROFILE",
            "RO_CORE_BIND_HOST",
            "RO_CORE_BIND_PORT",
            "RO_CORE_LOG_LEVEL",
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONNOUSERSITE",
            "PYTHONSAFEPATH",
            "PYTHONPATH",
        }
        self.assertEqual(set(environment) - {"SystemRoot", "WINDIR"}, expected)
        self.assertEqual(environment["TEMP"], str(self.root))
        self.assertEqual(environment["TMP"], str(self.root))
        self.assertEqual(environment["RO_CORE_BIND_HOST"], "127.0.0.1")
        self.assertEqual(environment["RO_CORE_BIND_PORT"], "0")
        self.assertEqual(environment["RO_CORE_PROFILE"], "local")
        self.assertEqual(
            environment["PYTHONPATH"].split(os.pathsep),
            [str(REPO / "services/core-api/src"), str(REPO / ".venv/Lib/site-packages")],
        )
        child = subprocess.run(
            [
                sys._base_executable,
                "-s",
                "-P",
                "-B",
                "-c",
                "import json,sys; print(json.dumps([sys.flags.no_user_site,sys.flags.safe_path,"
                "sys.dont_write_bytecode,sys.flags.optimize]))",
            ],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(child.returncode, 0)
        self.assertEqual(json.loads(child.stdout), [1, True, True, 0])

    def test_report_namespace_is_checked_before_filesystem_access(self) -> None:
        with mock.patch.object(Path, "exists", side_effect=AssertionError("unexpected filesystem access")):
            for path in (REPO / "outside.json", runner.REPORTS / "W9.A01.T01.json", runner.REPORTS / "../bad.json"):
                with (
                    self.subTest(name=path.name),
                    self.assertRaisesRegex(AssertionError, "scope denied|namespace denied"),
                ):
                    runner.report_target(path)

    def test_exclusive_report_publication_preserves_concurrent_writer(self) -> None:
        reports = self.root / "reports"
        reports.mkdir()
        report = reports / "W1.A09.T03.default-core-fresh-race.json"
        with mock.patch.object(runner, "REPORTS", reports):
            runner.report_target(report)
            report.write_text("concurrent synthetic witness", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "already exists"):
                runner.publish_report(report, {"unexpected": True})
            # Model a writer racing after the final existence check, not merely
            # before it. The real exclusive open must still preserve the bytes.
            with mock.patch.object(runner, "report_target", return_value=report), self.assertRaises(FileExistsError):
                runner.publish_report(report, {"unexpected": True})
            self.assertEqual(report.read_text(encoding="utf-8"), "concurrent synthetic witness")
            final = reports / "W1.A09.T03.default-core-fresh-success.json"
            runner.publish_report(final, {"synthetic": True})
            self.assertEqual(json.loads(final.read_text(encoding="utf-8")), {"synthetic": True})

    def test_native_resolver_checks_build_hash_and_manifest_on_both_sides(self) -> None:
        executable = self.root / "synthetic-not-executable.bin"
        executable.write_bytes(b"synthetic original")
        build = {"executableSha256": hashlib.sha256(executable.read_bytes()).hexdigest()}
        completed = subprocess.CompletedProcess([], 0, '{"synthetic":true}', "")
        # These doubles test binding control flow only, not actual PE validity
        # or a native resolver. Complete-mode uses the real manifest inspector.
        with mock.patch.object(native_helper, "assert_project_probe_manifest") as manifest:
            with mock.patch.object(runner.subprocess, "run", return_value=completed) as execute:
                self.assertEqual(runner.run_native_resolver(executable, build), {"synthetic": True})
                self.assertEqual(manifest.call_count, 2)
                self.assertEqual(execute.call_args.args[0], [str(executable), "--default-parent"])
            manifest.reset_mock()
            with mock.patch.object(runner.subprocess, "run", side_effect=subprocess.TimeoutExpired("synthetic", 1)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    runner.run_native_resolver(executable, build)
                self.assertEqual(manifest.call_count, 2)

            def replace(*_: object, **__: object) -> subprocess.CompletedProcess:
                executable.write_bytes(b"synthetic substituted")
                return completed

            with (
                mock.patch.object(runner.subprocess, "run", side_effect=replace),
                self.assertRaisesRegex(AssertionError, "differs from bound build"),
            ):
                runner.run_native_resolver(executable, build)
            with mock.patch.object(runner.subprocess, "run") as execute:
                with self.assertRaisesRegex(AssertionError, "differs from bound build"):
                    runner.run_native_resolver(executable, build)
                execute.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
