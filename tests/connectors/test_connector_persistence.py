"""Actual SQLCipher/object-envelope proofs with isolated in-memory test keys."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connector_repository import ConnectorRepository  # noqa: E402
from research_observatory_core.connectors.broker import ConnectorBroker, ProviderRateController  # noqa: E402
from research_observatory_core.connectors.providers import ProviderProblem, map_response  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.credential_store import SecretKind, SecretReference  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    configure_protected_database_provider,
    initialize_database,
    open_canonical_database,
)

from tests.connectors.test_connector_broker import Authority, Cancellation, Clock, Secrets  # noqa: E402
from tests.connectors.test_connector_transport import BytesStream  # noqa: E402
from tests.connectors.test_scholarly_mapping import NOW, fixture, request, search  # noqa: E402
from tests.data.test_encrypted_object_store import MemoryKeyProvider  # noqa: E402
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402


class ConnectorPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-connector-synthetic-")
        self.root = Path(self.temporary.name).resolve()
        for name in ("state", "objects", ".tmp"):
            (self.root / name).mkdir()
        self.database = self.root / "state/project.sqlite3"
        self.authority = Authority()
        self.project = self.authority.stamp.project_id
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        initialized = initialize_database(self.database, project_id=self.project, project_created_at=NOW)
        self.assertTrue(initialized.ok, initialized.errors)
        self.keys = MemoryKeyProvider({"synthetic-key": b"s" * 32}, "synthetic-key")
        self.repo = self.repository()

    def tearDown(self):
        if os.name == "nt":
            subprocess.run(
                [
                    str(Path(os.environ["SYSTEMROOT"]) / "System32/icacls.exe"),
                    self.temporary.name,
                    "/reset",
                    "/t",
                    "/c",
                    "/q",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        self.temporary.cleanup()

    def repository(self):
        return ConnectorRepository(
            self.database, self.project, create_local_object_store(self.root, self.project, key_provider=self.keys)
        )

    def page(self, value=None, document=None):
        value = value or request("openalex", query=search())
        body = json.dumps(document or fixture("openalex"), separators=(",", ":")).encode()
        clock = Clock()
        broker = ConnectorBroker(
            authority=self.authority,
            repository=self.repo,
            rates=ProviderRateController(clock=clock.monotonic),
            now=clock.now,
        )
        page = broker._page(
            value,
            broker._rates.bucket("openalex"),
            mapped=map_response(value, json.loads(body), retrieved_at=NOW),
            retrieved_at=NOW,
            body=body,
            retain=True,
        )
        return page, body

    def publish(self, page, body, stamp=None):
        return self.repo.publish(
            page, body=body, etag='"synthetic"', last_modified=None, authority=stamp or self.authority.stamp
        )

    def test_encrypted_restart_idempotence_and_source_handoff(self):
        page, body = self.page()
        self.assertEqual(page, self.publish(page, body))
        self.repo = self.repository()
        self.assertEqual(page, self.repo.replay(page.request))
        self.assertEqual(page, self.publish(page, body))
        checkpoint = self.repo.checkpoint(page.request)
        self.assertIsNotNone(checkpoint)
        assert checkpoint is not None
        self.assertEqual(page, checkpoint[1])
        self.assertEqual(page.records[0], self.repo.source_record(checkpoint[0], 0))
        cached = self.repo.cached(page.request)
        assert cached is not None
        self.assertEqual(body, cached.body)
        self.assertEqual(hashlib.sha256(body).hexdigest(), page.response.object_sha256)
        self.assertNotEqual(self.database.read_bytes()[:16], b"SQLite format 3\x00")
        for path in (self.root / "objects").rglob("*"):
            if path.is_file():
                self.assertNotIn(b"synthetic topic", path.read_bytes())
                self.assertNotIn(b"synthetic-adapter", path.read_bytes())

    def test_cache_hits_do_not_renew_remote_validation_and_preserve_redaction(self):
        calls = []
        document = fixture("openalex") | {"echo": "private-key-sentinel"}

        async def respond(wire):
            calls.append(wire)
            response = httpx2.Response(200, json=document, headers={"ETag": '"synthetic"'})
            if len(calls) == 2:
                self.assertEqual('"synthetic"', wire.headers["if-none-match"])
                response = httpx2.Response(304)
            return httpx2.Response(response.status_code, headers=response.headers, stream=BytesStream(response.content))

        clock = Clock()
        broker = ConnectorBroker(
            authority=self.authority,
            repository=self.repo,
            rates=ProviderRateController(clock=clock.monotonic),
            transport=httpx2.MockTransport(respond),
            credentials=Secrets(),
            key_references={"openalex": SecretReference("local", SecretKind.PROVIDER_KEY, "openalex", "api-key")},
            now=clock.now,
            sleep=clock.sleep,
        )
        value = request("openalex", query=search())
        value = type(value).model_validate(
            value.model_dump()
            | {"policy": value.policy.model_dump() | {"cache_mode": "allow-fresh", "maximum_fresh_age_ms": 5000}}
        )
        first = asyncio.run(broker.fetch(value, cancellation=Cancellation()))
        self.assertEqual("applied", first.response.redaction)
        for seconds, expected in ((4, "hit"), (8, "revalidated"), (12, "hit")):
            with self.subTest(seconds=seconds):
                clock.seconds = seconds
                checkpoint = self.repo.checkpoint(value)
                self.authority.stamp = replace(self.authority.stamp, expected_checkpoint_revision_id=checkpoint[0])
                value = type(value).model_validate(value.model_dump() | {"invocation_id": new_uuid_v7()})
                page = asyncio.run(broker.fetch(value, cancellation=Cancellation()))
                self.assertEqual(expected, page.cache.state)
                self.assertEqual("applied", page.response.redaction)
                self.assertEqual(first.retrieved_at, page.retrieved_at)
        self.assertEqual(2, len(calls))
        restarted = self.repository().cached(value)
        self.assertEqual("2026-01-01T00:00:08.000Z", restarted.validated_at)
        self.assertNotIn(b"private-key-sentinel", restarted.body)
        asyncio.run(broker.aclose())

    def test_fault_rolls_back_observation_and_checkpoint_then_retries(self):
        page, body = self.page()
        with (
            patch.object(self.repo, "_write_pointer", side_effect=OSError("synthetic fault")),
            self.assertRaises(ProviderProblem),
        ):
            self.publish(page, body)
        self.repo = self.repository()
        self.assertIsNone(self.repo.replay(page.request))
        self.assertIsNone(self.repo.checkpoint(page.request))
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as connection:
            self.assertEqual(0, connection.execute("SELECT count(*) FROM aggregate_revisions").fetchone()[0])
        self.publish(page, body)
        self.assertEqual(page, self.repo.replay(page.request))

    def test_checkpoint_compare_and_swap_and_invocation_collision(self):
        page, body = self.page()
        self.publish(page, body)
        checkpoint = self.repo.checkpoint(page.request)
        assert checkpoint is not None
        following = type(page.request).model_validate(
            page.request.model_dump() | {"invocation_id": new_uuid_v7(), "cursor": page.next_cursor}
        )
        document = fixture("openalex")
        document["meta"]["next_cursor"] = None
        next_page, next_body = self.page(following, document)
        with self.assertRaises(ProviderProblem):
            self.publish(next_page, next_body)
        self.assertEqual(checkpoint, self.repo.checkpoint(page.request))
        self.publish(next_page, next_body, replace(self.authority.stamp, expected_checkpoint_revision_id=checkpoint[0]))
        self.assertEqual(next_page, self.repository().checkpoint(page.request)[1])
        changed = type(page.request).model_validate(page.request.model_dump() | {"query": search(text="different")})
        with self.assertRaises(ProviderProblem):
            self.repo.replay(changed)

    def test_failed_page_does_not_advance_checkpoint_and_cross_project_is_denied(self):
        page, body = self.page()
        self.publish(page, body)
        checkpoint = self.repo.checkpoint(page.request)
        assert checkpoint is not None
        clock = Clock()
        broker = ConnectorBroker(
            authority=self.authority,
            repository=self.repo,
            rates=ProviderRateController(clock=clock.monotonic),
            now=clock.now,
        )
        failed_request = type(page.request).model_validate(page.request.model_dump() | {"invocation_id": new_uuid_v7()})
        failed = broker._page(failed_request, broker._rates.bucket("openalex"), error="timeout")
        self.publish(failed, None, replace(self.authority.stamp, expected_checkpoint_revision_id=checkpoint[0]))
        self.assertEqual(checkpoint, self.repo.checkpoint(page.request))
        changed = type(page.request).model_validate(page.request.model_dump() | {"project_id": new_uuid_v7()})
        with self.assertRaises(ProviderProblem):
            self.repo.replay(changed)


if __name__ == "__main__":
    unittest.main()
