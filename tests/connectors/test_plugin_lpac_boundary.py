"""Actual Windows LPAC probe for the hostile connector process boundary."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services/core-api/src"))


class PluginLPACBoundaryTests(unittest.TestCase):
    def test_loopback_report_does_not_promote_startup_failure_to_connect_denial(self) -> None:
        from workers.windows.lpac_launcher import LPACError, _validated_loopback_observation

        startup_failure = {
            "startupCode": 10107,
            "connectAttempted": False,
            "connectOutcome": "not-tested",
            "connectErrorCode": None,
        }
        self.assertEqual(_validated_loopback_observation(startup_failure), startup_failure)
        with self.assertRaisesRegex(LPACError, "observation-invalid"):
            _validated_loopback_observation("denied")
        with self.assertRaisesRegex(LPACError, "connection-not-denied"):
            _validated_loopback_observation(
                {"startupCode": 0, "connectAttempted": True, "connectOutcome": "allowed", "connectErrorCode": None}
            )

    @unittest.skipUnless(os.name == "nt", "Windows x64 LPAC qualification")
    def test_packaged_worker_is_lpac_and_denies_ambient_authority(self) -> None:
        from workers.windows.lpac_launcher import run_probe

        with tempfile.TemporaryDirectory(prefix="lpac-test-", dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            package = root / "package"
            report = root / "package.json"
            subprocess.run(
                [
                    sys.executable,
                    str(REPO / "tools" / "plugin_worker_probe_build.py"),
                    "--output",
                    str(package),
                    "--report",
                    str(report),
                ],
                cwd=REPO,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            inventory = json.loads(report.read_text(encoding="utf-8"))

            unrelated = root / "unrelated-project-secret.txt"
            unrelated.write_text("synthetic-secret", encoding="utf-8")
            writable = root / "outside-write.txt"
            with socket.socket() as server:
                server.bind(("127.0.0.1", 0))
                server.listen(1)
                server.settimeout(1)
                with socket.create_connection(server.getsockname(), timeout=1):
                    control, _ = server.accept()
                    control.close()
                with patch.dict(os.environ, {"RO_LPAC_TEST_SECRET": "synthetic-secret"}):
                    result = run_probe(
                        package,
                        inventory,
                        read_path=unrelated,
                        write_path=writable,
                        loopback_port=server.getsockname()[1],
                    )
                server.settimeout(0.3)
                with self.assertRaises(socket.timeout):
                    server.accept()

            self.assertIs(result["token"]["appContainer"], True)
            self.assertIs(result["token"]["lessPrivileged"], True)
            self.assertEqual(result["token"]["capabilityCount"], 0)
            probes = result["probes"]
            loopback = probes["directLoopback"]
            child_breakaway = probes["childBreakaway"]
            self.assertEqual(child_breakaway["attempted"], True)
            self.assertEqual(child_breakaway["outcome"], "denied")
            self.assertIsInstance(child_breakaway["errorCode"], int)
            self.assertIsInstance(loopback["startupCode"], int)
            self.assertIsInstance(loopback["connectAttempted"], bool)
            self.assertIn(loopback["connectOutcome"], {"denied", "not-tested"})
            if loopback["connectAttempted"]:
                self.assertEqual(loopback["connectOutcome"], "denied")
            else:
                self.assertEqual(loopback["connectOutcome"], "not-tested")
            self.assertEqual(
                {key: value for key, value in probes.items() if key not in {"directLoopback", "childBreakaway"}},
                {
                    "unrelatedRead": "denied",
                    "outsideWrite": "denied",
                    "profileWrite": "denied",
                    "tempWrite": "denied",
                    "parentEnvironmentSecret": "denied",
                },
            )
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "synthetic-secret")
            self.assertFalse(writable.exists())

    def test_control_frame_rejects_oversize_duplicate_and_wrong_job(self) -> None:
        from workers.windows.protocol import FrameError, decode_frame, encode_frame

        nonce = "a" * 32
        encoded = encode_frame({"protocolVersion": "1.0", "jobNonce": nonce, "sequence": 0, "operation": "probe"})
        self.assertEqual(decode_frame(encoded, expected_nonce=nonce, expected_sequence=0)["operation"], "probe")
        with self.assertRaisesRegex(FrameError, "nonce"):
            decode_frame(encoded, expected_nonce="b" * 32, expected_sequence=0)
        with self.assertRaisesRegex(FrameError, "sequence"):
            decode_frame(encoded, expected_nonce=nonce, expected_sequence=1)
        duplicate = (
            b'{"protocolVersion":"1.0","jobNonce":"'
            + nonce.encode("ascii")
            + b'","sequence":0,"operation":"probe","operation":"probe"}'
        )
        with self.assertRaisesRegex(FrameError, "duplicate"):
            decode_frame(len(duplicate).to_bytes(4, "big") + duplicate, expected_nonce=nonce, expected_sequence=0)
        with self.assertRaisesRegex(FrameError, "length"):
            decode_frame((1_048_577).to_bytes(4, "big"), expected_nonce=nonce, expected_sequence=0)

    def test_binary_frame_has_an_independent_limit_and_exact_length(self) -> None:
        from io import BytesIO

        from workers.windows.protocol import MAX_BINARY_FRAME, FrameError, read_binary_frame, write_binary_frame

        stream = BytesIO()
        write_binary_frame(stream, b"synthetic")
        stream.seek(0)
        self.assertEqual(read_binary_frame(stream), b"synthetic")
        with self.assertRaisesRegex(FrameError, "binary-frame-length-invalid"):
            write_binary_frame(BytesIO(), b"a" * (MAX_BINARY_FRAME + 1))
        with self.assertRaisesRegex(FrameError, "binary-frame-length-invalid"):
            read_binary_frame(BytesIO((MAX_BINARY_FRAME + 1).to_bytes(4, "big")))
        with self.assertRaisesRegex(FrameError, "binary-frame-truncated"):
            read_binary_frame(BytesIO((4).to_bytes(4, "big") + b"ab"))

    def test_worker_exit_wait_remains_cancellable_after_result_frame(self) -> None:
        import time

        from workers.windows.connector_launcher import _wait_for_worker_exit
        from workers.windows.lpac_launcher import LPACError

        class HungWorker:
            waits = 0

            def WaitForSingleObject(self, _handle: int, timeout_ms: int) -> int:
                self.waits += 1
                self.assert_timeout(timeout_ms)
                return 0x102

            @staticmethod
            def assert_timeout(timeout_ms: int) -> None:
                if not 1 <= timeout_ms <= 50:
                    raise AssertionError("worker wait exceeded cancellation poll bound")

        kernel = HungWorker()
        with self.assertRaisesRegex(LPACError, "worker-cancelled"):
            _wait_for_worker_exit(kernel, 1, time.monotonic() + 1, lambda: kernel.waits >= 1)
        self.assertEqual(kernel.waits, 1)

    def test_fixed_worker_uses_bounded_broker_frames_without_plugin_paths(self) -> None:
        import hashlib
        import threading

        from workers.windows.plugin_worker import run_worker
        from workers.windows.protocol import read_binary_frame, read_frame, write_binary_frame, write_frame

        source = (
            b"def invoke(input_data, broker, operation):\n"
            b"    assert operation == 'lookup'\n"
            b"    response = broker({'operation': 'lookup', 'identifier': input_data.decode('ascii')})\n"
            b"    return response + b':done'\n"
        )
        nonce = "a" * 32
        with tempfile.TemporaryDirectory(prefix="worker-protocol-", dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            entry = root / "plugin" / "connector.py"
            entry.parent.mkdir()
            entry.write_bytes(source)
            (root / "plugin-assets").mkdir()
            to_worker_read, to_worker_write = os.pipe()
            from_worker_read, from_worker_write = os.pipe()
            errors: list[BaseException] = []

            def worker() -> None:
                with (
                    os.fdopen(to_worker_read, "rb", buffering=0) as incoming,
                    os.fdopen(from_worker_write, "wb", buffering=0) as outgoing,
                ):
                    try:
                        run_worker(incoming, outgoing, asset_root=root)
                    except BaseException as exc:
                        errors.append(exc)

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            with (
                os.fdopen(to_worker_write, "wb", buffering=0) as outgoing,
                os.fdopen(from_worker_read, "rb", buffering=0) as incoming,
            ):
                request = {
                    "protocolVersion": "1.0",
                    "jobNonce": nonce,
                    "sequence": 0,
                    "operation": "invoke",
                    "invocationId": "synthetic-1",
                    "connectorOperation": "lookup",
                    "inputSha256": hashlib.sha256(b"record-1").hexdigest(),
                    "pluginSha256": hashlib.sha256(source).hexdigest(),
                    "inputLength": 8,
                }
                write_frame(outgoing, request)
                write_binary_frame(outgoing, b"record-1")
                call = read_frame(incoming, expected_nonce=nonce, expected_sequence=1)
                self.assertEqual(
                    call,
                    {
                        "protocolVersion": "1.0",
                        "jobNonce": nonce,
                        "sequence": 1,
                        "operation": "broker-call",
                        "call": {"operation": "lookup", "identifier": "record-1"},
                    },
                )
                reply = b"synthetic-metadata"
                write_frame(
                    outgoing,
                    {
                        "protocolVersion": "1.0",
                        "jobNonce": nonce,
                        "sequence": 2,
                        "operation": "broker-result",
                        "responseLength": len(reply),
                        "responseSha256": hashlib.sha256(reply).hexdigest(),
                    },
                )
                write_binary_frame(outgoing, reply)
                result = read_frame(incoming, expected_nonce=nonce, expected_sequence=3)
                self.assertEqual(result["operation"], "invoke-result")
                self.assertEqual(read_binary_frame(incoming), b"synthetic-metadata:done")
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])

    def test_application_signed_runtime_rejects_tamper_and_self_trust(self) -> None:
        import hashlib

        from nacl.signing import SigningKey

        from workers.windows.runtime_inventory import (
            WORKER_IMAGE_PATH,
            RuntimeInventoryError,
            SignedWorkerRuntime,
            verify_worker_runtime,
        )

        with tempfile.TemporaryDirectory(prefix="worker-inventory-", dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            image = root / WORKER_IMAGE_PATH
            image.parent.mkdir()
            image.write_bytes(b"synthetic-signed-image")
            inventory = json.dumps(
                {
                    "schemaVersion": "1.0",
                    "documentType": "application-signed-lpac-worker-package",
                    "imagePath": WORKER_IMAGE_PATH,
                    "files": [{"path": WORKER_IMAGE_PATH, "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            key = SigningKey(b"\x56" * 32)  # A known synthetic test key, never installed as product trust.
            runtime = SignedWorkerRuntime(root, inventory, key.sign(inventory).signature, bytes(key.verify_key))
            self.assertEqual(verify_worker_runtime(runtime), image)
            with self.assertRaisesRegex(RuntimeInventoryError, "signature-invalid"):
                verify_worker_runtime(SignedWorkerRuntime(root, inventory, runtime.signature, b"\x57" * 32))
            image.write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeInventoryError, "hash-mismatch"):
                verify_worker_runtime(runtime)

    def test_application_signed_runtime_rejects_redirected_root_and_ancestor(self) -> None:
        import hashlib

        from nacl.signing import SigningKey

        from workers.windows.runtime_inventory import (
            WORKER_IMAGE_PATH,
            RuntimeInventoryError,
            SignedWorkerRuntime,
            verify_worker_runtime,
        )

        with tempfile.TemporaryDirectory(prefix="worker-redirect-", dir=REPO / "artifacts/tmp") as temporary:
            parent = Path(temporary)
            real = parent / "real"
            package_root = real / "package"
            image = package_root / WORKER_IMAGE_PATH
            image.parent.mkdir(parents=True)
            image.write_bytes(b"synthetic-signed-image")
            inventory = json.dumps(
                {
                    "schemaVersion": "1.0",
                    "documentType": "application-signed-lpac-worker-package",
                    "imagePath": WORKER_IMAGE_PATH,
                    "files": [{"path": WORKER_IMAGE_PATH, "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            key = SigningKey(b"\x56" * 32)
            signature = key.sign(inventory).signature
            public = bytes(key.verify_key)
            self.assertEqual(
                verify_worker_runtime(SignedWorkerRuntime(package_root, inventory, signature, public)), image
            )
            alias_root = parent / "alias-root"
            alias_ancestor = parent / "alias-parent"
            for alias, target in ((alias_root, package_root), (alias_ancestor, real)):
                try:
                    alias.symlink_to(target, target_is_directory=True)
                except OSError:
                    junction = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if junction.returncode:
                        self.skipTest("directory symlinks and junctions are unavailable for this Windows token")
            with self.assertRaisesRegex(RuntimeInventoryError, "redirect-denied"):
                verify_worker_runtime(SignedWorkerRuntime(alias_root, inventory, signature, public))
            with self.assertRaisesRegex(RuntimeInventoryError, "redirect-denied"):
                verify_worker_runtime(SignedWorkerRuntime(alias_ancestor / "package", inventory, signature, public))

    @unittest.skipUnless(os.name == "nt", "Windows x64 LPAC qualification")
    def test_signed_product_worker_denies_ambient_authority(self) -> None:
        """Run the fixed, signed product worker when a local signed bundle is supplied."""

        import secrets

        from nacl.signing import SigningKey
        from research_observatory_core.connectors.plugin_manifest import verify_plugin_package

        from tests.connectors.test_plugin_manifest_contract import (
            PATH,
            PUBLISHER_ID,
            _manifest_bytes,
            _manifest_document,
        )
        from workers.windows import recovery_guardian
        from workers.windows.connector_launcher import run_connector
        from workers.windows.runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime

        build_path = os.environ.get("RO_W2_SIGNED_WORKER_BUILD")
        if not build_path:
            self.skipTest("local signed worker bundle not installed for native qualification")
        build = Path(build_path).resolve(strict=True)
        runtime = SignedWorkerRuntime(
            build / "package",
            (build / "inventory.json").read_bytes(),
            (build / "inventory.sig").read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
        sidecar = os.environ.get("RO_W2_CORE_SIDECAR_GUARDIAN")
        guardian_command = (
            [str(Path(sidecar).resolve(strict=True)), "--plugin-acl-guardian"]
            if sidecar
            else recovery_guardian._guardian_command()
        )
        with tempfile.TemporaryDirectory(prefix="product-lpac-", dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            private = root / "unrelated-project-secret.txt"
            other_project = root / "other-project-sentinel.txt"
            vault = root / "vault-sentinel.txt"
            private.write_bytes(b"synthetic-secret")
            other_project.write_bytes(b"synthetic-secret")
            vault.write_bytes(b"synthetic-secret")
            outside = root / "outside-write.txt"
            runtime_parent_write = Path(os.environ["LOCALAPPDATA"]) / "RoWorker" / "synthetic-outside-runtime.txt"
            source = """
