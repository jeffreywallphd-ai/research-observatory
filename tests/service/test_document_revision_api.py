"""Native transport denial/redaction; explicitly synthetic service port."""

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


class DocumentRevisionApiTests(unittest.TestCase):
    def setUp(self):
        owner = self
        self.calls = 0

        class SyntheticService:
            def start(self):
                pass

            def shutdown(self):
                pass

            def signal_stop(self, root=None):
                pass

            def parse(self, command, *, trace_id):
                owner.calls += 1
                raise RuntimeError("synthetic-private-document-content")

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
        self.command = dict(
            root="C:/synthetic-project",
            projectId=new_uuid_v7(),
            sessionId="b" * 32,
            commandId=new_uuid_v7(),
            attachmentId=new_uuid_v7(),
        )

    def test_untrusted_actor_content_duplicate_and_oversize_never_reach_core(self):
        for field in ("actorId", "ir", "parserPath", "permissions"):
            response = self.client.post(
                "/native/document-revisions/parse", json={**self.command, field: "synthetic-secret"}
            )
            self.assertEqual(422, response.status_code)
            self.assertNotIn("synthetic-secret", response.text)
        duplicate = json.dumps(self.command)[:-1] + ',"attachmentId":"duplicated"}'
        response = self.client.post(
            "/native/document-revisions/parse", content=duplicate, headers={"Content-Type": "application/json"}
        )
        self.assertEqual(422, response.status_code)
        response = self.client.post(
            "/native/document-revisions/parse", content=b" " * 8193, headers={"Content-Type": "application/json"}
        )
        self.assertEqual(413, response.status_code)
        self.assertEqual(0, self.calls)

    def test_native_authentication_origin_denial_redaction_and_schema_exclusion(self):
        self.assertEqual(
            401,
            self.client.post(
                "/native/document-revisions/parse", json=self.command, headers={"Authorization": ""}
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/native/document-revisions/parse", json=self.command, headers={"Origin": "tauri://localhost"}
            ).status_code,
        )
        self.assertEqual(0, self.calls)
        response = self.client.post("/native/document-revisions/parse", json=self.command)
        self.assertEqual(409, response.status_code)
        self.assertEqual("RO-CORE-DOCUMENT-REVISION-DENIED", response.json()["code"])
        self.assertNotIn("synthetic-private-document-content", response.text)
        self.assertEqual(1, self.calls)
        self.assertFalse(
            any(
                path.startswith("/native/document-revisions")
                for path in self.client.get("/openapi.json").json()["paths"]
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
