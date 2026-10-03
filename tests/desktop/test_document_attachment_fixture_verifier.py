"""Canonical project identity accepted by the read-only attachment verifier."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/desktop/tools"))
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.ports.repositories import AggregateRevision, AtomicRepositoryEvent  # noqa: E402
from research_observatory_core.provenance import canonical_aggregate_provenance_event  # noqa: E402
from verify_document_attachment_fixture import (  # noqa: E402
    Expected,
    FixtureFailure,
    _project_id,
    _require_provenance_binding,
)

_PROJECT = "f52f40de-6a15-455c-b180-269a76267051"
_DOCUMENT = "01a1001f-ac2d-7d87-acd6-a4a61497a3a0"
_REVISION = "01a1001f-ac2d-7d87-acd6-a4a61497a3a1"
_ACTOR = "01a1001f-ac2d-7d87-acd6-a4a61497a3a2"
_COMMAND = "01a1001f-ac2d-7d87-acd6-a4a61497a3a3"
_TIME = "2026-10-03T08:00:00.000Z"


class ProjectIdentityTests(unittest.TestCase):
    def test_existing_uuid4_bridge_and_new_uuid7_projects_are_canonical(self) -> None:
        self.assertTrue(_project_id("f52f40de-6a15-455c-b180-269a76267051"))
        self.assertTrue(_project_id("01a1001f-ac2d-7d87-acd6-a4a61497a3a0"))

    def test_case_malformed_and_wrong_version_fail_closed(self) -> None:
        self.assertFalse(_project_id("F52F40DE-6A15-455C-B180-269A76267051"))
        self.assertFalse(_project_id("f52f40de-6a15-455c-b180-269a7626705"))
        self.assertFalse(_project_id("01a1001f-ac2d-1d87-acd6-a4a61497a3a0"))


class AttachmentProvenanceBindingTests(unittest.TestCase):
    def test_verifier_accepts_cores_canonical_document_event_and_rejects_wrong_bindings(self) -> None:
        revision = AggregateRevision(
            revision_id=_REVISION,
            aggregate_id=_DOCUMENT,
            aggregate_kind="document",
            project_id=_PROJECT,
            revision=0,
            contract_version="2.0.0",
            created_at=_TIME,
            modified_at=_TIME,
            display_label_observed="Synthetic document",
            display_label_normalized=None,
            knowledge_status="observed",
            rights_status="allowed",
        )
        event = AtomicRepositoryEvent(
            event_id="01a1001f-ac2d-7d87-acd6-a4a61497a3a4",
            outbox_id="01a1001f-ac2d-7d87-acd6-a4a61497a3a5",
            event_type="document.attached",
            occurred_at=_TIME,
            available_at=_TIME,
            trace_id="1" * 32,
            actor_type="human",
            actor_id=_ACTOR,
            idempotency_key="document-attachment-" + _COMMAND,
        )
        canonical = json.loads(canonical_aggregate_provenance_event(revision=revision, previous=None, event=event))
        expected = Expected(
            project_id=_PROJECT,
            work_id="01a1001f-ac2d-7d87-acd6-a4a61497a3a6",
            work_revision_id="01a1001f-ac2d-7d87-acd6-a4a61497a3a7",
            version_id="01a1001f-ac2d-7d87-acd6-a4a61497a3a8",
            version_revision_id="01a1001f-ac2d-7d87-acd6-a4a61497a3a9",
            source_assertion_revision_id="01a1001f-ac2d-7d87-acd6-a4a61497a3aa",
            source_sha256="a" * 64,
            operation_id="01a1001f-ac2d-7d87-acd6-a4a61497a3ab",
            command_id=_COMMAND,
            attachment_id="01a1001f-ac2d-7d87-acd6-a4a61497a3ac",
            document_revision_id=_REVISION,
            candidate_id=None,
        )
        attachment = {"actor_id": _ACTOR, "committed_at": _TIME}
        provenance = {
            "project_id": _PROJECT,
            "outbox_project_id": _PROJECT,
            "revision_id": _REVISION,
            "outbox_revision_id": _REVISION,
            "event_type": canonical["type"],
            "outbox_event_type": canonical["type"],
            "actor_type": "human",
            "actor_id": _ACTOR,
            "occurred_at": _TIME,
            "record_sha256": "b" * 64,
            "outbox_record_sha256": "b" * 64,
            "idempotency_key": event.idempotency_key,
        }

        _require_provenance_binding(provenance, attachment, expected)
        for changed in (
            {"event_type": "document.attached", "outbox_event_type": "document.attached"},
            {"outbox_record_sha256": "c" * 64},
            {"outbox_revision_id": _DOCUMENT},
        ):
            with (
                self.subTest(changed=changed),
                self.assertRaisesRegex(FixtureFailure, "attachment-provenance-binding-mismatch"),
            ):
                _require_provenance_binding(provenance | changed, attachment, expected)


if __name__ == "__main__":
    unittest.main()