def invoke(input_data, broker, operation):
    import json, os, sys
    from pathlib import Path
    observed = {}
    def attempt(name, action):
        try:
            action()
        except BaseException as error:
            observed[name] = "denied:" + type(error).__name__
        else:
            observed[name] = "allowed"
    entry = Path(__file__)
    attempt("unrelatedRead", lambda: Path(__PRIVATE__).read_bytes())
    attempt("otherProjectRead", lambda: Path(__OTHER_PROJECT__).read_bytes())
    attempt("vaultRead", lambda: Path(__VAULT__).read_bytes())
    attempt("outsideWrite", lambda: Path(__OUTSIDE__).write_bytes(b"synthetic-only"))
    attempt("runtimeParentWrite", lambda: Path(__RUNTIME_PARENT_WRITE__).write_bytes(b"synthetic-only"))
    attempt("profileWrite", lambda: (Path(os.environ["LOCALAPPDATA"]) / "probe.txt").write_bytes(b"x"))
    attempt("tempWrite", lambda: (Path(os.environ["TEMP"]) / "probe.txt").write_bytes(b"x"))
    attempt("runtimeAppend", lambda: entry.open("ab").write(b"x"))
    attempt("runtimeOverwrite", lambda: entry.open("r+b").write(b"x"))
    attempt("runtimeAds", lambda: open(str(entry) + ":synthetic-stream", "xb").write(b"x"))
    attempt("runtimeDelete", lambda: entry.unlink())
    attempt("runtimeRename", lambda: entry.rename(entry.with_name("renamed.py")))
    attempt("child", lambda: os.spawnv(os.P_NOWAIT, sys.executable, [sys.executable]))
    observed["parentSecret"] = "leaked" if os.getenv("RO_LPAC_TEST_SECRET") else "denied"
    try:
        import socket
    except BaseException as error:
        observed["loopback"] = "startup-failed:" + type(error).__name__
    else:
        try:
            socket.create_connection(("127.0.0.1", __PORT__), timeout=0.3).close()
        except OSError:
            observed["loopback"] = "connect-denied"
        else:
            observed["loopback"] = "connect-allowed"
    observed["brokerResponse"] = broker(
        {"operation": "lookup", "identifier": input_data.decode("ascii")}
    ).decode("ascii")
    return json.dumps(observed, sort_keys=True).encode("ascii")
