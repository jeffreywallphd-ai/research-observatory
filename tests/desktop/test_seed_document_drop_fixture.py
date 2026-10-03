"""The disposable document seed follows the published Work revision."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/desktop/tools"))

import seed_document_drop_fixture as fixture  # noqa: E402


class PublishedSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.before: dict[str, Any] = {
            "workId": "01900000-0000-7000-8000-000000000001",
            "revisionId": "01900000-0000-7000-8000-000000000002",
            "assertionRevisionIds": ["01900000-0000-7000-8000-000000000003"],
        }
        self.after: dict[str, Any] = {
            **self.before,
            "revisionId": "01900000-0000-7000-8000-000000000004",
        }
        self.context: dict[str, Any] = {
            "works": [self.after],
            "versions": [
                {
                    "versionId": "01900000-0000-7000-8000-000000000005",
                    "revisionId": "01900000-0000-7000-8000-000000000006",
                }
            ],
        }

    def test_seed_uses_current_work_revision_after_version_publication(self) -> None:
        selected = fixture.published_seed_selection(self.before, [self.after], self.context)
        self.assertEqual(
            selected,
            {
                "workId": self.before["workId"],
                "workRevisionId": self.after["revisionId"],
                "versionId": self.context["versions"][0]["versionId"],
                "versionRevisionId": self.context["versions"][0]["revisionId"],
                "sourceAssertionRevisionId": self.before["assertionRevisionIds"][0],
            },
        )
        self.assertNotEqual(selected["workRevisionId"], self.before["revisionId"])

    def test_stale_or_substituted_published_work_is_denied(self) -> None:
        changed_id = {**self.after, "workId": "01900000-0000-7000-8000-000000000007"}
        changed_membership = {**self.after, "assertionRevisionIds": ["01900000-0000-7000-8000-000000000008"]}
        changed_context = {**self.context, "works": [self.before]}
        for works, context in (
            ([self.before], self.context),
            ([changed_id], self.context),
            ([changed_membership], self.context),
            ([self.after, self.after], self.context),
            ([self.after], changed_context),
        ):
            with self.subTest(works=works, context=context), self.assertRaises(RuntimeError):
                fixture.published_seed_selection(self.before, works, context)


if __name__ == "__main__":
    unittest.main()
