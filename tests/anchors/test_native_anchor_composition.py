"""Real Core native routes/session/SQLCipher/envelopes; authored synthetic IR.

The in-process HTTP client and precursor parser output are declared fixtures.
No parser, Tauri process or newly frozen installation qualification is claimed.
"""

import json
import os
import sys
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402

from tests.documents import test_document_revision_workflow as workflow_fixtures  # noqa: E402


class NativeAnchorCompositionTests(unittest.TestCase):
    def setUp(self):
        self.f = workflow_fixtures.DocumentRevisionWorkflowTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        result = self.f.fixture.parse("First synthetic passage. Second synthetic passage.")
        self.accepted = self.f.fixture.repository.accept(self.f.fixture.command(result))
        self.client = self.enterContext(
            TestClient(
                create_app(
                    document_revisions=self.f.service,
                    capability_digest=capability_token_digest("a" * 64),
                    expected_authority="127.0.0.1:49152",
                ),
                base_url="http://127.0.0.1:49152",
                headers={"Authorization": "Bearer " + "a" * 64},
                client=("127.0.0.1", 50000),
            )
        )
        self.session = {
            "root": self.f.f.preview.root,
            "projectId": self.accepted.project_id,
            "sessionId": self.f.f.session,
        }

    def post(self, action, **fields):
        return self.client.post("/native/document-revisions/" + action, json=self.session | fields)

    def test_create_reopen_highlight_input_and_current_authority_use_actual_composition(self):
        selection = {
            "schemaVersion": "1.0",
            "revisionId": self.accepted.revision_id,
            "nodeId": self.accepted.structure.nodes[0].node_id,
            "normalizedRange": {"start": 25, "end": 49},
        }
        command = new_uuid_v7()
        created = self.post("anchor-create", commandId=command, selection=selection)
        self.assertEqual(200, created.status_code)
        anchor = created.json()
        self.assertEqual("Second synthetic passage", anchor["target"]["quote"]["exact"])
        read_fields = {"anchorId": anchor["anchorId"], "expectedRevisionId": self.accepted.revision_id}
        reopened = self.post("anchor-read", **read_fields)
        self.assertEqual(200, reopened.status_code)
        self.assertEqual(anchor, reopened.json())
        replayed = self.post("anchor-create", commandId=command, selection=selection)
        self.assertEqual(200, replayed.status_code)
        self.assertEqual(anchor, replayed.json())
        ids = self.post("anchor-list", revisionId=self.accepted.revision_id)
        self.assertEqual(200, ids.status_code)
        self.assertEqual([anchor["anchorId"]], ids.json()["anchorIds"])
        outline = self.post("reader-outline", revisionId=self.accepted.revision_id)
        self.assertEqual(200, outline.status_code)
        choices = self.post("reader-revisions", attachmentId=self.f.f.source.attachment_id)
        self.assertEqual(200, choices.status_code)
        self.assertEqual(self.accepted.revision_id, choices.json()["revisions"][0]["revisionId"])

        samples = []
        for _ in range(20):
            began = time.perf_counter()
            response = self.post("anchor-read", **read_fields)
            samples.append((time.perf_counter() - began) * 1000)
            self.assertEqual(200, response.status_code)
            self.assertEqual(anchor, response.json())

        output = os.environ.get("RO_ANCHOR_BROWSER_FIXTURE")
        if output:
            path = Path(output).resolve()
            path.relative_to((ROOT / "artifacts/tmp").resolve())
            if path.exists():
                raise AssertionError("owned fixture output already exists")
            # No native root/session/token; only explicitly synthetic passage data.
            path.write_text(
                json.dumps(
                    {
                        "kind": "synthetic-anchor-from-actual-Core-native-composition",
                        "anchor": anchor,
                        "outline": outline.json(),
                        "anchorIds": ids.json()["anchorIds"],
                        "readTimingsMs": samples,
                        "warmP95Ms": sorted(samples)[18],
                        "timingScope": "in-process-HTTP/current-native-authority/SQLCipher/context-authentication",
                        "parsing": "declared-synthetic-predecessor-IR",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        wrong = self.post("anchor-read", anchorId=anchor["anchorId"], expectedRevisionId=new_uuid_v7())
        self.assertEqual(409, wrong.status_code)
        self.assertNotIn("Second synthetic", wrong.text)
        self.f.f.permit(derive="denied")
        denied = self.post("anchor-read", **read_fields)
        self.assertEqual(409, denied.status_code)
        self.assertNotIn("Second synthetic", denied.text)
        self.assertEqual(409, self.post("anchor-create", commandId=command, selection=selection).status_code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
