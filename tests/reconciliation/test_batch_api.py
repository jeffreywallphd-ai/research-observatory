"""Authenticated request, durable worker and historical candidate-page journey."""

import unittest

from research_observatory_core.domain_contracts import new_uuid_v7

from tests.reconciliation import test_batch_worker as fixtures


class BatchApiTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.BatchWorkerTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.client = self.enterContext(self.f.client())

    def post(self, route, **values):
        return self.client.post("/projects/reconciliation/" + route, json={"root": self.f.root, **values})

    def test_prepare_schedule_inspect_replay_and_foreign_request_denial(self):
        prepared = self.post("batches/prepare")
        self.assertEqual(200, prepared.status_code, prepared.text)
        request = prepared.json()["requestId"]
        scheduled = self.post("batches/schedule", requestId=request)
        self.assertEqual(200, scheduled.status_code, scheduled.text)
        self.assertEqual("runnable", scheduled.json()["state"])
        self.assertIsNone(scheduled.json()["setRevisionId"])
        job = scheduled.json()["jobId"]
        self.f.service.run_pending()
        status = self.post("batches/status", requestId=request, jobId=job)
        self.assertEqual(200, status.status_code, status.text)
        self.assertEqual("succeeded", status.json()["state"])
        revision = status.json()["setRevisionId"]
        page = self.post("candidates", setRevisionId=revision, after=0, limit=1)
        self.assertEqual(200, page.status_code, page.text)
        self.assertEqual("no-store", page.headers["cache-control"])
        self.assertEqual(2, page.json()["recordCount"])
        self.assertEqual("unchanged", page.json()["membershipState"])
        self.assertEqual(7, len(page.json()["items"][0]["features"]))
        self.assertEqual(status.json(), self.post("batches/schedule", requestId=request).json())
        self.assertEqual(403, self.post("batches/status", requestId=new_uuid_v7(), jobId=job).status_code)
        self.assertEqual(422, self.post("candidates", setRevisionId=revision, after=0, limit=101).status_code)
        self.assertEqual(422, self.post("batches/prepare", actorId=new_uuid_v7()).status_code)

    def test_cancelled_batch_has_no_candidate_output(self):
        request = self.post("batches/prepare").json()["requestId"]
        job = self.post("batches/schedule", requestId=request).json()["jobId"]
        cancelled = self.post("batches/cancel", requestId=request, jobId=job)
        self.assertEqual(200, cancelled.status_code, cancelled.text)
        self.assertEqual("cancelled", cancelled.json()["state"])
        self.assertIsNone(cancelled.json()["setRevisionId"])
