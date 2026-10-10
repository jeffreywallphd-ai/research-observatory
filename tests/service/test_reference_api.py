"""Strict native route/authentication boundary; explicitly doubled service."""

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]
from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402


class ReferenceApiTests(unittest.TestCase):
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

            def reference_enrich(self, command, *, trace_id):
                owner.calls.append(command)
                raise RuntimeError("synthetic-private-reference")

            references_read = reference_enrich

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
        self.base = {"root": "C:/synthetic-project", "projectId": new_uuid_v7(), "sessionId": "b" * 32}

    def test_closed_commands_reject_research_text_authority_and_unbounded_paging(self):
        cases = (
            (
                "references-enrich",
                self.base
                | {
                    "enrichment": {
                        "commandId": new_uuid_v7(),
                        "revisionId": new_uuid_v7(),
                        "expectedCollectionRevisionId": None,
                    }
                },
            ),
            (
                "references-read",
                self.base | {"revisionId": new_uuid_v7(), "expectedCollectionRevisionId": None, "afterOrder": None},
            ),
        )
        for action, command in cases:
            path = "/native/document-revisions/" + action
            for field in ("actorId", "source", "referenceText", "url", "targetWorkId", "scholarlyVerification"):
                result = self.client.post(path, json=command | {field: "synthetic-private-reference"})
                self.assertEqual(422, result.status_code)
                self.assertNotIn("synthetic-private-reference", result.text)
            self.assertEqual(401, self.client.post(path, json=command, headers={"Authorization": ""}).status_code)
            self.assertEqual(
                403, self.client.post(path, json=command, headers={"Origin": "tauri://localhost"}).status_code
            )
            result = self.client.post(path, json=command)
            self.assertEqual(409, result.status_code)
            self.assertNotIn("synthetic-private-reference", result.text)
        for after in (-1, 1000, True, "0"):
            self.assertEqual(
                422,
                self.client.post(
                    "/native/document-revisions/references-read", json=cases[1][1] | {"afterOrder": after}
                ).status_code,
            )
        self.assertEqual(2, len(self.calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
