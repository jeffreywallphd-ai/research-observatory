"""Versioned connector entry-point compatibility at the real worker frame boundary."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from workers.windows.plugin_worker import WorkerProtocolError, run_worker
from workers.windows.protocol import read_binary_frame, read_frame, write_binary_frame, write_frame

REPO = Path(__file__).resolve().parents[2]
INVOCATION_ID = "0190a000-0000-7000-8000-000000000042"
NONCE = "a" * 32


class PluginWorkerApiTests(unittest.TestCase):
    def _invoke(self, source: bytes, input_data: bytes = b'{"identifier":"synthetic-1"}') -> bytes:
        with tempfile.TemporaryDirectory(prefix="worker-api-", dir=REPO / "artifacts/tmp") as temporary:
            root = Path(temporary)
            entry = root / "plugin" / "connector.py"
            entry.parent.mkdir()
            entry.write_bytes(source)
            (root / "plugin-assets").mkdir()
            incoming = io.BytesIO()
            write_frame(
                incoming,
                {
                    "protocolVersion": "1.0",
                    "jobNonce": NONCE,
                    "sequence": 0,
                    "operation": "invoke",
                    "invocationId": INVOCATION_ID,
                    "connectorOperation": "lookup",
                    "inputSha256": hashlib.sha256(input_data).hexdigest(),
                    "pluginSha256": hashlib.sha256(source).hexdigest(),
                    "inputLength": len(input_data),
                },
            )
            write_binary_frame(incoming, input_data)
            incoming.seek(0)
            outgoing = io.BytesIO()
            run_worker(incoming, outgoing, asset_root=root)
            outgoing.seek(0)
            result = read_frame(outgoing, expected_nonce=NONCE, expected_sequence=1)
            self.assertEqual("invoke-result", result["operation"])
            output = read_binary_frame(outgoing)
            self.assertEqual(len(output), result["outputLength"])
            self.assertEqual(hashlib.sha256(output).hexdigest(), result["outputSha256"])
            self.assertEqual(b"", outgoing.read())
            return output

    def test_keyword_only_context_contains_only_trusted_invocation_id(self) -> None:
        source = (
            b"import json\n"
            b"def invoke(input_data, broker, operation, *, context):\n"
            b"    assert operation == 'lookup'\n"
            b"    assert json.loads(input_data) == {'identifier': 'synthetic-1'}\n"
            b"    return json.dumps(context, sort_keys=True).encode('ascii')\n"
        )
        self.assertEqual({"invocationId": INVOCATION_ID}, json.loads(self._invoke(source)))

    def test_existing_three_argument_entry_point_remains_callable(self) -> None:
        source = (
            b"def invoke(input_data, broker, operation):\n"
            b"    assert operation == 'lookup'\n"
            b"    return input_data + b':legacy'\n"
        )
        self.assertEqual(b'{"identifier":"synthetic-1"}:legacy', self._invoke(source))

    def test_legacy_entry_point_does_not_require_inspectable_signature(self) -> None:
        source = (
            b"def invoke(input_data, broker, operation):\n"
            b"    return input_data + b':legacy'\n"
            b"invoke.__signature__ = 'not-inspectable'\n"
        )
        self.assertEqual(b'{"identifier":"synthetic-1"}:legacy', self._invoke(source))

    def test_context_entry_point_still_requires_bounded_bytes_output(self) -> None:
        source = (
            b"def invoke(input_data, broker, operation, *, context):\n"
            b"    return {'invocationId': context['invocationId']}\n"
        )
        with self.assertRaisesRegex(WorkerProtocolError, "worker-output-invalid"):
            self._invoke(source)


if __name__ == "__main__":
    unittest.main()
