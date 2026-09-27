"""Authenticated version decisions over actual project, Intent and import owners."""

import unittest

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.versions import version_digest

from tests.reconciliation import test_batch_worker as fixtures


class VersionApiTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.BatchWorkerTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.client = self.enterContext(self.f.client())
        request = self.f.service.prepare_batch(self.f.root, trace_id="a" * 32)
        self.f.service.schedule_batch(self.f.root, request, trace_id="a" * 32)
        self.f.service.run_pending()

    def post(self, route, **values):
        return self.client.post("/projects/reconciliation/versions/" + route, json={"root": self.f.root, **values})

    def ok(self, route, **values):
        response = self.post(route, **values)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("no-store", response.headers["cache-control"])
        return response.json()

    def test_work_inventory_version_preference_exact_retry_and_history(self):
        page = self.ok("works", after=None, limit=1)
        self.assertEqual(1, len(page["items"]))
        self.assertIsNone(page["nextAfter"])
        work = page["items"][0]
        context = self.ok("context", workIds=[work["workId"]])
        self.assertEqual([], context["versions"])
        self.assertEqual("not-reported", context["preferenceStates"][0]["state"])
        self.assertEqual(
            context["contextSha256"],
            version_digest({key: value for key, value in context.items() if key != "contextSha256"}),
        )
        plan = dict(
            schemaVersion="1.0",
            action="register",
            workIds=[work["workId"]],
            contextSha256=context["contextSha256"],
            rationale="Synthetic explicit manifestation classification",
            definition=dict(
                kind="version-of-record",
                assertionRevisionIds=work["assertionRevisionIds"],
                date=dict(precision="not-reported", value=None),
            ),
            version=None,
            relation=None,
            previousPreferenceRevisionId=None,
        )
        preview = self.ok("preview", plan=plan)
        command = dict(commandId=preview["commandId"], plan=plan, expectedPreviewSha256=preview["previewSha256"])
        outcome = self.ok("commit", command=command)
        self.assertEqual(outcome, self.ok("commit", command=command))
        version = outcome["versionRevisions"][0]
        inspected = self.ok("inspect", revisionId=version["revisionId"])
        self.assertEqual("version-of-record", inspected["definition"]["kind"])
        context = self.ok("context", workIds=[work["workId"]])
        preferred = dict(
            plan, action="prefer", contextSha256=context["contextSha256"], definition=None, version=version
        )
        preview = self.ok("preview", plan=preferred)
        choice = self.ok(
            "commit",
            command=dict(
                commandId=preview["commandId"], plan=preferred, expectedPreviewSha256=preview["previewSha256"]
            ),
        )
        current = self.ok("context", workIds=[work["workId"]])
        self.assertEqual("current", current["preferenceStates"][0]["state"])
        self.assertEqual(choice["preferenceRevisionId"], current["preferenceStates"][0]["preferenceRevisionId"])
        self.assertEqual(409, self.post("commit", command=dict(command, commandId=new_uuid_v7())).status_code)
        self.assertEqual(422, self.post("preview", plan=preferred, actorId=new_uuid_v7()).status_code)
        self.assertEqual(422, self.post("works", after=None, limit=33).status_code)
        self.f.f.projects.close(root=self.f.root, trace_id="a" * 32)
        self.assertNotEqual(200, self.post("context", workIds=[work["workId"]]).status_code)
