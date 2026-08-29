from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.ports.repositories import AggregateRevisionDraft, AtomicRepositoryEvent
from research_observatory_core.projects import ProjectLifecycleService
from research_observatory_core.provenance import ProvenanceService
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_provenance_ledger_repository,
)
from research_observatory_core.storage import development_plaintext_database_fixture

TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}
CREATED_AT = "2026-08-29T10:00:00.000Z"
ACTOR_ID = "018f0000-0000-7000-8000-000000000001"
AGGREGATE_ID = "018f0000-0000-7000-8000-000000000101"


def draft(index: int) -> AggregateRevisionDraft:
    return AggregateRevisionDraft(
        revision_id=f"018f0000-0000-7000-8000-{index + 200:012x}",
        aggregate_id=AGGREGATE_ID,
        aggregate_kind="evidence",
        created_at=CREATED_AT,
        modified_at=f"2026-08-29T10:00:{index:02d}.000Z",
        display_label_observed=f"Evidence revision {index}",
        display_label_normalized=None,
        knowledge_status="verified" if index > 1 else "extracted",
        rights_status="allowed",
    )


def event(index: int) -> AtomicRepositoryEvent:
    return AtomicRepositoryEvent(
        event_id=f"018f0000-0000-7000-8000-{index + 300:012x}",
        outbox_id=f"018f0000-0000-7000-8000-{index + 400:012x}",
        event_type="evidence.revised" if index else "evidence.created",
        occurred_at=f"2026-08-29T10:01:{index:02d}.000Z",
        available_at=f"2026-08-29T10:01:{index:02d}.000Z",
        trace_id=f"{index + 1:032x}",
        actor_type="human",
        actor_id=ACTOR_ID,
        idempotency_key=f"evidence-write-{index}",
    )


class ProvenanceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-provenance-service-")
        self.projects = ProjectLifecycleService()
        created = self.projects.create(
            parent_directory=self.temporary.name,
            directory_name="lineage-study",
            display_name="Lineage Study",
            template_id="theory-synthesis",
            trace_id="a" * 32,
        )
        self.root = created.root
        opened = self.projects.open(root=self.root, trace_id="b" * 32)
        factory = create_sqlite_unit_of_work_factory(Path(self.root) / "state" / "project.sqlite3", opened.project_id)
        with factory() as unit:
            self.first = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()
        with factory() as unit:
            self.second = unit.aggregates.append(draft(2), event(1), expected_revision=0)
            unit.commit()
        provenance = ProvenanceService(self.projects, sqlite_provenance_ledger_repository)
        self.app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            projects=self.projects,
            provenance=provenance,
        )

    def tearDown(self) -> None:
        self.projects.shutdown()
        self.temporary.cleanup()
        self.database_profile.__exit__(None, None, None)

    def test_api_returns_bounded_ancestors_with_activity_and_responsible_agent(self) -> None:
        with TestClient(
            self.app,
            base_url=f"http://{AUTHORITY}",
            headers=AUTH_HEADERS,
            client=("127.0.0.1", 50000),
        ) as client:
            response = client.post(
                "/projects/provenance/lineage",
                json={
                    "root": self.root,
                    "revisionId": self.second.revision_id,
                    "direction": "ancestors",
                    "pageSize": 10,
                    "maxDepth": 4,
                },
            )
            rejected = client.post(
                "/projects/provenance/lineage",
                json={
                    "root": self.root,
                    "revisionId": self.second.revision_id,
                    "direction": "ancestors",
                    "pageSize": 101,
                    "maxDepth": 4,
                },
            )

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("verified", body["integrityState"])
        self.assertEqual(
            [self.second.revision_id, self.first.revision_id],
            [item["revisionId"] for item in body["items"]],
        )
        self.assertEqual([0, 1], [item["depth"] for item in body["items"]])
        self.assertTrue(all(item["agentId"] == ACTOR_ID for item in body["items"]))
        self.assertTrue(all(item["activityType"] == "evidence.write" for item in body["items"]))
        self.assertEqual(422, rejected.status_code)


if __name__ == "__main__":
    unittest.main()
