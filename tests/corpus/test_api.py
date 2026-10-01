"""Bounded corpus and source-rights HTTP diagnostics stay content-free."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.corpus.membership import CorpusProblem
from research_observatory_core.corpus_report_model import (
    CorpusReportAccumulator,
    CorpusReportDrillPage,
    CorpusReportFilter,
)
from research_observatory_core.ports.rights import RightsOutputRecheckState
from research_observatory_core.rights_policy import RightsDecision, RightsPolicyRevision
from research_observatory_core.rights_repository import RightsProblem

RIGHTS_FIXTURES = Path(__file__).resolve().parents[2] / "packages/contracts/rights/fixtures"


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

    def rights_command(self):
        policy = json.loads((RIGHTS_FIXTURES / "valid-policy.v1.json").read_text(encoding="utf-8"))
        permission = policy["permissions"][0]
        draft = {
            key: value
            for key, value in permission.items()
            if key not in {"assertionId", "subject", "assertedByActorId", "recordedAt"}
        }
        return {
            "root": "C:/synthetic-project",
            "commandId": "01900000-0000-7000-8000-000000000006",
            "subject": policy["subject"],
            "permissions": [draft],
            "expectedPredecessorRevisionId": None,
            "confirmed": True,
        }, policy

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

    def test_rights_routes_require_authentication_and_forward_bounded_values(self):
        command, policy = self.rights_command()
        decision = json.loads((RIGHTS_FIXTURES / "valid-decision.v1.json").read_text(encoding="utf-8"))
        policy_model = RightsPolicyRevision.model_validate_json(json.dumps(policy))
        decision_model = RightsDecision.model_validate_json(json.dumps(decision))
        calls: list[tuple[Any, ...]] = []

        def publish(root, **values):
            calls.append(("publish", root, values))
            if values["confirmed"] is not True:
                raise CorpusProblem("corpus-rights-denied")
            return policy_model

        def current(root, subject, **values):
            calls.append(("current", root, subject, values))
            return policy_model

        def recheck_scope(root, subject, **values):
            calls.append(("recheck-scope", root, subject, values))
            return None

        output_state = RightsOutputRecheckState(
            output_revision_id=command["commandId"],
            markers=(),
            propagation_pending=False,
            propagation_unknown=False,
            truncated=False,
        )

        def output_rechecks(root, output_revision_id, **values):
            calls.append(("output-rechecks", root, output_revision_id, values))
            return output_state

        def advance_rechecks(root, subject, **values):
            calls.append(("advance-rechecks", root, subject, values))
            return None

        def evaluate(root, subject, use, **values):
            calls.append(("evaluate", root, subject, use, values))
            return decision_model

        runtime = SimpleNamespace(
            publish_rights=publish,
            current_rights=current,
            rights_recheck_scope=recheck_scope,
            output_rights_rechecks=output_rechecks,
            advance_rights_rechecks=advance_rechecks,
            evaluate_rights=evaluate,
        )
        with self.client(self.application(runtime)) as client:
            unauthorized = client.post("/projects/corpus/rights/publish", json=command, headers={"Authorization": ""})
            self.assertEqual(401, unauthorized.status_code)
            published = client.post("/projects/corpus/rights/publish", json=command)
            self.assertEqual(200, published.status_code, published.text)
            self.assertEqual(policy, published.json())
            self.assertEqual("no-store", published.headers["Cache-Control"])
            current_result = client.post(
                "/projects/corpus/rights/current", json={"root": command["root"], "subject": command["subject"]}
            )
            self.assertEqual(policy, current_result.json())
            rechecks = client.post(
                "/projects/corpus/rights/recheck-scope", json={"root": command["root"], "subject": command["subject"]}
            )
            self.assertEqual(200, rechecks.status_code)
            self.assertIsNone(rechecks.json())
            output = client.post(
                "/projects/corpus/rights/output-rechecks",
                json={"root": command["root"], "outputRevisionId": command["commandId"]},
            )
            self.assertEqual(200, output.status_code, output.text)
            self.assertEqual(output_state.model_dump(mode="json", by_alias=True), output.json())
            advanced = client.post(
                "/projects/corpus/rights/advance-rechecks",
                json={"root": command["root"], "subject": command["subject"], "batchSize": 1},
            )
            self.assertEqual(200, advanced.status_code)
            self.assertIsNone(advanced.json())
            evaluated = client.post(
                "/projects/corpus/rights/evaluate",
                json={"root": command["root"], "subject": command["subject"], "use": decision["use"]},
            )
            self.assertEqual(decision, evaluated.json())
            denied = client.post("/projects/corpus/rights/publish", json=command | {"confirmed": False})
            self.assertEqual((403, "RO-CORE-CORPUS-DENIED"), (denied.status_code, denied.json()["code"]))
            self.assertEqual(
                ["publish", "current", "recheck-scope", "output-rechecks", "advance-rechecks", "evaluate", "publish"],
                [call[0] for call in calls],
            )
            self.assertEqual(1, calls[4][3]["batch_size"])
            self.assertEqual(
                command["subject"]["sourceAssertionRevisionId"], calls[0][2]["subject"].source_assertion_revision_id
            )

    def test_rights_input_limits_and_repository_diagnostics_are_content_free(self):
        command, _ = self.rights_command()
        failure = {"code": "rights-command-conflict"}

        def publish(*_args, **_kwargs):
            raise RightsProblem(failure["code"])

        with self.client(self.application(SimpleNamespace(publish_rights=publish))) as client:
            malformed = client.post("/projects/corpus/rights/publish", json=command | {"actorId": "forged"})
            self.assertEqual((422, "RO-CORE-VALIDATION-FAILED"), (malformed.status_code, malformed.json()["code"]))
            # Publication has its own 256 KiB cap; the 32 KiB read/action cap remains.
            above_old_limit = client.post("/projects/corpus/rights/publish", json=command | {"padding": "x" * 40_000})
            self.assertEqual(422, above_old_limit.status_code)
            oversized = client.post("/projects/corpus/rights/publish", json=command | {"padding": "x" * 262_144})
            self.assertEqual((413, "RO-CORE-CORPUS-REQUEST-LIMIT"), (oversized.status_code, oversized.json()["code"]))
            read_oversized = client.post(
                "/projects/corpus/rights/current",
                json={"root": command["root"], "subject": command["subject"], "padding": "x" * 32_768},
            )
            self.assertEqual(413, read_oversized.status_code)
            excessive_batch = client.post(
                "/projects/corpus/rights/advance-rechecks",
                json={"root": command["root"], "subject": command["subject"], "batchSize": 1_001},
            )
            self.assertEqual(422, excessive_batch.status_code)
            for internal, status, public in (
                ("rights-command-conflict", 409, "RO-CORE-CORPUS-CONFLICT"),
                ("rights-evidence-unrelated", 403, "RO-CORE-CORPUS-DENIED"),
                ("rights-policy-integrity-invalid", 500, "RO-CORE-CORPUS-INTEGRITY-FAILED"),
            ):
                failure["code"] = internal
                result = client.post("/projects/corpus/rights/publish", json=command)
                self.assertEqual((status, public), (result.status_code, result.json()["code"]))
                self.assertNotIn(command["root"], result.text)
                self.assertNotIn(command["subject"]["sourceAssertionRevisionId"], result.text)

    def test_report_routes_bind_idempotency_snapshot_filter_and_authority(self):
        snapshot_id = "01900000-0000-7000-8000-000000000020"
        project_id = "01900000-0000-7000-8000-000000000021"
        command_id = "01900000-0000-7000-8000-000000000022"
        snapshot = CorpusReportAccumulator(snapshot_id=snapshot_id, project_id=project_id).finalize(
            intent_revision_id="01900000-0000-7000-8000-000000000023",
            protocol_revision_id="01900000-0000-7000-8000-000000000023",
            created_at="2026-10-01T00:00:00.000Z",
        )
        selected = CorpusReportFilter(kind="all")
        page = CorpusReportDrillPage(
            snapshot_id=snapshot_id,
            project_id=project_id,
            filter=selected,
            members=(),
            next_cursor=None,
            total=0,
        )
        calls: list[tuple[Any, ...]] = []

        def create_report(root, **values):
            calls.append(("create", root, values))
            return snapshot

        def inspect_report(root, selected_snapshot, **values):
            calls.append(("inspect", root, selected_snapshot, values))
            return snapshot

        def drill_report(root, selected_snapshot, **values):
            calls.append(("drill", root, selected_snapshot, values))
            return page

        runtime = SimpleNamespace(
            create_report=create_report,
            inspect_report=inspect_report,
            drill_report=drill_report,
        )
        root = "C:/synthetic-project"
        with self.client(self.application(runtime)) as client:
            unauthorized = client.post(
                "/projects/corpus/reports/create",
                json={"root": root, "commandId": command_id},
                headers={"Authorization": ""},
            )
            self.assertEqual(401, unauthorized.status_code)
            created = client.post("/projects/corpus/reports/create", json={"root": root, "commandId": command_id})
            self.assertEqual((200, snapshot_id), (created.status_code, created.json()["snapshotId"]))
            self.assertEqual("no-store", created.headers["Cache-Control"])
            read = client.post("/projects/corpus/reports/inspect", json={"root": root, "snapshotId": snapshot_id})
            self.assertEqual((200, snapshot_id), (read.status_code, read.json()["snapshotId"]))
            drilled = client.post(
                "/projects/corpus/reports/drill",
                json={"root": root, "snapshotId": snapshot_id, "filter": {"kind": "all"}, "limit": 25},
            )
            self.assertEqual((200, 0), (drilled.status_code, drilled.json()["total"]))
            self.assertEqual(["create", "inspect", "drill"], [call[0] for call in calls])
            self.assertEqual(command_id, calls[0][2]["command_id"])
            self.assertEqual(25, calls[2][3]["limit"])
            self.assertEqual(selected, calls[2][3]["filter"])
            self.assertIsNone(calls[2][3]["cursor"])
            for payload in (
                {"root": root, "snapshotId": snapshot_id, "limit": 101},
                {"root": root, "snapshotId": snapshot_id, "filter": {"kind": "source"}},
                {"root": root, "snapshotId": snapshot_id, "cursor": "x" * 513},
            ):
                invalid = client.post("/projects/corpus/reports/drill", json=payload)
                self.assertEqual(422, invalid.status_code)
            self.assertEqual(3, len(calls))

    def test_report_limit_and_rights_failure_keep_distinct_content_free_diagnostics(self):
        failure = {"code": "corpus-report-limit"}

        def create_report(*_args, **_kwargs):
            raise CorpusProblem(failure["code"])

        command = {"root": "C:/synthetic-project", "commandId": "01900000-0000-7000-8000-000000000022"}
        with self.client(self.application(SimpleNamespace(create_report=create_report))) as client:
            for internal, status, public in (
                ("corpus-report-limit", 409, "RO-CORE-CORPUS-REPORT-LIMIT"),
                ("corpus-rights-denied", 403, "RO-CORE-CORPUS-DENIED"),
                ("corpus-report-integrity-invalid", 500, "RO-CORE-CORPUS-INTEGRITY-FAILED"),
            ):
                failure["code"] = internal
                result = client.post("/projects/corpus/reports/create", json=command)
                self.assertEqual((status, public), (result.status_code, result.json()["code"]))
                self.assertNotIn(command["root"], result.text)
