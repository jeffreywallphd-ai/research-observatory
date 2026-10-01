"""Protected report publication, exact retry, drill, and current-rights checks."""

from __future__ import annotations

import hashlib
import unittest
from contextlib import closing
from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch

from research_observatory_core.corpus.membership import CorpusDecision, CorpusItemRevision, DiscoveryPath
from research_observatory_core.corpus_report_model import CorpusReportFilter, CorpusReportProblem
from research_observatory_core.corpus_report_repository import SqliteCorpusReportRepository
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.reconciliation import ReconciliationActor
from research_observatory_core.reconciliation.contracts import ScholarlyField, SourceAddress
from research_observatory_core.reconciliation.exact import IdentifierAssertion
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.rights_policy import RightsPermission, RightsPolicyRevision, RightsUse
from research_observatory_core.storage import CanonicalConnection, open_canonical_database

from tests.rights import test_repository as rights_fixture


class CorpusReportRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        rights = rights_fixture.RightsRepositoryTests(methodName="runTest")
        rights.setUp()
        self.addCleanup(rights.doCleanups)
        self.rights = rights
        self.corpus = rights.corpus
        self.repository = SqliteCorpusReportRepository(self.corpus.database, self.corpus.project)
        self.item = self.corpus._create()

    def _policy(self, *, previous: str | None = None, value: str = "permitted", subject=None) -> RightsPolicyRevision:
        first = self.rights._policy(
            predecessor_revision_id=previous,
            value=value,
            subject=subject,
            use=RightsUse(action="derive", purpose="corpus-report", destination_kind="local-project"),
        )
        inspect = RightsPermission.model_validate(
            first.permissions[0].model_copy(
                update={
                    "assertion_id": new_uuid_v7(),
                    "use": RightsUse(action="inspect", purpose="corpus-report", destination_kind="local-project"),
                }
            )
        )
        return RightsPolicyRevision(
            revision_id=first.revision_id,
            predecessor_revision_id=previous,
            subject=first.subject,
            permissions=(first.permissions[0], inspect),
        )

    def _counts(self) -> tuple[int, ...]:
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as connection:
            return tuple(
                int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "corpus_report_snapshots",
                    "corpus_report_members",
                    "corpus_report_paths",
                    "corpus_report_sources",
                    "provenance_events",
                    "outbox_events",
                )
            )

    def _read_attempt_state(self) -> tuple[int, tuple[tuple[str, str, str, str, str], ...]]:
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            decisions = int(connection.execute("SELECT COUNT(*) FROM rights_use_decisions").fetchone()[0])
            events = tuple(
                tuple(str(value) for value in row)
                for row in connection.execute(
                    "SELECT event_type,occurred_at,trace_id,actor_id,record_sha256 "
                    "FROM provenance_events WHERE project_id=? AND event_type LIKE 'corpus.report-%-read-denied' "
                    "ORDER BY event_id",
                    (self.corpus.project,),
                )
            )
            return decisions, cast(tuple[tuple[str, str, str, str, str], ...], events)

    def test_missing_report_purpose_denies_without_partial_snapshot(self) -> None:
        before = self._counts()
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-rights-denied"):
            self.repository.create(command_id=new_uuid_v7(), command_sha256="a" * 64, actor=self.corpus.actor)
        self.assertEqual(before[:4], self._counts()[:4])

    def test_no_target_source_witness_is_unknown_not_not_reported(self) -> None:
        fields = SqliteCorpusReportRepository._fields(())
        self.assertEqual(("unknown",) * 7, tuple(field.state for field in fields))

    def test_citation_source_year_is_not_relabelled_as_target_work_year(self) -> None:
        fixture = self.corpus._fixture
        fixture.prepare_another(raw=b"title,doi,year\nCiting synthetic work,10.99999/synthetic-b,2025\n")
        output = fixture.publish()
        member = next(
            value
            for value in fixture.fixture.repository.manifest_members(output.revision_id, after=0, limit=100)
            if value.decision.included
        )
        assert member.source_record_revision_id is not None
        address = SourceAddress(
            kind="import-member",
            context_id=fixture.fixture.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as connection:
            raw_sha = connection.execute(
                "SELECT raw_sha256 FROM import_manifest_members WHERE project_id=? "
                "AND manifest_revision_id=? AND ordinal=?",
                (self.corpus.project, output.revision_id, member.ordinal),
            ).fetchone()[0]
        citing_source = self.corpus.source.model_copy(
            update={
                "address": address,
                "source_revision_id": member.source_record_revision_id,
                "source_sha256": raw_sha,
                "identifiers": (IdentifierAssertion(scheme="doi", observed="10.99999/synthetic-b"),),
                "fields": (ScholarlyField(name="year", observed="2025", origin="observed", source_selector="year"),),
            }
        )
        citing = SqliteReconciliationRepository(self.corpus.database, self.corpus.project).reconcile(
            address,
            command_id=new_uuid_v7(),
            actor=ReconciliationActor(new_uuid_v7(), "a" * 32, self.corpus.actor.occurred_at, "b" * 64, "c" * 64),
            resolve=lambda _address: citing_source,
        )
        assert citing.work_id is not None and citing.work_revision_id is not None
        citing_work_id, citing_work_revision_id = citing.work_id, citing.work_revision_id

        def add_citation(current: CorpusItemRevision) -> tuple[DiscoveryPath, CorpusDecision]:
            path = DiscoveryPath(
                path_id=new_uuid_v7(),
                project_id=self.corpus.project,
                item_id=current.item_id,
                kind="citation",
                source_revision_id=citing.assertion_revision_id,
                direction="source-to-corpus-item",
                occurred_at=self.corpus.actor.occurred_at,
                predecessor_item_revision_id=current.revision_id,
                context_id=citing_work_id,
                context_revision_id=citing_work_revision_id,
                citing_work_revision_id=citing_work_revision_id,
            )
            decision = CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=self.corpus.project,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="discovery",
                command="add-discovery",
                previous_value=current.discovery_fingerprint,
                next_value=path.path_id,
                previous_decision_revision_id=current.decision_revision_id,
                actor_id=self.corpus.actor.actor_id,
                reason_code="researcher-attested-citation",
                protocol_revision_id=self.corpus.actor.intent_revision_id,
                evidence_revision_ids=(citing.assertion_revision_id,),
                occurred_at=self.corpus.actor.occurred_at,
            )
            return path, decision

        self.corpus.repository.add_citation_path(
            self.item.item_id,
            expected_revision_id=self.item.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="d" * 64,
            actor=self.corpus.actor,
            citing_work_id=citing_work_id,
            citing_work_revision_id=citing_work_revision_id,
            source_assertion_revision_id=citing.assertion_revision_id,
            build=add_citation,
        )
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as connection:
            connection.execute("BEGIN")
            citing_subject = self.rights.repository.source_metadata_subject_with_connection(connection, citing_source)
        self.rights._publish(self._policy())
        self.rights._publish(self._policy(subject=citing_subject))
        report = self.repository.create(command_id=new_uuid_v7(), command_sha256="e" * 64, actor=self.corpus.actor)
        self.assertEqual(1, report.member_count)
        self.assertEqual(2, report.discovery_path_count)
        self.assertEqual(1, report.unattributed_discovery_path_count)
        self.assertEqual(1, report.source_contributions[0].discovery_path_count)
        self.assertEqual(1, report.route_overlaps[0].item_count)
        self.assertEqual(1, report.route_overlaps[0].discovery_path_pair_count)
        page = self.repository.page(
            report.snapshot_id, filter=CorpusReportFilter(kind="all"), after=None, limit=10, actor=self.corpus.actor
        )
        self.assertEqual("not-reported", page.members[0].fields[1].state)
        self.assertEqual(("citation", "import-member"), tuple(sorted(path.route for path in page.members[0].paths)))
        self.assertEqual({"retained"}, {path.metadata_assertion_status for path in page.members[0].paths})
        self.assertEqual({"allowed"}, {path.report_inspect_status for path in page.members[0].paths})
        self.assertEqual({"unknown"}, {path.source_copy_availability for path in page.members[0].paths})

    def test_create_retry_reopen_summary_and_exact_drill(self) -> None:
        self.rights._publish(self._policy())
        command_id = new_uuid_v7()
        summary = self.repository.create(command_id=command_id, command_sha256="a" * 64, actor=self.corpus.actor)
        self.assertEqual(1, summary.member_count)
        self.assertEqual(1, summary.source_contributions[0].item_count)
        self.assertEqual(f"import:{self.corpus.address.revision_id}", summary.source_contributions[0].source_key)
        self.assertEqual(1, summary.coverage[0].known)
        self.assertEqual(1, summary.coverage[1].not_reported)
        initial = self._counts()
        self.assertEqual(
            summary,
            self.repository.create(
                command_id=command_id,
                command_sha256="a" * 64,
                actor=self.corpus.actor,
            ),
        )
        self.assertEqual(initial, self._counts())
        reopened = SqliteCorpusReportRepository(self.corpus.database, self.corpus.project)
        self.assertEqual(summary, reopened.summary(summary.snapshot_id, actor=self.corpus.actor))
        selected = CorpusReportFilter(kind="source", source_key=summary.source_contributions[0].source_key)
        page = reopened.page(summary.snapshot_id, filter=selected, after=None, limit=1, actor=self.corpus.actor)
        self.assertEqual(1, page.total)
        self.assertEqual((self.item.item_id,), tuple(member.item_id for member in page.members))
        self.assertIsNone(page.next_cursor)
        self.assertEqual(self.item.revision_id, page.members[0].item_revision_id)
        self.assertIsNone(page.members[0].display_label)
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-command-conflict"):
            reopened.create(command_id=command_id, command_sha256="b" * 64, actor=self.corpus.actor)

    def test_revoked_report_purpose_blocks_historical_inspection(self) -> None:
        current = self.rights._publish(self._policy())
        summary = self.repository.create(
            command_id=new_uuid_v7(),
            command_sha256="a" * 64,
            actor=self.corpus.actor,
        )
        self.rights._publish(self._policy(previous=current.revision_id, value="denied"))
        reopened = SqliteCorpusReportRepository(self.corpus.database, self.corpus.project)
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-rights-denied"):
            reopened.summary(summary.snapshot_id, actor=self.corpus.actor)
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-rights-denied"):
            reopened.page(
                summary.snapshot_id, filter=CorpusReportFilter(kind="all"), after=None, limit=1, actor=self.corpus.actor
            )

    def test_expired_retained_report_rights_deny_and_durably_audit_without_a_use_decision(self) -> None:
        self.rights._publish(self._policy())
        summary = self.repository.create(command_id=new_uuid_v7(), command_sha256="a" * 64, actor=self.corpus.actor)
        before_counts = self._counts()
        before_decisions, before_events = self._read_attempt_state()
        expired_at = datetime(2030, 10, 1, tzinfo=UTC)
        with (
            patch("research_observatory_core.corpus_report_repository._now_utc", return_value=expired_at),
            self.assertRaisesRegex(CorpusReportProblem, "corpus-report-rights-denied"),
        ):
            self.repository.summary(summary.snapshot_id, actor=self.corpus.actor)
        after_counts = self._counts()
        after_decisions, after_events = self._read_attempt_state()
        self.assertEqual(before_counts[:4], after_counts[:4])
        self.assertEqual(before_counts[4] + 1, after_counts[4])
        self.assertEqual(before_counts[5], after_counts[5])
        self.assertEqual(before_decisions, after_decisions)
        self.assertEqual(
            (
                *before_events,
                (
                    "corpus.report-expired-read-denied",
                    "2030-10-01T00:00:00.000Z",
                    self.corpus.actor.trace_id,
                    self.corpus.actor.actor_id,
                    hashlib.sha256(summary.snapshot_id.encode("utf-8")).hexdigest(),
                ),
            ),
            after_events,
        )

    def test_allowing_policy_change_denies_stale_report_without_persisting_false_allow(self) -> None:
        retained = self.rights._publish(self._policy())
        summary = self.repository.create(command_id=new_uuid_v7(), command_sha256="a" * 64, actor=self.corpus.actor)
        self.rights._publish(self._policy(previous=retained.revision_id))
        before_counts = self._counts()
        before_decisions, before_events = self._read_attempt_state()
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-rights-denied"):
            self.repository.page(
                summary.snapshot_id,
                filter=CorpusReportFilter(kind="all"),
                after=None,
                limit=1,
                actor=self.corpus.actor,
            )
        after_counts = self._counts()
        after_decisions, after_events = self._read_attempt_state()
        self.assertEqual(before_counts[:4], after_counts[:4])
        self.assertEqual(before_counts[4] + 1, after_counts[4])
        self.assertEqual(before_counts[5], after_counts[5])
        self.assertEqual(before_decisions, after_decisions)
        self.assertEqual(len(before_events) + 1, len(after_events))
        self.assertEqual(
            (
                "corpus.report-stale-witness-read-denied",
                self.corpus.actor.trace_id,
                self.corpus.actor.actor_id,
                hashlib.sha256(summary.snapshot_id.encode("utf-8")).hexdigest(),
            ),
            (after_events[-1][0], after_events[-1][2], after_events[-1][3], after_events[-1][4]),
        )

    def test_cursor_is_bound_to_snapshot_and_filter_and_foreign_project_denies(self) -> None:
        self.corpus._create()
        self.rights._publish(self._policy())
        summary = self.repository.create(
            command_id=new_uuid_v7(),
            command_sha256="a" * 64,
            actor=self.corpus.actor,
        )
        all_members = CorpusReportFilter(kind="all")
        first = self.repository.page(
            summary.snapshot_id, filter=all_members, after=None, limit=1, actor=self.corpus.actor
        )
        self.assertEqual(2, first.total)
        self.assertIsNotNone(first.next_cursor)
        second = self.repository.page(
            summary.snapshot_id, filter=all_members, after=first.next_cursor, limit=1, actor=self.corpus.actor
        )
        self.assertEqual(1, len(second.members))
        self.assertNotEqual(first.members[0].item_id, second.members[0].item_id)
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-cursor-invalid"):
            self.repository.page(
                summary.snapshot_id,
                filter=CorpusReportFilter(kind="membership", membership="candidate"),
                after=first.next_cursor,
                limit=1,
                actor=self.corpus.actor,
            )
        assert first.next_cursor is not None
        with self.assertRaisesRegex(CorpusReportProblem, "corpus-report-cursor-invalid"):
            self.repository.page(
                summary.snapshot_id,
                filter=all_members,
                after=first.next_cursor[:-2] + "xx",
                limit=1,
                actor=self.corpus.actor,
            )
        foreign = SqliteCorpusReportRepository(self.corpus.database, new_uuid_v7())
        with self.assertRaises(CorpusReportProblem):
            foreign.summary(summary.snapshot_id, actor=self.corpus.actor)

    def test_later_membership_revision_does_not_relabel_sealed_snapshot(self) -> None:
        self.rights._publish(self._policy())
        summary = self.repository.create(
            command_id=new_uuid_v7(),
            command_sha256="a" * 64,
            actor=self.corpus.actor,
        )

        def include(current: CorpusItemRevision) -> CorpusDecision:
            return CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=self.corpus.project,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="membership",
                command="include",
                previous_value="candidate",
                next_value="included",
                previous_decision_revision_id=current.decision_revision_id,
                actor_id=self.corpus.actor.actor_id,
                reason_code="screened-in",
                protocol_revision_id=self.corpus.actor.intent_revision_id,
                evidence_revision_ids=(self.corpus.source.source_revision_id,),
                occurred_at=self.corpus.actor.occurred_at,
            )

        changed = self.corpus.repository.decide(
            self.item.item_id,
            expected_revision_id=self.item.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="b" * 64,
            actor=self.corpus.actor,
            build=include,
        )
        self.assertEqual("included", changed.membership)
        old = self.repository.page(
            summary.snapshot_id, filter=CorpusReportFilter(kind="all"), after=None, limit=10, actor=self.corpus.actor
        )
        self.assertEqual(self.item.revision_id, old.members[0].item_revision_id)
        self.assertEqual("candidate", old.members[0].membership)
        current = self.repository.create(command_id=new_uuid_v7(), command_sha256="c" * 64, actor=self.corpus.actor)
        self.assertEqual(1, current.membership_counts[1].item_count)

    def test_protected_inspection_detects_missing_member_stream_even_when_summary_row_is_intact(self) -> None:
        self.rights._publish(self._policy())
        summary = self.repository.create(
            command_id=new_uuid_v7(),
            command_sha256="a" * 64,
            actor=self.corpus.actor,
        )

        class MissingMemberRead:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, statement, parameters=()):
                if statement.startswith("SELECT ordinal,item_id,member_json,member_sha256"):
                    return iter(())
                return self.connection.execute(statement, parameters)

        # The protected connection's schema authorizer prevents actual row
        # deletion. Simulate a missing read row to exercise stream verification.
        with (
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as connection,
            self.assertRaisesRegex(CorpusReportProblem, "corpus-report-integrity-invalid"),
        ):
            self.repository._load_snapshot(
                cast(CanonicalConnection, MissingMemberRead(connection)), summary.snapshot_id
            )
        self.assertEqual(summary, self.repository.summary(summary.snapshot_id, actor=self.corpus.actor))

    def test_interruption_after_seal_rolls_back_report_provenance_and_outbox(self) -> None:
        self.rights._publish(self._policy())
        before = self._counts()
        command_id = new_uuid_v7()

        def interrupt(step: str) -> None:
            if step == "after-seal":
                raise RuntimeError("synthetic-report-publication-interruption")

        with (
            patch("research_observatory_core.corpus_report_repository._step", side_effect=interrupt),
            self.assertRaisesRegex(RuntimeError, "synthetic-report-publication-interruption"),
        ):
            self.repository.create(command_id=command_id, command_sha256="f" * 64, actor=self.corpus.actor)
        self.assertEqual(before, self._counts())
        reopened = SqliteCorpusReportRepository(self.corpus.database, self.corpus.project)
        completed = reopened.create(command_id=command_id, command_sha256="f" * 64, actor=self.corpus.actor)
        self.assertEqual(1, completed.member_count)


if __name__ == "__main__":
    unittest.main()
