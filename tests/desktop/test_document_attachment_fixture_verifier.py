"""Canonical project identity accepted by the read-only attachment verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/desktop/tools"))

from verify_document_attachment_fixture import _project_id  # noqa: E402


class ProjectIdentityTests(unittest.TestCase):
    def test_existing_uuid4_bridge_and_new_uuid7_projects_are_canonical(self) -> None:
        self.assertTrue(_project_id("f52f40de-6a15-455c-b180-269a76267051"))
        self.assertTrue(_project_id("01a1001f-ac2d-7d87-acd6-a4a61497a3a0"))

    def test_case_malformed_and_wrong_version_fail_closed(self) -> None:
        self.assertFalse(_project_id("F52F40DE-6A15-455C-B180-269A76267051"))
        self.assertFalse(_project_id("f52f40de-6a15-455c-b180-269a7626705"))
        self.assertFalse(_project_id("01a1001f-ac2d-1d87-acd6-a4a61497a3a0"))


if __name__ == "__main__":
    unittest.main()
