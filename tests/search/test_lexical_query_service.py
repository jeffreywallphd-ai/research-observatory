"""Canonical authority around protected BM25, without renderer or HTTP fixtures."""

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.lexical_index_repository import IndexServiceProblem  # noqa: E402
from research_observatory_core.lexical_index_store import ProtectedLexicalStore  # noqa: E402
from research_observatory_core.lexical_input_repository import (  # noqa: E402
    rights_time_partition,
    source_authority_epoch,
)
from research_observatory_core.rights_policy import RightsPolicyRevision  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402

from tests.search.fixture_support import CanonicalIndexFixture  # noqa: E402


class LexicalQueryServiceTests(CanonicalIndexFixture):
    def reader(self):
        from research_observatory_core.lexical_query_repository import CoreLexicalQueryService

        return CoreLexicalQueryService(self.service)

    def test_stable_rank_has_exact_current_selection_and_complete_input_identity(self):
        selected = self.service.rebuild()
        first = self.reader().read(parse_query("identifiers:synthetic"))
        second = self.reader().read(parse_query("identifiers:synthetic"))
        self.assertEqual(first, second)
        self.assertEqual(selected.selection_id, first.generation.selection_id)
        self.assertEqual(selected.projection_sha256, first.generation.projection_sha256)
        self.assertEqual(self.service.catalog.watermark(), first.validation.watermark)
        self.assertEqual((self.f.item.item_id,), tuple(hit.item_id for hit in first.ranked))
        self.assertEqual(64, len(first.input_sha256))
        with self.f.corpus.repository._transaction(write=False) as (db, _aggregates):
            for revision in first.source_revisions:
                self.assertIsNotNone(
                    db.execute(
                        "SELECT 1 FROM aggregate_revisions WHERE project_id=? AND revision_id=?",
                        (self.service.project, revision),
                    ).fetchone()
                )

    def test_revoked_nonmatching_text_blocks_statistics_before_any_rank_call(self):
        parsed = self.f.f.parse("entirely unrelated gamma passage")
        self.f.f.repository.accept(self.f.f.command(parsed))
        subject = self.f.f.f.candidate.rights_subject
        grant = self.f.permit(subject, previous=self.f.f.f.policy.revision_id)
        self.service.rebuild()
        self.assertTrue(self.reader().read(parse_query("identifiers:synthetic")).ranked)
        self.f.permit(subject, previous=grant.revision_id, index="denied")
        with patch.object(ProtectedLexicalStore, "rank") as ranked, self.assertRaises(IndexServiceProblem):
            self.reader().read(parse_query("identifiers:synthetic"))
        ranked.assert_not_called()
        self.service.synchronize()
        self.assertEqual(1, len(self.reader().read(parse_query("identifiers:synthetic")).ranked))

    def test_expiry_at_delivery_discards_buffered_result(self):
        expiry = (datetime.now(UTC) + timedelta(minutes=2)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        self.f.permit(self.subject, previous=self.grant.revision_id, corpus_membership=True, expires_at=expiry)
        self.service.rebuild()

        def expired(snapshot, _store):
            self.service.catalog.now = lambda: expiry
            return snapshot

        with self.assertRaises(IndexServiceProblem):
            self.reader().read(parse_query("identifiers:synthetic"), consume=expired)

    def test_source_change_or_cancellation_during_delivery_discards_buffered_result(self):
        self.service.rebuild()
        stopped = False

        def stop(snapshot, _store):
            nonlocal stopped
            stopped = True
            return snapshot

        with self.assertRaises(IndexServiceProblem):
            self.reader().read(parse_query("identifiers:synthetic"), consume=stop, cancelled=lambda: stopped)

        def revoke(snapshot, _store):
            self.f.permit(self.subject, previous=self.grant.revision_id, corpus_membership=True, index="denied")
            return snapshot

        with self.assertRaises(IndexServiceProblem):
            self.reader().read(parse_query("identifiers:synthetic"), consume=revoke)

    def test_nonoutbox_object_state_change_at_delivery_is_denied(self):
        self.service.rebuild()
        head = self.service.catalog.watermark()

        def quarantine(snapshot, _store):
            with self.f.corpus.repository._transaction(write=True) as (db, _aggregates):
                db.execute(
                    "UPDATE object_records SET storage_state='quarantined',verified_at=NULL "
                    "WHERE storage_state='available'"
                )
            self.assertEqual(head, self.service.catalog.watermark())
            return snapshot

        with self.assertRaises(IndexServiceProblem):
            self.reader().read(parse_query("identifiers:synthetic"), consume=quarantine)

    def test_clock_rollback_during_delivery_denies_with_unchanged_time_partition(self):
        self.service.rebuild()
        baseline = datetime.now(UTC) + timedelta(minutes=1)
        baseline = baseline.replace(microsecond=baseline.microsecond // 1000 * 1000)
        earlier = baseline - timedelta(milliseconds=1)

        def stamp(value: datetime) -> str:
            return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        self.service.catalog.now = lambda: stamp(baseline)
        with self.f.corpus.repository._transaction(write=False) as (db, _aggregates):
            self.assertEqual(
                rights_time_partition(db, self.service.project, stamp(baseline)),
                rights_time_partition(db, self.service.project, stamp(earlier)),
            )

        def roll_back(snapshot, _store):
            self.assertEqual(stamp(baseline), snapshot.validated_at)
            self.service.catalog.now = lambda: stamp(earlier)
            return snapshot

        with self.assertRaises(IndexServiceProblem):
            self.reader().read(parse_query("identifiers:synthetic"), consume=roll_back)

    def test_future_nonmatching_permission_activation_denies_without_source_writes(self):
        parsed = self.f.f.parse("Entirely unrelated activation boundary passage")
        self.f.f.repository.accept(self.f.f.command(parsed))
        subject = self.f.f.f.candidate.rights_subject
        grant = self.f.permit(subject, previous=self.f.f.f.policy.revision_id)
        baseline = datetime.now(UTC)
        baseline = baseline.replace(microsecond=baseline.microsecond // 1000 * 1000)
        boundary = baseline + timedelta(minutes=1)
        instant = baseline

        def stamp(value: datetime) -> str:
            return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        # A real immutable typed policy, with real retained source/evidence IDs.
        # A future recordedAt assertion is deliberately not yet effective.
        policy = RightsPolicyRevision(
            revision_id=new_uuid_v7(),
            predecessor_revision_id=grant.revision_id,
            subject=subject,
            permissions=tuple(
                permission.model_copy(
                    update={
                        "assertion_id": new_uuid_v7(),
                        "recorded_at": stamp(boundary),
                        "expires_at": None,
                    }
                )
                for permission in grant.permissions
            ),
        )
        self.f.attachments.rights.publish(
            policy,
            command_id=new_uuid_v7(),
            command_sha256="c" * 64,
            actor=self.f.f.actor,
        )
        self.service.catalog.now = lambda: stamp(instant)
        with patch("research_observatory_core.rights_repository._utcnow", side_effect=lambda: instant):
            self.service.rebuild()
            captured = self.f.sources.capture(self.f.item.item_id)
            self.assertTrue(captured.rows)
            self.assertFalse(any(row.full_text for row in captured.rows))
            watermark = self.service.catalog.watermark()
            with self.f.corpus.repository._transaction(write=False) as (db, _aggregates):
                epoch = source_authority_epoch(db, self.service.project)
                self.assertLess(
                    rights_time_partition(db, self.service.project, stamp(baseline)),
                    rights_time_partition(db, self.service.project, stamp(boundary)),
                )

            def activate(snapshot, _store):
                nonlocal instant
                self.assertTrue(snapshot.ranked)
                self.assertIsNone(snapshot.validation.expires_at)
                instant = boundary
                return snapshot

            with self.assertRaises(IndexServiceProblem):
                self.reader().read(parse_query("identifiers:synthetic"), consume=activate)
            self.assertEqual(watermark, self.service.catalog.watermark())
            with self.f.corpus.repository._transaction(write=False) as (db, _aggregates):
                self.assertEqual(epoch, source_authority_epoch(db, self.service.project))
            after = self.f.sources.capture(self.f.item.item_id)
            self.assertTrue(any("activation boundary" in row.full_text for row in after.rows))


if __name__ == "__main__":
    unittest.main()
