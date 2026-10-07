"""Chunked parser transport does not enlarge a generic connector frame."""

import hashlib
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "services/core-api/src")]

from workers.windows import connector_launcher as parent  # noqa: E402
from workers.windows import parsing_launcher as parser  # noqa: E402
from workers.windows.lpac_launcher import LPACError  # noqa: E402
from workers.windows.protocol import MAX_BINARY_FRAME, MAX_DOCUMENT_CHUNK  # noqa: E402


class ParsingLauncherTests(unittest.TestCase):
    def exchange(self, source, raw, *, declared_length=None, footer=None):
        chunks = [raw[i : i + MAX_DOCUMENT_CHUNK] for i in range(0, len(raw), MAX_DOCUMENT_CHUNK)]
        wire = BytesIO(b"".join(len(c).to_bytes(4, "big") + c for c in chunks) + b"\0" * 4)
        response = {
            "protocolVersion": "1.0",
            "jobNonce": "a" * 32,
            "sequence": 2,
            "operation": "parse-result",
            "outputLength": len(raw) if declared_length is None else declared_length,
            "outputSha256": footer or hashlib.sha256(raw).hexdigest(),
        }

        def run(_runtime, **kwargs):
            self.assertEqual(kwargs["profile"], "parser")
            self.assertEqual(kwargs["memory_mib"], 4096)
            self.assertEqual(kwargs["wall_seconds"], 900)
            request = kwargs["prepare_request"](Path("fixed-image"))
            output, calls = kwargs["dialogue"](None, 1, 2, request)
            return parent.WorkerResult(output, {}, calls)

        with (
            patch.object(parent, "_run_signed_worker", run),
            patch.object(parent, "_read_exact", side_effect=lambda _k, _h, n: wire.read(n)),
            patch.object(parent, "_read_control", return_value=response),
            patch.object(parent, "_write_binary"),
            patch.object(parser.win, "_write"),
        ):
            return parser.parse_document(
                None, BytesIO(source), format="txt", length=len(source), sha256=hashlib.sha256(source).hexdigest()
            )

    def test_valid_large_output_remains_one_megabyte_chunks(self):
        raw = b"synthetic" * (MAX_BINARY_FRAME // 9 + 1)
        self.assertGreater(len(raw), MAX_BINARY_FRAME)
        self.assertEqual(self.exchange(b"synthetic input", raw).output, raw)
        self.assertEqual(MAX_BINARY_FRAME, 10 * 1_048_576)

    def test_bad_digest_length_and_ir_limit_refuse_delivery(self):
        for kwargs in ({"footer": "f" * 64}, {"declared_length": 1}, {"declared_length": 64 * 1_048_576 + 1}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(LPACError, "output-invalid"):
                self.exchange(b"synthetic input", b"synthetic output", **kwargs)


if __name__ == "__main__":
    unittest.main()
