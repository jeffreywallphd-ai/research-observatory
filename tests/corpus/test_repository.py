"""Real protected corpus publication, exact retry, and rollback boundaries."""

import hashlib
import json
import unittest
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher
from research_observatory_core import storage
from research_observatory_core.corpus.membership import (
    CorpusDecision,
    CorpusItemRevision,
    CorpusProblem,
    DiscoveryPath,
)
from research_observatory_core.corpus_repository import SqliteCorpusRepository, _connector_output_matches
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ingestion.preview_workflow import fingerprint
from research_observatory_core.models import IntentAcceptRequest
from research_observatory_core.ports.corpus import CorpusActor
from research_observatory_core.ports.reconciliation import ReconciliationActor
from research_observatory_core.ports.repositories import AggregateRevision
from research_observatory_core.privacy import _read_policy
from research_observatory_core.reconciliation.contracts import SourceAddress, SourceAssertion
from research_observatory_core.reconciliation.exact import IdentifierAssertion
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.repositories import _SqliteIntentRevisionRepository, _SqlitePrivacyPolicyRepository
from research_observatory_core.research_intents import validated_workflow_authority
from research_observatory_core.storage import open_canonical_database

from tests.connectors.test_connector_workflow import ConnectorWorkflowFixture
from tests.data import test_import_commit_publication as import_fixture
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider
from tests.service.test_research_intents import draft_request


class CorpusRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = import_fixture.ImportCommitPublicationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self._fixture = fixture
        output = fixture.publish()
        f = fixture.fixture
        self.database = f.database
        self.project = f.inputs.project_id
        member = next(
            item
            for item in f.repository.manifest_members(output.revision_id, after=0, limit=100)
            if item.decision.included
        )
        assert member.source_record_revision_id is not None
        self.address = SourceAddress(
            kind="import-member",
            context_id=f.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        with open_canonical_database(self.database, expected_project_id=self.project) as connection:
            raw_sha256 = connection.execute(
                "SELECT raw_sha256 FROM import_manifest_members WHERE project_id=? "
                "AND manifest_revision_id=? AND ordinal=?",
                (self.project, output.revision_id, member.ordinal),
            ).fetchone()[0]
        permission = ImportPermission(value="permitted", basis="researcher-confirmed")
        self.source = SourceAssertion(
            project_id=self.project,
            address=self.address,
            source_revision_id=member.source_record_revision_id,
            provider="local-import",
            identifiers=(IdentifierAssertion(scheme="doi", observed="10.99999/synthetic-a"),),
            fields=(),
            rights=ImportRights(store=permission, inspect=permission, derive=permission, index=permission),
            source_sha256=raw_sha256,
        )
        reconcile_actor = ReconciliationActor(new_uuid_v7(), "a" * 32, f.actor.occurred_at, "b" * 64, "c" * 64)
        result = SqliteReconciliationRepository(self.database, self.project).reconcile(
            self.address,
            command_id=new_uuid_v7(),
            actor=reconcile_actor,
            resolve=lambda _address: self.source,
        )
        assert result.work_id is not None and result.work_revision_id is not None
        self.work_id, self.work_revision_id = result.work_id, result.work_revision_id
        preview_fixture = f.fixture.fixture.fixture
        draft = preview_fixture.intents.workspace(preview_fixture.root).current
        assert draft is not None
        change = draft_request(preview_fixture.root, expected_revision=draft.revision)
        impact = preview_fixture.intents.preview(change.to_impact_request())
        if impact.acknowledgement_required:
            change = change.model_copy(update={"impact_acknowledgement": impact.acknowledgement_token})
        draft = preview_fixture.intents.save_draft(
            change,
            trace_id="d" * 32,
            idempotency_key="f" * 32,
        )
        preview_fixture.intents.accept(
            IntentAcceptRequest(
                root=preview_fixture.root,
                expected_revision=draft.revision,
                expected_revision_content_hash=draft.revision_content_hash,
                confirmed=True,
                decision_rationale="Synthetic fixture accepts the exact research intent.",
            ),
            trace_id="d" * 32,
            idempotency_key="e" * 32,
        )
        intent_repo = _SqliteIntentRevisionRepository(self.database, self.project)
        bridge = intent_repo.project_identity()
        assert bridge is not None
        _, revisions, _, _ = validated_workflow_authority(intent_repo, expected_project_id=bridge.domain_project_id)
        current = revisions[0]
        policy = _read_policy(_SqlitePrivacyPolicyRepository(self.database, self.project), self.project)
        self.actor = CorpusActor(
            actor_id=new_uuid_v7(),
            trace_id="d" * 32,
            occurred_at=f.actor.occurred_at,
            intent_revision_id=current["revisionId"],
            intent_sha256=current["revisionContentHash"].removeprefix("sha256:"),
            policy_sha256=fingerprint(policy.model_dump(mode="json", by_alias=True)).removeprefix("sha256:"),
        )
        self.repository = SqliteCorpusRepository(self.database, self.project)

    def _build_item(self) -> tuple[CorpusItemRevision, DiscoveryPath]:
        item_id = new_uuid_v7()
        path = DiscoveryPath(
            path_id=new_uuid_v7(),
            project_id=self.project,
            item_id=item_id,
            kind="import-member",
            source_revision_id=self.source.source_revision_id,
            direction="source-to-corpus-item",
            occurred_at=self.actor.occurred_at,
            predecessor_item_revision_id=None,
            context_id=self.address.context_id,
            context_revision_id=self.address.revision_id,
            ordinal=self.address.ordinal,
            record_key_sha256=self.address.record_key,
        )
        return (
            CorpusItemRevision(
                project_id=self.project,
                item_id=item_id,
                revision_id=new_uuid_v7(),
                previous_revision_id=None,
                work_id=self.work_id,
                work_revision_id=self.work_revision_id,
                membership="candidate",
                review="pending",
                duplicate_of_item_id=None,
                availability="unknown",
                discovery_path_ids=(path.path_id,),
                decision_revision_id=None,
            ),
            path,
        )

    def _create(self, command_id: str | None = None, build=None) -> CorpusItemRevision:
        return self.repository.create(
            command_id=command_id or new_uuid_v7(),
            command_sha256="1" * 64,
            actor=self.actor,
            source=self.source,
            build=build or self._build_item,
        )

    def _counts(self) -> tuple[int, ...]:
        with open_canonical_database(self.database, expected_project_id=self.project) as connection:
            return tuple(
                int(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])
                for table in (
                    "aggregate_revisions",
                    "corpus_item_states",
                    "corpus_discovery_paths",
                    "corpus_decisions",
                    "corpus_commands",
                    "provenance_events",
                    "outbox_events",
                    "material_dependency_outputs",
                )
            )

    def _citing_work(self):
        self._fixture.prepare_another(raw=b"title,doi\nCiting synthetic work,10.99999/synthetic-b\n")
        output = self._fixture.publish()
        f = self._fixture.fixture
        member = next(
            value
            for value in f.repository.manifest_members(output.revision_id, after=0, limit=100)
            if value.decision.included
        )
        assert member.source_record_revision_id is not None
        address = SourceAddress(
            kind="import-member",
            context_id=f.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        with open_canonical_database(self.database, expected_project_id=self.project) as connection:
            raw_sha256 = connection.execute(
                "SELECT raw_sha256 FROM import_manifest_members WHERE project_id=? "
                "AND manifest_revision_id=? AND ordinal=?",
                (self.project, output.revision_id, member.ordinal),
            ).fetchone()[0]
        citing_source = self.source.model_copy(
            update={
                "address": address,
                "source_revision_id": member.source_record_revision_id,
                "source_sha256": raw_sha256,
                "identifiers": (IdentifierAssertion(scheme="doi", observed="10.99999/synthetic-b"),),
            }
        )
        return SqliteReconciliationRepository(self.database, self.project).reconcile(
            address,
            command_id=new_uuid_v7(),
            actor=ReconciliationActor(new_uuid_v7(), "a" * 32, self.actor.occurred_at, "b" * 64, "c" * 64),
            resolve=lambda requested: citing_source if requested == address else self.source,
        )

    def test_create_and_decide_publish_replay_and_reopen_exact_history(self) -> None:
        command = new_uuid_v7()
        before = self._counts()
        item = self._create(command)
        after = self._counts()
        self.assertEqual(before[0] + 1, after[0])
        self.assertEqual(before[1] + 1, after[1])
        self.assertEqual(before[2] + 1, after[2])
        self.assertEqual(before[4] + 1, after[4])
        self.assertEqual(before[5] + 1, after[5])
        self.assertEqual(before[6] + 1, after[6])
        self.assertEqual(
            item, SqliteCorpusRepository(self.database, self.project).inspect(item.item_id, actor=self.actor)
        )

        def never_build():
            self.fail("exact retry must not mint IDs or invoke builder")

        self.assertEqual(
            item,
            self.repository.create(
                command_id=command,
                command_sha256="1" * 64,
                actor=self.actor,
                source=self.source,
                build=never_build,
            ),
        )
        self.assertEqual(after, self._counts())
        with self.assertRaisesRegex(CorpusProblem, "corpus-command-conflict"):
            self.repository.create(
                command_id=command,
                command_sha256="2" * 64,
                actor=self.actor,
                source=self.source,
                build=never_build,
            )
        self.assertEqual(after, self._counts())

        decision_command = new_uuid_v7()

        def include(current: CorpusItemRevision) -> CorpusDecision:
            return CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=self.project,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="membership",
                command="include",
                previous_value="candidate",
                next_value="included",
                previous_decision_revision_id=current.decision_revision_id,
                actor_id=self.actor.actor_id,
                reason_code="screened-in",
                protocol_revision_id=self.actor.intent_revision_id,
                evidence_revision_ids=(self.source.source_revision_id,),
                occurred_at=self.actor.occurred_at,
            )

        included = self.repository.decide(
            item.item_id,
            expected_revision_id=item.revision_id,
            command_id=decision_command,
            command_sha256="3" * 64,
            actor=self.actor,
            build=include,
        )
        self.assertEqual(("included", "pending"), included.conditions)
        self.assertEqual(item.revision_id, included.previous_revision_id)
        self.assertEqual(
            included, SqliteCorpusRepository(self.database, self.project).inspect(item.item_id, actor=self.actor)
        )
        with open_canonical_database(self.database, expected_project_id=self.project) as connection:
            row = connection.execute(
                "SELECT previous_value,next_value,actor_id,reason_code,protocol_revision_id FROM corpus_decisions "
                "WHERE decision_id=?",
                (included.decision_revision_id,),
            ).fetchone()
            self.assertEqual(
                ("candidate", "included", self.actor.actor_id, "screened-in", self.actor.intent_revision_id),
                tuple(row),
            )
        history = SqliteCorpusRepository(self.database, self.project).history(item.item_id, actor=self.actor)
        self.assertEqual(2, len(history))
        self.assertEqual((item, included), tuple(entry[0] for entry in history))
        self.assertEqual(
            (None, included.decision_revision_id),
            tuple(None if entry[2] is None else entry[2].decision_id for entry in history),
        )
        self.assertEqual(("import-member",), tuple(path.kind for path in history[0][1]))
        self.assertEqual("source-to-corpus-item", history[0][1][0].direction)
        self.assertEqual(self.actor.occurred_at, history[0][1][0].occurred_at)
        self.assertIsNone(history[0][1][0].predecessor_item_revision_id)
        self.assertEqual(
            ("screened-in",), tuple(decision.reason_code for _, _, decision in history if decision is not None)
        )

    def test_failure_after_state_write_rolls_back_all_common_and_corpus_facts(self) -> None:
        before = self._counts()

        def fail(step: str) -> None:
            if step == "state-created":
                raise RuntimeError("deterministic-stop")

        with (
            patch("research_observatory_core.corpus_repository._publication_step", fail),
            self.assertRaisesRegex(RuntimeError, "deterministic-stop"),
        ):
            self._create()
        self.assertEqual(before, self._counts())

    def test_portable_contract_rejection_rolls_back_item_path_and_decision(self) -> None:
        before = self._counts()
        for encoder in ("encode_corpus_item_revision", "encode_discovery_path"):
            with (
                self.subTest(encoder=encoder),
                patch("research_observatory_core.corpus_repository." + encoder, return_value=None),
                self.assertRaisesRegex(CorpusProblem, "corpus-contract-invalid"),
            ):
                self._create()
            self.assertEqual(before, self._counts())
        item = self._create()
        before_decision = self._counts()

        def include(current: CorpusItemRevision) -> CorpusDecision:
            return CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=self.project,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="membership",
                command="include",
                previous_value="candidate",
                next_value="included",
                previous_decision_revision_id=current.decision_revision_id,
                actor_id=self.actor.actor_id,
                reason_code="screened-in",
                protocol_revision_id=self.actor.intent_revision_id,
                evidence_revision_ids=(self.source.source_revision_id,),
                occurred_at=self.actor.occurred_at,
            )

        with (
            patch("research_observatory_core.corpus_repository.encode_corpus_decision", return_value=None),
            self.assertRaisesRegex(CorpusProblem, "corpus-contract-invalid"),
        ):
            self.repository.decide(
                item.item_id,
                expected_revision_id=item.revision_id,
                command_id=new_uuid_v7(),
                command_sha256="c" * 64,
                actor=self.actor,
                build=include,
            )
        self.assertEqual(before_decision, self._counts())
        self.assertEqual(item, self.repository.inspect(item.item_id, actor=self.actor))

    def test_sqlcipher_reopen_and_create_use_the_same_protected_writer(self) -> None:
        protected = self.database.parent.parent / "protected" / "state" / "project.sqlite3"
        protected.parent.mkdir(parents=True, exist_ok=True)
        keys = InMemoryDatabaseKeyProvider()
        with keys.active_key(self.project, create=True) as lease:
            material = lease.use(bytes)
        source = sqlcipher.connect(self.database.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(protected), f"x'{material.hex()}'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute(f"PRAGMA protected.user_version={storage.DATABASE_SCHEMA_VERSION}")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")
        finally:
            source.close()
        self.assertNotEqual(b"SQLite format 3\x00", protected.read_bytes()[:16])
        with storage._DATABASE_PROTECTION_LOCK:
            previous_profile = storage._DATABASE_PROTECTION
        try:
            storage.configure_protected_database_provider(keys)
            repository = SqliteCorpusRepository(protected, self.project)
            item = repository.create(
                command_id=new_uuid_v7(),
                command_sha256="d" * 64,
                actor=self.actor,
                source=self.source,
                build=self._build_item,
            )
            self.assertEqual(
                item, SqliteCorpusRepository(protected, self.project).inspect(item.item_id, actor=self.actor)
            )
            history = SqliteCorpusRepository(protected, self.project).history(item.item_id, actor=self.actor)
            self.assertEqual((item,), tuple(entry[0] for entry in history))
        finally:
            with storage._DATABASE_PROTECTION_LOCK:
                storage._DATABASE_PROTECTION = previous_profile

    def test_human_attested_citation_path_binds_citing_work_and_retained_assertion(self) -> None:
        item = self._create()
        citing = self._citing_work()
        assert citing.work_id is not None and citing.work_revision_id is not None
        self.assertNotEqual(item.work_id, citing.work_id)

        def build(current: CorpusItemRevision) -> tuple[DiscoveryPath, CorpusDecision]:
            path = DiscoveryPath(
                path_id=new_uuid_v7(),
                project_id=self.project,
                item_id=current.item_id,
                kind="citation",
                source_revision_id=citing.assertion_revision_id,
                direction="source-to-corpus-item",
                occurred_at=self.actor.occurred_at,
                predecessor_item_revision_id=current.revision_id,
                context_id=citing.work_id,
                context_revision_id=citing.work_revision_id,
                citing_work_revision_id=citing.work_revision_id,
            )
            decision = CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=self.project,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="discovery",
                command="add-discovery",
                previous_value=current.discovery_fingerprint,
                next_value=path.path_id,
                previous_decision_revision_id=current.decision_revision_id,
                actor_id=self.actor.actor_id,
                reason_code="researcher-attested-citation",
                protocol_revision_id=self.actor.intent_revision_id,
                evidence_revision_ids=(citing.assertion_revision_id,),
                occurred_at=self.actor.occurred_at,
            )
            return path, decision

        before = self._counts()
        with self.assertRaisesRegex(CorpusProblem, "corpus-citation-source-unavailable"):
            self.repository.add_citation_path(
                item.item_id,
                expected_revision_id=item.revision_id,
                command_id=new_uuid_v7(),
                command_sha256="a" * 64,
                actor=self.actor,
                citing_work_id=citing.work_id,
                citing_work_revision_id=citing.work_revision_id,
                source_assertion_revision_id=new_uuid_v7(),
                build=build,
            )
        self.assertEqual(before, self._counts())
        with open_canonical_database(self.database, expected_project_id=self.project) as connection:
            unrelated_assertion_id = connection.execute(
                "SELECT assertion_revision_id FROM reconciliation_work_members "
                "WHERE project_id=? AND work_revision_id=? LIMIT 1",
                (self.project, self.work_revision_id),
            ).fetchone()[0]
        with self.assertRaisesRegex(CorpusProblem, "corpus-citation-source-unavailable"):
            self.repository.add_citation_path(
                item.item_id,
                expected_revision_id=item.revision_id,
                command_id=new_uuid_v7(),
                command_sha256="a" * 64,
                actor=self.actor,
                citing_work_id=citing.work_id,
                citing_work_revision_id=citing.work_revision_id,
                source_assertion_revision_id=unrelated_assertion_id,
                build=build,
            )
        self.assertEqual(before, self._counts())
        command = new_uuid_v7()
        appended = self.repository.add_citation_path(
            item.item_id,
            expected_revision_id=item.revision_id,
            command_id=command,
            command_sha256="b" * 64,
            actor=self.actor,
            citing_work_id=citing.work_id,
            citing_work_revision_id=citing.work_revision_id,
            source_assertion_revision_id=citing.assertion_revision_id,
            build=build,
        )
        self.assertEqual(2, len(appended.discovery_path_ids))
        history = SqliteCorpusRepository(self.database, self.project).history(item.item_id, actor=self.actor)
        citation_path = next(path for path in history[-1][1] if path.kind == "citation")
        self.assertEqual("source-to-corpus-item", citation_path.direction)
        self.assertEqual(self.actor.occurred_at, citation_path.occurred_at)
        self.assertEqual(item.revision_id, citation_path.predecessor_item_revision_id)
        self.assertEqual("researcher-attested-citation", history[-1][2].reason_code)
        self.assertEqual(
            appended,
            self.repository.add_citation_path(
                item.item_id,
                expected_revision_id=item.revision_id,
                command_id=command,
                command_sha256="b" * 64,
                actor=self.actor,
                citing_work_id=citing.work_id,
                citing_work_revision_id=citing.work_revision_id,
                source_assertion_revision_id=citing.assertion_revision_id,
                build=lambda _current: self.fail("exact replay must not build a citation path"),
            ),
        )

    def test_initial_human_attested_citation_creates_candidate_with_exact_replay(self) -> None:
        citing = self._citing_work()
        assert citing.work_id is not None and citing.work_revision_id is not None
        self.assertNotEqual(self.work_id, citing.work_id)

        def build() -> tuple[CorpusItemRevision, DiscoveryPath]:
            item_id, path_id = new_uuid_v7(), new_uuid_v7()
            path = DiscoveryPath(
                path_id=path_id,
                project_id=self.project,
                item_id=item_id,
                kind="citation",
                source_revision_id=citing.assertion_revision_id,
                direction="source-to-corpus-item",
                occurred_at=self.actor.occurred_at,
                predecessor_item_revision_id=None,
                context_id=citing.work_id,
                context_revision_id=citing.work_revision_id,
                citing_work_revision_id=citing.work_revision_id,
            )
            item = CorpusItemRevision(
                project_id=self.project,
                item_id=item_id,
                revision_id=new_uuid_v7(),
                previous_revision_id=None,
                work_id=self.work_id,
                work_revision_id=self.work_revision_id,
                membership="candidate",
                review="pending",
                duplicate_of_item_id=None,
                availability="unknown",
                discovery_path_ids=(path_id,),
                decision_revision_id=None,
            )
            return item, path

        before = self._counts()
        with self.assertRaisesRegex(CorpusProblem, "corpus-citation-source-unavailable"):
            self.repository.create_citation(
                command_id=new_uuid_v7(),
                command_sha256="a" * 64,
                actor=self.actor,
                work_id=self.work_id,
                work_revision_id=self.work_revision_id,
                citing_work_id=citing.work_id,
                citing_work_revision_id=citing.work_revision_id,
                source_assertion_revision_id=new_uuid_v7(),
                build=lambda: self.fail("forged assertion must deny before identity minting"),
            )
        self.assertEqual(before, self._counts())
        with self.assertRaisesRegex(CorpusProblem, "corpus-work-unavailable"):
            self.repository.create_citation(
                command_id=new_uuid_v7(),
                command_sha256="a" * 64,
                actor=self.actor,
                work_id=self.work_id,
                work_revision_id=new_uuid_v7(),
                citing_work_id=citing.work_id,
                citing_work_revision_id=citing.work_revision_id,
                source_assertion_revision_id=citing.assertion_revision_id,
                build=lambda: self.fail("stale target must deny before identity minting"),
            )
        self.assertEqual(before, self._counts())
        command = new_uuid_v7()
        item = self.repository.create_citation(
            command_id=command,
            command_sha256="b" * 64,
            actor=self.actor,
            work_id=self.work_id,
            work_revision_id=self.work_revision_id,
            citing_work_id=citing.work_id,
            citing_work_revision_id=citing.work_revision_id,
            source_assertion_revision_id=citing.assertion_revision_id,
            build=build,
        )
        history = SqliteCorpusRepository(self.database, self.project).history(item.item_id, actor=self.actor)
        self.assertEqual(1, len(history))
        self.assertEqual(item, history[0][0])
        self.assertIsNone(history[0][2])
        self.assertEqual("citation", history[0][1][0].kind)
        self.assertIsNone(history[0][1][0].predecessor_item_revision_id)
        self.assertEqual(self.actor.occurred_at, history[0][1][0].occurred_at)
        self.assertEqual(
            item,
            self.repository.create_citation(
                command_id=command,
                command_sha256="b" * 64,
                actor=self.actor,
                work_id=self.work_id,
                work_revision_id=self.work_revision_id,
                citing_work_id=citing.work_id,
                citing_work_revision_id=citing.work_revision_id,
                source_assertion_revision_id=citing.assertion_revision_id,
                build=lambda: self.fail("exact replay must not build another item"),
            ),
        )
        with self.assertRaisesRegex(CorpusProblem, "corpus-command-conflict"):
            self.repository.create_citation(
                command_id=command,
                command_sha256="c" * 64,
                actor=self.actor,
                work_id=self.work_id,
                work_revision_id=self.work_revision_id,
                citing_work_id=citing.work_id,
                citing_work_revision_id=citing.work_revision_id,
                source_assertion_revision_id=citing.assertion_revision_id,
                build=lambda: self.fail("conflict must not build another item"),
            )

    def test_forged_import_source_or_stale_work_denies_without_publication(self) -> None:
        before = self._counts()
        forged = self.source.model_copy(update={"source_sha256": "e" * 64})
        with self.assertRaisesRegex(CorpusProblem, "corpus-source-unavailable"):
            self.repository.create(
                command_id=new_uuid_v7(),
                command_sha256="4" * 64,
                actor=self.actor,
                source=forged,
                build=self._build_item,
            )
        changed_assertion = self.source.model_copy(update={"identifiers": ()})
        with self.assertRaisesRegex(CorpusProblem, "corpus-source-work-mismatch"):
            self.repository.create(
                command_id=new_uuid_v7(),
                command_sha256="5" * 64,
                actor=self.actor,
                source=changed_assertion,
                build=self._build_item,
            )

        def stale_work():
            item, path = self._build_item()
            return item.model_copy(update={"work_revision_id": new_uuid_v7()}), path

        with self.assertRaises(CorpusProblem):
            self.repository.create(
                command_id=new_uuid_v7(),
                command_sha256="6" * 64,
                actor=self.actor,
                source=self.source,
                build=stale_work,
            )

        def forged_initial():
            item, path = self._build_item()
            return item.model_copy(update={"availability": "available"}), path

        with self.assertRaisesRegex(CorpusProblem, "corpus-item-invalid"):
            self.repository.create(
                command_id=new_uuid_v7(),
                command_sha256="6" * 64,
                actor=self.actor,
                source=self.source,
                build=forged_initial,
            )
        self.assertEqual(before, self._counts())

    def test_unrelated_existing_revision_cannot_be_decision_evidence(self) -> None:
        item = self._create()
        with open_canonical_database(self.database, expected_project_id=self.project) as connection:
            unrelated = connection.execute(
                "SELECT revision_id FROM aggregate_revisions WHERE project_id=? AND aggregate_kind='workflow' "
                "ORDER BY revision_id LIMIT 1",
                (self.project,),
            ).fetchone()[0]
        before = self._counts()

        def forged(current: CorpusItemRevision) -> CorpusDecision:
            return CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=self.project,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="membership",
                command="include",
                previous_value="candidate",
                next_value="included",
                previous_decision_revision_id=current.decision_revision_id,
                actor_id=self.actor.actor_id,
                reason_code="synthetic-review",
                protocol_revision_id=self.actor.intent_revision_id,
                evidence_revision_ids=(unrelated,),
                occurred_at=self.actor.occurred_at,
            )

        with self.assertRaisesRegex(CorpusProblem, "corpus-evidence-unrelated"):
            self.repository.decide(
                item.item_id,
                expected_revision_id=item.revision_id,
                command_id=new_uuid_v7(),
                command_sha256="7" * 64,
                actor=self.actor,
                build=forged,
            )
        self.assertEqual(before, self._counts())

    def test_rebind_then_append_second_import_discovery_preserves_both_paths(self) -> None:
        item = self._create()
        self._fixture.prepare_another(raw=b"title,doi\nSecond synthetic,10.99999/synthetic-a\n")
        output = self._fixture.publish()
        f = self._fixture.fixture
        member = next(
            value
            for value in f.repository.manifest_members(output.revision_id, after=0, limit=100)
            if value.decision.included
        )
        assert member.source_record_revision_id is not None
        address = SourceAddress(
            kind="import-member",
            context_id=f.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        with open_canonical_database(self.database, expected_project_id=self.project) as connection:
            raw_sha256 = connection.execute(
                "SELECT raw_sha256 FROM import_manifest_members WHERE project_id=? "
                "AND manifest_revision_id=? AND ordinal=?",
                (self.project, output.revision_id, member.ordinal),
            ).fetchone()[0]
        second = self.source.model_copy(
            update={
                "address": address,
                "source_revision_id": member.source_record_revision_id,
                "source_sha256": raw_sha256,
            }
        )
        reconciliation = SqliteReconciliationRepository(self.database, self.project)
        result = reconciliation.reconcile(
            address,
            command_id=new_uuid_v7(),
            actor=ReconciliationActor(new_uuid_v7(), "a" * 32, self.actor.occurred_at, "b" * 64, "c" * 64),
            resolve=lambda requested: second if requested == address else self.source,
        )
        self.assertEqual(self.work_id, result.work_id)
        assert result.work_revision_id is not None
        self.assertNotEqual(item.work_revision_id, result.work_revision_id)

        def rebind(current: CorpusItemRevision) -> CorpusDecision:
            return CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=self.project,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="work-reference",
                command="rebind-work",
                previous_value=current.work_revision_id,
                next_value=result.work_revision_id,
                previous_decision_revision_id=current.decision_revision_id,
                next_work_id=self.work_id,
                actor_id=self.actor.actor_id,
                reason_code="work-updated",
                protocol_revision_id=self.actor.intent_revision_id,
                evidence_revision_ids=(result.work_revision_id,),
                occurred_at=self.actor.occurred_at,
            )

        rebound = self.repository.rebind(
            item.item_id,
            expected_revision_id=item.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="9" * 64,
            actor=self.actor,
            build=rebind,
        )
        self.assertEqual(result.work_revision_id, rebound.work_revision_id)

        def append(current: CorpusItemRevision):
            path = DiscoveryPath(
                path_id=new_uuid_v7(),
                project_id=self.project,
                item_id=current.item_id,
                kind="import-member",
                source_revision_id=second.source_revision_id,
                direction="source-to-corpus-item",
                occurred_at=self.actor.occurred_at,
                predecessor_item_revision_id=current.revision_id,
                context_id=address.context_id,
                context_revision_id=address.revision_id,
                ordinal=address.ordinal,
                record_key_sha256=address.record_key,
            )
            decision = CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=self.project,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="discovery",
                command="add-discovery",
                previous_value=current.discovery_fingerprint,
                next_value=path.path_id,
                previous_decision_revision_id=current.decision_revision_id,
                actor_id=self.actor.actor_id,
                reason_code="new-import-path",
                protocol_revision_id=self.actor.intent_revision_id,
                evidence_revision_ids=(second.source_revision_id,),
                occurred_at=self.actor.occurred_at,
            )
            return path, decision

        command = new_uuid_v7()
        appended = self.repository.add_path(
            item.item_id,
            expected_revision_id=rebound.revision_id,
            command_id=command,
            command_sha256="a" * 64,
            actor=self.actor,
            source=second,
            build=append,
        )
        self.assertEqual(2, len(appended.discovery_path_ids))
        self.assertIn(item.discovery_path_ids[0], appended.discovery_path_ids)
        latest_history = SqliteCorpusRepository(self.database, self.project).history(item.item_id, actor=self.actor)
        appended_path = next(path for path in latest_history[-1][1] if path.path_id not in item.discovery_path_ids)
        self.assertEqual(rebound.revision_id, appended_path.predecessor_item_revision_id)
        self.assertEqual(
            appended,
            SqliteCorpusRepository(self.database, self.project).add_path(
                item.item_id,
                expected_revision_id=rebound.revision_id,
                command_id=command,
                command_sha256="a" * 64,
                actor=self.actor,
                source=second,
                build=lambda _current: self.fail("replay must not build another path"),
            ),
        )

    def test_connector_without_exact_accepted_query_binding_denies(self) -> None:
        original = self.source
        address = SourceAddress(
            kind="connector-record",
            context_id=new_uuid_v7(),
            revision_id=new_uuid_v7(),
            ordinal=0,
            record_key=None,
        )
        source = original.model_copy(
            update={
                "address": address,
                "source_revision_id": address.revision_id,
                "provider": "synthetic-provider",
            }
        )
        before = self._counts()

        def build():
            item, _ = self._build_item()
            path = DiscoveryPath(
                path_id=new_uuid_v7(),
                project_id=self.project,
                item_id=item.item_id,
                kind="connector-record",
                source_revision_id=address.revision_id,
                direction="source-to-corpus-item",
                occurred_at=self.actor.occurred_at,
                predecessor_item_revision_id=None,
                context_id=address.context_id,
                context_revision_id=address.revision_id,
                ordinal=0,
                query_revision_id=address.context_id,
            )
            return item.model_copy(update={"discovery_path_ids": (path.path_id,)}), path

        with self.assertRaisesRegex(CorpusProblem, "corpus-connector-source-unavailable"):
            self.repository.create(
                command_id=new_uuid_v7(),
                command_sha256="8" * 64,
                actor=self.actor,
                source=source,
                build=build,
            )
        self.assertEqual(before, self._counts())

    def test_changed_intent_or_policy_snapshot_denies_writer(self) -> None:
        before = self._counts()
        for actor in (
            self.actor.__class__(
                self.actor.actor_id,
                self.actor.trace_id,
                self.actor.occurred_at,
                self.actor.intent_revision_id,
                "f" * 64,
                self.actor.policy_sha256,
            ),
            self.actor.__class__(
                self.actor.actor_id,
                self.actor.trace_id,
                self.actor.occurred_at,
                self.actor.intent_revision_id,
                self.actor.intent_sha256,
                "f" * 64,
            ),
        ):
            with self.subTest(actor=actor.intent_sha256), self.assertRaises(CorpusProblem):
                self.repository.create(
                    command_id=new_uuid_v7(),
                    command_sha256="6" * 64,
                    actor=actor,
                    source=self.source,
                    build=self._build_item,
                )
        self.assertEqual(before, self._counts())


