"""Consumer example using only public JSON contracts, never Core/storage internals."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]


def consume_complete_manifest(bundle):
    """Plan source-ID handoff, not reconciliation, permission grants or execution."""
    schema = json.loads((REPO / "packages/contracts/core-api/openapi.json").read_text("utf-8"))
    for key, model in (
        ("manifest", "ImportManifestView"),
        ("members", "ImportManifestPage"),
        ("rights", "ImportRights"),
    ):
        Draft202012Validator({"$ref": f"#/components/schemas/{model}", "components": schema["components"]}).validate(
            bundle[key]
        )
    manifest, page = bundle["manifest"], bundle["members"]
    if (
        page["previewId"] != manifest["previewId"]
        or page["revisionId"] != manifest["revisionId"]
        or not page["complete"]
        or len(page["records"]) != manifest["recordCount"]
        or [row["ordinal"] for row in page["records"]] != list(range(1, manifest["recordCount"] + 1))
        or page["nextAfter"] != manifest["recordCount"]
        or sum(row["included"] for row in page["records"]) != manifest["selectedCount"]
    ):
        raise ValueError("incomplete-or-unbound-handoff")
    return {
        "projectId": manifest["projectId"],
        "manifestRevisionId": manifest["revisionId"],
        "sourceSha256": manifest["sourceSha256"],
        "parserVersion": manifest["parserVersion"],
        "mapping": {"id": manifest["mappingId"], "revision": manifest["mappingRevision"]},
        "sourceRecords": [
            {"revisionId": row["sourceRecordRevisionId"], "recordKey": row["recordKey"], "ordinal": row["ordinal"]}
            for row in page["records"]
            if row["included"]
        ],
        "excluded": [copy.deepcopy(row) for row in page["records"] if not row["included"]],
        "rightsSnapshot": copy.deepcopy(bundle["rights"]),
        "requiresCurrentAuthorization": True,
    }


class ImportPublicHandoffTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((REPO / "tests/fixtures/imports/public-handoff-v1.json").read_text("utf-8"))

    def test_downstream_can_preserve_identities_decisions_provenance_and_unknown_rights(self):
        handoff = consume_complete_manifest(self.bundle)
        self.assertEqual(self.bundle["manifest"]["revisionId"], handoff["manifestRevisionId"])
        self.assertEqual([2, 3], [row["ordinal"] for row in handoff["sourceRecords"]])
        self.assertEqual(2, len({row["revisionId"] for row in handoff["sourceRecords"]}))
        self.assertEqual(["invalid-doi"], handoff["excluded"][0]["warnings"])
        self.assertIsNone(handoff["excluded"][0]["sourceRecordRevisionId"])
        self.assertEqual("unknown", handoff["rightsSnapshot"]["export"]["value"])
        self.assertTrue(handoff["requiresCurrentAuthorization"])
        self.bundle["rights"]["export"]["value"] = "permitted"
        self.assertEqual("unknown", handoff["rightsSnapshot"]["export"]["value"])
        self.assertNotIn("workId", handoff)

    def test_consumer_rejects_partial_or_other_manifest_membership(self):
        changes: tuple[dict[str, object], ...] = (
            {"complete": False},
            {"revisionId": self.bundle["manifest"]["mappingId"]},
            {"records": []},
        )
        for change in changes:
            bundle = copy.deepcopy(self.bundle)
            bundle["members"].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "incomplete-or-unbound-handoff"):
                consume_complete_manifest(bundle)


if __name__ == "__main__":
    unittest.main()
