"""Run the published sample in the signed Windows LPAC worker with synthetic broker data."""

from __future__ import annotations

import json
import os
import secrets
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_manifest import verify_plugin_package  # noqa: E402
from research_observatory_core.connectors.plugin_result import PluginWorkerPage  # noqa: E402

from workers.windows import recovery_guardian  # noqa: E402
from workers.windows.connector_launcher import WorkerResult, run_connector  # noqa: E402
from workers.windows.lpac_launcher import LPACError  # noqa: E402
from workers.windows.runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime  # noqa: E402

SAMPLE = REPO / "plugins/connectors/sample_repository"
ENTRY = "plugin/connector.py"
SEARCH_CASES = (
    SAMPLE / "fixtures/search-page-1.case.json",
    SAMPLE / "fixtures/search-page-2.case.json",
)


@unittest.skipUnless(os.name == "nt", "Windows x64 LPAC qualification")
class SampleConnectorNativeLpacTests(unittest.TestCase):
    def setUp(self) -> None:
        build_path = os.environ.get("RO_W2_SIGNED_WORKER_BUILD")
        guardian_path = os.environ.get("RO_W2_CORE_SIDECAR_GUARDIAN")
        if not build_path or not guardian_path:
            self.skipTest("locally signed worker and frozen Core guardian are required")
        build = Path(build_path).resolve(strict=True)
        guardian = Path(guardian_path).resolve(strict=True)
        self.runtime = SignedWorkerRuntime(
            build / "package",
            (build / "inventory.json").read_bytes(),
            (build / "inventory.sig").read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
        self.guardian_command = [str(guardian), "--plugin-acl-guardian"]
        source = (SAMPLE / ENTRY).read_bytes()
        manifest = (SAMPLE / "manifest.json").read_bytes()
        signing_key = SigningKey(b"\x5d" * 32)
        self.package = verify_plugin_package(
            manifest,
            signing_key.sign(manifest).signature,
            {ENTRY: source},
            {"sample-repository-publisher": bytes(signing_key.verify_key)},
        )
        self.package_files = {ENTRY: source}

    def _run_case(self, case: dict, response: dict) -> tuple[WorkerResult, list[dict]]:
        calls: list[dict] = []

        def broker(call: dict) -> bytes:
            calls.append(call)
            return json.dumps(response, separators=(",", ":")).encode("utf-8")

        with patch.object(recovery_guardian, "_guardian_command", return_value=self.guardian_command):
            result = run_connector(
                self.runtime,
                self.package,
                self.package_files,
                job_nonce=secrets.token_hex(16),
                invocation_id=case["invocationId"],
                operation=case["operation"],
                input_data=json.dumps(case["input"], separators=(",", ":")).encode("utf-8"),
                broker_callback=broker,
            )
        return result, calls

    def test_two_sample_pages_execute_inside_signed_lpac_worker(self) -> None:
        for path in SEARCH_CASES:
            with self.subTest(case=path.name):
                case = json.loads(path.read_text(encoding="utf-8"))
                result, calls = self._run_case(case, case["brokerResponse"])
                self.assertEqual([case["brokerCall"]], calls)
                self.assertEqual(1, result.broker_calls)
                self.assertIs(result.token["appContainer"], True)
                self.assertIs(result.token["lessPrivileged"], True)
                self.assertEqual(0, result.token["capabilityCount"])
                output = json.loads(result.output)
                self.assertEqual(case["output"], output)
                PluginWorkerPage.model_validate(output)

    def test_malformed_broker_page_fails_closed_without_echoing_content(self) -> None:
        case = json.loads(SEARCH_CASES[0].read_text(encoding="utf-8"))
        broker_response = json.loads(json.dumps(case["brokerResponse"]))
        broker_response["records"][0]["privateToken"] = "SYNTHETIC-PRIVATE-DO-NOT-ECHO"
        calls: list[dict] = []

        def broker(call: dict) -> bytes:
            calls.append(call)
            return json.dumps(broker_response, separators=(",", ":")).encode("utf-8")

        with (
            patch.object(recovery_guardian, "_guardian_command", return_value=self.guardian_command),
            self.assertRaises(LPACError) as denied,
        ):
            run_connector(
                self.runtime,
                self.package,
                self.package_files,
                job_nonce=secrets.token_hex(16),
                invocation_id=case["invocationId"],
                operation=case["operation"],
                input_data=json.dumps(case["input"], separators=(",", ":")).encode("utf-8"),
                broker_callback=broker,
            )
        self.assertEqual([case["brokerCall"]], calls)
        self.assertNotIn("SYNTHETIC-PRIVATE-DO-NOT-ECHO", str(denied.exception))


if __name__ == "__main__":
    unittest.main()
