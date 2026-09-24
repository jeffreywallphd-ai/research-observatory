"""Four-provider broker admission with isolated real private settings."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.settings import ConnectorSettings  # noqa: E402
from research_observatory_core.ports.credential_store import SecretAuditEvent  # noqa: E402
from research_observatory_core.windows_credentials import WindowsCredentialStore  # noqa: E402

from tests.connectors import test_connector_broker as broker_fixtures  # noqa: E402
from tests.connectors.test_connector_settings import CONTACT, CONTEXT, KEY  # noqa: E402
from tests.connectors.test_graph_oa_mapping import PAPER, graph_request, oa_document, oa_request, paper  # noqa: E402


@unittest.skipUnless(os.name == "nt", "Windows DPAPI private configuration")
class GraphOaBrokerTests(broker_fixtures.ConnectorBrokerFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix="ro-graph-broker-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.events: list[SecretAuditEvent] = []
        self.settings = ConnectorSettings(
            WindowsCredentialStore(Path(self.temp.name) / "vault", audit_sink=self.events.append)
        )

    async def test_public_adapter_description_tracks_current_private_configuration(self):
        from research_observatory_core.connectors.adapters import scholarly_adapters

        broker = self.broker([], settings=self.settings)
        adapter = next(value for value in scholarly_adapters(broker) if value.describe().provider_id == "unpaywall")
        self.assertEqual("not-configured", adapter.describe().configuration)
        self.settings.replace("unpaywall", key=None, contact=CONTACT, expected_version=None, context=CONTEXT)
        self.assertEqual("ready", adapter.describe().configuration)
        self.assertEqual([], self.calls)

    async def test_required_configuration_and_policy_are_checked_before_network(self):
        broker = self.broker([], settings=self.settings)
        page = await broker.fetch(oa_request(), cancellation=self.cancel)
        self.assertEqual("not-configured", page.errors[0].code)
        self.assertEqual([], self.calls)
        self.authority.denied = True
        self.events.clear()
        page = await broker.fetch(graph_request(), cancellation=self.cancel)
        self.assertEqual("policy-denied", page.errors[0].code)
        self.assertEqual([], self.events)

    async def test_unpaywall_contact_is_injected_and_encoded_echo_is_redacted(self):
        self.settings.replace("unpaywall", key=None, contact=CONTACT, expected_version=None, context=CONTEXT)
        document = oa_document() | {"future": {CONTACT: "https://example.invalid/?email=synthetic%40example.invalid"}}

        def response(wire):
            self.assertEqual(CONTACT, wire.url.params["email"])
            self.assertNotIn("mailto", wire.url.params)
            return httpx2.Response(200, json=document)

        broker = self.broker([response], settings=self.settings)
        page = await broker.fetch(oa_request(), cancellation=self.cancel)
        self.assertEqual("complete", page.outcome)
        self.assertEqual("applied", page.response.redaction)
        self.assertNotIn(CONTACT, page.model_dump_json())
        self.assertNotIn("synthetic%40example.invalid", page.model_dump_json())
        self.assertEqual(1, len(page.records))

    async def test_recommendation_body_and_key_header_rotation_on_retry(self):
        first = self.settings.replace("semantic-scholar", key=KEY, contact=None, expected_version=None, context=CONTEXT)
        second_key = KEY + "-rotated"

        def rotate(wire):
            self.assertEqual(KEY, wire.headers["x-api-key"])
            self.settings.replace(
                "semantic-scholar", key=second_key, contact=None, expected_version=first.version, context=CONTEXT
            )
            return httpx2.Response(429, headers={"Retry-After": "1"})

        def success(wire):
            self.assertEqual("POST", wire.method)
            self.assertEqual(second_key, wire.headers["x-api-key"])
            self.assertNotIn(second_key, str(wire.url))
            self.assertEqual({"positivePaperIds": [PAPER], "negativePaperIds": []}, json.loads(wire.content))
            return httpx2.Response(200, json={"recommendedPapers": [paper() | {"future": second_key}]})

        value = graph_request(
            {
                "kind": "recommendations",
                "positiveSeeds": [{"scheme": "semantic-scholar", "value": PAPER}],
                "negativeSeeds": [],
            }
        )
        page = await self.broker([rotate, success], settings=self.settings).fetch(value, cancellation=self.cancel)
        self.assertEqual("complete", page.outcome)
        self.assertEqual(2, len(self.calls))
        self.assertNotIn(KEY, page.model_dump_json())

    async def test_cleared_required_contact_denies_cache_and_new_observation_replay(self):
        configured = self.settings.replace(
            "unpaywall", key=None, contact=CONTACT, expected_version=None, context=CONTEXT
        )
        value = oa_request()
        value = type(value).model_validate(
            value.model_dump()
            | {"policy": value.policy.model_dump() | {"cache_mode": "allow-fresh", "maximum_fresh_age_ms": 5000}}
        )
        broker = self.broker([httpx2.Response(200, json=oa_document())], settings=self.settings)
        first = await broker.fetch(value, cancellation=self.cancel)
        self.assertEqual("complete", first.outcome)
        self.settings.replace("unpaywall", key=None, contact=None, expected_version=configured.version, context=CONTEXT)
        for replay in (None, first):
            with patch.object(self.repository, "replay", return_value=replay):
                denied = await broker.fetch(value, cancellation=self.cancel)
            self.assertEqual("not-configured", denied.errors[0].code)
        self.assertEqual(1, len(self.calls))
        self.assertEqual([first], self.repository.pages)

    async def test_null_graph_edge_is_failure_without_partial_success_publication(self):
        value = graph_request(
            {"kind": "citations", "seed": {"scheme": "semantic-scholar", "value": PAPER}, "direction": "citations"}
        )
        response = {"offset": 0, "data": [{"citingPaper": paper()}, {"citingPaper": None}]}
        value = type(value).model_validate(value.model_dump() | {"page_size": 2})
        page = await self.broker([httpx2.Response(200, json=response)], settings=self.settings).fetch(
            value, cancellation=self.cancel
        )
        self.assertEqual("incompatible-response", page.errors[0].code)
        self.assertEqual((), page.records)
        self.assertTrue(all(saved.outcome == "failed" for saved in self.repository.pages))
