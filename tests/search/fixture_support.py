"""Typed composition of existing protected fixtures; no inherited test replay."""

import unittest

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.lexical_query_repository import CoreLexicalQueryService
from research_observatory_core.search import load_query_document, parse_query
from research_observatory_core.search.run_values import SearchFilters, SearchRequestInput

from tests.search.test_index_service import IndexServiceTests
from tests.search.test_protected_lexical_store import ProtectedLexicalStoreTests


class ProtectedIndexFixture(unittest.TestCase):
    def setUp(self):
        fixture = ProtectedLexicalStoreTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.protected_fixture = fixture
        self.root, self.scope, self.keys = fixture.root, fixture.scope, fixture.keys

    def store(self, create=False):
        return self.protected_fixture.store(create=create)


class CanonicalIndexFixture(unittest.TestCase):
    def setUp(self):
        fixture = IndexServiceTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.index_fixture = fixture
        self.f, self.service = fixture.f, fixture.service
        self.subject, self.grant = fixture.subject, fixture.grant


class SearchRunFixture(CanonicalIndexFixture):
    def setUp(self):
        super().setUp()
        from research_observatory_core.lexical_run_repository import SqliteLexicalRunRepository

        self.document_fixture = self.f.f
        self.repo = SqliteLexicalRunRepository(
            self.service,
            session_id=self.document_fixture.f.session,
            intent=lambda: self.document_fixture.intent,
            now=lambda: self.document_fixture.now,
        )
        self.reader = CoreLexicalQueryService(self.service)

    def inputs(self, command=None, query="identifiers:synthetic"):
        actor = self.document_fixture.actor
        return SearchRequestInput(
            project_id=self.service.project,
            command_id=command or new_uuid_v7(),
            actor_id=actor.actor_id,
            session_id=self.document_fixture.f.session,
            intent=self.document_fixture.intent,
            policy_sha256=actor.policy_sha256,
            query_document=parse_query(query).to_json(),
            filters=SearchFilters(),
        )

    def claim(self, job):
        claim = self.repo.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            activity_types=("lexical-search",),
            now=self.document_fixture.now,
            lease_duration_ms=30000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(job.job_id, claim.job_id)
        self.repo.queue.start(claim, now=self.document_fixture.now)
        return claim

    def execute(self, inputs):
        job = self.repo.submit(inputs)
        claim = self.claim(job)
        query = load_query_document(inputs.query_document)
        result = self.reader.read(
            query, consume=lambda snapshot, _store: self.repo.complete(claim, snapshot, cancelled=lambda: False)
        )
        return job, claim, result
