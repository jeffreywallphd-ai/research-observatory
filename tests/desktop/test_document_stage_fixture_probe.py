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
