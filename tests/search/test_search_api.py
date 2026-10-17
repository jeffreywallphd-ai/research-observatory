"""Search transport DTOs and byte bounds; no claim of a Native principal proof."""

import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.lexical_search_api import register_search_routes  # noqa: E402
from research_observatory_core.transport import CoreProblem, TraceCorrelationMiddleware  # noqa: E402


class SearchApiTests(unittest.TestCase):
    def client(self, service=None):
        app = FastAPI()

        app.add_middleware(TraceCorrelationMiddleware)

        @app.exception_handler(CoreProblem)
        async def problem(_request, error):
            from fastapi.responses import JSONResponse

            return JSONResponse(error.problem.model_dump(mode="json", by_alias=True), status_code=error.problem.status)

        register_search_routes(app, lambda _request: service)
        return TestClient(app)

    def test_validation_is_explicit_and_returns_content_free_locations_for_failure(self):
        with self.client() as client:
            response = client.post(
                "/projects/search/validate", json={"query": 'title:"synthetic phrase" AND year>=2020'}
            )
            self.assertEqual(200, response.status_code)
            self.assertTrue(response.json()["valid"])
            self.assertIn("originalQuery", response.json())
            self.assertIsInstance(response.json()["queryDocument"], str)
            failed = client.post("/projects/search/validate", json={"query": "privateunknown:secret"})
            self.assertEqual(200, failed.status_code)
            self.assertFalse(failed.json()["valid"])
            self.assertNotIn("secret", failed.text)
            self.assertIn("start", failed.json()["diagnostic"])
            self.assertEqual(
                422, client.post("/projects/search/validate", json={"query": "x", "actorId": "forged"}).status_code
            )
            self.assertEqual(422, client.post("/projects/search/validate", json={"query": "x" * 8193}).status_code)

    def test_run_transport_rejects_claimed_actor_and_oversized_body_before_service(self):
        class Service:
            def submit(self, *_args, **_kwargs):
                raise AssertionError("invalid command reached service")

        body = {
            "root": "synthetic",
            "projectId": "0199e895-0000-7000-8000-000000000001",
            "commandId": "0199e895-0000-7000-8000-000000000002",
            "query": "synthetic",
        }
        with self.client(Service()) as client:
            self.assertEqual(
                422, client.post("/projects/search/run", json={**body, "actorId": body["commandId"]}).status_code
            )
            response = client.post(
                "/projects/search/run", content=b" " * (256 * 1024 + 1), headers={"content-type": "application/json"}
            )
            self.assertEqual(413, response.status_code)


if __name__ == "__main__":
    unittest.main()
