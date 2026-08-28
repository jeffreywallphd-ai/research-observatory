from __future__ import annotations

import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.domain_lifecycles import (  # noqa: E402
    DomainLifecycleProblem,
    apply_lifecycle_transition,
    prepare_lifecycle_transition,
)

AGGREGATE_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a1"


def snapshot(state: str, revision: int = 0) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-lifecycle-snapshot",
        "profileVersion": "1.0.0",
        "subjectKind": "dossier",
        "aggregateId": AGGREGATE_ID,
        "state": state,
        "revision": revision,
    }


def command(name: str, revision: int = 0) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-lifecycle-command",
        "profileVersion": "1.0.0",
        "subjectKind": "dossier",
        "aggregateId": AGGREGATE_ID,
        "expectedRevision": revision,
        "command": name,
        "actor": {"kind": "human", "id": "researcher:local-owner"},
        "reason": {"code": "review-decision", "detail": "The authorized reviewer completed the bounded assessment."},
        "occurredAt": "2026-08-28T13:50:00.000Z",
        "idempotencyKey": f"dossier.{name}.{revision}",
    }


class DomainLifecycleServiceTests(unittest.TestCase):
    def test_validation_precedes_the_persistence_boundary(self) -> None:
        writes: list[object] = []
        with self.assertRaises(DomainLifecycleProblem) as denied:
            apply_lifecycle_transition(snapshot("draft"), command("approve"), writes.append)
        self.assertEqual("lifecycle-command-not-allowed", denied.exception.code)
        self.assertEqual([], writes)

        accepted = apply_lifecycle_transition(snapshot("draft"), command("submit"), writes.append)
        self.assertEqual([accepted], writes)
        self.assertEqual("in-review", accepted["toState"])

    def test_committed_projection_restarts_at_the_exact_next_revision(self) -> None:
        submitted = prepare_lifecycle_transition(snapshot("draft"), command("submit"))
        submitted_revision = cast(int, submitted["revision"])
        restarted = snapshot(str(submitted["toState"]), submitted_revision)
        approved = prepare_lifecycle_transition(restarted, command("approve", submitted_revision))
        self.assertEqual("approved", approved["toState"])
        self.assertEqual(2, approved["revision"])
        approved_actor = cast(Mapping[str, object], approved["actor"])
        approved_reason = cast(Mapping[str, object], approved["reason"])
        self.assertEqual("researcher:local-owner", approved_actor["id"])
        self.assertEqual("review-decision", approved_reason["code"])

    def test_stale_revision_and_hostile_reason_return_only_stable_codes(self) -> None:
        stale = command("submit", 0)
        cast(dict[str, object], stale["reason"])["detail"] = "private manuscript text that must not enter errors"
        with self.assertRaises(DomainLifecycleProblem) as conflict:
            prepare_lifecycle_transition(snapshot("draft", 3), stale)
        self.assertEqual(("lifecycle-revision-conflict",), conflict.exception.codes)
        self.assertNotIn("manuscript", str(conflict.exception))

        hostile = command("submit")
        cast(dict[str, object], hostile["reason"])["detail"] = "unsafe\ncontent"
        with self.assertRaises(DomainLifecycleProblem) as invalid:
            prepare_lifecycle_transition(snapshot("draft"), hostile)
        self.assertEqual(("lifecycle-command-invalid",), invalid.exception.codes)
        self.assertNotIn("unsafe", str(invalid.exception))


if __name__ == "__main__":
    unittest.main()
