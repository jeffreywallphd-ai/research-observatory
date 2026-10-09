"""Strict additive link values; IDs are selectors rather than authority."""

import unittest

from pydantic import ValidationError
from research_observatory_core.ports import document_viewer


def identity(value):
    return "00000000-0000-7000-8000-" + format(value, "012x")


class ViewerDeepLinkTests(unittest.TestCase):
    def value(self):
        return {
            "schemaVersion": "1.0",
            "projectId": identity(1),
            "selector": {
                "attachmentId": identity(4),
                "documentRevisionId": identity(5),
                "normalizedRevisionId": identity(3),
            },
            "anchorIds": [identity(20), identity(22)],
        }

    def test_exact_ordered_opaque_link_round_trip(self):
        model = document_viewer.ViewerDeepLink.model_validate(self.value())
        self.assertEqual(self.value(), model.model_dump(mode="json", by_alias=True))
        value = self.value()
        value["projectId"] = "00000000-0000-4000-8000-000000000001"
        self.assertEqual(
            value, document_viewer.ViewerDeepLink.model_validate(value).model_dump(mode="json", by_alias=True)
        )

    def test_unknown_fields_duplicate_or_unavailable_revision_and_oversized_selection_deny(self):
        examples = [
            dict(self.value(), root="untrusted"),
            dict(self.value(), quote="untrusted"),
            dict(self.value(), schemaVersion="2.0"),
            dict(self.value(), anchorIds=[]),
            dict(self.value(), anchorIds=[identity(20)] * 2),
            dict(self.value(), anchorIds=[identity(n) for n in range(30, 131)]),
        ]
        for normalized in (None, identity(5)):
            value = self.value()
            value["selector"]["normalizedRevisionId"] = normalized
            examples.append(value)
        for value in examples:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                document_viewer.ViewerDeepLink.model_validate(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
