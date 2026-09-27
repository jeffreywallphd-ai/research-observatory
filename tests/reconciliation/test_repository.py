"""Real canonical database publication, rollback, source preservation and replay."""

import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ports.reconciliation import ReconciliationActor
from research_observatory_core.reconciliation.contracts import (
    ReconciliationProblem,
    ScholarlyField,
    SourceAddress,
    SourceAssertion,
)
from research_observatory_core.reconciliation.exact import IdentifierAssertion
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.storage import open_canonical_database

from tests.data import test_import_commit_publication as import_fixture


class ReconciliationRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = import_fixture.ImportCommitPublicationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        output = self.fixture.publish()
        f = self.fixture.fixture
        self.database, self.project = f.database, f.inputs.project_id
        member = next(
            item
            for item in f.repository.manifest_members(output.revision_id, after=0, limit=100)
            if item.decision.included
        )
        self.address = SourceAddress(
            kind="import-member",
            context_id=f.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        permission = ImportPermission(value="permitted", basis="researcher-confirmed")
        assert member.source_record_revision_id is not None
        self.source = SourceAssertion(
            project_id=self.project,
            address=self.address,
            source_revision_id=member.source_record_revision_id,
            provider="local-import",
            identifiers=(IdentifierAssertion(scheme="doi", observed="10.99999/synthetic-a"),),
            fields=(),
            rights=ImportRights(store=permission, inspect=permission, derive=permission, index=permission),
            source_sha256="2" * 64,
        )
        self.actor = ReconciliationActor(new_uuid_v7(), "3" * 32, f.actor.occurred_at, "4" * 64, "5" * 64)
        self.repository = SqliteReconciliationRepository(self.database, self.project)
        self.resolved = {self.address.revision_id: self.source}
        self.resolve = lambda address: self.resolved[address.revision_id]

    def counts(self):
        with open_canonical_database(self.database, expected_project_id=self.project) as db:
            return tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "aggregate_revisions",
                    "reconciliation_assertions",
                    "reconciliation_work_revisions",
                    "reconciliation_identifier_links",
                    "reconciliation_commands",
                    "provenance_events",
                    "outbox_events",
                )
            )

    def another_source(self, *, identifiers=None):
        self.fixture.prepare_another(raw=b"title,doi\nAnother synthetic record,10.99999/synthetic-a\n")
        output = self.fixture.publish()
        f = self.fixture.fixture
        member = next(
            item
            for item in f.repository.manifest_members(output.revision_id, after=0, limit=100)
            if item.decision.included
        )
        address = SourceAddress(
            kind="import-member",
            context_id=f.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        self.resolved[address.revision_id] = self.source.model_copy(
            update={
                "address": address,
                "source_revision_id": member.source_record_revision_id,
                "identifiers": identifiers or self.source.identifiers,
            }
        )
        return address

    def test_concurrent_sources_cannot_create_two_works_for_the_same_identifier(self):
        second = self.another_source()
        commands = (new_uuid_v7(), new_uuid_v7())

        def submit(item):
            address, command = item
            repository = SqliteReconciliationRepository(self.database, self.project)
            try:
                return repository.reconcile(address, command_id=command, actor=self.actor, resolve=self.resolve)
            except ReconciliationProblem as error:
                self.assertEqual("reconciliation-concurrent-source-change", error.code)
                return repository.reconcile(address, command_id=command, actor=self.actor, resolve=self.resolve)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(submit, zip((self.address, second), commands, strict=True)))
        self.assertEqual(results[0].work_id, results[1].work_id)
        self.assertEqual({"new-work", "exact-linked"}, {item.disposition for item in results})
        self.assertEqual(2, self.counts()[2])

    def test_conflicting_match_is_durable_and_does_not_append_a_work_revision(self):
        original = self.source.model_copy(
            update={"identifiers": (*self.source.identifiers, IdentifierAssertion(scheme="pmid", observed="123"))}
        )
        self.resolved[self.address.revision_id] = original
        first = self.repository.reconcile(
            self.address, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve
        )
        second = self.another_source(
            identifiers=(*self.source.identifiers, IdentifierAssertion(scheme="pmid", observed="456"))
        )
        result = self.repository.reconcile(second, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve)
        self.assertEqual("review-required", result.disposition)
        self.assertIsNone(result.work_id)
        self.assertEqual((first.work_id,), result.candidates)
        self.assertIn("conflicting-identifiers", result.flags)
        self.assertEqual(1, self.counts()[2])
        inspection = SqliteReconciliationRepository(self.database, self.project).inspect(
            result.assertion_revision_id, resolve=self.resolve
        )
        self.assertEqual(result, inspection.result)
        self.assertIsNone(inspection.canonical_work)

    def test_total_source_budget_denies_publication_and_inspection_without_partial_facts(self):
        first = self.repository.reconcile(
            self.address, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve
        )
        second = self.another_source()
        size = sum(len(source.model_dump_json(by_alias=True).encode()) for source in self.resolved.values())
        before = self.counts()
        for limit, value in (("_MAX_SOURCE_BYTES", size - 1), ("_MAX_SOURCE_COUNT", 1)):
            with (
                self.subTest(limit=limit),
                patch("research_observatory_core.reconciliation_repository." + limit, value),
                self.assertRaisesRegex(ReconciliationProblem, "reconciliation-source-limit"),
            ):
                self.repository.reconcile(second, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve)
            self.assertEqual(before, self.counts())
        self.repository.reconcile(second, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve)
        before = self.counts()
        with (
            patch("research_observatory_core.reconciliation_repository._MAX_SOURCE_BYTES", size - 1),
            self.assertRaisesRegex(ReconciliationProblem, "reconciliation-source-limit"),
        ):
            self.repository.inspect(first.assertion_revision_id, resolve=self.resolve)
        self.assertEqual(before, self.counts())

    def test_storage_rejects_untyped_or_substituted_source_assertion_documents(self):
        result = self.repository.reconcile(
            self.address, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve
        )
        before = self.counts()
        with open_canonical_database(self.database, expected_project_id=self.project) as db:
            for field, value in (
                ("schemaVersion", "2.0"),
                ("projectId", new_uuid_v7()),
                ("sourceRevisionId", new_uuid_v7()),
                ("address.revisionId", new_uuid_v7()),
            ):
                with self.subTest(field=field), self.assertRaises(sqlite3.IntegrityError):
                    db.execute(
                        "INSERT INTO reconciliation_assertions "
                        "SELECT ?, project_id, aggregate_kind, source_revision_id, address_revision_id, ?, "
                        "payload_sha256, json_set(assertion_json, ?, ?), result_json "
                        "FROM reconciliation_assertions WHERE revision_id=?",
                        (result.work_revision_id, "9" * 64, "$." + field, value, result.assertion_revision_id),
                    )
        self.assertEqual(before, self.counts())

    def test_publication_survives_restart_and_lost_reply_without_new_facts(self):
        command = new_uuid_v7()
        before = self.counts()
        result = self.repository.reconcile(self.address, command_id=command, actor=self.actor, resolve=self.resolve)
        self.assertEqual("new-work", result.disposition)
        self.assertEqual(before[0] + 2, self.counts()[0])
        after = self.counts()
        reopened = SqliteReconciliationRepository(self.database, self.project)
        self.assertEqual(
            result, reopened.reconcile(self.address, command_id=command, actor=self.actor, resolve=self.resolve)
        )
        self.assertEqual(after, self.counts())
        inspection = reopened.inspect(result.assertion_revision_id, resolve=self.resolve)
        self.assertEqual(self.source, inspection.assertion)
        self.assertEqual(result, inspection.result)
        with open_canonical_database(self.database, expected_project_id=self.project) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM import_source_records").fetchone()[0])
            self.assertEqual(
                2,
                db.execute(
                    "SELECT COUNT(*) FROM material_dependency_outputs WHERE output_revision_id IN (?, ?)",
                    (result.assertion_revision_id, result.work_revision_id),
                ).fetchone()[0],
            )

    def test_current_projection_binds_its_revision_without_rewriting_the_original_receipt(self):
        self.source = self.source.model_copy(
            update={
                "fields": (
                    ScholarlyField(
                        name="title", observed="First synthetic title", origin="observed", source_selector="title"
                    ),
                )
            }
        )
        self.resolved[self.address.revision_id] = self.source
        first = self.repository.reconcile(
            self.address, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve
        )
        original_receipt = first.model_dump_json(by_alias=True)
        initial = self.repository.inspect(first.assertion_revision_id, resolve=self.resolve)
        assert initial.canonical_work is not None
        self.assertEqual(first.work_id, initial.canonical_work.work_id)
        self.assertEqual(first.work_revision_id, initial.canonical_work.revision_id)
        second_address = self.another_source()
        self.resolved[second_address.revision_id] = self.resolved[second_address.revision_id].model_copy(
            update={
                "fields": (
                    ScholarlyField(
                        name="title", observed="Second synthetic title", origin="observed", source_selector="title"
                    ),
                )
            }
        )
        second = self.repository.reconcile(
            second_address, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve
        )
        reopened = SqliteReconciliationRepository(self.database, self.project)
        for repository in (self.repository, reopened):
            inspection = repository.inspect(first.assertion_revision_id, resolve=self.resolve)
            assert inspection.canonical_work is not None
            self.assertEqual(original_receipt, inspection.result.model_dump_json(by_alias=True))
            self.assertEqual(first.work_id, inspection.canonical_work.work_id)
            self.assertEqual(second.work_revision_id, inspection.canonical_work.revision_id)
            self.assertNotEqual(first.work_revision_id, inspection.canonical_work.revision_id)
            title = next(field for field in inspection.canonical_fields if field.name == "title")
            self.assertEqual("disputed", title.status)
            self.assertEqual(
                {first.assertion_revision_id, second.assertion_revision_id},
                {observation.assertion_revision_id for observation in title.observations},
            )
        before = self.counts()
        self.resolved[second_address.revision_id] = self.resolved[second_address.revision_id].model_copy(
            update={"rights": ImportRights()}
        )
        with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-rights-denied"):
            reopened.inspect(first.assertion_revision_id, resolve=self.resolve)
        self.assertEqual(before, self.counts())

    def test_conflicting_actor_retry_and_current_rights_denial_leave_state_unchanged(self):
        command = new_uuid_v7()
        result = self.repository.reconcile(self.address, command_id=command, actor=self.actor, resolve=self.resolve)
        before = self.counts()
        with self.assertRaises(ReconciliationProblem):
            self.repository.reconcile(
                self.address,
                command_id=command,
                actor=replace(self.actor, actor_id=new_uuid_v7()),
                resolve=self.resolve,
            )
        self.resolved[self.address.revision_id] = self.source.model_copy(update={"rights": ImportRights()})
        with self.assertRaises(ReconciliationProblem):
            self.repository.reconcile(self.address, command_id=command, actor=self.actor, resolve=self.resolve)
        with self.assertRaises(ReconciliationProblem):
            self.repository.inspect(result.assertion_revision_id, resolve=self.resolve)
        self.assertEqual(before, self.counts())

    def test_every_publication_failpoint_rolls_back(self):
        for step in ("assertion-created", "work-created", "links-created", "command-created"):
            with self.subTest(step=step):
                before = self.counts()

                def fail(observed, expected=step):
                    if observed == expected:
                        raise ReconciliationProblem("synthetic-interruption")

                with (
                    patch("research_observatory_core.reconciliation_repository._publication_step", side_effect=fail),
                    self.assertRaises(ReconciliationProblem),
                ):
                    self.repository.reconcile(
                        self.address, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve
                    )
                self.assertEqual(before, self.counts())

    def test_forged_address_and_changed_source_payload_are_denied(self):
        with self.assertRaises(ReconciliationProblem):
            self.repository.reconcile(
                self.address.model_copy(update={"record_key": "9" * 64}),
                command_id=new_uuid_v7(),
                actor=self.actor,
                resolve=self.resolve,
            )
        result = self.repository.reconcile(
            self.address, command_id=new_uuid_v7(), actor=self.actor, resolve=self.resolve
        )
        self.resolved[self.address.revision_id] = self.source.model_copy(
            update={"identifiers": (IdentifierAssertion(scheme="doi", observed="10.99999/different"),)}
        )
        with self.assertRaises(ReconciliationProblem):
            self.repository.inspect(result.assertion_revision_id, resolve=self.resolve)
