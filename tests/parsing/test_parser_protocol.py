"""Content-free failures and source identity before any inference import."""

import hashlib
import sys
import unittest
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "services/core-api/src")]

from workers.windows.parser_worker import ParserWorkerError, _source, parse_document  # noqa: E402
from workers.windows.protocol import encode_frame, write_binary_frame  # noqa: E402


class ParserProtocolTests(unittest.TestCase):
    def frames(self, data, *, digest=None, nonce="a" * 32, chunk=None):
        request = {
            "protocolVersion": "1.0",
            "jobNonce": "a" * 32,
            "sequence": 0,
            "operation": "parse-document",
            "format": "txt",
            "inputLength": len(data),
            "inputSha256": digest or hashlib.sha256(data).hexdigest(),
        }
        stream = BytesIO()
        write_binary_frame(stream, data if chunk is None else chunk)
        write_binary_frame(stream, b"")
        stream.write(
            encode_frame({"protocolVersion": "1.0", "jobNonce": nonce, "sequence": 1, "operation": "parse-end"})
        )
        stream.seek(0)
        return stream, request

    def test_wrong_source_and_oversize_chunk_refused_before_parser(self):
        stream, request = self.frames(b"private synthetic", digest="f" * 64)
        with self.assertRaisesRegex(ParserWorkerError, "source-invalid"):
            _source(stream, request)
        stream, request = self.frames(b"x" * 1_048_577)
        with self.assertRaisesRegex(ParserWorkerError, "source-invalid"):
            _source(stream, request)

    def test_source_identity_and_bounded_text_without_docling(self):
        data = "Synthetic \u03b1\r\ntext".encode()
        stream, request = self.frames(data)
        self.assertEqual(_source(stream, request), data)
        result = parse_document(data, "txt", Path("unused-assets"))
        self.assertIn("\u03b1", result.decode())


if __name__ == "__main__":
    unittest.main()