"""
            with socket.socket() as server:
                server.bind(("127.0.0.1", 0))
                server.listen(1)
                server.settimeout(0.3)
                source_bytes = (
                    source.replace("__PRIVATE__", repr(str(private)))
                    .replace("__OTHER_PROJECT__", repr(str(other_project)))
                    .replace("__VAULT__", repr(str(vault)))
                    .replace("__OUTSIDE__", repr(str(outside)))
                    .replace("__RUNTIME_PARENT_WRITE__", repr(str(runtime_parent_write)))
                    .replace("__PORT__", str(server.getsockname()[1]))
                    .encode("utf-8")
                )
                manifest = _manifest_bytes(_manifest_document(package_file=source_bytes))
                signing_key = SigningKey(b"\x42" * 32)
                package = verify_plugin_package(
                    manifest,
                    signing_key.sign(manifest).signature,
                    {PATH: source_bytes},
                    {PUBLISHER_ID: bytes(signing_key.verify_key)},
                )
                calls: list[dict[str, object]] = []

                def record_broker_call(call: dict[str, object], history: list[dict[str, object]]) -> bytes:
                    history.append(call)
                    return b"synthetic-metadata"

                with (
                    patch.dict(os.environ, {"RO_LPAC_TEST_SECRET": "synthetic-secret"}),
                    patch.object(recovery_guardian, "_guardian_command", return_value=guardian_command),
                ):
                    result = run_connector(
                        runtime,
                        package,
                        {PATH: source_bytes},
                        job_nonce=secrets.token_hex(16),
                        invocation_id="synthetic-product-boundary",
                        operation="lookup",
                        input_data=b"synthetic-1",
                        broker_callback=lambda call: record_broker_call(call, calls),
                    )
                with self.assertRaises(socket.timeout):
                    server.accept()

            observed = json.loads(result.output)
            self.assertEqual(result.token["appContainer"], True)
            self.assertEqual(result.token["lessPrivileged"], True)
            self.assertEqual(result.token["capabilityCount"], 0)
            self.assertEqual(result.token["integrityLevelRid"], 4096)
            self.assertEqual(result.broker_calls, 1)
            self.assertEqual(calls, [{"operation": "lookup", "identifier": "synthetic-1"}])
            for name in (
                "unrelatedRead",
                "otherProjectRead",
                "vaultRead",
                "outsideWrite",
                "runtimeParentWrite",
                "profileWrite",
                "tempWrite",
                "runtimeAppend",
                "runtimeOverwrite",
                "runtimeAds",
                "runtimeDelete",
                "runtimeRename",
                "child",
            ):
                self.assertTrue(observed[name].startswith("denied:"), (name, observed[name]))
            self.assertNotEqual(observed["loopback"], "connect-allowed")
            self.assertEqual(observed["parentSecret"], "denied")
            self.assertEqual(observed["brokerResponse"], "synthetic-metadata")
            self.assertEqual(private.read_bytes(), b"synthetic-secret")
            self.assertEqual(other_project.read_bytes(), b"synthetic-secret")
            self.assertEqual(vault.read_bytes(), b"synthetic-secret")
            self.assertFalse(outside.exists())
            self.assertFalse(runtime_parent_write.exists())

    def _prove_guardian_recovery(self, phase: str, *, delayed_lock: bool = False) -> None:
        """Kill Core before or after sealing; guardian must own exact cleanup."""

        import ctypes
        import re
        import shutil
        import time
        from ctypes import wintypes

        from workers.windows import lpac_launcher as win
        from workers.windows.no_write_acl import _open_saved, _sddl, _security_api, _tree
        from workers.windows.recovery_guardian import _restore_present

        build_value = os.environ.get("RO_W2_SIGNED_WORKER_BUILD")
        if not build_value:
            self.skipTest("local signed worker bundle not installed for native qualification")
        build = Path(build_value).resolve(strict=True)
        sidecar = os.environ.get("RO_W2_CORE_SIDECAR_GUARDIAN", "-")
        if sidecar != "-" and not Path(sidecar).is_file():
            self.fail("configured frozen Core guardian image is unavailable")
        kernel, advapi, userenv, _ = win._api()
        _security_api(kernel, advapi)
        kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        kernel.IsProcessInJob.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        profile_saved = []
        runtime_saved = []
        profile_root = runtime_root = unrelated = None
        profile_name = None
        child = None
        job = None
        lock_handle = None
        worker_handle = None
        with tempfile.TemporaryDirectory(prefix="lpac-core-crash-", dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            marker = root / "state.json"
            ack = root / "parent-holds-backup-handles"
            worker_ack = root / "parent-holds-worker-handle"
            gate = root / "assigned-to-core-job"
            try:
                child = subprocess.Popen(
                    [
                        sys.executable,
                        str(REPO / "tests/connectors/fixtures/lpac_core_crash.py"),
                        str(build),
                        str(marker),
                        str(ack),
                        str(gate),
                        sidecar,
                        phase,
                    ],
                    cwd=REPO,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=0x08000000,
                )
                job = kernel.CreateJobObjectW(None, None)
                self.assertTrue(job)
                limits = win._ExtendedLimitInformation()
                limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x0800  # kill-on-close, explicit breakaway
                self.assertTrue(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
                child_handle = cast(Any, child)._handle  # Windows Popen handle is runtime-only.
                self.assertTrue(kernel.AssignProcessToJobObject(job, child_handle))
                in_job = wintypes.BOOL()
                self.assertTrue(kernel.IsProcessInJob(child_handle, job, ctypes.byref(in_job)))
                self.assertTrue(in_job.value)
                gate.touch()
                deadline = time.monotonic() + 15
                while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.025)
                self.assertTrue(marker.exists(), "Core did not reach the guardian boundary")
                state = json.loads(marker.read_text(encoding="utf-8"))
                self.assertEqual(state["stage"], "guardian-created" if phase == "pre-seal" else "guardian-sealed")
                profile_name = state["profileName"]
                profile_root = Path(state["profileRoot"])
                runtime_root = Path(state["runtimeRoot"])
                local = Path(os.environ["LOCALAPPDATA"]).resolve(strict=True)
                runtime_parent = (local / "RoWorker").resolve(strict=True)
                self.assertRegex(profile_name, r"\AResearchObservatory\.PluginProbe\.[0-9a-f]{24}\Z")
                self.assertEqual(profile_root.name.casefold(), profile_name.casefold())
                self.assertEqual(profile_root.resolve(strict=True).parent, (local / "Packages").resolve(strict=True))
                self.assertRegex(runtime_root.name, r"\A[0-9a-f]{16}\Z")
                self.assertEqual(runtime_root.resolve(strict=True).parent, runtime_parent)
                self.assertFalse(profile_root.is_symlink() or profile_root.is_junction())
                self.assertFalse(runtime_root.is_symlink() or runtime_root.is_junction())
                guardian = kernel.OpenProcess(0x1000, False, state["guardianPid"])
                self.assertTrue(guardian)
                try:
                    in_job = wintypes.BOOL()
                    self.assertTrue(kernel.IsProcessInJob(guardian, job, ctypes.byref(in_job)))
                    self.assertFalse(in_job.value, "guardian remained in Core's kill-on-close Job")
                finally:
                    kernel.CloseHandle(guardian)
                user_sid = win._current_user_sid(advapi, kernel)
                if phase == "post-seal":
                    for path in _tree(profile_root):
                        profile_saved.append(_open_saved(kernel, advapi, path, user_sid))
                    for path in _tree(runtime_root):
                        runtime_saved.append(_open_saved(kernel, advapi, path, user_sid))
                if delayed_lock:
                    locked = next(path for path in _tree(runtime_root) if path.is_file())
                    lock_handle = kernel.CreateFileW(str(locked), 0x80000000, 3, None, 3, 0, None)
                    self.assertTrue(
                        lock_handle and lock_handle != ctypes.c_void_p(-1).value,
                        f"test lock open failed: {ctypes.get_last_error()}",
                    )
                unrelated = runtime_parent / f"synthetic-unrelated-{os.urandom(8).hex()}.txt"
                unrelated.write_bytes(b"synthetic-only")
                ack.touch()
                if phase == "post-seal":
                    worker_deadline = time.monotonic() + 15
                    while time.monotonic() < worker_deadline and child.poll() is None:
                        state = json.loads(marker.read_text(encoding="utf-8"))
                        if "workerPid" in state:
                            break
                        time.sleep(0.025)
                    self.assertIn("workerPid", state, "Core did not expose the suspended LPAC worker PID")
                    worker_handle = kernel.OpenProcess(0x101000, False, state["workerPid"])
                    self.assertTrue(worker_handle, "could not retain worker SYNCHRONIZE handle")
                    in_job = wintypes.BOOL()
                    self.assertTrue(kernel.IsProcessInJob(worker_handle, job, ctypes.byref(in_job)))
                    self.assertTrue(in_job.value, "LPAC worker escaped the Core kill-on-close Job")
                    worker_ack.touch()
                self.assertEqual(child.wait(timeout=20), 86 if phase == "pre-seal" else 87)
                if phase == "post-seal":
                    state = json.loads(marker.read_text(encoding="utf-8"))
                    self.assertEqual(state["stage"], "worker-broker-called-core-crashed")
                kernel.CloseHandle(job)
                job = None  # Tauri's kill-on-close boundary now terminates the worker tree.
                if worker_handle:
                    self.assertEqual(kernel.WaitForSingleObject(worker_handle, 5000), 0)
                if profile_saved or runtime_saved:
                    restore_deadline = time.monotonic() + 15
                    while time.monotonic() < restore_deadline:
                        restored = all(
                            _sddl(kernel, advapi, item.handle) == item.sddl for item in (*profile_saved, *runtime_saved)
                        )
                        if restored:
                            break
                        time.sleep(0.05)
                    else:
                        self.fail("guardian did not restore the exact original ACLs")
                    # The test parent only observed restoration. Close its
                    # independent safety handles so they cannot block delete.
                    for item in (*profile_saved, *runtime_saved):
                        kernel.CloseHandle(item.handle)
                        kernel.LocalFree(item.descriptor)
                    profile_saved.clear()
                    runtime_saved.clear()
                if delayed_lock:
                    # A lock exceeding the old ten-second timeout must leave
                    # the guardian alive with exact cleanup ownership.
                    time.sleep(11)
                    guardian = kernel.OpenProcess(0x1000, False, state["guardianPid"])
                    self.assertTrue(guardian, "guardian exited while deletion was blocked")
                    kernel.CloseHandle(guardian)
                    self.assertTrue(runtime_root.exists())
                    kernel.CloseHandle(lock_handle)
                    lock_handle = None
                deadline = time.monotonic() + 20
                while (profile_root.exists() or runtime_root.exists()) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(profile_root.exists(), "guardian left the exact LPAC profile")
                self.assertFalse(runtime_root.exists(), "guardian left the exact copied runtime")
                self.assertEqual(unrelated.read_bytes(), b"synthetic-only")
            finally:
                if child and child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                if child:
                    if child.stdout:
                        child.stdout.close()
                    if child.stderr:
                        child.stderr.close()
                if job:
                    kernel.CloseHandle(job)
                if lock_handle:
                    kernel.CloseHandle(lock_handle)
                if worker_handle:
                    kernel.CloseHandle(worker_handle)
                # The test parent keeps independent pre-lockdown handles so an
                # adverse guardian result cannot strand a disposable ACL.
                _restore_present(kernel, advapi, profile_saved)
                _restore_present(kernel, advapi, runtime_saved)
                if profile_name and profile_root and profile_root.exists():
                    self.assertEqual(userenv.DeleteAppContainerProfile(profile_name), 0)
                if runtime_root and runtime_root.exists():
                    resolved = runtime_root.resolve(strict=True)
                    parent = (Path(os.environ["LOCALAPPDATA"]).resolve(strict=True) / "RoWorker").resolve(strict=True)
                    if resolved.parent != parent or re.fullmatch(r"[0-9a-f]{16}", resolved.name) is None:
                        raise AssertionError("test runtime cleanup target changed")
                    shutil.rmtree(resolved)
                if unrelated and unrelated.exists():
                    unrelated.unlink()

    @unittest.skipUnless(os.name == "nt", "Windows x64 LPAC qualification")
    def test_guardian_recovers_exact_job_after_core_crash(self) -> None:
        self._prove_guardian_recovery("post-seal")

    @unittest.skipUnless(os.name == "nt", "Windows x64 LPAC qualification")
    def test_guardian_recovers_before_seal_after_core_crash(self) -> None:
        self._prove_guardian_recovery("pre-seal")

    @unittest.skipUnless(os.name == "nt", "Windows x64 LPAC qualification")
    def test_guardian_retries_after_delayed_os_lock(self) -> None:
        self._prove_guardian_recovery("post-seal", delayed_lock=True)

    def test_product_launcher_rejects_unpinned_or_uninstalled_runtime(self) -> None:
        from research_observatory_core.connectors.plugin_manifest import VerifiedPluginPackage

        from workers.windows.connector_launcher import run_connector
        from workers.windows.lpac_launcher import LPACError
        from workers.windows.runtime_inventory import (
            RuntimeInventoryError,
            SignedWorkerRuntime,
            load_installed_worker_runtime,
        )

        with (
            patch.object(sys, "frozen", False, create=True),
            self.assertRaisesRegex(RuntimeInventoryError, "worker-runtime-unavailable"),
        ):
            load_installed_worker_runtime()
        unpinned = SignedWorkerRuntime(REPO, b"{}", b"\0" * 64, b"\x57" * 32)
        with self.assertRaisesRegex(LPACError, "application-pin-mismatch"):
            run_connector(
                unpinned,
                cast(VerifiedPluginPackage, None),
                {},
                job_nonce="0" * 32,
                invocation_id="synthetic",
                operation="lookup",
                input_data=b"",
                broker_callback=lambda _: b"",
            )


if __name__ == "__main__":
    unittest.main()
