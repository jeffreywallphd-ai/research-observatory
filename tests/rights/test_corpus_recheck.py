"""A current rights revision cannot be bypassed by retained import permissions."""

from __future__ import annotations

import hashlib
import unittest
from contextlib import closing

from research_observatory_core.corpus.membership import CorpusProblem
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.rights_policy import RightsPermission, RightsPolicyRevision, RightsUse
from research_observatory_core.rights_repository import SqliteRightsRepository
from research_observatory_core.storage import open_canonical_database


class CorpusRightsRecheckTests(unittest.TestCase):
    def setUp(self) -> None:
        from tests.corpus.test_repository import CorpusRepositoryTests

        fixture = CorpusRepositoryTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture

    def test_new_policy_denial_blocks_old_import_grant_and_marks_exact_output(self) -> None:
        fixture = self.fixture
        original = fixture._create()
        rights = SqliteRightsRepository(fixture.database, fixture.project)
        with closing(open_canonical_database(fixture.database, expected_project_id=fixture.project)) as connection:
            connection.execute("BEGIN")
            subject = rights.source_metadata_subject_with_connection(connection, fixture.source)
        permissions = tuple(
            RightsPermission(
                assertion_id=new_uuid_v7(),
                subject=subject,
                use=RightsUse(action=action, purpose="corpus-membership", destination_kind="local-project"),
                value="denied" if action == "index" else "permitted",
                basis="researcher-confirmed",
                confidence="confirmed",
                asserted_by_actor_id=fixture.actor.actor_id,
                evidence_revision_ids=(subject.source_assertion_revision_id,),
                license_observation_revision_id=None,
                entitlement_revision_id=None,
                recorded_at=fixture.actor.occurred_at,
                expires_at=None,
            )
            for action in ("store", "inspect", "derive", "index")
        )
        policy = RightsPolicyRevision(
            revision_id=new_uuid_v7(),
            predecessor_revision_id=None,
            subject=subject,
            permissions=permissions,
        )
        rights.publish(
            policy,
            command_id=new_uuid_v7(),
            command_sha256=hashlib.sha256(policy.model_dump_json(by_alias=True).encode("utf-8")).hexdigest(),
            actor=fixture.actor,
        )
        before_denial = fixture._counts()

        with self.assertRaises(CorpusProblem) as caught:
            fixture._create()
        self.assertEqual(caught.exception.code, "corpus-rights-denied")
        self.assertEqual(before_denial, fixture._counts())
        with closing(open_canonical_database(fixture.database, expected_project_id=fixture.project)) as connection:
            marked = connection.execute(
                "SELECT COUNT(*) FROM rights_policy_rechecks WHERE project_id=? AND output_revision_id=? "
                "AND reason='RIGHTS_POLICY'",
                (fixture.project, original.revision_id),
            ).fetchone()[0]
            audit = connection.execute(
                "SELECT d.event_kind,d.decision_code,d.reason_code,d.policy_revision_id,d.policy_sha256,"
                "d.actor_id,d.trace_id,d.source_assertion_revision_id,d.use_action,r.policy_sha256 "
                "FROM rights_use_decisions d JOIN rights_policy_revisions r "
                "ON r.project_id=d.project_id AND r.revision_id=d.policy_revision_id "
                "WHERE d.project_id=? AND d.event_kind='denied-attempt'",
                (fixture.project,),
            ).fetchall()
        self.assertGreater(marked, 0)
        self.assertEqual(len(audit), 1)
        event, code, reason, revision, stored_hash, actor_id, trace_id, source_revision, action, policy_hash = tuple(
            audit[0]
        )
        self.assertEqual(
            (event, code, reason, revision, actor_id, trace_id, source_revision, action),
            (
                "denied-attempt",
                "deny",
                "rights-explicit-denial",
                policy.revision_id,
                fixture.actor.actor_id,
                fixture.actor.trace_id,
                subject.source_assertion_revision_id,
                "index",
            ),
        )
        self.assertEqual(stored_hash, policy_hash)


if __name__ == "__main__":
    unittest.main()
