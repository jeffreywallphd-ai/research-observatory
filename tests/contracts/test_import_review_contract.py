"""Import review OpenAPI/client generation matches action-specific rights."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from core_api_contract import _interfaces  # noqa: E402
from research_observatory_core.app import create_app  # noqa: E402


class ImportReviewContractTests(unittest.TestCase):
    def test_generated_types_quote_action_names_without_changing_wire_keys(self):
        schema = create_app().openapi()
        rendered = _interfaces(schema)
        self.assertIn('readonly "model-use": ImportPermission;', rendered)
        self.assertIn("model-use", schema["components"]["schemas"]["ImportRights"]["properties"])
        self.assertIn("/projects/imports/detail", schema["paths"])


if __name__ == "__main__":
    unittest.main()