class CorpusConnectorWriterTests(ConnectorWorkflowFixture):
    """Accepted query/page provenance reaches the corpus writer on a protected database."""

    def setUp(self) -> None:
        super().setUp()
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        self.rights = self.rights.model_copy(
            update={"rights": ImportRights(store=grant, inspect=grant, derive=grant, index=grant)}
        )

    def test_accepted_query_page_and_reconciled_work_publish_exact_typed_path(self) -> None:
        preview, job = self.schedule()
        self.worker.run_pending()
        page = self.worker.reconciliation_sources(self.root, job.job_id, after=0, limit=1)
        self.assertEqual(1, len(page.addresses))
        address = page.addresses[0]
        source = self.worker.reconciliation_source(self.root, address)
        database = self.repository._database
        project = self.project.project_id
        reconciled = SqliteReconciliationRepository(database, project).reconcile(
            address,
            command_id=new_uuid_v7(),
            actor=ReconciliationActor(new_uuid_v7(), "a" * 32, self.clock.now(), "b" * 64, "c" * 64),
            resolve=lambda requested: (
                source if requested == address else self.worker.reconciliation_source(self.root, requested)
            ),
        )
        assert reconciled.work_id is not None and reconciled.work_revision_id is not None
        intent_repo = _SqliteIntentRevisionRepository(database, project)
        bridge = intent_repo.project_identity()
        assert bridge is not None
        _, revisions, _, _ = validated_workflow_authority(intent_repo, expected_project_id=bridge.domain_project_id)
        current_intent = revisions[0]
        policy = _read_policy(_SqlitePrivacyPolicyRepository(database, project), project)
        actor = CorpusActor(
            actor_id=new_uuid_v7(),
            trace_id="d" * 32,
            occurred_at=self.clock.now(),
            intent_revision_id=current_intent["revisionId"],
            intent_sha256=current_intent["revisionContentHash"].removeprefix("sha256:"),
            policy_sha256=fingerprint(policy.model_dump(mode="json", by_alias=True)).removeprefix("sha256:"),
        )
        item_id, path_id = new_uuid_v7(), new_uuid_v7()

        def build() -> tuple[CorpusItemRevision, DiscoveryPath]:
            path = DiscoveryPath(
                path_id=path_id,
                project_id=project,
                item_id=item_id,
                kind="connector-record",
                source_revision_id=source.source_revision_id,
                direction="source-to-corpus-item",
                occurred_at=actor.occurred_at,
                predecessor_item_revision_id=None,
                context_id=address.context_id,
                context_revision_id=address.revision_id,
                ordinal=address.ordinal,
                query_revision_id=preview.preview_id,
            )
            item = CorpusItemRevision(
                project_id=project,
                item_id=item_id,
                revision_id=new_uuid_v7(),
                previous_revision_id=None,
                work_id=reconciled.work_id,
                work_revision_id=reconciled.work_revision_id,
                membership="candidate",
                review="pending",
                duplicate_of_item_id=None,
                availability="unknown",
                discovery_path_ids=(path_id,),
                decision_revision_id=None,
            )
            return item, path

        repository = SqliteCorpusRepository(database, project)
        command = new_uuid_v7()
        item = repository.create(
            command_id=command,
            command_sha256="f" * 64,
            actor=actor,
            source=source,
            build=build,
        )
        self.assertEqual(1, len(self.calls))
        self.assertEqual(
            preview.preview_id,
            SqliteCorpusRepository(database, project).history(item.item_id, actor=actor)[0][1][0].query_revision_id,
        )
        self.assertEqual(
            item,
            repository.create(
                command_id=command,
                command_sha256="f" * 64,
                actor=actor,
                source=source,
                build=lambda: self.fail("replay must not mint another corpus identity"),
            ),
        )
        self.assertEqual(1, len(self.calls))


class CorpusConnectorManifestTests(unittest.TestCase):
    def test_page_uuid_in_unrelated_manifest_field_is_not_an_output_binding(self) -> None:
        page = AggregateRevision(
            revision_id=new_uuid_v7(),
            aggregate_id=new_uuid_v7(),
            aggregate_kind="document",
            project_id=new_uuid_v7(),
            revision=0,
            contract_version="1.0.0",
            created_at="2026-09-30T00:00:00.000Z",
            modified_at="2026-09-30T00:00:00.000Z",
            display_label_observed="Synthetic page",
            display_label_normalized=None,
            knowledge_status="observed",
            rights_status="unknown",
            object_sha256="a" * 64,
        )
        manifest = json.dumps(
            {
                "outputs": [{"revisionId": new_uuid_v7()}],
                "unrelatedRevisionId": page.revision_id,
            }
        )
        digest = "sha256:" + hashlib.sha256(manifest.encode("utf-8")).hexdigest()
        self.assertFalse(_connector_output_matches(manifest, digest, page))


if __name__ == "__main__":
    unittest.main()
