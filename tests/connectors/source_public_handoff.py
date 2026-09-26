"""Downstream example over public JSON schemas, without Core/storage imports."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]


def consume_source_observation(bundle):
    page = bundle["page"]
    schema = json.loads((REPO / "packages/contracts/connectors/connector-page.schema.json").read_text("utf-8"))
    Draft202012Validator(schema).validate(page)
    api = json.loads((REPO / "packages/contracts/core-api/openapi.json").read_text("utf-8"))
    Draft202012Validator({"$ref": "#/components/schemas/ConnectorRetention", "components": api["components"]}).validate(
        bundle["retention"]
    )
    request = page["request"]
    if (
        page["outcome"] != "complete"
        or page["retrievedAt"] is None
        or any(row["providerId"] != request["providerId"] for row in page["records"])
    ):
        raise ValueError("incomplete-or-unbound-source-handoff")
    if any(row["retrievedAt"] != page["retrievedAt"] for row in page["records"]):
        raise ValueError("incomplete-or-unbound-source-handoff")
    return {
        "projectId": request["projectId"],
        "observationId": page["observationId"],
        "invocationId": request["invocationId"],
        "providerId": request["providerId"],
        "adapterVersion": request["adapterVersion"],
        "sourceApiVersion": request["sourceApiVersion"],
        "query": copy.deepcopy(request["query"]),
        "cursor": copy.deepcopy(request["cursor"]),
        "continuation": page["continuation"],
        "nextCursor": copy.deepcopy(page["nextCursor"]),
        "retrievedAt": page["retrievedAt"],
        "response": copy.deepcopy(page["response"]),
        "records": copy.deepcopy(page["records"]),
        "terms": copy.deepcopy(page["terms"]),
        "rightsSnapshot": copy.deepcopy(bundle["retention"]["rights"]),
        "requiresCurrentAuthorization": True,
    }


def assert_source_handoff(check, bundles, count):
    results = [consume_source_observation(bundle) for bundle in bundles]
    check.assertEqual({"openalex", "crossref", "unpaywall", "semantic-scholar"}, {row["providerId"] for row in results})
    check.assertEqual(1, len({row["projectId"] for row in results}))
    check.assertEqual(4, len({row["observationId"] for row in results}))
    check.assertEqual(4, len({row["invocationId"] for row in results}))
    for row in results:
        check.assertEqual("1.0.0", row["adapterVersion"])
        check.assertTrue(row["requiresCurrentAuthorization"])
        check.assertEqual("retained", row["response"]["bodyState"])
        check.assertIsNotNone(row["response"]["objectSha256"])
        check.assertEqual(1 if row["providerId"] == "unpaywall" else count, len(row["records"]))
        check.assertEqual(
            count if row["providerId"] != "unpaywall" else 1,
            len({(record["rawIdentifier"]["scheme"], record["rawIdentifier"]["value"]) for record in row["records"]}),
        )
        for action in ("model-use", "export", "share"):
            check.assertEqual("unknown", row["rightsSnapshot"][action]["value"])
        check.assertNotIn("workId", row)
        for record in row["records"]:
            check.assertEqual(row["providerId"], record["providerId"])
            check.assertTrue(record["rawIdentifier"]["value"])
            check.assertTrue(record["identifiers"])
            fields = {field["name"]: field["value"] for field in record["fields"]}
            check.assertIn("candidate.title", fields)
            if row["providerId"] == "unpaywall":
                locations = json.loads(fields["candidate.oa-locations"])
                check.assertEqual(2, len(locations))
                check.assertEqual([None, "cc-by"], [item["license"] for item in locations])
                check.assertEqual(["repository", "repository"], [item["host_type"] for item in locations])
                check.assertTrue(all(item["url"] == "https://example.invalid/synthetic.pdf" for item in locations))
            if row["providerId"] == "semantic-scholar":
                check.assertEqual(row["query"], json.loads(fields["candidate.discovery"]))
                check.assertEqual("citations", row["query"]["direction"])
                check.assertEqual("a" * 40, row["query"]["seed"]["value"])
    # The consumer takes a copy and can never turn source terms into action grants.
    changed = copy.deepcopy(bundles[0])
    planned = consume_source_observation(changed)
    changed["retention"]["rights"]["export"]["value"] = "permitted"
    check.assertEqual("unknown", planned["rightsSnapshot"]["export"]["value"])
    for mutation in ("provider", "partial", "retrieval"):
        changed = copy.deepcopy(bundles[0])
        if mutation == "provider":
            changed["page"]["records"][0]["providerId"] = "other-provider"
        elif mutation == "partial":
            changed["page"]["outcome"] = "partial"
        else:
            changed["page"]["records"][0]["retrievedAt"] = "2020-01-01T00:00:00.000Z"
        with check.assertRaises(ValueError):
            consume_source_observation(changed)
