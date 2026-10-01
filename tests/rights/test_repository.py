"""Exact, protected rights publication and re-evaluation boundaries."""

from __future__ import annotations

import copy
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

from research_observatory_core.corpus.membership import CorpusItemRevision, DiscoveryPath
from research_observatory_core.corpus_repository import SqliteCorpusRepository
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.preview_workflow import fingerprint
from research_observatory_core.ports.corpus import CorpusActor
from research_observatory_core.ports.reconciliation import ReconciliationActor
from research_observatory_core.ports.repositories import (
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyImpactLimitExceeded,
    MaterialDependency,
)
from research_observatory_core.ports.rights import RightsPermissionDraft
from research_observatory_core.privacy import _read_policy
from research_observatory_core.reconciliation.contracts import SourceAddress, SourceAssertion
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.repositories import (
    _projection_content_sha256,
    _SqliteDependencyImpactRepository,
    _SqliteIntentRevisionRepository,
    _SqlitePrivacyPolicyRepository,
)
from research_observatory_core.research_intents import validated_workflow_authority
from research_observatory_core.rights_policy import (
    RightsPermission,
    RightsPolicyRevision,
    RightsRequest,
    RightsSubject,
    RightsUse,
)
from research_observatory_core.rights_repository import RightsProblem, SqliteRightsRepository
from research_observatory_core.storage import open_canonical_database

from tests.connectors import test_connector_workflow as connector_workflow_tests
from tests.connectors import test_scholarly_mapping as scholarly_fixtures
from tests.corpus import test_repository as corpus_tests


class RightsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        corpus = corpus_tests.CorpusRepositoryTests(methodName="runTest")
        corpus.setUp()
        self.addCleanup(corpus.doCleanups)
        self.corpus = corpus
        self.repository = SqliteRightsRepository(corpus.database, corpus.project)
        with closing(open_canonical_database(corpus.database, expected_project_id=corpus.project)) as connection:
            connection.execute("BEGIN")
            self.subject = self.repository.source_metadata_subject_with_connection(connection, corpus.source)
        self.use = RightsUse(action="inspect", purpose="scholarly-screening", destination_kind="local-project")

    def _policy(
        self,
        *,
        revision_id: str | None = None,
        predecessor_revision_id: str | None = None,
        value: str = "permitted",
        basis: str = "researcher-confirmed",
        subject: RightsSubject | None = None,
        use: RightsUse | None = None,
        asserted_by_actor_id: str | None = None,
        expires_at: str | None = "2030-10-01T00:00:00.000Z",
    ) -> RightsPolicyRevision:
        selected_subject = subject or self.subject
        permission = RightsPermission.model_validate(
            {
                "assertion_id": new_uuid_v7(),
                "subject": selected_subject,
                "use": use or self.use,
                "value": value,
                "basis": basis,
                "confidence": "verified"
                if basis == "verified-entitlement"
                else ("reported" if basis == "source-observation" else "confirmed"),
                "asserted_by_actor_id": (
                    None if basis == "source-observation" else asserted_by_actor_id or self.corpus.actor.actor_id
                ),
                "evidence_revision_ids": (selected_subject.source_assertion_revision_id,),
                "license_observation_revision_id": None,
                "entitlement_revision_id": selected_subject.source_assertion_revision_id
                if basis == "verified-entitlement"
                else None,
                "recorded_at": "2026-09-01T00:00:00.000Z",
                "expires_at": expires_at,
            }
        )
        return RightsPolicyRevision(
            revision_id=revision_id or new_uuid_v7(),
            predecessor_revision_id=predecessor_revision_id,
            subject=selected_subject,
            permissions=(permission,),
        )

    def _publish(self, policy: RightsPolicyRevision, *, command_id: str | None = None) -> RightsPolicyRevision:
        return self.repository.publish(
            policy,
            command_id=command_id or new_uuid_v7(),
            command_sha256="4" * 64,
            actor=self.corpus.actor,
        )

    def _counts(self) -> tuple[int, ...]:
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            return tuple(
                int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "rights_policy_subjects",
                    "rights_policy_revisions",
                    "rights_policy_rechecks",
                    "aggregate_revisions",
                    "provenance_events",
                    "outbox_events",
                    "rights_policy_recheck_scopes",
                )
            )

    def test_publish_retry_restart_and_revocation_use_current_policy(self) -> None:
        self.assertIsNone(self.repository.recheck_scope(self.subject, actor=self.corpus.actor))
        proposed = self._policy()
        command_id = new_uuid_v7()
        initial = self._publish(proposed, command_id=command_id)
        self.assertIsNotNone(initial.source_observation)
        assert initial.source_observation is not None
        self.assertEqual("not-reported", initial.source_observation.terms.license.state)
        first = self._counts()
        self.assertEqual(initial, self._publish(proposed, command_id=command_id))
        self.assertEqual(first, self._counts())
        reopened = SqliteRightsRepository(self.corpus.database, self.corpus.project)
        self.assertEqual(initial, reopened.current(self.subject, actor=self.corpus.actor))
        complete_scope = reopened.recheck_scope(self.subject, actor=self.corpus.actor)
        assert complete_scope is not None
        self.assertEqual(initial.revision_id, complete_scope.rights_revision_id)
        self.assertEqual("complete", complete_scope.disposition)
        self.assertEqual("complete", complete_scope.exact_state)
        self.assertEqual("complete", complete_scope.generic_state)
        self.assertIsNone(complete_scope.pending_reason)
        request = RightsRequest(actor_id=self.corpus.actor.actor_id, subject=self.subject, use=self.use)
        with patch(
            "research_observatory_core.rights_repository._utcnow",
            return_value=datetime(2026, 9, 30, tzinfo=UTC),
        ):
            self.assertEqual("allow", reopened.evaluate(request, actor=self.corpus.actor).code)
        revoked = self._policy(predecessor_revision_id=initial.revision_id, value="denied")
        revoked = self._publish(revoked)
        with patch(
            "research_observatory_core.rights_repository._utcnow",
            return_value=datetime(2026, 9, 30, tzinfo=UTC),
        ):
            result = reopened.evaluate(request, actor=self.corpus.actor)
        self.assertEqual("deny", result.code)
        self.assertEqual(revoked.revision_id, result.policy_revision_id)
        self.assertEqual(revoked, reopened.current(self.subject, actor=self.corpus.actor))

    def test_use_decisions_and_post_rollback_denial_are_durable_redacted_audit(self) -> None:
        request = RightsRequest(actor_id=self.corpus.actor.actor_id, subject=self.subject, use=self.use)
        unknown = self.repository.evaluate(request, actor=self.corpus.actor)
        self.assertEqual("unknown", unknown.code)
        self.assertIsNone(unknown.policy_revision_id)
        allowed_policy = self._publish(self._policy())
        allowed = self.repository.evaluate(request, actor=self.corpus.actor)
        self.assertEqual("allow", allowed.code)
        denied_policy = self._publish(self._policy(predecessor_revision_id=allowed_policy.revision_id, value="denied"))
        copied_denial = None
        with (
            self.assertRaisesRegex(RightsProblem, "rights-injected-rollback"),
            self.repository._transaction(write=True) as (connection, _),
        ):
            copied_denial = self.repository.evaluate_with_connection(connection, request, actor=self.corpus.actor)
            raise RightsProblem("rights-injected-rollback")
        assert copied_denial is not None
        self.assertEqual("deny", copied_denial.code)
        self.repository.append_denied_attempt(copied_denial, actor=self.corpus.actor)
        reopened = SqliteRightsRepository(self.corpus.database, self.corpus.project)
        self.assertEqual(denied_policy, reopened.current(self.subject, actor=self.corpus.actor))
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            rows = list(
                map(
                    tuple,
                    connection.execute(
                        "SELECT event_kind,decision_code,reason_code,policy_revision_id,policy_sha256,"
                        "actor_id,trace_id,source_assertion_revision_id,use_action,use_sha256 "
                        "FROM rights_use_decisions WHERE project_id=? ORDER BY rowid",
                        (self.corpus.project,),
                    ).fetchall(),
                )
            )
        self.assertEqual(3, len(rows))
        self.assertEqual(("evaluate", "unknown", "rights-policy-missing", None, None), rows[0][:5])
        self.assertEqual(("evaluate", "allow", "rights-explicit-permission", allowed_policy.revision_id), rows[1][:4])
        self.assertEqual(("denied-attempt", "deny", "rights-explicit-denial", denied_policy.revision_id), rows[2][:4])
        self.assertEqual((self.corpus.actor.actor_id, self.corpus.actor.trace_id), rows[2][5:7])
        self.assertEqual(self.subject.source_assertion_revision_id, rows[2][7])
        self.assertEqual(self.use.action, rows[2][8])
        self.assertRegex(rows[2][9], r"^[0-9a-f]{64}$")
        with self.assertRaisesRegex(RightsProblem, "rights-decision-invalid"):
            reopened.append_denied_attempt(allowed, actor=self.corpus.actor)

    def test_remote_use_requires_further_authority_in_returned_and_audited_decision(self) -> None:
        remote_use = RightsUse(
            action="model-use",
            purpose="scholarly-screening",
            destination_kind="remote-model",
            provider="synthetic",
            region="us-east",
        )
        policy = self._publish(self._policy(use=remote_use))
        decision = self.repository.evaluate(
            RightsRequest(actor_id=self.corpus.actor.actor_id, subject=self.subject, use=remote_use),
            actor=self.corpus.actor,
        )
        self.assertEqual("require-confirmation", decision.code)
        self.assertEqual("rights-further-authority-required", decision.reason_code)
        self.assertEqual(policy.revision_id, decision.policy_revision_id)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            row = connection.execute(
                "SELECT decision_code,reason_code,policy_revision_id,use_action,event_kind "
                "FROM rights_use_decisions WHERE project_id=?",
                (self.corpus.project,),
            ).fetchone()
        self.assertEqual(
            ("require-confirmation", "rights-further-authority-required", policy.revision_id, "model-use", "evaluate"),
            tuple(row),
        )

    def test_confirmed_import_bridge_is_exact_public_decision_and_policy_supersedes_it(self) -> None:
        use = RightsUse(action="store", purpose="corpus-membership", destination_kind="local-project")
        request = RightsRequest(actor_id=self.corpus.actor.actor_id, subject=self.subject, use=use)
        bridged = self.repository.evaluate(request, actor=self.corpus.actor)
        self.assertEqual("allow", bridged.code)
        self.assertEqual("legacy-import-bridge", bridged.authority_kind)
        self.assertEqual("rights-legacy-import-confirmed", bridged.reason_code)
        self.assertIsNone(bridged.policy_revision_id)
        self.assertEqual((self.subject.source_assertion_revision_id,), bridged.governing_assertion_ids)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            witness = connection.execute(
                "SELECT payload_sha256 FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
                (self.corpus.project, self.subject.source_assertion_revision_id),
            ).fetchone()[0]
            row = connection.execute(
                "SELECT authority_kind,source_assertion_sha256,event_kind,decision_code,policy_revision_id "
                "FROM rights_use_decisions WHERE project_id=?",
                (self.corpus.project,),
            ).fetchone()
        self.assertEqual(witness, bridged.source_assertion_sha256)
        self.assertEqual(("legacy-import-bridge", witness, "legacy-import-bridge", "allow", None), tuple(row))

        policy = self._publish(self._policy())
        superseded = self.repository.evaluate(request, actor=self.corpus.actor)
        self.assertEqual("unknown", superseded.code)
        self.assertEqual("policy", superseded.authority_kind)
        self.assertEqual(policy.revision_id, superseded.policy_revision_id)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            latest = connection.execute(
                "SELECT authority_kind,event_kind,decision_code,policy_revision_id FROM rights_use_decisions "
                "WHERE project_id=? ORDER BY rowid DESC LIMIT 1",
                (self.corpus.project,),
            ).fetchone()
        self.assertEqual(("policy", "evaluate", "unknown", policy.revision_id), tuple(latest))

    def test_import_bridge_does_not_grant_other_copy_location_or_resource(self) -> None:
        use = RightsUse(action="store", purpose="corpus-membership", destination_kind="local-project")
        for change in (
            {"copy_id": new_uuid_v7()},
            {"copy_location": "provider-hosted"},
            {"resource_class": "full-text"},
        ):
            with self.subTest(change=change):
                subject = RightsSubject.model_validate(self.subject.model_copy(update=change))
                decision = self.repository.evaluate(
                    RightsRequest(actor_id=self.corpus.actor.actor_id, subject=subject, use=use),
                    actor=self.corpus.actor,
                )
                self.assertEqual("unknown", decision.code)
                self.assertEqual("none", decision.authority_kind)
                self.assertIsNone(decision.policy_revision_id)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            rows = connection.execute(
                "SELECT event_kind,authority_kind,decision_code FROM rights_use_decisions WHERE project_id=?",
                (self.corpus.project,),
            ).fetchall()
        self.assertEqual([("evaluate", "none", "unknown")] * 3, list(map(tuple, rows)))

    def test_exact_cap_commits_denial_and_pending_scope_survives_restart_and_later_allow(self) -> None:
        first = self.corpus._create()
        second = self.corpus._create()
        self.assertNotEqual(first.revision_id, second.revision_id)
        initial = self._policy()
        self._publish(initial)
        request = RightsRequest(actor_id=self.corpus.actor.actor_id, subject=self.subject, use=self.use)
        self.assertEqual("allow", self.repository.evaluate(request, actor=self.corpus.actor).code)

        revoked = self._policy(predecessor_revision_id=initial.revision_id, value="denied")
        with patch("research_observatory_core.rights_repository._MAX_EXACT_RECHECKS", 1):
            revoked = self._publish(revoked)
        reopened = SqliteRightsRepository(self.corpus.database, self.corpus.project)
        self.assertEqual(revoked, reopened.current(self.subject, actor=self.corpus.actor))
        self.assertEqual("deny", reopened.evaluate(request, actor=self.corpus.actor).code)
        scope = reopened.recheck_scope(self.subject, actor=self.corpus.actor)
        assert scope is not None
        self.assertEqual(revoked.revision_id, scope.rights_revision_id)
        self.assertEqual("pending", scope.disposition)
        self.assertEqual("pending", scope.exact_state)
        self.assertEqual("complete", scope.generic_state)
        self.assertEqual("exact-limit", scope.pending_reason)
        before_materialization = reopened.output_rechecks(first.revision_id, actor=self.corpus.actor)
        self.assertNotIn(revoked.revision_id, {marker.rights_revision_id for marker in before_materialization.markers})
        self.assertTrue(before_materialization.propagation_pending)
        self.assertFalse(before_materialization.propagation_unknown)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM rights_policy_rechecks WHERE project_id=? AND rights_revision_id=?",
                    (self.corpus.project, revoked.revision_id),
                ).fetchone()[0],
            )

        later_allow = self._policy(predecessor_revision_id=revoked.revision_id)
        later_allow = self._publish(later_allow)
        self.assertEqual(later_allow, reopened.current(self.subject, actor=self.corpus.actor))
        decision = reopened.evaluate(request, actor=self.corpus.actor)
        self.assertEqual("unknown", decision.code)
        self.assertEqual("rights-impact-pending", decision.reason_code)
        self.assertEqual(later_allow.revision_id, decision.policy_revision_id)
        persistent_scope = reopened.recheck_scope(self.subject, actor=self.corpus.actor)
        assert persistent_scope is not None
        self.assertEqual(revoked.revision_id, persistent_scope.rights_revision_id)
        self.assertEqual("pending", persistent_scope.disposition)

        halfway = reopened.advance_rechecks(self.subject, actor=self.corpus.actor, batch_size=1)
        assert halfway is not None
        self.assertEqual("pending", halfway.disposition)
        self.assertEqual(revoked.revision_id, halfway.rights_revision_id)
        finished = reopened.advance_rechecks(self.subject, actor=self.corpus.actor, batch_size=1)
        assert finished is not None
        self.assertEqual("complete", finished.disposition)
        self.assertEqual(later_allow.revision_id, finished.rights_revision_id)
        self.assertEqual("allow", reopened.evaluate(request, actor=self.corpus.actor).code)
        reviewed_output = reopened.output_rechecks(first.revision_id, actor=self.corpus.actor)
        self.assertFalse(reviewed_output.propagation_pending)
        self.assertEqual({"exact"}, {marker.kind for marker in reviewed_output.markers})
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            self.assertEqual(
                2,
                connection.execute(
                    "SELECT COUNT(*) FROM rights_policy_rechecks WHERE project_id=? AND rights_revision_id=?",
                    (self.corpus.project, revoked.revision_id),
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                connection.execute(
                    "SELECT COUNT(*) FROM rights_policy_recheck_completions "
                    "WHERE project_id=? AND rights_revision_id=? AND dimension='exact'",
                    (self.corpus.project, revoked.revision_id),
                ).fetchone()[0],
            )

    def test_generic_planner_cap_commits_denial_with_observable_pending_scope(self) -> None:
        initial = self._policy()
        self._publish(initial)
        revoked = self._policy(predecessor_revision_id=initial.revision_id, value="denied")

        def exceed_planner_cap(*_args: object, **_kwargs: object) -> None:
            raise DependencyImpactLimitExceeded("synthetic low planner cap")

        with patch(
            "research_observatory_core.rights_repository._SqliteDependencyImpactRepository._preview_with_connection",
            side_effect=exceed_planner_cap,
        ):
            revoked = self._publish(revoked)
        reopened = SqliteRightsRepository(self.corpus.database, self.corpus.project)
        self.assertEqual(revoked, reopened.current(self.subject, actor=self.corpus.actor))
        scope = reopened.recheck_scope(self.subject, actor=self.corpus.actor)
        assert scope is not None
        self.assertEqual("pending", scope.disposition)
        self.assertEqual("complete", scope.exact_state)
        self.assertEqual("pending", scope.generic_state)
        self.assertEqual("generic-limit", scope.pending_reason)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM dependency_impact_runs WHERE project_id=? AND replacement_revision_id=?",
                    (self.corpus.project, revoked.revision_id),
                ).fetchone()[0],
            )

    def test_generic_limit_continues_direct_and_transitive_outputs_after_restart(self) -> None:
        initial = self._publish(self._policy())
        outputs = []
        with self.repository._transaction(write=True) as (_, aggregates):
            prior = aggregates.get_revision(initial.revision_id)
            for dependency_kind in ("human-decision", "source-revision"):
                output_revision_id = new_uuid_v7()
                prior = aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=output_revision_id,
                        aggregate_id=new_uuid_v7(),
                        aggregate_kind="workflow",
                        created_at=self.corpus.actor.occurred_at,
                        modified_at=self.corpus.actor.occurred_at,
                        display_label_observed="Synthetic rights-dependent output",
                        display_label_normalized=None,
                        knowledge_status="inferred",
                        rights_status="unknown",
                        dependency_coverage="complete",
                        provenance_inputs=(prior,),
                        material_dependencies=(
                            MaterialDependency(
                                new_uuid_v7(),
                                dependency_kind,
                                "direct",
                                prior.revision_id,
                                None,
                                None,
                                _projection_content_sha256(prior),
                                "dependency.material.v1",
                                "1.0.0",
                            ),
                        ),
                    ),
                    AtomicRepositoryEvent(
                        event_id=new_uuid_v7(),
                        outbox_id=new_uuid_v7(),
                        event_type="rights.test-dependent",
                        occurred_at=self.corpus.actor.occurred_at,
                        available_at=self.corpus.actor.occurred_at,
                        trace_id=self.corpus.actor.trace_id,
                        actor_type="human",
                        actor_id=self.corpus.actor.actor_id,
                        idempotency_key="rights-test-" + new_uuid_v7(),
                    ),
                    expected_revision=None,
                )
                outputs.append(output_revision_id)
        revoked = self._policy(predecessor_revision_id=initial.revision_id, value="denied")
        with patch(
            "research_observatory_core.rights_repository._SqliteDependencyImpactRepository._preview_with_connection",
            side_effect=DependencyImpactLimitExceeded("synthetic low planner cap"),
        ):
            revoked = self._publish(revoked)
        reopened = SqliteRightsRepository(self.corpus.database, self.corpus.project)
        scope = reopened.recheck_scope(self.subject, actor=self.corpus.actor)
        assert scope is not None
        self.assertEqual("pending", scope.generic_state)
        self.assertEqual("generic-limit", scope.pending_reason)
        self.assertEqual(revoked.revision_id, scope.rights_revision_id)
        for output_revision_id in outputs:
            guarded = reopened.output_rechecks(output_revision_id, actor=self.corpus.actor)
            self.assertEqual((), guarded.markers)
            self.assertTrue(guarded.propagation_pending)
            self.assertFalse(guarded.propagation_unknown)
        with patch("research_observatory_core.rights_repository._generic_budget_exceeded", return_value=True):
            unknown_guard = reopened.output_rechecks(outputs[0], actor=self.corpus.actor)
        self.assertTrue(unknown_guard.propagation_pending)
        self.assertTrue(unknown_guard.propagation_unknown)
        with patch("research_observatory_core.rights_repository._generic_budget_exceeded", return_value=True):
            limited = reopened.advance_rechecks(self.subject, actor=self.corpus.actor, batch_size=1)
        assert limited is not None
        self.assertEqual("pending", limited.generic_state)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM rights_policy_generic_rechecks WHERE project_id=? AND rights_revision_id=?",
                    (self.corpus.project, revoked.revision_id),
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM rights_policy_recheck_completions "
                    "WHERE project_id=? AND rights_revision_id=? AND dimension='generic'",
                    (self.corpus.project, revoked.revision_id),
                ).fetchone()[0],
            )
        later_allow = self._publish(self._policy(predecessor_revision_id=revoked.revision_id))
        request = RightsRequest(actor_id=self.corpus.actor.actor_id, subject=self.subject, use=self.use)
        self.assertEqual("unknown", reopened.evaluate(request, actor=self.corpus.actor).code)
        first = reopened.advance_rechecks(self.subject, actor=self.corpus.actor, batch_size=1)
        assert first is not None
        self.assertEqual("pending", first.generic_state)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            self.assertEqual(
                1,
                connection.execute(
                    "SELECT COUNT(*) FROM rights_policy_generic_rechecks WHERE project_id=? AND rights_revision_id=?",
                    (self.corpus.project, revoked.revision_id),
                ).fetchone()[0],
            )
        restarted = SqliteRightsRepository(self.corpus.database, self.corpus.project)
        final = restarted.advance_rechecks(self.subject, actor=self.corpus.actor, batch_size=1)
        assert final is not None
        self.assertEqual("complete", final.disposition)
        self.assertEqual(later_allow.revision_id, final.rights_revision_id)
        self.assertEqual("allow", restarted.evaluate(request, actor=self.corpus.actor).code)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            rows = connection.execute(
                "SELECT output_revision_id,reason,disposition FROM rights_policy_generic_rechecks "
                "WHERE project_id=? AND rights_revision_id=?",
                (self.corpus.project, revoked.revision_id),
            ).fetchall()
            receipts = connection.execute(
                "SELECT COUNT(*) FROM rights_policy_recheck_completions "
                "WHERE project_id=? AND rights_revision_id=? AND dimension='generic'",
                (self.corpus.project, revoked.revision_id),
            ).fetchone()[0]
        self.assertEqual(set(outputs), {str(row[0]) for row in rows})
        self.assertEqual({("RIGHTS_POLICY", "requires-review")}, {(row[1], row[2]) for row in rows})
        self.assertEqual(1, receipts)

    def test_changed_policy_marks_exact_source_path_and_publishes_atomically(self) -> None:
        item = self.corpus._create()
        before = self._counts()
        initial = self._policy()
        initial = self._publish(initial)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            rows = connection.execute(
                "SELECT output_revision_id,path_id,reason,disposition FROM rights_policy_rechecks "
                "WHERE project_id=? AND rights_revision_id=?",
                (self.corpus.project, initial.revision_id),
            ).fetchall()
            path_id = connection.execute(
                "SELECT primary_discovery_path_id FROM corpus_item_states WHERE revision_id=?",
                (item.revision_id,),
            ).fetchone()[0]
        self.assertEqual([(item.revision_id, path_id, "RIGHTS_POLICY", "requires-review")], list(map(tuple, rows)))
        self.assertEqual(before[4] + 1, self._counts()[4])
        self.assertEqual(before[5] + 1, self._counts()[5])

        revised = self._policy(predecessor_revision_id=initial.revision_id, value="denied")
        snapshot = self._counts()

        def fail_after_aggregate(step: str) -> None:
            if step == "aggregate-created":
                raise RightsProblem("rights-injected-failure")

        with (
            patch("research_observatory_core.rights_repository._publication_step", side_effect=fail_after_aggregate),
            self.assertRaisesRegex(RightsProblem, "rights-injected-failure"),
        ):
            self._publish(revised)
        self.assertEqual(snapshot, self._counts())
        self.assertEqual(initial, self.repository.current(self.subject, actor=self.corpus.actor))
        self._publish(revised)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            self.assertEqual(
                [(item.revision_id,)],
                list(
                    map(
                        tuple,
                        connection.execute(
                            "SELECT output_revision_id FROM rights_policy_rechecks WHERE project_id=? "
                            "AND rights_revision_id=?",
                            (self.corpus.project, revised.revision_id),
                        ).fetchall(),
                    )
                ),
            )

    def test_stale_predecessor_and_command_substitution_are_denied_without_writes(self) -> None:
        initial = self._policy()
        command = new_uuid_v7()
        self._publish(initial, command_id=command)
        saved = self._counts()
        with self.assertRaisesRegex(RightsProblem, "rights-command-conflict"):
            self._publish(self._policy(), command_id=command)
        with self.assertRaisesRegex(RightsProblem, "rights-predecessor-stale"):
            self._publish(self._policy())
        self.assertEqual(saved, self._counts())

    def test_source_copy_actor_and_unverified_entitlement_cannot_create_grant(self) -> None:
        for policy in (
            self._policy(subject=self.subject.model_copy(update={"copy_id": new_uuid_v7()})),
            self._policy(subject=self.subject.model_copy(update={"source_assertion_revision_id": new_uuid_v7()})),
            self._policy(asserted_by_actor_id=new_uuid_v7()),
            self._policy(basis="verified-entitlement"),
            self._policy(basis="source-observation"),
            self._policy().model_copy(
                update={
                    "source_observation": self.repository._source_observation(
                        self.corpus.source, self.subject.source_assertion_revision_id
                    ).model_copy(update={"source_sha256": "0" * 64})
                }
            ),
            self._policy().model_copy(
                update={
                    "permissions": (
                        self._policy()
                        .permissions[0]
                        .model_copy(
                            update={
                                "license_observation_revision_id": self.subject.source_assertion_revision_id,
                            }
                        ),
                    ),
                }
            ),
        ):
            with self.subTest(policy=policy):
                before = self._counts()
                with self.assertRaises(RightsProblem):
                    self._publish(policy)
                self.assertEqual(before, self._counts())

    def test_replacement_completes_generic_impact_and_stale_cause_after_restart(self) -> None:
        initial = self._policy()
        self._publish(initial)
        with self.repository._transaction(write=True) as (_, aggregates):
            prior = aggregates.get_revision(initial.revision_id)
            output_revision_id = new_uuid_v7()
            aggregates.append(
                AggregateRevisionDraft(
                    revision_id=output_revision_id,
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="workflow",
                    created_at=self.corpus.actor.occurred_at,
                    modified_at=self.corpus.actor.occurred_at,
                    display_label_observed="Synthetic dependent output",
                    display_label_normalized=None,
                    knowledge_status="inferred",
                    rights_status="unknown",
                    dependency_coverage="complete",
                    provenance_inputs=(prior,),
                    material_dependencies=(
                        MaterialDependency(
                            new_uuid_v7(),
                            "human-decision",
                            "direct",
                            prior.revision_id,
                            None,
                            None,
                            _projection_content_sha256(prior),
                            "dependency.material.v1",
                            "1.0.0",
                        ),
                    ),
                ),
                AtomicRepositoryEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type="rights.test-dependent",
                    occurred_at=self.corpus.actor.occurred_at,
                    available_at=self.corpus.actor.occurred_at,
                    trace_id=self.corpus.actor.trace_id,
                    actor_type="human",
                    actor_id=self.corpus.actor.actor_id,
                    idempotency_key="rights-test-" + new_uuid_v7(),
                ),
                expected_revision=None,
            )
        revised = self._policy(predecessor_revision_id=initial.revision_id, value="denied")
        before_impact_failure = self._counts()

        def fail_during_impact(step: str) -> None:
            if step == "dependency-impact-batch-created":
                raise RightsProblem("rights-injected-impact-failure")

        with (
            patch("research_observatory_core.rights_repository._publication_step", side_effect=fail_during_impact),
            self.assertRaisesRegex(RightsProblem, "rights-injected-impact-failure"),
        ):
            self._publish(revised)
        self.assertEqual(before_impact_failure, self._counts())
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM dependency_impact_runs WHERE project_id=? AND replacement_revision_id=?",
                    (self.corpus.project, revised.revision_id),
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM dependency_stale_causes WHERE project_id=? AND output_revision_id=?",
                    (self.corpus.project, output_revision_id),
                ).fetchone()[0],
            )
        self._publish(revised)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            rows = connection.execute(
                "SELECT i.output_revision_id,i.disposition,r.reason,r.previous_revision_id,r.replacement_revision_id,"
                "r.run_id "
                "FROM dependency_impact_items i JOIN dependency_impact_runs r ON r.run_id=i.run_id "
                "WHERE i.project_id=? AND i.output_revision_id=?",
                (self.corpus.project, output_revision_id),
            ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual(
            (output_revision_id, "stale", "RIGHTS_POLICY", initial.revision_id, revised.revision_id),
            tuple(rows[0][:5]),
        )
        run_id = str(rows[0][5])
        reopened = _SqliteDependencyImpactRepository(self.corpus.database, self.corpus.project)
        run = reopened.run(run_id)
        self.assertEqual("completed", run.state)
        self.assertEqual(1, run.processed_items)
        self.assertEqual(1, run.stale_count)
        causes = reopened.stale_states(output_revision_id=output_revision_id)
        self.assertEqual(1, len(causes))
        self.assertEqual(run.change_id, causes[0].change_id)
        self.assertEqual("RIGHTS_POLICY", causes[0].reason)
        self.assertEqual("stale", causes[0].disposition)

    def test_draft_mints_ids_only_after_replay_and_binds_semantic_request(self) -> None:
        draft = RightsPermissionDraft(
            use=self.use,
            value="permitted",
            basis="researcher-confirmed",
            confidence="confirmed",
            evidence_revision_ids=(self.subject.source_assertion_revision_id,),
            expires_at="2030-10-01T00:00:00.000Z",
        )
        command_id = new_uuid_v7()
        first = self.repository.publish_draft(
            self.subject,
            (draft,),
            None,
            command_id=command_id,
            command_sha256="c" * 64,
            actor=self.corpus.actor,
        )
        counts = self._counts()
        later_actor = replace(self.corpus.actor, occurred_at="2026-10-02T00:00:00.000Z", trace_id="e" * 32)
        with patch(
            "research_observatory_core.rights_repository._utcnow",
            return_value=datetime(2026, 10, 2, tzinfo=UTC),
        ):
            replay = self.repository.publish_draft(
                self.subject,
                (draft,),
                None,
                command_id=command_id,
                command_sha256="c" * 64,
                actor=later_actor,
            )
        self.assertEqual(first, replay)
        self.assertEqual(counts, self._counts())
        self.assertEqual(self.corpus.actor.actor_id, first.permissions[0].asserted_by_actor_id)
        with self.assertRaisesRegex(RightsProblem, "rights-command-conflict"):
            self.repository.publish_draft(
                self.subject,
                (draft.model_copy(update={"value": "denied"}),),
                None,
                command_id=command_id,
                command_sha256="c" * 64,
                actor=self.corpus.actor,
            )
        self.assertEqual(counts, self._counts())

    def test_initial_policy_marks_citation_output_bound_to_exact_assertion(self) -> None:
        citing = self.corpus._citing_work()
        assert citing.work_id is not None and citing.work_revision_id is not None

        def build():
            item_id, path_id = new_uuid_v7(), new_uuid_v7()
            return (
                CorpusItemRevision(
                    project_id=self.corpus.project,
                    item_id=item_id,
                    revision_id=new_uuid_v7(),
                    previous_revision_id=None,
                    work_id=self.corpus.work_id,
                    work_revision_id=self.corpus.work_revision_id,
                    membership="candidate",
                    review="pending",
                    duplicate_of_item_id=None,
                    availability="unknown",
                    discovery_path_ids=(path_id,),
                    decision_revision_id=None,
                ),
                DiscoveryPath(
                    path_id=path_id,
                    project_id=self.corpus.project,
                    item_id=item_id,
                    kind="citation",
                    source_revision_id=citing.assertion_revision_id,
                    direction="source-to-corpus-item",
                    occurred_at=self.corpus.actor.occurred_at,
                    predecessor_item_revision_id=None,
                    context_id=citing.work_id,
                    context_revision_id=citing.work_revision_id,
                    citing_work_revision_id=citing.work_revision_id,
                ),
            )

        item = self.corpus.repository.create_citation(
            command_id=new_uuid_v7(),
            command_sha256="b" * 64,
            actor=self.corpus.actor,
            work_id=self.corpus.work_id,
            work_revision_id=self.corpus.work_revision_id,
            citing_work_id=citing.work_id,
            citing_work_revision_id=citing.work_revision_id,
            source_assertion_revision_id=citing.assertion_revision_id,
            build=build,
        )
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            row = connection.execute(
                "SELECT assertion_json FROM reconciliation_assertions WHERE project_id=? AND revision_id=?",
                (self.corpus.project, citing.assertion_revision_id),
            ).fetchone()
            assert row is not None
            source = SourceAssertion.model_validate_json(str(row[0]))
            connection.execute("BEGIN")
            subject = self.repository.source_metadata_subject_with_connection(connection, source)
        initial = self._policy(subject=subject)
        self._publish(initial)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            marked = {
                str(row[0])
                for row in connection.execute(
                    "SELECT output_revision_id FROM rights_policy_rechecks WHERE project_id=? AND rights_revision_id=?",
                    (self.corpus.project, initial.revision_id),
                )
            }
        self.assertEqual({item.revision_id}, marked)

    def test_two_retained_sources_of_one_work_keep_distinct_rights(self) -> None:
        self.corpus._fixture.prepare_another(
            raw=b"title,doi\nDistinct source for same synthetic work,10.99999/synthetic-a\n"
        )
        output = self.corpus._fixture.publish()
        fixture = self.corpus._fixture.fixture
        member = next(
            value
            for value in fixture.repository.manifest_members(output.revision_id, after=0, limit=100)
            if value.decision.included
        )
        assert member.source_record_revision_id is not None
        address = SourceAddress(
            kind="import-member",
            context_id=fixture.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            raw_sha = connection.execute(
                "SELECT raw_sha256 FROM import_manifest_members WHERE project_id=? "
                "AND manifest_revision_id=? AND ordinal=?",
                (self.corpus.project, output.revision_id, member.ordinal),
            ).fetchone()[0]
        other_source = self.corpus.source.model_copy(
            update={
                "address": address,
                "source_revision_id": member.source_record_revision_id,
                "source_sha256": raw_sha,
            }
        )
        linked = SqliteReconciliationRepository(self.corpus.database, self.corpus.project).reconcile(
            address,
            command_id=new_uuid_v7(),
            actor=ReconciliationActor(new_uuid_v7(), "a" * 32, self.corpus.actor.occurred_at, "b" * 64, "c" * 64),
            resolve=lambda requested: other_source if requested == address else self.corpus.source,
        )
        self.assertEqual(self.corpus.work_id, linked.work_id)
        self.assertNotEqual(self.subject.source_assertion_revision_id, linked.assertion_revision_id)
        with closing(
            open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project)
        ) as connection:
            connection.execute("BEGIN")
            other_subject = self.repository.source_metadata_subject_with_connection(connection, other_source)
        allowed = self._policy()
        denied = self._policy(subject=other_subject, value="denied")
        self._publish(allowed)
        self._publish(denied)
        with patch(
            "research_observatory_core.rights_repository._utcnow",
            return_value=datetime(2026, 9, 30, tzinfo=UTC),
        ):
            first = self.repository.evaluate(
                RightsRequest(actor_id=self.corpus.actor.actor_id, subject=self.subject, use=self.use),
                actor=self.corpus.actor,
            )
            second = self.repository.evaluate(
                RightsRequest(actor_id=self.corpus.actor.actor_id, subject=other_subject, use=self.use),
                actor=self.corpus.actor,
            )
        self.assertEqual("allow", first.code)
        self.assertEqual("deny", second.code)
        self.assertNotEqual(first.policy_revision_id, second.policy_revision_id)


class RightsConnectorSiblingTests(unittest.TestCase):
    def test_one_connector_page_sibling_does_not_inherit_other_records_recheck(self) -> None:
        fixture = corpus_tests.CorpusConnectorWriterTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        fixture.request = type(fixture.request).model_validate(
            fixture.request.model_dump() | {"page_size": 2, "query": scholarly_fixtures.search()}
        )
        document = scholarly_fixtures.fixture("openalex")
        sibling = copy.deepcopy(document["results"][0])
        sibling["id"] = "https://openalex.org/W999999999902"
        sibling["doi"] = "https://doi.org/10.99999/SYNTHETIC-SIBLING"
        sibling["ids"]["openalex"] = sibling["id"]
        sibling["ids"]["doi"] = sibling["doi"]
        sibling["title"] = "Unrelated synthetic sibling record"
        document["results"].append(sibling)
        document["meta"]["next_cursor"] = None
        preview, job = fixture.schedule()
        with patch.object(connector_workflow_tests, "fixture", return_value=document):
            fixture.worker.run_pending()
        page = fixture.worker.reconciliation_sources(fixture.root, job.job_id, after=0, limit=2)
        self.assertEqual(2, len(page.addresses))
        self.assertEqual(page.addresses[0].revision_id, page.addresses[1].revision_id)
        sources = tuple(fixture.worker.reconciliation_source(fixture.root, address) for address in page.addresses)
        database, project = fixture.repository._database, fixture.project.project_id
        reconciliation = SqliteReconciliationRepository(database, project)
        outcomes = tuple(
            reconciliation.reconcile(
                address,
                command_id=new_uuid_v7(),
                actor=ReconciliationActor(new_uuid_v7(), "a" * 32, fixture.clock.now(), "b" * 64, "c" * 64),
                resolve=lambda requested: sources[page.addresses.index(requested)],
            )
            for address in page.addresses
        )
        intent_repo = _SqliteIntentRevisionRepository(database, project)
        bridge = intent_repo.project_identity()
        assert bridge is not None
        _, revisions, _, _ = validated_workflow_authority(intent_repo, expected_project_id=bridge.domain_project_id)
        current_intent = revisions[0]
        intent_revision_id = current_intent["revisionId"]
        intent_content_hash = current_intent["revisionContentHash"]
        assert isinstance(intent_revision_id, str)
        assert isinstance(intent_content_hash, str)
        privacy = _read_policy(_SqlitePrivacyPolicyRepository(database, project), project)
        actor = CorpusActor(
            actor_id=new_uuid_v7(),
            trace_id="d" * 32,
            occurred_at=fixture.clock.now(),
            intent_revision_id=intent_revision_id,
            intent_sha256=intent_content_hash.removeprefix("sha256:"),
            policy_sha256=fingerprint(privacy.model_dump(mode="json", by_alias=True)).removeprefix("sha256:"),
        )
        rights = SqliteRightsRepository(database, project, connector_record_resolver=fixture.repository.source_record)
        with closing(open_canonical_database(database, expected_project_id=project)) as connection:
            connection.execute("BEGIN")
            subjects = tuple(rights.source_metadata_subject_with_connection(connection, source) for source in sources)

        def permission(subject: RightsSubject, use: RightsUse) -> RightsPermission:
            return RightsPermission(
                assertion_id=new_uuid_v7(),
                subject=subject,
                use=use,
                value="permitted",
                basis="researcher-confirmed",
                confidence="confirmed",
                asserted_by_actor_id=actor.actor_id,
                evidence_revision_ids=(subject.source_assertion_revision_id,),
                license_observation_revision_id=None,
                entitlement_revision_id=None,
                recorded_at="2026-09-01T00:00:00.000Z",
                expires_at="2030-10-01T00:00:00.000Z",
            )

        initial_policies = tuple(
            RightsPolicyRevision(
                revision_id=new_uuid_v7(),
                predecessor_revision_id=None,
                subject=subject,
                permissions=tuple(
                    permission(
                        subject,
                        RightsUse(action=action, purpose="corpus-membership", destination_kind="local-project"),
                    )
                    for action in ("store", "inspect", "derive", "index")
                ),
            )
            for subject in subjects
        )
        with self.assertRaisesRegex(RightsProblem, "rights-observation-unavailable"):
            SqliteRightsRepository(database, project).publish(
                initial_policies[0], command_id=new_uuid_v7(), command_sha256="f" * 64, actor=actor
            )
        with self.assertRaisesRegex(RightsProblem, "rights-observation-source-mismatch"):
            SqliteRightsRepository(
                database,
                project,
                connector_record_resolver=lambda revision, _ordinal: fixture.repository.source_record(revision, 1),
            ).publish(initial_policies[0], command_id=new_uuid_v7(), command_sha256="f" * 64, actor=actor)
        for initial in initial_policies:
            published = rights.publish(initial, command_id=new_uuid_v7(), command_sha256="f" * 64, actor=actor)
            assert published.source_observation is not None
            record = fixture.repository.source_record(
                initial.subject.address.revision_id, initial.subject.address.ordinal
            )
            self.assertEqual(record.terms, published.source_observation.terms)

        corpus = SqliteCorpusRepository(database, project)
        items = []
        for address, source, outcome in zip(page.addresses, sources, outcomes, strict=True):
            assert outcome.work_id is not None and outcome.work_revision_id is not None
            item_id, path_id = new_uuid_v7(), new_uuid_v7()

            def build(item_id=item_id, path_id=path_id, outcome=outcome, source=source, address=address):
                return (
                    CorpusItemRevision(
                        project_id=project,
                        item_id=item_id,
                        revision_id=new_uuid_v7(),
                        previous_revision_id=None,
                        work_id=outcome.work_id,
                        work_revision_id=outcome.work_revision_id,
                        membership="candidate",
                        review="pending",
                        duplicate_of_item_id=None,
                        availability="unknown",
                        discovery_path_ids=(path_id,),
                        decision_revision_id=None,
                    ),
                    DiscoveryPath(
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
                    ),
                )

            items.append(
                corpus.create(
                    command_id=new_uuid_v7(),
                    command_sha256="f" * 64,
                    actor=actor,
                    source=source,
                    build=build,
                )
            )
        policy = RightsPolicyRevision(
            revision_id=new_uuid_v7(),
            predecessor_revision_id=initial_policies[0].revision_id,
            subject=subjects[0],
            permissions=(
                permission(
                    subjects[0],
                    RightsUse(action="inspect", purpose="scholarly-screening", destination_kind="local-project"),
                ),
            ),
        )
        published = rights.publish(policy, command_id=new_uuid_v7(), command_sha256="f" * 64, actor=actor)
        assert published.source_observation is not None
        first_record = fixture.repository.source_record(sources[0].address.revision_id, sources[0].address.ordinal)
        self.assertEqual(first_record.terms, published.source_observation.terms)
        with closing(open_canonical_database(database, expected_project_id=project)) as connection:
            marked = {
                str(row[0])
                for row in connection.execute(
                    "SELECT output_revision_id FROM rights_policy_rechecks WHERE project_id=? AND rights_revision_id=?",
                    (project, policy.revision_id),
                )
            }
        self.assertEqual({items[0].revision_id}, marked)
        self.assertNotIn(items[1].revision_id, marked)


if __name__ == "__main__":
    unittest.main()
