"""Canonical subtype identities cannot be borrowed from other scholarly objects."""

import unittest

from research_observatory_core.reconciliation.versions import VersionDate, VersionDefinition
from research_observatory_core.reconciliation_repository import _digest
from research_observatory_core.storage import _DATABASE_ERRORS

from tests.reconciliation import test_review_repository as fixtures


class VersionStorageTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ReviewRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_work_genesis_cannot_be_reclassified_as_a_work_version(self):
        f = self.f
        with f.repo._transaction(write=True) as (db, aggregates):
            decision = f.repo._append(
                aggregates,
                sources=(),
                actor=f.actor,
                digest="a" * 64,
                kind="decision",
                label="Synthetic unrelated decision",
            )
            with self.assertRaises(_DATABASE_ERRORS):
                db.execute(
                    "INSERT INTO reconciliation_versions (revision_id,project_id,version_id,"
                    "previous_revision_id,version_kind,date_precision,date_value,decision_revision_id,"
                    "source_count,status_sha256,content_sha256) VALUES (?,?,?,NULL,'preprint','unknown',NULL,?,"
                    "1,?,?)",
                    (f.a.work_revision_id, f.fixture.project, f.a.work_id, decision.revision_id, "a" * 64, "b" * 64),
                )

    def test_work_version_identity_cannot_later_be_reclassified_as_a_work(self):
        f = self.f
        with f.repo._transaction(write=True) as (db, aggregates):
            decision = f.repo._append(
                aggregates, sources=(), actor=f.actor, digest="a" * 64, kind="decision", label="Synthetic decision"
            )
            version = self.version(db, aggregates, decision, f.a.assertion_revision_id)
            with self.assertRaises(_DATABASE_ERRORS):
                db.execute(
                    "INSERT INTO reconciliation_work_states (revision_id,project_id,work_id,"
                    "previous_revision_id,disposition,alias_target,decision_revision_id) VALUES (?,?,?,NULL,"
                    "'active',NULL,?)",
                    (version.revision_id, f.fixture.project, version.aggregate_id, decision.revision_id),
                )

    def test_unrelated_decision_cannot_be_reclassified_as_a_version_preference(self):
        f = self.f
        with f.repo._transaction(write=True) as (db, aggregates):
            decision = f.repo._append(
                aggregates,
                sources=(),
                actor=f.actor,
                digest="a" * 64,
                kind="decision",
                label="Synthetic unrelated decision",
            )
            version = self.version(db, aggregates, decision, f.a.assertion_revision_id)
            with self.assertRaises(_DATABASE_ERRORS):
                db.execute(
                    "INSERT INTO reconciliation_version_preferences (revision_id,project_id,preference_id,"
                    "previous_revision_id,decision_revision_id,work_revision_id,work_id,selected_revision_id,"
                    "membership_sha256,status_sha256) VALUES (?,?,?,NULL,?,?,?,?,?,?)",
                    (
                        decision.revision_id,
                        f.fixture.project,
                        decision.aggregate_id,
                        decision.revision_id,
                        f.a.work_revision_id,
                        f.a.work_id,
                        version.revision_id,
                        "a" * 64,
                        "b" * 64,
                    ),
                )

    def version(self, db, aggregates, decision, assertion):
        definition = VersionDefinition(
            kind="preprint", assertion_revision_ids=(assertion,), date=VersionDate(precision="unknown", value=None)
        )
        status = _digest([])
        digest = _digest([definition.model_dump(mode="json", by_alias=True), None, decision.revision_id, status])
        version = self.f.repo._append(
            aggregates,
            sources=(decision,),
            actor=self.f.actor,
            digest=digest,
            label="Synthetic version",
            payload_configuration="version-content",
        )
        db.execute(
            "INSERT INTO reconciliation_versions (revision_id,project_id,version_id,previous_revision_id,"
            "version_kind,date_precision,date_value,decision_revision_id,source_count,status_sha256,"
            "content_sha256) VALUES (?,?,?,NULL,'preprint','unknown',NULL,?,1,?,?)",
            (version.revision_id, self.f.fixture.project, version.aggregate_id, decision.revision_id, status, digest),
        )
        db.execute(
            "INSERT INTO reconciliation_version_sources VALUES (?,?,1,?)",
            (version.revision_id, self.f.fixture.project, assertion),
        )
        return version

    def test_work_genesis_cannot_be_reclassified_as_a_version_relation(self):
        f = self.f
        with f.repo._transaction(write=True) as (db, aggregates):
            decision = f.repo._append(
                aggregates,
                sources=(),
                actor=f.actor,
                digest="a" * 64,
                kind="decision",
                label="Synthetic unrelated decision",
            )
            source = self.version(db, aggregates, decision, f.a.assertion_revision_id)
            target = self.version(db, aggregates, decision, f.b.assertion_revision_id)
            with self.assertRaises(_DATABASE_ERRORS):
                db.execute(
                    "INSERT INTO reconciliation_version_relations (revision_id,project_id,relation_id,"
                    "decision_revision_id,source_revision_id,target_revision_id,relation_kind,knowledge_status,"
                    "date_precision,date_value,evidence_count,content_sha256) VALUES (?,?,?,?,?,?,"
                    "'is-version-of','adjudicated','unknown',NULL,1,?)",
                    (
                        f.a.work_revision_id,
                        f.fixture.project,
                        f.a.work_id,
                        decision.revision_id,
                        source.revision_id,
                        target.revision_id,
                        "a" * 64,
                    ),
                )
