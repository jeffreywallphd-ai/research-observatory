"""Bounded corpus HTTP diagnostics stay content-free across failure classes."""

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.corpus.membership import CorpusProblem


class CorpusApiTests(unittest.TestCase):
    def client(self, app):
        return TestClient(
            app,
            base_url="http://127.0.0.1:49152",
            headers={"Authorization": "Bearer " + "a" * 64},
            client=("127.0.0.1", 50000),
        )

    def application(self, corpus=None):
        return create_app(
            corpus=corpus,
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )

    def command(self):
        return {
            "root": "C:/synthetic-project",
            "commandId": "01900000-0000-7000-8000-000000000001",
            "workId": "01900000-0000-7000-8000-000000000002",
            "workRevisionId": "01900000-0000-7000-8000-000000000003",
            "source": {
                "kind": "import-member",
                "contextId": "01900000-0000-7000-8000-000000000004",
                "revisionId": "01900000-0000-7000-8000-000000000005",
                "ordinal": 1,
                "recordKey": "a" * 64,
            },
        }

    def test_absent_runtime_malformed_and_oversized_commands_fail_safely(self):
        with self.client(self.application()) as client:
            absent = client.post("/projects/corpus/create", json=self.command())
            self.assertEqual((503, "RO-CORE-CORPUS-UNAVAILABLE"), (absent.status_code, absent.json()["code"]))
            malformed = client.post("/projects/corpus/create", json=self.command() | {"actorId": "forged"})
            self.assertEqual((422, "RO-CORE-VALIDATION-FAILED"), (malformed.status_code, malformed.json()["code"]))
            oversized = client.post("/projects/corpus/create", json=self.command() | {"padding": "x" * 32768})
            self.assertEqual((413, "RO-CORE-CORPUS-REQUEST-LIMIT"), (oversized.status_code, oversized.json()["code"]))

    def test_conflict_rights_and_integrity_do_not_expose_source_fields(self):
        failure = {"code": "corpus-command-conflict"}

        def create(*_args, **_kwargs):
            raise CorpusProblem(failure["code"])

        with self.client(self.application(SimpleNamespace(create=create))) as client:
            for internal, status, public in (
                ("corpus-command-conflict", 409, "RO-CORE-CORPUS-CONFLICT"),
                ("corpus-rights-denied", 403, "RO-CORE-CORPUS-DENIED"),
                ("corpus-history-integrity-invalid", 500, "RO-CORE-CORPUS-INTEGRITY-FAILED"),
            ):
                failure["code"] = internal
                result = client.post("/projects/corpus/create", json=self.command())
                self.assertEqual((status, public), (result.status_code, result.json()["code"]))
                self.assertNotIn("recordKey", result.text)
                self.assertNotIn("C:/synthetic-project", result.text)
