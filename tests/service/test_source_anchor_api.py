"""Native-only anchor shape/authentication boundary; explicitly doubled service."""

import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402


class SourceAnchorApiTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        owner = self

        class SyntheticService:
            def start(self):
                pass

            def shutdown(self):
                pass

            def signal_stop(self, root=None):
                pass

            def anchor_create(self, command, *, trace_id):
                owner.calls.append(command)
                raise RuntimeError("synthetic-private-passage")

            anchor_resolve = anchor_create
            citation_links = anchor_create

        self.client = self.enterContext(
            TestClient(
                create_app(
                    document_revisions=SyntheticService(),
                    capability_digest=capability_token_digest("a" * 64),
                    expected_authority="127.0.0.1:49152",
                ),
                base_url="http://127.0.0.1:49152",
                headers={"Authorization": "Bearer " + "a" * 64},
                client=("127.0.0.1", 50000),
            )
        )
        self.command = {
            "root": "C:/synthetic-project",
            "projectId": new_uuid_v7(),
            "sessionId": "b" * 32,
            "commandId": new_uuid_v7(),
            "selection": {
                "revisionId": new_uuid_v7(),
                "nodeId": new_uuid_v7(),
                "normalizedRange": {"start": 0, "end": 10},
            },
        }
        self.path = "/native/document-revisions/anchor-create"

    def test_quote_actor_coordinates_and_extra_authority_never_reach_service(self):
        for field in ("quote", "actorId", "pageRegion", "confidence", "source"):
            command = dict(
                self.command, selection=dict(self.command["selection"], **{field: "synthetic-private-passage"})
            )
            response = self.client.post(self.path, json=command)
            self.assertEqual(422, response.status_code)
            self.assertNotIn("synthetic-private-passage", response.text)
        self.assertEqual([], self.calls)

    def test_duplicate_and_oversize_requests_are_denied_before_service(self):
        duplicate = json.dumps(self.command)[:-1] + ',"commandId":"duplicated"}'
        self.assertEqual(
            422,
            self.client.post(self.path, content=duplicate, headers={"Content-Type": "application/json"}).status_code,
        )
        self.assertEqual(
            413,
            self.client.post(self.path, content=b" " * 8193, headers={"Content-Type": "application/json"}).status_code,
        )
        self.assertEqual([], self.calls)

    def test_native_authentication_origin_and_redacted_denial(self):
        self.assertEqual(401, self.client.post(self.path, json=self.command, headers={"Authorization": ""}).status_code)
        self.assertEqual(
            403, self.client.post(self.path, json=self.command, headers={"Origin": "tauri://localhost"}).status_code
        )
        self.assertEqual([], self.calls)
        response = self.client.post(self.path, json=self.command)
        self.assertEqual(409, response.status_code)
        self.assertNotIn("synthetic-private-passage", response.text)
        self.assertEqual(1, len(self.calls))
        self.assertFalse(
            any(
                path.startswith("/native/document-revisions")
                for path in self.client.get("/openapi.json").json()["paths"]
            )
        )

    def test_resolution_and_reference_routes_reject_authority_and_unbounded_requests(self):
        base = {key: self.command[key] for key in ("root", "projectId", "sessionId")}
        cases = (
            ("anchor-resolve", base | {"anchorId": new_uuid_v7(), "expectedRevisionId": new_uuid_v7()}),
            ("citation-links", base | {"revisionId": new_uuid_v7(), "citationId": new_uuid_v7(), "limit": 2}),
        )
        for action, command in cases:
            path = "/native/document-revisions/" + action
            for field in ("actorId", "source", "quote", "url", "resolvedReferenceId", "scholarlyVerification"):
                response = self.client.post(path, json=command | {field: "synthetic-private-passage"})
                self.assertEqual(422, response.status_code)
                self.assertNotIn("synthetic-private-passage", response.text)
            self.assertEqual(
                403, self.client.post(path, json=command, headers={"Origin": "tauri://localhost"}).status_code
            )
            self.assertEqual(401, self.client.post(path, json=command, headers={"Authorization": ""}).status_code)
            response = self.client.post(path, json=command)
            self.assertEqual(409, response.status_code)
            self.assertNotIn("synthetic-private-passage", response.text)
        reference = cases[1][1]
        for limit in (0, 3, True, "2"):
            self.assertEqual(
                422,
                self.client.post(
                    "/native/document-revisions/citation-links", json=reference | {"limit": limit}
                ).status_code,
            )
        self.assertEqual(2, len(self.calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
