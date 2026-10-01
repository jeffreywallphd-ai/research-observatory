"""Downstream handoff examples using only committed portable JSON contracts.

These consumers plan references for later capabilities. A validated fixture is
never a current Core authorization or a substitute for protected source lookup.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2] / "packages/contracts"


def fixture(package: str, name: str) -> dict:
    return json.loads((ROOT / package / "fixtures" / name).read_text(encoding="utf-8"))


def validate(package: str, schema_name: str, document: dict) -> None:
    schema = json.loads((ROOT / package / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(document)


def membership_handoff(item: dict, path: dict, decision: dict) -> dict:
    for document in (item, path, decision):
        validate("corpus", "corpus-membership.schema.json", document)
    if not (
        item["projectId"] == path["projectId"] == decision["projectId"]
        and item["itemId"] == path["itemId"] == decision["itemId"]
        and item["revisionId"] == decision["previousRevisionId"]
        and decision["dimension"] == "membership"
        and decision["previousValue"] == item["membership"]
        and path["pathId"] in item["discoveryPathIds"]
        and path["sourceRevisionId"] in decision["evidenceRevisionIds"]
    ):
        raise ValueError("unbound-membership-history")
    return {
        "projectId": item["projectId"],
        "itemId": item["itemId"],
        "workRevisionId": item["workRevisionId"],
        "priorItemRevisionId": item["revisionId"],
        "nextItemRevisionId": decision["nextRevisionId"],
        "decisionId": decision["decisionId"],
        "reasonCode": decision["reasonCode"],
        "protocolRevisionId": decision["protocolRevisionId"],
        "sourceRevisionId": path["sourceRevisionId"],
        "pathId": path["pathId"],
    }


def rights_handoff(policy: dict, decision: dict) -> dict:
    for document in (policy, decision):
        validate("rights", "rights-policy.schema.json", document)
    governing = set(decision["governingAssertionIds"])
    matching = [
        permission
        for permission in policy["permissions"]
        if permission["assertionId"] in governing
        and permission["subject"] == policy["subject"]
        and permission["use"] == decision["use"]
    ]
    if not (
        decision["authorityKind"] == "policy"
        and decision["policyRevisionId"] == policy["revisionId"]
        and decision["subject"] == policy["subject"]
        and governing
        and governing == {permission["assertionId"] for permission in matching}
    ):
        raise ValueError("unbound-rights-decision")
    subject = policy["subject"]
    return {
        "projectId": subject["projectId"],
        "sourceAssertionRevisionId": subject["sourceAssertionRevisionId"],
        "sourceAddress": copy.deepcopy(subject["address"]),
        "copyId": subject["copyId"],
        "copyLocation": subject["copyLocation"],
        "resourceClass": subject["resourceClass"],
        "action": decision["use"]["action"],
        "purpose": decision["use"]["purpose"],
        "destinationKind": decision["use"]["destinationKind"],
        "policyRevisionId": policy["revisionId"],
        "historicalDecision": decision["code"],
        "requiresCurrentAuthorization": True,
    }


def report_handoff(snapshot: dict, member: dict, page: dict) -> dict:
    for document in (snapshot, member, page):
        validate("corpus-reports", "corpus-report.schema.json", document)
    if not (
        snapshot["projectId"] == member["projectId"] == page["projectId"]
        and snapshot["snapshotId"] == member["snapshotId"] == page["snapshotId"]
        and snapshot["memberCount"] == page["total"] == len(page["members"]) == 1
        and page["nextCursor"] is None
        and page["filter"]["kind"] == "all"
        and page["members"][0] == member
        and sum(row["itemCount"] for row in snapshot["membershipCounts"]) == snapshot["memberCount"]
        and next(row["itemCount"] for row in snapshot["membershipCounts"] if row["membership"] == member["membership"])
        == 1
        and snapshot["discoveryPathCount"] == len(member["paths"])
        and all(
            path["metadataAssertionStatus"] == "retained"
            and path["reportInspectStatus"] == "allowed"
            and path["rightsPolicyRevisionId"] is not None
            for path in member["paths"]
        )
    ):
        raise ValueError("unbound-report-snapshot")
    return {
        "projectId": snapshot["projectId"],
        "snapshotId": snapshot["snapshotId"],
        "itemId": member["itemId"],
        "itemRevisionId": member["itemRevisionId"],
        "workRevisionId": member["workRevisionId"],
        "pathWitnesses": [
            {
                "pathId": path["pathId"],
                "sourceRevisionId": path["sourceRevisionId"],
                "contextRevisionId": path["contextRevisionId"],
                "rightsPolicyRevisionId": path["rightsPolicyRevisionId"],
                "reportInspectStatus": path["reportInspectStatus"],
            }
            for path in member["paths"]
        ],
        "requiresCurrentAuthorization": True,
    }


class CorpusPublicHandoffTests(unittest.TestCase):
    def test_cap06_can_follow_immutable_membership_and_source_history(self) -> None:
        item = fixture("corpus", "valid-corpus-item-revision.v1.json")
        path = fixture("corpus", "valid-discovery-path.v1.json")
        decision = fixture("corpus", "valid-corpus-decision.v1.json")
        handoff = membership_handoff(item, path, decision)
        self.assertEqual("candidate", item["membership"])
        self.assertEqual(
            ("candidate", "included", "criterion-met"),
            (decision["previousValue"], decision["nextValue"], handoff["reasonCode"]),
        )
        self.assertEqual(
            (item["revisionId"], decision["nextRevisionId"]),
            (handoff["priorItemRevisionId"], handoff["nextItemRevisionId"]),
        )
        self.assertEqual(
            (item["itemId"], path["sourceRevisionId"], path["pathId"]),
            (handoff["itemId"], handoff["sourceRevisionId"], handoff["pathId"]),
        )
        with self.assertRaisesRegex(ValueError, "unbound-membership-history"):
            membership_handoff(item, path, decision | {"previousRevisionId": path["pathId"]})

    def test_cap05_receives_exact_source_copy_action_and_historical_rights(self) -> None:
        policy = fixture("rights", "valid-policy.v1.json")
        decision = fixture("rights", "valid-decision.v1.json")
        handoff = rights_handoff(policy, decision)
        subject = policy["subject"]
        self.assertEqual(
            (subject["sourceAssertionRevisionId"], subject["address"], subject["copyId"]),
            (handoff["sourceAssertionRevisionId"], handoff["sourceAddress"], handoff["copyId"]),
        )
        self.assertEqual(
            ("inspect", "scholarly-screening", "local-project"),
            (handoff["action"], handoff["purpose"], handoff["destinationKind"]),
        )
        self.assertEqual(
            (policy["revisionId"], "allow", True),
            (handoff["policyRevisionId"], handoff["historicalDecision"], handoff["requiresCurrentAuthorization"]),
        )
        policy["subject"]["copyId"] = subject["sourceAssertionRevisionId"]
        self.assertNotEqual(policy["subject"]["copyId"], handoff["copyId"])
        with self.assertRaisesRegex(ValueError, "unbound-rights-decision"):
            rights_handoff(
                fixture("rights", "valid-policy.v1.json"), decision | {"use": decision["use"] | {"action": "export"}}
            )

    def test_cap08_and_cap18_receive_bound_snapshot_member_and_path_witnesses(self) -> None:
        snapshot = fixture("corpus-reports", "valid-snapshot.v1.json")
        member = fixture("corpus-reports", "valid-member.v1.json")
        page = fixture("corpus-reports", "valid-drill-page.v1.json")
        handoff = report_handoff(snapshot, member, page)
        self.assertEqual(
            (snapshot["snapshotId"], member["itemRevisionId"], member["workRevisionId"]),
            (handoff["snapshotId"], handoff["itemRevisionId"], handoff["workRevisionId"]),
        )
        self.assertEqual(
            {path["sourceRevisionId"] for path in member["paths"]},
            {path["sourceRevisionId"] for path in handoff["pathWitnesses"]},
        )
        self.assertEqual({"allowed"}, {path["reportInspectStatus"] for path in handoff["pathWitnesses"]})
        self.assertTrue(handoff["requiresCurrentAuthorization"])
        with self.assertRaisesRegex(ValueError, "unbound-report-snapshot"):
            report_handoff(snapshot, member, page | {"snapshotId": member["itemId"]})
        with self.assertRaisesRegex(ValueError, "unbound-report-snapshot"):
            report_handoff(snapshot, member, page | {"members": []})
        unassessed_member = copy.deepcopy(member)
        unassessed_member["paths"][0].update(
            metadataAssertionStatus="no-external-assertion",
            reportInspectStatus="unassessed",
            rightsPolicyRevisionId=None,
            sourceKey=None,
        )
        with self.assertRaisesRegex(ValueError, "unbound-report-snapshot"):
            report_handoff(snapshot, unassessed_member, page | {"members": [unassessed_member]})


if __name__ == "__main__":
    unittest.main()
