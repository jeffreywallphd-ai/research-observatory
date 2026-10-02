"""Synthetic child Core process for the signed LPAC crash-recovery test."""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from pathlib import Path

from nacl.signing import SigningKey

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / "services/core-api/src"))

from research_observatory_core.connectors.plugin_manifest import verify_plugin_package  # noqa: E402

from tests.connectors.test_plugin_manifest_contract import (  # noqa: E402
    PATH,
    PUBLISHER_ID,
    _manifest_bytes,
    _manifest_document,
)
from workers.windows import connector_launcher, recovery_guardian  # noqa: E402
from workers.windows.runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime  # noqa: E402


def main() -> int:
    build, marker, ack, gate, sidecar = (Path(value) for value in sys.argv[1:6])
    phase = sys.argv[6]
    if phase not in {"pre-seal", "post-seal"}:
        return 4
    deadline = time.monotonic() + 15
    while not gate.exists() and time.monotonic() < deadline:
        time.sleep(0.025)
    if not gate.exists():
        return 3
    runtime = SignedWorkerRuntime(
        build / "package",
        (build / "inventory.json").read_bytes(),
        (build / "inventory.sig").read_bytes(),
        APPLICATION_INVENTORY_PUBLIC_KEY,
    )
    if sidecar != Path("-"):
        recovery_guardian._guardian_command = lambda: [str(sidecar), "--plugin-acl-guardian"]
    source = (
        b"def invoke(input_data, broker, operation):\n"
        b"    return broker({'operation': 'lookup', 'identifier': input_data.decode('ascii')})\n"
    )
    manifest = _manifest_bytes(_manifest_document(package_file=source))
    signing_key = SigningKey(b"\x42" * 32)
    package = verify_plugin_package(
        manifest,
        signing_key.sign(manifest).signature,
        {PATH: source},
        {PUBLISHER_ID: bytes(signing_key.verify_key)},
    )
    worker_ack = ack.with_name("parent-holds-worker-handle")

    def publish(state):
        pending = marker.with_suffix(".pending")
        pending.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        os.replace(pending, marker)

    def publish_and_pause(guardian, stage):
        publish(
            {
                "profileName": guardian.name,
                "profileRoot": str(guardian.profile.parent),
                "runtimeRoot": str(guardian.runtime),
                "guardianPid": guardian.process.pid,
                "stage": stage,
            }
        )
        deadline = time.monotonic() + 15
        while not ack.exists() and time.monotonic() < deadline:
            time.sleep(0.025)
        if not ack.exists():
            raise RuntimeError("test-parent-safety-backup-unavailable")

    original_start = connector_launcher.start_guardian

    def start_and_pause():
        guardian = original_start()
        if phase == "pre-seal":
            publish_and_pause(guardian, "guardian-created")
            os._exit(86)
        return guardian

    connector_launcher.start_guardian = start_and_pause
    original_seal = recovery_guardian.GuardianProcess.seal

    def seal_and_pause(self):
        original_seal(self)
        if phase == "post-seal":
            publish_and_pause(self, "guardian-sealed")

    setattr(recovery_guardian.GuardianProcess, "seal", seal_and_pause)  # noqa: B010 - deliberate fault injection
    original_token = connector_launcher.win._token

    def token_and_pause(advapi, kernel, process, sid_text):
        token = original_token(advapi, kernel, process, sid_text)
        from ctypes import wintypes

        kernel.GetProcessId.argtypes = [wintypes.HANDLE]
        kernel.GetProcessId.restype = wintypes.DWORD
        state = json.loads(marker.read_text(encoding="utf-8"))
        state["workerPid"] = kernel.GetProcessId(process)
        publish(state)
        deadline = time.monotonic() + 15
        while not worker_ack.exists() and time.monotonic() < deadline:
            time.sleep(0.025)
        if not worker_ack.exists():
            raise RuntimeError("test-parent-worker-handle-unavailable")
        return token

    connector_launcher.win._token = token_and_pause

    def crash_after_worker_broker_call(_call):
        observed = json.loads(marker.read_text(encoding="utf-8"))
        observed["stage"] = "worker-broker-called-core-crashed"
        publish(observed)
        os._exit(87)

    connector_launcher.run_connector(
        runtime,
        package,
        {PATH: source},
        job_nonce=secrets.token_hex(16),
        invocation_id="synthetic-core-crash",
        operation="lookup",
        input_data=b"synthetic-1",
        broker_callback=crash_after_worker_broker_call,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
