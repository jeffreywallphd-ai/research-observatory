"""CorpusItem keeps its exact kind inside the frozen v1 provenance grammar."""

from __future__ import annotations

import json
import unittest

from research_observatory_core.ports.repositories import AggregateRevision, AtomicRepositoryEvent
from research_observatory_core.provenance import (
    canonical_aggregate_provenance_event,
    canonical_invalidation_provenance_event,
)
from research_observatory_core.provenance_contracts import provenance_event_errors

_PROJECT = "123e4567-e89b-42d3-a456-426614174000"
_ITEM = "018f0000-0000-7000-8000-000000000101"
_REVISION = "018f0000-0000-7000-8000-000000000102"
_ACTOR = "018f0000-0000-7000-8000-000000000103"
_TIME = "2026-09-30T12:00:00.000Z"


def _revision() -> AggregateRevision:
    return AggregateRevision(
        revision_id=_REVISION,
        aggregate_id=_ITEM,
        aggregate_kind="corpus-item",
        project_id=_PROJECT,
        revision=0,
        contract_version="2.0.0",
        created_at=_TIME,
        modified_at=_TIME,
        display_label_observed="Corpus item",
        display_label_normalized=None,
        knowledge_status="observed",
        rights_status="unknown",
    )


def _event() -> AtomicRepositoryEvent:
    return AtomicRepositoryEvent(
        event_id="018f0000-0000-7000-8000-000000000104",
        outbox_id="018f0000-0000-7000-8000-000000000105",
        event_type="corpus-item.created",
        occurred_at=_TIME,
        available_at=_TIME,
        trace_id="1" * 32,
        actor_type="human",
        actor_id=_ACTOR,
        idempotency_key="corpus-test",
    )


class CorpusProvenanceTypeTests(unittest.TestCase):
    def test_revision_event_uses_portable_type_and_exact_corpus_subject(self) -> None:
        event = json.loads(canonical_aggregate_provenance_event(revision=_revision(), previous=None, event=_event()))
        self.assertEqual((), provenance_event_errors(event))
        self.assertEqual("org.research-observatory.corpus.revision-recorded.v1", event["type"])
        self.assertIn("/entity/corpus-item/", event["subject"])
        self.assertEqual("corpus-item", event["data"]["outputs"][0]["entityKind"])

    def test_invalidation_event_preserves_exact_corpus_subject(self) -> None:
        event = json.loads(canonical_invalidation_provenance_event(revision=_revision(), event=_event()))
        self.assertEqual((), provenance_event_errors(event))
        self.assertEqual("org.research-observatory.corpus.invalidated.v1", event["type"])
        self.assertIn("/entity/corpus-item/", event["subject"])


if __name__ == "__main__":
    unittest.main()
