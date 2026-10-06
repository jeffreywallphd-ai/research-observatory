"""Bounded, content-free diagnostics for the disposable signed document fixture."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/core-api/src"))
sys.path.insert(0, str(ROOT / "tests/service/fixtures"))

from native_integration_sidecar import _StageExceptionProbe  # noqa: E402


class DocumentStageFixtureProbeTests(unittest.TestCase):
    def test_stage_rejection_records_fixed_code_and_preserves_wire_response(self) -> None:
        cases = [
            (503, "RO-CORE-DOCUMENT-UNAVAILABLE", "document-unavailable"),
            (422, "RO-CORE-DOCUMENT-INTAKE-INVALID", "intake-invalid"),
            (500, "RO-CORE-INTERNAL-ERROR", "other"),
            (500, "PRIVATE-TOKEN-CANARY", "other"),
        ]
        for status, code, expected in cases:
            with self.subTest(status=status, expected=expected):
                body = json.dumps({"code": code, "detail": "private document path and token"}).encode()
                messages = [
                    {"type": "http.response.start", "status": status, "headers": []},
                    {"type": "http.response.body", "body": body, "more_body": False},
                ]
                forwarded: list[dict[str, object]] = []

                async def rejected_app(_scope, _receive, send, messages=messages) -> None:
                    for message in messages:
                        await send(message)

                async def receive():
                    return {}

                async def send(message, forwarded=forwarded) -> None:
                    forwarded.append(message)

                with tempfile.TemporaryDirectory(dir=ROOT / "artifacts/tmp") as directory:
                    temporary = Path(directory)
                    probe = _StageExceptionProbe(rejected_app, temporary)
                    asyncio.run(probe({"type": "http", "path": "/native/document-attachments/stage"}, receive, send))
                    receipt = temporary / "document-stage-rejection.json"
                    self.assertEqual(
                        {"kind": "document-stage-rejection", "status": status, "code": expected},
                        json.loads(receipt.read_text(encoding="ascii")),
                    )
                    self.assertNotIn("private", receipt.read_text(encoding="ascii"))
                    self.assertNotIn("CANARY", receipt.read_text(encoding="ascii"))
                    self.assertEqual(messages, forwarded)

    def test_only_exact_stage_unhandled_exception_writes_one_fixed_code(self) -> None:
        async def failing_app(_scope, _receive, _send) -> None:
            raise TypeError("private document path and token must never be recorded")

        async def receive() -> dict[str, str]:
            return {}

        async def send(_message) -> None:
            return None

        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts/tmp") as directory:
            temporary = Path(directory)
            probe = _StageExceptionProbe(failing_app, temporary)
            with self.assertRaises(TypeError):
                asyncio.run(probe({"type": "http", "path": "/native/document-attachments/context"}, receive, send))
            receipt = temporary / "document-stage-exception.json"
            self.assertFalse(receipt.exists())
            with self.assertRaises(TypeError):
                asyncio.run(probe({"type": "http", "path": "/native/document-attachments/stage"}, receive, send))
            self.assertEqual(
                json.loads(receipt.read_text(encoding="ascii")),
                {"kind": "document-stage-exception", "classCode": "builtins-type-error"},
            )
            self.assertNotIn("private", receipt.read_text(encoding="ascii"))
            with self.assertRaises(TypeError):
                asyncio.run(probe({"type": "http", "path": "/native/document-attachments/stage"}, receive, send))
            self.assertEqual(json.loads(receipt.read_text(encoding="ascii"))["classCode"], "builtins-type-error")


if __name__ == "__main__":
    unittest.main()
