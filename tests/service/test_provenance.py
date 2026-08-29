from __future__ import annotations

import tempfile
import unittest
from itertools import pairwise
from pathlib import Path

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.ports.repositories import (
    ActorType,
    AggregateKind,
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    RightsStatus,
)
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


def draft(
    index: int,
    *,
    aggregate_id: str = AGGREGATE_ID,
    aggregate_kind: AggregateKind = "evidence",
    provenance_inputs: tuple[AggregateRevision, ...] = (),
    rights_status: RightsStatus = "allowed",
) -> AggregateRevisionDraft:
    return AggregateRevisionDraft(
        revision_id=f"018f0000-0000-7000-8000-{index + 200:012x}",
        aggregate_id=aggregate_id,
        aggregate_kind=aggregate_kind,
        created_at=CREATED_AT,
        modified_at=f"2026-08-29T10:00:{index:02d}.000Z",
        display_label_observed=f"Evidence revision {index}",
        display_label_normalized=None,
        knowledge_status="verified" if index > 1 else "extracted",
        rights_status=rights_status,
        provenance_inputs=provenance_inputs,
    )


def event(index: int, *, actor_type: ActorType = "human") -> AtomicRepositoryEvent:
    return AtomicRepositoryEvent(
        event_id=f"018f0000-0000-7000-8000-{index + 300:012x}",
        outbox_id=f"018f0000-0000-7000-8000-{index + 400:012x}",
        event_type="evidence.revised" if index else "evidence.created",
        occurred_at=f"2026-08-29T10:01:{index:02d}.000Z",
        available_at=f"2026-08-29T10:01:{index:02d}.000Z",
        trace_id=f"{index + 1:032x}",
        actor_type=actor_type,
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
        self.factory = create_sqlite_unit_of_work_factory(
            Path(self.root) / "state" / "project.sqlite3", opened.project_id
        )
        with self.factory() as unit:
            self.first = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()
        with self.factory() as unit:
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
        self.assertEqual(self.second.revision_id, body["items"][0]["revisionId"])
        self.assertEqual(0, body["items"][0]["depth"])
        depths = [item["depth"] for item in body["items"]]
        self.assertTrue(all(left <= right for left, right in pairwise(depths)))
        self.assertEqual(
            {"wasDerivedFrom", "wasGeneratedBy", "wasAttributedTo"},
            {item["relationType"] for item in body["items"] if item["revisionId"] == self.second.revision_id},
        )
        self.assertTrue(all(item["agentId"] == ACTOR_ID for item in body["items"]))
        self.assertTrue(all(item["agentType"] == "human" for item in body["items"]))
        self.assertTrue(all(item["agentRole"] == "canonical.writer" for item in body["items"]))
        self.assertTrue(all(item["activityType"] == "evidence.write" for item in body["items"]))
        self.assertTrue(all(item["configurationId"] == "core.aggregate-write" for item in body["items"]))
        self.assertTrue(all(item["configurationVersion"] == "1.0.0" for item in body["items"]))
        self.assertTrue(all(item["configurationHash"].startswith("sha256:") for item in body["items"]))
        self.assertTrue(body["exportAllowed"])
        self.assertIsNone(body["exportDenialReason"])
        self.assertEqual(422, rejected.status_code)

    def test_real_cross_aggregate_trace_keeps_sources_decision_and_valid_invalidation_visible(self) -> None:
        with self.factory() as unit:
            alternate = unit.aggregates.append(
                draft(3, aggregate_id="018f0000-0000-7000-8000-000000000102"),
                event(2),
                expected_revision=None,
            )
            unit.commit()
        with self.factory() as unit:
            decision = unit.aggregates.append(
                draft(
                    4,
                    aggregate_id="018f0000-0000-7000-8000-000000000103",
                    aggregate_kind="decision",
                ),
                event(3),
                expected_revision=None,
            )
            unit.commit()
        with self.factory() as unit:
            synthesis_sentence = unit.aggregates.append(
                draft(
                    5,
                    aggregate_id="018f0000-0000-7000-8000-000000000104",
                    aggregate_kind="record",
                    provenance_inputs=(self.second, alternate, decision),
                ),
                event(4, actor_type="model"),
                expected_revision=None,
            )
            unit.commit()
        invalidation = event(5)
        with self.factory() as unit:
            unit.aggregates.invalidate(alternate.revision_id, invalidation)
            unit.commit()
        with self.factory() as unit:
            unit.aggregates.invalidate(alternate.revision_id, invalidation)
            unit.commit()

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
                    "revisionId": synthesis_sentence.revision_id,
                    "direction": "ancestors",
                    "pageSize": 50,
                    "maxDepth": 8,
                },
            )
            paged_items: list[dict[str, object]] = []
            cursor = 0
            while True:
                page_response = client.post(
                    "/projects/provenance/lineage",
                    json={
                        "root": self.root,
                        "revisionId": synthesis_sentence.revision_id,
                        "direction": "ancestors",
                        "cursor": cursor,
                        "pageSize": 2,
                        "maxDepth": 8,
                    },
                )
                self.assertEqual(200, page_response.status_code, page_response.text)
                page = page_response.json()
                paged_items.extend(page["items"])
                if page["nextCursor"] is None:
                    break
                self.assertGreater(page["nextCursor"], cursor)
                cursor = page["nextCursor"]

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        revisions = {item["revisionId"] for item in body["items"]}
        self.assertTrue(
            {synthesis_sentence.revision_id, self.second.revision_id, alternate.revision_id, decision.revision_id}
            <= revisions
        )
        self.assertTrue(
            any(
                item["revisionId"] == synthesis_sentence.revision_id
                and item["relationType"] == "wasDerivedFrom"
                and item["agentType"] == "model"
                for item in body["items"]
            )
        )
        self.assertEqual(
            {self.second.revision_id, alternate.revision_id, decision.revision_id},
            {
                item["relatedRevisionId"]
                for item in body["items"]
                if item["revisionId"] == synthesis_sentence.revision_id and item["relationType"] == "wasDerivedFrom"
            },
        )
        self.assertTrue(
            any(
                item["revisionId"] == alternate.revision_id
                and item["relationType"] == "wasInvalidatedBy"
                and item["entityDirection"] == "input"
                for item in body["items"]
            )
        )
        self.assertTrue(any(item["entityKind"] == "decision" for item in body["items"]))
        self.assertEqual(len({item["factId"] for item in body["items"]}), len(body["items"]))
        self.assertEqual(
            [item["factId"] for item in body["items"]],
            [item["factId"] for item in paged_items],
        )
        self.assertEqual("verified", body["integrityState"])
        self.assertTrue(body["exportAllowed"])

    def test_rights_restricted_target_denies_manifest_export_at_the_service_boundary(self) -> None:
        with self.factory() as unit:
            restricted = unit.aggregates.append(
                draft(
                    6,
                    aggregate_id="018f0000-0000-7000-8000-000000000105",
                    rights_status="denied",
                ),
                event(6),
                expected_revision=None,
            )
            unit.commit()
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
                    "revisionId": restricted.revision_id,
                    "direction": "ancestors",
                    "pageSize": 10,
                    "maxDepth": 4,
                },
            )
        self.assertEqual(200, response.status_code, response.text)
        self.assertFalse(response.json()["exportAllowed"])
        self.assertEqual("rights-restricted", response.json()["exportDenialReason"])


if __name__ == "__main__":
    unittest.main()
