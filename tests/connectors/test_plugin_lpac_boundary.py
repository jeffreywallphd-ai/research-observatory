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
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


class PluginLPACBoundaryTests(unittest.TestCase):
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
                with patch.dict(os.environ, {"RO_LPAC_TEST_SECRET": "synthetic-secret"}):
                    result = run_probe(
                        package,
                        inventory,
                        read_path=unrelated,
                        write_path=writable,
                        loopback_port=server.getsockname()[1],
                    )

            self.assertIs(result["token"]["appContainer"], True)
            self.assertIs(result["token"]["lessPrivileged"], True)
            self.assertEqual(result["token"]["capabilityCount"], 0)
            self.assertEqual(
                result["probes"],
                {
                    "unrelatedRead": "denied",
                    "outsideWrite": "denied",
                    "directLoopback": "denied",
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


if __name__ == "__main__":
    unittest.main()
